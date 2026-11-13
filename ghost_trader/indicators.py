"""Market indicators for the Indicators tab and the readings stamped on trades.

- Stochastic oscillator on TQQQ daily bars: 14,3,3 (slow: %K smoothed 3, %D = 3-day average of %K) and raw
  %K over 30, 60 and 180 days.
- VIX (CBOE Volatility Index) daily closes.
- CNN Fear & Greed index (no official feed: read from the JSON CNN's own page uses; may break without notice).

Each source is fetched on demand, cached in memory, and fails on its own without affecting the others.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import threading
import time
import urllib.request

from . import SYMBOL, timeutil

log = logging.getLogger(__name__)

LOOKBACKS = (14, 30, 60, 180)
SLOW = {14: (3, 3)}          # lookback -> (%K smoothing, %D period); others are raw %K
TTL = 15 * 60                 # seconds before a refresh
HISTORY_DAYS = 2 * 365 + 300  # 2 years shown + room for the 180-day lookback
VIX = "^VIX"

CNN_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata/{start}"
CNN_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:132.0) Gecko/20100101 Firefox/132.0",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://edition.cnn.com/",
    "Origin": "https://edition.cnn.com",
}


# ---------------------------------------------------------------- math
def sma(vals, n):
    """Simple moving average; None until n values are available (Nones in the window give None)."""
    out = []
    for i in range(len(vals)):
        w = vals[max(0, i - n + 1):i + 1]
        out.append(sum(w) / n if len(w) == n and None not in w else None)
    return out


def raw_k(bars, n):
    """%K = 100 × (close − lowest low) ÷ (highest high − lowest low) over the last n bars."""
    out = []
    for i in range(len(bars)):
        if i + 1 < n:
            out.append(None)
            continue
        w = bars[i + 1 - n:i + 1]
        hh = max(b["high"] for b in w)
        ll = min(b["low"] for b in w)
        out.append(100.0 * (bars[i]["close"] - ll) / (hh - ll) if hh > ll else 50.0)
    return out


def stochastic(bars, n):
    """Returns (k, d): for 14 the slow stochastic (%K smoothed 3, %D 3); for other lookbacks raw %K and d=None."""
    k = raw_k(bars, n)
    if n in SLOW:
        ks, dp = SLOW[n]
        k = sma(k, ks)
        return k, sma(k, dp)
    return k, None


def fg_rating(score):
    """CNN's bands: 0–24 extreme fear, 25–44 fear, 45–55 neutral, 56–75 greed, 76–100 extreme greed."""
    if score is None:
        return None
    s = round(score)
    return ("extreme fear" if s < 25 else "fear" if s < 45 else "neutral" if s <= 55 else "greed" if s <= 75
            else "extreme greed")


def parse_cnn(j):
    """CNN graphdata JSON -> {score, rating, asof, previous_close, week_ago, month_ago, year_ago, history{day: score}}."""
    cur = j.get("fear_and_greed") or {}
    if cur.get("score") is None:
        raise ValueError("no current score in CNN's data")
    hist = {}
    for p in (j.get("fear_and_greed_historical") or {}).get("data") or []:
        try:
            d = dt.datetime.fromtimestamp(float(p["x"]) / 1000, dt.timezone.utc).astimezone(timeutil.ET).date()
            hist[d.isoformat()] = float(p["y"])
        except (KeyError, TypeError, ValueError):
            continue

    def f(k):
        v = cur.get(k)
        return float(v) if isinstance(v, (int, float)) else None

    return {"score": float(cur["score"]), "rating": str(cur.get("rating") or fg_rating(cur["score"])).lower(),
            "asof": cur.get("timestamp"), "previous_close": f("previous_close"), "week_ago": f("previous_1_week"),
            "month_ago": f("previous_1_month"), "year_ago": f("previous_1_year"), "history": hist}


