"""Execute a specification and build the run record (the behavior snapshot)."""
from __future__ import annotations

import platform
import sys
from datetime import datetime, timezone

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


def execute(spec) -> dict:
    """Run the spec ``samples`` times and capture everything about the inference."""
    provider = get_provider(spec)
    embedder = get_embedder(spec.evaluation.embedding_model)
    n = max(1, int(spec.evaluation.samples))
    input_text = spec.inputs[0] if spec.inputs else ""

    samples = []
    outputs = []
    runtime_meta: dict = {}
    for i in range(n):
        g = provider.generate(input_text, i)
        samples.append(
            {"output": g.output, "tokens": g.tokens, "latency_ms": g.latency_ms}
        )
        outputs.append(g.output)
        runtime_meta = {
            "provider": provider.name,
            "model_name": spec.model.name,
            "model_version": g.model_version,
            "model_revision": g.model_revision,
            "system_fingerprint": g.system_fingerprint,
            "seed": spec.sampling.seed,
            "embedding_model": embedder.name,
        }

    embs = embedder.embed(outputs)
    stab = stability(embs)

    return {
        "spec_name": spec.name,
        "spec_fingerprint": spec.fingerprint(),
        "run_id": _now_id(),
        "input": input_text,
        "config": spec.to_dict(),
        "runtime": {
            **runtime_meta,
            "platform": platform.platform(),
            "library_versions": library_versions(),
        },
        "samples": samples,
        "metrics": {"stability": round(stab, 4)},
    }
