"""Web demo (web/): the seed builds a valid run on many different 'todays', and the browser shim answers API calls."""
import datetime as dt
import importlib
import json
import sys
import threading
from pathlib import Path

import pytest

from ghost_trader import timeutil

WEB = Path(__file__).resolve().parent.parent / "web"


@pytest.fixture
def web(tmp_path, monkeypatch):
    monkeypatch.setenv("GHOST_TRADER_HOME", str(tmp_path))
    monkeypatch.syspath_prepend(str(WEB))
    start, tstart, sub = threading.Thread.start, threading.Timer.start, sys.modules["subprocess"].Popen
    import gt_web
    importlib.reload(gt_web)
    gt_web.HOME = str(tmp_path)
    yield gt_web
    threading.Thread.start, threading.Timer.start = start, tstart
    sys.modules["subprocess"].Popen = sub
    timeutil.freeze(None)
    if gt_web.app:
        gt_web.app.db.close()


@pytest.mark.parametrize("day", ["2026-11-18", "2026-11-23", "2026-12-26", "2027-01-04", "2027-03-14", "2027-07-05"])
def test_seed_and_dispatch(web, day):
    d = dt.date.fromisoformat(day)
    timeutil.freeze(dt.datetime(d.year, d.month, d.day, 19, 30, tzinfo=timeutil.CT))
    assert web.start() == "seeded"
    a = web.app
    hist = a.led.db.q("SELECT kind, title FROM events")
    titles = " | ".join(r["title"] for r in hist)
    assert "Put assigned" in titles and "Expired worthless" in titles and "Buy to close" in titles
    assert len(a.led.positions()) >= 1
    code, body = web.dispatch("loaded")
    assert code == 200
    code, body = web.dispatch("startup_status")
    st = json.loads(body)
    assert st["state"] == "done", st
    for name in ("state", "boot", "history", "performance"):
        code, body = web.dispatch(name)
        assert code in (200, 400), (name, body)
    code, body = web.dispatch("state")
    s = json.loads(body)
    assert s["run"] and s["bal"]
    assert web.dispatch("nope")[0] == 404


def test_resume(web):
    timeutil.freeze(dt.datetime(2026, 11, 18, 12, 0, tzinfo=timeutil.CT))
    assert web.start() == "seeded"
    web.app.db.close()
    assert web.start() == "resumed"
