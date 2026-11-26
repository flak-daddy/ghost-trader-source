"""Wheel cycles and performance stats (v1.13.0). Read-only: works out, from the ledger, each trip around the wheel.

A cycle starts when you sell a cash-secured put. It ends when that put expires or is closed, or, if it was assigned,
when the shares it brought in are gone (called away or sold). Covered calls you sold on those shares belong to the
cycle. Shares you bought outright aren't part of any cycle. Interest on the collateral isn't counted: a cycle's
numbers are the options' premium (net of buy-backs) plus the gain or loss on the shares.
"""
import datetime as dt

from . import SYMBOL, timeutil
from .ledger import cents


def _day(ts):
    return timeutil.parse(ts).astimezone(timeutil.CT).date()


def _outcome(status):
    return {"expired": "Put expired worthless", "closed": "Put closed early", "assigned": "Put assigned"}.get(status, status)


def cycles(led, share_price=None):
    """Every wheel cycle of the current run, oldest first."""
    rid = led.run_id()
    if not rid:
        return []
    today = timeutil.today_ct()
    out = []
    for p in led.db.q("SELECT * FROM positions WHERE run_id=? AND type='put' AND side='short' ORDER BY opened_at, id", (rid,)):
        qty, k = p["qty"], p["strike"]
        put_c = p["realized_c"]
        coll = cents(k) * 100 * qty
        start = _day(p["opened_at"])
        steps = [{"day": start.isoformat(), "text": f"Sold {qty} × ${k:g} put", "c": cents(p["open_price"]) * 100 * qty}]
        cyc = {"id": p["id"], "put_id": p["id"], "symbol": p["symbol"], "qty": qty, "strike": k, "expiry": p["expiry"], "collateral_c": coll,
               "start": start.isoformat(), "put_c": put_c, "call_c": 0, "share_c": 0, "calls": 0, "lot_id": None,
               "shares": 0, "cost": None, "breakeven": None, "open_calls": 0}
        if p["status"] == "open":
            cyc.update(open=True, stage="Short put", outcome=None)
            end = today
        elif p["status"] in ("expired", "closed"):
            end = _day(p["closed_at"]) if p["closed_at"] else today
            cyc.update(open=False, stage="Done", outcome=_outcome(p["status"]))
            steps.append({"day": end.isoformat(), "text": _outcome(p["status"]),
                          "c": put_c - steps[0]["c"] if p["status"] == "closed" else 0})
        else:  # assigned: follow the shares
            lot = led.db.one("SELECT * FROM lots WHERE run_id=? AND source_position_id=?", (rid, p["id"]))
            end = _day(p["closed_at"]) if p["closed_at"] else today
            steps.append({"day": end.isoformat(), "text": f"Assigned: bought {qty * 100} @ ${k:.2f}", "c": 0})
            if not lot:
                cyc.update(open=False, stage="Done", outcome="Put assigned")
            else:
                cost = lot["cost"]
                cyc.update(lot_id=lot["id"], cost=cost, shares=lot["open_qty"])
                calls = [dict(c) for c in led.db.q("SELECT * FROM positions WHERE run_id=? AND lot_id=? AND type='call' "
                                                   "AND side='short' ORDER BY opened_at, id", (rid, lot["id"]))]
                call_c = sum(c["realized_c"] for c in calls)
                cyc["calls"] = len(calls)
                cyc["open_calls"] = sum(1 for c in calls if c["status"] == "open")
                for c in calls:
                    cs = _day(c["opened_at"])
                    steps.append({"day": cs.isoformat(), "text": f"Sold {c['qty']} × ${c['strike']:g} call", "c": cents(c["open_price"]) * 100 * c["qty"]})
                    if c["status"] != "open":
                        w = {"called": "Shares called away", "expired": "Call expired worthless", "closed": "Call closed early"}.get(c["status"], c["status"])
                        steps.append({"day": (_day(c["closed_at"]) if c["closed_at"] else cs).isoformat(), "text": w,
                                      "c": (c["realized_c"] - cents(c["open_price"]) * 100 * c["qty"]) if c["status"] == "closed" else 0})
                moves = [dict(m) for m in led.db.q("SELECT * FROM lot_moves WHERE lot_id=? AND direction='out' ORDER BY ts", (lot["id"],))]
                share_c = sum(cents((m["price"] - cost) * m["qty"]) for m in moves)
                for m in moves:
                    steps.append({"day": m["day"], "text": f"{m['how'].capitalize()}: {m['qty']} @ ${m['price']:.2f}",
                                  "c": cents((m["price"] - cost) * m["qty"])})
                prem_c = put_c + call_c
                per_share = prem_c / 100 / (qty * 100)
                cyc.update(call_c=call_c, share_c=share_c, breakeven=round(cost - per_share, 2))
                if lot["open_qty"] > 0:
                    sp = share_price if p["symbol"] == SYMBOL else led.price_of(p["symbol"])
                    if sp:
                        cyc["unreal_c"] = cents((sp - cost) * lot["open_qty"])
                    cyc.update(open=True, stage="Covered call" if cyc["open_calls"] else "Holding shares", outcome=None)
                    end = today
                else:
                    last = moves[-1]["how"] if moves else ""
                    end = _day(lot["closed_at"]) if lot["closed_at"] else end
                    cyc.update(open=False, stage="Done", outcome="Called away" if last == "called away" else "Shares sold")
        pnl = cyc["put_c"] + cyc["call_c"] + cyc["share_c"] + (cyc.get("unreal_c") or 0)
        days = max((end - start).days, 0)
        steps.sort(key=lambda s: s["day"])
        for s in steps:
            s["when"] = timeutil.fmt_date(s["day"])
        cyc.update(pnl_c=pnl, days=days, end=end.isoformat() if not cyc["open"] else None,
                   ret=pnl / coll if coll else None, ann=(pnl / coll) * 365 / max(days, 1) if coll else None,
                   win=pnl > 0, steps=steps, start_txt=timeutil.fmt_date(start.isoformat()),
                   end_txt=None if cyc["open"] else timeutil.fmt_date(end.isoformat()),
                   label=(f"{p['symbol']} " if p["symbol"] != SYMBOL else "") +
                   f"${k:g} put · exp {timeutil.fmt_exp(dt.date.fromisoformat(p['expiry']))}")
        out.append(cyc)
    return out


