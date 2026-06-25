#!/usr/bin/env python
"""Restaurant chatbot for the "Spice Route Biryani" restaurant.

A small, fully offline, deterministic chatbot. It is the unit of AI behavior that
dow versions and evaluates: dow's ``python`` provider calls :func:`reply` with a
``GenRequest`` and records what it says.

Two things drive its behavior, so editing the spec measurably changes it:

* The **system prompt** acts as policy. The bot honors directives it finds there -
  greet warmly, quote prices, confirm the spice level, recommend the signature
  dish, suggest a pairing - exactly the way a real LLM follows a system prompt.
  Add a directive in the spec and the next ``dow run`` shows the behavior (and the
  evaluator scores) change.
* The **sampling temperature** controls per-sample variation. At ``temperature: 0``
  every sample is identical (stability 1.0); higher values pick among more phrasings
  and lower the stability score - the regression signal dow is built to surface.

Run it yourself:

    python chatbot.py        # chat in the terminal
"""
from __future__ import annotations

import hashlib
import random
import re
from dataclasses import dataclass

RESTAURANT = "Spice Route Biryani"

# Menu: keyword -> (display name, price in rupees).
BIRYANIS = {
    "chicken": ("Chicken Dum Biryani", 220),
    "mutton": ("Mutton Biryani", 320),
    "paneer": ("Paneer Biryani", 210),
    "egg": ("Egg Biryani", 160),
    "prawn": ("Prawn Biryani", 360),
    "veg": ("Hyderabadi Veg Biryani", 180),
    "vegetable": ("Hyderabadi Veg Biryani", 180),
    "vegetarian": ("Hyderabadi Veg Biryani", 180),
}
SIGNATURE = ("Mutton Biryani", 320)  # the chef's special / bestseller
DRINKS = ["Mango Lassi", "Masala Chai"]
DESSERTS = ["Double ka Meetha", "Qubani ka Meetha"]

GREETING_WORDS = ["hi", "hello", "hey", "namaste", "good morning", "good evening"]
ORDER_WORDS = ["order", "want", "get me", "i'll have", "i will have", "can i have",
               "could i have", "give me", "buy", "take", "book"]
DELIVERY_WORDS = ["deliver", "delivery", "home delivery", "takeaway", "takeout", "parcel"]
MENU_WORDS = ["menu", "what do you have", "what do you serve", "options", "choices"]
RECO_WORDS = ["recommend", "suggest", "best", "popular", "special", "signature", "favourite"]
HOURS_WORDS = ["open", "hours", "timing", "close", "closing"]
LOCATION_WORDS = ["where", "location", "address", "located"]
THANKS_WORDS = ["thank", "thanks", "cheers"]
NUMBER_WORDS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4,
                "five": 5, "six": 6, "couple": 2, "dozen": 12}

# Phrasing banks. Index 0 is the deterministic choice (temperature 0); higher
# temperatures open up the later phrasings and so lower the stability score.
PLAIN_GREETINGS = ["Hi there!", "Hello!", "Hi, welcome to Spice Route Biryani!"]
WARM_GREETINGS = [
    "Namaste and a warm welcome to Spice Route Biryani!",
    "Hello and welcome - so glad you stopped by Spice Route Biryani!",
    "Welcome to Spice Route Biryani, we're happy to serve you!",
]
ORDER_ACK = [
    "Got it - {qty} {item}{plural} coming right up.",
    "Sure thing! That's {qty} {item}{plural} for you.",
    "Order noted: {qty} {item}{plural}.",
    "Absolutely - {qty} {item}{plural} it is.",
]
SPICE_PROMPTS = [
    "How spicy would you like it - mild, medium, or spicy?",
    "What spice level should we cook it at: mild, medium, or spicy?",
    "Let me know your preferred spice level (mild, medium, or spicy).",
]
SPECIAL_LINES = [
    "Our chef's signature {special} is a customer favourite, by the way.",
    "If you're undecided, the signature {special} is what we're known for.",
    "I'd recommend the chef's special {special} - it's our bestseller.",
]
UPSELL_LINES = [
    "Care to add a {drink} or some {dessert} to go with it?",
    "It pairs beautifully with a {drink} or {dessert} - shall I add one?",
    "Can I tempt you with a {drink} or {dessert} on the side?",
]
DELIVERY_LINES = [
    "We'll deliver it hot to your door in about 30-40 minutes.",
    "Delivery usually takes 30-40 minutes - we'll bring it to you piping hot.",
    "Sit back - delivery is on its way and takes roughly 30-40 minutes.",
]
ORDER_CLOSERS = [
    "Anything else I can get you?",
    "Would you like to add anything else?",
    "Is there anything more for your order?",
]


