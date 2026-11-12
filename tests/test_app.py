"""App-level tests with the synthetic DemoProvider: startup steps and issue dialogs, ticket, review, place,
close run, history CSV, migrations, updater version parsing."""
import datetime as dt
import json
import sqlite3
import subprocess
import time

import pytest

from ghost_trader import config, db as dbm, timeutil, updater
from ghost_trader.api import App
from ghost_trader.market import DemoProvider


def wait_startup(app, timeout=20, after=None):
    t0 = time.time()
    while time.time() - t0 < timeout:
        s = app.api_startup_status()
        if s["state"] == "done" or (s["state"] == "issue" and s["issue"]["id"] != after):
            return s
        time.sleep(0.05)
    raise AssertionError("startup didn't finish")


def make(home, **kw):
    a = App(demo=True, provider=DemoProvider(**kw))
    a.api_loaded()
    return a


def test_startup_and_first_trade(home):
    a = make(home)
    s = wait_startup(a)
    assert s["state"] == "done", s
    assert a.api_start_run(cash="$100,000.00")["ok"]
    c = a.api_chain()
    assert c["strikes"] and c["expiry"]
    k = float(round(c["price"]) - 3)
    o = {"action": "sell_to_open", "type": "put", "expiry": c["expiry"], "strike": k, "qty": 1}
    t = a.api_ticket(order=o, fresh=True)
    assert t["check"]["ok"], t["check"]
    assert t["default_fill"] == t["quote"]["mid"]             # sells default to the mid
    assert len(t["compare"]["rows"]) >= 2
    o["price"] = t["default_fill"]
    r = a.api_review(order=o, shown={"bid": t["quote"]["bid"], "ask": t["quote"]["ask"]})
    assert r["ok"] and not r["moved"] and r["title"].startswith("SELL TO OPEN 1 ×")
    assert a.api_place(order=o)["ok"]
    st = a.api_state()
    assert len(st["positions"]) == 1
    assert st["bal"]["collateral_c"] == int(k * 100 * 100)
    h = a.api_history()
    assert [e["kind"] for e in h["events"]][:1] == ["Trade"]


def test_buy_default_fill_is_between_mid_and_ask(home):
    q = {"mid": 1.00, "ask": 1.10, "bid": 0.90}
    assert App.default_fill(q, "buy") == 1.05
    assert App.default_fill(q, "sell") == 1.00


def test_rate_issue_dialog_manual_rate(home):
    a = make(home, fail={"irx"})
    s = wait_startup(a)
    assert s["state"] == "issue" and s["issue"]["kind"] == "rate"
    a.api_startup_resolve(issue_id=s["issue"]["id"], choice="rate", value="4.1")
    s = wait_startup(a, after=s["issue"]["id"])
    assert s["state"] == "done"
    assert a.rates.latest()[0] == 4.1
    step = next(x for x in s["steps"] if x["id"] == "rate")
    assert step["status"] == "warn"
    assert a.db.val("SELECT COUNT(*) FROM events WHERE is_warning=1") >= 1


def test_price_issue_skip_logs_and_continues(home):
    a = make(home)
    wait_startup(a)
    a.api_start_run(cash=50000)
    b = App(demo=True, provider=DemoProvider(fail={"underlying", "expirations"}))
    b.api_loaded()
    s = wait_startup(b)
    assert s["issue"]["kind"] == "price"
    b.api_startup_resolve(issue_id=s["issue"]["id"], choice="skip")
    s = wait_startup(b, after=s["issue"]["id"])
    assert s["state"] == "done"
    assert b.api_state()["price_stale"]


def test_close_run_and_new_run(home):
    a = make(home)
    wait_startup(a)
    a.api_start_run(cash=10000)
    pre = a.api_close_run_preview()
    assert a.api_close_run(typed="1.00")["error"]
    res = a.api_close_run(typed=f"${float(pre['final']):,.2f}")
    assert res["ok"], res
    text = open(res["path"]).read()
    assert text.startswith("Ghost Trader run summary") and "Final value,10000.00" in text
    assert (config.data_dir() / "runs" / pre["name"]).exists()
    assert a.led.run() is None
    assert a.api_start_run(cash=20000)["ok"]
    assert a.api_settings()["past"][0]["final_c"] == 1000000


def test_close_run_cancelled_save_keeps_run(home):
    a = make(home)
    wait_startup(a)
    a.api_start_run(cash=10000)

    class W:
        def save_dialog(self, name):
            return None
    a.window = W()
    pre = a.api_close_run_preview()
    assert a.api_close_run(typed=pre["final"]) == {"cancelled": True}
    assert a.led.run() is not None


