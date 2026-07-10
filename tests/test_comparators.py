"""Upgrade A end-to-end: a project supplies its own paired *comparators* (dow
ships none). Through the ``python`` provider a version captures a per-item
``payload``; a comparator receives both versions aligned per item and may return
a scalar, a ``{estimate, ci_low, ci_high}`` band, or a bag of named metrics.
Attribution still pins the single changed field."""
from dow import service

OPS_PY = '''
def relabel(req):
    variant = req.config.get("params", {}).get("variant", "baseline")
    base = [4, 4, 3, 2, 1]
    labels = [max(1, x - 1) for x in base] if variant == "shift" else list(base)
    return {"output": variant, "payload": {"labels": labels}}
'''

METRICS_PY = '''
def flip_rate(cctx):
    a = cctx.a.payload["labels"]
    b = cctx.b.payload["labels"]
    return sum(1 for x, y in zip(a, b) if x != y) / len(a)

def band(cctx):
    a = cctx.a.payload["labels"]
    b = cctx.b.payload["labels"]
    est = sum(abs(x - y) for x, y in zip(a, b)) / len(a)
    return {"mad": {"estimate": est, "ci_low": est - 0.1, "ci_high": est + 0.1}}
'''

SPEC_YAML = '''spec_version: 1
name: t
operation: relabel
params:
  variant: baseline
model:
  provider: python
  name: "ops.py:relabel"
  version: relabel-1
sampling:
  seed: 7
evaluation:
  samples: 1
  metrics: []
  comparators:
    - "metrics.py:flip_rate"
    - "metrics.py:band"
inputs:
  - "x"
'''


def _project(tmp_path, comparators=SPEC_YAML):
    (tmp_path / "ops.py").write_text(OPS_PY, encoding="utf-8")
    (tmp_path / "metrics.py").write_text(METRICS_PY, encoding="utf-8")
    (tmp_path / "specs").mkdir()
    (tmp_path / "specs" / "t.yaml").write_text(comparators, encoding="utf-8")


def _perturb_to_shift(tmp_path):
    p = tmp_path / "specs" / "t.yaml"
    p.write_text(p.read_text(encoding="utf-8").replace("variant: baseline", "variant: shift"),
                 encoding="utf-8")


def test_paired_comparators_end_to_end(tmp_path):
    _project(tmp_path)
    root = str(tmp_path)

    service.commit(root, name="t", message="baseline")
    _perturb_to_shift(tmp_path)
    service.commit(root, name="t", from_version="v1")

    c = service.compare(root, name="t", a="v1", b="v2")
    assert c["comparatorError"] is None
    # base [4,4,3,2,1] -> shift [3,3,2,1,1]: 4 of 5 items move.
    assert abs(c["comparators"]["flip_rate"] - 0.8) < 1e-9
    # A structured metric value is stored verbatim (estimate + CI band).
    mad = c["comparators"]["mad"]
    assert set(mad) == {"estimate", "ci_low", "ci_high"}
    assert abs(mad["estimate"] - 0.8) < 1e-9

    # Attribution: exactly one field changed -> not confounded, cause pinned.
    e = service.explain(root, name="t", a="v1", b="v2")
    assert e["confounded"] is False
    assert e["cause"]["field"] == "params.variant"
    assert (e["cause"]["from"], e["cause"]["to"]) == ("baseline", "shift")


def test_comparator_error_is_captured_not_raised(tmp_path):
    _project(tmp_path, comparators=SPEC_YAML.replace("metrics.py:flip_rate", "metrics.py:missing"))
    root = str(tmp_path)

    service.commit(root, name="t")
    _perturb_to_shift(tmp_path)
    service.commit(root, name="t", from_version="v1")

    c = service.compare(root, name="t", a="v1", b="v2")
    # The broken comparator is reported, but built-in signals still return.
    assert c["comparatorError"] is not None
    assert c["comparators"] == {}
    assert "verdict" in c
