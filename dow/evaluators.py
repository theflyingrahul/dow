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
