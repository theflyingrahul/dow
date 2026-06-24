"""Terminal rendering. The interface is command line only - no web or GUI."""
from __future__ import annotations

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

console = Console()

_VERDICT_COLOR = {
    "Consistent": "green",
    "Behavior Drift": "yellow",
    "Likely Regression": "red",
}


def _fmt(v) -> str:
    return "null" if v is None else str(v)


def _short_time(ts) -> str:
    if not ts:
        return ""
    return str(ts).replace("T", " ").replace("Z", "")


def print_run(record: dict, vid: str, note: str = "") -> None:
    rt = record["runtime"]
    stab = record["metrics"]["stability"]
    lines = [
        f"[bold]Captured {vid}[/bold]   stability {stab:.3f}",
        f"model: {rt['provider']}/{rt['model_version']}   samples: {len(record['samples'])}",
        f"fingerprint: {record['spec_fingerprint']}",
    ]
    if note:
        lines.append(f"[dim]{note}[/dim]")
    console.print(Panel.fit("\n".join(lines), title="aiver run", border_style="green"))


def print_history(name: str, versions: list, work_fp=None) -> None:
    if not versions:
        console.print("[yellow]No versions yet.[/yellow] Run [bold]aiver run[/bold] to capture one.")
        return
    table = Table(box=box.SIMPLE, header_style="bold", title=f"{name}: behavior history")
    table.add_column("version")
    table.add_column("when")
    table.add_column("stability", justify="right")
    table.add_column("change")
    table.add_column("note")
    prev_fp = None
    for v in versions:
        if prev_fp is None:
            change = "baseline"
        elif v["fingerprint"] == prev_fp:
            change = "[dim]same config[/dim]"
        else:
            change = "[yellow]config changed[/yellow]"
        table.add_row(
            v["id"], _short_time(v.get("created")), f"{v['stability']:.3f}", change, v.get("message") or ""
        )
        prev_fp = v["fingerprint"]
    console.print(table)
    if work_fp is not None and work_fp != versions[-1]["fingerprint"]:
        console.print(
            "[yellow]The working spec has unsaved changes[/yellow] since "
            f"{versions[-1]['id']}; run [bold]aiver run[/bold] to capture them."
        )


