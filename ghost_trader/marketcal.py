"""Built-in NYSE calendar: holidays, early closes, market hours.

Holidays follow NYSE rule 7.2 (Saturday holidays observed Friday, Sunday holidays observed Monday,
except New Year's Day on a Saturday, which is not observed). One-off closures are listed in
SPECIAL_CLOSURES and kept current through app updates.
"""
import datetime as dt
from functools import lru_cache

from .timeutil import ET, CT

D = dt.date

SPECIAL_CLOSURES = {
    D(2012, 10, 29): "Hurricane Sandy",
    D(2012, 10, 30): "Hurricane Sandy",
    D(2018, 12, 5): "National Day of Mourning (George H.W. Bush)",
    D(2025, 1, 9): "National Day of Mourning (Jimmy Carter)",
}

OPEN_ET = dt.time(9, 30)
CLOSE_ET = dt.time(16, 0)
EARLY_CLOSE_ET = dt.time(13, 0)


def _nth_weekday(year, month, weekday, n):
    d = D(year, month, 1)
    d += dt.timedelta(days=(weekday - d.weekday()) % 7)
    return d + dt.timedelta(weeks=n - 1)


def _last_weekday(year, month, weekday):
    nxt = D(year + (month == 12), month % 12 + 1, 1)
    d = nxt - dt.timedelta(days=1)
    return d - dt.timedelta(days=(d.weekday() - weekday) % 7)


def _easter(year):
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    ll = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ll) // 451
    month = (h + ll - 7 * m + 114) // 31
    day = (h + ll - 7 * m + 114) % 31 + 1
    return D(year, month, day)


def _observed(d):
    if d.weekday() == 5:
        return d - dt.timedelta(days=1)
    if d.weekday() == 6:
        return d + dt.timedelta(days=1)
    return d


@lru_cache(maxsize=None)
def holidays(year):
    """{date: name} of full-day NYSE closures in a year."""
    h = {}
    ny = D(year, 1, 1)
    if ny.weekday() == 6:
        h[D(year, 1, 2)] = "New Year's Day (observed)"
    elif ny.weekday() != 5:
        h[ny] = "New Year's Day"
    h[_nth_weekday(year, 1, 0, 3)] = "Martin Luther King Jr. Day"
    h[_nth_weekday(year, 2, 0, 3)] = "Washington's Birthday"
    h[_easter(year) - dt.timedelta(days=2)] = "Good Friday"
    h[_last_weekday(year, 5, 0)] = "Memorial Day"
    if year >= 2022:
        h[_observed(D(year, 6, 19))] = "Juneteenth"
    h[_observed(D(year, 7, 4))] = "Independence Day"
    h[_nth_weekday(year, 9, 0, 1)] = "Labor Day"
    h[_nth_weekday(year, 11, 3, 4)] = "Thanksgiving Day"
    h[_observed(D(year, 12, 25))] = "Christmas Day"
    # New Year's of next year falling on a Saturday is not observed on Dec 31 (rule 7.2).
    for d, name in SPECIAL_CLOSURES.items():
        if d.year == year:
            h[d] = name
    return h


def holiday_name(d):
    return holidays(d.year).get(d)


def is_trading_day(d):
    return d.weekday() < 5 and d not in holidays(d.year)


@lru_cache(maxsize=None)
def early_closes(year):
    out = {}
    j3 = D(year, 7, 3)
    if j3.weekday() <= 3 and is_trading_day(j3):
        out[j3] = "Day before Independence Day"
    out[_nth_weekday(year, 11, 3, 4) + dt.timedelta(days=1)] = "Day after Thanksgiving"
    c24 = D(year, 12, 24)
    if c24.weekday() <= 3 and is_trading_day(c24):
        out[c24] = "Christmas Eve"
    return out


def close_time_et(d):
    return EARLY_CLOSE_ET if d in early_closes(d.year) else CLOSE_ET


def prev_trading_day(d, inclusive=False):
    if not inclusive:
        d -= dt.timedelta(days=1)
    while not is_trading_day(d):
        d -= dt.timedelta(days=1)
    return d


def next_trading_day(d, inclusive=False):
    if not inclusive:
        d += dt.timedelta(days=1)
    while not is_trading_day(d):
        d += dt.timedelta(days=1)
    return d


def market_status(ts):
    """('open'|'closed', label) for an aware datetime."""
    e = ts.astimezone(ET)
    d = e.date()
    if not is_trading_day(d):
        why = holiday_name(d) or "weekend"
        return "closed", f"Market closed ({why})" if holiday_name(d) else "Market closed"
    if OPEN_ET <= e.time() < close_time_et(d):
        return "open", "Market open" + (" · early close 12:00 PM CT" if d in early_closes(d.year) else "")
    return "closed", "Market closed"


def is_open(ts):
    return market_status(ts)[0] == "open"


def last_close_dt(ts):
    """Aware datetime of the most recent regular-session close at or before ts."""
    e = ts.astimezone(ET)
    d = e.date()
    if is_trading_day(d) and e.time() >= close_time_et(d):
        day = d
    else:
        day = prev_trading_day(d)
    return dt.datetime.combine(day, close_time_et(day), ET)


def interest_pay_date(year, month):
    """The 15th, or the previous business day if the 15th is a weekend or market holiday."""
    return prev_trading_day(D(year, month, 15), inclusive=True)


def pay_dates_between(start, end):
    """Pay dates p with start < p <= end."""
    out = []
    y, m = start.year, start.month
    while D(y, m, 1) <= end:
        p = interest_pay_date(y, m)
        if start < p <= end:
            out.append(p)
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def next_pay_date(after):
    """First pay date strictly after `after`... or on it if it is one and not yet paid (caller decides)."""
    y, m = after.year, after.month
    for _ in range(3):
        p = interest_pay_date(y, m)
        if p > after:
            return p
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return None


def expiration_settle_ready(expiry, ts):
    """Expirations are processed at the first startup after 5 PM Central on expiration day."""
    c = ts.astimezone(CT)
    if c.date() > expiry:
        return True
    return c.date() == expiry and c.time() >= dt.time(17, 0)
