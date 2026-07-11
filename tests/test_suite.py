"""Suite end-to-end: a project aggregates versions across *several* specs (the
check x model x domain x temperature matrix). dow only wires the members in - it
ships none of the coefficients or the plotting library. Each member keeps its own
captured config (so the aggregator buckets by spec/axis) and payload (aligned per
item), and the cross-spec result persists as a durable, git-tracked suite bundle."""
import re

import pytest

from dow import service

# One op per axis; each emits per-item ordinal labels in its payload, shifted by a
# param so different versions/specs disagree in a controlled way.
OPS_PY = '''
def probe(req):
    p = req.config.get("params", {})
    shift = int(p.get("shift", 0))
    base = [4, 4, 3, 2, 1]
    labels = [max(1, x - (1 if (i + shift) % 3 == 0 else 0)) for i, x in enumerate(base)]
    return {"output": f"{req.config.get('name')}-shift{shift}",
            "payload": {"labels": labels, "shift": shift}}
'''

# A cross-spec aggregator: it buckets members by their spec (via cctx.specs) and
# reads each member's captured config (the axis coords), then returns a matrix.
SUITE_AGG_PY = '''
def agg_matrix(cctx):
    by_spec = {}
    for spec, m in zip(cctx.specs, cctx.members):
        by_spec.setdefault(spec, 0)
        by_spec[spec] += 1
    # prove the aggregator saw every member's own config (spec name + params)
    names = sorted({m.config.get("name") for m in cctx.members})
    shifts = sorted({m.payload["shift"] for m in cctx.members})
    return {
        "n_members": float(len(cctx.members)),
        "specs_seen": names,
        "per_spec_counts": {k: float(v) for k, v in by_spec.items()},
        "distinct_shifts": [float(s) for s in shifts],
        "member_ids": list(cctx.ids),
    }
'''

SUITE_PLOT_PY = '''
import os


def plot_matrix(pctx):
    os.makedirs(pctx.out_dir, exist_ok=True)
    path = os.path.join(pctx.out_dir, "matrix.txt")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(str(pctx.results.get("per_spec_counts", {})))
    return path
'''


def _spec_yaml(name, agg=True):
    return f'''spec_version: 1
name: {name}
operation: probe
params:
  shift: 0
model:
  provider: python
  name: "ops.py:probe"
  version: probe-1
sampling:
  seed: 7
evaluation:
  samples: 1
  metrics: []
  aggregators:
    - "aggs.py:agg_matrix"
inputs:
  - "x"
'''


SUITE_YAML = '''name: robustness_matrix
task: "check x axis matrix"
specs:
  - alpha
  - beta
select: all
evaluation:
  aggregators:
    - "suite_aggs.py:agg_matrix"
  plots:
    - "suite_plots.py:plot_matrix"
'''


def _project(tmp_path, suite=SUITE_YAML):
    (tmp_path / "ops.py").write_text(OPS_PY, encoding="utf-8")
    (tmp_path / "suite_aggs.py").write_text(SUITE_AGG_PY, encoding="utf-8")
    (tmp_path / "suite_plots.py").write_text(SUITE_PLOT_PY, encoding="utf-8")
    (tmp_path / "specs").mkdir()
    (tmp_path / "specs" / "alpha.yaml").write_text(_spec_yaml("alpha"), encoding="utf-8")
    (tmp_path / "specs" / "beta.yaml").write_text(_spec_yaml("beta"), encoding="utf-8")
    if suite is not None:
        (tmp_path / "specs" / "robustness_matrix.suite.yaml").write_text(suite, encoding="utf-8")


def _set_shift(tmp_path, spec, shift):
    p = tmp_path / "specs" / f"{spec}.yaml"
    p.write_text(re.sub(r"shift: \d+", f"shift: {shift}", p.read_text(encoding="utf-8"), count=1),
                 encoding="utf-8")


def _build_matrix(tmp_path):
    """Commit 2 versions of alpha (shift 0,1) and 2 of beta (shift 0,2)."""
    root = str(tmp_path)
    service.commit(root, name="alpha", message="a shift 0")
    _set_shift(tmp_path, "alpha", 1)
    service.commit(root, name="alpha", from_version="v1")
    service.commit(root, name="beta", message="b shift 0")
    _set_shift(tmp_path, "beta", 2)
    service.commit(root, name="beta", from_version="v1")
    return root


