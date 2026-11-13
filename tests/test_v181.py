"""v1.8.1: junk Yahoo IV is replaced (from price, or the nearest strike), and chances carry what they were based on."""
import math

from ghost_trader.api import App
from ghost_trader.market import bs, fix_ivs, implied_vol, iv_ok


def test_implied_vol_round_trip():
    for iv in (0.2, 0.6, 1.5):
        for K, call in ((49, False), (65, False), (75, True)):
            px = bs(65, K, 7 / 365, 0.04, iv, call)[0]
            if px > 0.005:
                assert abs(implied_vol(px, 65, K, 7 / 365, 0.04, call) - iv) < 1e-3


def test_implied_vol_unsolvable():
    assert implied_vol(0, 65, 49, 7 / 365, 0.04, False) is None
    assert implied_vol(1.0, 65, 70, 7 / 365, 0.04, False) is None  # below intrinsic value of 5
    assert implied_vol(1.0, 65, 49, 0, 0.04, False) is None


def _row(K, iv, mid, typ="put"):
    return {"type": typ, "strike": K, "iv": iv, "mid": mid}


def test_fix_ivs_keeps_sensible_and_repairs_junk():
    T, r = 7 / 365, 0.04
    good_px = bs(65, 49, T, r, 0.9, False)[0]
    rows = [_row(60, 0.55, 0.8), _row(49, 0.00001, good_px), _row(45, 0.00001, 0), _row(70, 0.6, 5.2, "call")]
    fix_ivs(rows, 65, T, r)
    assert rows[0]["iv"] == 0.55 and rows[0]["iv_src"] == "quote"
    assert abs(rows[1]["iv"] - 0.9) < 1e-3 and rows[1]["iv_src"] == "price"
    # no usable price either: borrow the nearest put strike's IV (49, the repaired one), never the call's
    assert rows[2]["iv_src"] == "nearby" and rows[2]["iv"] == rows[1]["iv"]
    assert all(iv_ok(x["iv"]) for x in rows)


def test_fix_ivs_nothing_to_go_on():
    rows = [_row(49, 0.0, 0)]
    fix_ivs(rows, 65, 7 / 365, 0.04)
    assert rows[0]["iv"] is None and rows[0]["iv_src"] is None


def test_junk_iv_no_longer_reads_certain():
    """The reported case: short 49 put, 7 calendar days, Yahoo IV ~0 → was exactly 100%/0%."""
    bad = App._chances("put", 65, 49, 0.05, 7, 0.00001, 4.0)
    assert bad["worthless"] == 1.0  # what the junk reading produced
    T, r = 7 / 365, 0.04
    rows = [_row(49, 0.00001, bs(65, 49, T, r, 1.1, False)[0])]
    fix_ivs(rows, 65, T, r)
    ch = App._chances("put", 65, 49, 0.05, 7, rows[0]["iv"], 4.0, rows[0]["iv_src"])
    assert 0.9 < ch["worthless"] < 0.9999 and ch["iv_src"] == "price"
    assert ch["S"] == 65 and ch["dte"] == 7 and math.isclose(ch["iv"], 1.1, abs_tol=1e-3)
