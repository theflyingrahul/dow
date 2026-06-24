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
    console.print(Panel.fit("\n".join(lines), title="dow run", border_style="green"))


def print_history(name: str, versions: list, work_fp=None) -> None:
    if not versions:
        console.print("[yellow]No versions yet.[/yellow] Run [bold]dow run[/bold] to capture one.")
        return
    table = Table(box=box.SIMPLE, header_style="bold", title=f"{name}: behavior history")
    table.add_column("version")
    table.add_column("when")
    table.add_column("stability", justify="right")
    table.add_column("change")
    table.add_column("tags")
    table.add_column("note")
    prev_fp = None
    for v in versions:
        if prev_fp is None:
            change = "baseline"
        elif v["fingerprint"] == prev_fp:
            change = "[dim]same config[/dim]"
        else:
            change = "[yellow]config changed[/yellow]"
        tags = ", ".join(f"[cyan]{t}[/cyan]" for t in v.get("tags", []))
        table.add_row(
            v["id"], _short_time(v.get("created")), f"{v['stability']:.3f}", change, tags, v.get("message") or ""
        )
        prev_fp = v["fingerprint"]
    console.print(table)
    if work_fp is not None and work_fp != versions[-1]["fingerprint"]:
        console.print(
            "[yellow]The working spec has unsaved changes[/yellow] since "
            f"{versions[-1]['id']}; run [bold]dow run[/bold] to capture them."
        )


def print_inspect(record: dict, vid: str, tags=None) -> None:
    rt = record["runtime"]
    cfg = record["config"]
    lines = [
        f"[bold]{record['spec_name']} {vid}[/bold]",
        f"model: {cfg['model']['provider']}/{cfg['model']['version']} "
        f"rev={_fmt(cfg['model'].get('revision'))}",
        f"temperature: {cfg['sampling']['temperature']}  "
        f"top_p: {cfg['sampling']['top_p']}  seed: {cfg['sampling']['seed']}",
        f"embedding: {rt['embedding_model']}  "
        f"stability: {record['metrics']['stability']:.3f}",
        f"system_fingerprint: {_fmt(rt.get('system_fingerprint'))}",
    ]
    if tags:
        lines.append("tags: " + ", ".join(f"[cyan]{t}[/cyan]" for t in tags))
    ev = record.get("eval")
    if isinstance(ev, dict) and ev.get("metrics"):
        lines.append("eval: " + "  ".join(f"{k}={v:.3f}" for k, v in ev["metrics"].items()))
    console.print(Panel.fit("\n".join(lines), title="dow inspect", border_style="cyan"))
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
        Panel.fit(f"[bold]{name}[/bold]   {a_id}  vs  {b_id}", title="dow compare", border_style="magenta")
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
            title="dow explain",
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


def _branch_name(vid: str) -> str:
    return f"{vid}-branch"


def _commit_fields(vid, stab, edge):
    """Build the gitGraph commit label, tag, and type for one version."""
    if not edge:
        return _mermaid_safe(f"{vid} (baseline)"), _mermaid_safe(f"s={stab:.2f}"), None
    label = _mermaid_safe(f"{vid}: {_summarize_change(edge['cfg'])}")
    tag = _mermaid_safe(f"d={edge['drift']:.2f} s={stab:.2f}")
    ctype = "HIGHLIGHT" if edge["verdict"] == "Likely Regression" else None
    return label, tag, ctype


def build_mermaid(name, versions, stab, parent_of, edges) -> str:
    """Render the evolution as a Mermaid gitGraph.

    The main line is the vertical trunk; the first child of a version continues
    that trunk, while later children fork a new lane that runs alongside it.
    Commits are emitted in chronological order so vertical position tracks time.
    """
    order = [v["id"] for v in versions]
    children = {vid: [] for vid in order}
    for vid in order:
        p = parent_of.get(vid)
        if p in children:
            children[p].append(vid)

    branch_of = {}
    forks_at = {vid: [] for vid in order}
    for vid in order:
        p = parent_of.get(vid)
        if p is None or p not in branch_of:
            branch_of[vid] = "main"
            continue
        if children[p] and children[p][0] == vid:
            branch_of[vid] = branch_of[p]
        else:
            lane = _branch_name(vid)
            branch_of[vid] = lane
            forks_at[p].append(lane)

    lines = ["gitGraph TB:"]
    current = "main"
    for vid in order:
        lane = branch_of[vid]
        if lane != current:
            lines.append(f"    checkout {lane}")
            current = lane
        label, tag, ctype = _commit_fields(vid, stab[vid], edges.get(vid))
        commit = f'    commit id: "{label}"'
        if ctype:
            commit += f" type: {ctype}"
        if tag:
            commit += f' tag: "{tag}"'
        lines.append(commit)
        for lane_child in forks_at[vid]:
            lines.append(f"    branch {lane_child}")
            current = lane_child
    return "\n".join(lines)


def _delta_cell(cur, ref) -> str:
    if ref is None:
        return "-"
    return f"{ref:.3f} ({cur - ref:+.3f})"


def print_eval(name, vid, target, prev_id, prev, good_tag, good_id, good) -> None:
    console.print(
        Panel.fit(f"[bold]{name} {vid}[/bold]  custom evaluation", title="dow eval", border_style="cyan")
    )
    tmetrics = (target or {}).get("metrics", {})
    pmetrics = (prev or {}).get("metrics", {})
    gmetrics = (good or {}).get("metrics", {})
    if not tmetrics:
        console.print("[yellow]No metric scores were produced.[/yellow]")
        return
    table = Table(box=box.SIMPLE, header_style="bold")
    table.add_column("metric")
    table.add_column(vid, justify="right")
    table.add_column(f"prev {prev_id}" if prev_id else "prev", justify="right")
    table.add_column(f"good {good_id}" if good_id else f"good <{good_tag}>", justify="right")
    for m in sorted(tmetrics):
        cur = tmetrics[m]
        table.add_row(m, f"{cur:.3f}", _delta_cell(cur, pmetrics.get(m)), _delta_cell(cur, gmetrics.get(m)))
    console.print(table)
    if not prev_id:
        console.print("[dim]no previous version to compare[/dim]")
    if not good_id:
        console.print(
            f"[dim]no version tagged '{good_tag}' yet - mark one with: "
            f"dow tag {good_tag} <version>[/dim]"
        )
