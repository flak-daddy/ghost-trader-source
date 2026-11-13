"""Indicators: stochastic math, CNN parsing, the tab's API, failures per source, readings stamped on trades."""
import json
import time

import pytest

from ghost_trader import csvout, indicators as ind
from ghost_trader.api import App
from ghost_trader.market import DemoProvider


def bars(closes, spread=1.0):
    return [{"day": f"2026-01-{i + 1:02d}", "high": c + spread, "low": c - spread, "close": c}
            for i, c in enumerate(closes)]


def test_raw_k_by_hand():
    b = bars([10, 11, 12, 13, 14])
    k = ind.raw_k(b, 3)
    assert k[:2] == [None, None]
    # last 3 bars: highs 13,14,15 lows 11,12,13 -> (14-11)/(15-11) = 75
    assert k[-1] == pytest.approx(75.0)
    flat = ind.raw_k([{"day": "d", "high": 5, "low": 5, "close": 5}] * 3, 3)
    assert flat[-1] == 50.0


def test_slow_14_3_3_and_raw_long():
    closes = [50 + (i % 7) - (i % 5) * .5 for i in range(60)]
    b = bars(closes)
    k, d = ind.stochastic(b, 14)
    raw = ind.raw_k(b, 14)
    i = 40
    assert k[i] == pytest.approx(sum(raw[i - 2:i + 1]) / 3)
    assert d[i] == pytest.approx(sum(k[i - 2:i + 1]) / 3)
    assert k[14] is None and k[15] is not None and d[17] is not None   # 14 raw + 2 smoothing + 2 signal
    k30, d30 = ind.stochastic(b, 30)
    assert d30 is None and k30 == ind.raw_k(b, 30)
    assert all(v is None or 0 <= v <= 100 for v in k + d + k30)


def test_fg_rating_bands():
    assert [ind.fg_rating(x) for x in (10, 24.4, 25, 44, 45, 55, 56, 75, 76)] == [
        "extreme fear", "extreme fear", "fear", "fear", "neutral", "neutral", "greed", "greed", "extreme greed"]


def test_parse_cnn():
    j = {"fear_and_greed": {"score": 41.2, "rating": "fear", "timestamp": "2026-11-12T21:00:00+00:00",
                            "previous_close": 39.0, "previous_1_week": 50.1, "previous_1_month": 60, "previous_1_year": 70},
         "fear_and_greed_historical": {"data": [{"x": 1762905600000.0, "y": 38.5, "rating": "fear"},
                                                {"x": "bad", "y": 1}]}}
    p = ind.parse_cnn(j)
    assert p["score"] == 41.2 and p["rating"] == "fear" and p["week_ago"] == 50.1 and p["year_ago"] == 70.0
    assert list(p["history"].values()) == [38.5]
    with pytest.raises(ValueError):
        ind.parse_cnn({"fear_and_greed": {}})


def test_view_ranges_and_snapshot():
    i = ind.Indicators(DemoProvider())
    i.refresh()
    v3, v2y = i.view(3), i.view(24)
    assert 55 <= len(v3["days"]) <= 70 and len(v2y["days"]) > 450
    assert set(v3["stoch"]) == {"14", "30", "60", "180"} and v3["stoch"]["30"]["d"] is None
    assert None not in v2y["stoch"]["180"]["k"]          # enough history for the longest lookback over 2 years
    s = i.snapshot()
    for k in ("stoch14_k", "stoch14_d", "stoch30_k", "stoch60_k", "stoch180_k", "vix", "fg", "fg_rating"):
        assert s[k] is not None


def test_one_source_failing_leaves_the_others(home):
    i = ind.Indicators(DemoProvider(fail={"fear_greed"}))
    i.refresh()
    v = i.view(3)
    assert v["status"]["fg"]["ok"] is False and v["status"]["tqqq"]["ok"] and v["status"]["vix"]["ok"]
    assert all(x is None for x in v["fg"]) and v["now"]["vix"] is not None
    assert i.snapshot()["fg"] is None and i.snapshot()["stoch14_k"] is not None
    # a later failure keeps the last good data
    good = ind.Indicators(DemoProvider())
    good.refresh()
    good.provider.fail = {"daily_bars"}
    good.refresh(force=True)
    assert good.view(3)["status"]["tqqq"]["ok"] is False and good.view(3)["days"]


def test_readings_stamped_on_trades(home):
    a = App(demo=True, provider=DemoProvider())
    a.api_loaded()
    t0 = time.time()
    while a.api_startup_status()["state"] != "done" and time.time() - t0 < 20:
        time.sleep(0.05)
    assert a.api_start_run(cash="$100,000.00")["ok"]
    v = a.api_indicators(range="6M")
    assert v["range"] == "5Y" and len(v["days"]) > 1200   # five years; each chart group slices its own range
    c = a.api_chain()
    o = {"action": "sell_to_open", "type": "put", "expiry": c["expiry"], "strike": float(round(c["price"]) - 5), "qty": 1}
    t = a.api_ticket(o)
    r = a.api_place({**o, "price": t["default_fill"]})
    assert r["ok"]
    rd = a._readings(r["event_id"])
    assert rd and rd["stoch14_k"] is not None and rd["vix"] is not None
    h = a.api_history()
    assert next(e for e in h["events"] if e["id"] == r["event_id"])["readings"]["fg"] == rd["fg"]
    pos = a.api_position(r["position_id"])
    assert pos["readings"][0]["label"] == "Opened"
    csv = csvout.history_csv(a.led, a.led.run_id())
    head, row = csv.splitlines()[0], [x for x in csv.splitlines() if "Sell to open" in x][0]
    assert "stoch 14,3,3 %K" in head and str(rd["stoch14_k"]) in row


def test_trade_still_places_without_readings(home):
    a = App(demo=True, provider=DemoProvider(fail={"daily_bars", "fear_greed"}))
    a.api_loaded()
    t0 = time.time()
    while a.api_startup_status()["state"] != "done" and time.time() - t0 < 20:
        time.sleep(0.05)
    a.api_start_run(cash="$100,000.00")
    a.provider.fail.add("daily_closes")   # VIX too: nothing available
    a.ind.data.clear()
    c = a.api_chain()
    o = {"action": "sell_to_open", "type": "put", "expiry": c["expiry"], "strike": float(round(c["price"]) - 5), "qty": 1}
    r = a.api_place({**o, "price": a.api_ticket(o)["default_fill"]})
    rd = a._readings(r["event_id"])
    assert r["ok"] and rd.get("stoch14_k") is None and rd.get("vix") is None and rd["chances"]["worthless"] > 0
    assert json.loads(json.dumps(a.api_indicators()))["status"]["tqqq"]["ok"] is False
