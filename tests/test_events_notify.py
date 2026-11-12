import datetime as dt

from ghost_trader import events, marketcal, notify, timeutil
from ghost_trader.api import App

from .conftest import at, q


def test_event_schedule_shape():
    assert len(events.FOMC) == 16 and len(events.CPI) == 24 and len(events.JOBS) == 24
    every = list(events.FOMC) + events.CPI + events.JOBS
    assert all(d.weekday() < 5 for d in every)
    # BLS can publish on a market holiday (the March 2026 jobs report came out on Good Friday).
    assert [d for d in every if not marketcal.is_trading_day(d)] == [dt.date(2026, 4, 3)]
    nov = events.events_between(dt.date(2026, 11, 1), dt.date(2026, 11, 30))
    assert [(e["day"].day, e["kind"]) for e in nov] == [(6, "jobs"), (10, "cpi")]
    dec = events.events_between(dt.date(2026, 12, 1), dt.date(2026, 12, 31))
    fed = next(e for e in dec if e["kind"] == "fomc")
    assert fed["day"] == dt.date(2026, 12, 9) and "1:00 PM CT" in fed["name"] and "dot plot" in fed["name"]
    jan = events.events_between(dt.date(2027, 1, 1), dt.date(2027, 1, 31))
    assert any("December" in e["name"] for e in jan if e["kind"] == "cpi")
    assert any("tentative" in e["name"] for e in jan if e["kind"] == "fomc")


def test_calendar_shows_events(home):
    a = App(demo=True)
    c = a.api_calendar(month="2026-12")
    days = {d["day"]: d for w in c["weeks"] for d in w}
    assert [e["text"] for e in days["2026-12-09"]["events"]] == ["Fed 1:00 PM"]
    assert [e["text"] for e in days["2026-12-10"]["events"]] == ["CPI 7:30 AM"]
    assert [e["text"] for e in days["2026-12-04"]["events"]] == ["Jobs 7:30 AM"]
    assert c["events_note"] is None
    assert a.api_calendar(month="2028-01")["events_note"]


def test_calendar_ex_dividend(home):
    a = App(demo=True)
    a.provider.dividends = lambda: [(dt.date(2026, 12, 23), 0.0123)]
    a.provider.next_ex_dividend = lambda: None
    days = {d["day"]: d for w in a.api_calendar(month="2026-12")["weeks"] for d in w}
    ev = days["2026-12-23"]["events"][0]
    assert ev["kind"] == "exdiv" and "0.0123" in ev["tip"]


def test_nudge_message_and_daily_check(led, monkeypatch, tmp_path):
    timeutil.freeze(at(2026, 11, 2))
    led.start_run(100000, at(2026, 11, 2))
    led.place({"action": "sell_to_open", "type": "put", "expiry": "2026-11-13", "strike": 54, "qty": 2, "price": 1.1},
              q(1.0, 1.2), 56)
    led.place({"action": "sell_to_open", "type": "put", "expiry": "2026-11-20", "strike": 50, "qty": 1, "price": 0.5},
              q(.4, .6), 56)
    sent = []
    monkeypatch.setattr(notify, "send", lambda t, b: (sent.append((t, b)), (True, "Sent."))[1])
    assert notify.daily_check(led, lambda: 55.0, at(2026, 11, 12, 7, 45)) == "nothing expires today"
    r = notify.daily_check(led, lambda: 55.0, at(2026, 11, 13, 7, 45))
    assert "2 TQQQ contracts expire today" in r
    title, body = sent[0]
    assert "2 × $54 Put (short): TQQQ 55.00, 1.9% out of the money" in body
    assert notify.daily_check(led, lambda: 55.0, at(2026, 11, 13, 9, 0)) == "already notified today"
    assert len(sent) == 1
    assert notify.daily_check(led, lambda: 55.0, at(2026, 11, 14, 7, 45)) == "not a trading day"


def test_timer_units():
    service, timer = notify.unit_texts()
    assert "--notify" in service and "Type=oneshot" in service
    assert "OnCalendar=Mon..Fri 07:45 America/Chicago" in timer and "Persistent=true" in timer


def test_ensure_timer_skips_without_launcher(home):
    assert notify.ensure_timer() is None