def test_tag_rename_merge_delete(home):
    a = make(home)
    wait_startup(a)
    a.api_start_run(cash=100000)
    c = a.api_chain()
    o = {"action": "sell_to_open", "type": "put", "expiry": c["expiry"], "strike": float(round(c["price"]) - 5), "qty": 1,
         "tags": ["#weekly", "#wheel"]}
    t = a.api_ticket(order=o)
    o["price"] = t["default_fill"]
    a.api_place(order=o)
    a.api_tag_edit(op="rename", tag="#weekly", to="weeklies")
    assert "#weeklies" in a._all_tags() and "#weekly" not in a._all_tags()
    a.api_tag_edit(op="merge", tag="#weeklies", to="#wheel")
    assert a._all_tags() == ["#wheel"]
    a.api_tag_edit(op="delete", tag="#wheel")
    assert a._all_tags() == []


def test_settings_file_is_private(home):
    s = config.Settings()
    s.update(av_key="ABC")
    assert (config.data_dir() / "settings.json").stat().st_mode & 0o777 == 0o600


def test_migration_versions(home):
    d = dbm.DB(config.db_path())
    assert d.version() == dbm.SCHEMA_VERSION
    d.close()
    con = sqlite3.connect(config.db_path())
    con.execute("UPDATE meta SET value='999' WHERE key='schema_version'")
    con.commit()
    con.close()
    with pytest.raises(RuntimeError, match="newer Ghost Trader"):
        dbm.DB(config.db_path())


def test_version_parsing():
    assert updater.parse_version("v1.2.3") == (1, 2, 3)
    assert updater.parse_version("v1.2") == (1, 2, 0)
    assert updater.parse_version("1.10.0") > updater.parse_version("1.9.9")
    assert updater.parse_version("nightly") is None


