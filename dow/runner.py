"""Execute a specification and build the run record (the behavior snapshot)."""
from __future__ import annotations

import hashlib
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

from .embeddings import get_embedder
from .metrics import stability
from .providers import get_provider


def _now_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def library_versions() -> dict:
    versions = {"python": sys.version.split()[0]}
    for mod in ("numpy", "openai", "sentence_transformers", "yaml", "typer", "rich"):
        try:
            m = __import__(mod)
            versions[mod] = getattr(m, "__version__", "unknown")
        except Exception:
            pass
    return versions


def _hash_file(path: Path) -> dict:
    """Content hash + size of an input artifact, for reproducible provenance."""
    h = hashlib.sha256()
    size = 0
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
            size += len(chunk)
    return {"kind": "file", "sha256": h.hexdigest(), "bytes": size}


def _hash_directory(path: Path) -> dict:
    """Deterministically bind every regular file in ``path`` without following links."""
    h = hashlib.sha256()
    total = 0
    files = 0
    entries = sorted(path.rglob("*"), key=lambda item: item.relative_to(path).as_posix())
    for item in entries:
        if item.is_symlink():
            raise ValueError(f"directory artifact contains a symlink: {item}")
        if not item.is_file():
            continue
        relative = item.relative_to(path).as_posix().encode("utf-8")
        size = item.stat().st_size
        h.update(relative)
        h.update(b"\0")
        h.update(str(size).encode("ascii"))
        h.update(b"\0")
        with item.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        h.update(b"\0")
        total += size
        files += 1
    return {
        "kind": "directory",
        "sha256": h.hexdigest(),
        "bytes": total,
        "files": files,
    }


def _hash_artifact(path: Path) -> dict:
    if path.is_symlink():
        raise ValueError(f"input artifact may not be a symlink: {path}")
    if path.is_dir():
        return _hash_directory(path)
    return _hash_file(path)


def input_artifacts(spec, base_dir=None) -> list:
    """Resolve and hash any ``{artifact: path, ...}`` inputs for provenance.

    dow never parses the artifact - a ``python`` provider/operation loads it. dow
    only records the actual on-disk ``sha256`` (and byte size) so a captured run
    can be verified and reproduced. Missing files are recorded, not fatal.
    """
    base = Path(base_dir) if base_dir else Path.cwd()
    out = []
    for item in getattr(spec, "inputs", []) or []:
        if isinstance(item, dict) and "artifact" in item:
            ref = str(item["artifact"])
            path = (base / ref).resolve() if not Path(ref).is_absolute() else Path(ref)
            entry = {"artifact": ref, "declared_sha256": item.get("sha256")}
            if path.exists():
                entry.update(_hash_artifact(path))
            else:
                entry["missing"] = True
            out.append(entry)
    return out


def execute(spec, base_dir=None) -> dict:
    """Run the spec ``samples`` times and capture everything about the inference."""
    provider = get_provider(spec, base_dir)
    embedder = get_embedder(spec.evaluation.embedding_model)
    n = max(1, int(spec.evaluation.samples))
    input_obj = spec.inputs[0] if spec.inputs else ""

    samples = []
    outputs = []
    payloads = []
    runtime_meta: dict = {}
    for i in range(n):
        g = provider.generate(input_obj, i)
        sample = {"output": g.output, "tokens": g.tokens, "latency_ms": g.latency_ms}
        if g.payload is not None:
            sample["payload"] = g.payload
        samples.append(sample)
        outputs.append(g.output)
        payloads.append(g.payload)
        runtime_meta = {
            "provider": provider.name,
            "model_name": spec.model.name,
            "model_version": g.model_version,
            "model_revision": g.model_revision,
            "system_fingerprint": g.system_fingerprint,
            "seed": spec.sampling.seed,
            "embedding_model": embedder.name,
        }

    metrics: dict = {}
    if getattr(embedder, "enabled", True):
        embs = embedder.embed(outputs)
        metrics["stability"] = round(stability(embs), 4)

    present = [p for p in payloads if p is not None]
    if not present:
        payload = None
    elif n == 1:
        payload = payloads[0]
    else:
        payload = payloads

    record = {
        "spec_name": spec.name,
        "spec_fingerprint": spec.fingerprint(),
        "run_id": _now_id(),
        "input": input_obj,
        "config": spec.to_dict(),
        "runtime": {
            **runtime_meta,
            "input_artifacts": input_artifacts(spec, base_dir),
            "platform": platform.platform(),
            "library_versions": library_versions(),
        },
        "samples": samples,
        "metrics": metrics,
    }
    if payload is not None:
        record["payload"] = payload
    return record
