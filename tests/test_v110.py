"""v1.10.0: chance of touching the strike, payoff inputs in the ticket, probability-cone data."""
import math
import random

from ghost_trader.api import App
from tests.test_v18 import ready


def test_touch_matches_a_simulation():
    S, K, T, r, v = 53.68, 49.0, 14 / 365, 0.042, 0.68
    closed = App._touch("put", S, K, T, r, v)
    random.seed(7)
    n, steps, hit, mu, dt = 6000, 300, 0, r - v * v / 2, T / 300
    for _ in range(n):
        x = math.log(S)
        for _ in range(steps):
            x += mu * dt + v * math.sqrt(dt) * random.gauss(0, 1)
            if x <= math.log(K):
                hit += 1
                break
    assert abs(closed - hit / n) < 0.04          # discrete monitoring misses a few touches


def test_touch_rules():
    assert App._touch("put", 48, 49, 0.05, 0.04, 0.6) == 1.0    # already through a put's strike
    assert App._touch("call", 61, 60, 0.05, 0.04, 0.6) == 1.0   # already through a call's strike
    far = App._touch("put", 53.68, 30, 7 / 365, 0.04, 0.6)
    near = App._touch("put", 53.68, 52, 7 / 365, 0.04, 0.6)
    assert 0 <= far < near <= 1
    c = App._chances("put", 53.68, 49, 0.45, 14, 0.68, 4.2)
    assert c["touch"] > 1 - c["worthless"]      # touching is always at least as likely as finishing through
    assert App._touch("put", 53.68, 49, 0, 0.04, 0.6) is None


def test_ticket_has_payoff_and_touch(home):
    a = ready(home)
    c = a.api_chain()
    o = {"action": "sell_to_open", "type": "put", "expiry": c["expiry"], "strike": float(round(c["price"]) - 4), "qty": 2}
    t = a.api_ticket(o)
    pf = t["payoff"]
    assert pf["type"] == "put" and pf["qty"] == 2 and pf["premium"] > 0 and pf["iv"] > 0 and not pf["covered"]
    assert 0 < t["chances"]["touch"] <= 1


def test_cone_data_portfolio_and_position(home):
    a = ready(home)
    c = a.api_chain()
    o = {"action": "sell_to_open", "type": "put", "expiry": c["expiry"], "strike": float(round(c["price"]) - 4), "qty": 1}
    assert a.api_place({**o, "price": a.api_ticket(o)["default_fill"]}).get("position_id")
    d = a.api_cone(days_back=60)
    assert d["closes"][-1][0] == d["today"] and d["closes"][-1][1] == d["price"]
    assert d["positions"] and d["iv"] > 0 and d["horizon"] >= d["positions"][0]["dte"]
    one = a.api_cone(id=d["positions"][0]["id"], days_back=30)
    assert len(one["positions"]) == 1 and one["iv_src"] == "this option's IV"


def test_chances_at_open_keep_touch(home):
    import json
    a = ready(home)
    c = a.api_chain()
    o = {"action": "sell_to_open", "type": "put", "expiry": c["expiry"], "strike": float(round(c["price"]) - 4), "qty": 1}
    assert a.api_place({**o, "price": a.api_ticket(o)["default_fill"]}).get("position_id")
    row = a.db.one("SELECT data FROM trade_readings ORDER BY event_id DESC LIMIT 1")
    assert "touch" in json.loads(row[0])["chances"]
