"""aiver command-line interface - the commands mirror git as closely as possible."""
import json
from pathlib import Path
from typing import Optional

import typer

from . import report
from .embeddings import get_embedder
from .gitstore import GitError, GitStore
from .metrics import output_difference, semantic_drift, stability
from .metrics import verdict as compute_verdict
from .runner import execute
from .spec import InferenceSpec, flatten

app = typer.Typer(add_completion=False, help="AI Behavior Versioning - Git for AI behavior.")

SPECS_DIR = "specs"
RUNS_DIR = "runs"

EXAMPLE_SPEC = """# specs/summarization.yaml - a fully versioned inference specification
spec_version: 1
name: summarization
task: Summarize a customer support ticket

prompt:
  system: You are an assistant that writes concise summaries.
  template: |
    Summarize the following ticket:

    {input}
  few_shot: []

model:
  provider: mock                    # mock | openai | ollama
  name: mock-summarizer
  version: mock-2024-07-18          # pinned snapshot, never a floating alias
  revision: null                    # model commit or revision hash for open-weight models

sampling:
  temperature: 0.2
  top_p: 1.0
  max_tokens: 256
  frequency_penalty: 0.0
  presence_penalty: 0.0
  stop: null
  seed: 7

evaluation:
  embedding_model: hashing-256      # offline default; swap for a sentence-transformers id
  samples: 5
  thresholds:
    drift_warn: 0.15
    drift_fail: 0.40

inputs:
  - "My order #123 never arrived and support has not replied in a week."
"""


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _root() -> Path:
    return Path.cwd()


def _git() -> GitStore:
    return GitStore(_root())


def _require_repo(git: GitStore) -> None:
    if not git.is_repo():
        raise typer.BadParameter("Not an aiver repository. Run 'aiver init' first.")


def _resolve_spec_name(name: Optional[str]) -> str:
    if name:
        return Path(name).stem
    runs = _root() / RUNS_DIR
    if runs.is_dir():
        subs = [p.name for p in runs.iterdir() if p.is_dir()]
        if len(subs) == 1:
            return subs[0]
    specs = _root() / SPECS_DIR
    if specs.is_dir():
        files = list(specs.glob("*.yaml"))
        if len(files) == 1:
            return files[0].stem
    raise typer.BadParameter("Multiple or no specs found; pass --spec NAME.")


def _spec_path(name: str) -> Path:
    return _root() / SPECS_DIR / f"{name}.yaml"


def _head_path(name: str) -> str:
    return f"{RUNS_DIR}/{name}/HEAD.json"


def _load_record_at(git: GitStore, name: str, ref: str) -> dict:
    return json.loads(git.show_file(ref, _head_path(name)))


def _config_diff(a_cfg: dict, b_cfg: dict) -> dict:
    fa, fb = flatten(a_cfg), flatten(b_cfg)
    diff = {}
    for k in sorted(set(fa) | set(fb)):
        if fa.get(k) != fb.get(k):
            diff[k] = (fa.get(k), fb.get(k))
    return diff


def _compare(git: GitStore, name: str, ref_a: str, ref_b: str):
    a = _load_record_at(git, name, ref_a)
    b = _load_record_at(git, name, ref_b)
    a_out = [s["output"] for s in a["samples"]]
    b_out = [s["output"] for s in b["samples"]]
    embedder = get_embedder(b["config"]["evaluation"]["embedding_model"])
    a_emb, b_emb = embedder.embed(a_out), embedder.embed(b_out)
    drift = semantic_drift(a_emb, b_emb)
    stab_a, stab_b = stability(a_emb), stability(b_emb)
    outdiff = output_difference(a_out, b_out)
    cfg_diff = _config_diff(a["config"], b["config"])
    thresholds = b["config"]["evaluation"]["thresholds"]
    label = compute_verdict(drift, stab_a, stab_b, thresholds)
    return cfg_diff, outdiff, drift, stab_a, stab_b, label, thresholds


# --------------------------------------------------------------------------- #
# commands (mirror git)
# --------------------------------------------------------------------------- #
@app.command()
def init() -> None:
    """Initialize a behavior repository, like 'git init'."""
    root = _root()
    (root / SPECS_DIR).mkdir(exist_ok=True)
    (root / RUNS_DIR).mkdir(exist_ok=True)
    gitignore = root / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text(".venv/\n__pycache__/\n*.pyc\n", encoding="utf-8")
    created = False
    example = _spec_path("summarization")
    if not example.exists():
        example.write_text(EXAMPLE_SPEC, encoding="utf-8")
        created = True

    git = _git()
    git.init()
    git.add("-A")
    try:
        sha = git.commit("aiver: initialize behavior repository")
        report.console.print(f"[green]Initialized[/green] at {root} (commit {sha[:10]})")
    except GitError as exc:
        report.console.print(f"[yellow]{exc}[/yellow]")
    if created:
        report.console.print("  example spec: specs/summarization.yaml")


