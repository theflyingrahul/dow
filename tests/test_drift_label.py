"""Feature: the built-in drift signal is labelled HONESTLY for its embedder.

dow's ``semantic_drift`` is ``1 - cosine`` of two mean output embeddings, so what
it measures depends entirely on the embedder: the default hashing embedder is
bag-of-words, so the number is *lexical* (word overlap), not semantic. dow must
say so - in the JSON (`driftKind`), in the human render ("Lexical drift"), and in
help - rather than over-claim "semantic" for a lexical default.
"""
from __future__ import annotations

from dow import report, service
from dow.embeddings import (
    HashingEmbedder,
    NullEmbedder,
    OpenAIEmbedder,
    SentenceTransformerEmbedder,
    drift_label,
    get_embedder,
)

# --------------------------------------------------------------------------- #
# unit: label helper + per-embedder kind
# --------------------------------------------------------------------------- #


def test_drift_label_is_honest_per_kind():
    assert drift_label("lexical") == "Lexical drift"
    assert drift_label("semantic") == "Semantic drift"
    # unknown / disabled kinds fall back to a neutral word, never "semantic"
    assert drift_label(None) == "Drift"
    assert drift_label("none") == "Drift"
    # lower-case variant for mid-sentence use
    assert drift_label("lexical", capitalized=False) == "lexical drift"
    assert drift_label("semantic", capitalized=False) == "semantic drift"


def test_embedder_kinds():
    # the default (offline) embedder is lexical, and advertises it
    assert HashingEmbedder(256).kind == "lexical"
    assert get_embedder("hashing-256").kind == "lexical"
    assert get_embedder("").kind == "none" or isinstance(get_embedder(""), NullEmbedder)
    assert NullEmbedder().kind == "none"
    # real model backends are the only ones that may claim "semantic"
    assert SentenceTransformerEmbedder.kind == "semantic"
    assert OpenAIEmbedder.kind == "semantic"


# --------------------------------------------------------------------------- #
# end-to-end: driftKind flows through compare/explain/tree with the real default
# --------------------------------------------------------------------------- #
ECHO_OPS = '''
def gen(req):
    return {"output": req.config.get("params", {}).get("text", "")}
'''

ECHO_SPEC = '''spec_version: 1
name: g
operation: gen
params:
  text: "alpha beta gamma"
model:
  provider: python
  name: "ops.py:gen"
  version: gen-1
sampling:
  seed: 7
evaluation:
  samples: 1
inputs:
  - "x"
'''


def _echo_project(tmp_path, text=None):
    (tmp_path / "ops.py").write_text(ECHO_OPS, encoding="utf-8")
    (tmp_path / "specs").mkdir()
    spec = ECHO_SPEC if text is None else ECHO_SPEC.replace("alpha beta gamma", text)
    (tmp_path / "specs" / "g.yaml").write_text(spec, encoding="utf-8")


def _set_text(tmp_path, text):
    import re

    p = tmp_path / "specs" / "g.yaml"
    p.write_text(re.sub(r'text: ".*"', f'text: "{text}"', p.read_text(encoding="utf-8"), count=1),
                 encoding="utf-8")


def test_compare_reports_lexical_kind_for_default_embedder(tmp_path):
    _echo_project(tmp_path)
    root = str(tmp_path)
    service.commit(root, name="g")                 # v1
    _set_text(tmp_path, "delta epsilon zeta")      # different words -> some drift
    service.commit(root, name="g")                 # v2

    out = service.compare(root, name="g")
    assert out["driftEnabled"] is True
    assert out["driftKind"] == "lexical"           # NOT "semantic": the default is bag-of-words
    assert out["embeddingModel"] == "hashing-256"
    assert isinstance(out["semanticDrift"], float)

    exp = service.explain(root, name="g")
    assert exp["driftKind"] == "lexical"

    tr = service.tree(root, name="g")
    assert tr["driftKind"] == "lexical"


def test_human_render_says_lexical_not_semantic(tmp_path):
    _echo_project(tmp_path)
    root = str(tmp_path)
    service.commit(root, name="g")
    _set_text(tmp_path, "delta epsilon zeta")
    service.commit(root, name="g")
    r = service.compare_records(service.Store(root), "g", "v1", "v2")

    with report.console.capture() as cap:
        report.print_compare("g", "v1", "v2", r["config_diff"], r["output_difference"],
                             r["semantic_drift"], r["stability_a"], r["stability_b"],
                             r["verdict"], r["thresholds"], r.get("drift_kind"))
    text = cap.get()
    assert "Lexical drift" in text
    assert "Semantic drift" not in text
