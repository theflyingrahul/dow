"""Thin wrapper over the git CLI - git is the versioning and storage backend."""
from __future__ import annotations

import subprocess
from pathlib import Path


class GitError(RuntimeError):
    pass


class GitStore:
    def __init__(self, root: Path):
        self.root = Path(root)

    def _run(self, *args: str, check: bool = True) -> str:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(self.root),
            capture_output=True,
            text=True,
        )
        if check and proc.returncode != 0:
            raise GitError((proc.stderr or proc.stdout).strip())
        return proc.stdout.strip()

    def is_repo(self) -> bool:
        """True only if this directory is *its own* git repository top-level.

        dow's store (``.dow``) normally lives *inside* the project's own git
        repository, so a naive ``rev-parse --is-inside-work-tree`` would walk up
        and report the enclosing project repo - causing dow to ``git add -A`` and
        commit the whole project tree into the project's history. The store must
        be self-contained, so we treat it as a repo only when its own top-level
        resolves to this exact directory (git stops walking up once it finds the
        ``.dow/.git`` created by :meth:`init`).
        """
        if not self.root.exists():
            return False
        top = self._run("rev-parse", "--show-toplevel", check=False)
        if not top:
            return False
        try:
            return Path(top).resolve() == self.root.resolve()
        except Exception:
            return False

    def init(self) -> None:
        self._run("init")
        # Ensure a commit identity exists so commits work in fresh environments.
        if not self._run("config", "user.email", check=False):
            self._run("config", "user.email", "dow@example.com")
        if not self._run("config", "user.name", check=False):
            self._run("config", "user.name", "dow")

    def add(self, *paths: str) -> None:
        self._run("add", *paths)

    def commit(self, message: str) -> str:
        self._run("commit", "-m", message, "--allow-empty")
        return self.rev_parse("HEAD")

    def rev_parse(self, ref: str) -> str:
        return self._run("rev-parse", ref)

    def show_file(self, ref: str, path: str) -> str:
        return self._run("show", f"{ref}:{path}")

    def tag(self, name: str, ref: str = "HEAD") -> None:
        self._run("tag", "-f", name, ref)

    def list_tags(self) -> list:
        return [t for t in self._run("tag", check=False).splitlines() if t]

    def log(self, path: str | None = None, limit: int = 20) -> list:
        args = ["log", f"-n{limit}", "--pretty=%h%x09%cI%x09%s"]
        if path:
            args += ["--", path]
        rows = []
        for line in self._run(*args, check=False).splitlines():
            parts = line.split("\t")
            if len(parts) == 3:
                rows.append((parts[0], parts[1], parts[2]))
        return rows
