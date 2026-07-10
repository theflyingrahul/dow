"""Pluggable evaluation metrics.

Users define their own evaluators - plain Python callables that receive an
``EvalContext`` and return a score (``float``) or a dict of named scores.
Reference them from a spec under ``evaluation.metrics`` as either:

    path/to/evals.py:function_name      # a local file
    package.module:function_name        # an importable module

The adapter loads the callable, runs it against a version's captured behavior,
and merges the returned scores. Evaluators are arbitrary local Python (your own
code) and are executed in-process.
"""
from __future__ import annotations

import importlib
import importlib.util
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class EvalContext:
    """Everything an evaluator needs about one captured version."""

    input: object
    outputs: list
    config: dict
    runtime: dict
    samples: list = field(default_factory=list)
    payload: object = None


@dataclass
class CompareContext:
    """Everything a paired comparator needs about two captured versions.

    A comparator is the paired counterpart of an evaluator: where an evaluator
    scores one version in isolation, a comparator receives *both* versions
    (baseline ``a`` and variant ``b``) aligned per item through their captured
    ``payload`` - exactly what an agreement/reliability coefficient (weighted
    kappa, Krippendorff's alpha, Gwet AC2, ICC, flip rate, ...) needs. dow ships
    none of those coefficients: the project supplies them as ``comparators``.
    """

    a: EvalContext
    b: EvalContext
    config_diff: dict = field(default_factory=dict)
    a_id: str = ""
    b_id: str = ""


@dataclass
class CohortContext:
    """Everything an N-way aggregator needs about a *cohort* of captured versions.

    An aggregator is the many-version generalization of a comparator: where a
    comparator receives exactly two versions, an aggregator receives a whole
    cohort - K seeds, judges, prompt wordings, or clustering permutations -
    aligned per item through each member's captured ``payload``. That is what a
    reliability coefficient over K raters (ICC, Fleiss kappa, Gwet AC2,
    Krippendorff's alpha, ...) consumes. By convention the first member is the
    baseline. dow ships none of the coefficients: the project supplies them as
    ``aggregators``.
    """

    members: list  # list[EvalContext], one per cohort version, order preserved
    ids: list = field(default_factory=list)     # version ids, parallel to members
    labels: list = field(default_factory=list)  # optional human labels (tags/params)
    name: str = ""


@dataclass
class PlotContext:
    """Everything a project plot callable needs to render one figure.

    dow ships no plotting library; the project plugs in its own plot functions.
    ``results`` is the analysis dict to render (a comparator or aggregator
    output, shaped by the project). ``out_dir`` is a dow-provided directory to
    write figure file(s) into; the callable returns the path(s) it wrote and dow
    stores each as a content-addressed artifact. ``records``/``ids`` expose the
    raw captured versions for plots that need the underlying payloads.
    """

    results: dict
    out_dir: str
    kind: str = ""   # "compare" | "aggregate" | "eval"
    name: str = ""
    ids: list = field(default_factory=list)
    records: list = field(default_factory=list)


def _load_callable(ref: str, base_dir: Path):
    if ":" not in ref:
        raise ValueError(
            f"Invalid evaluator '{ref}'. Use 'path/to/evals.py:function' or 'module:function'."
        )
    target, func_name = ref.rsplit(":", 1)
    target, func_name = target.strip(), func_name.strip()

    if target.endswith(".py") or "/" in target or "\\" in target:
        path = (base_dir / target).resolve()
        if not path.exists():
            raise FileNotFoundError(f"Evaluator file not found: {path}")
        module_spec = importlib.util.spec_from_file_location(path.stem, path)
        module = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(module)  # executes the user's evaluator file
    else:
        module = importlib.import_module(target)

    if not hasattr(module, func_name):
        raise AttributeError(f"Evaluator '{func_name}' not found in {target}.")
    return func_name, getattr(module, func_name)


def run_evaluators(refs, ctx: EvalContext, base_dir) -> dict:
    """Run each referenced evaluator and merge the results into one score dict."""
    base_dir = Path(base_dir)
    results: dict = {}
    for ref in refs or []:
        name, fn = _load_callable(ref, base_dir)
        out = fn(ctx)
        if isinstance(out, dict):
            for key, value in out.items():
                results[str(key)] = float(value)
        else:
            results[name] = float(out)
    return results


