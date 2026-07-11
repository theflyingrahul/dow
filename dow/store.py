"""Behavior store: automatic, named versions backed by Git for durability.

Git is an internal implementation detail - users never run git commands. Each
``run`` snapshots the current spec and its captured behavior as ``v1``, ``v2``,
and so on, and records it durably in a hidden Git repository under ``.dow``.

Heavy per-item ``payload`` data (e.g. thousands of aligned labels a comparator
needs) is not stored inline in the version JSON: it is written once, keyed by its
content hash, under ``.dow/artifacts/`` (which is git-ignored) and referenced from
the record. This keeps the versioned history light while the record stays
verifiable and reproducible.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
from pathlib import Path
from typing import Optional

from .gitstore import GitError, GitStore
from .spec import flatten

STORE_DIR = ".dow"
ARTIFACTS_DIR = "artifacts"
AGGREGATIONS_DIR = "aggregations"


def _safe_component(value, kind: str) -> str:
    """Guard a single path component dow joins into a store path.

    Version ids, aggregation ids, spec names, and artifact references reach the
    store from callers - including the MCP tools and resources advertised as
    read-only - so a value bearing a path separator, ``..``, an absolute prefix,
    or a NUL byte must never be joined into a filesystem path: it would escape
    the ``.dow`` store and read arbitrary files. Only a plain single-segment
    slug is accepted.
    """
    s = str(value)
    if (
        s in ("", ".", "..")
        or s != os.path.basename(s)
        or "/" in s
        or "\\" in s
        or "\x00" in s
        or os.path.isabs(s)
    ):
        raise ValueError(f"Invalid {kind}: {value!r}")
    return s


def _json_default(obj):
    """Best-effort JSON coercion so dow can persist a project's payload no matter
    how it is represented in memory - dow stays agnostic to the project's data
    structures. numpy scalars/arrays, sets, bytes, dataclasses, and Paths degrade
    to a JSON-native form (finally ``str``) instead of breaking the capture. The
    project owns round-trip fidelity; dow only guarantees it will never refuse to
    store what an evaluator or provider returned.
    """
    if isinstance(obj, (set, frozenset)):
        return list(obj)
    if isinstance(obj, (bytes, bytearray)):
        return obj.decode("utf-8", "replace")
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return dataclasses.asdict(obj)
    for attr in ("tolist", "item"):  # numpy array -> list, numpy scalar -> py scalar
        fn = getattr(obj, attr, None)
        if callable(fn):
            try:
                return fn()
            except Exception:
                pass
    if isinstance(obj, Path):
        return str(obj)
    return str(obj)


class Store:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.dir = self.root / STORE_DIR
        self.index_path = self.dir / "index.json"
        self.artifacts_dir = self.dir / ARTIFACTS_DIR
        self.git = GitStore(self.dir)

    # -- lifecycle -------------------------------------------------------- #
    def is_initialized(self) -> bool:
        return self.index_path.exists()

    def ensure(self) -> None:
        self.dir.mkdir(exist_ok=True)
        (self.dir / "versions").mkdir(exist_ok=True)
        self.artifacts_dir.mkdir(exist_ok=True)
        gitignore = self.dir / ".gitignore"
        if not gitignore.exists():
            gitignore.write_text(f"{ARTIFACTS_DIR}/\n", encoding="utf-8")
        if not self.index_path.exists():
            self._save_index({"specs": {}})
        if not self.git.is_repo():
            self.git.init()
            self.git.add("-A")
            try:
                self.git.commit("dow: initialize behavior store")
            except GitError:
                pass

    # -- artifact-reference storage for heavy payloads -------------------- #
    def _externalize(self, record: dict) -> dict:
        """Return a copy of ``record`` with any heavy ``payload`` swapped for a
        content-addressed reference; the payload bytes are written to
        ``.dow/artifacts/<sha256>.json`` (git-ignored) exactly once."""
        payload = record.get("payload")
        if payload is None:
            return record
        blob = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, default=_json_default
        ).encode("utf-8")
        sha = hashlib.sha256(blob).hexdigest()
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        art = self.artifacts_dir / f"{sha}.json"
        if not art.exists():
            art.write_text(blob.decode("utf-8"), encoding="utf-8")
        disk = dict(record)
        disk["payload"] = {"__artifact__": f"{sha}.json", "sha256": sha, "bytes": len(blob)}
        return disk

    def _internalize(self, record: dict) -> dict:
        """Rehydrate an artifact-referenced ``payload`` back into the record."""
        payload = record.get("payload")
        if isinstance(payload, dict) and "__artifact__" in payload:
            ref = str(payload["__artifact__"])
            if (
                ref in ("", ".", "..")
                or ref != os.path.basename(ref)
                or "/" in ref
                or "\\" in ref
                or "\x00" in ref
                or os.path.isabs(ref)
            ):
                record["_payload_integrity"] = "invalid-artifact-ref"
                record["payload"] = None
                return record
            art = self.artifacts_dir / ref
            if not art.exists():
                record["_payload_missing"] = payload
                record["payload"] = None
                return record
            blob = art.read_text(encoding="utf-8")
            if hashlib.sha256(blob.encode("utf-8")).hexdigest() != payload.get("sha256"):
                record["_payload_integrity"] = "sha256-mismatch"
            record["payload"] = json.loads(blob)
        return record

    def store_figure(self, src_path) -> dict:
        """Store a produced figure file as a content-addressed artifact.

        Figures are binary and derived, so - like heavy payloads - their bytes
        live under the git-ignored ``.dow/artifacts/`` (keeping the versioned
        history light and free of binary churn). The returned reference (sha256 +
        original filename + on-disk path) is what goes into a persisted result
        bundle, so the figure stays integrity-checkable and can be regenerated
        from the recorded results plus the project's plot function.
        """
        src = Path(src_path)
        data = src.read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        art = self.artifacts_dir / f"{sha}{src.suffix}"
        if not art.exists():
            art.write_bytes(data)
        return {
            "__artifact__": art.name,
            "sha256": sha,
            "bytes": len(data),
            "filename": src.name,
            "path": str(art.relative_to(self.root)),
        }

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
    def _change_summary(self, spec_name: str, parent: Optional[str], new_config: dict):
        """Describe how ``new_config`` differs from its parent version.

        Returns ``(subject, [(field, old, new), ...])`` used to build a proper,
        descriptive commit message instead of a bare version label.
        """
        if not parent:
            return "Initial version", []
        try:
            parent_config = self.get_record(spec_name, parent)["config"]
        except Exception:
            return "Update configuration", []
        before, after = flatten(parent_config), flatten(new_config)
        changes = [
            (k, before.get(k), after.get(k))
            for k in sorted(set(before) | set(after))
            if before.get(k) != after.get(k)
        ]
        if not changes:
            return "Re-run with unchanged configuration", []
        fields = [field for field, _, _ in changes]
        if len(fields) == 1:
            subject = f"Change {fields[0]}"
        else:
            shown = ", ".join(fields[:3])
            more = f" (+{len(fields) - 3} more)" if len(fields) > 3 else ""
            subject = f"Change {shown}{more}"
        return subject, changes

    @staticmethod
    def _short(value, limit: int = 80) -> str:
        text = str(value).replace("\n", " ").strip()
        return text if len(text) <= limit else text[: limit - 1] + "\u2026"

    def add_version(
        self, spec_name: str, record: dict, message: str = "", parent: Optional[str] = None
    ) -> str:
        spec_name = _safe_component(spec_name, "spec name")
        index = self._load_index()
        entry = index["specs"].setdefault(spec_name, {"counter": 0, "versions": []})
        if parent is None and entry["versions"]:
            parent = entry["versions"][-1]["id"]
        entry["counter"] += 1
        vid = f"v{entry['counter']}"

        vdir = self.dir / "versions" / spec_name
        vdir.mkdir(parents=True, exist_ok=True)
        (vdir / f"{vid}.json").write_text(
            json.dumps(self._externalize(record), indent=2, default=_json_default),
            encoding="utf-8",
        )

        entry["versions"].append(
            {
                "id": vid,
                "parent": parent,
                "created": record.get("run_id"),
                "stability": record["metrics"].get("stability"),
                "fingerprint": record.get("spec_fingerprint"),
                "message": message,
            }
        )
        self._save_index(index)

        subject_auto, changes = self._change_summary(spec_name, parent, record["config"])
        subject = message.strip() if message and message.strip() else subject_auto
        body = [
            f"Version: {vid}" + (f" (branched from {parent})" if parent else " (root)"),
            f"Spec: {spec_name} @ {record.get('spec_fingerprint', 'n/a')}",
            f"Stability: {record['metrics'].get('stability')}",
        ]
        if changes:
            body.append("")
            body.append("Configuration changes:")
            body += [f"  {f}: {self._short(a)} -> {self._short(b)}" for f, a, b in changes]
        full_message = subject + "\n\n" + "\n".join(body)

        self.git.add("-A")
        try:
            sha = self.git.commit(full_message)
            self.git.tag(f"{spec_name}-{vid}", sha)
        except GitError:
            pass
        return vid

    def get_record(self, spec_name: str, version_id: str) -> dict:
        spec_name = _safe_component(spec_name, "spec name")
        version_id = _safe_component(version_id, "version id")
        path = self.dir / "versions" / spec_name / f"{version_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"Unknown version: {version_id}")
        return self._internalize(json.loads(path.read_text(encoding="utf-8")))

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
        self._commit(f"Tag {spec_name} {version_id} as '{tag}'")

    def latest_with_tag(self, spec_name: str, tag: str):
        t = (tag or "").strip().lower()
        matches = [
            v["id"]
            for v in self.list_versions(spec_name)
            if t in [str(x).lower() for x in v.get("tags", [])]
        ]
        return matches[-1] if matches else None

    def versions_with_tag(self, spec_name: str, tag: str) -> list:
        """All version ids carrying ``tag`` - the cohort selector for aggregation.

        Where :meth:`latest_with_tag` picks one version, an N-way aggregation runs
        over a whole cohort (e.g. every version tagged ``seed``), so it needs the
        full, order-preserved list.
        """
        t = (tag or "").strip().lower()
        return [
            v["id"]
            for v in self.list_versions(spec_name)
            if t in [str(x).lower() for x in v.get("tags", [])]
        ]

    # -- evaluation results ---------------------------------------------- #
    def save_eval(self, spec_name: str, version_id: str, eval_result: dict) -> None:
        spec_name = _safe_component(spec_name, "spec name")
        version_id = _safe_component(version_id, "version id")
        path = self.dir / "versions" / spec_name / f"{version_id}.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        record["eval"] = eval_result
        path.write_text(
            json.dumps(record, indent=2, default=_json_default), encoding="utf-8"
        )
        index = self._load_index()
        for v in index["specs"].get(spec_name, {}).get("versions", []):
            if v["id"] == version_id:
                v["eval"] = eval_result.get("metrics", {})
                break
        self._save_index(index)
        self._commit(f"Record evaluation of {spec_name} {version_id}")

    # -- cohort aggregations (durable, git-tracked result bundles) ------- #
    def save_aggregation(self, spec_name: str, result: dict) -> str:
        """Persist a cohort-aggregation result bundle and register it in the index.

        The bundle JSON (aggregator results + figure references + provenance) is
        committed to git under ``.dow/aggregations/<spec>/<id>.json``; any figure
        *bytes* live in the git-ignored artifact store, referenced by hash. This
        is dow's git-native equivalent of a project's result bundle (JSON + plot),
        making a robustness check a durable, citable, reproducible object.
        """
        spec_name = _safe_component(spec_name, "spec name")
        index = self._load_index()
        entry = index["specs"].setdefault(spec_name, {"counter": 0, "versions": []})
        entry["agg_counter"] = entry.get("agg_counter", 0) + 1
        agg_id = f"a{entry['agg_counter']}"
        result = dict(result)
        result["id"] = agg_id
        adir = self.dir / AGGREGATIONS_DIR / spec_name
        adir.mkdir(parents=True, exist_ok=True)
        (adir / f"{agg_id}.json").write_text(
            json.dumps(result, indent=2, default=_json_default), encoding="utf-8"
        )
        entry.setdefault("aggregations", []).append({
            "id": agg_id,
            "members": result.get("members", []),
            "created": result.get("created"),
            "figures": [f.get("filename") for f in result.get("figures", [])],
        })
        self._save_index(index)
        self._commit(
            f"Aggregate {spec_name} over {len(result.get('members', []))} versions ({agg_id})"
        )
        return agg_id

    def list_aggregations(self, spec_name: str) -> list:
        if not self.index_path.exists():
            return []
        return self._load_index().get("specs", {}).get(spec_name, {}).get("aggregations", [])

    def get_aggregation(self, spec_name: str, agg_id: str) -> dict:
        spec_name = _safe_component(spec_name, "spec name")
        agg_id = _safe_component(agg_id, "aggregation id")
        path = self.dir / AGGREGATIONS_DIR / spec_name / f"{agg_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"Unknown aggregation: {agg_id}")
        return json.loads(path.read_text(encoding="utf-8"))

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
            raise ValueError("No versions yet. Run 'dow commit' first.")
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
