"""v1.24.0: a copy-ready order line at the bottom of the ticket (text only)."""
from pathlib import Path

from ghost_trader.api import App, order_line

JS = (Path(__file__).parent.parent / "ghost_trader" / "static" / "app.js").read_text()


def test_order_line_formats():
    o = {"action": "sell_to_open", "symbol": "tqqq", "type": "put", "expiry": "2026-12-11", "strike": 47, "qty": 1, "price": 1.15}
    assert order_line(o) == "SELL TO OPEN 1 TQQQ 12/11/2026 47.00 PUT · LIMIT 1.15 · DAY"
    assert order_line({**o, "action": "buy_to_close", "type": "call", "symbol": "SPY", "strike": 612.5}) == \
        "BUY TO CLOSE 1 SPY 12/11/2026 612.50 CALL · LIMIT 1.15 · DAY"
    assert order_line({"action": "buy_shares", "symbol": "IWM", "qty": 50, "price": 211.3}) == "BUY 50 IWM · LIMIT 211.30 · DAY"
    assert order_line({"action": "sell_shares", "qty": 10}) == "SELL 10 TQQQ · DAY"


def _app(tmp_path, monkeypatch):
    monkeypatch.setenv("GHOST_TRADER_HOME", str(tmp_path))
    a = App(demo=True)
    a.led.start_run(100000)
    return a


def test_ticket_returns_line_for_option_and_shares(tmp_path, monkeypatch):
    a = _app(tmp_path, monkeypatch)
    exp = a.quotes.expirations()[2]
    t = a.api_ticket({"action": "sell_to_open", "type": "put", "expiry": exp, "strike": 40, "qty": 1})
    if t["check"]["ok"]:
        assert t["order_line"].startswith("SELL TO OPEN 1 TQQQ ") and t["order_line"].endswith("PUT · LIMIT %.2f · DAY" % t["order"]["price"])
    s = a.api_ticket({"action": "buy_shares", "symbol": "SPY", "qty": 5})
    assert s["check"]["ok"] and s["order_line"].startswith("BUY 5 SPY · LIMIT ")


def test_no_line_when_check_fails(tmp_path, monkeypatch):
    a = _app(tmp_path, monkeypatch)
    s = a.api_ticket({"action": "sell_shares", "symbol": "SPY", "qty": 5})  # holds none
    assert not s["check"]["ok"] and s["order_line"] == ""


def test_ui_has_line_and_copy_button():
    assert "tkCopyLine" in JS and "d.order_line" in JS and "practice only, nothing is sent" in JS
