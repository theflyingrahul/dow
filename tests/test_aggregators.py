"""Upgrade E end-to-end: a project supplies its own N-way *aggregators* (dow ships
none). Where a comparator sees two versions, an aggregator sees a whole cohort
(K seeds / judges / prompt wordings) aligned per item through each member's
captured ``payload`` - what a reliability coefficient over K raters needs. The
structured result is persisted as a durable, git-tracked bundle."""
import re

from dow import service

OPS_PY = '''
def relabel(req):
    rater = int(req.config.get("params", {}).get("rater", 0))
    base = [4, 4, 3, 2, 1]
    labels = [max(1, x - (1 if (i + rater) % 3 == 0 else 0)) for i, x in enumerate(base)]
    return {"output": f"rater-{rater}", "payload": {"labels": labels}}
'''

AGG_PY = '''
import itertools


def cohort_agreement(cctx):
    grids = [m.payload["labels"] for m in cctx.members]
    n = len(grids[0])
    unanimous = sum(1 for i in range(n) if len({g[i] for g in grids}) == 1) / n
    flips = [sum(1 for x, y in zip(a, b) if x != y) / n
             for a, b in itertools.combinations(grids, 2)]
    return {
        "n_raters": float(len(grids)),
        "unanimous_rate": {"estimate": unanimous, "ci_low": unanimous - 0.1,
                           "ci_high": unanimous + 0.1},
        "mean_pairwise_flip": sum(flips) / len(flips) if flips else 0.0,
        "per_rater": [{"id": rid} for rid in cctx.ids],
    }
'''

SPEC_YAML = '''spec_version: 1
name: t
operation: relabel
params:
  rater: 0
model:
  provider: python
  name: "ops.py:relabel"
  version: relabel-1
sampling:
  seed: 7
evaluation:
  samples: 1
  metrics: []
  aggregators:
    - "aggs.py:cohort_agreement"
inputs:
  - "x"
'''


def _project(tmp_path, spec=SPEC_YAML):
    (tmp_path / "ops.py").write_text(OPS_PY, encoding="utf-8")
    (tmp_path / "aggs.py").write_text(AGG_PY, encoding="utf-8")
    (tmp_path / "specs").mkdir()
    (tmp_path / "specs" / "t.yaml").write_text(spec, encoding="utf-8")


def _set_rater(tmp_path, rater):
    p = tmp_path / "specs" / "t.yaml"
    p.write_text(re.sub(r"rater: \d+", f"rater: {rater}", p.read_text(encoding="utf-8"), count=1),
                 encoding="utf-8")


def _build_cohort(tmp_path):
    """Commit a 3-version cohort (raters 0, 1, 2), each branched from v1."""
    root = str(tmp_path)
    service.commit(root, name="t", message="rater 0")
    for r in (1, 2):
        _set_rater(tmp_path, r)
        service.commit(root, name="t", from_version="v1")
    return root


def test_nway_aggregation_over_full_cohort(tmp_path):
    _project(tmp_path)
    root = _build_cohort(tmp_path)

    res = service.aggregate(root, name="t")  # default cohort = every version
    assert res["aggregatorError"] is None
    assert res["members"] == ["v1", "v2", "v3"]

    aggs = res["aggregators"]
    # a plain number is coerced to float; the whole cohort was seen at once
    assert aggs["n_raters"] == 3.0
    # a structured {estimate, ci_low, ci_high} band is stored verbatim
    assert set(aggs["unanimous_rate"]) == {"estimate", "ci_low", "ci_high"}
    # a table (list of rows) survives intact - one row per cohort member
    assert isinstance(aggs["per_rater"], list) and len(aggs["per_rater"]) == 3
    assert [row["id"] for row in aggs["per_rater"]] == ["v1", "v2", "v3"]

    # the bundle is persisted, listed, and retrievable (a citable result object)
    assert res["id"] == "a1"
    listed = service.aggregations(root, name="t")["aggregations"]
    assert [a["id"] for a in listed] == ["a1"]
    got = service.get_aggregation(root, name="t", agg_id="a1")
    assert got["aggregators"]["n_raters"] == 3.0
    assert got["members"] == ["v1", "v2", "v3"]


def test_cohort_selection_by_tag(tmp_path):
    _project(tmp_path)
    root = _build_cohort(tmp_path)
    service.tag(root, name="t", label="seed", version="v1")
    service.tag(root, name="t", label="seed", version="v3")

    res = service.aggregate(root, name="t", tag="seed")
    assert res["members"] == ["v1", "v3"]
    assert res["aggregators"]["n_raters"] == 2.0


def test_explicit_cohort_and_error_is_captured_not_raised(tmp_path):
    _project(tmp_path, spec=SPEC_YAML.replace("aggs.py:cohort_agreement", "aggs.py:missing"))
    root = _build_cohort(tmp_path)

    res = service.aggregate(root, name="t", versions=["v1", "v2"])
    # explicit selection honored
    assert res["members"] == ["v1", "v2"]
    # a broken aggregator ref is reported, not raised; the run still persists
    assert res["aggregatorError"] is not None
    assert res["aggregators"] == {}
    assert res["id"] == "a1"
