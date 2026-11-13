"""v1.7.0: indicator alerts, end-of-day summary, ticket chances, readings vs. outcomes, earnings dates, chain volume,
auto-refresh and the new settings."""
import json
import time

import pytest

from ghost_trader import alerts, config, notify, timeutil
from ghost_trader.api import App
from ghost_trader.market import DemoProvider
from tests.conftest import at, q


def ready(home, **kw):
    a = App(demo=True, provider=DemoProvider(**kw))
    a.api_loaded()
    t0 = time.time()
    while a.api_startup_status()["state"] != "done" and time.time() - t0 < 20:
        time.sleep(0.05)
    return a


# ---------------------------------------------------------------- alerts
def test_alert_rules_cleaned():
    r = alerts.clean_rules([{"metric": "vix", "op": "above", "value": "30"}, {"metric": "nope", "op": "above", "value": 1},
                            {"metric": "fg", "op": "sideways", "value": 1}, {"metric": "fg", "op": "below"}])
    assert r == [{"id": "vix-above-30", "metric": "vix", "op": "above", "value": 30.0, "on": True}]


def test_alert_fires_once_per_crossing():
    rules = alerts.clean_rules([{"metric": "stoch14_k", "op": "below", "value": 20}])
    fired, st = alerts.evaluate({"stoch14_k": 15}, rules, {})
    assert len(fired) == 1
    fired, st = alerts.evaluate({"stoch14_k": 12}, rules, st)
    assert fired == []                                   # still below: no repeat
    fired, st = alerts.evaluate({"stoch14_k": None}, rules, st)
    assert fired == [] and st[rules[0]["id"]] is True    # no reading keeps the state
    fired, st = alerts.evaluate({"stoch14_k": 40}, rules, st)
    fired, st = alerts.evaluate({"stoch14_k": 18}, rules, st)
    assert len(fired) == 1                               # crossed again
    off = [{**rules[0], "on": False}]
    assert alerts.evaluate({"stoch14_k": 1}, off, {})[0] == []


def test_alert_check_sends_and_logs(led):
    led.start_run(100_000_00, at(2026, 11, 2))
    sent = []
    s = config.Settings()
    s.update(ind_alerts=[{"metric": "vix", "op": "above", "value": 30}, {"metric": "fg", "op": "below", "value": 25}])
    fired = alerts.check({"vix": 31.2, "fg": 20}, s, lambda t, b: (sent.append((t, b)), (True, "Sent."))[1], led)
    assert len(fired) == 2 and sent[0][0] == "2 TQQQ indicator alerts"
    assert "VIX is 31.20 (above 30)" in sent[0][1] and "Fear & Greed is 20 (below 25)" in sent[0][1]
    assert led.db.val("SELECT COUNT(*) FROM events WHERE kind='Alert'") == 1
    assert alerts.check({"vix": 31.5, "fg": 19}, s, lambda t, b: (True, ""), led) == []


# ---------------------------------------------------------------- end-of-day summary + timer
def test_timer_has_both_times():
    _, timer = notify.unit_texts()
    assert "OnCalendar=Mon..Fri 07:45 America/Chicago" in timer and "OnCalendar=Mon..Fri 15:30 America/Chicago" in timer


def test_eod_summary(led, monkeypatch):
    led.start_run(100_000, at(2026, 11, 9))
    led.place({"action": "sell_to_open", "type": "put", "expiry": "2026-11-13", "strike": 55, "qty": 1, "price": 1.10},
              q(1.05, 1.15), 56.0, ts=at(2026, 11, 12, 10))
    title, body = notify.eod_summary(led, 56.0, at(2026, 11, 12).date(), rate=4.0)
    assert title.startswith("Ghost Trader today: +$110.00")
    assert "Premium today $110.00" in body and "Expiring Nov 13: 1 contract ($55 Put ×1)" in body
    assert "\n" in body
    sent = []
    monkeypatch.setattr(notify, "send", lambda t, b: (sent.append(t), (True, "Sent."))[1])
    r = notify.daily_check(led, lambda: 56.0, at(2026, 11, 12, 15, 30), rate=4.0)
    assert "Ghost Trader today" in r and len(sent) == 1
    assert "already done today" in notify.daily_check(led, lambda: 56.0, at(2026, 11, 12, 15, 45))
    s = config.Settings()
    s.update(eod_summary=False)
    assert "end-of-day summary off" in notify.daily_check(led, lambda: 56.0, at(2026, 11, 13, 15, 30), settings=s)


