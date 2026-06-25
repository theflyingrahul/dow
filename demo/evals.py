"""Custom dow evaluators for the chatbot.

Each evaluator receives an ``EvalContext`` (``input``, ``outputs``, ``config``,
``runtime``, ``samples``) and returns either a single float or a dict of named
float scores. dow runs them on every captured version and tracks how the numbers
move as you evolve the bot's spec.

Reference them from specs/chatbot.yaml under ``evaluation.metrics`` as
``evals.py:<function>``.
"""
import re

# Signals we look for in the bot's replies.
DISH_RE = re.compile(r"\b(biryani|salan|raita|lassi|chai|meetha|shorba)s?\b", re.I)
PRICE_RE = re.compile(r"(?:rs\.?|\u20b9)\s?\d+", re.I)
SPICE_RE = re.compile(r"\b(spicy|mild|medium)\b", re.I)
SPECIAL_RE = re.compile(r"\b(signature|recommend|bestseller|chef|favourite|favorite)\b", re.I)
PAIRING_RE = re.compile(r"\b(lassi|chai|meetha|dessert|drink|sweet)\b", re.I)
GREETING_RE = re.compile(r"\b(welcome|hello|hi|namaste|glad|happy to serve)\b", re.I)


def _fraction(outputs, predicate) -> float:
    if not outputs:
        return 0.0
    return round(sum(1 for o in outputs if predicate(o)) / len(outputs), 3)


def service_checklist(ctx) -> dict:
    """Fraction of replies that hit each customer-service expectation.

    These are the behaviors a good restaurant assistant should show. As you add
    directives to the system prompt, more of them light up - dow records the lift.
    """
    outs = ctx.outputs
    return {
        "greets": _fraction(outs, lambda o: bool(GREETING_RE.search(o))),
        "names_dish": _fraction(outs, lambda o: bool(DISH_RE.search(o))),
        "states_price": _fraction(outs, lambda o: bool(PRICE_RE.search(o))),
        "confirms_spice": _fraction(outs, lambda o: bool(SPICE_RE.search(o))),
        "recommends_special": _fraction(outs, lambda o: bool(SPECIAL_RE.search(o))),
        "suggests_pairing": _fraction(outs, lambda o: bool(PAIRING_RE.search(o))),
    }


def captures_order(ctx) -> float:
    """Fraction of replies that confirm a quantity and a dish (a booked order).

    This is the core task and should stay high even as phrasing drifts.
    """
    return _fraction(
        ctx.outputs,
        lambda o: bool(re.search(r"\b\d+\b", o)) and bool(DISH_RE.search(o)),
    )


def avg_response_length(ctx) -> float:
    """Average words per reply - a proxy for how much the bot offers the customer."""
    counts = [len(o.split()) for o in ctx.outputs]
    return round(sum(counts) / len(counts), 2) if counts else 0.0
