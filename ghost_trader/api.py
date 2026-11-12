"""The application object and every call the UI makes. Each public `api_*` method takes JSON-able keyword
arguments and returns JSON-able data. Rule failures come back as {'error': message}."""
import datetime as dt
import json
import logging
import subprocess
import threading
import time
from pathlib import Path

from . import SYMBOL, __version__, config, csvout, db as dbm, events, marketcal, notify, perf, timeutil
from .ledger import Ledger, TradeError, cents, money, strike_txt
from .market import DemoProvider, Quotes, Rates, YahooProvider
from .startup import Startup

log = logging.getLogger("ghost_trader.api")


def _fmt_ts(ts):
    t = timeutil.parse(ts) if isinstance(ts, str) else ts
    c, e = t.astimezone(timeutil.CT), t.astimezone(timeutil.ET)
    clock = lambda x: x.strftime("%I:%M %p").lstrip("0")  # noqa: E731
    return {"d": c.strftime("%b ") + str(c.day) + ", " + clock(c), "et": clock(e), "day": c.date().isoformat()}


class App:
    def __init__(self, demo=False, provider=None):
        self.demo = demo
        self.settings = config.Settings()
        self.db = dbm.DB(config.db_path())
        self.led = Ledger(self.db, self.settings)
        self.provider = provider or (DemoProvider() if demo else YahooProvider())
        self.rates = Rates(self.db, self.settings, self.provider)
        self.quotes = Quotes(self.db, self.provider, self.rates)
        self.startup = Startup(self)
        self.data_asof = None
        self.loaded = threading.Event()
        self.last_beat = time.time()
        self.window = None          # set by window.py: object with save_dialog(name) -> path|None
        self.restart_requested = False
        self.on_restart = None

    # ------------------------------------------------------------------ plumbing
    def backup(self, label="startup"):
        return dbm.rotate_backups(self.db, config.data_dir() / "backups", 30, label)

    def restore_backup(self, path):
        self.db.close()
        dbm.restore_backup(path, config.db_path())

    def request_restart(self):
        self.restart_requested = True
        if self.on_restart:
            threading.Timer(1.2, self.on_restart).start()

    def led_event_safe(self, kind, title, detail, warning=False):
        try:
            self.led.event(kind, title, detail, warning=warning)
        except Exception:  # noqa: BLE001
            log.exception("event log failed")

    def log_error(self, title, what, did, todo, tech=None, warning=False):
        log.error("%s: %s | %s", title, what, tech or "")
        detail = what
        self.led.event("Error" if not warning else "Warning", title, detail,
                       {"what": what, "did": did, "todo": todo, "log": "logs/ghost-trader.log"},
                       error=not warning, warning=warning)

    def marks(self):
        out = {}
        for p in self.led.positions():
            try:
                q = self.quotes.quote(p["expiry"], p["type"], p["strike"], fresh=False)
                if q:
                    out[str(p["id"])] = q["mid"]
            except Exception:  # noqa: BLE001
                pass
        return out

    def price(self):
        try:
            return self.quotes.underlying()["price"]
        except Exception:  # noqa: BLE001
            r = self.db.one("SELECT close FROM prices WHERE symbol=? ORDER BY day DESC LIMIT 1", (SYMBOL,))
            return r[0] if r else None

    # ------------------------------------------------------------------ boot / lifecycle
    def api_boot(self):
        return {"version": __version__, "demo": self.demo, "theme": self.settings.get("theme"),
                "provider": self.provider.name, "symbol": SYMBOL}

    def api_loaded(self):
        self.loaded.set()
        self.last_beat = time.time()
        self.startup.start()
        return {"ok": True}

    def api_gate_answer(self, answer):
        self.gate_answer = answer
        g = getattr(self, "gate", None)
        if g:
            g.set()
        return {"ok": True}

    def api_heartbeat(self):
        self.last_beat = time.time()
        return {"ok": True, "restarting": self.restart_requested}

    def api_startup_status(self):
        return self.startup.status()

    def api_startup_resolve(self, issue_id, choice, value=None):
        return {"ok": self.startup.resolve(issue_id, choice, value)}

    def api_report(self):
        r = self.db.one("SELECT * FROM reports ORDER BY id DESC LIMIT 1")
        if not r:
            return {"steps": self.startup.steps, "started": None}
        d = json.loads(r["data"])
        st = timeutil.parse(d["started"])
        took = (timeutil.parse(d["finished"]) - st).total_seconds()
        d["when"] = st.astimezone(timeutil.CT).strftime("%a %b ") + str(st.astimezone(timeutil.CT).day) + ", " + \
            timeutil.fmt_ct(st)
        d["took"] = f"{took:.0f} s"
        return d

    # ------------------------------------------------------------------ header + portfolio
    def _market(self):
        now = timeutil.now()
        status, lbl = marketcal.market_status(now)
        lc = marketcal.last_close_dt(now)
        return {"open": status == "open", "label": lbl,
                "close_txt": timeutil.fmt_ct(lc, with_et=True)}

    def api_state(self):
        S = self.price()
        r = self.led.run()
        u = {}
        try:
            u = self.quotes.underlying()
        except Exception:  # noqa: BLE001
            pass
        out = {"run": None, "price": S, "prev_close": u.get("prev_close"), "price_stale": u.get("stale", True),
               "market": self._market(), "version": __version__, "demo": self.demo,
               "data_asof": timeutil.fmt_ct(self.data_asof) if self.data_asof else None,
               "errors": self.db.val("SELECT COUNT(*) FROM events WHERE (run_id=? OR run_id IS NULL) AND is_error=1",
                                     (r["id"] if r else -1,), 0)}
        if not r:
            return out
        b = self.led.breakdown(S or 0)
        pos = []
        today = timeutil.today_ct()
        for p in self.led.positions():
            q = None
            try:
                q = self.quotes.quote(p["expiry"], p["type"], p["strike"], fresh=False)
            except Exception:  # noqa: BLE001
                pass
            mark = q["mid"] if q else None
            sign = 1 if p["side"] == "short" else -1
            pnl = cents((p["open_price"] - mark) * 100 * p["open_qty"]) * sign if mark is not None else None
            prem = cents(p["open_price"]) * 100 * p["open_qty"]
            dte = (dt.date.fromisoformat(p["expiry"]) - today).days
            dist = (S - p["strike"]) / p["strike"] if S else None
            otm = (S > p["strike"]) if p["type"] == "put" else (S < p["strike"]) if S else None
            pos.append({**_pubpos(p), "mark": mark, "bid": q and q["bid"], "ask": q and q["ask"], "pnl_c": pnl,
                        "pnl_pct": (pnl / prem) if (pnl is not None and prem) else None,
                        "dte": dte, "dist": dist, "otm": otm, "quote_stale": q["stale"] if q else True})
        # alerts
        alerts = []
        mon = today - dt.timedelta(days=today.weekday())
        sun = mon + dt.timedelta(days=6)
        for p in pos:
            if dt.date.fromisoformat(p["expiry"]) <= sun:
                alerts.append({"kind": "expiring", "pos": p})
        for p in pos:
            if p["type"] == "put" and p["side"] == "short" and S and (S - p["strike"]) / p["strike"] < 0.03:
                alerts.append({"kind": "near", "pos": p})
        lots = [dict(lt) for lt in self.led.lots()]
        for lt in lots:
            lt["acquired"] = timeutil.fmt_date(lt["acquired_day"])
        nxt = marketcal.next_pay_date(today - dt.timedelta(days=1))
        ex_div = None
        try:
            ex_div = self.provider.next_ex_dividend()
        except Exception:  # noqa: BLE001
            pass
        if ex_div and 0 <= (ex_div - today).days <= 7:
            for p in pos:
                if p["type"] == "call" and p["side"] == "short" and S and S > p["strike"] \
                        and dt.date.fromisoformat(p["expiry"]) >= ex_div:
                    alerts.append({"kind": "exdiv", "pos": p, "ex": timeutil.fmt_date(ex_div)})
        out.update({
            "run": {"id": r["id"], "start_day": r["start_day"], "start_txt": dt.date.fromisoformat(r["start_day"]).strftime("%b %-d, %Y"),
                    "start_cash_c": r["start_cash_c"]},
            "bal": b, "positions": pos, "lots": lots, "alerts": alerts,
            "shares": self.led.shares(), "locked": self.led.locked_shares(), "avg_cost": self.led.avg_cost(),
            "premium_c": self.led.premium_collected_c(), "interest_c": self.led.interest_earned_c(),
            "dividends_c": self.led.dividends_c(),
            "next_pay": timeutil.fmt_exp(nxt) if nxt else None,
            "warnings": self.startup.warnings,
            "long_options": bool(self.settings.get("long_options")),
            "tags": self._all_tags(),
        })
        return out

    # ------------------------------------------------------------------ chain
    def _exp_groups(self, exps):
        today = timeutil.today_ct()
        mon = today - dt.timedelta(days=today.weekday())
        groups = {"This week": [], "Weeklies": [], "Monthlies": [], "LEAPS": []}
        for e in exps:
            d = dt.date.fromisoformat(e)
            if d < mon + dt.timedelta(days=7):
                g = "This week"
            elif (d - today).days > 270:
                g = "LEAPS"
            elif 15 <= d.day <= 21 and d.weekday() in (3, 4):
                g = "Monthlies"
            else:
                g = "Weeklies"
            groups[g].append({"exp": e, "label": timeutil.fmt_exp(e), "dte": (d - today).days})
        return [[k, v] for k, v in groups.items() if v]

    def _default_exp(self, exps):
        today = timeutil.today_ct()
        last = self.settings.get("chain_exp")
        if last in exps:
            return last
        for e in exps:
            d = dt.date.fromisoformat(e)
            if (d - today).days >= 7 and d.weekday() in (3, 4):
                return e
        return exps[0] if exps else None

    def api_chain(self, expiry=None, view=None):
        try:
            exps = self.quotes.expirations()
        except Exception as e:  # noqa: BLE001
            return {"error": f"No expiration list: {e}"}
        if expiry and expiry not in exps:
            exps = sorted(set(exps) | {expiry})
        e = expiry or self._default_exp(exps)
        if expiry:
            self.settings.update(chain_exp=expiry)
        if view:
            self.settings.update(chain_view=view)
        try:
            c = self.quotes.chain(e)
        except Exception as ex:  # noqa: BLE001
            return {"error": str(ex), "groups": self._exp_groups(exps), "expiry": e}
        u = self.quotes.underlying()
        held = [_pubpos(p) for p in self.led.positions() if p["expiry"] == e] if self.led.run() else []
        rows = {}
        for x in c["rows"]:
            rows.setdefault(x["strike"], {})[x["type"]] = {k: x.get(k) for k in ("bid", "ask", "mid", "delta", "iv")}
        strikes = [{"k": k, "call": v.get("call"), "put": v.get("put")} for k, v in sorted(rows.items())]
        return {"expiry": e, "label": timeutil.fmt_exp(e), "groups": self._exp_groups(exps), "strikes": strikes,
                "price": u["price"], "prev_close": u.get("prev_close"), "stale": c["stale"] or not self._market()["open"],
                "asof": timeutil.fmt_ct(c["asof"]), "market": self._market(), "held": held,
                "view": self.settings.get("chain_view") or "both", "error": c.get("error")}

    # ------------------------------------------------------------------ ticket
    def _quote_for(self, o, fresh):
        if o["action"] in ("buy_shares", "sell_shares"):
            return self.quotes.share_quote(fresh=fresh)
        if o.get("position_id") and o["action"] in ("buy_to_close", "sell_to_close"):
            p = self.led.position(int(o["position_id"]))
            o.update(type=p["type"], expiry=p["expiry"], strike=p["strike"])
        return self.quotes.quote(o["expiry"], o["type"], o["strike"], fresh=fresh)

    @staticmethod
    def default_fill(q, side):
        if side == "sell":
            return q["mid"]
        return round((q["mid"] + q["ask"]) / 2 + 1e-9, 2)

    def api_ticket(self, order, fresh=False):
        """Quote + rule check + effects + compare tables for the ticket side panel."""
        o = dict(order)
        try:
            q = self._quote_for(o, fresh)
        except Exception as e:  # noqa: BLE001
            return {"error": f"Couldn't get a quote: {e}"}
        S = self.price()
        side = "sell" if o["action"] in ("sell_to_open", "sell_to_close", "sell_shares") else "buy"
        if q and o.get("price") in (None, ""):
            o["price"] = self.default_fill(q, side)
        chk = self.led.check(o, q, S)
        out = {"order": {**o, "price": o.get("price")}, "quote": q, "check": {k: chk[k] for k in ("ok", "msg", "warn")},
               "effects": chk["effects"], "price": S, "market": self._market(), "default_fill": q and self.default_fill(q, side)}
        if q and q.get("asof"):
            out["quote_txt"] = timeutil.fmt_ct(q["asof"], with_et=False)
            out["too_old"] = self.quotes.is_too_old(q["asof"])
            if out["too_old"]:
                out["check"] = {"ok": False, "msg": "These quotes are more than 15 minutes old. Click Refresh quote.",
                                "warn": None}
        if o["action"].endswith("shares"):
            return out
        rate = self.rates.for_day(timeutil.today_ct()) or 0.0
        e = dt.date.fromisoformat(o["expiry"])
        dte = (e - timeutil.today_ct()).days
        out["dte"] = dte
        out["rate"] = rate
        k = float(o["strike"])
        qty = chk["order"]["qty"] or 0
        px = chk["order"]["price"] or 0
        if o["action"] == "sell_to_open":
            coll = k * 100 * qty if o["type"] == "put" else 0
            prem = px * 100 * qty
            intr = coll * rate / 100 * max(dte, 0) / 365
            base = coll if coll else (S or 0) * 100 * qty
            ret = (prem + intr) / base if base else 0
            out.update(interest_c=cents(intr), ret=ret, ann=ret * 365 / max(dte, 1))
        # strikes available (with a bid) for this expiry/type, and the expiration list
        try:
            c = self.quotes.chain(o["expiry"])
            out["strikes"] = sorted({x["strike"] for x in c["rows"] if x["type"] == o["type"] and (x["bid"] or 0) > 0}
                                    | {k})
        except Exception:  # noqa: BLE001
            out["strikes"] = [k]
        try:
            out["groups"] = self._exp_groups(self.quotes.expirations())
        except Exception:  # noqa: BLE001
            out["groups"] = []
        if o["action"] == "sell_to_open":
            out["compare"] = self._compare(o, k, rate, S, order.get("compare") or "dates")
        return out

    def _compare(self, o, k, rate, S, mode):
        rows = []
        today = timeutil.today_ct()
        if mode == "dates":
            exps = [e for e in self.quotes.expirations() if dt.date.fromisoformat(e).weekday() in (3, 4)][:6]
            for e in exps:
                try:
                    q = self.quotes.quote(e, o["type"], k, fresh=False)
                except Exception:  # noqa: BLE001
                    q = None
                d = (dt.date.fromisoformat(e) - today).days
                rows.append(self._cmp_row(q, o["type"], k, d, rate, S, exp=e, label=timeutil.fmt_exp(e)))
        else:
            try:
                c = self.quotes.chain(o["expiry"])
            except Exception:  # noqa: BLE001
                return {"mode": mode, "rows": []}
            ks = sorted({x["strike"] for x in c["rows"] if x["type"] == o["type"] and (x["bid"] or 0) > 0})
            if k in ks:
                i = ks.index(k)
                near = ks[max(0, i - 2): i + 3]
            else:
                near = sorted(ks, key=lambda s: abs(s - k))[:5]
            d = (dt.date.fromisoformat(o["expiry"]) - today).days
            for s in sorted(near):
                q = next((x for x in c["rows"] if x["type"] == o["type"] and x["strike"] == s), None)
                rows.append(self._cmp_row(q, o["type"], s, d, rate, S, strike=s, label=strike_txt(s)))
        valid = [r for r in rows if r.get("ann") is not None]
        best = max(valid, key=lambda r: r["ann"]) if valid else None
        for r in rows:
            r["best"] = r is best
        return {"mode": mode, "rows": rows}

    def _cmp_row(self, q, typ, k, d, rate, S, **kw):
        if not q or not (q.get("bid") or 0) > 0:
            return {**kw, "dte": d, "bid": None, "ask": None, "fill": None, "ret": None, "ann": None,
                    "delta": q and q.get("delta")}
        f = q["mid"]
        coll = k * 100 if typ == "put" else 0
        base = coll or (S or 0) * 100
        ret = (f * 100 + coll * rate / 100 * max(d, 0) / 365) / base if base else 0
        return {**kw, "dte": d, "bid": q["bid"], "ask": q["ask"], "fill": f, "ret": ret,
                "ann": ret * 365 / max(d, 1), "delta": q.get("delta")}

    def api_review(self, order, shown=None):
        """Confirm step: re-quote, re-check, describe the trade. `shown` = the bid/ask the ticket displayed."""
        o = dict(order)
        try:
            q = self._quote_for(o, fresh=True)
        except Exception as e:  # noqa: BLE001
            return {"error": f"Couldn't re-quote: {e}"}
        if q is None:
            return {"error": "No quote for this contract right now."}
        S = self.price()
        chk = self.led.check(o, q, S)
        moved = bool(shown) and (abs((shown.get("bid") or 0) - (q["bid"] or 0)) > 1e-9 or
                                 abs((shown.get("ask") or 0) - (q["ask"] or 0)) > 1e-9)
        too_old = self.quotes.is_too_old(q["asof"]) if q.get("asof") else False
        ok = chk["ok"] and not too_old
        msg = chk["msg"] if not too_old else "Quotes are more than 15 minutes old and couldn't be refreshed."
        no = chk["order"]
        if no["action"].endswith("shares"):
            title = f"{'BUY' if no['action'] == 'buy_shares' else 'SELL'} {no['qty']} {SYMBOL} SHARES"
        else:
            words = {"sell_to_open": "SELL TO OPEN", "buy_to_open": "BUY TO OPEN", "buy_to_close": "BUY TO CLOSE",
                     "sell_to_close": "SELL TO CLOSE"}[no["action"]]
            e = dt.date.fromisoformat(o["expiry"])
            title = f"{words} {no['qty']} × {SYMBOL} {e.strftime('%a %b %d %Y')} {strike_txt(float(o['strike']))} " \
                    f"{'Put' if o['type'] == 'put' else 'Call'}"
        pos = self.led.position(no["position_id"]) if no.get("position_id") else None
        return {"ok": ok, "msg": msg, "warn": chk["warn"], "effects": chk["effects"], "quote": q, "moved": moved,
                "stale": bool(q.get("stale")) or not self._market()["open"], "title": title, "order": no,
                "position": _pubpos(pos) if pos else None, "quote_txt": timeutil.fmt_ct(q["asof"], with_et=False)
                if q.get("asof") else ""}

    def api_place(self, order):
        o = dict(order)
        try:
            q = self._quote_for(o, fresh=False)
            res = self.led.place(o, q, self.price())
        except TradeError as e:
            return {"error": str(e)}
        except Exception as e:  # noqa: BLE001
            log.exception("place failed")
            return {"error": f"The trade wasn't placed: {e}"}
        return {"ok": True, **res}

    # ------------------------------------------------------------------ position panel
    def api_position(self, id):
        p = self.led.position(int(id))
        if not p:
            return {"error": "Position not found."}
        if p["status"] != "open":
            return self._position_story(p)
        S = self.price()
        q = None
        try:
            q = self.quotes.quote(p["expiry"], p["type"], p["strike"], fresh=False)
        except Exception:  # noqa: BLE001
            pass
        rate = self.rates.for_day(timeutil.today_ct()) or 0
        dte = (dt.date.fromisoformat(p["expiry"]) - timeutil.today_ct()).days
        coll = p["collateral_c"]
        sign = 1 if p["side"] == "short" else -1
        pnl = cents((p["open_price"] - q["mid"]) * 100 * p["open_qty"]) * sign if q else None
        prem = cents(p["open_price"]) * 100 * p["open_qty"]
        return {**_pubpos(p), "quote": q, "pnl_c": pnl, "pnl_pct": pnl / prem if (pnl is not None and prem) else None,
                "premium_c": prem, "interest_c": cents(coll / 100 * rate / 100 * max(dte, 0) / 365), "dte": dte,
                "price": S, "dist": (S - p["strike"]) / p["strike"] if S else None,
                "otm": (S > p["strike"]) if p["type"] == "put" else (S < p["strike"])}

    def _position_story(self, p):
        """A finished position: what happened, start to end, with every History event for it."""
        evs = []
        close_notes = []
        bought_back = []
        for e in self.db.q("SELECT * FROM events WHERE position_id=? ORDER BY ts, id", (p["id"],)):
            data = json.loads(e["data"] or "{}")
            if data.get("close_note"):
                close_notes.append(data["close_note"])
            if data.get("action") in ("buy_to_close", "sell_to_close"):
                bought_back.append((data.get("qty"), data.get("price")))
            f = _fmt_ts(e["ts"])
            evs.append({"id": e["id"], "when": timeutil.fmt_date(f["day"]), "kind": e["kind"], "title": e["title"],
                        "detail": e["detail"]})
        opened = timeutil.parse(p["opened_at"]).astimezone(timeutil.CT).date()
        ended = timeutil.parse(p["closed_at"]).astimezone(timeutil.CT).date() if p["closed_at"] else None
        outcome = {"closed": "Closed early" if p["side"] == "short" else "Sold before expiration", "expired":
                   "Expired worthless", "assigned": "Assigned", "called": "Called away",
                   "exercised": "Exercised"}.get(p["status"], p["status"].title())
        settle = next((e for e in self.db.q("SELECT data FROM events WHERE position_id=? AND kind IN "
                                            "('Expired','Assigned','Called away','Exercised')", (p["id"],))), None)
        close_px = json.loads(settle[0]).get("close") if settle else None
        return {**_pubpos(p), "finished": True, "outcome": outcome, "events": evs, "close_notes": close_notes,
                "bought_back": bought_back, "premium_c": cents(p["open_price"]) * 100 * p["qty"],
                "result_c": p["realized_c"], "interest_c": cents(self.led.interest_on_collateral(p)),
                "opened_day": timeutil.fmt_date(opened), "ended_day": ended and timeutil.fmt_date(ended),
                "days_held": (ended - opened).days if ended else None, "settle_close": close_px}

    # ------------------------------------------------------------------ history
    def api_history(self, filter="All", tag=None, day=None):
        r = self.led.run()
        rid = r["id"] if r else -1
        rows = self.db.q("SELECT * FROM events WHERE (run_id=? OR run_id IS NULL) ORDER BY ts DESC, id DESC", (rid,))
        cats = {"Trades": ("Trade", "Shares", "Summary"), "Expirations & Assignments":
                ("Expired", "Assigned", "Called away", "Exercised"), "Interest": ("Interest", "Dividend")}
        out = []
        for e in rows:
            tags = [t[0] for t in self.db.q("SELECT tag FROM event_tags WHERE event_id=? ORDER BY tag", (e["id"],))]
            if filter == "Errors" and not (e["is_error"] or e["is_warning"]):
                continue
            if filter in cats and e["kind"] not in cats[filter]:
                continue
            if tag and tag not in tags:
                continue
            f = _fmt_ts(e["ts"])
            if day and f["day"] != day:
                continue
            out.append({"id": e["id"], **f, "kind": e["kind"], "title": e["title"], "detail": e["detail"], "tags": tags,
                        "err": bool(e["is_error"]), "warn": bool(e["is_warning"]), "data": json.loads(e["data"] or "{}"),
                        "lot_id": e["lot_id"], "position_id": e["position_id"],
                        "share_event": e["kind"] in ("Assigned", "Called away", "Shares", "Exercised") and e["lot_id"]})
        total = self.db.val("SELECT COUNT(*) FROM events WHERE run_id=? OR run_id IS NULL", (rid,), 0)
        return {"events": out, "total": total, "tags": self._all_tags()}

    # ------------------------------------------------------------------ calendar
    TRADE_KINDS = ("Trade", "Shares")

    def _closes(self, start, end):
        """TQQQ daily closes {iso: close} for [start, end], fetching any missing past days from the provider once."""
        rows = {r[0]: r[1] for r in self.db.q("SELECT day, close FROM prices WHERE symbol=? AND day>=? AND day<=?",
                                              (SYMBOL, start.isoformat(), end.isoformat()))}
        want = [d for d in _days(start, end) if marketcal.is_trading_day(d) and d.isoformat() not in rows]
        if want:
            try:
                got = self.provider.daily_closes(min(want), max(want))
                with self.db.tx():
                    for d, c in got.items():
                        self.db.x("INSERT OR REPLACE INTO prices(symbol,day,close) VALUES(?,?,?)", (SYMBOL, d, c))
                rows.update(got)
            except Exception as e:  # noqa: BLE001
                log.warning("calendar closes: %s", e)
        return rows

    def api_calendar(self, month=None):
        today = timeutil.today_ct()
        y, m = (map(int, month.split("-")) if month else (today.year, today.month))
        first = dt.date(y, m, 1)
        last = dt.date(y + (m == 12), m % 12 + 1, 1) - dt.timedelta(days=1)
        grid_start = first - dt.timedelta(days=first.weekday())
        grid_end = last + dt.timedelta(days=4 - last.weekday()) if last.weekday() < 5 else last
        now = timeutil.now()
        closed_through = marketcal.last_close_dt(now).astimezone(timeutil.ET).date()
        prev_day = marketcal.prev_trading_day(grid_start)
        closes = self._closes(prev_day, min(grid_end, closed_through)) if prev_day <= closed_through else {}
        r = self.led.run()
        rid = r["id"] if r else -1
        days = {}
        for d in _days(grid_start, grid_end):
            if d.weekday() >= 5:
                continue
            iso = d.isoformat()
            cell = {"day": iso, "n": d.day, "in_month": d.month == m, "today": d == today, "items": []}
            hol = marketcal.holiday_name(d)
            if hol:
                cell["holiday"] = hol
            elif d in marketcal.early_closes(d.year):
                cell["early"] = f"Early close 12:00 PM CT · {marketcal.early_closes(d.year)[d]}"
            if d <= closed_through and iso in closes:
                pd = marketcal.prev_trading_day(d)
                pc = closes.get(pd.isoformat())
                cell["close"] = closes[iso]
                cell["chg"] = (closes[iso] / pc - 1) if pc else None
            days[iso] = cell
        # expiries
        if r:
            for p in self.db.q("SELECT id FROM positions WHERE run_id=? AND expiry>=? AND expiry<=? ORDER BY strike",
                               (rid, grid_start.isoformat(), grid_end.isoformat())):
                pos = self.led.position(p[0])
                c = days.get(pos["expiry"])
                if not c:
                    continue
                short = f"{strike_txt(pos['strike'])} {'Put' if pos['type'] == 'put' else 'Call'}"
                if pos["status"] == "open":
                    c["items"].append({"kind": "expiry", "active": True, "text": f"{short} ×{pos['open_qty']}",
                                       "tip": f"{pos['label']} · {pos['open_qty']} open · double-click: open in the Chain",
                                       "go": f"chainpos:{pos['id']}", "side": pos["side"]})
                elif pos["status"] in ("expired", "assigned", "called", "exercised"):
                    ev = self.db.one("SELECT id FROM events WHERE position_id=? AND kind IN "
                                     "('Expired','Assigned','Called away','Exercised') ORDER BY id LIMIT 1", (pos["id"],))
                    word = {"expired": "expired", "assigned": "assigned", "called": "called away",
                            "exercised": "exercised"}[pos["status"]]
                    c["items"].append({"kind": "expiry", "active": False, "text": f"{short} ×{pos['qty']} · {word}",
                                       "tip": f"{pos['label']} · {word} · double-click: open in History",
                                       "go": f"history:event:{ev[0]}" if ev else "history"})
        # interest pay dates
        for pdate in marketcal.pay_dates_between(grid_start - dt.timedelta(days=1), grid_end):
            c = days.get(pdate.isoformat())
            if not c:
                continue
            ev = self.db.one("SELECT id, title FROM events WHERE run_id=? AND kind='Interest' AND substr(ts,1,10)>=? "
                             "AND substr(ts,1,10)<=? ORDER BY id DESC LIMIT 1",
                             (rid, (pdate - dt.timedelta(days=1)).isoformat(), (pdate + dt.timedelta(days=1)).isoformat()))
            amt = self.db.val("SELECT SUM(amount_c) FROM cash WHERE run_id=? AND reason='interest' AND day=?",
                              (rid, pdate.isoformat()), 0) if r else 0
            if amt:
                c["items"].append({"kind": "interest", "active": True, "text": f"Interest {money(amt, True)}",
                                   "tip": "Interest posted · double-click: open in History",
                                   "go": f"history:event:{ev['id']}" if ev else "history"})
            elif r and pdate >= today:
                c["items"].append({"kind": "interest", "active": True, "text": "Interest pay day",
                                   "tip": f"Accrued interest is paid today ({money(cents(self.led.accrued()))} accrued so far)"})
        # market events (built-in schedule) and TQQQ ex-dividend dates (Yahoo)
        for ev in events.events_between(grid_start, grid_end):
            c = days.get(ev["day"].isoformat())
            if c:
                c.setdefault("events", []).append({"kind": ev["kind"], "text": ev["short"], "tip": ev["name"]})
        for exd, amt in self._ex_dividends():
            c = days.get(exd.isoformat())
            if c:
                c.setdefault("events", []).append({
                    "kind": "exdiv", "text": f"Ex-div ${amt:.4f}".rstrip("0") if amt else "Ex-dividend",
                    "tip": f"{SYMBOL} ex-dividend date" + (f" · ${amt:.4f} per share" if amt else "")
                    + " · in-the-money covered calls are more likely to be assigned early the day before"})
        # trade days
        if r:
            for row in self.db.q("SELECT ts, kind FROM events WHERE run_id=? AND kind IN ('Trade','Shares')", (rid,)):
                iso = _fmt_ts(row["ts"])["day"]
                c = days.get(iso)
                if c:
                    c["trades"] = c.get("trades", 0) + 1
        weeks = []
        wk = []
        for iso in sorted(days):
            wk.append(days[iso])
            if len(wk) == 5:
                weeks.append(wk)
                wk = []
        start_m = dt.date.fromisoformat(r["start_day"]).strftime("%Y-%m") if r else None
        beyond = grid_end > events.COVERED_THROUGH
        return {"month": f"{y:04d}-{m:02d}", "label": first.strftime("%B %Y"), "weeks": weeks,
                "prev": (first - dt.timedelta(days=1)).strftime("%Y-%m"), "next": (last + dt.timedelta(days=1)).strftime("%Y-%m"),
                "this_month": today.strftime("%Y-%m"), "run_start_month": start_m,
                "events_note": f"Fed, CPI and jobs dates are built in through {events.COVERED_THROUGH.strftime('%B %Y')}; "
                               "later ones arrive with an app update." if beyond else None}

    def _ex_dividends(self):
        """[(date, amount)] past ex-dates from Yahoo plus the next announced one; fetched once per session."""
        if getattr(self, "_exdivs", None) is None:
            out = []
            try:
                out = [(d, a) for d, a in self.provider.dividends()]
                nxt = self.provider.next_ex_dividend()
                if nxt and all(d != nxt for d, _ in out):
                    out.append((nxt, None))
            except Exception as e:  # noqa: BLE001
                log.warning("ex-dividend dates: %s", e)
            self._exdivs = out
        return self._exdivs

    def api_history_csv(self):
        r = self.led.run()
        if not r:
            return {"error": "No run yet."}
        name = f"ghost-trader-history_{timeutil.today_ct().isoformat()}.csv"
        return self._save_text(name, csvout.history_csv(self.led, r["id"]))

    def api_lot(self, id):
        s = perf.lot_story(self.led, int(id), self.price())
        if not s:
            return {"error": "Lot not found."}
        for t in s["timeline"]:
            t["when"] = timeutil.fmt_date(timeutil.parse(t["ts"]).astimezone(timeutil.CT).date())
        s["lot"]["acquired"] = timeutil.fmt_date(s["lot"]["acquired_day"])
        return s

    # ------------------------------------------------------------------ performance
    def api_performance(self):
        p = perf.build(self.led, self.rates, self.price())
        if not p:
            return {"empty": True}
        p["labels"] = [timeutil.fmt_date(d) for d in p["days"]]
        for m in p["markers"]:
            m["when"] = timeutil.fmt_date(m["day"])
            m["story"] = perf.lot_story(self.led, m["lot_id"], self.price())
        for m in p["monthly"]:
            y, mo = map(int, m["month"].split("-"))
            m["label"] = dt.date(y, mo, 1).strftime("%b %Y")
        p["next_pay"] = timeutil.fmt_exp(marketcal.next_pay_date(timeutil.today_ct() - dt.timedelta(days=1)))
        return p

    # ------------------------------------------------------------------ settings & tags
    def api_settings(self):
        rate, day, src = self.rates.latest()
        r = self.led.run()
        past = [{"id": x["id"], "start": timeutil.fmt_date(x["start_day"]), "end": timeutil.fmt_date(x["end_day"]),
                 "final_c": x["final_value_c"], "start_c": x["start_cash_c"], "name": x["csv_name"]}
                for x in self.db.q("SELECT * FROM runs WHERE closed_at IS NOT NULL ORDER BY id DESC")]
        backups = sorted((config.data_dir() / "backups").glob("ledger-*.db"))
        last_b = None
        if backups:
            last_b = timeutil.fmt_ct(dt.datetime.fromtimestamp(backups[-1].stat().st_mtime, dt.timezone.utc), with_date=True)
        return {"settings": self.settings.all(), "rate": {"rate": rate, "day": day and timeutil.fmt_date(day), "source": src},
                "run": r and {"start": dt.date.fromisoformat(r["start_day"]).strftime("%b %-d, %Y"),
                              "cash_c": r["start_cash_c"]},
                "past": past, "data_dir": str(config.data_dir()), "last_backup": last_b, "version": __version__,
                "tags": self._tag_counts(), "provider": self.provider.name, "demo": self.demo,
                "nudges": notify.status(), "install": config.install_kind()}

    def api_test_notify(self):
        ok, msg = notify.send("Ghost Trader", "Test notification: expiration-day reminders will look like this.")
        return {"ok": ok, "msg": msg}

    def api_settings_set(self, **kw):
        old = self.settings.all()
        if "manual_rate" in kw and kw["manual_rate"] not in (None, ""):
            kw["manual_rate"] = float(str(kw["manual_rate"]).replace("%", ""))
        elif "manual_rate" in kw:
            kw["manual_rate"] = None
        if "haircut" in kw:
            kw["haircut"] = float(str(kw["haircut"] or 0).replace("%", ""))
        if "long_options" in kw:
            kw["long_options"] = bool(kw["long_options"])
        self.settings.update(**kw)
        changed = [k for k in kw if old.get(k) != self.settings.get(k) and k not in ("chain_exp", "chain_view", "theme")]
        if changed and self.led.run():
            nice = {"av_key": "Alpha Vantage key", "manual_rate": "manual rate", "haircut": "haircut",
                    "long_options": "buying options to open"}
            parts = []
            for k in changed:
                v = self.settings.get(k)
                if k == "av_key":
                    parts.append("Alpha Vantage key updated")
                elif k == "long_options":
                    parts.append(f"buying options to open {'on' if v else 'off'}")
                else:
                    parts.append(f"{nice.get(k, k)} {v if v is not None else 'cleared'}{'%' if v is not None else ''}")
            self.led.event("Settings", "Settings changed", " · ".join(parts))
        return {"ok": True, "settings": self.settings.all()}

    def _all_tags(self):
        return sorted({t[0] for t in self.db.q("SELECT tag FROM position_tags UNION SELECT tag FROM event_tags")})

    def _tag_counts(self):
        return [{"tag": t[0], "n": t[1]} for t in self.db.q(
            "SELECT tag, COUNT(*) FROM event_tags GROUP BY tag ORDER BY tag")]

    def api_tag_edit(self, op, tag, to=None):
        tag = "#" + tag.lstrip("#")
        with self.db.tx():
            if op == "delete":
                self.db.x("DELETE FROM event_tags WHERE tag=?", (tag,))
                self.db.x("DELETE FROM position_tags WHERE tag=?", (tag,))
                msg = f"Deleted {tag}"
            else:
                to = "#" + str(to or "").strip().lstrip("#").replace(" ", "-").lower()
                if len(to) < 2:
                    return {"error": "Enter a tag name."}
                for tbl, col in (("event_tags", "event_id"), ("position_tags", "position_id")):
                    self.db.x(f"INSERT OR IGNORE INTO {tbl}({col},tag) SELECT {col}, ? FROM {tbl} WHERE tag=?", (to, tag))
                    self.db.x(f"DELETE FROM {tbl} WHERE tag=?", (tag,))
                msg = f"{'Renamed' if op == 'rename' else 'Merged'} {tag} → {to}"
            if self.led.run():
                self.led.event("Settings", "Tags changed", msg)
        return {"ok": True, "tags": self._tag_counts()}

    # ------------------------------------------------------------------ runs
    def api_start_run(self, cash):
        try:
            v = float(str(cash).replace("$", "").replace(",", "").strip())
            rid = self.led.start_run(v)
        except (TradeError, ValueError) as e:
            return {"error": str(e) if isinstance(e, TradeError) else "Enter an amount like 100000"}
        S = self.price()
        if S:
            self.led.snapshot(timeutil.today_ct(), S, S)
        return {"ok": True, "run_id": rid}

    def _final(self):
        S = self.price() or 0
        b = self.led.breakdown(S)
        return S, b

    def api_close_run_preview(self):
        r = self.led.run()
        if not r:
            return {"error": "No open run."}
        S, b = self._final()
        start = dt.date.fromisoformat(r["start_day"])
        today = timeutil.today_ct()
        return {**b, "final": f"{b['account_value_c'] / 100:.2f}", "start": start.strftime("%b %-d, %Y"),
                "end": today.strftime("%b %-d, %Y"), "days": (today - start).days, "start_cash_c": r["start_cash_c"],
                "open_puts": len([p for p in self.led.positions() if p["type"] == "put"]),
                "open_calls": len([p for p in self.led.positions() if p["type"] == "call"]),
                "name": f"ghost-trader-run_{start.isoformat()}_to_{today.isoformat()}.csv"}

    def api_close_run(self, typed):
        pre = self.api_close_run_preview()
        if "error" in pre:
            return pre
        try:
            v = float(str(typed).replace("$", "").replace(",", "").strip())
        except ValueError:
            return {"error": "Type the final value exactly, like 101234.56"}
        if cents(v) != pre["account_value_c"]:
            return {"error": f"That doesn't match the final value ({money(pre['account_value_c'])})."}
        path = self._ask_save(pre["name"])
        if not path:
            return {"cancelled": True}
        try:
            return self._close_run(pre, path)
        except OSError as e:
            return {"error": f"Couldn't save the CSV there ({e.strerror}). The run stays open; try another folder."}

    def _close_run(self, pre, path):
        r = self.led.run()
        S = self.price() or 0
        now = timeutil.now()
        with self.db.tx():
            self.led.pay_interest(timeutil.today_ct(), now, force=True)
            av = self.led.snapshot(timeutil.today_ct(), S, S, marks=self.marks(), ts=now)
            p = perf.build(self.led, self.rates, S) or {"summary": {}}
            sm = p["summary"]
            counts = dict(self.db.q("SELECT kind, COUNT(*) FROM events WHERE run_id=? GROUP BY kind", (r["id"],)))
            start = dt.date.fromisoformat(r["start_day"])
            summary = [
                ("Start date", start.isoformat()), ("End date", timeutil.today_ct().isoformat()),
                ("Starting cash", f"{r['start_cash_c'] / 100:.2f}"), ("Final value", f"{av / 100:.2f}"),
                ("Total return", f"{(av / r['start_cash_c'] - 1) * 100:.2f}%"),
                ("Annualized return", f"{sm.get('ann', 0) * 100:.2f}%"),
                (f"{SYMBOL} buy-and-hold, same dates", f"{(sm.get('bh_ret') or 0) * 100:.2f}%"),
                ("T-bills (cash only), same dates", f"{(sm.get('tb_ret') or 0) * 100:.2f}%"),
                ("Premium collected", f"{self.led.premium_collected_c() / 100:.2f}"),
                ("Interest earned", f"{self.led.interest_earned_c() / 100:.2f}"),
                ("Dividends", f"{self.led.dividends_c() / 100:.2f}"),
                ("Trades", counts.get("Trade", 0) + counts.get("Shares", 0)),
                ("Assignments", counts.get("Assigned", 0)), ("Called away", counts.get("Called away", 0)),
                ("Valuation", "account value = cash + collateral + accrued interest + shares at market; "
                              "open option prices not counted"),
            ]
            self.led.event("Run", "Run closed", f"Final value {money(av)} · {(av / r['start_cash_c'] - 1) * 100:.2f}% "
                           f"over {(timeutil.today_ct() - start).days} days.", ts=now)
            text = csvout.run_csv(self.led, r["id"], summary)
            self.db.x("UPDATE runs SET closed_at=?, end_day=?, final_value_c=?, csv_name=?, csv_text=? WHERE id=?",
                      (timeutil.iso(now), timeutil.today_ct().isoformat(), av, pre["name"], text, r["id"]))
            # Write the files before the transaction commits: if saving fails, the run stays open.
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_text(text)
            (config.data_dir() / "runs" / pre["name"]).write_text(text)
        return {"ok": True, "path": str(path), "final_c": av}

    def api_export_run(self, id):
        r = self.db.one("SELECT * FROM runs WHERE id=?", (int(id),))
        if not r or not r["csv_text"]:
            return {"error": "No CSV saved for that run."}
        return self._save_text(r["csv_name"], r["csv_text"])

    # ------------------------------------------------------------------ files & folders
    def _ask_save(self, name):
        if self.window is not None:
            return self.window.save_dialog(name)
        return str(Path.home() / "Downloads" / name)

    def _save_text(self, name, text):
        path = self._ask_save(name)
        if not path:
            return {"cancelled": True}
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(text)
        return {"ok": True, "path": str(path)}

    def api_open_folder(self):
        try:
            subprocess.Popen(["xdg-open", str(config.data_dir())], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
            return {"ok": True}
        except OSError as e:
            return {"error": f"Couldn't open the folder: {e}"}

    def api_refresh_quote(self, expiry, type, strike):
        try:
            self.quotes.chain(expiry, fresh=True)
            self.quotes.underlying(fresh=True)
            return {"ok": True}
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}


def _days(a, b):
    d = a
    while d <= b:
        yield d
        d += dt.timedelta(days=1)


def _pubpos(p):
    if not p:
        return None
    return {k: p[k] for k in ("id", "type", "side", "expiry", "strike", "qty", "open_qty", "open_price", "status",
                              "collateral_c", "note", "lot_id", "label", "tags", "realized_c")} | {
        "opened": timeutil.fmt_date(timeutil.parse(p["opened_at"]).astimezone(timeutil.CT).date()),
        "exp_label": timeutil.fmt_exp(p["expiry"]),
        "kind": ("Short put" if p["type"] == "put" else "Covered call") if p["side"] == "short"
        else ("Long put" if p["type"] == "put" else "Long call")}


def method_names(app):
    return {n[4:] for n in dir(app) if n.startswith("api_")}

