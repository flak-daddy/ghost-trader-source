"""The app window and its fallback chain.

1. Own native window (pywebview + WebKitGTK). If it errors or stays blank for 10 s, retry once automatically with
   WEBKIT_DISABLE_DMABUF_RENDERER=1 (a known WebKitGTK fix on some Wayland/NVIDIA setups).
2. Chromium --app window, automatically, only if Chromium is installed.
3. Firefox: never automatic. A small GTK dialog asks first (terminal prompt, or a local "continue?" page, if GTK
   can't show anything).
Each fallback used is logged to History. In browser modes the app quits when the page stops sending heartbeats.
"""
import json
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from . import APP_NAME, config, updater

log = logging.getLogger("ghost_trader.window")
LOAD_TIMEOUT = 10


class _Reasons:
    @staticmethod
    def get():
        try:
            return json.loads(os.environ.get("GT_FALLBACKS", "[]"))
        except ValueError:
            return []

    @staticmethod
    def env_with(reason, attempt, extra=None):
        env = {"GT_ATTEMPT": str(attempt), "GT_FALLBACKS": json.dumps(_Reasons.get() + [reason])}
        env.update(extra or {})
        return env


def _zenity_save(name):
    z = shutil.which("zenity")
    default = Path.home() / "Downloads" / name
    if z:
        r = subprocess.run([z, "--file-selection", "--save", "--confirm-overwrite", f"--filename={default}",
                            f"--title=Save {name}"], capture_output=True, text=True)
        return r.stdout.strip() or None
    default.parent.mkdir(parents=True, exist_ok=True)
    return str(default)


class BrowserAdapter:
    mode = "browser"

    def save_dialog(self, name):
        return _zenity_save(name)


class WebviewAdapter:
    mode = "native"

    def __init__(self, webview, win):
        self.webview, self.win = webview, win

    def save_dialog(self, name):
        wv = self.webview
        kind = getattr(getattr(wv, "FileDialog", None), "SAVE", None) or getattr(wv, "SAVE_DIALOG")
        res = self.win.create_file_dialog(kind, directory=str(Path.home()), save_filename=name)
        if not res:
            return None
        return res if isinstance(res, str) else res[0]


def _log_fallbacks(app, mode):
    reasons = _Reasons.get()
    if not reasons:
        return
    detail = " → ".join(reasons) + f". Now running in: {mode}."
    app.led_event_safe("Warning", "Window fallback used", detail, warning=True)


def _restart_env():
    return {"GT_ATTEMPT": "1", "GT_FALLBACKS": "[]"}


def run(app, server):
    attempt = int(os.environ.get("GT_ATTEMPT", "1"))
    if attempt <= 2:
        ok, reason = _try_webview(app, server)
        if ok:
            return 0
        nxt = {"WEBKIT_DISABLE_DMABUF_RENDERER": "1"} if attempt == 1 else {}
        label = f"native window failed ({reason})" + ("; retrying with WEBKIT_DISABLE_DMABUF_RENDERER=1"
                                                      if attempt == 1 else "")
        log.warning(label)
        server.stop()
        updater.restart(_Reasons.env_with(label, attempt + 1, nxt))
    if attempt == 3:
        ok, reason = _try_chromium(app, server)
        if ok:
            return 0
        server.stop()
        updater.restart(_Reasons.env_with(reason, 4))
    return _firefox(app, server)


def _try_webview(app, server):
    try:
        import webview
    except Exception as e:  # noqa: BLE001
        return False, f"pywebview not available: {e}"
    failed = {}
    try:
        win = webview.create_window(APP_NAME, server.url, width=1440, height=920, min_size=(960, 640),
                                    background_color="#0f1115")
    except Exception as e:  # noqa: BLE001
        return False, f"couldn't create the window: {e}"
    app.window = WebviewAdapter(webview, win)

    def watchdog():
        if not app.loaded.wait(LOAD_TIMEOUT):
            failed["reason"] = f"window stayed blank for {LOAD_TIMEOUT} s"
            try:
                win.destroy()
            except Exception:  # noqa: BLE001
                pass
        else:
            _log_fallbacks(app, "native window")

    def restart():
        try:
            win.destroy()
        except Exception:  # noqa: BLE001
            pass

    app.on_restart = restart
    threading.Thread(target=watchdog, daemon=True).start()
    try:
        webview.start(gui="gtk", private_mode=False, storage_path=str(config.data_dir() / "webview"))
    except Exception as e:  # noqa: BLE001
        failed["reason"] = f"window error: {e}"
    if app.restart_requested:
        server.stop()
        updater.restart(_restart_env())
    if failed:
        return False, failed["reason"]
    server.stop()
    return True, None


