"""Daily TQQQ implied-volatility history (v1.9.0).

Saves one 30-day at-the-money IV reading per trading session, silently, so IV rank and percentile have a
year of history to work from once they're shown. Never blocks or fails anything: every entry point swallows
its own errors.
"""
import datetime as dt
import logging
import math

from . import marketcal, timeutil

log = logging.getLogger("ghost_trader.ivhist")
TARGET_DAYS = 30
OPEN_CT = dt.time(8, 30)


def atm_iv(rows, S):
    """At-the-money IV for one expiration: the strike nearest TQQQ that has an IV, averaging its call and put."""
    by_k = {}
    for r in rows:
        if r.get("iv") and r["iv"] > 0:
            by_k.setdefault(r["strike"], []).append(r["iv"])
    if not by_k or not S:
        return None
    k = min(by_k, key=lambda x: (abs(x - S), -len(by_k[x])))
    v = by_k[k]
    return sum(v) / len(v)


def interp(points, target=TARGET_DAYS):
    """Constant-maturity IV from (days, iv) points: linear in total variance between the two expirations that
    bracket `target`; the nearest one if none bracket it."""
    pts = sorted((d, v) for d, v in points if d and d > 0 and v)
    if not pts:
        return None
    lo = [p for p in pts if p[0] <= target]
    hi = [p for p in pts if p[0] >= target]
    if lo and hi:
        (d1, v1), (d2, v2) = lo[-1], hi[0]
        if d1 == d2:
            return v1
        w = (target - d1) / (d2 - d1)
        var = (v1 * v1 * d1) * (1 - w) + (v2 * v2 * d2) * w
        return math.sqrt(var / target)
    return (lo[-1] if lo else hi[0])[1]


def session_day(now_ct):
    """The trading session a reading belongs to, or None if it's before the open on a trading day (those
    quotes are yesterday's close, which is only used to fill a day that has no reading yet)."""
    d = now_ct.date()
    if marketcal.is_trading_day(d) and now_ct.time() >= OPEN_CT:
        return d, True
    return marketcal.prev_trading_day(d), False


def pick_expiries(expiries, today):
    """The expirations that bracket 30 days (plus one extra on each side when available)."""
    ds = sorted({e for e in expiries})
    days = [(e, (dt.date.fromisoformat(e) - today).days) for e in ds]
    days = [x for x in days if x[1] >= 3]
    lo = [x for x in days if x[1] <= TARGET_DAYS][-1:]
    hi = [x for x in days if x[1] >= TARGET_DAYS][:1]
    return [e for e, _ in (lo + hi)] or [e for e, _ in days[:1]]


def record(app):
    """Take today's reading from the chains Ghost Trader already pulls. Returns the saved row or None."""
    now = timeutil.now_ct()
    day, in_session = session_day(now)
    if not in_session and app.db.val("SELECT 1 FROM iv_history WHERE day=?", (day.isoformat(),)):
        return None
    u = app.quotes.underlying()
    if not u or u.get("stale") or u.get("manual"):
        return None
    S = u["price"]
    today = now.date()
    pts = []
    for e in pick_expiries(app.quotes.expirations(), today):
        c = app.quotes.chain(e)
        if c.get("error"):
            continue
        v = atm_iv(c["rows"], S)
        if v:
            pts.append(((dt.date.fromisoformat(e) - today).days, v))
    iv = interp(pts)
    if not iv:
        return None
    row = (day.isoformat(), round(iv, 4), round(S, 2), timeutil.iso(), ",".join(f"{d}:{v:.4f}" for d, v in pts))
    app.db.x("INSERT OR REPLACE INTO iv_history(day, iv, price, asof, points) VALUES(?,?,?,?,?)", row)
    return row


def record_safe(app):
    try:
        return record(app)
    except Exception as e:  # noqa: BLE001 - background data collection must never bother the user
        log.warning("IV reading not saved: %s", e)
        return None


def history(db, since=None):
    q = "SELECT day, iv FROM iv_history" + (" WHERE day>=?" if since else "") + " ORDER BY day"
    return [(r[0], r[1]) for r in db.q(q, (since,) if since else ())]
