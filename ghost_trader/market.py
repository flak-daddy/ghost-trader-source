"""Market data: option chains, the underlying price, daily closes, dividends/splits (Yahoo via yfinance, ~15 min
delayed), and the interest rate (Alpha Vantage 3-month Treasury -> ^IRX via Yahoo -> manual).

A DemoProvider produces synthetic but consistent data with no network, for `--demo` and the tests.
"""
import datetime as dt
import json
import logging
import math
import random
import threading
import time
import urllib.parse
import urllib.request

from . import SYMBOL, marketcal, timeutil

log = logging.getLogger("ghost_trader.market")


class DataError(Exception):
    pass


# ---------------------------------------------------------------- pricing helpers
def ncdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bs(S, K, T, r, sigma, call):
    if T <= 0 or sigma <= 0 or S <= 0:
        return (max(0.0, S - K) if call else max(0.0, K - S)), (1.0 if (call and S > K) else (-1.0 if (not call and S < K) else 0.0))
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    if call:
        return S * ncdf(d1) - K * math.exp(-r * T) * ncdf(d2), ncdf(d1)
    return K * math.exp(-r * T) * ncdf(-d2) - S * ncdf(-d1), ncdf(d1) - 1.0


def year_frac(expiry, now=None):
    now = now or timeutil.now()
    close = dt.datetime.combine(expiry, marketcal.close_time_et(expiry), timeutil.ET)
    return max((close - now).total_seconds(), 0) / (365 * 86400)


def occ(symbol, expiry, type_, strike):
    e = expiry if isinstance(expiry, dt.date) else dt.date.fromisoformat(expiry)
    return f"{symbol.upper()}{e.strftime('%y%m%d')}{'C' if type_ == 'call' else 'P'}{int(round(strike * 1000)):08d}"


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def mid_of(bid, ask, last=None):
    if bid and ask and ask >= bid:
        return round((bid + ask) / 2 + 1e-9, 2)
    if ask and not bid:
        return round(ask / 2 + 1e-9, 2)
    return last


# ---------------------------------------------------------------- Yahoo
class YahooProvider:
    name = "Yahoo Finance (~15 min delayed)"
    demo = False

    def __init__(self, symbol=SYMBOL):
        try:
            import yfinance as yf  # noqa: F401
        except ImportError as e:  # pragma: no cover - depends on install
            raise DataError("The yfinance package isn't installed. Run ./install.sh again.") from e
        self.yf = yf
        self.symbol = symbol

    def _t(self, sym=None):
        return self.yf.Ticker(sym or self.symbol)

    def underlying(self):
        fi = self._t().fast_info
        price = _num(fi["last_price"])
        prev = _num(fi["previous_close"])
        if not price:
            raise DataError(f"Yahoo returned no price for {self.symbol}.")
        return {"price": price, "prev_close": prev, "bid": None, "ask": None, "asof": timeutil.iso()}

    def stock_bidask(self):
        """Share bid/ask (slower call; only used when a share ticket is open)."""
        info = self._t().info
        return _num(info.get("bid")) or None, _num(info.get("ask")) or None

    def expirations(self):
        exps = list(self._t().options)
        if not exps:
            raise DataError(f"Yahoo returned no expirations for {self.symbol}.")
        return exps

    def chain(self, expiry):
        oc = self._t().option_chain(expiry)
        rows = []
        for df, typ in ((oc.calls, "call"), (oc.puts, "put")):
            for r in df.to_dict("records"):
                rows.append({
                    "type": typ, "strike": _num(r.get("strike")), "bid": _num(r.get("bid")) or 0.0,
                    "ask": _num(r.get("ask")) or 0.0, "last": _num(r.get("lastPrice")),
                    "iv": _num(r.get("impliedVolatility")), "volume": int(_num(r.get("volume")) or 0),
                    "oi": int(_num(r.get("openInterest")) or 0),
                })
        if not rows:
            raise DataError(f"Yahoo returned an empty chain for {expiry}.")
        return rows

    def daily_closes(self, start, end, symbol=None):
        h = self._t(symbol).history(start=start, end=end + dt.timedelta(days=1), auto_adjust=False)
        out = {}
        if h is not None and not h.empty:
            for idx, row in h.iterrows():
                c = _num(row.get("Close"))
                if c:
                    out[idx.date().isoformat()] = c
        return out

    def daily_bars(self, symbol, start, end):
        """Daily bars [{day, high, low, close}] (split-adjusted), including today's partial bar when trading."""
        h = self._t(symbol).history(start=start, end=end + dt.timedelta(days=1), auto_adjust=False)
        out = []
        if h is not None and not h.empty:
            for idx, row in h.iterrows():
                c, hi, lo = _num(row.get("Close")), _num(row.get("High")), _num(row.get("Low"))
                if c and hi and lo:
                    out.append({"day": idx.date().isoformat(), "high": hi, "low": lo, "close": c})
        return out

    def fear_greed(self, start):
        from .indicators import fetch_cnn
        return fetch_cnn(start)

    def earnings_dates(self, symbols):
        """{symbol: [upcoming earnings dates]} from Yahoo's calendar; symbols that fail are left out."""
        out = {}
        for sym in symbols:
            try:
                cal = self._t(sym).calendar or {}
                ds = cal.get("Earnings Date") or []
                ds = ds if isinstance(ds, (list, tuple)) else [ds]
                got = [d if isinstance(d, dt.date) else getattr(d, "date", lambda: None)() for d in ds]
                if got and got[0]:
                    out[sym] = [got[0]]   # Yahoo sometimes gives a range; the first date is the expected one
            except Exception as e:  # noqa: BLE001
                log.warning("earnings %s: %s", sym, e)
        return out

    def dividends(self):
        s = self._t().dividends
        return [(idx.date(), float(v)) for idx, v in s.items()] if s is not None else []

    def splits(self):
        s = self._t().splits
        return [(idx.date(), float(v)) for idx, v in s.items()] if s is not None else []

    def next_ex_dividend(self):
        try:
            cal = self._t().calendar or {}
            d = cal.get("Ex-Dividend Date")
            return d if isinstance(d, dt.date) else None
        except Exception:
            return None

    def irx(self, start, end):
        """^IRX daily closes (13-week T-bill discount rate, in percent)."""
        return self.daily_closes(start, end, symbol="^IRX")