def _chromium_bin():
    for b in ("chromium", "chromium-browser"):
        p = shutil.which(b)
        if p:
            return p
    return None


def _heartbeat_loop(app, proc=None, grace=25):
    while True:
        time.sleep(2)
        if app.restart_requested:
            if proc:
                proc.terminate()
            updater.restart(_restart_env())
        if proc is not None and proc.poll() is not None:
            return
        if time.time() - app.last_beat > grace:
            return


def _try_chromium(app, server):
    b = _chromium_bin()
    if not b:
        return False, "Chromium isn't installed (skipped)"
    app.window = BrowserAdapter()
    prof = config.data_dir() / "chromium-profile"
    proc = subprocess.Popen([b, f"--app={server.url}", f"--user-data-dir={prof}", "--class=GhostTrader",
                             "--no-first-run", "--window-size=1440,920"], stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, start_new_session=True)
    if not app.loaded.wait(LOAD_TIMEOUT + 10):
        proc.terminate()
        return False, "Chromium app window didn't load"
    _log_fallbacks(app, "Chromium app window")
    _heartbeat_loop(app, proc)
    if proc.poll() is None:
        proc.terminate()
    server.stop()
    return True, None


def _ask_gtk(reason):
    try:
        import gi
        gi.require_version("Gtk", "3.0")
        from gi.repository import Gtk
    except Exception:  # noqa: BLE001
        return None
    try:
        d = Gtk.MessageDialog(message_type=Gtk.MessageType.QUESTION, buttons=Gtk.ButtonsType.NONE,
                              text="The Ghost Trader window didn't start as designed")
        d.format_secondary_text(f"{reason}.\n\nOpen Ghost Trader in Firefox instead?")
        d.add_button("Quit", Gtk.ResponseType.CANCEL)
        d.add_button("Open in Firefox", Gtk.ResponseType.OK)
        d.set_title(APP_NAME)
        resp = d.run()
        d.destroy()
        while Gtk.events_pending():
            Gtk.main_iteration()
        return resp == Gtk.ResponseType.OK
    except Exception:  # noqa: BLE001
        return None


def _firefox(app, server):
    reasons = _Reasons.get()
    reason = reasons[-1] if reasons else "the native window failed"
    ff = shutil.which("firefox")
    if not ff:
        print(f"{APP_NAME} couldn't open a window: " + "; ".join(reasons or [reason])
              + ". Firefox isn't installed either. See logs/ghost-trader.log.", file=sys.stderr)
        return 3
    answer = _ask_gtk(reason)
    if answer is None and sys.stdin and sys.stdin.isatty():
        try:
            answer = input(f"{APP_NAME}: {reason}. Open in Firefox instead? [y/N] ").strip().lower().startswith("y")
        except EOFError:
            answer = False
    app.window = BrowserAdapter()
    if answer is None:
        # Nothing could ask: open a local page that asks, and don't load the app until Continue is clicked.
        app.gate = threading.Event()
        app.gate_answer = None
        subprocess.Popen([ff, "--new-window", server.url.replace("/?", "/gate?")], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
        app.gate.wait()
        answer = app.gate_answer == "continue"
    else:
        if answer:
            subprocess.Popen([ff, "--new-window", server.url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
    if not answer:
        server.stop()
        return 0
    if not app.loaded.wait(60):
        server.stop()
        return 4
    os.environ["GT_FALLBACKS"] = json.dumps(reasons + ["opened in Firefox after asking"])
    _log_fallbacks(app, "Firefox")
    _heartbeat_loop(app)
    server.stop()
    return 0