def test_updater_finds_newer_tag(tmp_path, monkeypatch):
    origin = tmp_path / "origin"
    work = tmp_path / "work"
    run = lambda *a, cwd: subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True)  # noqa: E731
    origin.mkdir()
    run("init", "-q", "-b", "main", cwd=origin)
    run("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "init", cwd=origin)
    run("-c", "user.email=t@t", "-c", "user.name=t", "tag", "-a", "v1.0.0", "-m", "first", cwd=origin)
    run("-c", "user.email=t@t", "-c", "user.name=t", "tag", "-a", "v9.1.0", "-m", "- Better charts\n- Fixes", cwd=origin)
    run("clone", "-q", str(origin), str(work), cwd=tmp_path)
    monkeypatch.setattr(config, "PROJECT_DIR", work)
    info = updater.check()
    assert info["tag"] == "v9.1.0" and "Better charts" in info["notes"]
    assert updater.local_edits() == []


def test_history_csv_and_errors(home):
    a = make(home)
    wait_startup(a)
    a.api_start_run(cash=1000)
    a.log_error("Stale quote", "what", "did", "todo")
    h = a.api_history(filter="Errors")
    assert h["events"][0]["data"]["what"] == "what"
    res = a.api_history_csv()
    assert res["ok"] and "Stale quote" in open(res["path"]).read()


def test_performance_shape(home):
    a = make(home)
    wait_startup(a)
    a.api_start_run(cash=1000)
    p = a.api_performance()
    assert p["days"] == [timeutil.today_ct().isoformat()]
    assert p["summary"]["value"] == 1000


def test_report_saved(home):
    a = make(home)
    wait_startup(a)
    r = a.api_report()
    assert [s["id"] for s in r["steps"]][0] == "update"
    assert json.dumps(r)


def test_expiration_list_groups(home):
    a = make(home)
    wait_startup(a)
    g = dict(a._exp_groups(a.quotes.expirations()))
    assert "This week" in g or "Weeklies" in g
    assert all(dt.date.fromisoformat(x["exp"]) >= timeutil.today_ct() for v in g.values() for x in v)


def test_blank_after_hours_quotes_use_last_good(home):
    class Blank(DemoProvider):
        blank = False

        def chain(self, expiry):
            rows = super().chain(expiry)
            if self.blank:
                for r in rows:
                    r["bid"] = r["ask"] = 0.0
            return rows
    p = Blank()
    a = App(demo=True, provider=p)
    a.api_loaded()
    wait_startup(a)
    e = a.quotes.expirations()[1]
    good = a.quotes.chain(e, fresh=True)
    k = next(r for r in good["rows"] if r["type"] == "put" and r["bid"] > 0.5)
    p.blank = True
    q = a.quotes.quote(e, "put", k["strike"], fresh=True)
    assert q["bid"] == k["bid"] and q["ask"] == k["ask"] and q["stale"]


def test_calendar_month(home):
    from tests.seed import seed
    seed()
    a = App(demo=True)
    a.api_loaded()
    wait_startup(a)
    c = a.api_calendar(month="2026-11")
    days = {d["day"]: d for w in c["weeks"] for d in w}
    assert all(len(w) == 5 for w in c["weeks"])
    assert days["2026-11-26"]["holiday"] == "Thanksgiving Day"
    assert "Early close" in days["2026-11-27"]["early"]
    nov6 = days["2026-11-06"]["items"]
    assert any(not i["active"] and "expired" in i["text"] and i["go"].startswith("history:event:") for i in nov6)
    assert days["2026-11-06"]["trades"] == 1
    assert days["2026-11-04"]["close"] and days["2026-11-04"]["chg"] is not None
    oct_ = {d["day"]: d for w in a.api_calendar(month="2026-10")["weeks"] for d in w}
    assert any(i["kind"] == "interest" and "+$" in i["text"] for i in oct_["2026-10-15"]["items"])
    assert any("assigned" in i["text"] for i in oct_["2026-10-16"]["items"])
    # open positions expiring later this month are active and jump to the Chain
    if timeutil.today_ct() <= dt.date(2026, 11, 20):
        assert any(i["active"] and i["go"].startswith("chainpos:") for i in days["2026-11-20"]["items"])


def test_history_day_filter(home):
    from tests.seed import seed
    seed()
    a = App(demo=True)
    h = a.api_history(day="2026-10-01")
    assert {e["kind"] for e in h["events"]} == {"Run", "Trade"}


def test_finished_position_story(home):
    from tests.seed import seed
    seed()
    a = App(demo=True)
    pid = a.db.val("SELECT id FROM positions WHERE status='expired'")
    s = a.api_position(id=pid)
    assert s["finished"] and s["outcome"] == "Expired worthless" and s["result_c"] == 8000
    assert s["days_held"] == 15 and s["settle_close"] == 57.20
    assert [e["kind"] for e in s["events"]] == ["Trade", "Expired", "Summary"]
    assigned = a.api_position(id=a.db.val("SELECT id FROM positions WHERE status='assigned'"))
    assert assigned["outcome"] == "Assigned" and assigned["lot_id"]
    assert not a.api_position(id=a.db.val("SELECT id FROM positions WHERE status='open' LIMIT 1")).get("finished")


def test_aur_install_shows_update_notice(home, monkeypatch):
    from ghost_trader import config as cfg, notify, updater as upd
    monkeypatch.setattr(cfg, "install_kind", lambda: "system")
    monkeypatch.setattr(upd, "check_public", lambda timeout=10: {"tag": "v9.0.0", "version": "9.0.0"})
    monkeypatch.setattr(notify, "ensure_timer", lambda: None)
    a = App(demo=False, provider=DemoProvider())
    a.api_loaded()
    s = wait_startup(a)
    assert s["state"] == "issue" and s["issue"]["kind"] == "update-notice"
    assert "yay -Syu ghost-trader" in s["issue"]["what"] and "yay -Bi ." in s["issue"]["what"]
    a.api_startup_resolve(issue_id=s["issue"]["id"], choice="ok")
    s = wait_startup(a, after=s["issue"]["id"])
    assert s["state"] == "done" and "yay -Syu" in s["steps"][0]["detail"]
    assert a.api_settings()["install"] == "system"


def test_pkgbuild_template():
    text = open("packaging/aur/PKGBUILD").read()
    assert "pkgver=@VERSION@" in text and "sha256sums=('@SHA256@')" in text
    assert "python-pywebview" in text and "python-yfinance" in text and "webkit2gtk-4.1" in text


def test_source_pkgbuild_template():
    text = open("packaging/arch/PKGBUILD").read()
    assert "pkgver=@VERSION@" in text and "#tag=v$pkgver" in text and "yay -Bi ." in text


def test_install_message_and_links(home):
    msg = open("packaging/ghost-trader.install").read()
    assert "https://www.alphavantage.co/support/#api-key" in msg
    assert open("packaging/arch/ghost-trader.install").read() == msg
    for p in ("packaging/aur/PKGBUILD", "packaging/arch/PKGBUILD"):
        assert "install=ghost-trader.install" in open(p).read()
    assert App(demo=True).api_open_link(name="nope")["error"]