def summary(cs):
    """Quick wheel numbers from the closed cycles (open ones are listed, not scored)."""
    closed = [c for c in cs if not c["open"]]
    n = len(closed)
    wins = [c for c in closed if c["pnl_c"] > 0]
    full = [c for c in closed if c["outcome"] in ("Called away", "Shares sold")]
    return {
        "open": sum(1 for c in cs if c["open"]), "closed": n, "wins": len(wins),
        "win_rate": len(wins) / n if n else None,
        "pnl_c": sum(c["pnl_c"] for c in closed),
        "avg_c": round(sum(c["pnl_c"] for c in closed) / n) if n else None,
        "avg_days": sum(c["days"] for c in closed) / n if n else None,
        "best_c": max((c["pnl_c"] for c in closed), default=None),
        "worst_c": min((c["pnl_c"] for c in closed), default=None),
        "wheels": len(full), "open_pnl_c": sum(c["pnl_c"] for c in cs if c["open"]),
    }


def stats(led, snaps=None):
    """Performance stats (v1.13.0): drawdown and recovery, how often short options paid, how long they were held,
    how much of the premium was kept, and premium per $1,000 of put collateral."""
    rid = led.run_id()
    shorts = [dict(r) for r in led.db.q("SELECT * FROM positions WHERE run_id=? AND side='short'", (rid,))]
    done = [r for r in shorts if r["status"] != "open"]
    out = {"options": len(shorts), "closed_options": len(done)}
    if done:
        out["win_rate"] = sum(1 for r in done if r["realized_c"] > 0) / len(done)
        out["avg_days"] = sum(max((_day(r["closed_at"]) - _day(r["opened_at"])).days, 0) for r in done if r["closed_at"]) / len(done)
        kept = []
        for r in done:
            init = cents(r["open_price"]) * 100 * r["qty"]
            if init:
                kept.append(max(min(r["realized_c"] / init, 1.0), -9.99))
        out["avg_kept"] = sum(kept) / len(kept) if kept else None
    puts = [r for r in shorts if r["type"] == "put"]
    coll = sum(cents(r["strike"]) * 100 * r["qty"] for r in puts)
    if coll:
        out["per_1k"] = sum(cents(r["open_price"]) * 100 * r["qty"] for r in puts) / coll * 1000   # dollars of premium per $1,000
    # drawdown from the daily account value
    snaps = snaps if snaps is not None else [dict(s) for s in led.db.q("SELECT * FROM snapshots WHERE run_id=? ORDER BY day", (rid,))]
    vals = [(s["day"], s["account_value_c"]) for s in snaps if s["account_value_c"]]
    if len(vals) >= 2:
        peak, peak_day, worst, w_peak, w_trough = vals[0][1], vals[0][0], 0.0, None, None
        for d, v in vals:
            if v >= peak:
                peak, peak_day = v, d
            dd = v / peak - 1
            if dd < worst:
                worst, w_peak, w_trough = dd, (peak, peak_day), (d, v)
        out["max_dd"] = worst
        if w_trough:
            rec = next((d for d, v in vals if d > w_trough[0] and v >= w_peak[0]), None)
            out["dd_trough_day"] = w_trough[0]
            out["dd_recover_days"] = (dt.date.fromisoformat(rec) - dt.date.fromisoformat(w_trough[0])).days if rec else None
            out["dd_recovered"] = rec is not None
    return out
