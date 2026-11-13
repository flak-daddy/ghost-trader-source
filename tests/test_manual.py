"""The manual: packaged copy, renderer, Help API, link allowlist."""
import re
from pathlib import Path

from ghost_trader import config, manual
from ghost_trader.api import App
from ghost_trader.market import DemoProvider

ROOT = Path(__file__).resolve().parent.parent


def test_packaged_copy_is_the_repo_manual():
    assert manual.MANUAL_PATH.read_text() == (ROOT / "MANUAL.md").read_text()
    assert manual.MANUAL_PATH.parent == config.STATIC_DIR


def test_render_anchors_and_toc():
    body, toc = manual.render(manual.load())
    ids = set(re.findall(r'id="([^"]+)"', body))
    links = re.findall(r'href="#([^"]+)"', body)
    assert links and not [a for a in links if a not in ids]
    parts = [t["id"] for t in toc if t["level"] == 2]
    for want in ("cash-secured-puts", "covered-calls-and-the-wheel", "tqqq-and-its-risks", "using-ghost-trader",
                 "your-first-trade-step-by-step", "glossary"):
        assert want in parts
    assert "**" not in body and "](" not in body
    assert "not financial advice" in body


def test_render_basics():
    body, _ = manual.render("# T\n\nA **b** *c* `<d>` [e](#t)\n\n- one\n  - sub\n- two\n\n| x | y |\n|---|---|\n| 1 | 2 |\n\n> q")
    assert "<strong>b</strong>" in body and "<em>c</em>" in body and "<code>&lt;d&gt;</code>" in body
    assert '<a href="#t">e</a>' in body
    assert "<ul><li>one<ul><li>sub</li></ul></li><li>two</li></ul>" in body
    assert "<td>1</td><td>2</td>" in body and "<blockquote><p>q</p></blockquote>" in body
    assert "<script>" not in manual.render("<script>x</script>")[0]


def test_to_text():
    t = manual.to_text("**a** [b](#x) [c](https://e.com)")
    assert t == "a b c (https://e.com)"


def test_help_api(home, monkeypatch):
    a = App(demo=True, provider=DemoProvider())
    m = a.api_manual()
    assert m["html"].startswith("<h1") and m["toc"]
    opened = []
    monkeypatch.setattr("subprocess.Popen", lambda *a, **k: opened.append(a[0]))
    assert a.api_open_manual_link("https://evil.example/")["error"]
    assert a.api_open_manual_link("file:///etc/passwd")["error"]
    url = re.search(r"\]\((https://[^)]+)\)", manual.load()).group(1)
    assert a.api_open_manual_link(url)["ok"] and opened[-1][-1] == url
