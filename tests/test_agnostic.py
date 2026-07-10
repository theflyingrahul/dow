"""dow is data-structure agnostic.

Two independent guarantees, both exercised end-to-end here:

1. The *built-in* behavioral signals (semantic drift, stability, output
   difference) assume the output is text. A project whose captured behavior is
   not free text sets ``embedding_model: none``; dow then tracks the spec change
   and the project's own plugged-in metrics without inventing a lexical number.

2. A version's per-item ``payload`` may be any in-memory structure the project's
   provider returns - numpy arrays, sets, dataclasses, numpy scalars - and dow
   persists it faithfully (as a JSON-native projection) without the project
   pre-converting anything. How the project stores its data never constrains dow.
"""
from dow import service
from dow.store import Store

OPS_PY = """
import numpy as np
from dataclasses import dataclass


@dataclass
class Meta:
    rater: str
    n: int


def rate(req):
    variant = req.config.get("params", {}).get("variant", "baseline")
    base = [4, 4, 3, 2, 1]
    labels = [max(1, x - 1) for x in base] if variant == "shift" else list(base)
    payload = {
        "labels": np.asarray(labels, dtype=np.int64),   # numpy array
        "seen": {variant},                              # a set
        "meta": Meta(rater=variant, n=len(labels)),     # a dataclass instance
        "score": np.float32(0.5),                       # a numpy scalar
    }
    # output is a non-prose string label; the real signal lives in payload.
    return {"output": "rated:" + variant, "payload": payload}
"""

METRICS_PY = """
def flip_rate(cctx):
    a = cctx.a.payload["labels"]
    b = cctx.b.payload["labels"]
    return sum(1 for x, y in zip(a, b) if x != y) / len(a)
"""

EVALS_PY = """
def n_labels(ctx):
    return float(len(ctx.payload["labels"])) if ctx.payload else 0.0
"""

SPEC_YAML = """spec_version: 1
name: t
operation: rate
params:
  variant: baseline
model:
  provider: python
  name: "ops.py:rate"
  version: rate-1
sampling:
  seed: 7
evaluation:
  embedding_model: none
  samples: 1
  metrics:
    - "evals.py:n_labels"
  comparators:
    - "metrics.py:flip_rate"
inputs:
  - "x"
"""


def _project(tmp_path):
    (tmp_path / "ops.py").write_text(OPS_PY, encoding="utf-8")
    (tmp_path / "metrics.py").write_text(METRICS_PY, encoding="utf-8")
    (tmp_path / "evals.py").write_text(EVALS_PY, encoding="utf-8")
    (tmp_path / "specs").mkdir()
    (tmp_path / "specs" / "t.yaml").write_text(SPEC_YAML, encoding="utf-8")


def _to_shift(tmp_path):
    p = tmp_path / "specs" / "t.yaml"
    p.write_text(p.read_text(encoding="utf-8").replace("variant: baseline", "variant: shift"),
                 encoding="utf-8")


def test_non_text_outputs_are_opaque_but_still_tracked(tmp_path):
    _project(tmp_path)
    root = str(tmp_path)

    c1 = service.commit(root, name="t", message="baseline")
    # No built-in text signal is invented for a non-text output...
    assert c1["stability"] is None
    # ...but the project's own numeric evaluator still runs at capture.
    assert c1.get("eval", {}).get("n_labels") == 5.0

    _to_shift(tmp_path)
    service.commit(root, name="t", from_version="v1")

    c = service.compare(root, name="t", a="v1", b="v2")
    assert c["driftEnabled"] is False
    assert c["embeddingModel"] == "none"
    assert c["semanticDrift"] is None
    assert c["stabilityA"] is None and c["stabilityB"] is None
    assert c["outputDifference"] is None
    assert c["verdict"] is None
    # The project's plugged-in comparator is unaffected by drift being off.
    assert c["comparatorError"] is None
    assert abs(c["comparators"]["flip_rate"] - 0.8) < 1e-9

    # Change tracking + attribution are intact without any embedding.
    e = service.explain(root, name="t", a="v1", b="v2")
    assert e["driftEnabled"] is False
    assert e["confounded"] is False
    assert e["cause"]["field"] == "params.variant"
    assert (e["cause"]["from"], e["cause"]["to"]) == ("baseline", "shift")

    # None-valued built-in signals never crash the read/render paths.
    h = service.history(root, name="t")
    assert [v["stability"] for v in h["versions"]] == [None, None]
    assert service.inspect(root, name="t", version="v1")["stability"] is None

    t = service.tree(root, name="t", mermaid=True)
    assert len(t["nodes"]) == 2
    assert t["nodes"][0]["stability"] is None
    assert t["nodes"][1]["edge"]["semanticDrift"] is None
    assert "gitGraph" in t["mermaid"]


def test_exotic_payload_persists_and_rehydrates(tmp_path):
    _project(tmp_path)
    root = str(tmp_path)
    service.commit(root, name="t")

    # Round-tripped through the git-backed JSON store, the payload comes back as a
    # faithful JSON-native projection - no project-side pre-conversion required.
    rec = Store(root).get_record("t", "v1")
    pl = rec["payload"]
    assert pl["labels"] == [4, 4, 3, 2, 1]              # numpy array -> list
    assert pl["score"] == 0.5                           # numpy scalar -> float
    assert pl["seen"] == ["baseline"]                   # set -> list
    assert pl["meta"] == {"rater": "baseline", "n": 5}  # dataclass -> dict
    assert rec.get("_payload_integrity") != "sha256-mismatch"