def print_inspect(record: dict, vid: str) -> None:
    rt = record["runtime"]
    cfg = record["config"]
    console.print(
        Panel.fit(
            f"[bold]{record['spec_name']} {vid}[/bold]\n"
            f"model: {cfg['model']['provider']}/{cfg['model']['version']} "
            f"rev={_fmt(cfg['model'].get('revision'))}\n"
            f"temperature: {cfg['sampling']['temperature']}  "
            f"top_p: {cfg['sampling']['top_p']}  seed: {cfg['sampling']['seed']}\n"
            f"embedding: {rt['embedding_model']}  "
            f"stability: {record['metrics']['stability']:.3f}\n"
            f"system_fingerprint: {_fmt(rt.get('system_fingerprint'))}",
            title="aiver inspect",
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


def print_compare(name, a_id, b_id, config_diff, outdiff, drift, stab_a, stab_b, verdict_label, thresholds) -> None:
    console.print(
        Panel.fit(f"[bold]{name}[/bold]   {a_id}  vs  {b_id}", title="aiver compare", border_style="magenta")
    )
    console.print("[bold]What changed in the configuration[/bold]")
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
    table.add_row(f"Stability {a_id}", f"{stab_a:.3f}")
    table.add_row(f"Stability {b_id}", f"{stab_b:.3f}")
    console.print(table)
    color = _VERDICT_COLOR.get(verdict_label, "white")
    console.print(f"[bold]Verdict:[/bold] [{color}]{verdict_label}[/{color}]")


def print_explain(name, a_id, b_id, config_diff, confounded, verdict_label, drift, stab_change) -> None:
    console.print(
        Panel.fit(
            f"[bold]{name}[/bold]   why did {a_id} -> {b_id} change?",
            title="aiver explain",
            border_style="magenta",
        )
    )
    if not config_diff:
        console.print(
            "[green]Nothing in the configuration changed.[/green] Any difference is "
            "sampling noise - see the stability score."
        )
        return
    console.print("[bold]What changed[/bold]")
    print_config_diff(config_diff)
    if confounded:
        console.print(
            "[yellow]More than one thing changed,[/yellow] so the effect cannot be "
            "pinned on a single cause. Change one field at a time for a clean answer."
        )
    else:
        key = next(iter(config_diff))
        a, b = config_diff[key]
        console.print(f"[bold]Cause:[/bold] [cyan]{key}[/cyan] ({_fmt(a)} -> {_fmt(b)})")
    color = _VERDICT_COLOR.get(verdict_label, "white")
    console.print(
        f"[bold]Effect:[/bold] semantic drift {drift:.3f}, stability change "
        f"{stab_change:+.3f}  ->  [{color}]{verdict_label}[/{color}]"
    )


def _summarize_change(cfg: dict) -> str:
    if not cfg:
        return "re-run (no config change)"
    if len(cfg) == 1:
        k, (a, b) = next(iter(cfg.items()))
        sa, sb = _fmt(a), _fmt(b)
        if len(sa) <= 18 and len(sb) <= 18:
            return f"{k}: {sa}->{sb}"
        return f"{k} changed"
    return f"{len(cfg)} fields changed"


def _verdict_class(label: str) -> str:
    return {
        "Consistent": "consistent",
        "Behavior Drift": "drift",
        "Likely Regression": "regression",
    }.get(label, "baseline")


def _node_label(vid: str, stab: float, edge) -> str:
    base = f"[bold cyan]{vid}[/bold cyan]  stability {stab:.2f}"
    if not edge:
        return base + "  [dim](baseline)[/dim]"
    arrow = "up" if edge["ds"] > 0 else ("down" if edge["ds"] < 0 else "flat")
    color = _VERDICT_COLOR.get(edge["verdict"], "white")
    return (
        f"{base}  [dim]{_summarize_change(edge['cfg'])}; drift {edge['drift']:.2f}; "
        f"stab {edge['ds']:+.2f} {arrow}[/dim]  [{color}]{edge['verdict']}[/{color}]"
    )


def print_tree(name, versions, stab, parent_of, edges) -> None:
    ids = [v["id"] for v in versions]
    children = {i: [] for i in ids}
    roots = []
    for i in ids:
        p = parent_of.get(i)
        if p in children:
            children[p].append(i)
        else:
            roots.append(i)
    root = Tree(f"[bold]{name}[/bold] - behavior evolution")

    def add(node, vid):
        branch = node.add(_node_label(vid, stab[vid], edges.get(vid)))
        for child in children[vid]:
            add(branch, child)

    for r in roots:
        add(root, r)
    console.print(root)


def _mermaid_safe(text: str) -> str:
    return text.replace('"', "'").replace("|", "/")


def build_mermaid(name, versions, stab, parent_of, edges) -> str:
    lines = ["graph TD"]
    for v in versions:
        vid = v["id"]
        lines.append(f'    {vid}["{vid}<br/>stability {stab[vid]:.2f}"]')
    for v in versions:
        vid = v["id"]
        p = parent_of.get(vid)
        if p:
            edge = edges.get(vid, {})
            label = _mermaid_safe(
                f"{_summarize_change(edge.get('cfg', {}))}<br/>drift {edge.get('drift', 0):.2f}"
            )
            lines.append(f'    {p} -->|"{label}"| {vid}')
    for v in versions:
        vid = v["id"]
        edge = edges.get(vid)
        cls = _verdict_class(edge["verdict"]) if edge else "baseline"
        lines.append(f"    class {vid} {cls}")
    lines += [
        "    classDef baseline fill:#e2e3e5,stroke:#6c757d,color:#000",
        "    classDef consistent fill:#d4edda,stroke:#28a745,color:#000",
        "    classDef drift fill:#fff3cd,stroke:#ffc107,color:#000",
        "    classDef regression fill:#f8d7da,stroke:#dc3545,color:#000",
    ]
    return "\n".join(lines)
