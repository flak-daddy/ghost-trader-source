"""v1.16.1: the ticket keeps its scroll place when it redraws."""
from pathlib import Path

JS = (Path(__file__).parent.parent / "ghost_trader" / "static" / "app.js").read_text()
CSS = (Path(__file__).parent.parent / "ghost_trader" / "static" / "app.css").read_text()


def test_ticket_keeps_scroll_and_reserves_cone_space():
    body = JS[JS.index("function renderTicket"):JS.index("Chances as text")]
    assert "keepY" in body and "scrollTop = keepY" in body
    # the late-loading cone has room reserved so the buttons below don't move when it appears
    assert "#tkCone{min-height" in CSS
