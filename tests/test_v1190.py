"""v1.19.0: buy and sell shares of any symbol (options stay TQQQ-only for now)."""
import datetime as dt
import sqlite3
from pathlib import Path

import pytest

from ghost_trader import db as dbm, timeutil
from ghost_trader.api import App
from ghost_trader.ledger import TradeError
from ghost_trader.market import DemoProvider

JS = (Path(__file__).parent.parent / "ghost_trader" / "static" / "app.js").read_text()
Q = {"bid": 99.9, "ask": 100.1}


def _buy(led, sym, qty, px=100.0, ts=None):
    q = {"bid": px - .1, "ask": px + .1}
    return led.place({"action": "buy_shares", "symbol": sym, "qty": qty, "price": px}, q, 50.0, ts)


def test_shares_are_kept_per_symbol(led):
    led.start_run(100_000)
    _buy(led, "TQQQ", 100, 100.0)
    _buy(led, "SPY", 20, 100.0)
    _buy(led, "SPY", 10, 100.0)
    assert led.holdings() == {"TQQQ": 100, "SPY": 30}
    assert led.shares() == 100 and led.shares("SPY") == 30        # TQQQ is still the default everywhere else
    assert [lt["symbol"] for lt in led.lots(symbol="SPY")] == ["SPY", "SPY"] and len(led.lots()) == 3
    assert led.avg_cost("SPY") == 100.0


def test_account_value_counts_every_symbol(led):
    led.start_run(100_000)
    _buy(led, "TQQQ", 100, 50.0)
    _buy(led, "SPY", 10, 100.0)
    led.set_price("SPY", 120.0)
    b = led.breakdown(60.0)
    assert b["shares"] == 100 and b["shares_value_c"] == 100 * 60 * 100 + 10 * 120 * 100
    spy = next(h for h in b["holdings"] if h["symbol"] == "SPY")
    assert spy["value_c"] == 120_000 and spy["avg_cost"] == 100.0
    assert b["account_value_c"] == b["available_c"] + b["collateral_c"] + b["shares_value_c"]
    assert led.account_value_c(60.0) == b["account_value_c"]
    # with no price set yet it falls back to the last saved quote, then the cost: never zero
    led.prices.clear()
    assert led.price_of("SPY") == 100.0


def test_sell_rules_per_symbol(led):
    led.start_run(100_000)
    _buy(led, "SPY", 10)
    with pytest.raises(TradeError, match="hold 10 SPY"):
        led.place({"action": "sell_shares", "symbol": "SPY", "qty": 11, "price": 100.0}, Q, 50.0)
    with pytest.raises(TradeError, match="hold 0 QQQ"):
        led.place({"action": "sell_shares", "symbol": "QQQ", "qty": 1, "price": 100.0}, Q, 50.0)
    led.place({"action": "sell_shares", "symbol": "SPY", "qty": 4, "price": 100.0}, Q, 50.0)
    assert led.shares("SPY") == 6 and led.shares("TQQQ") == 0
    assert any("Sold 4 SPY" in e["title"] for e in led.db.q("SELECT title FROM events"))


def test_covered_calls_only_lock_their_own_symbol(led):
    led.start_run(100_000)
    _buy(led, "TQQQ", 100)
    _buy(led, "SPY", 50)
    assert led.free_shares("SPY") == 50 and led.locked_shares("SPY") == 0
    # 50 SPY can't cover a call (it needs 100); TQQQ's shares don't count towards SPY's cover
    exp = (timeutil.today_ct() + dt.timedelta(days=30)).isoformat()
    order = {"action": "sell_to_open", "symbol": "SPY", "type": "call", "expiry": exp, "strike": 120.0, "qty": 1,
             "price": 1.0}
    with pytest.raises(TradeError, match="Not covered: you hold 50 SPY"):
        led.place(order, {"bid": .9, "ask": 1.1}, 50.0)


def test_dividends_are_per_symbol(led):
    t0 = timeutil.now() - dt.timedelta(days=30)
    led.start_run(100_000, ts=t0)
    _buy(led, "TQQQ", 100, ts=t0 + dt.timedelta(days=1))
    _buy(led, "SPY", 50, ts=t0 + dt.timedelta(days=1))
    ex = (t0 + dt.timedelta(days=10)).date()
    assert led.credit_dividend(ex, 0.10, symbol="SPY")
    assert led.credit_dividend(ex, 0.20, symbol="TQQQ")           # same ex-date, another symbol: both pay
    assert led.credit_dividend(ex, 0.10, symbol="SPY") is None    # and each only once
    assert led.dividends_c() == 50 * 10 + 100 * 20


