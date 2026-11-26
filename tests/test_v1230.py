"""v1.23.0: options on any stock or ETF (cash-secured puts, covered calls) with per-symbol settlement."""
import datetime as dt
from pathlib import Path

import pytest

from ghost_trader import marketcal, timeutil
from ghost_trader.api import App
from ghost_trader.ledger import TradeError
from ghost_trader.market import DemoProvider

JS = (Path(__file__).parent.parent / "ghost_trader" / "static" / "app.js").read_text()


def _buy(led, sym, qty, px=100.0, ts=None):
    return led.place({"action": "buy_shares", "symbol": sym, "qty": qty, "price": px},
                     {"bid": px - .1, "ask": px + .1}, 50.0, ts)


def _past_friday(days_ago=40):
    d = timeutil.today_ct() - dt.timedelta(days=days_ago)
    while d.weekday() != 4 or not marketcal.is_trading_day(d):
        d += dt.timedelta(days=1)
    return d


def _sell(led, sym, typ, exp, k, ts, qty=1, px=1.0):
    return led.place({"action": "sell_to_open", "symbol": sym, "type": typ, "expiry": exp.isoformat(), "strike": k,
                      "qty": qty, "price": px}, {"bid": px - .05, "ask": px + .05}, 100.0, ts)


def test_put_on_another_symbol_is_cash_secured_and_labelled(led):
    t0 = timeutil.now() - dt.timedelta(days=45)
    led.start_run(100_000, ts=t0)
    exp = _past_friday(30)
    r = _sell(led, "SPY", "put", exp, 100.0, t0 + dt.timedelta(days=1))
    p = led.position(r["position_id"])
    assert p["symbol"] == "SPY" and p["label"].startswith("SPY ") and p["collateral_c"] == 10_000 * 100
    # more than the cash it needs is refused for any symbol: no unsecured puts
    with pytest.raises(TradeError):
        _sell(led, "SPY", "put", exp, 950.0, t0 + dt.timedelta(days=1))


def test_covered_call_needs_that_symbols_shares(led):
    t0 = timeutil.now() - dt.timedelta(days=45)
    led.start_run(100_000, ts=t0)
    exp = _past_friday(30)
    _buy(led, "TQQQ", 100, ts=t0 + dt.timedelta(days=1))
    with pytest.raises(TradeError, match="Not covered"):
        _sell(led, "SPY", "call", exp, 110.0, t0 + dt.timedelta(days=2))        # TQQQ shares don't cover SPY
    _buy(led, "SPY", 100, ts=t0 + dt.timedelta(days=1))
    r = _sell(led, "SPY", "call", exp, 110.0, t0 + dt.timedelta(days=2))
    assert led.locked_shares("SPY") == 100 and led.locked_shares("TQQQ") == 0
    lot = led.position(r["position_id"])["lot_id"]
    assert led.db.val("SELECT symbol FROM lots WHERE id=?", (lot,)) == "SPY"
    with pytest.raises(TradeError, match="Not covered"):                          # all 100 SPY are covering now
        _sell(led, "SPY", "call", exp, 112.0, t0 + dt.timedelta(days=2))


def test_settles_each_symbol_at_its_own_close(led):
    t0 = timeutil.now() - dt.timedelta(days=45)
    led.start_run(200_000, ts=t0)
    exp = _past_friday(30)
    a = _sell(led, "SPY", "put", exp, 100.0, t0 + dt.timedelta(days=1))
    b = _sell(led, "TQQQ", "put", exp, 50.0, t0 + dt.timedelta(days=1))
    assert led.due_settlements(timeutil.now()) == [("SPY", exp), ("TQQQ", exp)]
    led.settle_expiration(exp, 95.0, symbol="SPY")                  # SPY closed under its strike: assigned
    assert led.position(a["position_id"])["status"] == "assigned"
    assert led.position(b["position_id"])["status"] == "open"        # TQQQ's put is untouched
    assert led.shares("SPY") == 100 and led.shares("TQQQ") == 0
    assert any(e["title"] == "Put assigned: bought 100 SPY @ 100.00" for e in led.db.q("SELECT title FROM events"))
    led.settle_expiration(exp, 55.0, symbol="TQQQ")                 # above its strike: expires worthless
    assert led.position(b["position_id"])["status"] == "expired"
    assert led.due_settlements(timeutil.now()) == []


