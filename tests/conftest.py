import datetime as dt

import pytest

from ghost_trader import config, db as dbm, timeutil
from ghost_trader.ledger import Ledger


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("GHOST_TRADER_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    yield tmp_path
    timeutil.freeze(None)


@pytest.fixture
def led(home):
    D = dbm.DB(config.db_path())
    L = Ledger(D, config.Settings())
    yield L
    D.close()


def at(y, m, d, hh=10, mm=0):
    return dt.datetime(y, m, d, hh, mm, tzinfo=timeutil.CT)


def q(bid, ask):
    return {"bid": bid, "ask": ask, "mid": round((bid + ask) / 2, 2)}
