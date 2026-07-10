"""Upgrade F end-to-end: a project plugs in its own *plot* functions (dow ships no
plotting library). A plotter writes figure file(s) into a dow-provided ``out_dir``
and returns their path(s); dow stores each as a content-addressed, integrity-
checked artifact and references it from the result. The figure bytes stay out of
the versioned history (git-ignored artifacts), like heavy payloads."""
import hashlib
from pathlib import Path

from dow import service

OPS_PY = '''
def relabel(req):
    rater = int(req.config.get("params", {}).get("rater", 0))
    return {"output": f"r{rater}", "payload": {"labels": [4, 3, 2, 1]}}
'''

AGG_PY = '''
def agg(cctx):
    return {"mean_len": sum(len(m.payload["labels"]) for m in cctx.members) / len(cctx.members)}
'''

# A dependency-free "plotter": writes a tiny SVG (no matplotlib needed for the test).
PLOTS_PY = '''
import os


def make_figure(pctx):
    out = os.path.join(pctx.out_dir, "fig.svg")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("<svg kind='%s' n='%d'></svg>" % (pctx.kind, len(pctx.ids)))
    return out
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
    - "aggs.py:agg"
  plots:
    - "plots.py:make_figure"
inputs:
  - "x"
'''


def _project(tmp_path):
    (tmp_path / "ops.py").write_text(OPS_PY, encoding="utf-8")
    (tmp_path / "aggs.py").write_text(AGG_PY, encoding="utf-8")
    (tmp_path / "plots.py").write_text(PLOTS_PY, encoding="utf-8")
    (tmp_path / "specs").mkdir()
    (tmp_path / "specs" / "t.yaml").write_text(SPEC_YAML, encoding="utf-8")


def _two_versions(tmp_path):
    root = str(tmp_path)
    service.commit(root, name="t")
    service.commit(root, name="t", from_version="v1")
    return root


def _assert_stored_figure(root, fig, kind):
    p = Path(root) / fig["path"]
    assert p.exists()
    # content-addressed under the git-ignored artifact store
    assert p.parent.name == "artifacts"
    assert p.parent.parent.name == ".dow"
    assert p.name == fig["sha256"] + p.suffix
    assert fig["filename"] == "fig.svg"
    data = p.read_bytes()
    assert hashlib.sha256(data).hexdigest() == fig["sha256"]
    assert fig["bytes"] == len(data)
    assert f"kind='{kind}'".encode() in data


def test_plot_hook_on_aggregate_stores_figure(tmp_path):
    _project(tmp_path)
    root = _two_versions(tmp_path)

    res = service.aggregate(root, name="t", plot=True)
    assert res["plotError"] is None
    assert len(res["figures"]) == 1
    _assert_stored_figure(root, res["figures"][0], "aggregate")

    # the persisted bundle references the figure (regenerable + integrity-checkable)
    got = service.get_aggregation(root, name="t", agg_id=res["id"])
    assert got["figures"][0]["sha256"] == res["figures"][0]["sha256"]

    # figure bytes are NOT tracked by git (kept out of the versioned history)
    gitignore = (Path(root) / ".dow" / ".gitignore").read_text(encoding="utf-8")
    assert "artifacts/" in gitignore


def test_plot_hook_on_compare_stores_figure(tmp_path):
    _project(tmp_path)
    root = _two_versions(tmp_path)

    c = service.compare(root, name="t", a="v1", b="v2", plot=True)
    assert c["plotError"] is None
    assert len(c["figures"]) == 1
    _assert_stored_figure(root, c["figures"][0], "compare")


def test_no_plot_flag_produces_no_figures(tmp_path):
    _project(tmp_path)
    root = _two_versions(tmp_path)

    res = service.aggregate(root, name="t")  # plot defaults to False
    assert res["figures"] == []
    assert res["plotRefs"] == []
