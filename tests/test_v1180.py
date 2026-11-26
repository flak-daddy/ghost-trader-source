"""v1.18.0: watchlist charts, and the Indicators tab for any tracked symbol."""
from pathlib import Path

from ghost_trader.api import App
from ghost_trader.market import DemoProvider

ROOT = Path(__file__).parent.parent
JS = (ROOT / "ghost_trader" / "static" / "app.js").read_text()


def _app(home, **kw):
    return App(provider=DemoProvider(**kw), demo=True)


def test_watch_charts_a_year_per_symbol(home):
    a = _app(home)
    c = a.api_watch_charts()
    assert set(c["series"]) == {"QQQ", "SPY", "SQQQ", "^GSPC", "^NDX", "^VIX"} and not c["missing"]
    assert len(c["series"]["SPY"]) > 150 and c["series"]["SPY"][0][0] < c["series"]["SPY"][-1][0]
    # other symbols sit at their own price level, not TQQQ's
    assert c["series"]["SPY"][-1][1] != c["series"]["QQQ"][-1][1]


def test_watch_charts_one_failure_leaves_the_rest(home):
    a = _app(home)
    real = a.provider.daily_closes

    def flaky(start, end, symbol=None):
        if symbol == "SPY":
            raise RuntimeError("nope")
        return real(start, end, symbol=symbol)
    a.provider.daily_closes = flaky
    c = a.api_watch_charts()
    assert c["missing"] == ["SPY"] and "QQQ" in c["series"]
    a.provider.daily_closes = real
    assert a.api_watch_charts()["missing"] == []      # retried next time


def test_indicators_for_another_symbol(home):
    a = _app(home)
    t, q = a.api_indicators(), a.api_indicators(symbol="qqq")
    assert t["symbol"] == "TQQQ" and q["symbol"] == "QQQ"
    assert t["symbols"] == ["TQQQ", "QQQ", "SPY", "SQQQ", "^GSPC", "^NDX", "^VIX"]
    assert q["close"] != t["close"] and q["now"]["price"] != t["now"]["price"]
    assert len(q["stoch"]["14"]["k"]) == len(q["days"]) and q["status"]["tqqq"]["ok"]
    # implied volatility and your trades are TQQQ-only; realized volatility still works
    assert not any(q["iv"]) and q["ivnow"] is None and q["trades"] == {} and any(x is not None for x in q["hv"])
    assert t["ivnow"] is None or t["ivnow"]["iv"]       # TQQQ unchanged
    assert a.api_indicators()["symbol"] == "TQQQ"


def test_indicators_rejects_unlisted_symbol(home):
    a = _app(home)
    assert "isn't on your tracked list" in a.api_indicators(symbol="AAPL")["error"]


def test_index_symbol_has_bars(home):
    a = _app(home)
    g = a.api_indicators(symbol="^GSPC")
    assert g["symbol"] == "^GSPC" and g["days"] and g["now"]["price"]


def test_trade_readings_still_use_tqqq(home):
    a = _app(home)
    a.api_indicators(symbol="SPY")
    s1 = a.ind.snapshot()
    a.api_indicators()
    assert a.ind.snapshot()["stoch14_k"] == s1["stoch14_k"]


def test_ui_wired():
    for k in ("function drawWatchlist(", "function sparkSvg(", "data-isym", "ui.indSym", 'api("watch_charts"', "id=wlGrid"):
        assert k in JS
    assert JS.count('["px", "TQQQ price"') == 1     # label made dynamic only where it's drawn
