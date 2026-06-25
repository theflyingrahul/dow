#!/usr/bin/env python
"""Showcase: version and evaluate a restaurant chatbot with dow.

Evolves the restaurant chatbot's spec through several versions - on a trunk and a
branch - improving its system prompt one directive at a time, then runs the full
dow analysis: stability, drift, causal attribution, custom evaluators, and the
evolution tree. Everything is fully offline (the bot is a local `python` provider
and the embedder is the built-in hashing embedder); no API key required.

    python run_demo.py             # fresh temp directory
    python run_demo.py --dir out   # a directory you can inspect afterwards
    python run_demo.py --pause 1   # pace it for a live walkthrough
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from rich.console import Console
from rich.rule import Rule

console = Console()
HERE = Path(__file__).resolve().parent

SPEC_TEMPLATE = """\
spec_version: 1
name: chatbot
task: Answer customer messages for the Spice Route Biryani restaurant

prompt:
  system: "{system}"
  template: |
    Customer: {{input}}
    Chatbot:
  few_shot: []

model:
  provider: python
  name: chatbot.py:reply
  version: chatbot-1
  revision: null

sampling:
  temperature: {temperature}
  top_p: 1.0
  max_tokens: 200
  frequency_penalty: 0.0
  presence_penalty: 0.0
  stop: null
  seed: 7

evaluation:
  embedding_model: hashing-256
  samples: 6
  metrics:
    - evals.py:service_checklist
    - evals.py:captures_order
    - evals.py:avg_response_length
  thresholds:
    drift_warn: 0.15
    drift_fail: 0.40

inputs:
  - "Hi! Can I order two chicken biryanis for delivery? What would you recommend?"
"""

# The system prompt grows one directive at a time - each step changes exactly one
# field (prompt.system), so `dow explain` attributes the drift cleanly.
S1 = "You are the ordering chatbot for Spice Route Biryani."
S2 = S1 + " Greet every customer warmly and always state the price of each dish you mention."
S3 = S2 + " Confirm the customer's spice level (mild, medium, or spicy) before taking the order."
S4 = S3 + " Recommend the chef's signature biryani and suggest a drink or dessert to pair."


def write_spec(path: Path, *, system: str, temperature: float) -> None:
    path.write_text(
        SPEC_TEMPLATE.format(system=system, temperature=temperature), encoding="utf-8"
    )


def dow(cwd: Path, *args: str) -> None:
    """Invoke the dow CLI, inheriting the terminal so output stays formatted."""
    subprocess.run([sys.executable, "-m", "dow", *args], cwd=str(cwd), check=True)


def step(title: str, pause: float) -> None:
    console.print()
    console.print(Rule(f"[bold cyan]{title}[/bold cyan]"))
    if pause:
        time.sleep(pause)


def main() -> None:
    parser = argparse.ArgumentParser(description="Version and evaluate a chatbot with dow.")
    parser.add_argument("--dir", help="Working directory (default: a fresh temp directory).")
    parser.add_argument(
        "--pause", type=float, default=0.0, help="Seconds to pause between steps (live demos)."
    )
    args = parser.parse_args()

    root = Path(args.dir).resolve() if args.dir else Path(tempfile.mkdtemp(prefix="biryani_demo_"))
    specs = root / "specs"
    specs.mkdir(parents=True, exist_ok=True)
    spec = specs / "chatbot.yaml"
    # The bot and the evaluators are the code under test - copy them in as-is.
    shutil.copy(HERE / "chatbot.py", root / "chatbot.py")
    shutil.copy(HERE / "evals.py", root / "evals.py")

    console.print(f"[bold]chatbot x dow[/bold]  ->  {root}")

    step("v1  -  baseline: a plain ordering assistant", args.pause)
    write_spec(spec, system=S1, temperature=0.2)
    dow(root, "run", "-m", "baseline ordering assistant")
    dow(root, "tag", "baseline", "v1")

    step("v2  -  prompt edit: warm welcome + always quote prices", args.pause)
    write_spec(spec, system=S2, temperature=0.2)
    dow(root, "run", "-m", "warm welcome and quote prices")

    step("v3  -  prompt edit: confirm the spice level on every order", args.pause)
    write_spec(spec, system=S3, temperature=0.2)
    dow(root, "run", "-m", "confirm spice level")

    step("v4  -  prompt edit: recommend the signature dish + suggest a pairing", args.pause)
    write_spec(spec, system=S4, temperature=0.2)
    dow(root, "run", "-m", "recommend special and suggest a pairing")
    dow(root, "tag", "good", "v4")
    dow(root, "tag", "golden", "v4")

    step("v5  -  stress test: raise temperature 0.2 -> 0.9 (expect instability)", args.pause)
    write_spec(spec, system=S4, temperature=0.9)
    dow(root, "run", "-m", "stress-test high temperature")
    dow(root, "tag", "bad", "v5")

    step("v6  -  branch from v4: pin temperature 0.0 for a deterministic release", args.pause)
    write_spec(spec, system=S4, temperature=0.0)
    dow(root, "run", "--from", "v4", "-m", "deterministic release")
    dow(root, "tag", "release", "v6")

    step("history  -  every version, its stability, and its tags", args.pause)
    dow(root, "history")

    step("inspect golden  -  resolve a tag to its full record", args.pause)
    dow(root, "inspect", "golden")

    step("compare baseline golden  -  how far the bot has come (drift + verdict)", args.pause)
    dow(root, "compare", "baseline", "golden")

    step("explain v3 v4  -  clean single-cause attribution (prompt.system)", args.pause)
    dow(root, "explain", "v3", "v4")

    step("explain v4 v5  -  the instability traced to sampling.temperature", args.pause)
    dow(root, "explain", "v4", "v5")

    step("tree  -  how the chatbot evolved across the trunk and the branch", args.pause)
    dow(root, "tree")

    step("tree -o evolution.md  -  export a shareable Mermaid diagram", args.pause)
    dow(root, "tree", "-o", "evolution.md")

    console.print()
    console.print(
        f"Done. Explore the store under [bold]{root}[/bold]; open "
        f"[bold]{root / 'evolution.md'}[/bold] in the Markdown preview to view the tree."
    )


if __name__ == "__main__":
    main()
