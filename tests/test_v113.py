"""v1.13.0: wheel cycles and performance stats."""
import datetime as dt

from ghost_trader import timeutil, wheel
from tests.conftest import at, q
from tests.test_ledger import SP, start


def sell_call(led, exp, k, px, S=58):
    led.place({"action": "sell_to_open", "type": "call", "expiry": exp, "strike": k, "qty": 1, "price": px}, q(px - .05, px + .05), S)


def test_full_wheel_cycle(led):
    start(led)
    led.place(SP(strike=58, expiry="2026-11-06", price=2.10), q(2.0, 2.2), 56)
    timeutil.freeze(at(2026, 11, 6, 17, 5))
    led.settle_expiration(dt.date(2026, 11, 6), 57.0)                # assigned: 100 sh @ 58
    sell_call(led, "2026-11-13", 59, 1.00)
    timeutil.freeze(at(2026, 11, 13, 17, 5))
    led.settle_expiration(dt.date(2026, 11, 13), 58.0)               # call expires worthless
    sell_call(led, "2026-11-20", 59, 1.00)
    timeutil.freeze(at(2026, 11, 20, 17, 5))
    cs = wheel.cycles(led, 57.0)
    assert len(cs) == 1 and cs[0]["open"] and cs[0]["stage"] == "Covered call"   # shares still held, call open
    led.settle_expiration(dt.date(2026, 11, 20), 61.0)               # called away at 59
    c = wheel.cycles(led, 61.0)[0]
    assert not c["open"] and c["outcome"] == "Called away"
    assert c["put_c"] == 21000 and c["call_c"] == 20000 and c["share_c"] == 10000     # +$210, +$100 +$100, (59-58)*100
    assert c["pnl_c"] == 51000 and c["win"] and c["calls"] == 2
    assert c["ret"] == 51000 / 580000 and c["days"] == 18      # Nov 2 (put sold) to Nov 20
    assert [s["text"].split(":")[0] for s in c["steps"]][:2] == ["Sold 1 × $58 put", "Assigned"]
    s = wheel.summary([c])
    assert s["closed"] == 1 and s["wins"] == 1 and s["win_rate"] == 1 and s["pnl_c"] == 51000 and s["wheels"] == 1


def test_open_put_and_expired_put_cycles(led):
    start(led)
    led.place(SP(strike=50, expiry="2026-11-06", price=0.80), q(.75, .85), 56)
    led.place(SP(strike=52, expiry="2026-11-20", price=1.00), q(.95, 1.05), 56)
    timeutil.freeze(at(2026, 11, 6, 17, 5))
    led.settle_expiration(dt.date(2026, 11, 6), 57.2)
    cs = wheel.cycles(led, 57.2)
    assert [c["open"] for c in cs] == [False, True]
    assert cs[0]["outcome"] == "Put expired worthless" and cs[0]["pnl_c"] == 8000
    assert cs[1]["stage"] == "Short put" and cs[1]["pnl_c"] == 10000
    s = wheel.summary(cs)
    assert s["open"] == 1 and s["closed"] == 1 and s["wheels"] == 0 and s["open_pnl_c"] == 10000


def test_put_closed_early_at_a_loss_is_not_a_win(led):
    start(led)
    r = led.place(SP(strike=55, expiry="2026-11-20", price=1.00), q(.95, 1.05), 56)
    led.place({"action": "buy_to_close", "position_id": r["position_id"], "qty": 1, "price": 2.0}, q(1.95, 2.05), 53)
    c = wheel.cycles(led, 53)[0]
    assert c["outcome"] == "Put closed early" and c["pnl_c"] < 0 and not c["win"]
    assert wheel.summary([c])["win_rate"] == 0


def test_stats(led):
    start(led)
    led.place(SP(strike=50, expiry="2026-11-06", price=0.80), q(.75, .85), 56)
    timeutil.freeze(at(2026, 11, 6, 17, 5))
    led.settle_expiration(dt.date(2026, 11, 6), 57.2)
    st = wheel.stats(led, snaps=[{"day": d, "account_value_c": v} for d, v in
                                 [("2026-11-02", 100), ("2026-11-03", 110), ("2026-11-04", 99), ("2026-11-05", 104), ("2026-11-06", 111)]])
    assert st["win_rate"] == 1 and st["avg_kept"] == 1.0 and st["closed_options"] == 1
    assert abs(st["per_1k"] - 0.8 * 100 / (50 * 100) * 1000) < 1e-6
    assert abs(st["max_dd"] - (99 / 110 - 1)) < 1e-9 and st["dd_recovered"] and st["dd_recover_days"] == 2
