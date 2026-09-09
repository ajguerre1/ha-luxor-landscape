"""No site data reaches the public repository.

This is a **publication** guard, not a code-quality one. The integration is public; the property it
was written against is not. The group names on the reference controller are its plants and
locations, the controller carries a serial, and the addresses are on a private network.

Two design choices matter here and both were deliberate:

**It enumerates every tracked file rather than checking the ones that look risky.** A guard that
inspects a hand-written list of files is a guard against the leaks you already thought of. `git
ls-files` is the actual publication surface, so that is what gets checked.

**The denylist lives outside the repository**, at `local/site-terms.txt`, which is gitignored.
Committing the list of secret terms alongside the check for them would defeat the check. That means
this test is a no-op for anyone cloning the repository without the file, and it says so out loud
rather than passing silently -- an absent denylist and a clean repository look identical otherwise.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DENYLIST = ROOT / "local" / "site-terms.txt"

#: Binary and generated files are read as bytes and decoded leniently rather than skipped. A term
#: can perfectly well end up inside a PNG's metadata or a lockfile.
SKIP_DIRS = {".git"}


def _terms() -> list[str]:
    if not DENYLIST.exists():
        return []
    return [
        line.strip()
        for line in DENYLIST.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def _tracked_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        capture_output=True,
        check=True,
    ).stdout
    return [ROOT / name for name in out.decode().split("\0") if name]


def test_the_denylist_is_present_or_this_guard_is_announced_as_inactive():
    """An absent denylist must not look like a clean result."""
    if not DENYLIST.exists():
        pytest.skip(
            f"{DENYLIST.relative_to(ROOT)} is absent, so the site-data guard is INACTIVE. "
            "This is expected for anyone but the author; it is not a pass."
        )
    assert _terms(), "the denylist exists but contains no terms"


def test_git_ls_files_is_the_surface_being_checked():
    """The guard is only as good as its enumeration."""
    files = _tracked_files()
    assert len(files) > 20, "git ls-files returned suspiciously little; is this a git checkout?"
    assert any(f.name == "manifest.json" for f in files)


def test_no_tracked_file_contains_a_denylisted_term():
    terms = _terms()
    if not terms:
        pytest.skip("no denylist; see test_the_denylist_is_present...")

    lowered = [(term, term.lower()) for term in terms]
    findings: list[str] = []

    for path in _tracked_files():
        if not path.exists() or any(part in SKIP_DIRS for part in path.parts):
            continue
        try:
            text = path.read_bytes().decode("utf-8", errors="ignore").lower()
        except OSError:  # pragma: no cover - unreadable file
            continue
        for term, needle in lowered:
            if needle in text:
                findings.append(f"{path.relative_to(ROOT).as_posix()}: {term!r}")

    assert not findings, "site data in tracked files:\n  " + "\n  ".join(findings)


def test_the_guard_can_actually_fail(tmp_path):
    """The disarmed control.

    Everything above passes just as happily when the matching is broken. This proves the matcher
    finds a term when one is present, using a temporary file rather than the repository.
    """
    terms = _terms()
    if not terms:
        pytest.skip("no denylist; see test_the_denylist_is_present...")

    planted = tmp_path / "leaky.md"
    planted.write_text(f"something something {terms[0]} something", encoding="utf-8")
    text = planted.read_bytes().decode("utf-8", errors="ignore").lower()
    assert terms[0].lower() in text, "the matcher cannot find a term that is definitely there"


def test_fixtures_use_generic_names(load_fixture):
    """The captures are sanitised at the source, not just filtered at publication time."""
    names = {g["Name"] for g in load_fixture("group_list_get")["GroupList"]}
    assert all(n.startswith("Group ") for n in names), sorted(names)[:5]

    themes = {t["Name"] for t in load_fixture("theme_list_get")["ThemeList"]}
    assert themes == {"Theme A", "Theme B", "Theme C"}

    controller = load_fixture("controller_name")["Controller"]
    assert controller == "lxtwo-000000000", "the controller serial must be zeroed"
