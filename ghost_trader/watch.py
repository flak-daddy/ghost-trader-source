"""Tracked symbols (v1.14.0): the list kept in Settings, and how a symbol is checked before it's added."""
import re

DEFAULT = ["QQQ", "SPY", "SQQQ", "^GSPC", "^NDX", "^VIX"]
MAX = 40
NAMES = {"QQQ": "Invesco QQQ (Nasdaq-100 ETF)", "SPY": "SPDR S&P 500 ETF", "SQQQ": "ProShares UltraPro Short QQQ",
         "TQQQ": "ProShares UltraPro QQQ", "^GSPC": "S&P 500 index", "^NDX": "Nasdaq-100 index", "^VIX": "VIX volatility index"}
_OK = re.compile(r"^\^?[A-Z][A-Z0-9.\-]{0,9}$")


def clean_symbol(s):
    """'  brk-b ' -> 'BRK-B'; '^spx' -> '^SPX'. None when it can't be a Yahoo ticker."""
    s = str(s or "").strip().upper()
    return s if _OK.match(s) else None


def is_index(sym):
    return str(sym).startswith("^")


def clean_list(v):
    """A saved list made safe: valid, upper-case, no repeats, in order, at most MAX."""
    out = []
    for s in v or []:
        s = clean_symbol(s)
        if s and s not in out:
            out.append(s)
    return out[:MAX]
