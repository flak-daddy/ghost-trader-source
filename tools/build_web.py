"""Build Ghost Trader Lite: the app running in the browser on synthetic data (see web/).

    python tools/build_web.py [out_dir]     # default: dist/web

Output is a static folder (index.html, boot.js, the normal UI files, fonts, gt-web.json with the
Python package). Serve it from any static host; it loads Python (Pyodide) from cdn.jsdelivr.net.
"""
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "ghost_trader"
STATIC = PKG / "static"
WEB = ROOT / "web"

BANNER = """
<style>
#gtboot{position:fixed;inset:0;display:flex;align-items:center;justify-content:center;flex-direction:column;gap:10px;
  background:var(--bg);color:var(--text);font:15px "GT Inter",system-ui,sans-serif;z-index:9999}
#gtboot b{font-size:18px;font-weight:600}#gtboot small{opacity:.65}
#gtboot.err b{color:#e5484d}
#gtboot .gh{width:42px;height:42px;color:var(--accent);animation:gtb 1.6s ease-in-out infinite}
@keyframes gtb{50%{transform:translateY(-6px)}}
#gtlite{position:fixed;left:12px;bottom:10px;z-index:900;display:flex;gap:8px;align-items:center;font-size:12px;
  padding:5px 10px;border-radius:999px;background:color-mix(in srgb,var(--panel) 92%,transparent);
  border:1px solid var(--line);color:var(--dim)}
#gtlite button{font:inherit;font-size:12px;padding:2px 9px;border-radius:999px;cursor:pointer;
  border:1px solid var(--line);background:transparent;color:inherit}
#gtlite button:hover{color:var(--text)}
</style>
<div id="gtboot"><svg class="gh" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linejoin="round"><path d="M12 3a7 7 0 0 0-7 7v10.5l2.4-1.7 2.3 1.7 2.3-1.7 2.3 1.7 2.3-1.7 2.4 1.7V10a7 7 0 0 0-7-7z"/><circle cx="9.5" cy="10.5" r="1.3" fill="currentColor" stroke="none"/><circle cx="14.5" cy="10.5" r="1.3" fill="currentColor" stroke="none"/></svg><b></b><small></small></div>
<div id="gtlite" title="The real Ghost Trader running in your browser on made-up prices. Your trades stay in this browser.">
  Ghost Trader Lite · synthetic prices that move with the clock
  <button id="gtreset" type="button">Reset demo</button>
</div>
<script>
document.getElementById("gtreset").addEventListener("click", e => {
  const b = e.currentTarget;
  if (b.dataset.sure) { window.GT_LITE && GT_LITE.reset(); return; }
  b.dataset.sure = 1; b.textContent = "Click again to start over";
  setTimeout(() => { delete b.dataset.sure; b.textContent = "Reset demo"; }, 4000);
});
</script>
<script src="boot.js"></script>
"""


def build(out):
    out = Path(out)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    # UI files, unchanged
    for f in ("app.js", "app.css", "icon.svg"):
        shutil.copy(STATIC / f, out / f)
    shutil.copytree(STATIC / "fonts", out / "fonts", ignore=shutil.ignore_patterns("*.txt"))

    # index.html: same page, with the Lite loader in place of the direct app.js include
    html = (STATIC / "index.html").read_text()
    html = html.replace("<title>Ghost Trader</title>", "<title>Ghost Trader Lite</title>")
    html, n = re.subn(r'<script src="app\.js"></script>', BANNER.strip(), html)
    assert n == 1, "index.html no longer includes app.js the expected way"
    (out / "index.html").write_text(html)
    shutil.copy(WEB / "boot.js", out / "boot.js")

    # the Python side: the app package (no UI assets) + the web shim
    # (a JSON map of path -> text: static hosts that refuse archives still serve it)
    files = {str(p.relative_to(ROOT)): p.read_text() for p in sorted(PKG.rglob("*.py"))}
    files["ghost_trader/static/MANUAL.md"] = (ROOT / "MANUAL.md").read_text()
    for f in ("gt_web.py", "seed_web.py"):
        files[f] = (WEB / f).read_text()
    (out / "gt-web.json").write_text(json.dumps(files))
    return out


if __name__ == "__main__":
    o = build(sys.argv[1] if len(sys.argv) > 1 else ROOT / "dist" / "web")
    print("built", o, sorted(p.name for p in o.iterdir()))
