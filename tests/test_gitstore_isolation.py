"""Regression: dow's store must stay self-contained even when ``.dow`` is created
*inside* another git repository (the normal deployment - e.g. a project's
``robustness_checks/dow_adapter/`` living in the project's own repo).

Before the fix, ``GitStore.is_repo()`` ran ``rev-parse --is-inside-work-tree``,
which walks *up* to the enclosing repo and returns ``true``; dow then skipped
creating its own ``.dow/.git`` and every ``git add -A`` / ``commit`` / ``tag`` ran
against the *host* project repo - committing the entire project tree (including
unrelated files) into the project's history. These tests pin the isolation.
"""
import shutil
import subprocess

import pytest

from dow.store import Store

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git is required")


def _git(cwd, *args):
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True,
                          text=True, check=True).stdout.strip()


def _init_outer(path):
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "outer@test")
    _git(path, "config", "user.name", "outer")
    (path / "keep.txt").write_text("host file\n", encoding="utf-8")
    _git(path, "add", "-A")
    _git(path, "commit", "-q", "-m", "outer base")
    return _git(path, "rev-parse", "HEAD")


def _record():
    return {
        "spec_name": "s",
        "spec_fingerprint": "fp0",
        "run_id": "2024-01-01T00:00:00Z",
        "input": "x",
        "config": {"evaluation": {}},
        "runtime": {},
        "samples": [{"output": "o"}],
        "metrics": {"stability": 1.0},
        "payload": {"labels": [1, 2, 3]},
    }


def test_store_nested_in_project_repo_does_not_touch_host(tmp_path):
    outer = tmp_path / "project"
    (outer / "sub" / "adapter").mkdir(parents=True)
    base = _init_outer(outer)
    # An unrelated untracked file that must never be swept into a commit.
    (outer / "unrelated.txt").write_text("do not commit me\n", encoding="utf-8")

    store_root = outer / "sub" / "adapter"
    st = Store(store_root)
    st.ensure()
    st.add_version("s", _record())

    # dow created its OWN repo under the store dir...
    assert (store_root / ".dow" / ".git").exists()
    assert st.git.is_repo() is True
    assert st.git.rev_parse("HEAD")  # the store repo has commits of its own

    # ...and the HOST project repo is completely untouched.
    assert _git(outer, "rev-parse", "HEAD") == base
    assert _git(outer, "rev-list", "--count", "HEAD") == "1"
    # The nested store shows only as an untracked dir; nothing else got staged.
    status = _git(outer, "status", "--porcelain")
    lines = {line.split() and line[3:] for line in status.splitlines()}
    assert "unrelated.txt" in status
    assert all(entry in {"sub/", "unrelated.txt"} for entry in lines if entry)
    assert _git(outer, "tag") == ""  # dow's per-version tags landed in .dow, not here


def test_is_repo_false_when_only_ancestor_is_a_repo(tmp_path):
    outer = tmp_path / "project"
    (outer / "sub").mkdir(parents=True)
    _init_outer(outer)
    # A store dir that has NOT been initialised yet, nested in the outer repo.
    st = Store(outer / "sub")
    assert st.git.is_repo() is False  # must not mistake the ancestor for its own
    st.ensure()
    assert st.git.is_repo() is True  # now it owns .dow/.git
