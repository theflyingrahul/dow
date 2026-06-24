"""Behavior store: automatic, named versions backed by Git for durability.

Git is an internal implementation detail - users never run git commands. Each
``run`` snapshots the current spec and its captured behavior as ``v1``, ``v2``,
and so on, and records it durably in a hidden Git repository under ``.dow``.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from .gitstore import GitError, GitStore

STORE_DIR = ".dow"


class Store:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.dir = self.root / STORE_DIR
        self.index_path = self.dir / "index.json"
        self.git = GitStore(self.dir)

    # -- lifecycle -------------------------------------------------------- #
    def is_initialized(self) -> bool:
        return self.index_path.exists()

    def ensure(self) -> None:
        self.dir.mkdir(exist_ok=True)
        (self.dir / "versions").mkdir(exist_ok=True)
        if not self.index_path.exists():
            self._save_index({"specs": {}})
        if not self.git.is_repo():
            self.git.init()
            self.git.add("-A")
            try:
                self.git.commit("dow: initialize behavior store")
            except GitError:
                pass

    # -- index ------------------------------------------------------------ #
    def _load_index(self) -> dict:
        return json.loads(self.index_path.read_text(encoding="utf-8"))

    def _save_index(self, index: dict) -> None:
        self.index_path.write_text(json.dumps(index, indent=2), encoding="utf-8")

    def list_versions(self, spec_name: str) -> list:
        if not self.index_path.exists():
            return []
        return self._load_index().get("specs", {}).get(spec_name, {}).get("versions", [])

    def meta(self, spec_name: str, version_id: str) -> dict:
        for v in self.list_versions(spec_name):
            if v["id"] == version_id:
                return v
        return {}

    # -- records ---------------------------------------------------------- #
    def add_version(
        self, spec_name: str, record: dict, message: str = "", parent: Optional[str] = None
    ) -> str:
        index = self._load_index()
        entry = index["specs"].setdefault(spec_name, {"counter": 0, "versions": []})
        if parent is None and entry["versions"]:
            parent = entry["versions"][-1]["id"]
        entry["counter"] += 1
        vid = f"v{entry['counter']}"

        vdir = self.dir / "versions" / spec_name
        vdir.mkdir(parents=True, exist_ok=True)
        (vdir / f"{vid}.json").write_text(json.dumps(record, indent=2), encoding="utf-8")

        entry["versions"].append(
            {
                "id": vid,
                "parent": parent,
                "created": record.get("run_id"),
                "stability": record["metrics"]["stability"],
                "fingerprint": record.get("spec_fingerprint"),
                "message": message,
            }
        )
        self._save_index(index)

        self.git.add("-A")
        try:
            sha = self.git.commit(f"{spec_name} {vid}: {message or 'run'}")
            self.git.tag(f"{spec_name}-{vid}", sha)
        except GitError:
            pass
        return vid

    def get_record(self, spec_name: str, version_id: str) -> dict:
        path = self.dir / "versions" / spec_name / f"{version_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"Unknown version: {version_id}")
        return json.loads(path.read_text(encoding="utf-8"))

    # -- tags ------------------------------------------------------------- #
    def add_tag(self, spec_name: str, version_id: str, tag: str) -> None:
        index = self._load_index()
        for v in index["specs"].get(spec_name, {}).get("versions", []):
            if v["id"] == version_id:
                tags = v.setdefault("tags", [])
                if tag not in tags:
                    tags.append(tag)
                break
        self._save_index(index)
        self._commit(f"{spec_name} {version_id}: tag {tag}")

    def latest_with_tag(self, spec_name: str, tag: str):
        t = (tag or "").strip().lower()
        matches = [
            v["id"]
            for v in self.list_versions(spec_name)
            if t in [str(x).lower() for x in v.get("tags", [])]
        ]
        return matches[-1] if matches else None

    # -- evaluation results ---------------------------------------------- #
    def save_eval(self, spec_name: str, version_id: str, eval_result: dict) -> None:
        path = self.dir / "versions" / spec_name / f"{version_id}.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        record["eval"] = eval_result
        path.write_text(json.dumps(record, indent=2), encoding="utf-8")
        index = self._load_index()
        for v in index["specs"].get(spec_name, {}).get("versions", []):
            if v["id"] == version_id:
                v["eval"] = eval_result.get("metrics", {})
                break
        self._save_index(index)
        self._commit(f"{spec_name} {version_id}: eval")

    def _commit(self, message: str) -> None:
        self.git.add("-A")
        try:
            self.git.commit(message)
        except GitError:
            pass

    # -- resolution ------------------------------------------------------- #
    def resolve(self, spec_name: str, ref: str) -> str:
        ids = [v["id"] for v in self.list_versions(spec_name)]
        if not ids:
            raise ValueError("No versions yet. Run 'dow run' first.")
        r = (ref or "last").strip().lower()
        if r in ("last", "latest", "head"):
            return ids[-1]
        if r in ("prev", "previous"):
            if len(ids) < 2:
                raise ValueError("There is no previous version yet.")
            return ids[-2]
        if r.isdigit():
            r = f"v{r}"
        if r in ids:
            return r
        tagged = self.latest_with_tag(spec_name, ref)
        if tagged:
            return tagged
        raise ValueError(f"Unknown version or tag '{ref}'. Available: {', '.join(ids)}")
