"""Command line: `ghost-trader` (normal), `ghost-trader --check`, `ghost-trader --demo`, `ghost-trader --version`."""
import argparse
import datetime as dt
import logging
import logging.handlers
import os
import sys

from . import APP_NAME, SYMBOL, __version__, config


def _logging():
    h = logging.handlers.RotatingFileHandler(config.log_path(), maxBytes=1_000_000, backupCount=5)
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(h)


def check():
    """Confirm Yahoo chains + ^IRX come through, the Alpha Vantage key works (if set), the window libraries are
    present and the bundled fonts load. Prints pass/fail for each."""
    results = []

    def item(name, fn):
        try:
            detail = fn()
            results.append(True)
            print(f"  PASS  {name}: {detail}")
        except Exception as e:  # noqa: BLE001
            results.append(False)
            print(f"  FAIL  {name}: {e}")

    print(f"{APP_NAME} v{__version__} self-check")
    from .market import Rates, YahooProvider
    prov = {}

    def yahoo():
        p = YahooProvider()
        prov["p"] = p
        u = p.underlying()
        ex = p.expirations()
        rows = p.chain(ex[min(1, len(ex) - 1)])
        bids = sum(1 for r in rows if r["bid"])
        return f"{SYMBOL} {u['price']:.2f} · {len(ex)} expirations · {len(rows)} contracts in {ex[min(1, len(ex) - 1)]} ({bids} with a bid)"

    def irx():
        p = prov.get("p") or YahooProvider()
        today = dt.date.today()
        s = p.irx(today - dt.timedelta(days=10), today)
        if not s:
            raise RuntimeError("no data")
        d = max(s)
        return f"{s[d]:.2f}% ({d})"

    def av():
        st = config.Settings()
        key = st.get("av_key")
        if not key:
            return "no key set yet (enter it in Settings) · skipped"
        r = Rates(None, st, None)._fetch_av(key)
        d = max(r)
        return f"{r[d]:.2f}% ({d})"

    def fonts():
        names = ["Inter-Regular.woff", "Inter-Medium.woff", "Inter-SemiBold.woff", "Inter-Bold.woff"]
        for n in names:
            b = (config.STATIC_DIR / "fonts" / n).read_bytes()
            if b[:4] != b"wOFF" or len(b) < 10000:
                raise RuntimeError(f"{n} is damaged")
        return "Inter Regular/Medium/SemiBold/Bold bundled and readable"

    def webkit():
        import gi
        gi.require_version("WebKit2", "4.1")
        from gi.repository import WebKit2  # noqa: F401
        import webview  # noqa: F401
        return "WebKitGTK 4.1 + pywebview importable"

    item("Yahoo option chains", yahoo)
    item("^IRX rate via Yahoo", irx)
    item("Alpha Vantage 3-mo Treasury", av)
    item("Bundled fonts", fonts)
    item("Native window libraries", webkit)
    ok = all(results)
    print("All checks passed." if ok else "Some checks failed (see above).")
    return 0 if ok else 1


def notify_check():
    from . import db as dbm, notify
    from .ledger import Ledger
    from .market import YahooProvider
    try:
        d = dbm.DB(config.db_path())
        led = Ledger(d, config.Settings())

        prov = YahooProvider()

        def price():
            return prov.underlying()["price"]

        def readings():
            from .indicators import Indicators
            ind = Indicators(prov)
            ind.refresh()
            return ind.snapshot()
        rate = d.val("SELECT rate FROM rates ORDER BY day DESC LIMIT 1")
        result = notify.daily_check(led, price, settings=led.settings, readings=readings, rate=rate)
        d.close()
    except Exception as e:  # noqa: BLE001
        logging.exception("notify check failed")
        print(f"notify check failed: {e}", file=sys.stderr)
        return 1
    logging.info("notify check: %s", result)
    print(result)
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="ghost-trader", description=f"{APP_NAME}: paper-trade covered calls and "
                                 "cash-secured puts.")
    ap.add_argument("--check", action="store_true", help="test data sources, window libraries and fonts")
    ap.add_argument("--demo", action="store_true", help="synthetic data in a separate demo ledger (no network)")
    ap.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    ap.add_argument("--notify", action="store_true", help="run the weekday notification check: expirations, end-of-day summary, indicator alerts (used by the timer)")
    ap.add_argument("--serve", action="store_true", help="run only the local server and print its URL (testing)")
    ap.add_argument("--port", type=int, default=0)
    args = ap.parse_args(argv)
    if args.check:
        return check()
    if args.demo:
        base = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
        os.environ.setdefault("GHOST_TRADER_HOME", os.path.join(base, "ghost-trader-demo"))
    _logging()
    if args.notify:
        return notify_check()
    from .api import App
    from .server import Server
    try:
        app = App(demo=args.demo)
    except Exception as e:  # noqa: BLE001
        logging.exception("app failed to start")
        print(f"{APP_NAME} couldn't start: {e}", file=sys.stderr)
        return 2
    srv = Server(app, port=args.port).start()
    logging.info("serving %s", srv.url.split("?")[0])
    if args.serve:
        print(srv.url, flush=True)
        try:
            srv.thread.join()
        except KeyboardInterrupt:
            pass
        return 0
    from . import window
    return window.run(app, srv)


if __name__ == "__main__":
    sys.exit(main())