def fetch_cnn(start, timeout=10):
    req = urllib.request.Request(CNN_URL.format(start=start.isoformat()), headers=CNN_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 - fixed https URL
        return parse_cnn(json.loads(r.read().decode("utf-8")))


# ---------------------------------------------------------------- data + cache
class Indicators:
    def __init__(self, provider):
        self.provider = provider
        self.lock = threading.Lock()
        self.warming = None
        self.data = {}   # source -> {"ok": bool, "value": ..., "error": str, "at": epoch}
        self.on_refresh = None  # called (no args) after a refresh that got new data

    def _fresh(self, src, ttl=TTL):
        e = self.data.get(src)
        return bool(e and e["ok"] and time.time() - e["at"] < ttl)

    def stale(self, ttl=TTL):
        return not all(self._fresh(s, ttl) for s in ("tqqq", "vix", "fg"))

    def refresh(self, force=False):
        """Fetch any source that's stale (or all, with force). Never raises."""
        with self.lock:
            today = timeutil.today_ct()
            start = today - dt.timedelta(days=HISTORY_DAYS)
            jobs = {"tqqq": lambda: self.provider.daily_bars(SYMBOL, start, today),
                    "vix": lambda: self.provider.daily_closes(start, today, symbol=VIX),
                    "fg": lambda: self.provider.fear_greed(today - dt.timedelta(days=2 * 365 + 10))}
            for src, fn in jobs.items():
                if not force and self._fresh(src):
                    continue
                try:
                    v = fn()
                    if not v:
                        raise ValueError("no data returned")
                    self.data[src] = {"ok": True, "value": v, "error": None, "at": time.time()}
                except Exception as e:  # noqa: BLE001
                    log.warning("indicator %s failed: %s", src, e)
                    prev = self.data.get(src) or {}
                    # keep the last good value (marked failed) so the tab still shows something
                    self.data[src] = {"ok": False, "value": prev.get("value"), "error": str(e) or e.__class__.__name__,
                                      "at": prev.get("at", 0)}
            got_new = any(self.data.get(x, {}).get("ok") for x in jobs)
        if got_new and self.on_refresh:
            try:
                self.on_refresh()
            except Exception:  # noqa: BLE001
                log.exception("on_refresh")

    def warm(self):
        """Refresh in the background if stale; returns immediately."""
        if not self.stale() or (self.warming and self.warming.is_alive()):
            return
        self.warming = threading.Thread(target=self.refresh, daemon=True, name="indicators")
        self.warming.start()

    def wait_warm(self, timeout):
        t = self.warming
        if t and t.is_alive():
            t.join(timeout)

    # ------------------------------------------------------------ views
    def _series(self):
        bars = sorted((self.data.get("tqqq") or {}).get("value") or [], key=lambda b: b["day"])
        days = [b["day"] for b in bars]
        stoch = {}
        for n in LOOKBACKS:
            k, d = stochastic(bars, n)
            stoch[str(n)] = {"k": k, "d": d}
        vix_map = (self.data.get("vix") or {}).get("value") or {}
        fg = (self.data.get("fg") or {}).get("value") or {}
        fg_map = fg.get("history") or {}
        if fg.get("score") is not None and days and days[-1] not in fg_map and fg.get("asof"):
            # CNN's history may lag today's reading; place the current score on the latest day it's from
            try:
                fd = timeutil.parse(fg["asof"]).astimezone(timeutil.ET).date().isoformat()
                if fd == days[-1]:
                    fg_map = {**fg_map, fd: fg["score"]}
            except Exception:  # noqa: BLE001
                pass
        return bars, days, stoch, vix_map, fg, fg_map

    def snapshot(self):
        """Current readings for stamping on a trade, or None if nothing is available."""
        bars, days, stoch, vix_map, fg, _ = self._series()
        if not days and not vix_map and fg.get("score") is None:
            return None

        def last(v):
            return round(v[-1], 1) if v and v[-1] is not None else None

        out = {"asof": timeutil.iso(), "bars_through": days[-1] if days else None}
        for n in LOOKBACKS:
            out[f"stoch{n}_k"] = last(stoch[str(n)]["k"])
            if stoch[str(n)]["d"] is not None:
                out[f"stoch{n}_d"] = last(stoch[str(n)]["d"])
        vd = sorted(vix_map)
        out["vix"] = round(vix_map[vd[-1]], 2) if vd else None
        out["fg"] = round(fg["score"], 1) if fg.get("score") is not None else None
        out["fg_rating"] = fg.get("rating")
        return out if any(v is not None for k, v in out.items() if k not in ("asof", "bars_through")) else None

    def view(self, months):
        """Everything the Indicators tab draws, trimmed to the last `months` months."""
        bars, days, stoch, vix_map, fg, fg_map = self._series()
        cut = (timeutil.today_ct() - dt.timedelta(days=int(months * 30.44))).isoformat()
        i0 = next((i for i, d in enumerate(days) if d >= cut), len(days))
        sl = slice(i0, None)
        r = lambda v: [None if x is None else round(x, 2) for x in v]  # noqa: E731
        vd = sorted(vix_map)
        vix_now = vix_map[vd[-1]] if vd else None
        vix_prev = vix_map[vd[-2]] if len(vd) > 1 else None
        yr = [vix_map[d] for d in vd if d >= (timeutil.today_ct() - dt.timedelta(days=365)).isoformat()]
        status = {s: {"ok": (self.data.get(s) or {}).get("ok", False), "error": (self.data.get(s) or {}).get("error"),
                      "at": timeutil.iso(dt.datetime.fromtimestamp(self.data[s]["at"], dt.timezone.utc))
                      if (self.data.get(s) or {}).get("at") else None} for s in ("tqqq", "vix", "fg")}
        cur = {}
        for n in LOOKBACKS:
            k, d = stoch[str(n)]["k"], stoch[str(n)]["d"]
            cur[str(n)] = {"k": k[-1] if k else None, "d": d[-1] if d else None,
                           "k_prev": k[-2] if len(k) > 1 else None}
        return {
            "days": days[sl], "close": [b["close"] for b in bars][sl],
            "stoch": {n: {"k": r(v["k"][sl]), "d": r(v["d"][sl]) if v["d"] is not None else None}
                      for n, v in stoch.items()},
            "vix": [vix_map.get(d) for d in days[sl]], "fg": [fg_map.get(d) for d in days[sl]],
            "now": {"price": bars[-1]["close"] if bars else None, "prev": bars[-2]["close"] if len(bars) > 1 else None,
                    "bars_through": days[-1] if days else None, "stoch": cur,
                    "vix": vix_now, "vix_prev": vix_prev, "vix_hi": max(yr) if yr else None,
                    "vix_lo": min(yr) if yr else None,
                    "fg": {k: v for k, v in fg.items() if k != "history"} if fg else None},
            "status": status, "lookbacks": list(LOOKBACKS), "slow": {str(k): list(v) for k, v in SLOW.items()},
        }