def run_comparators(refs, cctx: CompareContext, base_dir) -> dict:
    """Run each referenced paired comparator over two versions and merge results.

    Unlike :func:`run_evaluators` (single version, scalar), a comparator sees both
    versions and may return richer values: a plain number, or a mapping such as
    ``{"estimate": .., "ci_low": .., "ci_high": ..}`` (an agreement coefficient
    with its bootstrap CI). Structured values are stored verbatim - dow does not
    coerce or interpret them; the render layer formats numbers and CI bands.
    """
    base_dir = Path(base_dir)
    results: dict = {}
    for ref in refs or []:
        name, fn = _load_callable(ref, base_dir)
        out = fn(cctx)
        if isinstance(out, dict) and not _is_metric_value(out):
            for key, value in out.items():
                results[str(key)] = _clean_value(value)
        else:
            results[name] = _clean_value(out)
    return results


def run_aggregators(refs, cctx: CohortContext, base_dir) -> dict:
    """Run each referenced N-way aggregator over a cohort of versions.

    Where a comparator sees two versions, an aggregator sees a whole *cohort*
    (K seeds / judges / prompt wordings / permutations) aligned per item through
    each member's captured ``payload`` - exactly what a reliability coefficient
    over K raters (ICC, Fleiss kappa, Gwet AC2, Krippendorff's alpha, ...) needs.
    Returns are structured and stored verbatim (a number, an
    ``{estimate, ci_low, ci_high}`` band, or a bag/table of named results); dow
    ships none of the coefficients.
    """
    base_dir = Path(base_dir)
    results: dict = {}
    for ref in refs or []:
        name, fn = _load_callable(ref, base_dir)
        out = fn(cctx)
        if isinstance(out, dict) and not _is_metric_value(out):
            for key, value in out.items():
                results[str(key)] = _clean_value(value)
        else:
            results[name] = _clean_value(out)
    return results


def run_plotters(refs, pctx: PlotContext, base_dir) -> list:
    """Run each referenced plot callable and collect the figure files it wrote.

    dow ships no plotting library. The project references its own plot functions
    (``path.py:function``); each receives a :class:`PlotContext` carrying the
    analysis ``results`` to render and a dow-provided ``out_dir`` to write into,
    and returns the path(s) of the figure file(s) it produced. dow then stores
    each produced file as a content-addressed artifact. A path may be returned as
    a str/Path or a list thereof; ``None`` means the plotter produced nothing.
    """
    base_dir = Path(base_dir)
    produced: list = []
    for ref in refs or []:
        _name, fn = _load_callable(ref, base_dir)
        out = fn(pctx)
        if out is None:
            continue
        items = out if isinstance(out, (list, tuple)) else [out]
        for item in items:
            if item:
                produced.append(str(item))
    return produced


def _is_metric_value(d: dict) -> bool:
    """A dict is a single metric value (not a bag of metrics) if it looks like a
    point estimate with an optional interval, e.g. ``{estimate, ci_low, ci_high}``."""
    return "estimate" in d or ("ci_low" in d and "ci_high" in d)


def _clean_value(v):
    """Keep a metric value JSON-serializable: a float, or a dict/list thereof."""
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, dict):
        return {str(k): _clean_value(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_clean_value(x) for x in v]
    return v


def build_eval_context(record: dict) -> EvalContext:
    """Construct an EvalContext (including any captured payload) from a record."""
    config = record.get("config", {})
    return EvalContext(
        input=record.get("input", ""),
        outputs=[s.get("output", "") for s in record.get("samples", [])],
        config=config,
        runtime=record.get("runtime", {}),
        samples=record.get("samples", []),
        payload=record.get("payload"),
    )


def evaluate_version(record: dict, base_dir) -> dict:
    """Build an EvalContext from a version record and run its configured metrics."""
    config = record.get("config", {})
    refs = config.get("evaluation", {}).get("metrics", [])
    ctx = build_eval_context(record)
    return {
        "metrics": run_evaluators(refs, ctx, base_dir),
        "evaluators": list(refs),
        "evaluated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
