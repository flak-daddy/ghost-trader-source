"""Build a demo ledger with a few weeks of history (used by the UI tests; also handy for poking around:
`GHOST_TRADER_HOME=/tmp/gt python -m tests.seed && GHOST_TRADER_HOME=/tmp/gt python -m ghost_trader --demo`)."""
import datetime as dt

from ghost_trader import config, db as dbm, timeutil
from ghost_trader.ledger import Ledger


def at(y, m, d, hh=10, mm=0):
    return dt.datetime(y, m, d, hh, mm, tzinfo=timeutil.CT)


def seed():
    D = dbm.DB(config.db_path())
    S = config.Settings()
    L = Ledger(D, S)
    day = dt.date(2026, 9, 25)
    while day <= timeutil.today_ct():
        D.x("INSERT OR REPLACE INTO rates(day,rate,source) VALUES(?,?,?)", (day.isoformat(), 4.2, "^IRX via Yahoo"))
        day += dt.timedelta(days=1)

    def trade(ts, **o):
        timeutil.freeze(ts)
        q = {"bid": round(o["price"] - .03, 2), "ask": round(o["price"] + .03, 2)}
        return L.place(o, q, 57.0, ts)

    timeutil.freeze(at(2026, 10, 1, 9, 31))
    L.start_run(100000, at(2026, 10, 1, 9, 31))
    trade(at(2026, 10, 1, 9, 35), action="sell_to_open", type="put", expiry="2026-10-16", strike=58, qty=1, price=2.10,
          tags=["#wheel"], note="Happy to own TQQQ at 58.")
    timeutil.freeze(at(2026, 10, 16, 17, 5))
    L.catch_up_interest(dt.date(2026, 10, 16), lambda d: 4.2)
    L.settle_expiration(dt.date(2026, 10, 16), 57.31, at(2026, 10, 16, 17, 5))
    trade(at(2026, 10, 20, 9, 40), action="sell_to_open", type="call", expiry="2026-11-20", strike=60, qty=1, price=0.95,
          tags=["#wheel"], note="Covered call on assigned shares, strike above cost.")
    trade(at(2026, 10, 22, 13, 20), action="sell_to_open", type="put", expiry="2026-11-06", strike=50, qty=1, price=0.80,
          tags=["#weekly"])
    trade(at(2026, 11, 4, 9, 48), action="sell_to_open", type="put", expiry="2026-11-13", strike=54, qty=1, price=1.10,
          tags=["#weekly"])
    trade(at(2026, 11, 6, 10, 5), action="sell_to_open", type="put", expiry="2026-11-20", strike=55, qty=2, price=1.65,
          tags=["#wheel", "#near-money"], note="Selling into the CPI dip; fine owning 200 more at 55.")
    timeutil.freeze(at(2026, 11, 6, 17, 5))
    L.catch_up_interest(dt.date(2026, 11, 6), lambda d: 4.2)
    L.settle_expiration(dt.date(2026, 11, 6), 57.20, at(2026, 11, 6, 17, 5))
    timeutil.freeze(None)
    D.close()


if __name__ == "__main__":
    seed()
    print("seeded", config.db_path())
