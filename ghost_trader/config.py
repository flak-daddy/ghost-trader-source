"""Paths and the private settings file (~/.local/share/ghost-trader/settings.json, mode 600)."""
import json
import os
import threading
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parent
PROJECT_DIR = PKG_DIR.parent
STATIC_DIR = PKG_DIR / "static"

DEFAULTS = {
    "av_key": "",            # Alpha Vantage API key
    "manual_rate": None,     # last-resort annual rate, percent (e.g. 4.24)
    "haircut": 0.0,          # percentage points below the T-bill rate
    "long_options": False,   # allow buying options to open
    "theme": "system",       # light | dark | system
    "chain_exp": None,       # last expiration viewed on the Chain
    "chain_view": "both",    # calls | both | puts
}


def install_kind():
    """'checkout' = the user's git clone (updates through the in-app updater);
    'system' = installed by a package manager (AUR / pacman; updates through yay -Syu);
    'other' = anything else (e.g. an unpacked source folder)."""
    if (PROJECT_DIR / ".git").exists():
        return "checkout"
    if str(PKG_DIR).startswith("/usr/"):
        return "system"
    return "other"


def data_dir():
    base = os.environ.get("GHOST_TRADER_HOME")
    if base:
        p = Path(base)
    else:
        xdg = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
        p = Path(xdg) / "ghost-trader"
    p.mkdir(parents=True, exist_ok=True)
    for sub in ("backups", "runs", "logs"):
        (p / sub).mkdir(exist_ok=True)
    return p


def db_path():
    return data_dir() / "ledger.db"


def log_path():
    return data_dir() / "logs" / "ghost-trader.log"


class Settings:
    def __init__(self, path=None):
        self.path = Path(path) if path else data_dir() / "settings.json"
        self._lock = threading.Lock()
        self._d = dict(DEFAULTS)
        if self.path.exists():
            try:
                self._d.update(json.loads(self.path.read_text()))
            except (OSError, ValueError):
                pass

    def get(self, key):
        return self._d.get(key, DEFAULTS.get(key))

    def all(self):
        return dict(self._d)

    def update(self, **kw):
        with self._lock:
            self._d.update({k: v for k, v in kw.items() if k in DEFAULTS})
            tmp = self.path.with_suffix(".tmp")
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as f:
                json.dump(self._d, f, indent=2)
            os.chmod(tmp, 0o600)
            os.replace(tmp, self.path)
