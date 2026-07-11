"""Feature: the regression GATE - a pure decision dow makes so a sweep or CI job
can fail fast. dow supplies its built-in text verdict (``verdict_gate``) and turns
a project-supplied metric threshold into a pass/fail (``threshold_gate``); the CLI
turns a breach into a non-zero exit code. dow computes no new numbers: the gate
only interprets the verdict/metric already produced. ``threshold_gate`` fails
CLOSED - a missing/non-numeric value where a bound is set is a breach, so a CI gate
never silently passes when the metric it guards has vanished."""
import re

import pytest
from typer.testing import CliRunner

from dow import cli, service

runner = CliRunner()


# --------------------------------------------------------------------------- #
# pure decision helpers
# --------------------------------------------------------------------------- #
def test_verdict_gate_regression_level():
    assert service.verdict_gate("Likely Regression", "regression")["breached"] is True
    # behavior drift is NOT a regression at the default level
    assert service.verdict_gate("Behavior Drift", "regression")["breached"] is False
    assert service.verdict_gate("Consistent", "regression")["breached"] is False


def test_verdict_gate_drift_level_is_stricter():
    g = service.verdict_gate("Behavior Drift", "drift")
    assert g["breached"] is True and g["mode"] == "verdict:drift"
    assert service.verdict_gate("Likely Regression", "drift")["breached"] is True
    assert service.verdict_gate("Consistent", "drift")["breached"] is False


def test_verdict_gate_null_verdict_never_trips():
    # embedding_model: none -> no built-in text signal -> gate on a project metric
    for level in ("regression", "drift"):
        g = service.verdict_gate(None, level)
        assert g["breached"] is False
        assert "embedding_model: none" in g["reason"]


def test_threshold_gate_min_and_max():
    assert service.threshold_gate(0.9, minimum=0.8)["breached"] is False
    assert service.threshold_gate(0.7, minimum=0.8, metric="acc")["breached"] is True
    assert service.threshold_gate(0.5, maximum=0.4, metric="err")["breached"] is True
    assert service.threshold_gate(0.3, maximum=0.4)["breached"] is False


def test_threshold_gate_no_bounds_never_trips():
    assert service.threshold_gate(None)["breached"] is False
    assert service.threshold_gate("not a number")["breached"] is False


def test_threshold_gate_fails_closed_on_missing_or_nonnumeric():
    # a bound is set but the value is absent/garbage -> breach (must not pass silently)
    assert service.threshold_gate(None, minimum=0.8, metric="acc")["breached"] is True
    assert service.threshold_gate("x", minimum=0.8, metric="acc")["breached"] is True
    # bool is not a valid metric value even though it is an int subclass
    assert service.threshold_gate(True, minimum=0.5, metric="acc")["breached"] is True


# --------------------------------------------------------------------------- #
# compare(fail_on=...) wires the verdict gate into the result (real pipeline)
# --------------------------------------------------------------------------- #
ECHO_OPS = '''
def gen(req):
    return {"output": req.config.get("params", {}).get("text", "")}
'''