@dataclass
class _Policies:
    warm: bool = False
    prices: bool = False
    spice: bool = False
    special: bool = False
    upsell: bool = False


def _policies(system: str) -> _Policies:
    """Read behavior directives out of the system prompt (the bot's policy)."""
    s = (system or "").lower()

    def any_in(words):
        return any(w in s for w in words)

    return _Policies(
        warm=any_in(["warm", "warmly", "friendly", "welcoming"]),
        prices=any_in(["price", "prices", "cost", "how much"]),
        spice=any_in(["spice level", "spicy", "how spicy"]),
        special=any_in(["special", "recommend", "signature", "bestseller", "best-seller"]),
        upsell=any_in(["upsell", "pair", "pairing", "suggest a drink", "drink or", "dessert"]),
    )


def _has(text: str, words) -> bool:
    return any(w in text for w in words)


def _has_word(text: str, word: str) -> bool:
    return re.search(rf"\b{re.escape(word)}\b", text) is not None


def _find_items(msg: str):
    """Return the menu items mentioned, de-duplicated and order-preserving."""
    found, seen = [], set()
    for key, item in BIRYANIS.items():
        if _has_word(msg, key) and item[0] not in seen:
            found.append(item)
            seen.add(item[0])
    if not found and "biryani" in msg:
        found.append(SIGNATURE)
    return found


def _find_qty(msg: str) -> int:
    m = re.search(r"\b(\d+)\b", msg)
    if m:
        return max(1, int(m.group(1)))
    for word, value in NUMBER_WORDS.items():
        if _has_word(msg, word):
            return value
    return 1


def _variant(options, req, salt: str) -> str:
    """Pick a phrasing; the choice set widens with temperature (drives stability)."""
    options = list(options)
    if len(options) == 1:
        return options[0]
    temp = max(0.0, min(1.0, float(getattr(req, "temperature", 0.0) or 0.0)))
    k = 1 + round(temp * (len(options) - 1))
    if k <= 1:
        return options[0]
    key = "|".join(
        [
            str(getattr(req, "system", "")),
            str(getattr(req, "model_version", "")),
            str(getattr(req, "input", "")),
            salt,
            str(getattr(req, "sample_index", 0)),
        ]
    )
    seed = int(hashlib.sha256(key.encode("utf-8")).hexdigest(), 16)
    return options[random.Random(seed).randrange(min(k, len(options)))]


def _menu_text(prices: bool) -> str:
    seen, lines = set(), []
    for _, (name, price) in BIRYANIS.items():
        if name in seen:
            continue
        seen.add(name)
        lines.append(f"{name} (Rs.{price})" if prices else name)
    return "Here's our biryani menu: " + ", ".join(lines) + "."


