"""The startup refresh: the only time data is refreshed in bulk. Runs in a background thread while the UI shows
the loading screen. Each step auto-retries once; if it fails again it raises an *issue* (a dialog in the UI)
with ways to fix it, retry, or skip. Skips are logged to History and the data is marked stale."""
import datetime as dt
import json
import logging
import threading
import time
import traceback

from . import SYMBOL, __version__, config, ivhist, marketcal, timeutil, updater
from .ledger import money

log = logging.getLogger("ghost_trader.startup")

STEPS = [
    ("update", "Check for updates"),
    ("rate", "Interest rate"),
    ("interest", "Interest"),
    ("settle", "Expirations, dividends, splits"),
    ("quotes", "Re-quote open positions"),
    ("price", f"{SYMBOL} price + expirations"),
    ("snapshot", "Daily snapshot + backup"),
]


class Skip(Exception):
    pass


class Startup:
    def __init__(self, app):
        self.app = app
        self.state = "idle"  # idle | running | issue | done | restarting
        self.steps = [{"id": s, "name": n, "status": "pending", "detail": "", "t": None} for s, n in STEPS]
        self.issue = None
        self._answer = None
        self._cv = threading.Condition()
        self.started = None
        self.finished = None
        self.warnings = []
        self._manual = {}

    # ------------------------------------------------------------------ public
    def start(self):
        if self.state != "idle":
            return
        self.state = "running"
        self.started = timeutil.now()
        threading.Thread(target=self._run, name="startup", daemon=True).start()

    def status(self):
        return {"state": self.state, "steps": self.steps, "issue": self.issue, "version": __version__,
                "started": self.started and timeutil.fmt_ct(self.started),
                "warnings": self.warnings}

    def resolve(self, issue_id, choice, value=None):
        with self._cv:
            if not self.issue or self.issue["id"] != issue_id:
                return False
            self._answer = (choice, value)
            self._cv.notify_all()
            return True

    # ------------------------------------------------------------------ internals
    def _ask(self, kind, title, what, options, **extra):
        iid = f"{kind}-{time.time():.3f}"
        with self._cv:
            self.issue = {"id": iid, "kind": kind, "title": title, "what": what, "options": options, **extra}
            self.state = "issue"
            self._answer = None
            while self._answer is None:
                self._cv.wait(0.5)
            ans = self._answer
            self.issue = None
            self.state = "running"
        return ans

    def _step(self, sid):
        return next(s for s in self.steps if s["id"] == sid)

    def _mark(self, sid, status, detail=""):
        s = self._step(sid)
        s.update(status=status, detail=detail, t=timeutil.fmt_ct(timeutil.now(), with_et=False))

    def _run(self):
        a = self.app
        try:
            for sid, _name in STEPS:
                self._mark(sid, "working")
                fn = getattr(self, "_s_" + sid)
                try:
                    detail = fn()
                    s = self._step(sid)
                    if sid in self._manual:
                        self._mark(sid, "warn", f"{detail} · {self._manual[sid]}")
                        self.warnings.append(f"{s['name']}: {self._manual[sid]}")
                    elif s["status"] == "working":
                        self._mark(sid, "ok", detail or "")
                except Skip as e:
                    self._mark(sid, "warn", str(e))
                    self.warnings.append(f"{self._step(sid)['name']}: {e}")
                if self.state == "restarting":
                    return
            self.finished = timeutil.now()
            a.data_asof = self.finished
            a.db.x("INSERT INTO reports(ts,data) VALUES(?,?)", (timeutil.iso(self.finished), json.dumps({
                "steps": self.steps, "started": timeutil.iso(self.started), "finished": timeutil.iso(self.finished),
                "warnings": self.warnings})))
            if a.led.run():
                a.led.event("App", "Startup refresh", " · ".join(f"{s['name']}: {s['detail']}" for s in self.steps
                                                                  if s["detail"]), ts=self.finished)
            self.state = "done"
            threading.Thread(target=ivhist.record_safe, args=(a,), daemon=True).start()
        except Exception as e:  # noqa: BLE001 - never leave the UI hanging
            log.exception("startup crashed")
            a.log_error("Startup problem", f"Something unexpected went wrong during the startup refresh: {e}",
                        "The app opened with the data it already had.", "Restart to try again.",
                        traceback.format_exc())
            self.warnings.append(f"Startup stopped early: {e}")
            self.state = "done"
            a.data_asof = timeutil.now()

    def _retry(self, fn, sid, title, what_prefix, options, on_choice):
        """Run fn; retry once; then ask. on_choice(choice, value) returns a result or raises Skip/continues."""
        last = None
        for attempt in range(2):
            try:
                return fn()
            except Exception as e:  # noqa: BLE001
                last = e
                log.warning("%s attempt %d failed: %s", sid, attempt + 1, e)
                time.sleep(0.4)
        while True:
            choice, value = self._ask(sid, title, f"{what_prefix} {last}", options)
            if choice == "retry":
                try:
                    return fn()
                except Exception as e:  # noqa: BLE001
                    last = e
                    continue
            try:
                return on_choice(choice, value)
            except ValueError as e:
                last = e
                continue

    # ------------------------------------------------------------------ steps
    def _s_update(self):
        a = self.app
        rn = config.data_dir() / "restore-note.txt"
        if rn.exists():
            a.led_event_safe("App", "Ledger restored", rn.read_text().strip())
            rn.unlink(missing_ok=True)
        note = config.data_dir() / "rollback-note.txt"
        if note.exists():
            a.led_event_safe("Update", "Update rolled back", note.read_text().strip(), warning=True)
            note.unlink(missing_ok=True)
        mark = updater.pending()
        if mark:
            probs = updater.self_check()
            if probs:
                a.led_event_safe("Update", f"Update to {mark.get('to')} rolled back",
                                 "The new version failed its startup self-check: " + "; ".join(probs)
                                 + f". Went back to {mark.get('from')} and restored the ledger backup.", warning=True)
                updater.rollback(mark, a.restore_backup)
                self.state = "restarting"
                a.request_restart()
                return "rolled back"
            updater.clear_pending()
            notes = ""
            try:
                notes = updater._git("tag", "-l", "--format=%(contents)", mark.get("to") or "")
            except Exception:  # noqa: BLE001
                pass
            a.led_event_safe("Update", f"Updated to {mark.get('to')}",
                             (f"From {mark.get('from')}. " if mark.get("from") else "") + (notes or ""))
        if a.demo:
            return f"v{__version__} (demo)"
        if config.install_kind() == "system":
            try:
                info = updater.check_public()
            except Exception as e:  # noqa: BLE001
                log.info("public update check failed: %s", e)
                raise Skip("couldn't reach GitHub to check for a newer version · skipped")
            if not info:
                return f"v{__version__} is current"
            self._ask("update-notice", f"Ghost Trader v{info['version']} is available",
                      f"You have v{__version__}. To update, close Ghost Trader, then:\n\n"
                      "  Installed from the AUR:\n    yay -Syu ghost-trader\n\n"
                      "  Built from the source repo:\n    cd ghost-trader-source && git pull\n"
                      "    cd packaging/arch && yay -Bi .\n\nYour account and settings are kept.",
                      [{"id": "ok", "label": "OK", "primary": True}])
            return f"v{info['version']} available · update with yay -Syu"
        if not updater.is_checkout():
            return f"v{__version__} · not a git checkout, updates off"
        try:
            info = updater.check()
        except Exception as e:  # noqa: BLE001
            a.log_error("Update check failed", f"Couldn't reach GitHub to check for updates: {e}",
                        "Skipped the update check.", "Nothing needed; it checks again next startup.", warning=True)
            raise Skip("couldn't reach GitHub · skipped")
        if not info:
            return f"v{__version__} is current"
        choice, _ = self._ask("update", f"Update to v{info['version']}?", info["notes"] or "No change list.",
                              [{"id": "update", "label": "Update and restart", "primary": True},
                               {"id": "later", "label": "Not now"}], tag=info["tag"], current=__version__)
        if choice != "update":
            return f"v{info['version']} available · not now"
        try:
            res = updater.apply(info["tag"], lambda: a.backup("pre-update"))
        except Exception as e:  # noqa: BLE001
            a.log_error("Update not applied", str(e), "Stayed on v" + __version__ + ".",
                        "See the message; then restart.", warning=True)
            self._ask("update-failed", "Update not applied", str(e), [{"id": "ok", "label": "OK", "primary": True}])
            raise Skip("update not applied")
        log.info("updated %s -> %s", res["from"], res["to"])
        self.state = "restarting"
        a.request_restart()
        return f"updating to {info['tag']}…"

    def _s_rate(self):
        a = self.app
        r = a.led.run()
        since = dt.date.fromisoformat(r["start_day"]) if r else timeutil.today_ct()
        last = a.led.last_accrual_day()
        if last:
            since = min(since, last)

        def fetch():
            return a.rates.refresh(since)

        def choose(choice, value):
            if choice == "rate":
                v = float(str(value).replace("%", "").strip())
                if not 0 <= v < 25:
                    raise ValueError("Enter a rate like 4.24")
                a.settings.update(manual_rate=v)
                a.rates.store({timeutil.today_ct().isoformat(): v}, "manual")
                self._manual["rate"] = "entered by you"
                a.log_error("Interest rate entered manually", "Couldn't get the 3-month T-bill rate automatically.",
                            f"Used the {v:.2f}% you entered.", "Check your Alpha Vantage key in Settings.", warning=True)
                return a.rates.latest()
            if choice == "key":
                a.settings.update(av_key=str(value or "").strip())
                return a.rates.refresh(since)
            rate, day, src = a.rates.latest()
            a.log_error("Interest rate not refreshed", "Couldn't get the 3-month T-bill rate from any source.",
                        f"Kept using the last known rate ({rate or 0:.2f}%).", "Enter a manual rate or your Alpha Vantage "
                        "key in Settings.", warning=True)
            raise Skip(f"skipped · using {rate or 0:.2f}% from {day or 'n/a'}")

        rate, day, src = self._retry(fetch, "rate", "Couldn't get the interest rate",
                                     "Tried Alpha Vantage, then ^IRX via Yahoo.",
                                     [{"id": "rate", "label": "Use this rate (%)", "input": "4.24", "primary": True},
                                      {"id": "key", "label": "Save Alpha Vantage key and retry", "input": "API key"},
                                      {"id": "retry", "label": "Retry"}, {"id": "skip", "label": "Skip"}], choose)
        return f"{rate:.2f}% · {src} ({timeutil.fmt_date(day)})"

    def _s_interest(self):
        a = self.app
        if not a.led.run():
            return "no run yet"
        today = timeutil.today_ct()
        n, amt, evs = a.led.catch_up_interest(today, a.rates.for_day, a.settings.get("haircut") or 0.0)
        txt = f"accrued {n} day{'s' if n != 1 else ''} ({money(round(amt * 100), True)})" if n else "up to date"
        if evs:
            txt += f" · {len(evs)} payment{'s' if len(evs) > 1 else ''} posted"
        return txt

    def _s_settle(self):
        a = self.app
        if not a.led.run():
            return "no run yet"
        now = timeutil.now()
        done = []
        for exp in a.led.due_expirations(now):
            def fetch(exp=exp):
                closes = a.provider.daily_closes(exp, exp)
                c = closes.get(exp.isoformat())
                if not c:
                    raise RuntimeError(f"no official close for {timeutil.fmt_date(exp)} yet")
                return c

            def choose(choice, value, exp=exp):
                if choice == "close":
                    v = float(str(value).replace("$", "").strip())
                    if v <= 0:
                        raise ValueError("Enter the closing price, like 56.56")
                    return v
                a.log_error(f"Expiration not settled ({timeutil.fmt_date(exp)})",
                            f"Couldn't get {SYMBOL}'s official close for {timeutil.fmt_date(exp)}.",
                            "Left those positions open; they settle at a later startup.",
                            "Enter the closing price when asked, or wait for the next startup.", warning=True)
                return None

            close = self._retry(fetch, "settle", f"Couldn't get the {timeutil.fmt_date(exp)} close",
                                f"Needed to settle positions expiring {timeutil.fmt_exp(exp)}.",
                                [{"id": "close", "label": f"Use this {SYMBOL} close", "input": "56.56", "primary": True},
                                 {"id": "retry", "label": "Retry"}, {"id": "skip", "label": "Skip"}], choose)
            if close is None:
                continue
            evs = a.led.settle_expiration(exp, close, now)
            done.append(f"{timeutil.fmt_date(exp)}: {len(evs)} settled")
        # dividends
        r = a.led.run()
        try:
            for d, amt in a.provider.dividends():
                if d > dt.date.fromisoformat(r["start_day"]) and d <= timeutil.today_ct():
                    if a.led.credit_dividend(d, amt, now):
                        done.append(f"dividend {timeutil.fmt_date(d)}")
        except Exception as e:  # noqa: BLE001
            log.warning("dividends: %s", e)
        # splits
        try:
            for d, ratio in a.provider.splits():
                if d > dt.date.fromisoformat(r["start_day"]):
                    known = a.db.one("SELECT handled FROM splits WHERE symbol=? AND day=?", (SYMBOL, d.isoformat()))
                    if known and known[0]:
                        continue
                    a.db.x("INSERT OR IGNORE INTO splits(symbol,day,ratio) VALUES(?,?,?)", (SYMBOL, d.isoformat(), ratio))
                    self._split_dialog(d, ratio)
                    done.append(f"split {timeutil.fmt_date(d)}")
        except Exception as e:  # noqa: BLE001
            log.warning("splits: %s", e)
        return " · ".join(done) if done else "nothing to settle"

    def _split_dialog(self, d, ratio):
        a = self.app
        aff = a.led.positions()
        lots = a.led.lots()
        lines = [f"{p['label']} ({p['open_qty']}) → strike ${p['strike'] / ratio:.2f}, {p['open_qty']} contracts of "
                 f"{int(100 * ratio)} shares" for p in aff]
        lines += [f"Lot of {lt['open_qty']} shares @ ${lt['cost']:.2f} → {int(lt['open_qty'] * ratio)} @ "
                  f"${lt['cost'] / ratio:.2f}" for lt in lots]
        what = (f"{SYMBOL} split {ratio:g}-for-1 on {timeutil.fmt_date(d)}. Prices before and after aren't comparable. "
                "Affected items and the standard adjustment:\n" + ("\n".join(lines) if lines else "Nothing is affected."))
        choice, _ = self._ask("split", f"{SYMBOL} split {ratio:g}-for-1", what,
                              [{"id": "apply", "label": "Apply these adjustments", "primary": True},
                               {"id": "manual", "label": "I'll adjust by hand later"}])
        with a.db.tx():
            if choice == "apply" and lines:
                for lt in lots:
                    a.db.x("UPDATE lots SET qty=CAST(qty*? AS INTEGER), open_qty=CAST(open_qty*? AS INTEGER), cost=cost/? "
                           "WHERE id=?", (ratio, ratio, ratio, lt["id"]))
                    a.db.x("UPDATE lot_moves SET qty=CAST(qty*? AS INTEGER), price=price/? WHERE lot_id=?",
                           (ratio, ratio, lt["id"]))
                for p in aff:
                    # Contracts keep their count; each now covers more shares. Approximate by scaling count.
                    a.db.x("UPDATE positions SET strike=strike/?, open_price=open_price/?, qty=CAST(qty*? AS INTEGER),"
                           " open_qty=CAST(open_qty*? AS INTEGER) WHERE id=?", (ratio, ratio, ratio, ratio, p["id"]))
            a.db.x("UPDATE splits SET handled=1 WHERE symbol=? AND day=?", (SYMBOL, d.isoformat()))
            a.led.event("Split", f"{SYMBOL} split {ratio:g}-for-1 ({timeutil.fmt_date(d)})",
                        ("Applied the standard adjustment: " if choice == "apply" else "Left for manual adjustment: ")
                        + ("; ".join(lines) or "nothing affected"), warning=choice != "apply")

    def _s_quotes(self):
        a = self.app
        pos = a.led.positions()
        if not pos:
            return "no open positions"
        exps = sorted({p["expiry"] for p in pos})
        fresh, stale = 0, []
        try:
            a.quotes.underlying(fresh=True)
        except Exception:  # noqa: BLE001
            pass
        for e in exps:
            held = [p for p in pos if p["expiry"] == e]
            bad = held
            for _ in range(2):
                try:
                    got = a.quotes.chain(e, fresh=True)
                    bad = _not_refreshed(got, held)
                    if not bad:
                        break
                except Exception:  # noqa: BLE001
                    bad = held
                time.sleep(0.3)
            fresh += len(held) - len(bad)
            stale += bad
        if stale:
            names = ", ".join(p["label"] for p in stale)
            choice, _ = self._ask("quotes", "Some quotes didn't refresh",
                                  f"Couldn't get fresh quotes for: {names}.",
                                  [{"id": "retry", "label": "Retry", "primary": True},
                                   {"id": "skip", "label": "Use last good quotes"}])
            if choice == "retry":
                return self._s_quotes()
            a.log_error("Stale quote", f"Couldn't get a fresh quote for {names} after 2 tries.",
                        "Used the last good quotes and marked them stale.",
                        "Nothing required; the next startup tries again.")
            raise Skip(f"{fresh} of {len(pos)} fresh · {len(stale)} used last good quote")
        return f"{len(pos)} position{'s' if len(pos) > 1 else ''} re-quoted"

    def _s_price(self):
        a = self.app

        def fetch():
            u = a.quotes.underlying(fresh=True)
            if u.get("stale"):
                raise RuntimeError(u.get("error") or "price unavailable")
            ex = a.quotes.expirations(fresh=True)
            return u, ex

        def choose(choice, value):
            if choice == "price":
                v = float(str(value).replace("$", "").strip())
                if v <= 0:
                    raise ValueError("Enter a price like 56.56")
                u = a.quotes.set_manual_price(v)
                self._manual["price"] = "price entered by you"
            else:
                self._manual["price"] = "using the last known price"
                u = a.quotes.underlying()
            try:
                ex = a.quotes.expirations()
            except Exception:  # noqa: BLE001
                ex = []
            a.log_error(f"{SYMBOL} price not refreshed", f"Couldn't get a current {SYMBOL} price.",
                        f"Using {'your entered' if choice == 'price' else 'the last known'} price ${u['price']:.2f}.",
                        "Nothing required; the next startup tries again.", warning=True)
            return u, ex

        u, ex = self._retry(fetch, "price", f"Couldn't get the {SYMBOL} price", "Yahoo didn't answer:",
                            [{"id": "price", "label": f"Use this {SYMBOL} price", "input": "56.56", "primary": True},
                             {"id": "retry", "label": "Retry"}, {"id": "skip", "label": "Skip (use last known)"}], choose)
        # daily closes since run start (chart + gap fill)
        r = a.led.run()
        if r:
            try:
                start = dt.date.fromisoformat(r["start_day"]) - dt.timedelta(days=7)
                have = a.db.val("SELECT MAX(day) FROM prices WHERE symbol=?", (SYMBOL,))
                if have:
                    start = max(start, dt.date.fromisoformat(have) - dt.timedelta(days=3))
                closes = a.provider.daily_closes(start, timeutil.today_ct())
                with a.db.tx():
                    for d, c in closes.items():
                        a.db.x("INSERT OR REPLACE INTO prices(symbol,day,close) VALUES(?,?,?)", (SYMBOL, d, c))
            except Exception as e:  # noqa: BLE001
                log.warning("daily closes: %s", e)
        return f"${u['price']:.2f} · {len(ex)} expirations"

    def _s_snapshot(self):
        a = self.app
        a.backup("startup")
        r = a.led.run()
        if not r:
            return "backup saved"
        today = timeutil.today_ct()
        closes = {row[0]: row[1] for row in a.db.q("SELECT day, close FROM prices WHERE symbol=? AND day>=?",
                                                   (SYMBOL, r["start_day"]))}
        if not a.demo:
            from . import notify
            note = notify.ensure_timer()
            if note:
                a.led_event_safe("App", "Expiration-day notifications", note[0].upper() + note[1:] + ".",
                                 warning=note.startswith("couldn't"))
        n = a.led.fill_snapshot_gaps(closes, today)
        u = a.quotes.underlying()
        close = closes.get(today.isoformat()) or u["price"]
        a.led.snapshot(today, u["price"], close, marks=a.marks())
        return "saved · ledger backed up" + (f" · {n} missed day{'s' if n > 1 else ''} estimated" if n else "")


