"""v1.22.0: command palette (Ctrl+K) data."""
from pathlib import Path

from tests.test_v18 import ready


def test_expirations_for_palette(home):
    a = ready(home)
    r = a.api_expirations()
    assert not r.get("error") and r["items"]
    exps = [x["exp"] for x in r["items"]]
    assert exps == sorted(exps) and len(exps) <= 16
    for x in r["items"]:
        assert x["dte"] >= 0 and x["label"] and "dec" not in x["words"] or x["exp"][5:7] == "12"
    assert any("fri" in x["words"] for x in r["items"])


def test_palette_is_wired_and_read_only():
    js = (Path(__file__).parent.parent / "ghost_trader" / "static" / "app.js").read_text()
    assert "openPalette" in js and 'e.key.toLowerCase() === "k"' in js
    # contracts only open a ticket (no direct trade call from the palette)
    body = js[js.index("async function openPalette"):js.index("/* ---------- render ---------- */")]
    assert "api(\"place" not in body and "api(\"trade" not in body
