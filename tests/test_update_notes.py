"""v1.8.2: an update that jumps several releases shows every skipped release's changes, newest first."""
import subprocess

from ghost_trader import __version__, updater


def test_single_release_is_unchanged():
    assert updater.combined_notes([("v9.0.0", "- v9.0.0: one thing\n")]) == "- v9.0.0: one thing"


def test_several_releases_listed_newest_first():
    out = updater.combined_notes([("v9.2.0", "- v9.2.0: c"), ("v9.1.0", ""), ("v9.0.0", "- v9.0.0: a\n- fix b")])
    assert out.startswith(f"This update includes 3 releases since v{__version__}:")
    assert out.index("v9.2.0") < out.index("v9.1.0") < out.index("v9.0.0")
    assert "v9.1.0\n- Maintenance release" in out and "- v9.0.0: a\n- fix b" in out


def test_long_gaps_are_summed_up():
    items = [(f"v9.{i}.0", f"- v9.{i}.0: x") for i in range(20, 0, -1)]
    out = updater.combined_notes(items)
    assert out.count("\nv9.") == updater.MAX_NOTES
    assert out.endswith(f"…and {20 - updater.MAX_NOTES} earlier releases (v9.1.0 to v9.8.0).")


def test_check_collects_every_newer_tag(tmp_path, monkeypatch):
    repo, origin = tmp_path / "app", tmp_path / "origin"

    def g(*a, cwd=repo):
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=cwd, check=True,
                       capture_output=True)
    origin.mkdir()
    g("init", "-q", "--bare", cwd=origin)
    repo.mkdir()
    g("init", "-q")
    g("remote", "add", "origin", str(origin))
    g("commit", "-q", "--allow-empty", "-m", "base")
    for t in ("v0.0.1", "v99.0.0", "v99.1.0", "v99.2.0"):   # one older than this version, three newer
        g("tag", "-a", t, "-m", f"- {t}: change")
    g("push", "-q", "origin", "--tags")
    monkeypatch.setattr(updater, "_git", lambda *a, timeout=30: subprocess.run(
        ["git", *a], cwd=repo, capture_output=True, text=True, check=True).stdout.strip())
    monkeypatch.setattr(updater, "is_checkout", lambda: True)
    info = updater.check()
    assert info["tag"] == "v99.2.0" and info["skipped"] == 2
    n = info["notes"]
    assert n.index("v99.2.0") < n.index("v99.1.0") < n.index("v99.0.0") and "v0.0.1" not in n
