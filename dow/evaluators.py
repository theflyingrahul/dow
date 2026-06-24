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

    input: str
    outputs: list
    config: dict
    runtime: dict
    samples: list = field(default_factory=list)


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


def evaluate_version(record: dict, base_dir) -> dict:
    """Build an EvalContext from a version record and run its configured metrics."""
    config = record.get("config", {})
    refs = config.get("evaluation", {}).get("metrics", [])
    ctx = EvalContext(
        input=record.get("input", ""),
        outputs=[s["output"] for s in record.get("samples", [])],
        config=config,
        runtime=record.get("runtime", {}),
        samples=record.get("samples", []),
    )
    return {
        "metrics": run_evaluators(refs, ctx, base_dir),
        "evaluators": list(refs),
        "evaluated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