def test_called_away_sells_that_symbols_shares(led):
    t0 = timeutil.now() - dt.timedelta(days=45)
    led.start_run(100_000, ts=t0)
    exp = _past_friday(30)
    _buy(led, "SPY", 100, ts=t0 + dt.timedelta(days=1))
    _buy(led, "TQQQ", 100, 50.0, ts=t0 + dt.timedelta(days=1))
    r = _sell(led, "SPY", "call", exp, 105.0, t0 + dt.timedelta(days=2))
    led.settle_expiration(exp, 110.0, symbol="SPY")
    assert led.position(r["position_id"])["status"] == "called"
    assert led.shares("SPY") == 0 and led.shares("TQQQ") == 100


def test_closing_uses_the_positions_symbol(led):
    led.start_run(100_000)
    exp = (timeutil.today_ct() + dt.timedelta(days=20))
    while exp.weekday() != 4:
        exp += dt.timedelta(days=1)
    r = _sell(led, "SPY", "put", exp, 100.0, None)
    o = {"action": "buy_to_close", "position_id": r["position_id"], "qty": 1, "price": 0.5, "symbol": "TQQQ"}
    led.place(o, {"bid": .45, "ask": .55}, 100.0)
    assert led.position(r["position_id"])["status"] == "closed"


# ---------------------------------------------------------------- through the app
def _app(home):
    a = App(demo=True, provider=DemoProvider())
    assert a.api_start_run(cash="$500,000.00")["ok"]
    return a


def test_chain_for_any_symbol(home):
    a = _app(home)
    c = a.api_chain(symbol="spy")
    assert c["symbol"] == "SPY" and c["strikes"] and c["price"]
    assert a.settings.get("chain_symbol") == "SPY"
    # SPY's strikes sit around SPY's price, not TQQQ's
    ks = [s["k"] for s in c["strikes"]]
    assert min(ks) < c["price"] < max(ks)
    assert a.api_chain()["symbol"] == "SPY"                                # remembered
    assert a.api_chain(symbol="TQQQ")["symbol"] == "TQQQ"
    assert "index" in a.api_chain(symbol="^GSPC")["error"]
    assert "ticker" in a.api_chain(symbol="not a ticker!")["error"]
    assert a.api_chain(symbol="ZZZZ")["error"]                             # nothing for it at the provider


def test_ticket_review_place_and_state_for_an_option_on_spy(home):
    a = _app(home)
    c = a.api_chain(symbol="SPY")
    k = min((s["k"] for s in c["strikes"] if s["put"] and s["put"]["bid"] and s["k"] < c["price"]),
            key=lambda x: abs(x - c["price"] * .95))
    o = {"action": "sell_to_open", "symbol": "SPY", "type": "put", "expiry": c["expiry"], "strike": k, "qty": 1}
    t = a.api_ticket(o)
    assert t["check"]["ok"], t["check"] and t["symbol"] == "SPY" and t["price"] == c["price"]
    assert t["strikes"] and all(abs(x - c["price"]) < c["price"] for x in t["strikes"])
    o["price"] = t["default_fill"]
    r = a.api_review(o)
    assert r["ok"] and " × SPY " in r["title"], r
    assert a.api_place(o)["ok"]
    s = a.api_state()
    pos = next(p for p in s["positions"] if p["symbol"] == "SPY")
    assert pos["label"].startswith("SPY ") and pos["mark"] is not None
    assert pos["dist"] == pytest.approx((c["price"] - k) / k, abs=0.02)      # measured against SPY, not TQQQ
    assert a.api_position(pos["id"])["symbol"] == "SPY"
    cone = a.api_cone(id=pos["id"])
    assert cone["symbol"] == "SPY" and cone["price"] == pytest.approx(c["price"], abs=1)
    # closing it needs no symbol on the ticket
    t2 = a.api_ticket({"action": "buy_to_close", "position_id": pos["id"], "qty": 1})
    assert t2["symbol"] == "SPY"


