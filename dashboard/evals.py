"""Example custom evaluators for dow.

Each evaluator receives an EvalContext and returns a score (float) or a dict of
named scores. Reference them from a spec under evaluation.metrics, e.g.
"evals.py:avg_word_count".
"""
import re


def avg_word_count(ctx):
    """Average number of words per output."""
    counts = [len(o.split()) for o in ctx.outputs]
    return sum(counts) / len(counts) if counts else 0.0


def mentions_order_id(ctx):
    """Fraction of outputs that mention a numeric order id."""
    if not ctx.outputs:
        return 0.0
    hits = sum(1 for o in ctx.outputs if re.search(r"\b\d{2,}\b", o))
    return hits / len(ctx.outputs)
