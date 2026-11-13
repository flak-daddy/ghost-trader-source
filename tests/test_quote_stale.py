"""Startup re-quote: only the contracts you hold decide whether quotes 'didn't refresh'."""
from ghost_trader.startup import _not_refreshed
from tests.conftest import at


def row(k, fallback=False, asof="2026-11-12T20:59:00+00:00", bid=1.0):
    return {"type": "put", "strike": k, "bid": bid, "ask": bid + .05, "asof": asof, **({"fallback": True} if fallback else {})}


HELD = [{"type": "put", "strike": 55.0, "label": "$55 Put"}]


def test_far_strike_fallback_doesnt_count():
    chain = {"rows": [row(55.0), row(20.0, fallback=True), row(90.0, fallback=True)]}
    assert _not_refreshed(chain, HELD, at(2026, 11, 13, 10)) == []


def test_held_fallback_during_market_hours_counts():
    chain = {"rows": [row(55.0, fallback=True)]}
    assert _not_refreshed(chain, HELD, at(2026, 11, 13, 10)) == HELD


def test_after_close_latest_session_quote_is_fine():
    # Thursday evening: the held put's quote is from Thursday's session (3:59 PM ET close)
    chain = {"rows": [row(55.0, fallback=True, asof="2026-11-12T20:59:00+00:00")]}
    assert _not_refreshed(chain, HELD, at(2026, 11, 12, 18)) == []
    # Friday 7:40 AM, before the open: Thursday's close is still the latest session
    assert _not_refreshed(chain, HELD, at(2026, 11, 13, 7, 40)) == []


def test_after_close_old_quote_counts():
    chain = {"rows": [row(55.0, fallback=True, asof="2026-11-10T20:59:00+00:00")]}
    assert _not_refreshed(chain, HELD, at(2026, 11, 12, 18)) == HELD


def test_missing_or_empty_held_row_counts():
    assert _not_refreshed({"rows": [row(54.0)]}, HELD, at(2026, 11, 12, 18)) == HELD
    assert _not_refreshed({"rows": [row(55.0, bid=0.0) | {"ask": 0.0}]}, HELD, at(2026, 11, 12, 18)) == HELD
