"""Clock and time-display helpers. Everything is shown in Central time, with Eastern in parentheses
outside the ticket/confirm screens."""
import datetime as dt
from zoneinfo import ZoneInfo

CT = ZoneInfo("America/Chicago")
ET = ZoneInfo("America/New_York")

# Tests (and --demo) can pin "now" by setting this to an aware datetime.
_frozen = None


def freeze(when):
    """Pin the clock (aware datetime or None to unpin)."""
    global _frozen
    _frozen = when


def now():
    return _frozen if _frozen is not None else dt.datetime.now(dt.timezone.utc)


def now_ct():
    return now().astimezone(CT)


def today_ct():
    return now_ct().date()


def iso(ts=None):
    return (ts or now()).astimezone(dt.timezone.utc).isoformat(timespec="seconds")


def parse(ts):
    d = dt.datetime.fromisoformat(ts)
    return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)


def _clock(t):
    return t.strftime("%I:%M %p").lstrip("0")


def fmt_ct(ts, with_et=True, with_date=False):
    """'3:15 PM CT (4:15 PM ET)' or with date 'Nov 11, 3:15 PM CT (4:15 PM ET)'."""
    if isinstance(ts, str):
        ts = parse(ts)
    c, e = ts.astimezone(CT), ts.astimezone(ET)
    s = (c.strftime("%b ") + str(c.day) + ", " if with_date else "") + _clock(c) + " CT"
    return s + (f" ({_clock(e)} ET)" if with_et else "")


def fmt_date(d):
    if isinstance(d, str):
        d = dt.date.fromisoformat(d[:10])
    return d.strftime("%b ") + str(d.day)


def fmt_exp(d):
    """'Fri Nov 20' (adds 'YY when not the current year)."""
    if isinstance(d, str):
        d = dt.date.fromisoformat(d)
    s = d.strftime("%a %b %d")
    if d.year != today_ct().year:
        s += d.strftime(" '%y")
    return s
