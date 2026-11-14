"""v1.12.0: Market tab (heavyweights, earnings impact) and calendar notes, events and reminders."""
import datetime as dt

from ghost_trader import notify, timeutil
from tests.test_v18 import ready


def test_market_payload(home):
    a = ready(home)
    m = a.api_market()
    assert m["qqq"]["price"] and m["tqqq"]["price"]
    assert [r["symbol"] for r in m["heavy"]] == list(a.EARNINGS) and all(r["cap"] for r in m["heavy"])
    assert len(m["earnings"]) == len(a.EARNINGS)
    a._earnh_thread.join(5)
    a._earn_thread.join(5)
    e = {r["symbol"]: r for r in a.api_market()["earnings"]}
    nv = e["NVDA"]
    assert nv["next"] and 1 <= len(nv["moves"]) <= 8 and nv["avg_abs"] is not None
    assert nv["worst"] <= nv["best"]


def test_earnings_move_is_close_before_to_close_after(home):
    a = ready(home)
    a.ind.refresh()
    bars = {b["day"]: b["close"] for b in a.ind.data["tqqq"]["value"]}
    a.db.x("DELETE FROM earnings WHERE symbol='NVDA'")
    from ghost_trader import marketcal
    d = marketcal.prev_trading_day(timeutil.today_ct() - dt.timedelta(days=20))
    a.db.x("INSERT INTO earnings(symbol, day) VALUES('NVDA', ?)", (d.isoformat(),))
    nv = next(r for r in a._earnings_impact() if r["symbol"] == "NVDA")
    want = bars[marketcal.next_trading_day(d).isoformat()] / bars[marketcal.prev_trading_day(d).isoformat()] - 1
    assert nv["moves"] == [{"day": d.isoformat(), "label": timeutil.fmt_date(d.isoformat()), "move": round(want, 4)}]


def test_notes_save_edit_delete_and_history(home):
    a = ready(home)
    day = (timeutil.today_ct() + dt.timedelta(days=3)).isoformat()
    assert a.api_note_save(day=day, kind="note", title="  ")["error"]
    assert a.api_note_save(day=day, kind="event", title="x", time="25:99")["error"]
    assert a.api_note_save(day=day, kind="bogus", title="x")["error"]
    n = a.api_note_save(day=day, kind="note", title="watch NVDA", remind="morning")["id"]
    e = a.api_note_save(day=day, kind="event", title="Review puts", time="2:30 PM", remind="daybefore")["id"]
    assert a.db.val("SELECT time FROM notes WHERE id=?", (e,)) == "14:30"
    cal = a.api_calendar(month=day[:7])
    cell = next(c for w in cal["weeks"] for c in w if c["day"] == day) if dt.date.fromisoformat(day).weekday() < 5 else None
    if cell:
        assert [x["title"] for x in cell["notes"]] == ["watch NVDA", "Review puts"]
        assert cell["notes"][1]["time_txt"] == "2:30 PM"
    assert a.api_note_save(id=n, day=day, kind="note", title="watch NVDA closely", remind="morning")["ok"]
    assert a.api_note_delete(id=e)["ok"] and a.api_note_delete(id=e)["error"]
    titles = [r[0] for r in a.db.q("SELECT title FROM events WHERE kind='Note' ORDER BY id")]
    assert titles[0].startswith("Note added for") and "Event added for" in titles[1] and "2:30 PM CT" in titles[1]
    assert titles[2].startswith("Note edited") and titles[3].startswith("Event deleted")
    from ghost_trader import csvout
    assert "Note added for" in csvout.history_csv(a.led, a.led.run_id())


def test_reminders_fire_once(home, monkeypatch):
    a = ready(home)
    sent = []
    monkeypatch.setattr(notify, "send", lambda t, b: (sent.append((t, b)), (True, "ok"))[1])
    mon = dt.date(2026, 11, 16)
    a.api_note_save(day=mon.isoformat(), kind="note", title="morning one", remind="morning")
    a.api_note_save(day=mon.isoformat(), kind="event", title="afternoon one", time="10:00", remind="daybefore")
    a.api_note_save(day=mon.isoformat(), kind="note", title="quiet", remind="none")
    fri_pm = dt.datetime(2026, 11, 13, 15, 30, tzinfo=timeutil.CT)       # Friday afternoon reminds for Monday
    assert notify.note_reminders(a.led, fri_pm) == 1 and "Monday 10:00 AM CT: afternoon one" in sent[-1][1]
    assert notify.note_reminders(a.led, fri_pm) == 0
    mon_am = dt.datetime(2026, 11, 16, 7, 45, tzinfo=timeutil.CT)
    assert notify.note_reminders(a.led, mon_am) == 1 and sent[-1][1].startswith("Today: morning one")
    assert notify.note_reminders(a.led, mon_am) == 0


def test_earnings_table_nearest_first_with_estimates(tmp_path, monkeypatch):
    monkeypatch.setenv("GHOST_TRADER_HOME", str(tmp_path))
    from ghost_trader.api import App
    a = App(demo=True)
    a.ind.refresh()
    a.api_market()
    for t in ("_earn_thread", "_earnh_thread"):
        th = getattr(a, t, None)
        if th:
            th.join(10)
    # like Yahoo right after a report: no date announced yet for two of them
    a.db.x("DELETE FROM earnings WHERE symbol IN ('AAPL','AMZN') AND day>=?", (timeutil.today_ct().isoformat(),))
    rows = a.api_market()["earnings"]
    dated = [r for r in rows if r["next"]]
    assert [r["next"] for r in dated] == sorted(r["next"] for r in dated)
    assert rows.index(dated[-1]) == len(dated) - 1          # undated ones (if any) come last
    est = [r for r in rows if r["est"]]
    assert {r["symbol"] for r in est} == {"AAPL", "AMZN"}
    assert all(r["days_to"] >= 0 for r in est)
    assert [r["symbol"] for r in rows] != list(a.EARNINGS)  # demo dates are out of list order


def test_cone_for_ticket_option(tmp_path, monkeypatch):
    monkeypatch.setenv("GHOST_TRADER_HOME", str(tmp_path))
    from ghost_trader.api import App
    a = App(demo=True)
    a.ind.refresh()
    ex = (timeutil.today_ct() + dt.timedelta(days=20)).isoformat()
    d = a.api_cone(days_back=30, type="put", strike=50, expiry=ex, iv=0.7)
    assert d["iv"] == 0.7 and d["iv_src"] == "this option's IV"
    assert len(d["positions"]) == 1
    p = d["positions"][0]
    assert p["strike"] == 50 and p["type"] == "put" and p["dte"] == 20 and "(this ticket)" in p["label"]
    assert d["horizon"] == 20
