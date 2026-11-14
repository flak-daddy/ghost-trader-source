"""The paper account: cash journal, positions, share lots, trade rules, expirations, interest, snapshots.

Money is kept in integer cents. Cash lives in two buckets: `available` (spendable) and `collateral`
(securing short puts). Every movement is a row in `cash`, so balances on any past day can be rebuilt.

Account value = available + collateral + shares x current price (v1.9.0: interest counts once it's paid on the 15th;
accrued, unpaid interest is shown separately). Open options' buy-back prices are deliberately excluded.
"""
import datetime as dt
import json
from decimal import ROUND_HALF_UP, Decimal

from . import SYMBOL, marketcal, timeutil
from .timeutil import fmt_date, fmt_exp

SIZING_WARN = 0.80
NEAR_MONEY = 0.03


class TradeError(Exception):
    """A rule refused the trade; the message is shown to the user as-is."""


def cents(x):
    return int(Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) * 100)


def money(c, sign=False):
    v = c / 100
    s = f"${abs(v):,.2f}"
    if v < 0:
        return "−" + s
    return ("+" + s) if sign and v > 0 else s


def strike_txt(k):
    return f"${k:g}" if k == int(k) else f"${k:.2f}".rstrip("0")


def label(type_, expiry, strike, symbol=SYMBOL):
    return f"{symbol} {fmt_exp(expiry)} {strike_txt(strike)} {'Put' if type_ == 'put' else 'Call'}"


def plural(n, word):
    return f"{n} {word}{'' if n == 1 else 's'}"


ACTIONS = ("sell_to_open", "buy_to_close", "buy_to_open", "sell_to_close", "buy_shares", "sell_shares")
ACTION_WORDS = {
    "sell_to_open": "Sell to open", "buy_to_close": "Buy to close", "buy_to_open": "Buy to open",
    "sell_to_close": "Sell to close", "buy_shares": "Buy", "sell_shares": "Sell",
}


