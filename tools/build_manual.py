"""Build the manual's release files: a PDF (via headless Chrome), a plain-text copy, and the Markdown.

    python tools/build_manual.py [--out dist]

Needs Google Chrome or Chromium on PATH (or set CHROME=/path/to/chrome).
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ghost_trader import __version__, manual  # noqa: E402

FONTS = ROOT / "ghost_trader" / "static" / "fonts"

CSS = """
@font-face{font-family:"Inter";src:url("%(f)s/Inter-Regular.woff");font-weight:400}
@font-face{font-family:"Inter";src:url("%(f)s/Inter-Medium.woff");font-weight:500}
@font-face{font-family:"Inter";src:url("%(f)s/Inter-SemiBold.woff");font-weight:600}
@font-face{font-family:"Inter";src:url("%(f)s/Inter-Bold.woff");font-weight:700}
@page{size:Letter;margin:0.8in 0.85in}
html{font:10.5pt/1.55 "Inter","DejaVu Sans",sans-serif;color:#15181e}
body{margin:0}
.cover{height:9.2in;display:flex;flex-direction:column;justify-content:center;break-after:page}
.cover .kicker{color:#2f6fde;font-weight:600;letter-spacing:.08em;text-transform:uppercase;font-size:10pt}
.cover h1{font-size:34pt;line-height:1.1;margin:.15in 0 .2in}
.cover p{font-size:13pt;color:#3c4350;max-width:5.2in;margin:0}
.cover .meta{margin-top:.5in;font-size:10pt;color:#5d6575}
.cover + h1, .cover + h1 + p{display:none}
h2{font-size:17pt;margin:0 0 8pt;padding-top:2pt;break-after:avoid}
.manual hr + h2{break-before:page}
.manual hr{display:none}
h3{font-size:12.5pt;margin:16pt 0 4pt;break-after:avoid}
h4{font-size:11pt;margin:12pt 0 3pt;break-after:avoid}
p{margin:0 0 7pt}
a{color:#2f6fde;text-decoration:none}
blockquote{margin:10pt 0;padding:7pt 12pt;border-left:3px solid #2f6fde;background:#eef3fc;break-inside:avoid}
blockquote p{margin:3pt 0}
table{width:100%%;border-collapse:collapse;margin:6pt 0 10pt;font-size:9.5pt;break-inside:auto}
tr{break-inside:avoid}
th{text-align:left;color:#5d6575;font-weight:600;font-size:8pt;text-transform:uppercase;letter-spacing:.03em;
   border-bottom:1.5px solid #c9ced8;padding:4pt 6pt}
td{border-bottom:1px solid #dde1e8;padding:4pt 6pt;vertical-align:top}
ul,ol{margin:0 0 8pt;padding-left:18pt}
li{margin:2pt 0}
code{font-family:"DejaVu Sans Mono",monospace;font-size:.88em;background:#eef0f4;padding:0 3pt;border-radius:3px}
"""


def find_chrome() -> str:
    for c in (os.environ.get("CHROME"), "google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        if c and shutil.which(c):
            return shutil.which(c)
    sys.exit("Chrome or Chromium not found (set CHROME=/path/to/chrome).")


def build(out: Path) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    md = (ROOT / "MANUAL.md").read_text(encoding="utf-8")
    body, toc = manual.render(md)
    today = dt.date.today().strftime("%B %Y")
    cover = (f'<section class="cover"><div class="kicker">Ghost Trader v{__version__}</div>'
             f"<h1>Ghost Trader Manual</h1><p>Cash-secured puts, covered calls and TQQQ, explained from scratch, "
             f"plus how Ghost Trader models all of it.</p><div class=\"meta\">{today} · Paper trading only. "
             f"Education, not financial advice.</div></section>")
    page = manual.page("Ghost Trader Manual", cover + body, toc, CSS % {"f": FONTS.as_uri()})
    pdf = out / "ghost-trader-manual.pdf"
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "manual.html"
        src.write_text(page, encoding="utf-8")
        subprocess.run([find_chrome(), "--headless=new", "--no-sandbox", "--disable-gpu", "--no-pdf-header-footer",
                        "--generate-pdf-document-outline", f"--user-data-dir={tmp}/profile",
                        f"--print-to-pdf={pdf}", src.as_uri()],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
    if not pdf.exists() or pdf.stat().st_size < 10_000:
        sys.exit("PDF wasn't produced.")
    txt = out / "ghost-trader-manual.txt"
    txt.write_text(manual.to_text(md), encoding="utf-8")
    mdo = out / "MANUAL.md"
    mdo.write_text(md, encoding="utf-8")
    return [pdf, txt, mdo]


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=str(ROOT / "dist"))
    for f in build(Path(ap.parse_args().out)):
        print(f)
