"""SQLite ledger with versioned migrations. Each release upgrades the database from any older version."""
import shutil
import sqlite3
import threading

from . import timeutil

MIGRATIONS = {
    1: """
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE runs(
  id INTEGER PRIMARY KEY, started_at TEXT NOT NULL, start_day TEXT NOT NULL, start_cash_c INTEGER NOT NULL,
  closed_at TEXT, end_day TEXT, final_value_c INTEGER, csv_name TEXT, csv_text TEXT);
CREATE TABLE events(
  id INTEGER PRIMARY KEY, run_id INTEGER, ts TEXT NOT NULL, kind TEXT NOT NULL, title TEXT NOT NULL,
  detail TEXT DEFAULT '', data TEXT DEFAULT '{}', is_error INTEGER DEFAULT 0, is_warning INTEGER DEFAULT 0,
  position_id INTEGER, lot_id INTEGER);
CREATE INDEX ev_run ON events(run_id, ts);
CREATE TABLE event_tags(event_id INTEGER NOT NULL, tag TEXT NOT NULL, PRIMARY KEY(event_id, tag));
CREATE TABLE cash(
  id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL, ts TEXT NOT NULL, day TEXT NOT NULL,
  bucket TEXT NOT NULL CHECK(bucket IN ('available','collateral')), amount_c INTEGER NOT NULL,
  reason TEXT, event_id INTEGER);
CREATE INDEX cash_run ON cash(run_id, day);
CREATE TABLE positions(
  id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL, symbol TEXT NOT NULL, type TEXT NOT NULL, side TEXT NOT NULL,
  expiry TEXT NOT NULL, strike REAL NOT NULL, qty INTEGER NOT NULL, open_qty INTEGER NOT NULL,
  open_price REAL NOT NULL, opened_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open',
  collateral_c INTEGER NOT NULL DEFAULT 0, note TEXT DEFAULT '', lot_id INTEGER, closed_at TEXT,
  realized_c INTEGER NOT NULL DEFAULT 0);
CREATE TABLE position_tags(position_id INTEGER NOT NULL, tag TEXT NOT NULL, PRIMARY KEY(position_id, tag));
CREATE TABLE lots(
  id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL, symbol TEXT NOT NULL, qty INTEGER NOT NULL, open_qty INTEGER NOT NULL,
  cost REAL NOT NULL, acquired_at TEXT NOT NULL, acquired_day TEXT NOT NULL, source TEXT NOT NULL,
  source_position_id INTEGER, closed_at TEXT);
CREATE TABLE lot_moves(
  id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL, lot_id INTEGER NOT NULL, ts TEXT NOT NULL, day TEXT NOT NULL,
  direction TEXT NOT NULL CHECK(direction IN ('in','out')), qty INTEGER NOT NULL, price REAL NOT NULL,
  how TEXT NOT NULL, event_id INTEGER, position_id INTEGER);
CREATE TABLE accruals(
  run_id INTEGER NOT NULL, day TEXT NOT NULL, rate REAL NOT NULL, balance_c INTEGER NOT NULL, amount REAL NOT NULL,
  paid_day TEXT, paid_event_id INTEGER, PRIMARY KEY(run_id, day));
CREATE TABLE rates(day TEXT PRIMARY KEY, rate REAL NOT NULL, source TEXT NOT NULL);
CREATE TABLE snapshots(
  run_id INTEGER NOT NULL, day TEXT NOT NULL, ts TEXT NOT NULL, available_c INTEGER, collateral_c INTEGER,
  accrued REAL, shares INTEGER, share_price REAL, account_value_c INTEGER, tqqq_close REAL, marks TEXT,
  estimated INTEGER DEFAULT 0, PRIMARY KEY(run_id, day));
CREATE TABLE quotes(
  contract TEXT PRIMARY KEY, symbol TEXT, expiry TEXT, type TEXT, strike REAL, bid REAL, ask REAL, last REAL,
  iv REAL, asof TEXT);
CREATE TABLE prices(symbol TEXT NOT NULL, day TEXT NOT NULL, close REAL NOT NULL, PRIMARY KEY(symbol, day));
CREATE TABLE dividends(run_id INTEGER NOT NULL, ex_day TEXT NOT NULL, amount REAL NOT NULL, PRIMARY KEY(run_id, ex_day));
CREATE TABLE splits(symbol TEXT NOT NULL, day TEXT NOT NULL, ratio REAL NOT NULL, handled INTEGER DEFAULT 0,
  PRIMARY KEY(symbol, day));
CREATE TABLE reports(id INTEGER PRIMARY KEY, ts TEXT NOT NULL, data TEXT NOT NULL);
""",
    2: """
CREATE TABLE trade_readings(event_id INTEGER PRIMARY KEY, asof TEXT NOT NULL, data TEXT NOT NULL);
""",
    3: """
CREATE TABLE earnings(symbol TEXT NOT NULL, day TEXT NOT NULL, PRIMARY KEY(symbol, day));
""",
    4: """
CREATE TABLE iv_history(day TEXT PRIMARY KEY, iv REAL NOT NULL, price REAL, asof TEXT NOT NULL, points TEXT);
""",
    # v1.9.0: account value no longer counts accrued (unpaid) interest; restate past snapshots the same way
    5: """
UPDATE snapshots SET account_value_c = available_c + collateral_c
  + CAST(ROUND(COALESCE(shares, 0) * COALESCE(share_price, 0) * 100) AS INTEGER);
""",
}
SCHEMA_VERSION = max(MIGRATIONS)