# ---------------------------------------------------------------- Demo
class DemoProvider:
    """Synthetic data priced with Black-Scholes and a put skew. Deterministic per day."""
    name = "Demo data (synthetic, not real prices)"
    demo = True

    def __init__(self, symbol=SYMBOL, base=56.56, fail=()):
        self.symbol = symbol
        self.base = base
        self.fail = set(fail)  # names of methods that should raise (for tests)

    def _chk(self, name):
        if name in self.fail:
            raise DataError(f"Demo failure in {name}.")

    def _price_on(self, d):
        rnd = random.Random(d.toordinal())
        k = (d - dt.date(2026, 1, 1)).days
        return round(self.base * (1 + 0.06 * math.sin(k / 9.0) + 0.02 * math.sin(k / 2.3)) + rnd.uniform(-.3, .3), 2)

    def underlying(self):
        self._chk("underlying")
        today = timeutil.today_ct()
        p = self._price_on(today)
        prev = self._price_on(marketcal.prev_trading_day(today))
        return {"price": p, "prev_close": prev, "bid": round(p - .01, 2), "ask": round(p + .01, 2),
                "asof": timeutil.iso()}

    def expirations(self):
        self._chk("expirations")
        today = timeutil.today_ct()
        out = []
        d = today + dt.timedelta(days=(4 - today.weekday()) % 7)
        for i in range(8):
            f = d + dt.timedelta(weeks=i)
            out.append(f if marketcal.is_trading_day(f) else marketcal.prev_trading_day(f))
        for m in range(3, 6):
            y, mo = today.year + (today.month + m - 1) // 12, (today.month + m - 1) % 12 + 1
            third = marketcal._nth_weekday(y, mo, 4, 3)
            out.append(third)
        out.append(marketcal._nth_weekday(today.year + 1, 1, 4, 3))
        out.append(marketcal._nth_weekday(today.year + 2, 1, 4, 3))
        return sorted({x.isoformat() for x in out if x >= today})

    def chain(self, expiry):
        self._chk("chain")
        S = self.underlying()["price"]
        e = dt.date.fromisoformat(expiry)
        T = year_frac(e) + 0.25 / 365
        rows = []
        for k in range(math.floor(S * 0.5), math.ceil(S * 1.5) + 1):
            K = float(k)
            m = math.log(K / S)
            iv = max(0.35, 0.62 - 0.55 * m + 0.9 * m * m)
            for typ in ("call", "put"):
                px, _ = bs(S, K, T, 0.042, iv, typ == "call")
                spread = max(0.01, round(px * 0.04, 2))
                bid = max(0.0, round(px - spread / 2, 2))
                ask = round(px + spread / 2, 2) if px > 0.005 else (0.01 if px > 0.0005 else 0.0)
                vol = int(4000 * math.exp(-abs(m) * 9) * (1.4 if typ == "put" else 1.0)) if bid > 0 else 0
                rows.append({"type": typ, "strike": K, "bid": bid, "ask": ask, "last": round(px, 2), "iv": round(iv, 4),
                             "volume": vol, "oi": 0})
        return rows

    def daily_closes(self, start, end, symbol=None):
        self._chk("daily_closes")
        out, d = {}, start
        while d <= end:
            if marketcal.is_trading_day(d) and (d < timeutil.today_ct() or timeutil.now_ct().hour >= 15):
                if symbol == "^IRX":
                    out[d.isoformat()] = 4.2
                elif symbol == "^VIX":
                    k = (d - dt.date(2026, 1, 1)).days
                    out[d.isoformat()] = round(19 + 6 * math.sin(k / 17.0) + 2 * math.sin(k / 3.7), 2)
                else:
                    out[d.isoformat()] = self._price_on(d)
            d += dt.timedelta(days=1)
        return out

    def daily_bars(self, symbol, start, end):
        self._chk("daily_bars")
        out = []
        for day, c in sorted(self.daily_closes(start, end).items()):
            rnd = random.Random(dt.date.fromisoformat(day).toordinal() * 7)
            out.append({"day": day, "high": round(c * (1 + rnd.uniform(.005, .03)), 2),
                        "low": round(c * (1 - rnd.uniform(.005, .03)), 2), "close": c})
        return out

    def fear_greed(self, start):
        self._chk("fear_greed")
        from .indicators import fg_rating
        hist, d, today = {}, start, timeutil.today_ct()
        while d <= today:
            if marketcal.is_trading_day(d):
                k = (d - dt.date(2026, 1, 1)).days
                hist[d.isoformat()] = round(50 + 28 * math.sin(k / 23.0) + 8 * math.sin(k / 5.1), 1)
            d += dt.timedelta(days=1)
        days = sorted(hist)
        score = hist[days[-1]]
        back = lambda n: hist[days[-1 - n]] if len(days) > n else None  # noqa: E731
        return {"score": score, "rating": fg_rating(score), "asof": timeutil.iso(), "previous_close": back(1),
                "week_ago": back(5), "month_ago": back(21), "year_ago": back(252), "history": hist}

    def earnings_dates(self, symbols):
        self._chk("earnings_dates")
        today = timeutil.today_ct()
        out = {}
        for i, sym in enumerate(symbols):
            d = today + dt.timedelta(days=3 + i * 4)
            while not marketcal.is_trading_day(d):
                d += dt.timedelta(days=1)
            out[sym] = [d]
        return out

    def dividends(self):
        return []

    def splits(self):
        return []

    def next_ex_dividend(self):
        return None

    def stock_bidask(self):
        p = self.underlying()["price"]
        return round(p - .01, 2), round(p + .01, 2)

    def irx(self, start, end):
        self._chk("irx")
        return self.daily_closes(start, end, symbol="^IRX")


