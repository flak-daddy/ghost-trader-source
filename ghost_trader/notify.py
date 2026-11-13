"""Desktop notifications from the weekday timer: the expiration-day nudge (7:45 AM CT), the end-of-day summary
(3:30 PM CT), and indicator alerts (checked at both times).

A systemd user timer runs `ghost-trader --notify` at those times on weekdays, whether or not the app is open.
The app sets the timer up itself (and install.sh does too); it needs `notify-send` and a notification daemon
(mako, dunst, swaync, ...) running in the desktop session.
"""
import datetime as dt
import json
import logging
import os
import shutil
import subprocess
from pathlib import Path

from . import APP_NAME, SYMBOL, config, marketcal, timeutil

log = logging.getLogger("ghost_trader.notify")

UNIT = "ghost-trader-nudge"
TIME_CT = "07:45"
EOD_CT = "15:30"
DAEMONS = ("mako", "dunst", "swaync", "fnott", "xfce4-notifyd", "notification-daemon", "plasmashell", "gnome-shell")


def _units_dir():
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "systemd" / "user"


def launcher():
    """The command the timer runs: the install.sh launcher for a git checkout, else the packaged /usr/bin one."""
    local = Path.home() / ".local" / "bin" / "ghost-trader"
    if local.exists():
        return local
    found = shutil.which("ghost-trader")
    return Path(found) if found else local


def unit_texts():
    service = f"""[Unit]
Description={APP_NAME}: weekday notification check

[Service]
Type=oneshot
ExecStart={launcher()} --notify
"""
    timer = f"""[Unit]
Description={APP_NAME}: weekday checks (expirations, end-of-day summary, indicator alerts)

[Timer]
OnCalendar=Mon..Fri {TIME_CT} America/Chicago
OnCalendar=Mon..Fri {EOD_CT} America/Chicago
Persistent=true

[Install]
WantedBy=timers.target
"""
    return service, timer


def send(title, body):
    """Show a desktop notification. Returns (ok, message)."""
    ns = shutil.which("notify-send")
    if not ns:
        return False, "notify-send isn't installed (sudo pacman -S libnotify)."
    icon = config.STATIC_DIR / "icon.svg"
    try:
        r = subprocess.run([ns, "-a", APP_NAME, "-i", str(icon), "-u", "normal", title, body],
                           capture_output=True, text=True, timeout=10)
    except Exception as e:  # noqa: BLE001
        return False, f"notify-send failed: {e}"
    if r.returncode != 0:
        return False, (r.stderr or "notify-send failed").strip()
    if not daemon_running():
        return True, "Sent, but no notification daemon seems to be running (e.g. mako), so it may not appear."
    return True, "Sent."


def daemon_running():
    try:
        out = subprocess.run(["ps", "-eo", "comm"], capture_output=True, text=True, timeout=5).stdout.split()
    except Exception:  # noqa: BLE001
        return True  # can't tell; don't nag
    return any(d in out for d in DAEMONS)


def status():
    d = _units_dir()
    installed = (d / f"{UNIT}.timer").exists()
    active = None
    if installed and shutil.which("systemctl"):
        try:
            active = subprocess.run(["systemctl", "--user", "is-active", f"{UNIT}.timer"], capture_output=True,
                                    text=True, timeout=5).stdout.strip() == "active"
        except Exception:  # noqa: BLE001
            active = None
    return {"installed": installed, "active": active, "time": "7:45 AM and 3:30 PM CT, weekdays",
            "notify_send": bool(shutil.which("notify-send")), "daemon": daemon_running()}


def ensure_timer():
    """Install/refresh the systemd user timer when running from an installed checkout. Returns a short note or None."""
    if not launcher().exists() or not shutil.which("systemctl"):
        return None
    d = _units_dir()
    d.mkdir(parents=True, exist_ok=True)
    service, timer = unit_texts()
    changed = False
    for name, text in ((f"{UNIT}.service", service), (f"{UNIT}.timer", timer)):
        p = d / name
        if not p.exists() or p.read_text() != text:
            p.write_text(text)
            changed = True
    if not changed and status()["active"]:
        return None
    try:
        subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True, timeout=15)
        r = subprocess.run(["systemctl", "--user", "enable", "--now", f"{UNIT}.timer"], capture_output=True,
                           text=True, timeout=15)
        if r.returncode != 0:
            return f"couldn't enable the notification timer: {(r.stderr or '').strip()}"
    except Exception as e:  # noqa: BLE001
        return f"couldn't enable the notification timer: {e}"
    return "notifications set up (7:45 AM and 3:30 PM CT on weekdays)"


def expiring_today(led, today):
    """Open positions expiring today, oldest first."""
    if not led.run():
        return []
    return [p for p in led.positions() if p["expiry"] == today.isoformat()]


def message(positions, price):
    lines = []
    for p in positions:
        side = "short" if p["side"] == "short" else "long"
        what = f"{p['open_qty']} × ${p['strike']:g} {'Put' if p['type'] == 'put' else 'Call'} ({side})"
        if price:
            itm = price < p["strike"] if p["type"] == "put" else price > p["strike"]
            pct = abs(price - p["strike"]) / p["strike"] * 100
            what += f": {SYMBOL} {price:.2f}, {pct:.1f}% {'in' if itm else 'out of'} the money"
        lines.append(what)
    n = sum(p["open_qty"] for p in positions)
    title = f"{n} {SYMBOL} contract{'s' if n != 1 else ''} expire today"
    body = "\n".join(lines) + "\nSettles at the 3:00 PM CT close; the app processes it after 5 PM."
    return title, body