class Ledger:
    def __init__(self, db, settings):
        self.db = db
        self.settings = settings

    # ------------------------------------------------------------------ runs
    def run(self):
        return self.db.one("SELECT * FROM runs WHERE closed_at IS NULL ORDER BY id DESC LIMIT 1")

    def run_id(self):
        r = self.run()
        return r["id"] if r else None

    def start_run(self, start_cash, ts=None):
        if self.run():
            raise TradeError("A run is already open. Close it first (Settings → Close run).")
        sc = cents(start_cash)
        if sc <= 0:
            raise TradeError("Starting cash must be more than $0.")
        ts = ts or timeutil.now()
        day = ts.astimezone(timeutil.CT).date().isoformat()
        with self.db.tx():
            rid = self.db.x("INSERT INTO runs(started_at,start_day,start_cash_c) VALUES(?,?,?)",
                            (timeutil.iso(ts), day, sc))
            ev = self.event("Run", "New run started", f"Starting cash {money(sc)}.", ts=ts, run_id=rid)
            self.move("available", sc, "starting cash", ts, ev, run_id=rid)
        return rid

    # ------------------------------------------------------------------ events & cash
    def event(self, kind, title, detail="", data=None, tags=(), ts=None, error=False, warning=False,
              position_id=None, lot_id=None, run_id=None):
        rid = run_id if run_id is not None else self.run_id()
        eid = self.db.x(
            "INSERT INTO events(run_id,ts,kind,title,detail,data,is_error,is_warning,position_id,lot_id)"
            " VALUES(?,?,?,?,?,?,?,?,?,?)",
            (rid, timeutil.iso(ts), kind, title, detail, json.dumps(data or {}), int(error), int(warning),
             position_id, lot_id))
        for t in tags or ():
            self.db.x("INSERT OR IGNORE INTO event_tags(event_id,tag) VALUES(?,?)", (eid, t))
        return eid

    def move(self, bucket, amount_c, reason, ts, event_id=None, run_id=None):
        if amount_c == 0:
            return
        rid = run_id if run_id is not None else self.run_id()
        day = ts.astimezone(timeutil.CT).date().isoformat()
        self.db.x("INSERT INTO cash(run_id,ts,day,bucket,amount_c,reason,event_id) VALUES(?,?,?,?,?,?,?)",
                  (rid, timeutil.iso(ts), day, bucket, amount_c, reason, event_id))

    def balances(self, day=None, run_id=None):
        rid = run_id or self.run_id()
        if rid is None:
            return 0, 0
        sql = "SELECT bucket, SUM(amount_c) FROM cash WHERE run_id=?"
        args = [rid]
        if day:
            sql += " AND day<=?"
            args.append(day if isinstance(day, str) else day.isoformat())
        rows = dict(self.db.q(sql + " GROUP BY bucket", args))
        return rows.get("available", 0) or 0, rows.get("collateral", 0) or 0

    def available(self):
        return self.balances()[0]

    # ------------------------------------------------------------------ shares
    def lots(self, open_only=True):
        rid = self.run_id()
        sql = "SELECT * FROM lots WHERE run_id=?" + (" AND open_qty>0" if open_only else "") + " ORDER BY id"
        return self.db.q(sql, (rid,))

    def shares(self):
        return self.db.val("SELECT SUM(open_qty) FROM lots WHERE run_id=?", (self.run_id(),), 0)

    def shares_on(self, day, run_id=None):
        rid = run_id or self.run_id()
        d = day if isinstance(day, str) else day.isoformat()
        r = self.db.one(
            "SELECT SUM(CASE direction WHEN 'in' THEN qty ELSE -qty END) FROM lot_moves WHERE run_id=? AND day<=?",
            (rid, d))
        return r[0] or 0

    def locked_shares(self):
        return 100 * self.db.val(
            "SELECT SUM(open_qty) FROM positions WHERE run_id=? AND status='open' AND type='call' AND side='short'",
            (self.run_id(),), 0)

    def free_shares(self):
        return self.shares() - self.locked_shares()

    def avg_cost(self):
        rows = self.lots()
        n = sum(r["open_qty"] for r in rows)
        return sum(r["open_qty"] * r["cost"] for r in rows) / n if n else 0.0

    def _add_lot(self, qty, price, ts, source, how, event_id, position_id=None):
        day = ts.astimezone(timeutil.CT).date().isoformat()
        lid = self.db.x(
            "INSERT INTO lots(run_id,symbol,qty,open_qty,cost,acquired_at,acquired_day,source,source_position_id)"
            " VALUES(?,?,?,?,?,?,?,?,?)",
            (self.run_id(), SYMBOL, qty, qty, price, timeutil.iso(ts), day, source, position_id))
        self.db.x("INSERT INTO lot_moves(run_id,lot_id,ts,day,direction,qty,price,how,event_id,position_id)"
                  " VALUES(?,?,?,?,'in',?,?,?,?,?)",
                  (self.run_id(), lid, timeutil.iso(ts), day, qty, price, how, event_id, position_id))
        return lid

    def _remove_shares(self, qty, price, ts, how, event_id, prefer_lot=None, position_id=None):
        """Take `qty` shares out of lots (preferred lot first, then oldest first). Returns [(lot_id, n, cost)]."""
        day = ts.astimezone(timeutil.CT).date().isoformat()
        lots = list(self.lots())
        if prefer_lot:
            lots.sort(key=lambda r: (r["id"] != prefer_lot, r["id"]))
        taken, left = [], qty
        for lot in lots:
            if left <= 0:
                break
            n = min(left, lot["open_qty"])
            self.db.x("UPDATE lots SET open_qty=open_qty-?, closed_at=CASE WHEN open_qty-?=0 THEN ? END WHERE id=?",
                      (n, n, timeutil.iso(ts), lot["id"]))
            self.db.x("INSERT INTO lot_moves(run_id,lot_id,ts,day,direction,qty,price,how,event_id,position_id)"
                      " VALUES(?,?,?,?,'out',?,?,?,?,?)",
                      (self.run_id(), lot["id"], timeutil.iso(ts), day, n, price, how, event_id, position_id))
            taken.append((lot["id"], n, lot["cost"]))
            left -= n
        if left > 0:
            raise TradeError(f"Not enough shares: needed {qty}, found {qty - left}.")
        return taken

    # ------------------------------------------------------------------ positions
    def positions(self, open_only=True):
        rid = self.run_id()
        sql = "SELECT * FROM positions WHERE run_id=?" + (" AND status='open'" if open_only else "")
        return [self._pos(r) for r in self.db.q(sql + " ORDER BY expiry, strike", (rid,))]

    def position(self, pid):
        r = self.db.one("SELECT * FROM positions WHERE id=?", (pid,))
        return self._pos(r) if r else None

    def _pos(self, r):
        d = dict(r)
        d["tags"] = [t[0] for t in self.db.q("SELECT tag FROM position_tags WHERE position_id=? ORDER BY tag", (r["id"],))]
        d["label"] = label(r["type"], r["expiry"], r["strike"], r["symbol"])
        return d

    def _set_tags(self, pid, tags):
        for t in tags:
            self.db.x("INSERT OR IGNORE INTO position_tags(position_id,tag) VALUES(?,?)", (pid, t))

    # ------------------------------------------------------------------ valuation
    def accrued(self, run_id=None, as_of=None):
        rid = run_id or self.run_id()
        if as_of is None:
            return self.db.val("SELECT SUM(amount) FROM accruals WHERE run_id=? AND paid_day IS NULL", (rid,), 0.0)
        d = as_of.isoformat() if not isinstance(as_of, str) else as_of
        return self.db.val(
            "SELECT SUM(amount) FROM accruals WHERE run_id=? AND day<=? AND (paid_day IS NULL OR paid_day>?)",
            (rid, d, d), 0.0)

    def account_value_c(self, share_price):
        a, c = self.balances()
        return a + c + cents(self.shares() * (share_price or 0))

    def breakdown(self, share_price):
        a, c = self.balances()
        acc = self.accrued()
        sh = self.shares()
        return {
            "available_c": a, "collateral_c": c, "accrued": round(acc, 6), "accrued_c": cents(acc),
            "shares": sh, "share_price": share_price, "shares_value_c": cents(sh * (share_price or 0)),
            "account_value_c": a + c + cents(sh * (share_price or 0)),
        }

    # ------------------------------------------------------------------ order checking
    def check(self, order, quote, share_price, ts=None):
        """Validate an order against the rules and the current quote. Returns a dict with ok/msg/effects.
        Never raises for rule failures; `place()` raises TradeError with the same message."""
        o = _norm(order)
        res = {"ok": False, "msg": "", "warn": None, "effects": {}, "order": o}
        if not self.run():
            res["msg"] = "Start a run first (enter your starting cash)."
            return res
        act = o["action"]
        if act not in ACTIONS:
            res["msg"] = "Unknown action."
            return res
        qty = o["qty"]
        if not isinstance(qty, int) or qty <= 0:
            res["msg"] = "Enter how many shares." if act.endswith("shares") else "Enter how many contracts."
            return res
        px = o["price"]
        bid, ask = (quote or {}).get("bid"), (quote or {}).get("ask")
        if quote is None or ask is None or (not ask and not bid):
            res["msg"] = "No usable quote for this contract right now, so it can't be traded until one is available."
            return res
        bid = bid or 0.0
        if px is None:
            res["msg"] = "Enter a fill price."
            return res
        pc, bc, ac = cents(px), cents(bid), cents(ask)
        if pc > ac:
            res["msg"] = f"{px:.2f} is above the ask. Enter a price from {bid:.2f} to {ask:.2f}."
            return res
        if pc < bc:
            res["msg"] = f"{px:.2f} is below the bid. Enter a price from {bid:.2f} to {ask:.2f}."
            return res
        if pc <= 0 and act in ("sell_to_open", "sell_shares", "sell_to_close", "buy_shares"):
            res["msg"] = "The fill price has to be more than 0.00."
            return res
        avail, coll = self.balances()
        mult = 1 if act.endswith("shares") else 100
        gross = pc * qty * mult
        eff = {"gross_c": gross, "available_before_c": avail}
        msg = ""
        if act == "sell_to_open":
            if o["type"] == "put":
                need = cents(o["strike"]) * 100 * qty
                if need > avail:
                    res["msg"] = (f"Not cash-secured: needs {money(need)}, you have {money(avail)} available. "
                                  "Collateral must come from cash you already have, not this trade's premium.")
                    return res
                eff.update(premium_c=gross, collateral_c=need, available_after_c=avail - need + gross)
                msg = f"Cash-secured: {money(avail)} available ≥ {money(need)} required"
                av = self.account_value_c(share_price)
                if av and need / av > SIZING_WARN:
                    res["warn"] = (f"This trade's collateral ({money(need)}) is {need / av * 100:.1f}% of account value "
                                   f"(warning above {SIZING_WARN * 100:.0f}%). You can still confirm.")
            else:
                free = self.free_shares()
                if free < qty * 100:
                    sh, lk = self.shares(), self.locked_shares()
                    res["msg"] = (f"Not covered: you hold {sh} shares, {lk} already covering, {max(free, 0)} free. "
                                  f"Need {qty * 100}.")
                    return res
                eff.update(premium_c=gross, locks_shares=qty * 100, available_after_c=avail + gross)
                msg = f"Covered: {free} free shares ≥ {qty * 100} needed"
        elif act == "buy_to_open":
            if not self.settings.get("long_options"):
                res["msg"] = "Buying options to open is off (Settings → Trading)."
                return res
            if gross > avail:
                res["msg"] = f"Not enough cash: costs {money(gross)}, you have {money(avail)} available."
                return res
            eff.update(cost_c=gross, available_after_c=avail - gross)
            msg = f"Paid from Available: {money(gross)}"
        elif act in ("buy_to_close", "sell_to_close"):
            p = self.position(o["position_id"]) if o.get("position_id") else None
            if not p or p["status"] != "open" or p["run_id"] != self.run_id():
                res["msg"] = "That position isn't open."
                return res
            if qty > p["open_qty"]:
                res["msg"] = f"You only have {plural(p['open_qty'], 'contract')} open."
                return res
            want_side = "short" if act == "buy_to_close" else "long"
            if p["side"] != want_side:
                res["msg"] = "That action doesn't match the position."
                return res
            if act == "buy_to_close":
                if p["type"] == "put":
                    released = p["collateral_c"] * qty // p["open_qty"]
                    if gross > released + avail:
                        res["msg"] = f"Not enough cash: buying back costs {money(gross)}."
                        return res
                    eff.update(cost_c=gross, collateral_released_c=released,
                               available_after_c=avail + released - gross)
                else:
                    if gross > avail:
                        res["msg"] = f"Not enough cash: buying back costs {money(gross)}, you have {money(avail)} available."
                        return res
                    eff.update(cost_c=gross, unlocks_shares=qty * 100, available_after_c=avail - gross)
                eff["result_c"] = cents(p["open_price"]) * 100 * qty - gross
                msg = f"Closes {plural(qty, 'contract')} of {p['label']}."
            else:
                eff.update(proceeds_c=gross, available_after_c=avail + gross,
                           result_c=gross - cents(p["open_price"]) * 100 * qty)
                msg = f"Closes {plural(qty, 'contract')} of {p['label']}."
        elif act == "buy_shares":
            if gross > avail:
                res["msg"] = f"Not enough cash: costs {money(gross)}, you have {money(avail)} available."
                return res
            eff.update(cost_c=gross, available_after_c=avail - gross)
            msg = f"Paid from Available: {money(gross)}"
        elif act == "sell_shares":
            free = self.free_shares()
            if qty > free:
                res["msg"] = (f"Only {free} shares are free to sell ({self.locked_shares()} are covering calls). "
                              "Close or let the calls expire first.")
                return res
            eff.update(proceeds_c=gross, available_after_c=avail + gross)
            msg = f"{free} free shares ≥ {qty}"
        res.update(ok=True, msg=msg, effects=eff)
        return res

    # ------------------------------------------------------------------ placing
    def place(self, order, quote, share_price, ts=None):
        ts = ts or timeutil.now()
        chk = self.check(order, quote, share_price, ts)
        if not chk["ok"]:
            raise TradeError(chk["msg"])
        o = chk["order"]
        act, qty, px = o["action"], o["qty"], o["price"]
        pc = cents(px)
        tags = o["tags"]
        with self.db.tx():
            if act == "sell_to_open":
                return self._sell_to_open(o, qty, px, pc, tags, ts)
            if act == "buy_to_open":
                return self._buy_to_open(o, qty, px, pc, tags, ts)
            if act in ("buy_to_close", "sell_to_close"):
                return self._close(o, qty, px, pc, ts)
            if act == "buy_shares":
                return self._buy_shares(o, qty, px, pc, tags, ts)
            return self._sell_shares(o, qty, px, pc, tags, ts)

    def _sell_to_open(self, o, qty, px, pc, tags, ts):
        typ, k, exp = o["type"], o["strike"], o["expiry"]
        prem = pc * 100 * qty
        lab = label(typ, exp, k)
        coll = cents(k) * 100 * qty if typ == "put" else 0
        lot_id = None
        if typ == "call":
            # Attach the call to the oldest lot that still has uncovered shares (for the lot story).
            covered = {}
            for r in self.db.q("SELECT lot_id, SUM(open_qty) n FROM positions WHERE run_id=? AND status='open' "
                               "AND type='call' AND side='short' GROUP BY lot_id", (self.run_id(),)):
                covered[r["lot_id"]] = r["n"] * 100
            for lot in self.lots():
                if lot["open_qty"] - covered.get(lot["id"], 0) > 0:
                    lot_id = lot["id"]
                    break
        pid = self.db.x(
            "INSERT INTO positions(run_id,symbol,type,side,expiry,strike,qty,open_qty,open_price,opened_at,"
            "collateral_c,note,lot_id,realized_c) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (self.run_id(), SYMBOL, typ, "short", exp, k, qty, qty, px, timeutil.iso(ts), coll, o["note"], lot_id, prem))
        self._set_tags(pid, tags)
        detail = f"{money(prem, True)} premium" + (f" · {money(coll)} collateral" if coll else
                                                    f" · {qty * 100} shares now covering")
        if o["note"]:
            detail += f" · “{o['note']}”"
        ev = self.event("Trade", f"Sell to open {qty} × {lab} @ {px:.2f}", detail,
                        {"action": "sell_to_open", "qty": qty, "price": px, "premium_c": prem, "collateral_c": coll},
                        tags, ts, position_id=pid, lot_id=lot_id)
        if coll:
            self.move("available", -coll, "collateral set aside", ts, ev)
            self.move("collateral", coll, "collateral set aside", ts, ev)
        self.move("available", prem, "premium", ts, ev)
        return {"event_id": ev, "position_id": pid}

    def _buy_to_open(self, o, qty, px, pc, tags, ts):
        typ, k, exp = o["type"], o["strike"], o["expiry"]
        cost = pc * 100 * qty
        lab = label(typ, exp, k)
        pid = self.db.x(
            "INSERT INTO positions(run_id,symbol,type,side,expiry,strike,qty,open_qty,open_price,opened_at,note,realized_c)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (self.run_id(), SYMBOL, typ, "long", exp, k, qty, qty, px, timeutil.iso(ts), o["note"], -cost))
        self._set_tags(pid, tags)
        ev = self.event("Trade", f"Buy to open {qty} × {lab} @ {px:.2f}",
                        f"{money(-cost)} cost" + (f" · “{o['note']}”" if o["note"] else ""),
                        {"action": "buy_to_open", "qty": qty, "price": px, "cost_c": cost}, tags, ts, position_id=pid)
        self.move("available", -cost, "option purchase", ts, ev)
        return {"event_id": ev, "position_id": pid}

    def _close(self, o, qty, px, pc, ts):
        p = self.position(o["position_id"])
        gross = pc * 100 * qty
        why = o.get("close_note") or ""
        left = p["open_qty"] - qty
        if p["side"] == "short":
            released = p["collateral_c"] * qty // p["open_qty"] if p["type"] == "put" else 0
            result = cents(p["open_price"]) * 100 * qty - gross
            title = f"Buy to close {qty} × {p['label']} @ {px:.2f}"
            detail = f"{money(-gross)}"
            if released:
                detail += f" from collateral · {money(released - gross)} released to Available"
            detail += f" · result {money(result, True)}"
        else:
            released = 0
            result = gross - cents(p["open_price"]) * 100 * qty
            title = f"Sell to close {qty} × {p['label']} @ {px:.2f}"
            detail = f"{money(gross, True)} · result {money(result, True)}"
        if why:
            detail += f" · “{why}”"
        ev = self.event("Trade", title, detail,
                        {"action": o["action"], "qty": qty, "price": px, "result_c": result, "close_note": why},
                        p["tags"], ts, position_id=p["id"], lot_id=p["lot_id"])
        if p["side"] == "short":
            if released:
                self.move("collateral", -released, "collateral released", ts, ev)
                self.move("available", released, "collateral released", ts, ev)
            self.move("available", -gross, "buy to close", ts, ev)
            realized = p["realized_c"] - gross
        else:
            self.move("available", gross, "sell to close", ts, ev)
            realized = p["realized_c"] + gross
        self.db.x("UPDATE positions SET open_qty=?, collateral_c=collateral_c-?, realized_c=?, status=?, closed_at=? WHERE id=?",
                  (left, released, realized, "open" if left else "closed", None if left else timeutil.iso(ts), p["id"]))
        if not left:
            self._position_summary(p["id"], ts)
        return {"event_id": ev, "position_id": p["id"]}

    def _position_summary(self, pid, ts):
        p = self.position(pid)
        intr = self.interest_on_collateral(p)
        txt = f"Net {money(p['realized_c'], True)} on the option"
        if p["type"] == "put" and p["side"] == "short":
            txt += f" + {money(cents(intr))} est. interest on its collateral"
        self.event("Summary", f"Position closed: {p['label']}", txt + ".",
                   {"realized_c": p["realized_c"], "interest": intr}, p["tags"], ts, position_id=pid, lot_id=p["lot_id"])

    def _buy_shares(self, o, qty, px, pc, tags, ts):
        cost = pc * qty
        ev = self.event("Shares", f"Bought {qty} {SYMBOL} @ {px:.2f}", f"{money(-cost)} from Available"
                        + (f" · “{o['note']}”" if o["note"] else ""),
                        {"action": "buy_shares", "qty": qty, "price": px}, tags, ts)
        self.move("available", -cost, "share purchase", ts, ev)
        lid = self._add_lot(qty, px, ts, "bought", "bought", ev)
        self.db.x("UPDATE events SET lot_id=? WHERE id=?", (lid, ev))
        return {"event_id": ev, "lot_id": lid}

    def _sell_shares(self, o, qty, px, pc, tags, ts):
        proceeds = pc * qty
        ev = self.event("Shares", f"Sold {qty} {SYMBOL} @ {px:.2f}", "", {"action": "sell_shares", "qty": qty, "price": px},
                        tags, ts)
        # Sell from lots that aren't covering calls first.
        covering = {r[0] for r in self.db.q("SELECT lot_id FROM positions WHERE run_id=? AND status='open' AND type='call'"
                                            " AND side='short'", (self.run_id(),))}
        free_first = next((lot["id"] for lot in self.lots() if lot["id"] not in covering), None)
        taken = self._remove_shares(qty, px, ts, "sold", ev, prefer_lot=free_first)
        gain = sum(cents((px - cost) * n) for _, n, cost in taken)
        self.move("available", proceeds, "share sale", ts, ev)
        self.db.x("UPDATE events SET detail=?, lot_id=? WHERE id=?",
                  (f"{money(proceeds, True)} to Available · gain/loss vs. cost {money(gain, True)}"
                   + (f" · “{o['note']}”" if o["note"] else ""), taken[0][0], ev))
        return {"event_id": ev}

    # ------------------------------------------------------------------ expirations
    def due_expirations(self, ts):
        rows = self.db.q("SELECT DISTINCT expiry FROM positions WHERE run_id=? AND status='open' ORDER BY expiry",
                         (self.run_id(),))
        return [dt.date.fromisoformat(r[0]) for r in rows
                if marketcal.expiration_settle_ready(dt.date.fromisoformat(r[0]), ts)]

    def settle_expiration(self, expiry, close, ts=None):
        """Settle every open position expiring on `expiry` against the official close. Auto-exercise / assign
        at >= $0.01 in the money. Returns a list of event ids."""
        ts = ts or timeutil.now()
        exp = expiry.isoformat() if not isinstance(expiry, str) else expiry
        out = []
        with self.db.tx():
            rows = self.db.q("SELECT id FROM positions WHERE run_id=? AND status='open' AND expiry=? "
                             "ORDER BY CASE WHEN type='put' AND side='short' THEN 0 ELSE 1 END, strike",
                             (self.run_id(), exp))
            for r in rows:
                out.append(self._settle_one(self.position(r[0]), close, ts))
        return out

    def _settle_one(self, p, close, ts):
        k, n = p["strike"], p["open_qty"]
        itm = (k - close) if p["type"] == "put" else (close - k)
        itm = round(itm, 4) >= 0.01
        lab = p["label"]
        closetxt = f"{SYMBOL} closed {close:.2f}."
        tags = p["tags"]
        if p["side"] == "short" and p["type"] == "put":
            coll = p["collateral_c"]
            if itm:
                ev = self.event("Assigned", f"Put assigned: bought {n * 100} {SYMBOL} @ {k:.2f}",
                                f"{lab}. {closetxt} {money(coll)} collateral used. Premium kept {money(p['realized_c'], True)}.",
                                {"close": close}, tags, ts, position_id=p["id"])
                self.move("collateral", -coll, "assignment", ts, ev)
                lid = self._add_lot(n * 100, k, ts, "assigned", "assigned", ev, p["id"])
                self.db.x("UPDATE events SET lot_id=? WHERE id=?", (lid, ev))
                self.db.x("UPDATE positions SET lot_id=? WHERE id=?", (lid, p["id"]))
                status = "assigned"
            else:
                ev = self.event("Expired", "Expired worthless",
                                f"{lab} ({n}). {closetxt} {money(coll)} collateral released. "
                                f"Kept {money(p['realized_c'], True)} premium.", {"close": close}, tags, ts, position_id=p["id"])
                self.move("collateral", -coll, "collateral released", ts, ev)
                self.move("available", coll, "collateral released", ts, ev)
                status = "expired"
        elif p["side"] == "short":  # covered call
            if itm:
                proceeds = cents(k) * 100 * n
                ev = self.event("Called away", f"Shares called away: sold {n * 100} {SYMBOL} @ {k:.2f}",
                                f"{lab}. {closetxt} {money(proceeds, True)} to Available. Premium kept "
                                f"{money(p['realized_c'], True)}.", {"close": close}, tags, ts, position_id=p["id"],
                                lot_id=p["lot_id"])
                taken = self._remove_shares(n * 100, k, ts, "called away", ev, prefer_lot=p["lot_id"], position_id=p["id"])
                self.move("available", proceeds, "called away", ts, ev)
                gain = sum(cents((k - cost) * q) for _, q, cost in taken)
                self.db.x("UPDATE events SET detail=detail || ? WHERE id=?",
                          (f" Shares vs. cost {money(gain, True)}.", ev))
                status = "called"
            else:
                ev = self.event("Expired", "Expired worthless",
                                f"{lab} ({n}). {closetxt} {n * 100} shares unlocked. Kept {money(p['realized_c'], True)} premium.",
                                {"close": close}, tags, ts, position_id=p["id"], lot_id=p["lot_id"])
                status = "expired"
        else:  # long option
            if itm and p["type"] == "call":
                cost = cents(k) * 100 * n
                if self.available() >= cost:
                    ev = self.event("Exercised", f"Call exercised: bought {n * 100} {SYMBOL} @ {k:.2f}",
                                    f"{lab}. {closetxt} {money(-cost)} from Available.", {"close": close}, tags, ts,
                                    position_id=p["id"])
                    self.move("available", -cost, "exercise", ts, ev)
                    self._add_lot(n * 100, k, ts, "exercised", "exercised", ev, p["id"])
                else:
                    val = cents((close - k) * 100 * n)
                    ev = self.event("Exercised", f"Long call settled for value {money(val, True)}",
                                    f"{lab}. {closetxt} Not enough cash to take the shares, so it was settled at "
                                    f"intrinsic value.", {"close": close}, tags, ts, position_id=p["id"])
                    self.move("available", val, "cash settlement", ts, ev)
                status = "exercised"
            elif itm:
                if self.free_shares() >= n * 100:
                    proceeds = cents(k) * 100 * n
                    ev = self.event("Exercised", f"Put exercised: sold {n * 100} {SYMBOL} @ {k:.2f}",
                                    f"{lab}. {closetxt} {money(proceeds, True)} to Available.", {"close": close},
                                    tags, ts, position_id=p["id"])
                    self._remove_shares(n * 100, k, ts, "exercised", ev, position_id=p["id"])
                    self.move("available", proceeds, "exercise", ts, ev)
                else:
                    val = cents((k - close) * 100 * n)
                    ev = self.event("Exercised", f"Long put settled for value {money(val, True)}",
                                    f"{lab}. {closetxt} Not enough free shares to deliver, so it was settled at "
                                    f"intrinsic value.", {"close": close}, tags, ts, position_id=p["id"])
                    self.move("available", val, "cash settlement", ts, ev)
                status = "exercised"
            else:
                ev = self.event("Expired", "Expired worthless", f"{lab} ({n}), bought option. {closetxt}",
                                {"close": close}, tags, ts, position_id=p["id"])
                status = "expired"
        self.db.x("UPDATE positions SET status=?, open_qty=0, collateral_c=0, closed_at=? WHERE id=?",
                  (status, timeutil.iso(ts), p["id"]))
        self._position_summary(p["id"], ts)
        return ev

    # ------------------------------------------------------------------ interest
    def last_accrual_day(self, run_id=None):
        rid = run_id or self.run_id()
        d = self.db.val("SELECT MAX(day) FROM accruals WHERE run_id=?", (rid,))
        return dt.date.fromisoformat(d) if d else None

    def accrue_interest(self, through, rate_for_day, haircut=0.0, ts=None):
        """Accrue simple daily interest (actual/365) on all cash for each calendar day from the day after the last
        accrual (or the run start) through `through`, inclusive. `rate_for_day(date)` returns an annual % rate.
        Returns (days, amount)."""
        r = self.run()
        if not r:
            return 0, 0.0
        start = self.last_accrual_day()
        day = (start + dt.timedelta(days=1)) if start else dt.date.fromisoformat(r["start_day"])
        n, total = 0, 0.0
        with self.db.tx():
            while day <= through:
                rate = max(0.0, (rate_for_day(day) or 0.0) - (haircut or 0.0))
                a, c = self.balances(day)
                amt = (a + c) / 100 * rate / 100 / 365
                self.db.x("INSERT OR REPLACE INTO accruals(run_id,day,rate,balance_c,amount) VALUES(?,?,?,?,?)",
                          (r["id"], day.isoformat(), rate, a + c, amt))
                n += 1
                total += amt
                day += dt.timedelta(days=1)
        return n, total

    def pay_interest(self, today, ts=None, force=False):
        """Post unpaid accruals on each pay date (the 15th or the business day before) that has arrived.
        Accruals for days before the pay date are paid. With force=True everything unpaid is paid now (Close run)."""
        r = self.run()
        if not r:
            return []
        ts = ts or timeutil.now()
        paid = []
        first = self.db.val("SELECT MIN(day) FROM accruals WHERE run_id=? AND paid_day IS NULL", (r["id"],))
        if not first:
            return []
        start = dt.date.fromisoformat(first)
        dates = marketcal.pay_dates_between(start, today)
        if force:
            dates = dates + [today]
        with self.db.tx():
            for p in dates:
                rows = self.db.q("SELECT day, amount, rate FROM accruals WHERE run_id=? AND paid_day IS NULL AND "
                                 + ("day<=?" if force and p == today else "day<?"), (r["id"], p.isoformat()))
                if not rows:
                    continue
                amt = sum(x["amount"] for x in rows)
                c = cents(amt)
                d0, d1 = rows[0]["day"], rows[-1]["day"]
                avg = sum(x["rate"] for x in rows) / len(rows)
                pts = ts if (force and p == today) else dt.datetime.combine(p, dt.time(8, 30), timeutil.CT)
                ev = self.event("Interest", f"Interest posted {money(c, True)}",
                                f"{fmt_date(d0)}–{fmt_date(d1)} · avg rate {avg:.2f}% on all cash.",
                                {"amount": amt, "from": d0, "to": d1}, ts=pts)
                self.move("available", c, "interest", pts, ev)
                self.db.x("UPDATE accruals SET paid_day=?, paid_event_id=? WHERE run_id=? AND paid_day IS NULL AND day IN (%s)"
                          % ",".join("?" * len(rows)), [p.isoformat(), ev, r["id"]] + [x["day"] for x in rows])
                paid.append(ev)
        return paid

    def catch_up_interest(self, today, rate_for_day, haircut=0.0, ts=None):
        """Accrue every day before `today` and post each pay date in order, so posted interest earns interest
        from the day it was paid. Returns (days accrued, amount accrued, [interest event ids])."""
        r = self.run()
        if not r:
            return 0, 0.0, []
        last = self.last_accrual_day() or (dt.date.fromisoformat(r["start_day"]) - dt.timedelta(days=1))
        days, amt, evs = 0, 0.0, []
        for p in marketcal.pay_dates_between(last, today):
            n, a = self.accrue_interest(p - dt.timedelta(days=1), rate_for_day, haircut, ts)
            days, amt = days + n, amt + a
            evs += self.pay_interest(p, ts)
        n, a = self.accrue_interest(today - dt.timedelta(days=1), rate_for_day, haircut, ts)
        evs += self.pay_interest(today, ts)
        return days + n, amt + a, evs

    def interest_earned_c(self):
        return self.db.val("SELECT SUM(amount_c) FROM cash WHERE run_id=? AND reason='interest'", (self.run_id(),), 0)

    def interest_on_collateral(self, p):
        """Estimated interest earned on a short put's collateral over the days it was held."""
        if not (p["type"] == "put" and p["side"] == "short"):
            return 0.0
        start = timeutil.parse(p["opened_at"]).astimezone(timeutil.CT).date()
        end = timeutil.parse(p["closed_at"]).astimezone(timeutil.CT).date() if p["closed_at"] else timeutil.today_ct()
        coll = cents(p["strike"]) * 100 * p["qty"] / 100
        rates = [r[0] for r in self.db.q("SELECT rate FROM accruals WHERE run_id=? AND day>=? AND day<? ORDER BY day",
                                         (p["run_id"], start.isoformat(), end.isoformat()))]
        days = max((end - start).days, 0)
        if len(rates) < days:
            last = rates[-1] if rates else self.db.val(
                "SELECT rate FROM accruals WHERE run_id=? ORDER BY day DESC LIMIT 1", (p["run_id"],), 0.0)
            rates += [last] * (days - len(rates))
        return sum(coll * r / 100 / 365 for r in rates[:days])

    # ------------------------------------------------------------------ dividends
    def credit_dividend(self, ex_day, amount, ts=None):
        """Credit a cash dividend for shares held at the close before the ex-date. Idempotent."""
        ts = ts or timeutil.now()
        exd = ex_day if isinstance(ex_day, dt.date) else dt.date.fromisoformat(ex_day)
        r = self.run()
        if not r or exd <= dt.date.fromisoformat(r["start_day"]):
            return None
        if self.db.one("SELECT 1 FROM dividends WHERE run_id=? AND ex_day=?", (r["id"], exd.isoformat())):
            return None
        held = self.shares_on(exd - dt.timedelta(days=1))
        with self.db.tx():
            self.db.x("INSERT INTO dividends(run_id,ex_day,amount) VALUES(?,?,?)", (r["id"], exd.isoformat(), amount))
            if held <= 0:
                return None
            c = cents(amount * held)
            ev = self.event("Dividend", f"Dividend {money(c, True)}",
                            f"{SYMBOL} ex-date {fmt_date(exd)} · ${amount:.4f}/share × {held} shares.",
                            {"amount": amount, "shares": held}, ts=ts)
            self.move("available", c, "dividend", ts, ev)
            return ev

    # ------------------------------------------------------------------ totals
    def premium_collected_c(self):
        return self.db.val("SELECT SUM(amount_c) FROM cash WHERE run_id=? AND reason='premium'", (self.run_id(),), 0)

    def dividends_c(self):
        return self.db.val("SELECT SUM(amount_c) FROM cash WHERE run_id=? AND reason='dividend'", (self.run_id(),), 0)

    # ------------------------------------------------------------------ snapshots
    def snapshot(self, day, share_price, tqqq_close, marks=None, estimated=False, ts=None):
        r = self.run()
        if not r:
            return
        d = day.isoformat() if not isinstance(day, str) else day
        if estimated:
            a, c = self.balances(d)
            acc = self.accrued(as_of=d)
            sh = self.shares_on(d)
        else:
            a, c = self.balances()
            acc = self.accrued()
            sh = self.shares()
        av = a + c + cents(sh * (share_price or 0))
        self.db.x("INSERT OR REPLACE INTO snapshots(run_id,day,ts,available_c,collateral_c,accrued,shares,share_price,"
                  "account_value_c,tqqq_close,marks,estimated) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                  (r["id"], d, timeutil.iso(ts), a, c, acc, sh, share_price, av, tqqq_close,
                   json.dumps(marks or {}), int(estimated)))
        return av

    def fill_snapshot_gaps(self, closes, through):
        """Fill trading days without a snapshot (app not opened) using daily closes: {date_iso: close}."""
        r = self.run()
        if not r:
            return 0
        have = {x[0] for x in self.db.q("SELECT day FROM snapshots WHERE run_id=?", (r["id"],))}
        d = dt.date.fromisoformat(r["start_day"])
        n = 0
        while d < through:
            iso = d.isoformat()
            if marketcal.is_trading_day(d) and iso not in have and iso in closes:
                self.snapshot(d, closes[iso], closes[iso], estimated=True)
                n += 1
            d += dt.timedelta(days=1)
        return n


def _norm(order):
    o = dict(order or {})
    o["action"] = o.get("action", "")
    try:
        o["qty"] = int(str(o.get("qty", "")).strip())
    except ValueError:
        o["qty"] = None
    try:
        p = o.get("price")
        o["price"] = None if p in (None, "") else float(str(p).replace("$", "").strip())
    except ValueError:
        o["price"] = None
    if o.get("strike") is not None:
        o["strike"] = float(o["strike"])
    if o.get("position_id") is not None:
        o["position_id"] = int(o["position_id"])
    o["note"] = (o.get("note") or "").strip()
    o["close_note"] = (o.get("close_note") or "").strip()
    tags = []
    for t in o.get("tags") or []:
        t = "#" + str(t).strip().lstrip("#").replace(" ", "-").lower()
        if len(t) > 1 and t not in tags:
            tags.append(t)
    o["tags"] = tags
    return o