# ---------------------------------------------------------------- rates
class Rates:
    """Daily 3-month T-bill rates stored in the `rates` table; source order Alpha Vantage -> ^IRX -> manual."""

    AV_URL = "https://www.alphavantage.co/query"

    def __init__(self, db, settings, provider):
        self.db, self.settings, self.provider = db, settings, provider

    def _fetch_av(self, key):
        qs = urllib.parse.urlencode({"function": "TREASURY_YIELD", "interval": "daily", "maturity": "3month",
                                     "apikey": key})
        with urllib.request.urlopen(f"{self.AV_URL}?{qs}", timeout=20) as r:
            js = json.loads(r.read().decode())
        if "data" not in js:
            msg = js.get("Information") or js.get("Note") or js.get("Error Message") or "unexpected reply"
            raise DataError(f"Alpha Vantage: {msg}")
        out = {}
        for row in js["data"]:
            v = _num(row.get("value"))
            if v is not None:
                out[row["date"]] = v
        if not out:
            raise DataError("Alpha Vantage returned no rates.")
        return out

    def store(self, series, source):
        with self.db.tx():
            for day, rate in series.items():
                self.db.x("INSERT OR REPLACE INTO rates(day,rate,source) VALUES(?,?,?)", (day, rate, source))

    def refresh(self, since):
        """Fetch rates back to `since`. Returns (rate, day, source). Raises DataError if nothing works."""
        errs = []
        key = (self.settings.get("av_key") or "").strip()
        if key and not getattr(self.provider, "demo", False):
            for attempt in range(2):
                try:
                    s = self._fetch_av(key)
                    self.store({d: v for d, v in s.items() if d >= (since - dt.timedelta(days=10)).isoformat()},
                               "Alpha Vantage 3-mo Treasury")
                    return self.latest()
                except Exception as e:  # noqa: BLE001
                    errs.append(str(e).rstrip("."))
                    time.sleep(0.5 * (attempt + 1))
        elif not key:
            errs.append("no Alpha Vantage key set (Settings)")
        for attempt in range(2):
            try:
                s = self.provider.irx(since - dt.timedelta(days=10), timeutil.today_ct())
                if not s:
                    raise DataError("^IRX returned no data.")
                self.store(s, "^IRX via Yahoo")
                return self.latest()
            except Exception as e:  # noqa: BLE001
                errs.append(f"^IRX: {str(e).rstrip('.')}")
        man = self.settings.get("manual_rate")
        if man is not None:
            self.store({timeutil.today_ct().isoformat(): float(man)}, "manual")
            return self.latest()
        raise DataError(" · ".join(dict.fromkeys(errs)) + ".")

    def latest(self):
        r = self.db.one("SELECT day, rate, source FROM rates ORDER BY day DESC LIMIT 1")
        return (r["rate"], r["day"], r["source"]) if r else (None, None, None)

    def for_day(self, d):
        iso = d.isoformat() if not isinstance(d, str) else d
        r = self.db.one("SELECT rate FROM rates WHERE day<=? ORDER BY day DESC LIMIT 1", (iso,))
        if r:
            return r[0]
        r = self.db.one("SELECT rate FROM rates ORDER BY day LIMIT 1")
        if r:
            return r[0]
        man = self.settings.get("manual_rate")
        return float(man) if man is not None else 0.0


