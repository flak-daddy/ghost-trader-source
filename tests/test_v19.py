"""v1.9.0: backup & restore in Settings, and the silent daily IV save."""
import base64
import datetime as dt
import time

from ghost_trader import config, db as dbm, ivhist, timeutil
from ghost_trader.api import App
from ghost_trader.market import DemoProvider
from tests.test_v18 import ready


# ---------------------------------------------------------------- IV history
def test_atm_iv_picks_nearest_strike_and_averages():
    rows = [{"strike": 50, "type": "put", "iv": .70}, {"strike": 50, "type": "call", "iv": .66},
            {"strike": 55, "type": "put", "iv": .60}, {"strike": 52, "type": "call", "iv": None}]
    assert abs(ivhist.atm_iv(rows, 51.2) - .68) < 1e-9
    assert ivhist.atm_iv([], 51) is None


def test_interp_constant_maturity():
    assert ivhist.interp([(30, .5)]) == .5
    v = ivhist.interp([(20, .6), (40, .5)])
    assert .5 < v < .6
    assert abs(v ** 2 * 30 - (.6 ** 2 * 20 * .5 + .5 ** 2 * 40 * .5)) < 1e-9   # linear in total variance
    assert ivhist.interp([(45, .55), (60, .5)]) == .55                         # nearest when nothing brackets
    assert ivhist.interp([]) is None


def test_pick_expiries_brackets_30_days():
    today = dt.date(2026, 11, 13)
    ex = [(today + dt.timedelta(days=d)).isoformat() for d in (1, 7, 14, 28, 35, 63)]
    assert ivhist.pick_expiries(ex, today) == [ex[3], ex[4]]


def test_session_day_rules():
    fri_open = timeutil.CT.localize(dt.datetime(2026, 11, 13, 10, 0)) if hasattr(timeutil.CT, "localize") else dt.datetime(2026, 11, 13, 10, 0, tzinfo=timeutil.CT)
    assert ivhist.session_day(fri_open) == (dt.date(2026, 11, 13), True)
    sat = fri_open + dt.timedelta(days=1)
    assert ivhist.session_day(sat) == (dt.date(2026, 11, 13), False)
    mon_early = fri_open + dt.timedelta(days=3, hours=-3)                      # Mon 7:00 CT, before the open
    assert ivhist.session_day(mon_early) == (dt.date(2026, 11, 13), False)


def test_record_saves_one_row_per_session(home):
    a = ready(home)
    a.db.x("DELETE FROM iv_history")
    row = ivhist.record_safe(a)
    assert row and 0.2 < row[1] < 1.5
    n = a.db.val("SELECT COUNT(*) FROM iv_history")
    ivhist.record_safe(a)
    assert a.db.val("SELECT COUNT(*) FROM iv_history") == n == 1
    assert ivhist.history(a.db)[0][0] == row[0]


def test_startup_saves_iv_in_background(home):
    a = ready(home)
    t0 = time.time()
    while not a.db.val("SELECT COUNT(*) FROM iv_history") and time.time() - t0 < 10:
        time.sleep(.05)
    assert a.db.val("SELECT COUNT(*) FROM iv_history") == 1


# ---------------------------------------------------------------- backup & restore
def test_backup_now_and_list(home):
    a = ready(home)
    r = a.api_backup_now()
    assert r["ok"] and r["name"].endswith("-manual.db")
    assert r["backups"][0]["name"] == r["name"] and r["backups"][0]["why"] == "by you"
    assert any(b["why"] == "at startup" for b in r["backups"])


def test_export_ledger_writes_a_usable_copy(home, tmp_path):
    a = ready(home)
    dest = tmp_path / "out.db"
    a._ask_save = lambda name: str(dest)
    assert a.api_export_ledger()["ok"]
    info = dbm.inspect_ledger(dest)
    assert info["run_cash_c"] == 10_000_000 and info["schema"] == dbm.SCHEMA_VERSION
    a._ask_save = lambda name: None
    assert a.api_export_ledger()["cancelled"]