# ---------------------------------------------------------------- ticket chances
def test_chances_math():
    c = App._chances("put", 54.19, 50, 2.11, 29, 0.67, 4.2)
    assert c["breakeven"] == 47.89 and c["profit"] == pytest.approx(0.718, abs=0.01)
    assert c["worthless"] == pytest.approx(0.637, abs=0.01) and c["profit"] > c["worthless"]
    cc = App._chances("call", 54.19, 58, 1.0, 14, 0.6, 4.2)
    assert cc["breakeven"] == 59.0 and cc["profit"] > cc["worthless"] > 0.5
    assert App._chances("put", 54, 50, 1, 10, None, 4) is None


def test_ticket_has_chances(home):
    a = ready(home)
    a.api_start_run(cash="$100,000.00")
    c = a.api_chain()
    t = a.api_ticket({"action": "sell_to_open", "type": "put", "expiry": c["expiry"], "strike": float(round(c["price"]) - 4),
                      "qty": 1})
    assert 0 < t["chances"]["worthless"] < t["chances"]["profit"] < 1
    v = [s["put"]["volume"] for s in c["strikes"] if s["put"] and s["put"]["bid"]]
    assert any(x > 0 for x in v)                          # chain volume passes through


# ---------------------------------------------------------------- readings vs. outcomes
def test_outcomes_grouping(home):
    a = ready(home)
    a.api_start_run(cash="$100,000.00")
    led = a.led
    ids = []
    for k, px, stoch in ((50, 1.0, 15), (52, 1.5, 15), (54, 2.0, 85)):
        r = led.place({"action": "sell_to_open", "type": "put", "expiry": "2026-11-13", "strike": k, "qty": 1, "price": px},
                      q(px - .05, px + .05), 55.0, ts=at(2026, 11, 9, 10))
        a.db.x("INSERT INTO trade_readings(event_id,asof,data) VALUES(?,?,?)",
               (r["event_id"], "x", json.dumps({"stoch14_k": stoch, "vix": 18, "fg": 40})))
        ids.append(r["position_id"])
    # close one for a loss, expire the others
    led.place({"action": "buy_to_close", "position_id": ids[0], "qty": 1, "price": 1.6}, q(1.55, 1.65), 55.0,
              ts=at(2026, 11, 10, 10))
    led.settle_expiration("2026-11-13", 56.0, ts=at(2026, 11, 13, 17, 5))
    o = a.api_outcomes(by="stoch14")
    low, mid, high = o["groups"]
    assert o["total"] == 3 and low["n"] == 2 and high["n"] == 1 and mid["n"] == 0
    assert low["win_rate"] == 0.5 and low["expired"] == 1 and high["expired"] == 1
    assert low["avg_result_c"] == round((-60_00 + 150_00) / 2)
    assert a.api_outcomes(by="fg")["groups"][1]["n"] == 3


# ---------------------------------------------------------------- earnings dates
def test_earnings_markers(home):
    a = ready(home)
    a._earnings_refresh()
    a._earn_thread.join(5)
    n = a.db.val("SELECT COUNT(*) FROM earnings")
    assert n == len(App.EARNINGS)
    assert a.db.val("SELECT value FROM meta WHERE key='earnings_checked'") == timeutil.today_ct().isoformat()
    day = a.db.val("SELECT day FROM earnings WHERE symbol='NVDA'")
    cal = a.api_calendar(month=day[:7])
    cells = [c for w in cal["weeks"] for c in w if c["day"] == day]
    assert any(e["kind"] == "earn" and "NVDA" in e["text"] for e in cells[0].get("events", []))
    a._earn_thread = None
    a._earnings_refresh()                                  # already checked today: no new thread
    assert a._earn_thread is None


# ---------------------------------------------------------------- settings + auto-refresh
def test_new_settings(home):
    a = ready(home)
    a.api_start_run(cash="$100,000.00")
    assert a.api_settings_set(auto_refresh=7)["error"]
    assert a.api_settings_set(auto_refresh=5)["settings"]["auto_refresh"] == 5
    a.api_settings_set(eod_summary=False, ind_alerts=[{"metric": "vix", "op": "above", "value": 30}, {"metric": "x"}])
    s = a.api_settings()
    assert s["settings"]["eod_summary"] is False and len(s["alerts"]["rules"]) == 1
    assert "VIX above 30" in a.db.val("SELECT detail FROM events WHERE kind='Settings' ORDER BY id DESC LIMIT 1")
    assert a.api_boot()["auto_refresh"] == 5


def test_refresh_open_respects_hours(home, monkeypatch):
    a = ready(home)
    monkeypatch.setattr("ghost_trader.marketcal.is_open", lambda ts: False)
    assert a.api_refresh_open()["closed"] is True
    monkeypatch.setattr("ghost_trader.marketcal.is_open", lambda ts: True)
    r = a.api_refresh_open()
    assert r["ok"] and r["asof"]
