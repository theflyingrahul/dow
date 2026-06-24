"""Terminal rendering. The interface is command line only - no web or GUI."""
from __future__ import annotations

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

_VERDICT_COLOR = {
    "Consistent": "green",
    "Behavior Drift": "yellow",
    "Likely Regression": "red",
}


def _fmt(v) -> str:
    return "null" if v is None else str(v)


def print_commit_summary(record: dict, sha: str, tagged=None) -> None:
    rt = record["runtime"]
    stab = record["metrics"]["stability"]
    console.print(
        Panel.fit(
            f"[bold]Behavior committed[/bold]  {sha[:10]}\n"
            f"spec: {record['spec_name']}   provider: {rt['provider']}   "
            f"model: {rt['model_version']}\n"
            f"samples: {len(record['samples'])}   stability: {stab:.3f}   "
            f"fingerprint: {record['spec_fingerprint']}",
            title="aiver commit",
            border_style="green",
        )
    )
    if tagged:
        console.print(f"  tagged as [bold cyan]{tagged}[/bold cyan]")


def print_log(rows) -> None:
    if not rows:
        console.print("[yellow]No behavior commits yet.[/yellow]")
        return
    table = Table(box=box.SIMPLE, header_style="bold")
    table.add_column("commit")
    table.add_column("date")
    table.add_column("message")
    for h, d, m in rows:
        table.add_row(h, d, m)
    console.print(table)


def print_show(record: dict, ref: str) -> None:
    rt = record["runtime"]
    cfg = record["config"]
    console.print(
        Panel.fit(
            f"[bold]{record['spec_name']}[/bold] @ {ref}\n"
            f"model: {cfg['model']['provider']}/{cfg['model']['version']} "
            f"rev={_fmt(cfg['model'].get('revision'))}\n"
            f"temperature: {cfg['sampling']['temperature']}  "
            f"top_p: {cfg['sampling']['top_p']}  seed: {cfg['sampling']['seed']}\n"
            f"embedding: {rt['embedding_model']}  "
            f"stability: {record['metrics']['stability']:.3f}\n"
            f"system_fingerprint: {_fmt(rt.get('system_fingerprint'))}",
            title="aiver show",
            border_style="cyan",
        )
    )
    table = Table(box=box.SIMPLE, header_style="bold")
    table.add_column("#")
    table.add_column("output")
    for i, s in enumerate(record["samples"]):
        table.add_row(str(i), s["output"])
    console.print(table)


def print_config_diff(config_diff: dict) -> None:
    if not config_diff:
        console.print("  [green]no configuration changes[/green]")
        return
    table = Table(box=box.SIMPLE, header_style="bold")
    table.add_column("field")
    table.add_column("A")
    table.add_column("B")
    for key, (a, b) in config_diff.items():
        table.add_row(key, _fmt(a), _fmt(b))
    console.print(table)


def print_diff(name, a_ref, b_ref, config_diff, outdiff, drift, stab_a, stab_b, verdict_label, thresholds) -> None:
    console.print(
        Panel.fit(f"[bold]{name}[/bold]   {a_ref}  ->  {b_ref}", title="aiver diff", border_style="magenta")
    )
    console.print("[bold]Configuration difference[/bold]")
    print_config_diff(config_diff)
    table = Table(box=box.SIMPLE, header_style="bold")
    table.add_column("signal")
    table.add_column("value")
    table.add_row("Output difference", f"{outdiff:.3f}")
    table.add_row(
        "Semantic drift",
        f"{drift:.3f}  (warn {thresholds.get('drift_warn', 0.15)}, "
        f"fail {thresholds.get('drift_fail', 0.40)})",
    )
    table.add_row("Stability A", f"{stab_a:.3f}")
    table.add_row("Stability B", f"{stab_b:.3f}")
    console.print(table)
    color = _VERDICT_COLOR.get(verdict_label, "white")
    console.print(f"[bold]Verdict:[/bold] [{color}]{verdict_label}[/{color}]")


def print_blame(name, a_ref, b_ref, config_diff, confounded, verdict_label, drift, stab_change) -> None:
    console.print(
        Panel.fit(f"[bold]{name}[/bold]   {a_ref}  ->  {b_ref}", title="aiver blame", border_style="magenta")
    )
    if not config_diff:
        console.print(
            "[green]No configuration changed.[/green] Any variation is sampling "
            "noise (see the stability score)."
        )
        return
    console.print("[bold]Attributed configuration changes[/bold]")
    print_config_diff(config_diff)
    if confounded:
        console.print(
            "[yellow]Confounded comparison:[/yellow] more than one field changed; "
            "the behavioral change cannot be attributed to a single cause."
        )
    else:
        key = next(iter(config_diff))
        console.print(f"[bold]Cause:[/bold] the change is attributable to [cyan]{key}[/cyan].")
    color = _VERDICT_COLOR.get(verdict_label, "white")
    console.print(
        f"[bold]Effect:[/bold] drift {drift:.3f}, stability change "
        f"{stab_change:+.3f} -> [{color}]{verdict_label}[/{color}]"
    )
