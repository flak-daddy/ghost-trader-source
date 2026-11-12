import datetime as dt

import pytest

from ghost_trader import timeutil
from ghost_trader.ledger import TradeError, cents

from .conftest import at, q

SP = lambda **o: {"action": "sell_to_open", "type": "put", "expiry": "2026-11-20", "qty": 1, **o}  # noqa: E731


def start(led, cash=100000, when=at(2026, 11, 2)):
    timeutil.freeze(when)
    led.start_run(cash, when)


def test_start_run_once(led):
    start(led)
    assert led.balances() == (10000000, 0)
    with pytest.raises(TradeError):
        led.start_run(5)


def test_cash_secured_put_moves_collateral_and_premium(led):
    start(led)
    led.place(SP(strike=55, qty=2, price=1.65), q(1.60, 1.70), 56)
    a, c = led.balances()
    assert c == 1100000
    assert a == 10000000 - 1100000 + 33000
    assert led.premium_collected_c() == 33000


def test_collateral_cannot_come_from_premium(led):
    start(led, cash=5000)
    chk = led.check(SP(strike=50.5, price=0.40), q(.35, .45), 56)   # needs 5050, has 5000 (+40 premium)
    assert not chk["ok"] and "Not cash-secured" in chk["msg"]


def test_fill_must_be_within_bid_ask(led):
    start(led)
    assert "above the ask" in led.check(SP(strike=55, price=1.71), q(1.60, 1.70), 56)["msg"]
    assert "below the bid" in led.check(SP(strike=55, price=1.59), q(1.60, 1.70), 56)["msg"]
    assert led.check(SP(strike=55, price=1.60), q(1.60, 1.70), 56)["ok"]
    assert led.check(SP(strike=55, price=1.70), q(1.60, 1.70), 56)["ok"]
    with pytest.raises(TradeError):
        led.place(SP(strike=55, price=2), q(1.60, 1.70), 56)


def test_no_quote_no_trade(led):
    start(led)
    assert "can't be traded" in led.check(SP(strike=55, price=1), None, 56)["msg"]
    assert "can't be traded" in led.check(SP(strike=55, price=1), {"bid": 0, "ask": 0}, 56)["msg"]


def test_covered_call_needs_free_shares(led):
    start(led)
    call = {"action": "sell_to_open", "type": "call", "expiry": "2026-11-20", "strike": 60, "qty": 1, "price": 0.9}
    assert "Not covered" in led.check(call, q(.85, .95), 56)["msg"]
    led.place({"action": "buy_shares", "qty": 150, "price": 56}, q(56, 56), 56)
    led.place(call, q(.85, .95), 56)
    assert led.locked_shares() == 100 and led.free_shares() == 50
    assert "Not covered" in led.check(call, q(.85, .95), 56)["msg"]
    # locked shares can't be sold
    assert not led.check({"action": "sell_shares", "qty": 60, "price": 56}, q(56, 56), 56)["ok"]
    assert led.check({"action": "sell_shares", "qty": 50, "price": 56}, q(56, 56), 56)["ok"]


def test_account_value_excludes_option_marks(led):
    start(led)
    led.place(SP(strike=55, price=1.65), q(1.60, 1.70), 56)
    v1 = led.account_value_c(56)
    assert v1 == 10000000 + 16500       # cash + collateral; the short put's buy-back price isn't counted
    led.place({"action": "buy_shares", "qty": 100, "price": 56}, q(56, 56), 56)
    assert led.account_value_c(60) == v1 + 400 * 100


def test_sizing_warning_over_80_percent(led):
    start(led, cash=10000)
    chk = led.check(SP(strike=85, price=1), q(.9, 1.1), 56)
    assert chk["ok"] and chk["warn"] and "85.0%" in chk["warn"]
    assert led.check(SP(strike=79, price=1), q(.9, 1.1), 56)["warn"] is None


def test_buy_to_close_put_draws_from_collateral(led):
    start(led)
    r = led.place(SP(strike=55, qty=2, price=1.65), q(1.60, 1.70), 56)
    pid = r["position_id"]
    a0, c0 = led.balances()
    led.place({"action": "buy_to_close", "position_id": pid, "qty": 1, "price": 0.50}, q(.45, .55), 56)
    a1, c1 = led.balances()
    assert c1 == c0 - 550000
    assert a1 == a0 + 550000 - 5000
    p = led.position(pid)
    assert p["open_qty"] == 1 and p["status"] == "open" and p["collateral_c"] == 550000
    led.place({"action": "buy_to_close", "position_id": pid, "qty": 1, "price": 0.40}, q(.35, .45), 56)
    p = led.position(pid)
    assert p["status"] == "closed" and p["realized_c"] == 33000 - 5000 - 4000
    assert led.balances()[1] == 0


def test_expired_worthless_releases_collateral(led):
    start(led)
    led.place(SP(strike=50, expiry="2026-11-06", price=0.8), q(.75, .85), 56)
    timeutil.freeze(at(2026, 11, 6, 17, 1))
    assert led.due_expirations(timeutil.now()) == [dt.date(2026, 11, 6)]
    led.settle_expiration(dt.date(2026, 11, 6), 57.20)
    assert led.balances() == (10000000 + 8000, 0)
    assert not led.positions()


