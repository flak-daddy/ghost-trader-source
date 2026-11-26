"""v1.13.2: Buy / Sell buttons on the Portfolio Shares tile (front-end only)."""
from pathlib import Path

JS = (Path(__file__).parent.parent / "ghost_trader" / "static" / "app.js").read_text()
CSS = (Path(__file__).parent.parent / "ghost_trader" / "static" / "app.css").read_text()


def test_shares_tile_has_buy_and_sell():
    body = JS[JS.index("function sharesBtns"):JS.index("function openShares")]
    assert "openShares('buy_shares')" in body and "openShares('sell_shares'" in body
    # Sell is only enabled when some shares (of any symbol, v1.19.0) are free, not covering a call, with a reason otherwise
    assert "h.shares - h.locked" in body and "disabled" in body
    assert "covering calls" in body and "any shares" in body
    # the Shares card, and only that card, gets the buttons
    assert 'a === "Shares" ? sharesBtns()' in JS
    assert ".tilebtns" in CSS


def test_existing_share_entry_points_kept():
    assert JS.count("openShares('buy_shares')") >= 2  # tile + the Shares section
