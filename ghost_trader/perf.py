"""Performance: account value over time vs. TQQQ buy-and-hold and T-bills, share in/out markers, and premium +
interest by month."""
import datetime as dt

from . import SYMBOL, timeutil
from .ledger import cents, money


def build(led, rates, share_price):
    r = led.run()
    if not r:
        return None
    rid = r["id"]
    snaps = [dict(s) for s in led.db.q("SELECT * FROM snapshots WHERE run_id=? ORDER BY day", (rid,))]
    start_cash = r["start_cash_c"] / 100
    start_day = dt.date.fromisoformat(r["start_day"])
    # TQQQ close on/just before the run start (buy & hold entry)
    entry = led.db.val("SELECT close FROM prices WHERE symbol=? AND day<=? ORDER BY day DESC LIMIT 1",
                       (SYMBOL, r["start_day"]))
    if entry is None and snaps:
        entry = snaps[0]["tqqq_close"] or snaps[0]["share_price"]
    days, acct, est, tq, bh, tb = [], [], [], [], [], []
    for s in snaps:
        d = dt.date.fromisoformat(s["day"])
        days.append(s["day"])
        acct.append(s["account_value_c"] / 100)
        est.append(bool(s["estimated"]))
        close = s["tqqq_close"] or s["share_price"]
        tq.append(close)
        bh.append(round(start_cash * close / entry, 2) if (entry and close) else None)
        tb.append(round(_tbill(start_cash, start_day, d, rates), 2))
    markers = []
    for m in led.db.q("SELECT lm.*, l.source, l.cost FROM lot_moves lm JOIN lots l ON l.id=lm.lot_id "
                      "WHERE lm.run_id=? ORDER BY lm.ts", (rid,)):
        word = {"assigned": "Assigned", "bought": "Bought", "exercised": "Exercised", "sold": "Sold",
                "called away": "Called away"}.get(m["how"], m["how"].title())
        markers.append({"day": m["day"], "lot_id": m["lot_id"], "dir": m["direction"], "qty": m["qty"],
                        "price": m["price"], "how": m["how"], "event_id": m["event_id"],
                        "label": f"{word} {m['qty']} @ ${m['price']:.2f}"})
    # monthly premium + interest
    months = {}
    for row in led.db.q("SELECT substr(day,1,7) m, reason, SUM(amount_c) FROM cash WHERE run_id=? AND reason IN "
                        "('premium','interest') GROUP BY m, reason", (rid,)):
        months.setdefault(row[0], {"premium_c": 0, "interest_c": 0, "accrued_c": 0})[
            "premium_c" if row[1] == "premium" else "interest_c"] = row[2]
    acc = led.accrued()
    if acc:
        m = timeutil.today_ct().strftime("%Y-%m")
        months.setdefault(m, {"premium_c": 0, "interest_c": 0, "accrued_c": 0})["accrued_c"] = cents(acc)
    monthly = [{"month": k, **v} for k, v in sorted(months.items())]
    av_now = led.account_value_c(share_price) / 100
    ndays = max((timeutil.today_ct() - start_day).days, 1)
    ret = av_now / start_cash - 1
    bh_now = start_cash * share_price / entry if (entry and share_price) else None
    tb_now = _tbill(start_cash, start_day, timeutil.today_ct(), rates)
    return {
        "days": days, "acct": acct, "est": est, "tqqq": tq, "bh": bh, "tb": tb, "markers": markers,
        "monthly": monthly, "entry": entry, "start_day": r["start_day"],
        "summary": {
            "value": av_now, "ret": ret, "ann": ret * 365 / ndays,
            "bh_value": bh_now, "bh_ret": (bh_now / start_cash - 1) if bh_now else None,
            "tb_value": tb_now, "tb_ret": tb_now / start_cash - 1, "days": ndays,
            "premium_c": led.premium_collected_c(), "interest_c": led.interest_earned_c(), "accrued_c": cents(acc),
        },
    }


