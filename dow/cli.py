"""dow command-line interface.

Task-oriented commands focused on behavioral analysis. Versioning is automatic
and the Git-backed store is hidden - there is no init, staging, or refs.
"""
from pathlib import Path
from typing import Optional

import typer

from . import report
from .dashboard import WEB_DIR, resolve_spec, serve, store_specs, write_payload
from .embeddings import get_embedder
from .evaluators import evaluate_version
from .metrics import output_difference, semantic_drift, stability
from .metrics import verdict as compute_verdict
from .runner import execute
from .spec import InferenceSpec, flatten
from .store import Store

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    context_settings={"help_option_names": []},
    help="Drift Observation Workbench - track how your AI's behavior changes across versions.",
    epilog="Run 'dow help <command>' for a full description and examples, e.g. 'dow help run'.",
)

SPECS_DIR = "specs"
EXAMPLE_NAME = "summarization"

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
  metrics:                          # your own evaluators: path.py:function (see evals.py)
    - evals.py:avg_word_count
    - evals.py:mentions_order_id
  thresholds:
    drift_warn: 0.15
    drift_fail: 0.40

inputs:
  - "My order #123 never arrived and support has not replied in a week."
"""

EXAMPLE_EVALS = r'''"""Example custom evaluators for dow.

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
'''


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _root() -> Path:
    return Path.cwd()


def _specs_dir() -> Path:
    return _root() / SPECS_DIR


def _spec_path(name: str) -> Path:
    return _specs_dir() / f"{name}.yaml"


def _spec_files() -> list:
    d = _specs_dir()
    return sorted(d.glob("*.yaml")) if d.is_dir() else []


def _find_spec_name(name: Optional[str]) -> Optional[str]:
    if name:
        return Path(name).stem
    files = _spec_files()
    if len(files) == 1:
        return files[0].stem
    if len(files) > 1:
        names = ", ".join(f.stem for f in files)
        raise typer.BadParameter(f"Multiple specs found; pass --spec NAME. Found: {names}")
    return None


def _need_spec(name: Optional[str]) -> str:
    resolved = _find_spec_name(name)
    if not resolved:
        raise typer.BadParameter("No spec found. Run 'dow commit' to get started.")
    return resolved


def _resolve(store: Store, name: str, ref: str) -> str:
    try:
        return store.resolve(name, ref)
    except ValueError as exc:
        raise typer.BadParameter(str(exc))


def _config_diff(a_cfg: dict, b_cfg: dict) -> dict:
    fa, fb = flatten(a_cfg), flatten(b_cfg)
    diff = {}
    for k in sorted(set(fa) | set(fb)):
        if fa.get(k) != fb.get(k):
            diff[k] = (fa.get(k), fb.get(k))
    return diff


def _resolve_pair(store: Store, name: str, a: Optional[str], b: Optional[str]):
    versions = store.list_versions(name)
    if a is None and b is None:
        if len(versions) < 2:
            raise typer.BadParameter(
                "Need at least two versions. Change your spec and run 'dow commit' again."
            )
        return versions[-2]["id"], versions[-1]["id"]
    if b is None:
        return _resolve(store, name, a), versions[-1]["id"]
    return _resolve(store, name, a), _resolve(store, name, b)


def _compare(store: Store, name: str, a_id: str, b_id: str):
    a = store.get_record(name, a_id)
    b = store.get_record(name, b_id)
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


def _ensure_eval(store: Store, name: str, vid: str, rerun: bool = False):
    """Return the version's eval result, running and saving it if not present."""
    rec = store.get_record(name, vid)
    refs = rec.get("config", {}).get("evaluation", {}).get("metrics", [])
    if not refs:
        return None
    if not rerun and isinstance(rec.get("eval"), dict) and rec["eval"].get("metrics"):
        return rec["eval"]
    result = evaluate_version(rec, _root())
    store.save_eval(name, vid, result)
    return result


def _auto_eval(store: Store, name: str, vid: str) -> None:
    """Run configured evaluators at capture time; never block the run on failure."""
    refs = store.get_record(name, vid).get("config", {}).get("evaluation", {}).get("metrics", [])
    if not refs:
        return
    try:
        result = _ensure_eval(store, name, vid)
    except Exception as exc:  # an evaluator bug must not lose the captured version
        report.console.print(f"  [yellow]eval skipped:[/yellow] {exc}")
        return
    metrics = (result or {}).get("metrics", {})
    if metrics:
        report.console.print("  eval: " + "  ".join(f"{k}={v:.2f}" for k, v in metrics.items()))


def _load_doc(name: str):
    """Load a command's shared docs (description + examples) from dow/docs/<name>.txt.

    The same text drives both 'dow help <name>' (Typer help and epilog) and the
    'man dow' page, so each command is documented in exactly one editable place.
    """
    try:
        text = (Path(__file__).parent / "docs" / f"{name}.txt").read_text(encoding="utf-8")
    except OSError:
        return "", None
    lines = text.splitlines()
    stripped = [ln.strip() for ln in lines]
    if "@examples" in stripped:
        idx = stripped.index("@examples")
        help_text = "\n".join(lines[:idx]).strip()
        examples = [ln.strip() for ln in lines[idx + 1 :] if ln.strip()]
    else:
        help_text, examples = text.strip(), []
    epilog = "Examples:\n\n" + "\n\n".join(examples) if examples else None
    return help_text, epilog


def _doc(name: str) -> dict:
    """Command decorator kwargs (help, epilog) sourced from dow/docs/<name>.txt."""
    help_text, epilog = _load_doc(name)
    return {"help": help_text, "epilog": epilog}


# --------------------------------------------------------------------------- #
# commands
# --------------------------------------------------------------------------- #
@app.command(**_doc("commit"))
def commit(
    spec: Optional[str] = typer.Argument(None, help="Spec file or name (optional)."),
    message: Optional[str] = typer.Option(None, "--message", "-m", help="Short note for this version."),
    from_: Optional[str] = typer.Option(None, "--from", help="Branch from an earlier version instead of the latest."),
) -> None:
    """Run your spec and capture its behavior as a new version."""
    files = _spec_files()
    if not files and not spec:
        _specs_dir().mkdir(parents=True, exist_ok=True)
        _spec_path(EXAMPLE_NAME).write_text(EXAMPLE_SPEC, encoding="utf-8")
        evals_path = _root() / "evals.py"
        if not evals_path.exists():
            evals_path.write_text(EXAMPLE_EVALS, encoding="utf-8")
        report.console.print(
            f"[green]Created[/green] specs/{EXAMPLE_NAME}.yaml and evals.py. "
            "Edit them, then run [bold]dow commit[/bold] again."
        )
        return

    name = _need_spec(spec)
    path = _spec_path(name)
    if not path.exists():
        raise typer.BadParameter(f"Spec not found: {path}")

    store = Store(_root())
    store.ensure()
    prior = store.list_versions(name)
    parent = _resolve(store, name, from_) if from_ else None
    record = execute(InferenceSpec.load(path))
    note = ""
    if prior and prior[-1]["fingerprint"] == record["spec_fingerprint"]:
        note = f"same configuration as {prior[-1]['id']} - re-running measures non-determinism"
    vid = store.add_version(name, record, message or "", parent=parent)
    report.print_run(record, vid, note)
    _auto_eval(store, name, vid)
    if prior:
        report.console.print("  next: [bold]dow compare[/bold]  or  [bold]dow eval[/bold]")


@app.command(**_doc("compare"))
def compare(
    a: Optional[str] = typer.Argument(None, help="First version (default: previous)."),
    b: Optional[str] = typer.Argument(None, help="Second version (default: latest)."),
    spec: Optional[str] = typer.Option(None, "--spec", "-s"),
) -> None:
    """Compare two versions: outputs, drift, stability, and a verdict."""
    name = _need_spec(spec)
    store = Store(_root())
    a_id, b_id = _resolve_pair(store, name, a, b)
    cfg_diff, outdiff, drift, stab_a, stab_b, label, thr = _compare(store, name, a_id, b_id)
    report.print_compare(name, a_id, b_id, cfg_diff, outdiff, drift, stab_a, stab_b, label, thr)


@app.command(**_doc("explain"))
def explain(
    a: Optional[str] = typer.Argument(None, help="First version (default: previous)."),
    b: Optional[str] = typer.Argument(None, help="Second version (default: latest)."),
    spec: Optional[str] = typer.Option(None, "--spec", "-s"),
) -> None:
    """Explain why behavior changed between two versions (causal attribution)."""
    name = _need_spec(spec)
    store = Store(_root())
    a_id, b_id = _resolve_pair(store, name, a, b)
    cfg_diff, _, drift, stab_a, stab_b, label, _ = _compare(store, name, a_id, b_id)
    confounded = len(cfg_diff) > 1
    report.print_explain(name, a_id, b_id, cfg_diff, confounded, label, drift, stab_b - stab_a)


@app.command(**_doc("history"))
def history(spec: Optional[str] = typer.Option(None, "--spec", "-s")) -> None:
    """List captured versions and their stability."""
    name = _need_spec(spec)
    store = Store(_root())
    versions = store.list_versions(name)
    work_fp = (
        InferenceSpec.load(_spec_path(name)).fingerprint()
        if _spec_path(name).exists()
        else None
    )
    report.print_history(name, versions, work_fp)


@app.command(**_doc("inspect"))
def inspect(
    version: Optional[str] = typer.Argument(None, help="Version to show (default: latest)."),
    spec: Optional[str] = typer.Option(None, "--spec", "-s"),
) -> None:
    """Show one version's spec, runtime capture, outputs, tags, and eval scores."""
    name = _need_spec(spec)
    store = Store(_root())
    vid = _resolve(store, name, version or "last")
    tags = store.meta(name, vid).get("tags", [])
    report.print_inspect(store.get_record(name, vid), vid, tags)


@app.command(**_doc("tag"))
def tag(
    label: str = typer.Argument(..., help="Free-form label, e.g. good, golden, baseline, bad."),
    version: Optional[str] = typer.Argument(None, help="Version to tag (default: latest)."),
    spec: Optional[str] = typer.Option(None, "--spec", "-s"),
) -> None:
    """Tag a version with a free-form label (good, golden, baseline, ...)."""
    name = _need_spec(spec)
    store = Store(_root())
    vid = _resolve(store, name, version or "last")
    store.add_tag(name, vid, label)
    report.console.print(f"[green]tagged[/green] {vid} as [cyan]{label}[/cyan]")


@app.command("eval", **_doc("eval"))
def evaluate(
    version: Optional[str] = typer.Argument(None, help="Version to evaluate (default: latest)."),
    rerun: bool = typer.Option(False, "--rerun", help="Re-run evaluators even if results are saved."),
    good_tag: str = typer.Option("good", "--good-tag", help="Tag that marks the known-good baseline."),
    spec: Optional[str] = typer.Option(None, "--spec", "-s"),
) -> None:
    """Run custom evaluators on a version; compare to the previous and last-good versions."""
    name = _need_spec(spec)
    store = Store(_root())
    versions = store.list_versions(name)
    if not versions:
        raise typer.BadParameter("No versions yet. Run 'dow commit' first.")
    ids = [v["id"] for v in versions]
    vid = _resolve(store, name, version or "last")
    refs = store.get_record(name, vid)["config"]["evaluation"].get("metrics", [])
    if not refs:
        report.console.print(
            "[yellow]No evaluators configured.[/yellow] Add 'metrics' under 'evaluation' "
            "in your spec, e.g.\n  metrics:\n    - evals.py:avg_word_count"
        )
        return
    target_eval = _ensure_eval(store, name, vid, rerun=rerun)
    idx = ids.index(vid)
    prev_id = ids[idx - 1] if idx > 0 else None
    good_id = store.latest_with_tag(name, good_tag)
    prev_eval = _ensure_eval(store, name, prev_id) if prev_id else None
    good_eval = _ensure_eval(store, name, good_id) if good_id else None
    report.print_eval(name, vid, target_eval, prev_id, prev_eval, good_tag, good_id, good_eval)


def _build_tree(store: Store, name: str) -> dict:
    versions = store.list_versions(name)
    if not versions:
        return {"versions": [], "stab": {}, "parent_of": {}, "edges": {}}
    records = {v["id"]: store.get_record(name, v["id"]) for v in versions}
    last_id = versions[-1]["id"]
    embedder = get_embedder(records[last_id]["config"]["evaluation"]["embedding_model"])
    emb, stab = {}, {}
    for v in versions:
        outs = [s["output"] for s in records[v["id"]]["samples"]]
        e = embedder.embed(outs)
        emb[v["id"]] = e
        stab[v["id"]] = stability(e)
    order = [v["id"] for v in versions]
    parent_of, edges = {}, {}
    for i, v in enumerate(versions):
        vid = v["id"]
        p = v["parent"] if "parent" in v else (order[i - 1] if i > 0 else None)
        parent_of[vid] = p
        if p and p in emb:
            drift = semantic_drift(emb[p], emb[vid])
            cfg = _config_diff(records[p]["config"], records[vid]["config"])
            thresholds = records[vid]["config"]["evaluation"]["thresholds"]
            label = compute_verdict(drift, stab[p], stab[vid], thresholds)
            edges[vid] = {"drift": drift, "ds": stab[vid] - stab[p], "cfg": cfg, "verdict": label}
    return {"versions": versions, "stab": stab, "parent_of": parent_of, "edges": edges}


@app.command(**_doc("tree"))
def tree(
    spec: Optional[str] = typer.Option(None, "--spec", "-s"),
    mermaid: bool = typer.Option(False, "--mermaid", help="Output a Mermaid diagram instead of a terminal tree."),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Write the Mermaid diagram to a Markdown file."),
) -> None:
    """Visualize how behavior evolves across versions."""
    name = _need_spec(spec)
    store = Store(_root())
    data = _build_tree(store, name)
    if not data["versions"]:
        report.console.print("[yellow]No versions yet.[/yellow] Run [bold]dow commit[/bold] to start.")
        return
    if mermaid or output:
        diagram = report.build_mermaid(
            name, data["versions"], data["stab"], data["parent_of"], data["edges"]
        )
        if output:
            Path(output).write_text(
                f"# {name} behavior evolution\n\n```mermaid\n{diagram}\n```\n", encoding="utf-8"
            )
            report.console.print(
                f"[green]Wrote[/green] {output}  (open the Markdown preview to view the tree)."
            )
        else:
            report.console.print(f"```mermaid\n{diagram}\n```")
    else:
        report.print_tree(name, data["versions"], data["stab"], data["parent_of"], data["edges"])


@app.command(**_doc("dashboard"))
def dashboard(
    spec: Optional[str] = typer.Option(None, "--spec", "-s", help="Spec to display (default: the only/first spec)."),
    port: int = typer.Option(0, "--port", "-p", help="Port to serve on (0 picks a free port)."),
    host: str = typer.Option("127.0.0.1", "--host", help="Interface to bind (localhost by default)."),
    no_open: bool = typer.Option(False, "--no-open", help="Do not open a browser window automatically."),
    export: Optional[str] = typer.Option(None, "--export", help="Write the live data to a JSON file and exit (no server)."),
) -> None:
    """Open the web dashboard backed by your live behavior store."""
    root = _root()
    name = resolve_spec(root, spec)
    if name is None:
        report.console.print(
            "[yellow]No versions yet.[/yellow] Run [bold]dow commit[/bold] to capture one, "
            "then open the dashboard."
        )
        raise typer.Exit(code=1)
    specs = store_specs(root)
    if spec is None and len(specs) > 1:
        report.console.print(
            f"[dim]Multiple specs found ({', '.join(specs)}); showing [bold]{name}[/bold]. "
            "Use --spec to choose another.[/dim]"
        )

    if export:
        payload = write_payload(root, name, export)
        report.console.print(
            f"[green]Wrote[/green] {export}  ({len(payload['versions'])} versions of {name})."
        )
        return

    if not (WEB_DIR / "index.html").exists():
        report.console.print(
            "[yellow]Dashboard assets are not bundled in this install.[/yellow]\n"
            "Build them once with:\n"
            "  [bold]cd dashboard && npm install && npm run build[/bold]"
        )
        raise typer.Exit(code=1)

    def _announce(url: str) -> None:
        report.console.print(
            f"[green]dow dashboard[/green] serving [bold]{name}[/bold] at [cyan]{url}[/cyan]"
        )
        report.console.print(
            "[dim]Reflects your .dow store live - re-run 'dow commit' and refresh. "
            "Press Ctrl+C to stop.[/dim]"
        )

    serve(root, name, host=host, port=port, open_browser=not no_open, on_start=_announce)


def _echo_help(command, ctx) -> None:
    """Render a command's help. Typer prints the Rich help as a side effect of
    get_help and returns an empty string; the echo covers any plain-text fallback."""
    text = command.get_help(ctx)
    if text:
        typer.echo(text)


@app.command(name="help", **_doc("help"))
def help_command(
    command: Optional[str] = typer.Argument(
        None, help="Command to explain in detail, e.g. 'commit'. Omit for the overview."
    ),
) -> None:
    """Show detailed help for dow or one command (e.g. 'dow help commit')."""
    cli = typer.main.get_command(app)
    root_ctx = typer.Context(cli, info_name="dow", help_option_names=[])
    if command is None:
        _echo_help(cli, root_ctx)
        return
    sub = cli.get_command(root_ctx, command)
    if sub is None:
        raise typer.BadParameter(
            f"No such command: {command!r}. Run 'dow help' to list commands."
        )
    _echo_help(sub, typer.Context(sub, info_name=command, parent=root_ctx, help_option_names=[]))


def _dow_version() -> str:
    try:
        from importlib.metadata import PackageNotFoundError, version

        try:
            return version("dow")
        except PackageNotFoundError:
            return "0.1.0"
    except Exception:
        return "0.1.0"


def _roff(text: str) -> str:
    """Escape dynamic text for a roff man page (backslashes and hyphens)."""
    return text.replace("\\", "\\\\").replace("-", "\\-")


def _command_usage(cmd, name: str) -> str:
    parts = [f"dow {name}", "[OPTIONS]"]
    for p in cmd.params:
        if getattr(p, "param_type_name", "") == "argument":
            metavar = p.name.upper()
            parts.append(metavar if p.required else f"[{metavar}]")
    return " ".join(parts)


def _render_manpage() -> str:
    """Build a roff(7) man page from the live CLI, so it never drifts from the code."""
    import datetime

    cli = typer.main.get_command(app)
    date = datetime.date.today().isoformat()
    out = [
        f'.TH DOW 1 "{date}" "dow {_dow_version()}" "Drift Observation Workbench"',
        ".SH NAME",
        "dow \\- track how your AI's behavior changes across versions",
        ".SH SYNOPSIS",
        ".B dow",
        "[\\fICOMMAND\\fR] [\\fIARGS\\fR]...",
        ".SH DESCRIPTION",
        _roff(cli.help or ""),
        ".PP",
        "Versioning is automatic and Git is a hidden storage backend; you never run git "
        "commands. The tool runs fully offline by default.",
        ".SH COMMANDS",
    ]
    for name, cmd in cli.commands.items():
        if getattr(cmd, "hidden", False):
            continue
        out.append(f".SS {name}")
        out.append(f".B {_roff(_command_usage(cmd, name))}")
        out.append(".PP")
        for para in (cmd.help or "").split("\n\n"):
            para = para.strip()
            if para:
                out.append(_roff(para))
                out.append(".PP")
        args = [p for p in cmd.params if getattr(p, "param_type_name", "") == "argument"]
        opts = [p for p in cmd.params if getattr(p, "param_type_name", "") == "option"]
        if args:
            out.append("Arguments:")
            out.append(".RS")
            for p in args:
                out.append(".TP")
                out.append(f".B {_roff(p.name.upper())}")
                out.append(_roff(getattr(p, "help", None) or "(no description)"))
            out.append(".RE")
            out.append(".PP")
        if opts:
            out.append("Options:")
            out.append(".RS")
            for p in opts:
                flags = ", ".join(list(p.opts) + list(getattr(p, "secondary_opts", [])))
                out.append(".TP")
                out.append(f".B {_roff(flags)}")
                out.append(_roff(getattr(p, "help", None) or "(no description)"))
            out.append(".RE")
            out.append(".PP")
        epilog = getattr(cmd, "epilog", None)
        if epilog:
            out.append("Examples:")
            out.append(".RS")
            out.append(".nf")
            for line in epilog.split("\n"):
                line = line.strip()
                if line and line.lower() != "examples:":
                    out.append(_roff(line))
            out.append(".fi")
            out.append(".RE")
            out.append(".PP")
    out.append(".SH SEE ALSO")
    out.append("Run \\fBdow help\\fR or \\fBdow help \\fICOMMAND\\fR for interactive help.")
    return "\n".join(out) + "\n"


@app.command(name="man", **_doc("man"))
def man_command(
    install: bool = typer.Option(
        False, "--install", help="Write the page to a man directory so 'man dow' works."
    ),
    directory: Optional[str] = typer.Option(
        None, "--dir", help="Target man1 directory (default: ~/.local/share/man/man1)."
    ),
) -> None:
    """Output dow's manual page in roff format, or install it so 'man dow' works."""
    roff = _render_manpage()
    if not install:
        typer.echo(roff)
        return
    target_dir = (
        Path(directory).expanduser()
        if directory
        else Path.home() / ".local" / "share" / "man" / "man1"
    )
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "dow.1"
    target.write_text(roff, encoding="utf-8")
    report.console.print(f"[green]Installed[/green] man page to {target}")
    report.console.print(
        "Run [bold]man dow[/bold] to view it "
        "(ensure the parent man directory is on your MANPATH)."
    )


_BANNER = r"""
██████╗  ██████╗ ██╗    ██╗
██╔══██╗██╔═══██╗██║    ██║
██║  ██║██║   ██║██║ █╗ ██║
██║  ██║██║   ██║██║███╗██║
██████╔╝╚██████╔╝╚███╔███╔╝
╚═════╝  ╚═════╝  ╚══╝╚══╝
"""

_WELCOME_MARKER = Path.home() / ".dow" / ".welcomed"


def _show_welcome_once() -> None:
    """Print the dow banner the first time the command is ever run."""
    if _WELCOME_MARKER.exists():
        return
    report.console.print(f"[bold cyan]{_BANNER}[/bold cyan]")
    report.console.print(
        "[dim]Drift Observation Workbench - "
        "track how your AI's behavior changes across versions.[/dim]\n"
    )
    try:
        _WELCOME_MARKER.parent.mkdir(parents=True, exist_ok=True)
        _WELCOME_MARKER.touch()
    except OSError:
        pass


def main() -> None:
    _show_welcome_once()
    app()


if __name__ == "__main__":
    main()
