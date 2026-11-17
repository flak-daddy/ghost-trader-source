"""v1.13.1: Indicators "Layers" view (front-end only)."""
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
JS = (ROOT / "ghost_trader" / "static" / "app.js").read_text()
CSS = (ROOT / "ghost_trader" / "static" / "app.css").read_text()


def test_layers_wiring_present():
    assert "function layersCard(" in JS and "function wireLayers(" in JS
    # the switch, the default (Layers unless explicitly Stacked) and the state keys
    assert 'data-il' in JS and "ui.indLayers !== false" in JS
    for k in ("ui.indLayerOn", "ui.indLayerRange"):
        assert k in JS
    # four curves, shared 0-100 axis, 20/80 dashed
    assert JS.count('["px", "TQQQ price"') == 1 and "[0, 20, 50, 80, 100]" in JS
    assert 'viewBox="0 0 ${W} ${H}"' in JS and 'preserveAspectRatio="none"' in JS
    # stacked charts and the table view are still there
    assert 'title: "Stochastic"' in JS and "ui.indTable" in JS
    # chips, footer picker, CSS
    for c in (".lchip", ".lchip.on", ".lfoot"):
        assert c in CSS


def test_no_data_api_or_settings_change():
    api = (ROOT / "ghost_trader" / "api.py").read_text()
    assert "indLayer" not in api and "ind_layer" not in api


def _free_port():
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_indicators_page_renders_in_both_themes(tmp_path):
    """Smoke check in a real browser; skipped where Playwright or Chrome isn't installed (e.g. CI)."""
    pw = pytest.importorskip("playwright.sync_api")
    chrome = shutil.which("google-chrome") or shutil.which("chromium")
    if not chrome:
        pytest.skip("no Chrome/Chromium")
    port = _free_port()
    env = {"GHOST_TRADER_HOME": str(tmp_path), "PATH": "/usr/bin:/bin"}
    proc = subprocess.Popen([sys.executable, "-m", "ghost_trader", "--demo", "--serve", "--port", str(port)],
                            cwd=ROOT, env=env, stdout=subprocess.PIPE, text=True)
    try:
        url = proc.stdout.readline().strip()
        assert url.startswith("http")
        with pw.sync_playwright() as p:
            b = p.chromium.launch(executable_path=chrome)
            page = b.new_page(viewport={"width": 1300, "height": 900})
            errs = []
            page.on("pageerror", lambda e: errs.append(str(e)))
            page.goto(url)
            for _ in range(80):
                if page.evaluate("document.querySelector('#splash').innerHTML===''"):
                    break
                time.sleep(0.5)
            page.evaluate("(async () => { await api('start_run', {cash: '$100,000.00'}); await refreshState(); render(); })()")
            page.wait_for_timeout(1500)
            page.evaluate("go('ind')")
            page.wait_for_selector("#lsvg", timeout=20000)
            for theme in ("dark", "light"):
                page.evaluate(f"ui.theme='{theme}'; applyTheme()")
                assert page.locator("#lsvg path").count() == 4 and page.locator(".lchip.on").count() == 4
            page.click(".lchip[data-ly=vix]")
            assert page.locator("#lsvg path").count() == 3
            page.click("[data-il=stacked]")
            page.wait_for_selector("#ichartbox .ichart", timeout=10000)
            assert page.locator("#lsvg").count() == 0
            assert not errs, errs
            b.close()
    finally:
        proc.terminate()
