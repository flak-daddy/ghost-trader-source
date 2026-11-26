"""Ghost Trader Lite: the real app running in the browser under Pyodide, on synthetic data.

Loaded by web/boot.js. Patches the few desktop-only pieces (threads, subprocess, notifications,
startup dialogs), seeds a lived-in demo run relative to today, and exposes `dispatch(name, json)`
which answers the UI's /api/<name> calls exactly like server.py does.
Also importable under plain CPython for tests (tests/test_web.py).
"""
import json
import logging
import math
import os
import random
import subprocess
import threading

HOME = os.environ.setdefault("GHOST_TRADER_HOME", "/gtdata")
WEB = True

# ---------------------------------------------------------------- desktop-only pieces
# Pyodide can't start threads. Run every background job to completion right away instead;
# the app's background work (startup steps, indicator warm-up, earnings fetch) is quick on demo data.
_real_start = threading.Thread.start


def _sync_start(self):
    try:
        if self._target:
            self._target(*self._args, **self._kwargs)
        else:
            self.run()
    except Exception:  # noqa: BLE001
        logging.getLogger("gt.web").exception("background job failed")


def patch_threads():
    threading.Thread.start = _sync_start
    threading.Timer.start = lambda self: None  # only used for restart-after-restore; no-op in the browser


class _NoProc:
    def __init__(self, *a, **k):
        self.returncode = 0

    def wait(self, *a, **k):
        return 0

    def communicate(self, *a, **k):
        return (b"", b"")


def patch_desktop():
    subprocess.Popen = _NoProc
    subprocess.run = lambda *a, **k: subprocess.CompletedProcess(a, 1, b"", b"")
    from ghost_trader import notify, startup

    notify.send = lambda title, body="", *a, **k: (False, "Desktop notifications are in the desktop app only.")
    if hasattr(notify, "ensure_timer"):
        notify.ensure_timer = lambda *a, **k: None

    # Startup dialogs wait for an answer from another thread; here nothing else can answer.
    # Pick the "keep going" option and log it, like choosing it by hand.
    def auto_ask(self, kind, title, what, options, **extra):
        prefer = ("skip", "later", "manual", "ok")
        pick = next((o["id"] for p in prefer for o in options if o["id"] == p), options[0]["id"])
        self.warnings.append(f"{title} ({pick}, automatic in the web demo)")
        return pick, None

    startup.Startup._ask = auto_ask

    # WAL needs shared memory the browser's file system doesn't have, and it would split the ledger
    # across two files when saving to browser storage. Use a plain rollback journal instead.
    from ghost_trader import db as dbm
    if not getattr(dbm.DB.__init__, "_web", False):
        orig = dbm.DB.__init__

        def init(self, *a, **k):
            orig(self, *a, **k)
            self.conn.execute("PRAGMA journal_mode=DELETE")
        init._web = True
        dbm.DB.__init__ = init


# ---------------------------------------------------------------- data
def make_provider():
    from ghost_trader import marketcal, timeutil
    from ghost_trader.market import DemoProvider

    class WebDemoProvider(DemoProvider):
        """DemoProvider, plus a gentle intraday drift so prices move with the clock while the market is open."""
        name = "Demo data (synthetic, moves with the clock)"

        def _intraday(self, d):
            now = timeutil.now_ct()
            if d != now.date() or not marketcal.is_trading_day(d):
                return 0.0
            open_ = now.replace(hour=8, minute=30, second=0, microsecond=0)
            mins = max(0.0, min((now - open_).total_seconds() / 60, 390.0))
            seed = d.toordinal()
            a, b = random.Random(seed).uniform(-1, 1), random.Random(seed + 7).uniform(0, 6.28)
            # smooth path: 0 at the open, back to the day's close at 3 PM, wiggling in between
            env = math.sin(mins / 390 * math.pi)
            return round(self.base * 0.012 * env * (a + 0.35 * math.sin(mins / 37 + b)), 2)

        def underlying(self):
            u = super().underlying()
            p = round(u["price"] + self._intraday(timeutil.today_ct()), 2)
            u.update(price=p, bid=round(p - .01, 2), ask=round(p + .01, 2))
            return u

        def chain(self, expiry):
            # DemoProvider.chain prices off self.underlying(), so it already follows the drift
            return super().chain(expiry)

    return WebDemoProvider()


# ---------------------------------------------------------------- the app
app = None
_methods = {}


def start():
    """Create the app (seeding a demo run on first visit). Returns 'seeded' or 'resumed'."""
    global app, _methods
    patch_threads()
    patch_desktop()
    logging.basicConfig(level=logging.WARNING)
    from ghost_trader import config
    from ghost_trader.api import App

    os.makedirs(HOME, exist_ok=True)
    fresh = not config.db_path().exists()
    if fresh:
        import seed_web
        seed_web.seed(make_provider())
    app = App(demo=True, provider=make_provider())
    app.web = True
    _methods = {n[4:]: getattr(app, n) for n in dir(app) if n.startswith("api_")}
    return "seeded" if fresh else "resumed"


def dispatch(name, args_json="{}"):
    """Same contract as server.py's POST /api/<name>: returns (status, json text)."""
    fn = _methods.get(name)
    if not fn:
        return 404, json.dumps({"error": f"no such call: {name}"})
    try:
        args = json.loads(args_json or "{}") or {}
        return 200, json.dumps(fn(**args), default=str)
    except TypeError as e:
        return 400, json.dumps({"error": f"bad call: {e}"})
    except Exception as e:  # noqa: BLE001
        logging.getLogger("gt.web").exception("api %s failed", name)
        return 500, json.dumps({"error": f"{type(e).__name__}: {e}"})


def reset():
    """Throw away this browser's demo ledger; the next start() seeds a new one."""
    global app
    import shutil
    try:
        app.db.close()
    except Exception:  # noqa: BLE001
        pass
    app = None
    for name in os.listdir(HOME):
        p = os.path.join(HOME, name)
        shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
