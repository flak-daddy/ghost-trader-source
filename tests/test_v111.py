"""v1.11.0: IV rank / percentile, the Volatility group, and the trade-marker layer on Indicators."""
import datetime as dt

from tests.test_v18 import ready


def seed_iv(a, vals):
    d = dt.date(2026, 11, 13)
    for v in reversed(vals):
        a.db.x("INSERT OR REPLACE INTO iv_history(day, iv, price, asof) VALUES(?,?,?,?)", (d.isoformat(), v, 50, "x"))
        d -= dt.timedelta(days=1)


def test_iv_rank_and_percentile(home):
    a = ready(home)
    a.db.x("DELETE FROM iv_history")
    seed_iv(a, [0.40, 0.50, 0.60, 0.80, 0.55])           # today 0.55
    v = a._vol_series([], [])["ivnow"]
    assert v["iv"] == 0.55 and v["n"] == 5 and v["lo"] == 0.40 and v["hi"] == 0.80
    assert v["rank"] == round((0.55 - 0.40) / 0.40 * 100)  # 38
    assert v["pct"] == 40                                   # 2 of 5 readings are lower


def test_realized_vol_matches_a_known_series():
    import math

    from ghost_trader.api import App

    class NoHistory:
        def q(self, *a):
            return []
    closes = [100 * math.exp(0.01 * (i % 2)) for i in range(60)]     # alternating +1% / -1% days
    hv = App._vol_series(type("A", (), {"db": NoHistory()})(), [str(i) for i in range(60)], closes)["hv"]
    assert hv[:30] == [None] * 30
    assert abs(hv[-1] - 0.01 * math.sqrt(252) * math.sqrt(30 / 29)) < 0.002


def test_trade_days_and_layer_setting(home):
    a = ready(home)
    c = a.api_chain()
    o = {"action": "sell_to_open", "type": "put", "expiry": c["expiry"], "strike": float(round(c["price"]) - 4), "qty": 1}
    assert a.api_place({**o, "price": a.api_ticket(o)["default_fill"]}).get("position_id")
    t = a._trade_days()
    day = max(t)
    assert t[day][-1]["kind"] == "open" and "Sell to open" in t[day][-1]["text"]
    a.api_settings_set(ind_trades=True)
    assert a.api_boot()["ind_trades"] is True
    assert not a.db.val("SELECT COUNT(*) FROM events WHERE kind='Settings'")   # a view toggle isn't logged
    a.api_settings_set(ind_ranges={"vol": "1Y"})
    assert a.settings.get("ind_ranges")["vol"] == "1Y"


def test_indicators_payload_has_vol_and_trades(home):
    a = ready(home)
    v = a.api_indicators()
    assert len(v["iv"]) == len(v["days"]) == len(v["hv"]) and "trades" in v


def test_vol_now_term_structure_and_skew(home):
    a = ready(home)
    v = a.api_vol_now()
    assert len(v["term"]) >= 3 and all(t["iv"] > 0 for t in v["term"])
    assert v["skew"] and {s["type"] for s in v["skew"]} == {"put", "call"}
    S = v["price"]
    assert all((s["strike"] < S) == (s["type"] == "put") for s in v["skew"])
