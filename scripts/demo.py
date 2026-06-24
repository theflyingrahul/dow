#!/usr/bin/env python
"""Self-contained dow demo.

Evolves a single AI specification through several versions - including two
branches - and showcases the analysis: stability, semantic drift, causal
attribution, and the evolution tree. Runs fully offline (mock provider +
built-in hashing embedder); no API key required.

    python scripts/demo.py             # fresh temp directory
    python scripts/demo.py --pause 1   # pace it for a live presentation
    python scripts/demo.py --dir demo  # use a specific directory
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

SPEC_TEMPLATE = """\
spec_version: 1
name: summarization
task: Summarize a customer support ticket

prompt:
  system: "{system}"
  template: |
    Summarize the following ticket:

    {{input}}
  few_shot: []

model:
  provider: mock
  name: mock-summarizer
  version: {model_version}
  revision: null

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
  samples: 6
  thresholds:
    drift_warn: 0.15
    drift_fail: 0.40

inputs:
  - "My order #123 never arrived and support has not replied in a week."
"""

BASE_PROMPT = "You are an assistant that writes concise summaries."


def write_spec(path: Path, system: str, model_version: str, temperature: float) -> None:
    path.write_text(
        SPEC_TEMPLATE.format(system=system, model_version=model_version, temperature=temperature),
        encoding="utf-8",
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
    parser = argparse.ArgumentParser(description="Run the dow behavior-versioning demo.")
    parser.add_argument("--dir", help="Demo directory (default: a fresh temp directory).")
    parser.add_argument(
        "--pause", type=float, default=0.0, help="Seconds to pause between steps (for live demos)."
    )
    args = parser.parse_args()

    root = Path(args.dir).resolve() if args.dir else Path(tempfile.mkdtemp(prefix="dow_demo_"))
    specs = root / "specs"
    specs.mkdir(parents=True, exist_ok=True)
    spec = specs / "summarization.yaml"

    console.print(f"[bold]dow demo[/bold]  ->  {root}")

    step("v1  -  baseline (temperature 0.2)", args.pause)
    write_spec(spec, BASE_PROMPT, "mock-2024-07-18", 0.2)
    dow(root, "run", "-m", "baseline")

    step("v2  -  raise temperature to 0.9 (expect instability)", args.pause)
    write_spec(spec, BASE_PROMPT, "mock-2024-07-18", 0.9)
    dow(root, "run", "-m", "raise temperature")

    step("v3  -  branch from v1: pin a new model snapshot, temperature 0", args.pause)
    write_spec(spec, BASE_PROMPT, "mock-2025-02-01", 0.0)
    dow(root, "run", "--from", "v1", "-m", "new model snapshot")

    step("v4  -  branch from v2: tune temperature down to 0.5", args.pause)
    write_spec(spec, BASE_PROMPT, "mock-2024-07-18", 0.5)
    dow(root, "run", "--from", "v2", "-m", "tune temperature")

    step("history  -  every captured version", args.pause)
    dow(root, "history")

    step("compare v1 v2  -  what changed and how much behavior drifted", args.pause)
    dow(root, "compare", "v1", "v2")

    step("explain v1 v2  -  attribute the change to a single cause", args.pause)
    dow(root, "explain", "v1", "v2")

    step("tree  -  how behavior evolved across versions", args.pause)
    dow(root, "tree")

    step("export  -  a shareable Mermaid diagram", args.pause)
    dow(root, "tree", "-o", "evolution.md")

    console.print()
    console.print(
        f"Open [bold]{root / 'evolution.md'}[/bold] in the Markdown preview to view the tree."
    )


if __name__ == "__main__":
    main()
