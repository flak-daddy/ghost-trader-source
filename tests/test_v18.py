"""v1.8.0: saved chart ranges, outcomes range, position-panel chances (now and at open), mark-as-read."""
import json
import time

from ghost_trader.api import App
from ghost_trader.market import DemoProvider
from tests.conftest import at, q


def ready(home):
    a = App(demo=True, provider=DemoProvider())
    a.api_loaded()
    t0 = time.time()
    while a.api_startup_status()["state"] not in ("done", "issue") and time.time() - t0 < 20:
        time.sleep(0.05)
    s = a.api_startup_status()
    if s["state"] == "issue":
        a.api_startup_resolve(issue_id=s["issue"]["id"], choice="skip", value=None)
        while a.api_startup_status()["state"] != "done" and time.time() - t0 < 20:
            time.sleep(0.05)
    a.api_start_run(cash="$100,000.00")
    return a


def test_ranges_saved_and_validated(home):
    a = ready(home)
    a.api_settings_set(ind_ranges={"st": "1M", "px": "bogus", "nope": "5Y"})
    assert a.settings.get("ind_ranges") == {"px": "3M", "st": "1M", "mood": "3M", "vol": "3M"}
    assert a.api_settings_set(out_range="2Y")["error"]
    a.api_settings_set(out_range="1Y")
    b = a.api_boot()
    assert b["ind_ranges"]["st"] == "1M" and b["out_range"] == "1Y"
    assert not a.db.val("SELECT COUNT(*) FROM events WHERE kind='Settings'")   # range clicks aren't logged


def test_position_panel_chances_now_and_at_open(home):
    a = ready(home)
    c = a.api_chain()
    o = {"action": "sell_to_open", "type": "put", "expiry": c["expiry"], "strike": float(round(c["price"]) - 4), "qty": 1}
    t = a.api_ticket(o)
    r = a.api_place({**o, "price": t["default_fill"]})
    p = a.api_position(r["position_id"])
    assert p["chances"]["worthless"] > 0 and p["chances_open"]["worthless"] == t["chances"]["worthless"]
    assert 0 < p["ret"] < 1 and p["ann"] > p["ret"] and p["days_total"] >= 1
    assert p["ret"] == round(t["ret"], 12) or abs(p["ret"] - t["ret"]) < 0.002   # same as the ticket said at open


def test_outcomes_range_filters_by_open_date(home):
    a = ready(home)
    led = a.led
    for when in (at(2026, 9, 1, 10), at(2026, 11, 9, 10)):
        r = led.place({"action": "sell_to_open", "type": "put", "expiry": "2026-11-13", "strike": 50, "qty": 1,
                       "price": 1.0}, q(.95, 1.05), 55.0, ts=when)
        a.db.x("INSERT INTO trade_readings(event_id,asof,data) VALUES(?,?,?)",
               (r["event_id"], "x", json.dumps({"stoch14_k": 50})))
    led.settle_expiration("2026-11-13", 56.0, ts=at(2026, 11, 13, 17, 5))
    assert a.api_outcomes(range="1M")["total"] == 1
    assert a.api_outcomes(range="1Y")["total"] == 2
    assert a.api_outcomes(range="14D")["range"] == "14D"


def test_mark_read_clears_badge_and_banner(home):
    a = ready(home)
    a.led.event("Error", "Something failed", error=True)
    a.startup.warnings.append("Quotes: used last good quotes")
    s = a.api_state()
    assert s["errors"] == 1 and s["warnings"]
    a.api_mark_read()
    s = a.api_state()
    assert s["errors"] == 0 and s["warnings"] == []
    a.led.event("Error", "Another failure", error=True)
    assert a.api_state()["errors"] == 1          # new errors show again