def test_restore_preview_compares_and_rejects_junk(home, tmp_path):
    a = ready(home)
    name = a.api_backup_now()["name"]
    p = a.api_restore_preview(name=name)
    assert p["ok"] and p["backup"]["run_start"] == p["current"]["run_start"]
    junk = base64.b64encode(b"not a database at all " * 50).decode()
    assert "isn't a Ghost Trader ledger" in a.api_restore_preview(data=junk)["error"]
    assert a.api_restore_preview(name="../../etc/passwd")["error"]


def test_restore_apply_swaps_ledger_and_logs_it(home):
    a = ready(home)
    name = a.api_backup_now()["name"]
    c = a.api_chain()
    a.api_place({"action": "sell_to_open", "type": "put", "expiry": c["expiry"], "strike": float(round(c["price"]) - 4),
                 "qty": 1, "price": None})
    restarted = []
    a.on_restart = lambda: restarted.append(1)
    r = a.api_restore_apply(source=name)
    assert r["ok"] and a.restart_requested
    note = (config.data_dir() / "restore-note.txt").read_text()
    assert name in note and "before a restore" not in note and "-pre-restore.db" in note
    assert any(f.name.endswith("-pre-restore.db") for f in (config.data_dir() / "backups").iterdir())
    # the restarted app logs the restore in History
    b = App(demo=True, provider=DemoProvider())
    b.api_loaded()
    t0 = time.time()
    while b.api_startup_status()["state"] not in ("done", "issue") and time.time() - t0 < 20:
        time.sleep(.05)
    assert b.db.val("SELECT COUNT(*) FROM events WHERE title='Ledger restored'") == 1
    assert not (config.data_dir() / "restore-note.txt").exists()


def test_restore_refuses_newer_schema(home, tmp_path):
    a = ready(home)
    f = tmp_path / "new.db"
    a.db.backup(f)
    import sqlite3
    c = sqlite3.connect(f)
    c.execute("UPDATE meta SET value='999' WHERE key='schema_version'")
    c.commit()
    c.close()
    data = base64.b64encode(f.read_bytes()).decode()
    assert "newer Ghost Trader" in a.api_restore_preview(data=data)["error"]


# ---------------------------------------------------------------- account value without unpaid interest
def test_account_value_leaves_out_unpaid_interest(home, tmp_path):
    a = ready(home)
    led = a.led
    db_ = a.db
    rid = led.run_id()
    db_.x("INSERT OR REPLACE INTO accruals(run_id, day, rate, balance_c, amount) VALUES(?,?,?,?,?)",
          (rid, "2026-11-01", 4.2, 10_000_000, 12.34))
    S = a.price()
    b = led.breakdown(S)
    assert b["accrued_c"] >= 1234
    assert b["account_value_c"] == b["available_c"] + b["collateral_c"] + b["shares_value_c"]
    assert led.account_value_c(S) == b["account_value_c"]
    p = a.api_close_run_preview()
    assert p["final_c"] == p["account_value_c"] + b["accrued_c"]   # closing pays it out first
    a._ask_save = lambda name: str(tmp_path / name)
    assert a.api_close_run(typed=p["final"])["ok"]
    assert a.api_settings()["past"][0]["final_c"] == p["final_c"]


def test_migration_restates_old_snapshots(home, tmp_path):
    import sqlite3
    a = ready(home)
    a.led.snapshot(timeutil.today_ct(), 50.0, 50.0)
    f = tmp_path / "old.db"
    a.db.backup(f)
    c = sqlite3.connect(f)
    c.execute("UPDATE snapshots SET accrued=7.5, account_value_c=account_value_c+750")
    c.execute("UPDATE meta SET value='4' WHERE key='schema_version'")
    c.commit()
    c.close()
    d = dbm.DB(f)
    row = d.one("SELECT available_c, collateral_c, shares, share_price, account_value_c FROM snapshots ORDER BY day DESC LIMIT 1")
    assert row[4] == row[0] + row[1] + round((row[2] or 0) * (row[3] or 0) * 100)