def reply(req) -> str:
    """Produce the chatbot's reply to one customer message (the dow entry point)."""
    msg = (getattr(req, "input", "") or "").lower()
    pol = _policies(getattr(req, "system", "") or "")
    parts = []

    greeted = _has(msg, GREETING_WORDS)
    if greeted or pol.warm:
        parts.append(_variant(WARM_GREETINGS if pol.warm else PLAIN_GREETINGS, req, "greet"))

    items = _find_items(msg)
    wants_order = _has(msg, ORDER_WORDS) or bool(items)

    if items and wants_order:
        qty = _find_qty(msg)
        name, price = items[0]
        plural = "s" if qty > 1 else ""
        line = _variant(ORDER_ACK, req, "ack").format(qty=qty, item=name, plural=plural)
        if pol.prices:
            line += f" That's Rs.{price} each (total Rs.{qty * price})."
        parts.append(line)
        if pol.spice:
            parts.append(_variant(SPICE_PROMPTS, req, "spice"))
        if pol.special and name != SIGNATURE[0]:
            parts.append(_variant(SPECIAL_LINES, req, "special").format(special=SIGNATURE[0]))
        if pol.upsell:
            drink = _variant(DRINKS, req, "drink")
            dessert = _variant(DESSERTS, req, "sweet")
            parts.append(_variant(UPSELL_LINES, req, "upsell").format(drink=drink, dessert=dessert))
        if _has(msg, DELIVERY_WORDS):
            parts.append(_variant(DELIVERY_LINES, req, "deliv"))
        parts.append(_variant(ORDER_CLOSERS, req, "close"))
        return " ".join(parts)

    if _has(msg, MENU_WORDS):
        parts.append(_menu_text(pol.prices))
        if pol.special:
            parts.append(_variant(SPECIAL_LINES, req, "special").format(special=SIGNATURE[0]))
        return " ".join(parts)

    if _has(msg, RECO_WORDS):
        special = SIGNATURE[0]
        suffix = f" (Rs.{SIGNATURE[1]})" if pol.prices else ""
        parts.append(f"I'd recommend our signature {special}{suffix} - it's the house favourite.")
        if pol.upsell:
            parts.append(
                _variant(UPSELL_LINES, req, "upsell").format(
                    drink=_variant(DRINKS, req, "drink"),
                    dessert=_variant(DESSERTS, req, "sweet"),
                )
            )
        return " ".join(parts)

    if _has(msg, DELIVERY_WORDS):
        parts.append("Yes, we deliver! " + _variant(DELIVERY_LINES, req, "deliv"))
        return " ".join(parts)

    if _has(msg, HOURS_WORDS):
        parts.append("We're open every day from 11am to 11pm.")
        return " ".join(parts)

    if _has(msg, LOCATION_WORDS):
        parts.append("You'll find us at 12 Charminar Road - dine in or order for delivery.")
        return " ".join(parts)

    if _has(msg, THANKS_WORDS):
        parts.append("You're most welcome - enjoy your meal!")
        return " ".join(parts)

    if greeted:
        parts.append("How can I help you with your biryani order today?")
        return " ".join(parts)

    parts.append(
        "I'm the chatbot - I can take your order, share the menu, or recommend a dish. "
        "What would you like?"
    )
    return " ".join(parts)


# --------------------------------------------------------------------------- #
# Interactive terminal chat (handy for trying the bot without dow).
# --------------------------------------------------------------------------- #
_REPL_SYSTEM = (
    "You are the chatbot for Spice Route Biryani. Greet customers warmly, always "
    "state prices, confirm the spice level, recommend the signature dish, and "
    "suggest a drink or dessert to pair."
)


def _repl_request(text: str):
    from types import SimpleNamespace

    return SimpleNamespace(
        input=text,
        system=_REPL_SYSTEM,
        template="{input}",
        few_shot=[],
        temperature=0.0,
        top_p=1.0,
        max_tokens=200,
        seed=7,
        sample_index=0,
        model_name="chatbot.py:reply",
        model_version="chatbot-1",
        model_revision=None,
        config={},
    )


def main() -> None:
    print(f"{RESTAURANT} - chatbot. Type 'quit' to exit.\n")
    while True:
        try:
            text = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not text:
            continue
        if text.lower() in {"quit", "exit"}:
            break
        print("bot>", reply(_repl_request(text)), "\n")


if __name__ == "__main__":
    main()