def test_suite_aggregates_across_specs(tmp_path):
    _project(tmp_path)
    root = _build_matrix(tmp_path)

    res = service.aggregate_suite(root, name="robustness_matrix")
    assert res["aggregatorError"] is None, res
    assert res["kind"] == "suite"
    # members are spec:version across BOTH specs, full matrix (select all)
    assert res["members"] == ["alpha:v1", "alpha:v2", "beta:v1", "beta:v2"]
    assert res["specs"] == ["alpha", "beta"]

    aggs = res["aggregators"]
    assert aggs["n_members"] == 4.0
    # the aggregator saw each member's own spec name + config
    assert aggs["specs_seen"] == ["alpha", "beta"]
    assert aggs["per_spec_counts"] == {"alpha": 2.0, "beta": 2.0}
    assert aggs["member_ids"] == ["alpha:v1", "alpha:v2", "beta:v1", "beta:v2"]

    # persisted as a durable, listable, retrievable suite bundle
    assert res["id"] == "a1"
    listed = service.suite_aggregations(root, name="robustness_matrix")["aggregations"]
    assert [a["id"] for a in listed] == ["a1"]
    got = service.get_suite_aggregation(root, name="robustness_matrix", agg_id="a1")
    assert got["aggregators"]["per_spec_counts"] == {"alpha": 2.0, "beta": 2.0}


def test_suite_select_latest(tmp_path):
    _project(tmp_path)
    root = _build_matrix(tmp_path)
    res = service.aggregate_suite(root, name="robustness_matrix", select="latest")
    assert res["members"] == ["alpha:v2", "beta:v2"]
    assert res["aggregators"]["per_spec_counts"] == {"alpha": 1.0, "beta": 1.0}


def test_suite_select_tag(tmp_path):
    _project(tmp_path)
    root = _build_matrix(tmp_path)
    # tag one version in each spec with the same label - a cross-spec cohort
    service.tag(root, name="alpha", label="golden", version="v1")
    service.tag(root, name="beta", label="golden", version="v2")
    res = service.aggregate_suite(root, name="robustness_matrix", select="golden")
    assert res["members"] == ["alpha:v1", "beta:v2"]
    assert res["labels"] == ["golden", "golden"]


def test_suite_plot_artifact_stored(tmp_path):
    _project(tmp_path)
    root = _build_matrix(tmp_path)
    res = service.aggregate_suite(root, name="robustness_matrix", plot=True)
    assert res["plotError"] is None, res
    assert len(res["figures"]) == 1
    assert res["figures"][0].get("filename")


def test_suite_aggregator_error_captured_not_raised(tmp_path):
    _project(tmp_path, suite=SUITE_YAML.replace("suite_aggs.py:agg_matrix", "suite_aggs.py:missing"))
    root = _build_matrix(tmp_path)
    res = service.aggregate_suite(root, name="robustness_matrix")
    # a broken aggregator ref is reported, not raised; the run still persists
    assert res["aggregatorError"] is not None
    assert res["aggregators"] == {}
    assert res["id"] == "a1"


def test_suite_requires_specs_and_aggregators(tmp_path):
    # missing specs:
    _project(tmp_path, suite='name: bad\nspecs: []\nevaluation:\n  aggregators: ["suite_aggs.py:agg_matrix"]\n')
    root = str(tmp_path)
    _build_matrix(tmp_path)
    with pytest.raises(service.DowError):
        service.aggregate_suite(root, name="bad")


def test_suite_missing_aggregators_errors(tmp_path):
    _project(tmp_path, suite='name: noagg\nspecs: [alpha, beta]\nevaluation:\n  aggregators: []\n')
    root = str(tmp_path)
    _build_matrix(tmp_path)
    with pytest.raises(service.DowError):
        service.aggregate_suite(root, name="noagg")


def test_suite_manifest_not_treated_as_spec(tmp_path):
    """The .suite.yaml must not leak into the inference-spec code paths."""
    _project(tmp_path)
    _build_matrix(tmp_path)
    root = str(tmp_path)
    spec_names = [s["name"] for s in service.list_specs(root)["specs"]]
    assert "robustness_matrix" not in spec_names
    assert set(spec_names) == {"alpha", "beta"}
    # and the suite is discoverable on its own channel
    suites = [s["name"] for s in service.list_suites(root)["suites"]]
    assert suites == ["robustness_matrix"]


def test_suite_empty_selection_errors(tmp_path):
    """A suite over specs with no committed versions is a clear error."""
    _project(tmp_path)
    root = str(tmp_path)  # nothing committed
    with pytest.raises(service.DowError):
        service.aggregate_suite(root, name="robustness_matrix")


def test_cli_spec_resolution_ignores_suite_manifest(tmp_path, monkeypatch):
    """The CLI's own spec enumeration (drives commit/history/compare/... auto-
    resolution) must exclude .suite.yaml, or a lone spec + a suite would be
    mis-seen as two specs (and a lone suite mis-run as an inference spec)."""
    from dow import cli

    _project(tmp_path)  # alpha.yaml, beta.yaml, robustness_matrix.suite.yaml
    monkeypatch.chdir(tmp_path)
    names = sorted(f.stem for f in cli._spec_files())
    assert names == ["alpha", "beta"]

    # a project with a single real spec + a suite manifest auto-resolves the spec
    (tmp_path / "specs" / "beta.yaml").unlink()
    assert cli._find_spec_name(None) == "alpha"


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__, "-q", *sys.argv[1:]]))
