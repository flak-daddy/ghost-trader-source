"""Updates through GitHub: the app follows tagged releases (vX.Y.Z) of its own git checkout.

Flow: fetch tags over the read-only deploy key -> newest release tag above the running version is offered at
startup with its change list (the tag message) -> on yes: back up the ledger, write a pending-update marker,
check out the tag, restart. The restarted app runs a self-check; if it fails, it checks the previous release
back out, restores the backup and logs the rollback. The launcher script does the same if the new version
crashes before it can check itself.
"""
import json
import logging
import os
import re
import subprocess
import sys

from . import __version__, config

log = logging.getLogger("ghost_trader.updater")
TAG_RE = re.compile(r"^v(\d+)\.(\d+)(?:\.(\d+))?$")
PUBLIC_REPO = "flak-daddy/ghost-trader-source"   # public mirror the AUR package builds from


def parse_version(s):
    m = TAG_RE.match(s.strip()) or TAG_RE.match("v" + s.strip())
    if not m:
        return None
    return tuple(int(x or 0) for x in m.groups())


def _git(*args, timeout=30):
    r = subprocess.run(["git", "-C", str(config.PROJECT_DIR), *args], capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip() or f"git {' '.join(args)} failed")
    return r.stdout.strip()


def is_checkout():
    return (config.PROJECT_DIR / ".git").exists()


def marker_path():
    return config.data_dir() / "update-pending.json"


def current_ref():
    try:
        return _git("describe", "--tags", "--exact-match", "HEAD")
    except Exception:  # noqa: BLE001
        try:
            return _git("rev-parse", "--short", "HEAD")
        except Exception:  # noqa: BLE001
            return None


def local_edits():
    """Tracked files changed in the project folder (they would be overwritten by an update)."""
    out = _git("status", "--porcelain", "--untracked-files=no")
    return [ln[3:] for ln in out.splitlines() if ln.strip()]


def check():
    """Returns None, or {'tag','version','notes'} for the newest release newer than this one.
    Raises RuntimeError if GitHub can't be reached."""
    if not is_checkout():
        return None
    _git("fetch", "--tags", "--force", "--quiet", "origin", timeout=40)
    cur = parse_version(__version__)
    best = None
    for t in _git("tag", "-l", "v*").splitlines():
        v = parse_version(t)
        if v and v > cur and (best is None or v > best[0]):
            best = (v, t)
    if not best:
        return None
    notes = _git("tag", "-l", "--format=%(contents)", best[1]).strip()
    return {"tag": best[1], "version": ".".join(map(str, best[0])), "notes": notes}


def check_public(timeout=10):
    """For package-manager installs: newest release tag in the public source repo, if newer than this one.
    Returns None or {'tag','version'}. Raises on network errors."""
    import urllib.request
    req = urllib.request.Request(f"https://api.github.com/repos/{PUBLIC_REPO}/tags?per_page=100",
                                 headers={"Accept": "application/vnd.github+json", "User-Agent": "ghost-trader"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        tags = [t["name"] for t in json.loads(r.read().decode())]
    cur = parse_version(__version__)
    best = max(((parse_version(t), t) for t in tags if parse_version(t)), default=None)
    if best and best[0] > cur:
        return {"tag": best[1], "version": ".".join(map(str, best[0]))}
    return None


def apply(tag, backup_fn):
    """Back up, mark, check out `tag`. Raises with a plain-English reason when it won't proceed."""
    edits = local_edits()
    if edits:
        raise RuntimeError(
            "Files in the project folder were edited locally, so the update won't overwrite them: "
            + ", ".join(edits[:6]) + ("…" if len(edits) > 6 else "")
            + ". Commit them to a branch on GitHub and open a pull request so they go through review, "
              "then restart.")
    prev = current_ref()
    backup = backup_fn()
    marker_path().write_text(json.dumps({"from": prev, "to": tag, "backup": str(backup),
                                         "from_version": __version__}))
    reqs_changed = bool(_git("diff", "--name-only", "HEAD", tag, "--", "requirements.txt"))
    _git("checkout", "--quiet", "--detach", tag)
    if reqs_changed:
        r = subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "-r",
                            str(config.PROJECT_DIR / "requirements.txt")], capture_output=True, text=True, timeout=600)
        if r.returncode != 0:
            _git("checkout", "--quiet", "--detach", prev)
            clear_pending()
            raise RuntimeError("The new version needs updated Python packages and installing them failed: "
                               + (r.stderr.strip().splitlines() or ["unknown error"])[-1]
                               + ". Stayed on the current version.")
    return {"from": prev, "to": tag, "backup": str(backup)}


def pending():
    p = marker_path()
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except ValueError:
        return None


def clear_pending():
    marker_path().unlink(missing_ok=True)


def rollback(mark, restore_fn):
    """Check the previous release back out and restore the pre-update ledger backup."""
    if mark.get("from"):
        _git("checkout", "--quiet", "--detach", mark["from"])
    if mark.get("backup") and os.path.exists(mark["backup"]):
        restore_fn(mark["backup"])
    clear_pending()


def self_check():
    """Quick checks that the freshly-updated app can run. Returns a list of problems (empty = OK)."""
    problems = []
    try:
        from . import api, ledger, market, marketcal, perf, startup, server, window  # noqa: F401
    except Exception as e:  # noqa: BLE001
        problems.append(f"import failed: {e}")
    for f in ("index.html", "app.js", "app.css"):
        if not (config.STATIC_DIR / f).exists():
            problems.append(f"missing static/{f}")
    return problems


def restart(extra_env=None, args=None):
    env = dict(os.environ)
    env.update(extra_env or {})
    argv = [sys.executable, "-m", "ghost_trader"] + (args if args is not None else sys.argv[1:])
    os.execve(sys.executable, argv, env)