def eod_summary(led, price, today, rate=None):
    """(title, body) for the end-of-day summary, or None without a run."""
    r = led.run()
    if not r:
        return None
    now_c = led.account_value_c(price)
    prev = led.db.one("SELECT account_value_c FROM snapshots WHERE run_id=? AND day<? ORDER BY day DESC LIMIT 1",
                      (r["id"], today.isoformat()))
    prev_c = prev[0] if prev else r["start_cash_c"]
    chg = now_c - prev_c
    prem = 0
    for e in led.db.q("SELECT ts, data FROM events WHERE run_id=? AND kind='Trade' ORDER BY ts DESC LIMIT 200", (r["id"],)):
        if timeutil.parse(e[0]).astimezone(timeutil.CT).date() != today:
            continue
        d = json.loads(e[1] or "{}")
        if d.get("action") == "sell_to_open":
            prem += d.get("premium_c") or 0
    avail, coll = led.balances()
    intr = (avail + coll) * (rate or 0) / 100 / 365
    nxt = marketcal.next_trading_day(today)
    tomorrow = [p for p in led.positions() if p["expiry"] == nxt.isoformat()]
    sign = "+" if chg >= 0 else "−"
    pct = chg / prev_c * 100 if prev_c else 0
    title = f"{APP_NAME} today: {sign}${abs(chg) / 100:,.2f} ({sign}{abs(pct):.2f}%)"
    lines = [f"Account value ${now_c / 100:,.2f}" + (f" · {SYMBOL} {price:.2f}" if price else "")]
    lines.append(f"Premium today ${prem / 100:,.2f} · interest about ${intr / 100:,.2f}/day")
    if tomorrow:
        n = sum(p["open_qty"] for p in tomorrow)
        what = ", ".join(f"${p['strike']:g} {'Put' if p['type'] == 'put' else 'Call'} ×{p['open_qty']}" for p in tomorrow)
        lines.append(f"Expiring {timeutil.fmt_date(nxt)}: {n} contract{'s' if n != 1 else ''} ({what})")
    else:
        lines.append(f"Nothing expires {timeutil.fmt_date(nxt)}")
    return title, "\n".join(lines)


def _once(name, today, fn):
    """Run fn() once per day per name (a marker file); fn returns (sent_ok, text)."""
    mark = config.data_dir() / f"{name}-{today.isoformat()}"
    if mark.exists():
        return f"{name}: already done today"
    ok, text = fn()
    if ok:
        mark.write_text(text)
        cutoff = f"{name}-{(today - dt.timedelta(days=14)).isoformat()}"
        for old in config.data_dir().glob(f"{name}-*"):
            if old != mark and old.name < cutoff:
                old.unlink(missing_ok=True)
    return text


def daily_check(led, quote_price=None, now=None, settings=None, readings=None, rate=None):
    """Called by the timer. Mornings: expiration nudge. From 3 PM CT: end-of-day summary (if on).
    Both times: indicator alerts (if a readings function is given). Returns what it did, for logging."""
    now = now or timeutil.now()
    today = now.astimezone(timeutil.CT).date()
    if not marketcal.is_trading_day(today):
        return "not a trading day"
    settings = settings or config.Settings()
    out = []
    if readings is not None:
        from . import alerts
        try:
            fired = alerts.check(readings(), settings, send, led)
            out.append(f"alerts: {len(fired)} fired")
        except Exception as e:  # noqa: BLE001
            log.warning("alerts: %s", e)
            out.append(f"alerts failed: {e}")
    if now.astimezone(timeutil.CT).hour >= 15:
        if settings.get("eod_summary") is False:
            return " · ".join(out + ["end-of-day summary off"])
        price = None
        try:
            price = quote_price() if quote_price else None
        except Exception as e:  # noqa: BLE001
            log.warning("eod price: %s", e)
        if price is None:
            price = led.db.val("SELECT last FROM quotes WHERE contract=?", ("_U_" + SYMBOL,))

        def go():
            m = eod_summary(led, price, today, rate)
            if not m:
                return False, "no run"
            ok, msg = send(*m)
            return ok, f"{m[0]} · {msg}"
        return " · ".join(out + [_once("eod", today, go)])
    return " · ".join(out + [_morning(led, quote_price, today)])


def _morning(led, quote_price, today):
    mark = config.data_dir() / f"nudged-{today.isoformat()}"
    if mark.exists():
        return "already notified today"
    pos = expiring_today(led, today)
    if not pos:
        return "nothing expires today"
    price = None
    try:
        price = quote_price() if quote_price else None
    except Exception as e:  # noqa: BLE001
        log.warning("nudge price: %s", e)
    if price is None:
        price = led.db.val("SELECT last FROM quotes WHERE contract=?", ("_U_" + SYMBOL,))
    title, body = message(pos, price)
    ok, msg = send(title, body)
    if ok:
        mark.write_text(title)
        for old in config.data_dir().glob("nudged-*"):
            if old != mark and old.name < f"nudged-{(today - dt.timedelta(days=14)).isoformat()}":
                old.unlink(missing_ok=True)
    return f"{title} · {msg}"