@app.command()
def commit(
    spec: Optional[str] = typer.Option(None, "--spec", "-s", help="Spec name."),
    message: Optional[str] = typer.Option(None, "--message", "-m", help="Commit message."),
    tag: Optional[str] = typer.Option(None, "--tag", "-t", help="Tag this snapshot, e.g. v1."),
) -> None:
    """Execute the spec and record a behavior snapshot, like 'git commit'."""
    git = _git()
    _require_repo(git)
    name = _resolve_spec_name(spec)
    record = execute(InferenceSpec.load(_spec_path(name)))

    runs_dir = _root() / RUNS_DIR / name
    runs_dir.mkdir(parents=True, exist_ok=True)
    (runs_dir / "HEAD.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    history = record["run_id"].replace(":", "-")
    (runs_dir / f"{history}.json").write_text(json.dumps(record, indent=2), encoding="utf-8")

    git.add("-A")
    msg = message or f"aiver: {name} run (stability {record['metrics']['stability']:.3f})"
    sha = git.commit(msg)
    tagged = None
    if tag:
        git.tag(tag, sha)
        tagged = tag
    report.print_commit_summary(record, sha, tagged)


@app.command()
def status(spec: Optional[str] = typer.Option(None, "--spec", "-s")) -> None:
    """Show whether the working spec differs from the last snapshot, like 'git status'."""
    git = _git()
    _require_repo(git)
    name = _resolve_spec_name(spec)
    work_fp = InferenceSpec.load(_spec_path(name)).fingerprint()
    try:
        rec = _load_record_at(git, name, "HEAD")
        head_fp = rec.get("spec_fingerprint")
        if head_fp == work_fp:
            report.console.print(
                f"[green]{name}: up to date[/green] (fingerprint {work_fp}); "
                f"last stability {rec['metrics']['stability']:.3f}"
            )
        else:
            report.console.print(
                f"[yellow]{name}: spec modified since last behavior commit[/yellow]\n"
                f"  committed {head_fp} -> working {work_fp}\n"
                f"  run 'aiver commit' to record a new snapshot."
            )
    except GitError:
        report.console.print(
            f"[yellow]{name}: no behavior committed yet[/yellow] "
            f"(working fingerprint {work_fp})"
        )


@app.command()
def log(spec: Optional[str] = typer.Option(None, "--spec", "-s")) -> None:
    """List the history of behavior snapshots, like 'git log'."""
    git = _git()
    _require_repo(git)
    name = _resolve_spec_name(spec)
    report.print_log(git.log(_head_path(name)))


@app.command()
def show(
    ref: str = typer.Argument("HEAD"),
    spec: Optional[str] = typer.Option(None, "--spec", "-s"),
) -> None:
    """Show a version's spec, runtime capture, and metrics, like 'git show'."""
    git = _git()
    _require_repo(git)
    name = _resolve_spec_name(spec)
    report.print_show(_load_record_at(git, name, ref), ref)


@app.command()
def diff(
    ref_a: str = typer.Argument(..., help="Base version."),
    ref_b: str = typer.Argument("HEAD", help="Compared version."),
    spec: Optional[str] = typer.Option(None, "--spec", "-s"),
) -> None:
    """Compare two versions, like 'git diff'."""
    git = _git()
    _require_repo(git)
    name = _resolve_spec_name(spec)
    cfg_diff, outdiff, drift, stab_a, stab_b, label, thr = _compare(git, name, ref_a, ref_b)
    report.print_diff(name, ref_a, ref_b, cfg_diff, outdiff, drift, stab_a, stab_b, label, thr)


@app.command()
def blame(
    ref_a: str = typer.Argument(..., help="Base version."),
    ref_b: str = typer.Argument("HEAD", help="Compared version."),
    spec: Optional[str] = typer.Option(None, "--spec", "-s"),
) -> None:
    """Attribute a behavioral change to the configuration difference, like 'git blame'."""
    git = _git()
    _require_repo(git)
    name = _resolve_spec_name(spec)
    cfg_diff, _, drift, stab_a, stab_b, label, _ = _compare(git, name, ref_a, ref_b)
    confounded = len(cfg_diff) > 1
    report.print_blame(name, ref_a, ref_b, cfg_diff, confounded, label, drift, stab_b - stab_a)


@app.command()
def tag(
    name: str = typer.Argument(..., help="Tag name, e.g. v1."),
    ref: str = typer.Argument("HEAD"),
) -> None:
    """Name a version, like 'git tag'."""
    git = _git()
    _require_repo(git)
    git.tag(name, ref)
    report.console.print(f"[cyan]tagged[/cyan] {ref} as {name}")


@app.command()
def checkout(
    ref: str = typer.Argument(..., help="Version to restore."),
    spec: Optional[str] = typer.Option(None, "--spec", "-s"),
) -> None:
    """Restore the working spec to a version, like 'git checkout'."""
    git = _git()
    _require_repo(git)
    name = _resolve_spec_name(spec)
    content = git.show_file(ref, f"{SPECS_DIR}/{name}.yaml")
    _spec_path(name).write_text(content, encoding="utf-8")
    report.console.print(f"[green]checked out[/green] specs/{name}.yaml from {ref}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
