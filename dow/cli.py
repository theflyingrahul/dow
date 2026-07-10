"""dow command-line interface.

Task-oriented commands focused on behavioral analysis. Versioning is automatic
and the Git-backed store is hidden - no staging or refs; 'dow init' only
scaffolds a starter spec.
"""
import sys
from pathlib import Path
from typing import Optional

import typer

from . import report, service
from .evaluators import evaluate_version
from .runner import execute
from .spec import InferenceSpec
from .store import Store

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    context_settings={"help_option_names": []},
    help="Drift Observation Workbench - track how your AI's behavior changes across versions.",
    epilog="Run 'dow help <command>' for a full description and examples, e.g. 'dow help commit'.",
)

SPECS_DIR = "specs"


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
        raise typer.BadParameter("No spec found. Run 'dow init' to get started.")
    return resolved


def _resolve(store: Store, name: str, ref: str) -> str:
    try:
        return store.resolve(name, ref)
    except ValueError as exc:
        raise typer.BadParameter(str(exc))


def _resolve_pair(store: Store, name: str, a: Optional[str], b: Optional[str]):
    try:
        return service.resolve_pair(store, name, a, b)
    except service.DowError as exc:
        raise typer.BadParameter(str(exc))


def _ensure_eval(store: Store, name: str, vid: str, rerun: bool = False):
    """Return the version's eval result, running and saving it if not present."""
    return service.ensure_eval(store, name, vid, _root(), rerun=rerun)


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
@app.command(**_doc("init"))
def init(
    name: str = typer.Argument(
        service.EXAMPLE_NAME, help="Name for the new spec (creates specs/<name>.yaml)."
    ),
) -> None:
    """Scaffold a starter spec (and evals.py) so you can start versioning."""
    try:
        result = service.init_spec(_root(), name)
    except service.DowError as exc:
        raise typer.BadParameter(str(exc))
    stem = result["spec"]
    created = result["created"]
    report.console.print(
        f"[green]Created[/green] {', '.join(created)}.\n"
        f"Edit [bold]specs/{stem}.yaml[/bold], then run [bold]dow commit[/bold] to capture v1."
    )


@app.command(**_doc("commit"))
def commit(
    spec: Optional[str] = typer.Argument(None, help="Spec file or name (optional)."),
    message: Optional[str] = typer.Option(None, "--message", "-m", help="Short note for this version."),
    from_: Optional[str] = typer.Option(None, "--from", help="Branch from an earlier version instead of the latest."),
) -> None:
    """Run your spec and capture its behavior as a new version."""
    name = _need_spec(spec)
    path = _spec_path(name)
    if not path.exists():
        raise typer.BadParameter(f"Spec not found: {path}")

    store = Store(_root())
    store.ensure()
    prior = store.list_versions(name)
    parent = _resolve(store, name, from_) if from_ else None
    record = execute(InferenceSpec.load(path), base_dir=_root())
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
    r = service.compare_records(store, name, a_id, b_id)
    report.print_compare(
        name, a_id, b_id, r["config_diff"], r["output_difference"], r["semantic_drift"],
        r["stability_a"], r["stability_b"], r["verdict"], r["thresholds"],
    )
    report.print_comparators(r.get("comparators", {}), r.get("comparator_refs", []), r.get("comparator_error"))


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
    r = service.compare_records(store, name, a_id, b_id)
    cfg_diff = r["config_diff"]
    confounded = len(cfg_diff) > 1
    report.print_explain(
        name, a_id, b_id, cfg_diff, confounded, r["verdict"],
        r["semantic_drift"], r["stability_b"] - r["stability_a"],
    )
    report.print_comparators(r.get("comparators", {}), r.get("comparator_refs", []), r.get("comparator_error"))


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
    draft: bool = typer.Option(
        False, "--draft", help="Evaluate the current working spec without committing a version."
    ),
    good_tag: str = typer.Option("good", "--good-tag", help="Tag that marks the known-good baseline."),
    spec: Optional[str] = typer.Option(None, "--spec", "-s"),
) -> None:
    """Run custom evaluators on a version; compare to the previous and last-good versions."""
    name = _need_spec(spec)
    store = Store(_root())

    if draft:
        # Preview: execute the working spec and score it without persisting a version.
        path = _spec_path(name)
        if not path.exists():
            raise typer.BadParameter(f"Spec not found: {path}")
        record = execute(InferenceSpec.load(path), base_dir=_root())
        refs = record["config"]["evaluation"].get("metrics", [])
        if not refs:
            report.console.print(
                "[yellow]No evaluators configured.[/yellow] Add 'metrics' under 'evaluation' "
                "in your spec, e.g.\n  metrics:\n    - evals.py:avg_word_count"
            )
            return
        result = evaluate_version(record, _root())
        existing = store.list_versions(name)
        prev_id = existing[-1]["id"] if existing else None
        good_id = store.latest_with_tag(name, good_tag)
        prev_eval = _ensure_eval(store, name, prev_id) if prev_id else None
        good_eval = _ensure_eval(store, name, good_id) if good_id else None
        report.print_eval(name, "draft", result, prev_id, prev_eval, good_tag, good_id, good_eval)
        report.console.print(
            "  [dim]draft preview - nothing was committed. "
            "Run [bold]dow commit[/bold] to capture this as a version.[/dim]"
        )
        return

    versions = store.list_versions(name)
    if not versions:
        raise typer.BadParameter(
            "No versions yet. Run 'dow commit' first, "
            "or 'dow eval --draft' to preview your working spec."
        )
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
    return service.build_tree_data(store, name)


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
        _print_banner()
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
    out.append(".SH BACKENDS")
    out.append(
        "The model sits behind one provider interface, chosen by \\fBmodel.provider\\fR "
        "in the spec. dow runs fully offline by default."
    )
    out.append(".RS")
    out.append(".TP")
    out.append(".B mock")
    out.append("Deterministic offline mock (default); no network or API keys.")
    out.append(".TP")
    out.append(".B python")
    out.append("A local Python callable (path.py:function); version your own generator offline.")
    out.append(".TP")
    out.append(".B openai")
    out.append("OpenAI hosted models; set OPENAI_API_KEY.")
    out.append(".TP")
    out.append(".B ollama")
    out.append("Local Ollama runtime at http://localhost:11434.")
    out.append(".TP")
    out.append(".B vllm")
    out.append(
        "A vLLM OpenAI-compatible server, local or remote. Set VLLM_BASE_URL "
        "(default http://localhost:8000/v1) and, if the server requires it, VLLM_API_KEY."
    )
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


def _print_banner() -> None:
    """Print the dow ASCII banner. Shown on the overview only - bare `dow` and
    `dow help` - every time, and never for any other command."""
    try:
        report.console.print(f"[bold cyan]{_BANNER}[/bold cyan]")
    except UnicodeEncodeError:
        pass  # decorative only; never let a legacy console break the command


def main() -> None:
    # UTF-8 output so the banner and box-drawing art survive redirection on Windows
    # (a piped stdout otherwise defaults to cp1252 and cannot encode the glyphs).
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    # Banner on the bare `dow` overview (no_args_is_help prints the command list);
    # `dow help` prints it from help_command. Every other command stays quiet.
    if len(sys.argv) <= 1:
        _print_banner()
    app()


if __name__ == "__main__":
    main()
