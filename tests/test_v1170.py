"""v1.17.0: the tracked-symbol list (Settings) and its quotes."""
from pathlib import Path

from ghost_trader import watch
from ghost_trader.api import App
from ghost_trader.market import DemoProvider

ROOT = Path(__file__).parent.parent
JS = (ROOT / "ghost_trader" / "static" / "app.js").read_text()


def test_clean_symbol():
    assert watch.clean_symbol("  brk-b ") == "BRK-B"
    assert watch.clean_symbol("^vix") == "^VIX"
    for bad in ("", None, "a b", "$QQQ", "TOOLONGSYMBOLX", "1ABC", "A;DROP", "^^X"):
        assert watch.clean_symbol(bad) is None
    assert watch.is_index("^GSPC") and not watch.is_index("SPY")


def test_clean_list_dedupes_and_caps():
    assert watch.clean_list(["spy", "SPY", "x y", "qqq"]) == ["SPY", "QQQ"]
    assert len(watch.clean_list([f"S{i}" for i in range(80)])) == watch.MAX


def _app(home):
    return App(provider=DemoProvider(), demo=True)


def test_default_list_and_quotes(home):
    a = _app(home)
    w = a.api_watchlist()
    assert [r["symbol"] for r in w["rows"]] == ["QQQ", "SPY", "SQQQ", "^GSPC", "^NDX", "^VIX"]
    assert all(r["price"] > 0 for r in w["rows"]) and w["rows"][3]["index"] and not w["rows"][0]["index"]


def test_add_remove_and_rules(home):
    a = _app(home)
    assert a.api_watch_add("iwm") == {"ok": True, "symbol": "IWM"}
    assert "IWM" in [r["symbol"] for r in a.api_watchlist()["rows"]]
    assert "already" in a.api_watch_add("IWM")["error"]
    assert "ticker" in a.api_watch_add("not a ticker!")["error"]
    assert "already tracked" in a.api_watch_add("TQQQ")["error"]
    assert a.api_watch_remove("IWM") == {"ok": True}
    assert "isn't on the list" in a.api_watch_remove("IWM")["error"]


def test_unknown_symbol_is_refused(home):
    a = _app(home)
    a.provider.market_snapshot = lambda syms: {}     # Yahoo has nothing for it
    assert "no quote" in a.api_watch_add("ZZZZ")["error"]
    assert "ZZZZ" not in a.settings.get("watchlist")


def test_quote_failure_keeps_last_good(home):
    a = _app(home)
    first = a.api_watchlist()["rows"]

    def boom(syms):
        raise RuntimeError("offline")
    a.provider.market_snapshot = boom
    w = a.api_watchlist(refresh=True)
    assert "offline" in w["error"] and [r["price"] for r in w["rows"]] == [r["price"] for r in first]


def test_settings_ui_wired():
    assert "async function renderWatchSettings(" in JS and "renderWatchSettings();" in JS
    for k in ("watch_add", "watch_remove", "wlCard"):
        assert k in JS