def test_migration_keeps_old_dividends(home):
    p = home / "old.db"
    c = sqlite3.connect(p, isolation_level=None)
    for n in range(1, 7):
        for s in dbm._split(dbm.MIGRATIONS[n]):
            c.execute(s)
    c.execute("INSERT INTO meta(key,value) VALUES('schema_version','6')")
    c.execute("INSERT INTO dividends(run_id,ex_day,amount) VALUES(1,'2026-03-01',0.05)")
    c.close()
    d = dbm.DB(p)
    assert d.version() == dbm.SCHEMA_VERSION >= 7
    assert [tuple(r) for r in d.q("SELECT run_id,symbol,ex_day,amount FROM dividends")] == [(1, "TQQQ", "2026-03-01", 0.05)]
    d.close()


# ---------------------------------------------------------------- through the app
def _app(home):
    a = App(demo=True, provider=DemoProvider())
    assert a.api_start_run(cash="$100,000.00")["ok"]
    return a


def test_ticket_review_place_for_another_symbol(home):
    a = _app(home)
    t = a.api_ticket({"action": "buy_shares", "symbol": "iwm", "qty": 10})
    assert t["symbol"] == "IWM" and t["sym_price"] and t["check"]["ok"], t
    o = {"action": "buy_shares", "symbol": "IWM", "qty": 10, "price": t["default_fill"]}
    r = a.api_review(o)
    assert r["ok"] and "BUY 10 IWM SHARES" == r["title"]
    assert a.api_place(o)["ok"]
    s = a.api_state()
    h = next(x for x in s["bal"]["holdings"] if x["symbol"] == "IWM")
    assert h["shares"] == 10 and h["value_c"] > 0 and s["bal"]["account_value_c"] > 0
    assert "IWM" in a.settings.get("watchlist")                    # a symbol you hold is a symbol you track
    assert s["bal"]["account_value_c"] == a.led.account_value_c(a.price())


def test_sell_other_symbol_through_app(home):
    a = _app(home)
    o = {"action": "buy_shares", "symbol": "SPY", "qty": 10, "price": a.api_ticket({"action": "buy_shares", "symbol": "SPY", "qty": 10})["default_fill"]}
    assert a.api_place(o)["ok"]
    t = a.api_ticket({"action": "sell_shares", "symbol": "SPY", "qty": 10})
    assert t["held"] == 10 and t["free"] == 10 and t["check"]["ok"]
    assert "hold 10 SPY" in a.api_ticket({"action": "sell_shares", "symbol": "SPY", "qty": 11})["check"]["msg"]


def test_indexes_and_junk_are_refused(home):
    a = _app(home)
    assert "index" in a.api_ticket({"action": "buy_shares", "symbol": "^GSPC", "qty": 1})["error"]
    assert "ticker" in a.api_place({"action": "buy_shares", "symbol": "a b!", "qty": 1, "price": 1})["error"]
    assert "Couldn't get a quote for ZZZZ" in a.api_ticket({"action": "buy_shares", "symbol": "ZZZZ", "qty": 1})["error"]


def test_tqqq_trading_unchanged(home):
    a = _app(home)
    t = a.api_ticket({"action": "buy_shares", "qty": 100})
    assert t["symbol"] == "TQQQ" and t["check"]["ok"]
    assert a.api_place({"action": "buy_shares", "qty": 100, "price": t["default_fill"]})["ok"]
    s = a.api_state()
    assert s["shares"] == 100 and [h["symbol"] for h in s["bal"]["holdings"]] == ["TQQQ"]


def test_snapshot_includes_other_symbols(home):
    a = _app(home)
    px = a.api_ticket({"action": "buy_shares", "symbol": "SPY", "qty": 10})["default_fill"]
    a.api_place({"action": "buy_shares", "symbol": "SPY", "qty": 10, "price": px})
    S = a.price()
    av = a.led.snapshot(timeutil.today_ct(), S, S)
    assert av == a.led.account_value_c(S) and av > 100_000 * 100 - 10 * px * 100 - 500


def test_ui_wired():
    for k in ("function symRow(", "function setTkSymbol(", "data-tsym", "function holdTxt(", "(st.bal.holdings || [])"):
        assert k in JS
