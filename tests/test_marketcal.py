import datetime as dt

from ghost_trader import marketcal as mc
from ghost_trader.timeutil import CT, ET

D = dt.date


def test_2026_holidays():
    h = mc.holidays(2026)
    assert D(2026, 1, 1) in h and D(2026, 1, 19) in h and D(2026, 2, 16) in h
    assert D(2026, 4, 3) in h          # Good Friday
    assert D(2026, 5, 25) in h and D(2026, 6, 19) in h
    assert D(2026, 7, 3) in h          # July 4 is a Saturday -> observed Friday
    assert D(2026, 9, 7) in h and D(2026, 11, 26) in h and D(2026, 12, 25) in h
    assert len(h) == 10


def test_new_year_on_saturday_not_observed():
    # Jan 1 2022 was a Saturday: no holiday on Dec 31 2021 or Jan 3 2022
    assert mc.is_trading_day(D(2021, 12, 31))
    assert mc.is_trading_day(D(2022, 1, 3))


def test_special_closure_and_juneteenth_start():
    assert not mc.is_trading_day(D(2025, 1, 9))
    assert mc.is_trading_day(D(2021, 6, 18))   # Juneteenth only from 2022


def test_early_closes():
    assert D(2026, 11, 27) in mc.early_closes(2026)      # day after Thanksgiving
    assert D(2026, 12, 24) in mc.early_closes(2026)      # Thursday
    assert D(2026, 7, 2) not in mc.early_closes(2026)    # July 3 is the holiday that year
    assert D(2025, 7, 3) in mc.early_closes(2025)
    assert mc.close_time_et(D(2026, 11, 27)) == dt.time(13, 0)


def test_interest_pay_dates():
    assert mc.interest_pay_date(2026, 11) == D(2026, 11, 13)   # 15th is a Sunday
    assert mc.interest_pay_date(2026, 2) == D(2026, 2, 13)     # 15th Sunday, 16th Presidents Day -> back to Fri
    assert mc.interest_pay_date(2026, 10) == D(2026, 10, 15)
    assert mc.pay_dates_between(D(2026, 10, 1), D(2026, 11, 20)) == [D(2026, 10, 15), D(2026, 11, 13)]
    assert mc.next_pay_date(D(2026, 11, 13)) == D(2026, 12, 15)


def test_market_status():
    assert mc.market_status(dt.datetime(2026, 11, 12, 10, 0, tzinfo=ET))[0] == "open"
    assert mc.market_status(dt.datetime(2026, 11, 12, 16, 0, tzinfo=ET))[0] == "closed"
    assert mc.market_status(dt.datetime(2026, 11, 26, 11, 0, tzinfo=ET))[0] == "closed"
    assert mc.market_status(dt.datetime(2026, 11, 27, 13, 30, tzinfo=ET))[0] == "closed"   # early close


def test_last_close():
    sat = dt.datetime(2026, 11, 14, 12, 0, tzinfo=CT)
    assert mc.last_close_dt(sat) == dt.datetime(2026, 11, 13, 16, 0, tzinfo=ET)


def test_expiration_ready_after_5pm_central():
    exp = D(2026, 11, 20)
    assert not mc.expiration_settle_ready(exp, dt.datetime(2026, 11, 20, 16, 59, tzinfo=CT))
    assert mc.expiration_settle_ready(exp, dt.datetime(2026, 11, 20, 17, 0, tzinfo=CT))
    assert mc.expiration_settle_ready(exp, dt.datetime(2026, 11, 23, 8, 0, tzinfo=CT))
