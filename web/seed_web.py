"""Seed a lived-in demo run relative to today, for the web demo.

About eight weeks of history on the demo provider's synthetic prices: a full wheel (put assigned,
covered call, shares called away), weekly puts that expire worthless, an early buy-to-close, and a
second wheel still in progress (assigned shares with an open covered call) plus an open put.
Strikes are picked from the synthetic path, which is known in advance, so the story always plays out.
"""
import datetime as dt
import math

from ghost_trader import config, db as dbm, marketcal, timeutil
from ghost_trader.ledger import Ledger
from ghost_trader.market import bs


def _at(d, hh=10, mm=0):
    return dt.datetime(d.year, d.month, d.day, hh, mm, tzinfo=timeutil.CT)


def _td(d):
    """Nearest trading day on or before d."""
    return d if marketcal.is_trading_day(d) else marketcal.prev_trading_day(d)


def _friday(d, weeks):
    """Trading-day expiration: the Friday `weeks` weeks after d's week (holiday-shifted)."""
    f = d + dt.timedelta(days=(4 - d.weekday()) % 7 + 7 * weeks)
    return _td(f)


def _price(S, K, opened, expiry, call):
    T = max((dt.datetime.combine(expiry, dt.time(15, 0), timeutil.CT) - opened).total_seconds(), 3600) / (365 * 86400)
    m = math.log(K / S)
    iv = max(0.35, 0.62 - 0.55 * m + 0.9 * m * m)
    px, _ = bs(S, K, T, 0.042, iv, call)
    return max(round(px, 2), 0.05)


def seed(provider, today=None):
    today = today or timeutil.today_ct()
    D = dbm.DB(config.db_path())
    L = Ledger(D, config.Settings())
    P = provider._price_on
    def monday(d):
        d = _td(d)
        while d.weekday() != 0 or not marketcal.is_trading_day(d):
            d = marketcal.next_trading_day(d)
        return d

    def story(st):
        """Score a start day: 2 = put assigned and later called away, 1 = assigned only, 0 = neither."""
        k = float(round(P(st)))
        e1 = next((e for e in (_friday(st, w) for w in (1, 2, 3)) if e < today and P(e) < k - 0.3), None)
        if not e1:
            return 0, None, None, k
        c = marketcal.next_trading_day(e1)
        e2 = next((e for e in (_friday(c, w) for w in (1, 2, 3)) if e < today and P(e) > k + 1.3), None)
        return (2 if e2 else 1), e1, e2, k

    best = None
    for back in range(6, 13):  # weeks back; first start with the full story wins
        st = monday(today - dt.timedelta(weeks=back))
        sc = story(st)
        if best is None or sc[0] > best[1][0]:
            best = (st, sc)
        if sc[0] == 2:
            break
    start, (score, e1, e2, k1) = best

    def trade(ts, **o):
        timeutil.freeze(ts)
        S = P(ts.date())
        px = o.pop("px", None)
        if px is None and o["action"] != "buy_to_close":
            exp = dt.date.fromisoformat(o["expiry"])
            px = _price(S, o["strike"], ts, exp, o["type"] == "call")
        q = {"bid": round(px * 0.98 - .01, 2), "ask": round(px * 1.02 + .01, 2)}
        return L.place(dict(o, price=px), q, S, ts)

    def settle(exp):
        ts = _at(exp, 17, 5)
        if ts.date() >= today:
            return
        timeutil.freeze(ts)
        L.catch_up_interest(exp, lambda d: 4.2)
        L.settle_expiration(exp, P(exp), ts)

    was = timeutil._frozen
    try:
        timeutil.freeze(_at(start, 9, 31))
        L.start_run(100000, _at(start, 9, 31))

        # Wheel 1: an at-the-money put that finishes in the money (assigned) ...
        e1 = e1 or _friday(start, 2)
        trade(_at(start, 9, 40), action="sell_to_open", type="put", expiry=e1.isoformat(), strike=k1, qty=1,
              tags=["#wheel"], note="Happy to own TQQQ here.")
        # ... beside a weekly put far below the market that expires worthless.
        w1 = _friday(start, 0) if _friday(start, 0) > start else _friday(start, 1)
        kw = float(math.floor(min(P(start), P(w1)) * 0.94))
        trade(_at(start + dt.timedelta(days=1), 11, 15), action="sell_to_open", type="put", expiry=w1.isoformat(),
              strike=kw, qty=2, tags=["#weekly"])
        for e in sorted({w1, e1}):
            settle(e)

        # Covered call at or above cost, on an expiration where TQQQ finishes above it (called away).
        c_open = marketcal.next_trading_day(e1)
        e2 = e2 or _friday(c_open, 2)
        k2 = float(max(k1 + 1, math.floor(min(P(e2) - 0.3, P(c_open) * 1.06))))
        if L.free_shares() >= 100:
            trade(_at(c_open, 9, 45), action="sell_to_open", type="call", expiry=e2.isoformat(), strike=k2, qty=1,
                  tags=["#wheel"], note="Covered call on the assigned shares, above cost.")
        # A weekly put closed early for most of its premium.
        e3 = _friday(c_open, 1)
        k3 = float(math.floor(P(c_open) * 0.93))
        trade(_at(c_open, 13, 5), action="sell_to_open", type="put", expiry=e3.isoformat(), strike=k3, qty=1,
              tags=["#weekly"], note="Selling a quiet week.")
        close_day = marketcal.next_trading_day(marketcal.next_trading_day(c_open))
        pid = next(p["id"] for p in L.positions() if p["strike"] == k3 and p["expiry"] == e3.isoformat())
        bt = _price(P(close_day), k3, _at(close_day, 10, 20), e3, False)
        trade(_at(close_day, 10, 20), action="buy_to_close", position_id=pid, qty=1, px=bt,
              close_note="Kept most of the premium; no reason to hold to Friday.")
        for e in sorted({e3, e2}):
            settle(e)

        # Wheel 2, still running: a put assigned recently, then an open covered call.
        p2 = marketcal.next_trading_day(e2)
        k4 = float(round(P(p2)))
        cands = [e for e in (_friday(p2, w) for w in (0, 1, 2)) if p2 < e < today]
        e4 = next((e for e in cands if P(e) < k4 - 0.3), cands[-1] if cands else today)
        if e4 < today and L.shares() == 0:
            trade(_at(p2, 9, 50), action="sell_to_open", type="put", expiry=e4.isoformat(), strike=k4, qty=1,
                  tags=["#wheel"], note="Back in for wheel two.")
            settle(e4)
        if L.free_shares() >= 100:
            cc = marketcal.next_trading_day(e4) if e4 < today else marketcal.prev_trading_day(today)
            cc = min(cc, marketcal.prev_trading_day(today))
            e5 = _friday(today, 2)
            k5 = float(max(k4, math.ceil(P(cc) * 1.05)))
            trade(_at(cc, 10, 10), action="sell_to_open", type="call", expiry=e5.isoformat(), strike=k5,
                  qty=1, tags=["#wheel"], note="Call a bit above cost while the shares recover.")

        # An open put expiring soon, near the money (shows up in the alerts).
        last = marketcal.prev_trading_day(today)
        e6 = _friday(today, 0) if _friday(today, 0) > today else _friday(today, 1)
        k6 = float(math.floor(P(last) * 0.97))
        trade(_at(last, 14, 20), action="sell_to_open", type="put", expiry=e6.isoformat(), strike=k6, qty=2,
              tags=["#weekly", "#near-money"], note="Two contracts into a soft day.")
    finally:
        timeutil.freeze(was)
        D.close()