ECHO_SPEC = '''spec_version: 1
name: g
operation: gen
params:
  text: "alpha alpha alpha alpha alpha"
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


def _echo_project(tmp_path):
    (tmp_path / "ops.py").write_text(ECHO_OPS, encoding="utf-8")
    (tmp_path / "specs").mkdir()
    (tmp_path / "specs" / "g.yaml").write_text(ECHO_SPEC, encoding="utf-8")


def _set_text(tmp_path, text):
    p = tmp_path / "specs" / "g.yaml"
    p.write_text(re.sub(r'text: ".*"', f'text: "{text}"', p.read_text(encoding="utf-8"), count=1),
                 encoding="utf-8")


def test_compare_fail_on_surfaces_a_gate(tmp_path):
    _echo_project(tmp_path)
    root = str(tmp_path)
    service.commit(root, name="g")                       # v1
    _set_text(tmp_path, "omega beta gamma delta epsilon")  # wholly different text
    service.commit(root, name="g")                       # v2

    out = service.compare(root, name="g", fail_on="regression")
    assert out["verdict"] == "Likely Regression"
    # the gate is exactly what verdict_gate decides for that verdict/level
    assert out["gate"] == service.verdict_gate(out["verdict"], "regression")
    assert out["gate"]["breached"] is True

    # no fail_on -> no gate key at all
    assert "gate" not in service.compare(root, name="g")


def test_compare_fail_on_does_not_trip_on_consistent(tmp_path):
    _echo_project(tmp_path)
    root = str(tmp_path)
    service.commit(root, name="g")   # v1
    service.commit(root, name="g")   # v2 identical config -> Consistent
    out = service.compare(root, name="g", fail_on="regression")
    assert out["verdict"] == "Consistent"
    assert out["gate"]["breached"] is False


# --------------------------------------------------------------------------- #
# CLI exit codes (what a sweep/CI actually consumes)
# --------------------------------------------------------------------------- #
def test_cli_compare_fail_on_regression_exit_code(tmp_path, monkeypatch):
    _echo_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    runner.invoke(cli.app, ["commit", "g"])
    _set_text(tmp_path, "omega beta gamma delta epsilon")
    runner.invoke(cli.app, ["commit", "g"])

    breach = runner.invoke(cli.app, ["compare", "-s", "g", "--fail-on-regression"])
    assert breach.exit_code == 1
    assert "GATE FAILED" in breach.stdout

    # a plain compare (no gate flag) still exits 0 on the same pair
    ok = runner.invoke(cli.app, ["compare", "-s", "g"])
    assert ok.exit_code == 0


def test_cli_compare_gate_passes_on_consistent(tmp_path, monkeypatch):
    _echo_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    runner.invoke(cli.app, ["commit", "g"])
    runner.invoke(cli.app, ["commit", "g"])   # identical -> Consistent
    res = runner.invoke(cli.app, ["compare", "-s", "g", "--fail-on-regression"])
    assert res.exit_code == 0
    assert "gate passed" in res.stdout


# a python-op + project evaluator so the metric value is fully controlled.
SCORE_OPS = '''
def gen(req):
    lvl = int(req.config.get("params", {}).get("level", 0))
    return {"output": f"l{lvl}", "payload": {"level": lvl}}
'''
SCORE_EVAL = '''
def score(ctx):
    return {"accuracy": int(ctx.config.get("params", {}).get("level", 0)) / 10.0}
'''
SCORE_SPEC = '''spec_version: 1
name: s
operation: gen
params:
  level: 9
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
inputs:
  - "x"
'''


def _score_project(tmp_path, level=9):
    (tmp_path / "ops.py").write_text(SCORE_OPS, encoding="utf-8")
    (tmp_path / "evals.py").write_text(SCORE_EVAL, encoding="utf-8")
    (tmp_path / "specs").mkdir()
    (tmp_path / "specs" / "s.yaml").write_text(
        SCORE_SPEC.replace("level: 9", f"level: {level}"), encoding="utf-8")


def test_cli_eval_metric_threshold_exit_codes(tmp_path, monkeypatch):
    _score_project(tmp_path, level=9)          # accuracy 0.9
    monkeypatch.chdir(tmp_path)
    runner.invoke(cli.app, ["commit", "s"])

    ok = runner.invoke(cli.app, ["eval", "-s", "s", "--metric", "accuracy", "--min", "0.8"])
    assert ok.exit_code == 0 and "gate passed" in ok.stdout

    bad = runner.invoke(cli.app, ["eval", "-s", "s", "--metric", "accuracy", "--min", "0.95"])
    assert bad.exit_code == 1 and "GATE FAILED" in bad.stdout


def test_cli_eval_threshold_requires_metric(tmp_path, monkeypatch):
    _score_project(tmp_path, level=9)
    monkeypatch.chdir(tmp_path)
    runner.invoke(cli.app, ["commit", "s"])
    res = runner.invoke(cli.app, ["eval", "-s", "s", "--min", "0.5"])
    assert res.exit_code != 0  # BadParameter: --min/--max require --metric


def test_cli_eval_draft_metric_gate(tmp_path, monkeypatch):
    _score_project(tmp_path, level=3)          # accuracy 0.3
    monkeypatch.chdir(tmp_path)
    # draft path (nothing committed) still gates
    res = runner.invoke(cli.app, ["eval", "-s", "s", "--draft", "--metric", "accuracy", "--min", "0.5"])
    assert res.exit_code == 1 and "GATE FAILED" in res.stdout


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__, "-q", *sys.argv[1:]]))