class DB:
    """Thin thread-safe wrapper. All writes go through `tx()`."""

    def __init__(self, path):
        self.path = str(path)
        self.conn = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.lock = threading.RLock()
        self._depth = 0
        self.migrate()

    def version(self):
        try:
            r = self.conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
            return int(r[0]) if r else 0
        except sqlite3.OperationalError:
            return 0

    def migrate(self):
        with self.lock:
            v = self.version()
            if v > SCHEMA_VERSION:
                raise RuntimeError(
                    f"ledger.db is from a newer Ghost Trader (schema {v}, this app knows {SCHEMA_VERSION})."
                )
            for n in range(v + 1, SCHEMA_VERSION + 1):
                self.conn.execute("BEGIN")
                try:
                    for stmt in _split(MIGRATIONS[n]):
                        self.conn.execute(stmt)
                    self.conn.execute(
                        "INSERT OR REPLACE INTO meta(key,value) VALUES('schema_version',?)", (str(n),))
                    self.conn.execute("COMMIT")
                except Exception:
                    self.conn.execute("ROLLBACK")
                    raise

    # --- helpers -----------------------------------------------------------------------------
    def q(self, sql, args=()):
        with self.lock:
            return self.conn.execute(sql, args).fetchall()

    def one(self, sql, args=()):
        with self.lock:
            return self.conn.execute(sql, args).fetchone()

    def val(self, sql, args=(), default=None):
        r = self.one(sql, args)
        return default if r is None or r[0] is None else r[0]

    def x(self, sql, args=()):
        with self.lock:
            return self.conn.execute(sql, args).lastrowid

    def tx(self):
        return _Tx(self)

    def backup(self, dest):
        with self.lock:
            out = sqlite3.connect(str(dest))
            self.conn.backup(out)
            out.close()

    def close(self):
        with self.lock:
            self.conn.close()


class _Tx:
    def __init__(self, db):
        self.db = db

    def __enter__(self):
        self.db.lock.acquire()
        if self.db._depth == 0:
            self.db.conn.execute("BEGIN IMMEDIATE")
        self.db._depth += 1
        return self.db

    def __exit__(self, et, ev, tb):
        self.db._depth -= 1
        try:
            if self.db._depth == 0:
                self.db.conn.execute("ROLLBACK" if et else "COMMIT")
        finally:
            self.db.lock.release()
        return False


def _split(script):
    return [s.strip() for s in script.split(";") if s.strip()]


def rotate_backups(db, folder, keep=30, label="startup"):
    folder.mkdir(parents=True, exist_ok=True)
    stamp = timeutil.now_ct().strftime("%Y%m%d-%H%M%S")
    dest = folder / f"ledger-{stamp}-{label}.db"
    db.backup(dest)
    files = sorted(folder.glob("ledger-*.db"))
    for old in files[:-keep]:
        old.unlink(missing_ok=True)
    return dest


def inspect_ledger(path, live=False):
    """What a ledger file holds, without opening it as the live ledger. Raises ValueError if it isn't a Ghost
    Trader ledger this version can use."""
    import sqlite3
    try:
        # immutable: a backup or upload is read as-is, without leaving -wal/-shm files beside it
        c = sqlite3.connect(f"file:{path}?mode=ro" + ("" if live else "&immutable=1"), uri=True)
        try:
            names = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not {"meta", "runs", "events"} <= names:
                raise ValueError("That file isn't a Ghost Trader ledger.")
            r = c.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
            v = int(r[0]) if r else 0
            if v > SCHEMA_VERSION:
                raise ValueError(f"That ledger is from a newer Ghost Trader (schema {v}); update the app first.")
            run = c.execute("SELECT start_day, start_cash_c FROM runs WHERE closed_at IS NULL ORDER BY id DESC LIMIT 1").fetchone()
            closed = c.execute("SELECT COUNT(*) FROM runs WHERE closed_at IS NOT NULL").fetchone()[0]
            ev = c.execute("SELECT COUNT(*), MAX(ts) FROM events").fetchone()
            trades = c.execute("SELECT COUNT(*) FROM events WHERE kind='Trade'").fetchone()[0]
            snap = None
            if "snapshots" in names:
                snap = c.execute("SELECT day, account_value_c FROM snapshots ORDER BY day DESC LIMIT 1").fetchone()
        finally:
            c.close()
    except sqlite3.DatabaseError as e:
        raise ValueError(f"That file isn't a Ghost Trader ledger ({e}).") from None
    return {"schema": v, "run_start": run and run[0], "run_cash_c": run and run[1], "closed_runs": closed,
            "events": ev[0], "last_event": ev[1], "trades": trades,
            "last_day": snap and snap[0], "last_value_c": snap and snap[1]}


def restore_backup(src, dest):
    """Copy a backup over the ledger (and drop the write-ahead log files that belonged to the old one)."""
    for suffix in ("-wal", "-shm"):
        p = str(dest) + suffix
        try:
            import os
            os.remove(p)
        except FileNotFoundError:
            pass
    shutil.copy2(src, dest)