def test_heat_map_roll_map_and_palette_follow_the_symbol(home):
    a = _app(home)
    m = a.api_chain_map(symbol="SPY")
    spy = a.spot("SPY")
    assert m["symbol"] == "SPY" and m["cols"] and all(abs(k - spy) / spy <= 0.16 for k in m["strikes"])
    assert a.api_expirations(symbol="SPY")["items"]
    c = a.api_chain(symbol="SPY")
    k = min((s["k"] for s in c["strikes"] if s["put"] and s["put"]["bid"] and s["k"] < c["price"]),
            key=lambda x: abs(x - c["price"] * .95))
    o = {"action": "sell_to_open", "symbol": "SPY", "type": "put", "expiry": c["expiry"], "strike": k, "qty": 1}
    o["price"] = a.api_ticket(o)["default_fill"]
    a.api_place(o)
    pid = a.led.positions()[0]["id"]
    r = a.api_roll_map(pid)
    assert r["symbol"] == "SPY" and r["rolls"] and all(x["strike"] < spy * 1.2 for x in r["rolls"])


def test_tqqq_still_works_and_the_two_dont_mix(home):
    a = _app(home)
    for sym in ("TQQQ", "SPY"):
        c = a.api_chain(symbol=sym)
        k = min((s["k"] for s in c["strikes"] if s["put"] and s["put"]["bid"] and s["k"] < c["price"]),
                key=lambda x: abs(x - c["price"] * .9))
        o = {"action": "sell_to_open", "symbol": sym, "type": "put", "expiry": c["expiry"], "strike": k, "qty": 1}
        o["price"] = a.api_ticket(o)["default_fill"]
        assert a.api_place(o)["ok"], sym
    s = a.api_state()
    assert sorted(p["symbol"] for p in s["positions"]) == ["SPY", "TQQQ"]
    assert len(a.api_chain(symbol="SPY")["held"]) == 1 and a.api_chain(symbol="SPY")["held"][0]["symbol"] == "SPY"
    assert len(a.api_chain(symbol="TQQQ")["held"]) == 1


def test_indicators_trade_layer_is_per_symbol(home):
    a = _app(home)
    c = a.api_chain(symbol="SPY")
    k = min((s["k"] for s in c["strikes"] if s["put"] and s["put"]["bid"] and s["k"] < c["price"]),
            key=lambda x: abs(x - c["price"] * .95))
    o = {"action": "sell_to_open", "symbol": "SPY", "type": "put", "expiry": c["expiry"], "strike": k, "qty": 1}
    o["price"] = a.api_ticket(o)["default_fill"]
    a.api_place(o)
    a.api_place({"action": "buy_shares", "symbol": "IWM", "qty": 5,
                 "price": a.api_ticket({"action": "buy_shares", "symbol": "IWM", "qty": 5})["default_fill"]})
    spy = a._trade_days(None, "SPY")
    assert sum(len(v) for v in spy.values()) == 1 and "SPY" in next(iter(spy.values()))[0]["text"]
    assert sum(len(v) for v in a._trade_days(None, "IWM").values()) == 1
    assert a._trade_days(None, "TQQQ") == {}


def test_notification_text_names_the_symbol():
    from ghost_trader import notify
    pos = [{"symbol": "SPY", "side": "short", "type": "put", "strike": 100.0, "open_qty": 2},
           {"symbol": "TQQQ", "side": "short", "type": "put", "strike": 50.0, "open_qty": 1}]
    title, body = notify.message(pos, 52.0, {"SPY": 98.0})
    assert "SPY" in title and "TQQQ" in title and "SPY 98.00" in body and "TQQQ 52.00" in body


def test_ui_wires_the_symbol_through():
    assert "chainSymBox" in JS and "TQQQ only for now" not in JS
    assert "symbol: c.symbol" in JS and "symbol: d.symbol" in JS