# ---------------------------------------------------------------- quotes
class Quotes:
    """Chains and the underlying with a short cache, plus a last-good-quote store so chains stay populated at
    night and when Yahoo hiccups."""

    CACHE_S = 60
    STALE_S = 15 * 60

    def __init__(self, db, provider, rates):
        self.db, self.p, self.rates = db, provider, rates
        self._lock = threading.Lock()
        self._chains = {}
        self._und = None
        self._exps = None

    # underlying ---------------------------------------------------------------------------------------
    def underlying(self, fresh=False):
        with self._lock:
            if self._und and not fresh and time.time() - self._und["_t"] < self.CACHE_S:
                return self._und
        try:
            u = self.p.underlying()
            u["_t"] = time.time()
            u["stale"] = False
            self.db.x("INSERT OR REPLACE INTO prices(symbol,day,close) VALUES(?,?,?)",
                      ("_last_" + SYMBOL, timeutil.today_ct().isoformat(), u["price"]))
            self.db.x("INSERT OR REPLACE INTO quotes(contract,symbol,bid,ask,last,asof) VALUES(?,?,?,?,?,?)",
                      ("_U_" + SYMBOL, SYMBOL, u.get("bid"), u.get("ask"), u["price"], u["asof"]))
            meta = json.dumps({"prev_close": u.get("prev_close")})
            self.db.x("INSERT OR REPLACE INTO quotes(contract,symbol,iv,last,asof,type) VALUES(?,?,?,?,?,?)",
                      ("_UP_" + SYMBOL, SYMBOL, None, u.get("prev_close"), u["asof"], meta))
        except Exception as e:  # noqa: BLE001
            log.warning("underlying failed: %s", e)
            r = self.db.one("SELECT * FROM quotes WHERE contract=?", ("_U_" + SYMBOL,))
            if not r:
                raise DataError(f"No price for {SYMBOL}: {e}")
            pr = self.db.one("SELECT last FROM quotes WHERE contract=?", ("_UP_" + SYMBOL,))
            u = {"price": r["last"], "bid": r["bid"], "ask": r["ask"], "asof": r["asof"],
                 "prev_close": pr[0] if pr else None, "_t": time.time(), "stale": True, "error": str(e)}
        with self._lock:
            self._und = u
        return u

    def set_manual_price(self, price):
        u = {"price": float(price), "bid": None, "ask": None, "prev_close": None, "asof": timeutil.iso(),
             "_t": time.time(), "stale": True, "manual": True}
        with self._lock:
            self._und = u
        self.db.x("INSERT OR REPLACE INTO quotes(contract,symbol,last,asof) VALUES(?,?,?,?)",
                  ("_U_" + SYMBOL, SYMBOL, float(price), u["asof"]))
        return u

    def expirations(self, fresh=False):
        if self._exps and not fresh:
            return self._exps
        today = timeutil.today_ct().isoformat()
        try:
            ex = [e for e in self.p.expirations() if e >= today]
            self.db.x("INSERT OR REPLACE INTO quotes(contract,symbol,type,asof) VALUES(?,?,?,?)",
                      ("_EXPS_" + SYMBOL, SYMBOL, json.dumps(ex), timeutil.iso()))
        except Exception as e:  # noqa: BLE001
            r = self.db.one("SELECT type FROM quotes WHERE contract=?", ("_EXPS_" + SYMBOL,))
            if not r:
                raise DataError(f"No expiration list: {e}")
            ex = [x for x in json.loads(r[0]) if x >= today]
        self._exps = ex
        return ex

    # chains -------------------------------------------------------------------------------------------
    def chain(self, expiry, fresh=False):
        """Returns {'rows': [...], 'asof', 'stale', 'error'} with mid and delta filled in."""
        with self._lock:
            c = self._chains.get(expiry)
            if c and not fresh and time.time() - c["_t"] < self.CACHE_S:
                return c
        err = None
        try:
            rows = self.p.chain(expiry)
            asof = timeutil.iso()
            stale = False
            with self.db.tx():
                for r in rows:
                    key = occ(SYMBOL, expiry, r["type"], r["strike"])
                    if r["bid"] or r["ask"]:
                        self.db.x("INSERT OR REPLACE INTO quotes(contract,symbol,expiry,type,strike,bid,ask,last,iv,asof)"
                                  " VALUES(?,?,?,?,?,?,?,?,?,?)",
                                  (key, SYMBOL, expiry, r["type"], r["strike"], r["bid"], r["ask"], r["last"], r["iv"], asof))
                    else:
                        # Yahoo often blanks bid/ask outside market hours: fall back to the last good quote.
                        g = self.db.one("SELECT bid, ask, iv, asof FROM quotes WHERE contract=?", (key,))
                        if g and (g["bid"] or g["ask"]):
                            r.update(bid=g["bid"] or 0.0, ask=g["ask"] or 0.0, iv=r.get("iv") or g["iv"], asof=g["asof"])
                            stale = True
        except Exception as e:  # noqa: BLE001
            log.warning("chain %s failed: %s", expiry, e)
            err = str(e)
            got = self.db.q("SELECT * FROM quotes WHERE symbol=? AND expiry=?", (SYMBOL, expiry))
            if not got:
                raise DataError(f"No quotes for {expiry}: {e}")
            rows = [{"type": g["type"], "strike": g["strike"], "bid": g["bid"] or 0.0, "ask": g["ask"] or 0.0,
                     "last": g["last"], "iv": g["iv"], "asof": g["asof"]} for g in got]
            asof = min(g["asof"] for g in got)
            stale = True
        self._enrich(rows, expiry)
        out = {"rows": rows, "asof": asof, "stale": stale, "error": err, "_t": time.time()}
        with self._lock:
            self._chains[expiry] = out
        return out

    def _enrich(self, rows, expiry):
        S = (self._und or {}).get("price")
        if S is None:
            try:
                S = self.underlying()["price"]
            except DataError:
                S = None
        r = (self.rates.for_day(timeutil.today_ct()) or 4.0) / 100
        T = year_frac(dt.date.fromisoformat(expiry))
        for x in rows:
            x["mid"] = mid_of(x["bid"], x["ask"], x.get("last")) or 0.0
            iv = x.get("iv")
            x["delta"] = round(bs(S, x["strike"], T, r, iv, x["type"] == "call")[1], 2) if (S and iv) else None

    def quote(self, expiry, type_, strike, fresh=True):
        c = self.chain(expiry, fresh=fresh)
        for x in c["rows"]:
            if x["type"] == type_ and abs(x["strike"] - float(strike)) < 1e-6:
                q = dict(x)
                q.update(asof=x.get("asof") or c["asof"], stale=c["stale"] and bool(x.get("asof")) or c["error"] is not None,
                         expiry=expiry)
                return q
        return None

    def share_quote(self, fresh=False):
        u = self.underlying(fresh=fresh)
        bid = ask = None
        if marketcal.is_open(timeutil.now()):
            try:
                bid, ask = self.p.stock_bidask()
            except Exception:  # noqa: BLE001
                pass
        if not bid or not ask or ask < bid:
            bid = ask = u["price"]
        return {"bid": bid, "ask": ask, "mid": round((bid + ask) / 2 + 1e-9, 2), "asof": u["asof"],
                "stale": u.get("stale"), "last": u["price"]}

    def is_too_old(self, asof_iso):
        """During market hours, quotes older than 15 minutes block trading until refreshed."""
        now = timeutil.now()
        if not marketcal.is_open(now):
            return False
        return (now - timeutil.parse(asof_iso)).total_seconds() > self.STALE_S

    def invalidate(self):
        with self._lock:
            self._chains.clear()
            self._und = None
