#!/usr/bin/env bash
# Ghost Trader one-time setup. Run from the project folder (Code OSS integrated terminal):  ./install.sh
# Safe to run again; it only adds what's missing.
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$APP_DIR"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}/ghost-trader"
BIN="$HOME/.local/bin"
APPS="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
ICONS="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/scalable/apps"

ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }
die()  { printf '\n  \033[31m✗\033[0m %s\n\n' "$*"; exit 1; }

echo "Ghost Trader setup ($APP_DIR)"

# 1. Basics -------------------------------------------------------------------------------------------
command -v python3 >/dev/null || die "python3 isn't installed. Fix: sudo pacman -S python"
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' \
  || die "Python 3.11 or newer is needed (found $(python3 --version))."
command -v git >/dev/null || die "git isn't installed. Fix: sudo pacman -S git"
ok "python $(python3 -c 'import platform; print(platform.python_version())'), git"

# 2. Fonts used by desktop dialogs (Save-as, the window-failed prompt). The app bundles its own UI font.
if ! command -v fc-list >/dev/null || [ "$(fc-list 2>/dev/null | wc -l)" -eq 0 ]; then
  die "No usable system font was found, so desktop dialogs would show blank text.
     Fix: sudo pacman -S ttf-dejavu   (then run ./install.sh again)"
fi
ok "system fonts present ($(fc-match -f '%{family}' sans-serif 2>/dev/null || echo 'sans-serif'))"

# 3. Native window libraries (WebKitGTK 4.1 + PyGObject from pacman) ----------------------------------
if python3 -c "import gi; gi.require_version('WebKit2','4.1'); from gi.repository import WebKit2" 2>/dev/null; then
  ok "WebKitGTK 4.1 + python-gobject"
else
  warn "WebKitGTK 4.1 / python-gobject not found. The app will fall back to Chromium or (after asking) Firefox."
  warn "Fix: sudo pacman -S --needed webkit2gtk-4.1 python-gobject   (then run ./install.sh again)"
fi

# 4. Virtual environment (sees system python-gobject) ---------------------------------------------------
if [ ! -x .venv/bin/python ]; then
  python3 -m venv --system-site-packages .venv
  ok "created .venv"
fi
.venv/bin/python -m pip install --quiet --upgrade pip
.venv/bin/python -m pip install --quiet -r requirements.txt -r requirements-dev.txt
ok "python packages: $(.venv/bin/python -c 'import yfinance, webview; print("yfinance", yfinance.__version__, "· pywebview", webview.__version__ if hasattr(webview, "__version__") else "")')"

# 5. Run the latest release -------------------------------------------------------------------------------
if [ -d .git ]; then
  git fetch --tags --force --quiet origin || warn "couldn't reach GitHub; staying on the current checkout"
  latest="$(git tag -l 'v*' --sort=-v:refname | head -n1)"
  if [ -n "$latest" ]; then
    if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
      warn "files here were edited locally, so the release ($latest) wasn't checked out over them"
    else
      git checkout --quiet --detach "$latest"
      ok "checked out release $latest"
    fi
  fi
fi

# 6. Launcher (rolls back an update that crashes before its own self-check) -----------------------------
mkdir -p "$BIN" "$DATA"
cat > "$BIN/ghost-trader" <<LAUNCH
#!/usr/bin/env bash
# Ghost Trader launcher (written by install.sh)
APP_DIR="$APP_DIR"
DATA="\${XDG_DATA_HOME:-\$HOME/.local/share}/ghost-trader"
MARK="\$DATA/update-pending.json"
cd "\$APP_DIR" || exit 1
start=\$(date +%s)
"\$APP_DIR/.venv/bin/python" -m ghost_trader "\$@"
code=\$?
if [ \$code -ne 0 ] && [ -f "\$MARK" ] && [ \$(( \$(date +%s) - start )) -lt 90 ]; then
  read -r from backup to < <(python3 -c 'import json,sys; m=json.load(open(sys.argv[1])); print(m.get("from") or "-", m.get("backup") or "-", m.get("to") or "-")' "\$MARK")
  [ "\$from" != "-" ] && git -C "\$APP_DIR" checkout --quiet --detach "\$from"
  if [ "\$backup" != "-" ] && [ -f "\$backup" ]; then rm -f "\$DATA/ledger.db-wal" "\$DATA/ledger.db-shm"; cp "\$backup" "\$DATA/ledger.db"; fi
  rm -f "\$MARK"
  echo "The update to \$to crashed at startup, so the launcher went back to \$from and restored the ledger backup." > "\$DATA/rollback-note.txt"
  exec "\$APP_DIR/.venv/bin/python" -m ghost_trader "\$@"
fi
exit \$code
LAUNCH
chmod +x "$BIN/ghost-trader"
ok "launcher: $BIN/ghost-trader"
case ":$PATH:" in *":$BIN:"*) ;; *) warn "$BIN isn't on your PATH; add it to your shell profile to run 'ghost-trader' by name." ;; esac

# 7. App menu entry + icon ------------------------------------------------------------------------------
mkdir -p "$APPS" "$ICONS"
cp ghost_trader/static/icon.svg "$ICONS/ghost-trader.svg"
cat > "$APPS/ghost-trader.desktop" <<DESK
[Desktop Entry]
Type=Application
Name=Ghost Trader
Comment=Paper-trade covered calls and cash-secured puts
Exec=$BIN/ghost-trader
Icon=ghost-trader
Terminal=false
Categories=Office;Finance;
StartupWMClass=Ghost Trader
DESK
command -v update-desktop-database >/dev/null && update-desktop-database -q "$APPS" || true
ok "app menu entry"

# 8. Notifications (systemd user timer, weekdays 7:45 AM and 3:30 PM CT) --------------------------------
if command -v notify-send >/dev/null; then
  note="$(.venv/bin/python -c 'from ghost_trader import notify; print(notify.ensure_timer() or "already set up")')"
  ok "notifications: $note"
  if ! .venv/bin/python -c 'import sys; from ghost_trader import notify; sys.exit(0 if notify.daemon_running() else 1)'; then
    warn "no notification daemon is running, so notifications won't show. Fix: sudo pacman -S mako  (then add 'exec-once = mako' to your Hyprland config)"
  fi
else
  warn "notify-send not found, so desktop notifications are off. Fix: sudo pacman -S libnotify mako  (then run ./install.sh again)"
fi

# 9. Folders open in Dolphin ------------------------------------------------------------------------------
if command -v xdg-mime >/dev/null; then
  fm="$(xdg-mime query default inode/directory 2>/dev/null || true)"
  if [ "$fm" = "org.kde.dolphin.desktop" ]; then ok "folders open in Dolphin"
  else warn "folders open in: ${fm:-nothing set}. To use Dolphin: xdg-mime default org.kde.dolphin.desktop inode/directory"; fi
else
  warn "xdg-mime not found (sudo pacman -S xdg-utils) — the data-folder link in Settings needs it"
fi

echo
echo "Done. Next: ghost-trader --check   (then launch Ghost Trader from the app menu or run: ghost-trader)"
