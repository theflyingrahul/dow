#!/usr/bin/env python
"""A comprehensive dow showcase - exercises every feature end to end.

It evolves one inference spec (a customer-support summarizer) through eight
versions across a trunk and three branches, changing exactly one configuration
field at a time (plus one deliberately "confounded" change), then runs the full
analysis surface:

  - run                capture trunk versions v1..v5 (auto-evaluated on capture)
  - run --from         fork branches v6, v7, v8 from earlier versions
  - tag                label versions: baseline, good, golden, bad, candidate
  - history            the whole tree with stability and tags
  - inspect            one version's spec, runtime, outputs, tags, eval scores
  - compare            outputs / drift / stability / verdict (version & tag refs)
  - explain            causal attribution: single cause vs a confounded change
  - eval               custom metrics vs the previous and a known-good version
  - tree / tree -o     terminal evolution tree + a shareable Mermaid diagram
  - help               the built-in documentation

Everything runs fully offline (mock provider + built-in hashing embedder); no
API key required.

    python scripts/showcase.py             # fresh temp directory
    python scripts/showcase.py --dir out   # a specific directory you can inspect
    python scripts/showcase.py --pause 1   # pace it for a live walkthrough
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from rich.console import Console
from rich.rule import Rule

console = Console()

# --------------------------------------------------------------------------- #
# Custom evaluators written into the working directory and referenced from the
# spec as evals.py:<function>. One returns a single score; one returns a dict of
# several named scores - dow merges them all into the version's metric table.
# --------------------------------------------------------------------------- #
EVALS = '''\
"""Custom evaluators for the dow showcase.

Each receives an EvalContext (input, outputs, config, runtime, samples) and
returns either a float or a dict of named float scores.
"""
import re


def avg_word_count(ctx):
    """Average words per output - a brevity signal."""
    counts = [len(o.split()) for o in ctx.outputs]
    return sum(counts) / len(counts) if counts else 0.0


def mentions_order_id(ctx):
    """Fraction of outputs that cite a numeric order id (must stay ~1.0)."""
    if not ctx.outputs:
        return 0.0
    return sum(1 for o in ctx.outputs if re.search(r"\\b\\d{2,}\\b", o)) / len(ctx.outputs)


def coverage(ctx):
    """A dict of content-coverage fractions across the sampled outputs."""
    outs = [o.lower() for o in ctx.outputs]
    n = len(outs) or 1

    def frac(pred):
        return round(sum(1 for o in outs if pred(o)) / n, 3)

    return {
        "mentions_escalation": frac(lambda o: "escalation" in o),
        "mentions_timeframe": frac(lambda o: "week" in o or "seven days" in o),
        "mentions_resolution": frac(lambda o: "resolution" in o or "resolve" in o),
    }
'''

SPEC_TEMPLATE = """\
spec_version: 1
name: support_summarizer
task: Summarize a customer support ticket for triage

prompt:
  system: "{system}"
  template: "{template}"
  few_shot: []

model:
  provider: mock
  name: mock-summarizer
  version: {model_version}
  revision: {model_revision}

sampling:
  temperature: {temperature}
  top_p: 1.0
  max_tokens: 256
  frequency_penalty: 0.0
  presence_penalty: 0.0
  stop: null
  seed: 7

evaluation:
  embedding_model: hashing-256
  samples: 8
  metrics:
    - evals.py:avg_word_count
    - evals.py:mentions_order_id
    - evals.py:coverage
  thresholds:
    drift_warn: 0.15
    drift_fail: 0.40

inputs:
  - "My order #123 never arrived and support has not replied in a week."
