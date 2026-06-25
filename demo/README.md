# Chatbot demo - version and evaluate AI behavior with dow

A small, fully offline chatbot for the **Spice Route Biryani** restaurant, set up
as a unit of AI behavior that [dow](../README.md) can version, evaluate, and track
for drift - exactly like you would a real LLM assistant, but with no API key and
deterministic results.

```
demo/
  chatbot.py             # the chatbot implementation (and a terminal REPL)
  evals.py               # custom evaluators that score the bot's replies
  specs/chatbot.yaml     # the versioned inference spec dow runs and captures
  run_demo.py            # evolves the bot across versions and runs the analysis
```

## Try the bot on its own

```bash
python demo/chatbot.py
```

```
you> hi, can I order two chicken biryanis?
bot> Namaste and a warm welcome to Spice Route Biryani! Got it - 2 Chicken Dum
     Biryanis coming right up. That's Rs.220 each (total Rs.440). How spicy would
     you like it - mild, medium, or spicy? ...
```

## Version and evaluate it with dow

Run the guided showcase (uses a throwaway temp directory, so it never clutters
the repo):

```bash
python demo/run_demo.py
# python demo/run_demo.py --dir out    # keep the store to poke around
# python demo/run_demo.py --pause 1    # pace it for a live walkthrough
```

It evolves the chatbot through six versions and runs `history`, `inspect`,
`compare`, `explain`, `eval`, and `tree`. Or drive it by hand:

```bash
cd demo
dow run                      # capture v1 from specs/chatbot.yaml
# edit the system prompt in specs/chatbot.yaml, then:
dow run                      # capture v2 (evaluators run automatically)
dow compare                  # v1 vs v2: drift, stability, verdict
dow explain                  # which spec field changed the behavior
dow eval                     # the service checklist vs previous and last-good
dow tree                     # the evolution tree
```

## How it plugs into dow

The spec sets `model.provider: python` and `model.name: chatbot.py:reply`. dow's
`python` provider imports that local callable and records what it returns for each
sample - so the chatbot *is* the model under version control.

Two parts of the spec drive behavior, which is the whole point of versioning it:

- **The system prompt is the chatbot's policy.** The bot honors directives it finds
  there - greet warmly, quote prices, confirm the spice level, recommend the
  signature dish, suggest a pairing - the way a real LLM follows a system prompt.
  The showcase adds these one at a time, and each edit is a single-field change, so
  `dow explain` attributes the drift cleanly to `prompt.system`.
- **`sampling.temperature` controls variation.** At `0` every sample is identical
  (stability 1.0); raising it makes the bot pick among more phrasings and lowers the
  stability score - the regression signal `dow compare` and `dow eval` surface.

## The evaluators ([evals.py](evals.py))

| Metric | What it measures |
| --- | --- |
| `service_checklist` | Fractions for `greets`, `names_dish`, `states_price`, `confirms_spice`, `recommends_special`, `suggests_pairing` (a dict metric) |
| `captures_order` | Replies that confirm a quantity and a dish - the core task; should stay high |
| `avg_response_length` | Average words per reply |

As the system prompt improves, the checklist fractions climb from version to
version while `captures_order` holds steady - and dow records every step.

> Security note: evaluators and a `python` provider are arbitrary local Python run
> in-process. Treat a shared spec's `model.name` and `evaluation.metrics` as code,
> not config.
