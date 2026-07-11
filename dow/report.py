"""Terminal rendering. The interface is command line only - no web or GUI."""
from __future__ import annotations

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

from .embeddings import drift_label

console = Console()

_VERDICT_COLOR = {
    "Consistent": "green",
    "Behavior Drift": "yellow",
    "Likely Regression": "red",
}


def _fmt(v) -> str:
    return "null" if v is None else str(v)


def _f(x, spec: str = "{:.3f}", dash: str = "[dim]n/a[/dim]") -> str:
    """Format a possibly-``None`` numeric signal (built-in text drift may be off)."""
    return dash if x is None else spec.format(x)


def _short_time(ts) -> str:
    if not ts:
        return ""
    return str(ts).replace("T", " ").replace("Z", "")


def print_run(record: dict, vid: str, note: str = "") -> None:
    rt = record["runtime"]
    stab = record["metrics"].get("stability")
    stab_txt = f"   stability {stab:.3f}" if isinstance(stab, (int, float)) else ""
    lines = [
        f"[bold]Captured {vid}[/bold]{stab_txt}",
        f"model: {rt['provider']}/{rt['model_version']}   samples: {len(record['samples'])}",
        f"fingerprint: {record['spec_fingerprint']}",
    ]
    if note:
        lines.append(f"[dim]{note}[/dim]")
    console.print(Panel.fit("\n".join(lines), title="dow commit", border_style="green"))


def print_history(name: str, versions: list, work_fp=None) -> None:
    if not versions:
        console.print("[yellow]No versions yet.[/yellow] Run [bold]dow commit[/bold] to capture one.")
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
            v["id"], _short_time(v.get("created")), _f(v.get("stability")), change, tags, v.get("message") or ""
        )
        prev_fp = v["fingerprint"]
    console.print(table)
    if work_fp is not None and work_fp != versions[-1]["fingerprint"]:
        console.print(
            "[yellow]The working spec has unsaved changes[/yellow] since "
            f"{versions[-1]['id']}; run [bold]dow commit[/bold] to capture them."
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
        f"stability: {_f(record['metrics'].get('stability'))}",
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


def print_compare(name, a_id, b_id, config_diff, outdiff, drift, stab_a, stab_b, verdict_label, thresholds, drift_kind=None) -> None:
    console.print(
        Panel.fit(f"[bold]{name}[/bold]   {a_id}  vs  {b_id}", title="dow compare", border_style="magenta")
    )
    console.print("[bold]What changed in the configuration[/bold]")
    print_config_diff(config_diff)
    table = Table(box=box.SIMPLE, header_style="bold")
    table.add_column("signal")
    table.add_column("value")
    if drift is None and stab_a is None and stab_b is None:
        console.print(
            "[dim]Built-in text drift is off for this spec (embedding_model: none); "
            "see custom metrics below and the configuration diff above.[/dim]"
        )
    else:
        table.add_row("Output difference", _f(outdiff))
        table.add_row(
            drift_label(drift_kind),
            f"{_f(drift)}  (warn {thresholds.get('drift_warn', 0.15)}, "
            f"fail {thresholds.get('drift_fail', 0.40)})",
        )
        table.add_row(f"Stability {a_id}", _f(stab_a))
        table.add_row(f"Stability {b_id}", _f(stab_b))
        console.print(table)
    if verdict_label:
        color = _VERDICT_COLOR.get(verdict_label, "white")
        console.print(f"[bold]Verdict:[/bold] [{color}]{verdict_label}[/{color}]")


def _fmt_metric_value(v) -> str:
    """Format a comparator value: a number, or an ``{estimate, ci_low, ci_high}`` band."""
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, (int, float)):
        return f"{float(v):.3f}"
    if isinstance(v, dict):
        est = v.get("estimate")
        lo, hi = v.get("ci_low"), v.get("ci_high")
        if isinstance(est, (int, float)) and isinstance(lo, (int, float)) and isinstance(hi, (int, float)):
            return f"{est:.3f}  [{lo:.3f}, {hi:.3f}]"
        if isinstance(est, (int, float)):
            return f"{est:.3f}"
        return "  ".join(f"{k}={_fmt_metric_value(x)}" for k, x in v.items())
    if isinstance(v, list):
        return f"[{len(v)} rows]"
    return str(v)