"""

# Two system prompts and two templates - changing either drifts behavior.
S1 = "You are an assistant that writes concise summaries."
S2 = "You are a support triage assistant. Name the order id and the delay in one sentence."
T1 = "Summarize the following support ticket: {input}"
T2 = "Read the ticket and write a one-sentence triage summary that names the order: {input}"
M1 = "mock-2024-07-18"
M2 = "mock-2025-02-01"


def write_spec(path, *, system, template, model_version, temperature, revision=None):
    rev = "null" if revision is None else f'"{revision}"'
    path.write_text(
        SPEC_TEMPLATE.format(
            system=system,
            template=template,
            model_version=model_version,
            model_revision=rev,
            temperature=temperature,
        ),
        encoding="utf-8",
    )


def dow(cwd, *args):
    """Invoke the dow CLI, inheriting the terminal so output stays formatted."""
    subprocess.run([sys.executable, "-m", "dow", *args], cwd=str(cwd), check=True)


def step(title, pause):
    console.print()
    console.print(Rule(f"[bold cyan]{title}[/bold cyan]"))
    if pause:
        time.sleep(pause)


def main():
    parser = argparse.ArgumentParser(description="Run the comprehensive dow showcase.")
    parser.add_argument("--dir", help="Working directory (default: a fresh temp directory).")
    parser.add_argument(
        "--pause", type=float, default=0.0, help="Seconds to pause between steps (live demos)."
    )
    args = parser.parse_args()

    root = Path(args.dir).resolve() if args.dir else Path(tempfile.mkdtemp(prefix="dow_showcase_"))
    specs = root / "specs"
    specs.mkdir(parents=True, exist_ok=True)
    spec = specs / "support_summarizer.yaml"
    (root / "evals.py").write_text(EVALS, encoding="utf-8")

    console.print(f"[bold]dow showcase[/bold]  ->  {root}")

    # ----- build a trunk: one change per version, auto-evaluated on capture ---
    step("v1  -  baseline (temperature 0.2)", args.pause)
    write_spec(spec, system=S1, template=T1, model_version=M1, temperature=0.2)
    dow(root, "commit", "-m", "baseline")
    dow(root, "tag", "baseline", "v1")

    step("v2  -  make it deterministic: temperature 0.2 -> 0.0", args.pause)
    write_spec(spec, system=S1, template=T1, model_version=M1, temperature=0.0)
    dow(root, "commit", "-m", "make deterministic")

    step("v3  -  upgrade the model snapshot (only model.version changes)", args.pause)
    write_spec(spec, system=S1, template=T1, model_version=M2, temperature=0.0)
    dow(root, "commit", "-m", "upgrade model snapshot")

    step("v4  -  tighten the system prompt (only prompt.system changes)", args.pause)
    write_spec(spec, system=S2, template=T1, model_version=M2, temperature=0.0)
    dow(root, "commit", "-m", "tighten system prompt")
    dow(root, "tag", "good", "v4")
    dow(root, "tag", "golden", "v4")

    step("v5  -  stress test: temperature 0.0 -> 0.95 (expect instability)", args.pause)
    write_spec(spec, system=S2, template=T1, model_version=M2, temperature=0.95)
    dow(root, "commit", "-m", "stress-test high temperature")
    dow(root, "tag", "bad", "v5")

    # ----- branches: fork earlier versions to explore alternatives -----------
    step("v6  -  branch from v2: pin a model revision (only model.revision)", args.pause)
    write_spec(spec, system=S1, template=T1, model_version=M1, temperature=0.0, revision="r2025.02")
    dow(root, "commit", "--from", "v2", "-m", "pin model revision")

    step("v7  -  branch from v3: change TWO fields at once (confounded)", args.pause)
    write_spec(spec, system=S2, template=T1, model_version=M2, temperature=0.6)
    dow(root, "commit", "--from", "v3", "-m", "raise temperature and reword prompt")

    step("v8  -  branch from v4: reword the template (only prompt.template)", args.pause)
    write_spec(spec, system=S2, template=T2, model_version=M2, temperature=0.0)
    dow(root, "commit", "--from", "v4", "-m", "reword template")
    dow(root, "tag", "candidate", "v8")

    # ----- analyze ------------------------------------------------------------
    step("history  -  every version, its stability, and its tags", args.pause)
    dow(root, "history")

    step("inspect golden  -  resolve a tag to its full record", args.pause)
    dow(root, "inspect", "golden")

    step("compare baseline v5  -  drift, stability drop, and a regression verdict", args.pause)
    dow(root, "compare", "baseline", "v5")

    step("compare good last  -  a tag against the latest version", args.pause)
    dow(root, "compare", "good", "last")

    step("explain v3 v4  -  a clean single-cause attribution (prompt.system)", args.pause)
    dow(root, "explain", "v3", "v4")

    step("explain v3 v7  -  a confounded change (two fields moved at once)", args.pause)
    dow(root, "explain", "v3", "v7")

    step("eval v5  -  custom metrics vs the previous and the last known-good", args.pause)
    dow(root, "eval", "v5")

    step("eval --good-tag golden v7  -  compare a branch against the golden version", args.pause)
    dow(root, "eval", "--good-tag", "golden", "v7")

    step("tree  -  how behavior evolved across the trunk and branches", args.pause)
    dow(root, "tree")

    step("tree -o evolution.md  -  export a shareable Mermaid diagram", args.pause)
    dow(root, "tree", "-o", "evolution.md")

    step("help  -  the built-in, single-sourced documentation", args.pause)
    dow(root, "help")

    console.print()
    console.print(
        f"Done. Explore the store under [bold]{root}[/bold]; open "
        f"[bold]{root / 'evolution.md'}[/bold] in the Markdown preview to view the tree. "
        "Try [bold]dow help <command>[/bold] or [bold]dow man[/bold] for the full reference."
    )


if __name__ == "__main__":
    main()