def market_line(ts=None):
    ts = ts or timeutil.now()
    st, lbl = marketcal.market_status(ts)
    return st, lbl


def _session_start(now):
    """Start (8:30 AM CT) of the latest trading session that has begun."""
    now_c = now.astimezone(timeutil.CT)
    d = now_c.date()
    if not marketcal.is_trading_day(d) or now_c.time() < dt.time(8, 30):
        d = marketcal.prev_trading_day(d)
    return dt.datetime.combine(d, dt.time(8, 30), tzinfo=timeutil.CT)


def _not_refreshed(chain, held, now=None):
    """Held positions whose own contract has no usable current quote. Other strikes falling back to their last good
    quote (common after hours, when Yahoo blanks far-away strikes) don't count. With the market closed, a held
    contract's quote from the latest session (e.g. the close) counts as current: that's what trading uses then."""
    now = now or timeutil.now()
    closed = not marketcal.is_open(now)
    since = _session_start(now)
    rows = {(r["type"], r["strike"]): r for r in chain.get("rows", [])}
    out = []
    for p in held:
        r = rows.get((p["type"], p["strike"]))
        ok = r is not None and bool(r.get("bid") or r.get("ask"))
        if ok and r.get("fallback"):
            try:
                ok = closed and timeutil.parse(r["asof"]) >= since
            except Exception:  # noqa: BLE001
                ok = False
        if not ok:
            out.append(p)
    return out

