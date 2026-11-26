# Ghost Trader Lite (web demo)

The real Ghost Trader running in a browser on synthetic data, for showing it off.

- **How:** [Pyodide](https://pyodide.org) runs the `ghost_trader` package in the page. `boot.js` answers the UI's
  `POST /api/<name>` calls with `gt_web.dispatch()` instead of the local server; the UI files are unchanged.
- **Data:** `DemoProvider` prices, plus a smooth intraday drift while the market is open, on the real clock and
  market calendar. On a visitor's first load, `seed_web.py` creates about 8 weeks of history ending today (a
  finished wheel, a running wheel, weeklies, an early close, an open put).
- **Saved per browser:** each visitor's run lives in their browser (IndexedDB). "Reset demo" starts over.
- **Lighter than the desktop app:** no desktop notifications, updates, data folder or real file downloads;
  startup questions take the "keep going" answer automatically.

## Build and publish

    python tools/build_web.py            # -> dist/web (serve it from any static host)
    python -m http.server -d dist/web    # try it locally at http://localhost:8000

Published by hand to GitHub Pages on the public `flak-daddy/ghost-trader-source` repo (branch `gh-pages`):
**Actions → Publish Lite → Run workflow** (optionally with a tag). Site:
https://flak-daddy.github.io/ghost-trader-source/

One-time setup: in `ghost-trader-source` → Settings → Pages, set Source to "Deploy from a branch",
branch `gh-pages`, folder `/ (root)`.

Not a Claude artifact: those pages block Pyodide from downloading its own files (connect-src).