def print_comparators(comparators: dict, refs=None, error=None) -> None:
    """Render the project's paired-comparator results beneath a compare/explain."""
    if error:
        console.print(f"[yellow]comparators skipped:[/yellow] {error}")
        return
    if not comparators:
        return
    console.print("[bold]Paired comparators[/bold] [dim](project-defined)[/dim]")
    table = Table(box=box.SIMPLE, header_style="bold")
    table.add_column("metric")
    table.add_column("value", justify="right")
    for k in sorted(comparators):
        table.add_row(k, _fmt_metric_value(comparators[k]))
    console.print(table)


def print_explain(name, a_id, b_id, config_diff, confounded, verdict_label, drift, stab_change, drift_kind=None) -> None:
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
    if drift is None and stab_change is None:
        console.print(
            "[bold]Effect:[/bold] [dim]built-in text drift is off "
            "(embedding_model: none); see custom metrics below.[/dim]"
        )
    else:
        color = _VERDICT_COLOR.get(verdict_label, "white")
        console.print(
            f"[bold]Effect:[/bold] {drift_label(drift_kind, capitalized=False)} {_f(drift)}, stability change "
            f"{_f(stab_change, '{:+.3f}')}  ->  [{color}]{verdict_label}[/{color}]"
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


def _node_label(vid: str, stab, edge) -> str:
    base = f"[bold cyan]{vid}[/bold cyan]  stability {_f(stab, '{:.2f}')}"
    if not edge:
        return base + "  [dim](baseline)[/dim]"
    if edge.get("drift") is None and edge.get("ds") is None:
        return f"{base}  [dim]{_summarize_change(edge['cfg'])}[/dim]"
    ds = edge["ds"]
    arrow = "up" if ds > 0 else ("down" if ds < 0 else "flat")
    color = _VERDICT_COLOR.get(edge["verdict"], "white")
    return (
        f"{base}  [dim]{_summarize_change(edge['cfg'])}; drift {_f(edge['drift'], '{:.2f}')}; "
        f"stab {_f(ds, '{:+.2f}')} {arrow}[/dim]  [{color}]{edge['verdict']}[/{color}]"
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
    s = f"s={stab:.2f}" if isinstance(stab, (int, float)) else "s=n/a"
    if not edge:
        return _mermaid_safe(f"{vid} (baseline)"), _mermaid_safe(s), None
    label = _mermaid_safe(f"{vid}: {_summarize_change(edge['cfg'])}")
    d = f"d={edge['drift']:.2f} " if isinstance(edge.get("drift"), (int, float)) else ""
    tag = _mermaid_safe(f"{d}{s}")
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


def print_trend(data: dict) -> None:
    """Render a metric's longitudinal trend across a spec's whole version history."""
    spec = data.get("spec", "")
    metrics = data.get("metrics", []) or []
    rows = data.get("rows", []) or []
    console.print(
        Panel.fit(
            f"[bold]{spec}[/bold]  metric trend over {data.get('count', len(rows))} versions",
            title="dow trend", border_style="cyan",
        )
    )
    if not metrics:
        console.print("[yellow]No numeric metrics recorded yet.[/yellow] "
                      "Add evaluators under 'evaluation.metrics', or use a text spec for stability.")
        return
    series = data.get("series", {})
    table = Table(box=box.SIMPLE, header_style="bold")
    table.add_column("version")
    table.add_column("change")
    single = len(metrics) == 1
    if single:
        m = metrics[0]
        table.add_column(m, justify="right")
        table.add_column("Δ prev", justify="right")
        table.add_column("Δ base", justify="right")
        for pt in series.get(m, []):
            table.add_row(
                pt["id"], pt["change"], _f(pt.get("value")),
                _f(pt.get("deltaPrev"), "{:+.3f}"), _f(pt.get("deltaBaseline"), "{:+.3f}"),
            )
    else:
        for m in metrics:
            table.add_column(m, justify="right")
        for r in rows:
            cells = [r["id"], r["change"]]
            for m in metrics:
                pt = next((p for p in series.get(m, []) if p["id"] == r["id"]), None)
                val = pt.get("value") if pt else r.get("values", {}).get(m)
                dp = pt.get("deltaPrev") if pt else None
                cells.append(_f(val) + (f" ([dim]{dp:+.3f}[/dim])" if isinstance(dp, (int, float)) else ""))
            table.add_row(*cells)
    console.print(table)


def print_gate(gate: dict) -> None:
    """Render a regression-gate decision (the CLI also sets the process exit code)."""
    if not gate:
        return
    mode = gate.get("mode", "gate")
    if gate.get("breached"):
        console.print(f"  [bold red]GATE FAILED[/bold red] [dim]({mode})[/dim]  {gate.get('reason', '')}")
    else:
        reason = gate.get("reason")
        note = f"  [dim]{reason}[/dim]" if reason else ""
        console.print(f"  [green]gate passed[/green] [dim]({mode})[/dim]{note}")


def print_figures(figs: dict) -> None:
    """Render the figures a project's plot functions produced (stored by dow)."""
    if not figs:
        return
    if figs.get("plotError"):
        console.print(f"[yellow]plots skipped:[/yellow] {figs['plotError']}")
        return
    figures = figs.get("figures", [])
    if not figures:
        return
    console.print("[bold]Figures[/bold] [dim](project-defined; stored as artifacts)[/dim]")
    table = Table(box=box.SIMPLE, header_style="bold")
    table.add_column("figure")
    table.add_column("bytes", justify="right")
    table.add_column("path")
    for f in figures:
        table.add_row(f.get("filename", "?"), str(f.get("bytes", "")), f.get("path", ""))
    console.print(table)


def print_aggregation(result: dict) -> None:
    """Render a cohort-aggregation bundle: members, aggregator values, figures.

    Also renders cross-spec *suite* bundles (``kind == 'suite'``): the member ids
    are ``spec:version`` and the header names the participating specs.
    """
    name = result.get("spec", "")
    members = result.get("members", [])
    labels = result.get("labels", []) or members
    agg_id = result.get("id", "")
    is_suite = result.get("kind") == "suite"
    if is_suite:
        n_specs = len(result.get("specs", []))
        title = (f"[bold]{name}[/bold]  suite aggregation over {len(members)} versions "
                 f"across {n_specs} spec{'s' if n_specs != 1 else ''}")
    else:
        title = f"[bold]{name}[/bold]  N-way aggregation over {len(members)} versions"
    if agg_id:
        title += f"  ([cyan]{agg_id}[/cyan])"
    panel_title = "dow suite" if is_suite else "dow aggregate"
    console.print(Panel.fit(title, title=panel_title, border_style="blue"))
    shown = ", ".join(
        vid + (f" ({lab})" if lab and lab != vid else "")
        for vid, lab in zip(members, labels)
    )
    console.print(f"[bold]Cohort:[/bold] {shown}")
    if result.get("aggregatorError"):
        console.print(f"[yellow]aggregators skipped:[/yellow] {result['aggregatorError']}")
    aggs = result.get("aggregators", {})
    if aggs:
        table = Table(box=box.SIMPLE, header_style="bold")
        table.add_column("metric")
        table.add_column("value", justify="right")
        for k in sorted(aggs):
            table.add_row(k, _fmt_metric_value(aggs[k]))
        console.print(table)
    elif not result.get("aggregatorError"):
        console.print(
            "[dim]No aggregators configured. Add 'aggregators' under 'evaluation' "
            "in the spec.[/dim]"
        )
    print_figures({
        "figures": result.get("figures", []),
        "plotError": result.get("plotError"),
        "plotRefs": result.get("plotRefs", []),
    })


def print_aggregation_list(name: str, aggregations: list) -> None:
    """Render the list of persisted cohort-aggregation bundles for a spec."""
    console.print(
        Panel.fit(f"[bold]{name}[/bold]  stored aggregations", title="dow aggregate", border_style="blue")
    )
    if not aggregations:
        console.print("[dim]none yet - run 'dow aggregate' to create one[/dim]")
        return
    table = Table(box=box.SIMPLE, header_style="bold")
    table.add_column("id")
    table.add_column("members", justify="right")
    table.add_column("figures", justify="right")
    table.add_column("created")
    for a in aggregations:
        table.add_row(
            a.get("id", "?"),
            str(len(a.get("members", []))),
            str(len(a.get("figures", []))),
            _short_time(a.get("created")),
        )
    console.print(table)
