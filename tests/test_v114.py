"""v1.20.0: roll map (read-only: maps the buy-to-close + sell-to-open pairs, places nothing)."""
from tests.test_v18 import ready


def _open(a, typ):
    c = a.api_chain()
    k = float(round(c["price"]) - 4) if typ == "put" else float(round(c["price"]) + 4)
    o = {"action": "sell_to_open", "type": typ, "expiry": c["expiry"], "strike": k, "qty": 1}
    if typ == "call":
        a.led.place({"action": "buy_shares", "qty": 100, "price": c["price"]}, {"bid": c["price"], "ask": c["price"], "mid": c["price"]}, c["price"])
    t = a.api_ticket(o)
    a.api_place(order={**o, "price": t["default_fill"]})
    return a.led.positions()[0]


def test_roll_map_for_a_put(home):
    a = ready(home)
    p = _open(a, "put")
    n_events = a.db.val("SELECT COUNT(*) FROM events")
    r = a.api_roll_map(p["id"])
    assert not r.get("error") and r["rolls"] and r["position"]["id"] == p["id"]
    assert r["close_px"] > 0 and r["close_c"] == round(r["close_px"] * 100 * p["open_qty"] * 100)
    for x in r["rolls"]:
        assert x["expiry"] > p["expiry"] and x["strike"] <= p["strike"]               # later, and never closer to the money
        assert x["added"] > 0 and x["price"] > 0
        assert abs(x["net_c"] - (x["price"] - r["close_px"]) * 100 * p["open_qty"] * 100) <= 1
        assert x["credit"] == (x["net_c"] >= 0)
        assert x["collateral_c"] == round(x["strike"] * 100 * p["open_qty"] * 100)
        assert x["chances"] is None or 0 <= x["chances"]["worthless"] <= 1
    assert any(x["strike"] == p["strike"] and x["move"] == "Roll out" for x in r["rolls"])
    assert a.db.val("SELECT COUNT(*) FROM events") == n_events                         # reading a map places nothing
    assert [q["id"] for q in a.led.positions()] == [p["id"]]


def test_roll_map_for_a_call_goes_up(home):
    a = ready(home)
    p = _open(a, "call")
    r = a.api_roll_map(p["id"])
    assert r["rolls"] and all(x["strike"] >= p["strike"] for x in r["rolls"])
    assert any("up" in x["move"] for x in r["rolls"]) or all(x["strike"] == p["strike"] for x in r["rolls"])


def test_roll_map_refuses_what_isnt_an_open_short(home):
    a = ready(home)
    assert a.api_roll_map(12345)["error"]
    p = _open(a, "put")
    a.api_place(order={"action": "buy_to_close", "position_id": p["id"], "qty": 1, "price": a.api_ticket(
        {"action": "buy_to_close", "position_id": p["id"], "qty": 1})["default_fill"]})
    assert a.api_roll_map(p["id"])["error"]
