"""Built-in schedule of market-moving releases, from the official calendars (kept current through app updates,
like the holiday calendar):

- FOMC rate decisions: https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm  (statement 2:00 PM ET on
  the second day; 2027 dates are tentative until confirmed at the meeting before)
- CPI: https://www.bls.gov/schedule/news_release/cpi.htm  (8:30 AM ET)
- Employment Situation (jobs report): https://www.bls.gov/schedule/news_release/empsit.htm  (8:30 AM ET)

Checked 2026-11-12. TQQQ ex-dividend dates come from Yahoo at run time, not from this file.
"""
import datetime as dt

D = dt.date

# FOMC: the decision (second) day of each meeting. SEP = Summary of Economic Projections ("dot plot").
FOMC = {
    D(2026, 1, 28): False, D(2026, 3, 18): True, D(2026, 4, 29): False, D(2026, 6, 17): True,
    D(2026, 7, 29): False, D(2026, 9, 16): True, D(2026, 10, 28): False, D(2026, 12, 9): True,
    D(2027, 1, 27): False, D(2027, 3, 17): True, D(2027, 4, 28): False, D(2027, 6, 9): True,
    D(2027, 7, 28): False, D(2027, 9, 15): True, D(2027, 10, 27): False, D(2027, 12, 8): True,
}

CPI = [
    D(2026, 1, 13), D(2026, 2, 13), D(2026, 3, 11), D(2026, 4, 10), D(2026, 5, 12), D(2026, 6, 10),
    D(2026, 7, 14), D(2026, 8, 12), D(2026, 9, 11), D(2026, 10, 14), D(2026, 11, 10), D(2026, 12, 10),
    D(2027, 1, 13), D(2027, 2, 11), D(2027, 3, 10), D(2027, 4, 13), D(2027, 5, 12), D(2027, 6, 10),
    D(2027, 7, 14), D(2027, 8, 11), D(2027, 9, 14), D(2027, 10, 14), D(2027, 11, 10), D(2027, 12, 10),
]

JOBS = [
    D(2026, 1, 9), D(2026, 2, 11), D(2026, 3, 6), D(2026, 4, 3), D(2026, 5, 8), D(2026, 6, 5),
    D(2026, 7, 2), D(2026, 8, 7), D(2026, 9, 4), D(2026, 10, 2), D(2026, 11, 6), D(2026, 12, 4),
    D(2027, 1, 8), D(2027, 2, 5), D(2027, 3, 5), D(2027, 4, 2), D(2027, 5, 7), D(2027, 6, 4),
    D(2027, 7, 2), D(2027, 8, 6), D(2027, 9, 3), D(2027, 10, 8), D(2027, 11, 5), D(2027, 12, 3),
]

COVERED_THROUGH = D(2027, 12, 31)


def _month_name(d):
    return d.strftime("%B")


def events_between(start, end):
    """[{day, kind, short, name}] for scheduled releases with start <= day <= end. Times are Central."""
    out = []
    for d, sep in FOMC.items():
        if start <= d <= end:
            out.append({"day": d, "kind": "fomc", "short": "Fed 1:00 PM",
                        "name": "Fed rate decision · statement 1:00 PM CT, press conference 1:30 PM CT"
                        + (" · with economic projections (dot plot)" if sep else "")
                        + (" · tentative date" if d.year >= 2027 else "")})
    for d in CPI:
        if start <= d <= end:
            ref = (d.replace(day=1) - dt.timedelta(days=1))
            out.append({"day": d, "kind": "cpi", "short": "CPI 7:30 AM",
                        "name": f"CPI inflation report for {_month_name(ref)} · 7:30 AM CT, before the open"})
    for d in JOBS:
        if start <= d <= end:
            ref = (d.replace(day=1) - dt.timedelta(days=1))
            out.append({"day": d, "kind": "jobs", "short": "Jobs 7:30 AM",
                        "name": f"Jobs report (Employment Situation) for {_month_name(ref)} · 7:30 AM CT, before the open"})
    order = {"cpi": 0, "jobs": 1, "fomc": 2}
    return sorted(out, key=lambda e: (e["day"], order[e["kind"]]))
