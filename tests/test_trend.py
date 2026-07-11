"""Feature: ``dow trend`` - the longitudinal sibling of ``dow compare``. Where
compare contrasts two versions, trend follows a metric across a spec's WHOLE
version history (tree-aware), so a slow drift over many iterations is visible.
dow computes no new numbers here: it lines up the built-in ``stability`` and the
project's own ``evaluation.metrics`` scores already recorded per version, reporting
each value with its change vs. the previous version and vs. the baseline."""
import re

from dow import service

# python provider op: the whole behavior is driven by params.level so a test can
# dial an exact metric value per version.
OPS_PY = '''
def gen(req):
    level = int(req.config.get("params", {}).get("level", 0))
    return {"output": f"level-{level}", "payload": {"level": level}}
'''

# a project evaluator (dow ships none). Returns a project metric read straight from
# the spec, and deliberately produces NO metric for level 0 (a sparse series).
EVAL_PY = '''
def score(ctx):
    level = int(ctx.config.get("params", {}).get("level", 0))
    if level == 0:
        return {}
    return {"accuracy": level / 10.0}
'''

PLOT_PY = '''
import os


def plot_trend(pctx):
    out = os.path.join(pctx.out_dir, "trend.svg")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("<svg/>")
    return [out]
'''

SPEC_YAML = '''spec_version: 1
name: t
operation: gen
params:
  level: 5
model:
  provider: python
  name: "ops.py:gen"
  version: gen-1
sampling:
  seed: 7
evaluation:
  embedding_model: none
  samples: 1
  metrics:
    - "evals.py:score"
  plots:
    - "plots.py:plot_trend"
inputs:
  - "x"
'''

# a plain text spec keeps dow's built-in stability on (default embedding).
TEXT_SPEC_YAML = '''spec_version: 1
name: tt
prompt:
  template: "Summarize: {input}"
model:
  provider: mock
  name: mock
  version: m-1
sampling:
  seed: 7
evaluation:
  samples: 3
inputs:
  - "the quick brown fox"
'''


def _project(tmp_path, spec=SPEC_YAML):
    (tmp_path / "ops.py").write_text(OPS_PY, encoding="utf-8")
    (tmp_path / "evals.py").write_text(EVAL_PY, encoding="utf-8")
    (tmp_path / "plots.py").write_text(PLOT_PY, encoding="utf-8")
    (tmp_path / "specs").mkdir()
    (tmp_path / "specs" / "t.yaml").write_text(spec, encoding="utf-8")


def _set_level(tmp_path, level):
    p = tmp_path / "specs" / "t.yaml"
    p.write_text(re.sub(r"level: \d+", f"level: {level}", p.read_text(encoding="utf-8"), count=1),
                 encoding="utf-8")


def _history(tmp_path, levels):
    """Commit one version per level (each a config change from the last)."""
    root = str(tmp_path)
    service.commit(root, name="t")  # v1 at the spec's initial level
    for lv in levels:
        _set_level(tmp_path, lv)
        service.commit(root, name="t")
    return root


def test_trend_series_deltas_and_change_labels(tmp_path):
    _project(tmp_path)              # v1 level=5 -> accuracy 0.5
    root = _history(tmp_path, [7, 6])  # v2 0.7, v3 0.6

    res = service.trend(root, name="t", metric="accuracy")
    assert res["metrics"] == ["accuracy"]
    assert res["count"] == 3
    seq = res["series"]["accuracy"]
    assert [p["id"] for p in seq] == ["v1", "v2", "v3"]

    # baseline: no previous, no baseline delta
    assert seq[0]["value"] == 0.5
    assert seq[0]["change"] == "baseline"
    assert seq[0]["deltaPrev"] is None and seq[0]["deltaBaseline"] is None

    # each later version reports change vs. prev AND vs. baseline (v1)
    assert seq[1]["value"] == 0.7
    assert seq[1]["change"] == "config-changed"
    assert seq[1]["deltaPrev"] == 0.2 and seq[1]["deltaBaseline"] == 0.2
    assert seq[2]["value"] == 0.6
    assert seq[2]["deltaPrev"] == -0.1 and seq[2]["deltaBaseline"] == 0.1


def test_trend_auto_discovers_metrics(tmp_path):
    _project(tmp_path)
    root = _history(tmp_path, [7])
    res = service.trend(root, name="t")  # no metric named -> discover
    # embedding is off for this spec, so stability is absent; only the project
    # metric is discovered.
    assert res["metrics"] == ["accuracy"]


def test_trend_marks_same_config_reruns(tmp_path):
    _project(tmp_path)
    root = str(tmp_path)
    service.commit(root, name="t")               # v1 (baseline)
    service.commit(root, name="t")               # v2 same config -> same-config
    res = service.trend(root, name="t", metric="accuracy")
    labels = [p["change"] for p in res["series"]["accuracy"]]
    assert labels == ["baseline", "same-config"]


def test_trend_tolerates_a_sparse_metric(tmp_path):
    """A version missing the metric yields a null point; deltas are measured
    against the last NON-NULL value, not the gap."""
    _project(tmp_path)
    root = str(tmp_path)
    service.commit(root, name="t")     # v1 level=5 -> 0.5
    _set_level(tmp_path, 0)
    service.commit(root, name="t")     # v2 level=0 -> NO accuracy (null)
    _set_level(tmp_path, 8)
    service.commit(root, name="t")     # v3 level=8 -> 0.8

    seq = service.trend(root, name="t", metric="accuracy")["series"]["accuracy"]
    assert seq[0]["value"] == 0.5
    assert seq[1]["value"] is None
    assert seq[1]["deltaPrev"] is None and seq[1]["deltaBaseline"] is None
    # v3 delta is vs. the last non-null (v1 0.5), and baseline is v1 too
    assert seq[2]["value"] == 0.8
    assert seq[2]["deltaPrev"] == 0.3 and seq[2]["deltaBaseline"] == 0.3


def test_trend_plot_runs_project_plotter(tmp_path):
    _project(tmp_path)
    root = _history(tmp_path, [7])
    res = service.trend(root, name="t", metric="accuracy", plot=True)
    assert res.get("plotError") is None
    figs = res.get("figures", [])
    assert len(figs) == 1 and figs[0]["filename"] == "trend.svg"


def test_trend_of_builtin_stability_on_text_spec(tmp_path):
    (tmp_path / "specs").mkdir()
    (tmp_path / "specs" / "tt.yaml").write_text(TEXT_SPEC_YAML, encoding="utf-8")
    root = str(tmp_path)
    service.commit(root, name="tt")
    service.commit(root, name="tt")

    res = service.trend(root, name="tt", metric="stability")
    seq = res["series"]["stability"]
    assert len(seq) == 2
    assert all(isinstance(p["value"], float) for p in seq)
    assert seq[0]["deltaBaseline"] is None  # baseline has no reference


def test_trend_requires_a_version(tmp_path):
    _project(tmp_path)
    import pytest
    with pytest.raises(service.DowError):
        service.trend(str(tmp_path), name="t")


if __name__ == "__main__":
    import sys
    import pytest
    raise SystemExit(pytest.main([__file__, "-q", *sys.argv[1:]]))