def _tbill(start_cash, start, end, rates):
    """Cash-only benchmark: start cash earning the daily T-bill rate, compounding monthly like the account."""
    v, acc, d = start_cash, 0.0, start
    while d < end:
        acc += v * (rates.for_day(d) or 0) / 100 / 365
        nd = d + dt.timedelta(days=1)
        if nd.day == 15 or nd == end:
            v, acc = v + acc, 0.0
        d = nd
    return v + acc


def lot_story(led, lot_id, share_price):
    lot = led.db.one("SELECT * FROM lots WHERE id=?", (lot_id,))
    if not lot:
        return None
    lot = dict(lot)
    tl = []
    premium_c = 0
    interest = 0.0
    src = led.position(lot["source_position_id"]) if lot["source_position_id"] else None
    if src:
        ev = led.db.one("SELECT * FROM events WHERE position_id=? AND kind='Trade' ORDER BY id LIMIT 1", (src["id"],))
        tl.append({"ts": src["opened_at"], "text": f"Sold {src['qty']} × {src['label']} @ {src['open_price']:.2f}",
                   "amt_c": cents(src["open_price"]) * 100 * src["qty"], "note": src["note"],
                   "event_id": ev["id"] if ev else None})
        premium_c += src["realized_c"] if src["side"] == "short" else 0
        interest += led.interest_on_collateral(src)
    for m in led.db.q("SELECT * FROM lot_moves WHERE lot_id=? ORDER BY ts", (lot_id,)):
        word = {"assigned": "Put assigned: bought", "bought": "Bought", "exercised": "Exercised:",
                "sold": "Sold", "called away": "Called away: sold"}.get(m["how"], m["how"])
        tl.append({"ts": m["ts"], "text": f"{word} {m['qty']} @ ${m['price']:.2f}", "event_id": m["event_id"],
                   "dir": m["direction"]})
    for p in led.db.q("SELECT id FROM positions WHERE lot_id=? AND type='call' AND side='short' ORDER BY opened_at",
                      (lot_id,)):
        p = led.position(p[0])
        tl.append({"ts": p["opened_at"], "text": f"Sold {p['qty']} × {p['label']} @ {p['open_price']:.2f}",
                   "amt_c": cents(p["open_price"]) * 100 * p["qty"], "note": p["note"],
                   "status": p["status"]})
        premium_c += p["realized_c"]
    tl.sort(key=lambda x: x["ts"])
    outs = led.db.q("SELECT * FROM lot_moves WHERE lot_id=? AND direction='out' ORDER BY ts", (lot_id,))
    sold_c = sum(cents((o["price"] - lot["cost"]) * o["qty"]) for o in outs)
    held_c = cents((share_price - lot["cost"]) * lot["open_qty"]) if share_price else 0
    open_calls = [led.position(r[0])["label"] for r in
                  led.db.q("SELECT id FROM positions WHERE lot_id=? AND status='open' AND type='call'", (lot_id,))]
    tags = sorted({t[0] for t in led.db.q(
        "SELECT DISTINCT tag FROM position_tags WHERE position_id IN (SELECT id FROM positions WHERE lot_id=? OR id=?)",
        (lot_id, lot["source_position_id"] or -1))})
    got_in = f"{'Put assigned' if lot['source'] == 'assigned' else lot['source'].title()} @ ${lot['cost']:.2f} · " \
             f"{timeutil.fmt_date(lot['acquired_day'])}"
    if lot["open_qty"] == 0 and outs:
        o = outs[-1]
        got_out = f"{'Called away' if o['how'] == 'called away' else o['how'].title()} @ ${o['price']:.2f} · " \
                  f"{timeutil.fmt_date(o['day'])} · {money(sold_c, True)}"
    else:
        got_out = "Not yet · still held" + (f", covering {open_calls[0]}" if open_calls else ", not covered")
    return {
        "lot": lot, "timeline": tl, "premium_c": premium_c, "interest_c": cents(interest),
        "shares_c": sold_c + held_c, "net_c": premium_c + cents(interest) + sold_c + held_c,
        "got_in": got_in, "got_out": got_out, "open_calls": open_calls, "tags": tags,
        "today": {"price": share_price, "pnl_c": held_c,
                  "pct": (share_price / lot["cost"] - 1) if share_price and lot["open_qty"] else None},
        "held": lot["open_qty"] > 0,
    }