def test_assignment_at_one_cent_itm_and_called_away(led):
    start(led)
    led.place(SP(strike=58, expiry="2026-11-06", price=2.1), q(2.0, 2.2), 56)
    timeutil.freeze(at(2026, 11, 6, 17, 5))
    led.settle_expiration(dt.date(2026, 11, 6), 57.99)      # exactly $0.01 ITM -> assigned
    assert led.shares() == 100 and led.balances()[1] == 0
    assert led.balances()[0] == 10000000 - 580000 + 21000
    led.place({"action": "sell_to_open", "type": "call", "expiry": "2026-11-13", "strike": 59, "qty": 1, "price": 1.0},
              q(.95, 1.05), 58)
    timeutil.freeze(at(2026, 11, 13, 17, 5))
    led.settle_expiration(dt.date(2026, 11, 13), 59.005)    # less than a cent ITM -> expires
    assert led.shares() == 100 and led.locked_shares() == 0
    led.place({"action": "sell_to_open", "type": "call", "expiry": "2026-11-20", "strike": 59, "qty": 1, "price": 1.0},
              q(.95, 1.05), 58)
    timeutil.freeze(at(2026, 11, 20, 17, 5))
    led.settle_expiration(dt.date(2026, 11, 20), 61)
    assert led.shares() == 0
    kinds = [r[0] for r in led.db.q("SELECT kind FROM events ORDER BY id")]
    assert "Assigned" in kinds and "Called away" in kinds


def test_put_out_of_the_money_by_less_than_a_cent_expires(led):
    start(led)
    led.place(SP(strike=58, expiry="2026-11-06", price=2.1), q(2.0, 2.2), 56)
    timeutil.freeze(at(2026, 11, 6, 17, 5))
    led.settle_expiration(dt.date(2026, 11, 6), 57.995)
    assert led.shares() == 0


def test_long_options_off_by_default(led):
    start(led)
    o = {"action": "buy_to_open", "type": "call", "expiry": "2026-11-20", "strike": 60, "qty": 1, "price": 1}
    assert "off" in led.check(o, q(.95, 1.05), 56)["msg"]
    led.settings.update(long_options=True)
    assert led.check(o, q(.95, 1.05), 56)["ok"]


def test_interest_accrues_daily_and_posts_on_pay_date(led):
    start(led, cash=100000, when=at(2026, 10, 1))
    n, amt, evs = led.catch_up_interest(dt.date(2026, 10, 16), lambda d: 3.65)
    assert n == 15                     # Oct 1..15
    assert len(evs) == 1               # posted Oct 15 for Oct 1..14
    paid = led.interest_earned_c()
    assert paid == cents(100000 * 0.0365 / 365 * 14)
    # Oct 15 accrual is on the balance including the posted interest
    row = led.db.one("SELECT balance_c FROM accruals WHERE day='2026-10-15'")
    assert row[0] == 10000000 + paid
    assert round(led.accrued(), 6) == round((100000 + paid / 100) * 0.0365 / 365, 6)


def test_interest_includes_collateral_and_haircut(led):
    start(led, cash=100000, when=at(2026, 10, 1))
    led.place(SP(strike=55, price=1.0), q(.9, 1.1), 56)
    led.catch_up_interest(dt.date(2026, 10, 3), lambda d: 4.0, haircut=0.5)
    r = led.db.q("SELECT rate, balance_c FROM accruals ORDER BY day")
    assert r[0]["rate"] == 3.5 and r[0]["balance_c"] == 10000000 + 10000


def test_close_run_forced_payout(led):
    start(led, cash=100000, when=at(2026, 10, 1))
    led.catch_up_interest(dt.date(2026, 10, 10), lambda d: 4.0)
    acc = led.accrued()
    timeutil.freeze(at(2026, 10, 10, 12))
    led.pay_interest(dt.date(2026, 10, 10), force=True)
    assert led.accrued() == 0 and led.interest_earned_c() == cents(acc)


def test_dividend_credit_once(led):
    start(led)
    led.place({"action": "buy_shares", "qty": 100, "price": 56}, q(56, 56), 56)
    timeutil.freeze(at(2026, 11, 20))
    assert led.credit_dividend(dt.date(2026, 11, 19), 0.12)
    assert led.credit_dividend(dt.date(2026, 11, 19), 0.12) is None
    assert led.dividends_c() == 1200


def test_tags_normalised(led):
    start(led)
    r = led.place(SP(strike=55, price=1.0, tags=["Wheel", "#near money", "wheel"]), q(.9, 1.1), 56)
    assert led.position(r["position_id"])["tags"] == ["#near-money", "#wheel"]


def test_snapshot_gap_fill(led):
    start(led, when=at(2026, 11, 2))
    n = led.fill_snapshot_gaps({"2026-11-02": 55.0, "2026-11-03": 56.0, "2026-11-04": 57.0}, dt.date(2026, 11, 5))
    assert n == 3
    rows = led.db.q("SELECT day, estimated FROM snapshots ORDER BY day")
    assert [r[1] for r in rows] == [1, 1, 1]
