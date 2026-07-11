"""Model Context Protocol (MCP) server for dow.

Exposes dow's core behavior-versioning workflow - scaffold a spec, capture
versions, compare/explain drift, aggregate reliability over a cohort (or across
specs as a matrix), evaluate, tag, and visualize evolution - as MCP tools so an
AI client can drive dow directly, at full parity with the CLI. Read-only MCP
resources expose dow's docs and the live project's specs as attachable context
(the ``dow://`` URIs below).

It runs over stdio (the standard MCP transport). Every tool acts on a dow
project directory, resolved in this order:

1. the tool's ``project_dir`` argument, when given;
2. the ``DOW_PROJECT_DIR`` environment variable;
3. the server process's current working directory.

Resources are not per-call, so they resolve the project from ``DOW_PROJECT_DIR``
or the working directory only (never a per-tool ``project_dir``).

All behavior comes from :mod:`dow.service`, the same headless core the CLI uses,
so these tools stay in lock-step with ``dow`` on the command line. dow is
data-structure agnostic: it versions the specification and records the project's
own pluggable metrics, and ships no metric, statistic, or plotting code itself.
Everything runs fully offline by default (mock provider + built-in hashing
embedder).
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from . import service

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as exc:  # pragma: no cover - only hit without the extra installed
    raise SystemExit(
        "The dow MCP server requires the 'mcp' package. Install it with:\n"
        "  pip install 'dow[mcp]'\n"
        "or:\n"
        "  pip install mcp"
    ) from exc


INSTRUCTIONS = """\
dow ("Drift Observation Workbench") versions the *complete inference
specification* - prompt, model identity/version, sampling, evaluation config,
and inputs - and tracks how AI behavior changes across versions, attributing
each change to a specific configuration field. It is built for exactly the
moment you are sweeping many prompt versions, models, or sampling settings and
need to know, reliably, what changed and what it did to your metrics.

Typical loop:
  1. dow_list_specs / dow_init            - find or scaffold a spec
  2. dow_read_spec -> edit -> dow_write_spec  - change ONE field for clean attribution
  3. dow_commit                           - capture a new version (v1, v2, ...)
  4. dow_compare / dow_explain            - what changed pairwise, and why
  5. dow_aggregate                        - reliability metrics over a COHORT (K seeds/judges/prompts)
  6. dow_suite                            - aggregate ACROSS specs (the check x model x domain x temp matrix)
  7. dow_eval / dow_tag / dow_tree / dow_history / dow_inspect

Refer to versions by name (v1, v2), the shortcuts "last"/"prev", or any label
applied with dow_tag (e.g. "good"). dow_commit(from_version=...) branches from an
earlier version. If a project has a single spec, the `spec` argument can be
omitted. Change one spec field per commit so dow_explain can attribute drift to a
single cause.

Data-structure agnostic. dow versions the *specification* (the change) and
records the *metrics your project computes*, and is deliberately incurious about
everything else. It ships no coefficients and no plotting library: the spec plugs
in its own metrics (evaluation.metrics), paired comparators (evaluation.comparators),
N-way cohort aggregators (evaluation.aggregators), and plot functions
(evaluation.plots); dow only wires them in and stores what they return - including
opaque per-item payloads it persists faithfully whatever their in-memory type.
dow's built-in text signals (semantic drift, stability, verdict) are a convenience
default for text outputs, not an assumption: set evaluation.embedding_model to
"none" when a version's behavior is not free text, and dow_compare/dow_explain/
dow_tree/dow_inspect/dow_history return those built-ins as null (driftEnabled is
false) and rely on the configuration diff plus your own metrics instead.

Context resources: read dow://overview for this guide, dow://docs/<command> for a
command's full help, dow://specs for the project's spec index, and
dow://spec/<name> for a spec's raw YAML.

Backends: the spec's model.provider selects where generations come from - "mock"
(default; fully offline and deterministic), "openai", "ollama", or "vllm" (a vLLM
OpenAI-compatible server, local or remote; set VLLM_BASE_URL, default
http://localhost:8000/v1, and VLLM_API_KEY if required). Change it with
dow_write_spec like any other field; everything runs offline on "mock".
"""

mcp = FastMCP("dow", instructions=INSTRUCTIONS)


def _root(project_dir: Optional[str]) -> Path:
    """Resolve the dow project directory (arg > DOW_PROJECT_DIR > cwd)."""
    if project_dir:
        return Path(project_dir).expanduser()
    env = os.environ.get("DOW_PROJECT_DIR")
    return Path(env).expanduser() if env else Path.cwd()


def _run(fn, *args, **kwargs) -> dict:
    """Call a service function, turning expected user errors into structured output."""
    try:
        return fn(*args, **kwargs)
    except (service.DowError, FileNotFoundError) as exc:
        return {"error": str(exc)}


# --------------------------------------------------------------------------- #
# discovery + spec editing
# --------------------------------------------------------------------------- #
@mcp.tool()
def dow_list_specs(project_dir: Optional[str] = None) -> dict:
    """List every spec in the project with its captured-version count and latest version.

    Use this first to discover what specs exist and how many versions each has.
    """
    return _run(service.list_specs, _root(project_dir))


@mcp.tool()
def dow_init(name: str = service.EXAMPLE_NAME, project_dir: Optional[str] = None) -> dict:
    """Scaffold a starter spec at specs/<name>.yaml (and evals.py) to begin versioning.

    Creates an offline, ready-to-run example (mock provider + hashing embedder).
    Fails if the spec already exists. Follow with dow_read_spec/dow_write_spec to
    customize, then dow_commit to capture v1.
    """
    return _run(service.init_spec, _root(project_dir), name)


@mcp.tool()
def dow_read_spec(spec: Optional[str] = None, project_dir: Optional[str] = None) -> dict:
    """Return the raw YAML text of a working spec file so it can be inspected or edited.

    Omit `spec` when the project has exactly one spec. Pair with dow_write_spec to
    make edits.
    """
    return _run(service.read_spec, _root(project_dir), spec)


@mcp.tool()
def dow_write_spec(
    text: str, spec: Optional[str] = None, project_dir: Optional[str] = None
) -> dict:
    """Create or overwrite a working spec file with `text` (full YAML) and validate it.

    The write always happens; the result reports whether the YAML parsed
    (`valid`) and any `error`. To capture the result as a version, call
    dow_commit next. Change one field at a time for clean drift attribution. Set
    `evaluation.embedding_model: none` when outputs are not text (labels, vectors,
    scores): dow then skips its built-in lexical drift and relies on your
    plugged-in metrics.
    """
    return _run(service.write_spec, _root(project_dir), spec, text)


# --------------------------------------------------------------------------- #
# capture + analysis
# --------------------------------------------------------------------------- #
@mcp.tool()
def dow_commit(
    spec: Optional[str] = None,
    message: Optional[str] = None,
    from_version: Optional[str] = None,
    project_dir: Optional[str] = None,
) -> dict:
    """Run the spec N times and capture its behavior as a new version (v1, v2, ...).

    Returns the new version id, stability, fingerprint, sample outputs, and any
    custom-evaluator scores (evaluators run automatically). When the spec sets
    `embedding_model: none` (outputs are not text) stability is null, and the
    evaluator scores plus the configuration are what describe the version. Set
    `from_version` (e.g. "v1") to branch from an earlier version instead of the
    latest. Add a short `message` to describe the change.
    """
    return _run(
        service.commit,
        _root(project_dir),
        name=spec,
        message=message,
        from_version=from_version,
    )


@mcp.tool()
def dow_compare(
    a: Optional[str] = None,
    b: Optional[str] = None,
    spec: Optional[str] = None,
    plot: bool = False,
    project_dir: Optional[str] = None,
) -> dict:
    """Compare two versions: config diff, output difference, semantic drift, stability, verdict.

    Defaults to the last two versions when `a`/`b` are omitted. Accepts version
    names (v1, v2), "last"/"prev", or tags (e.g. "good"). The verdict is one of
    Consistent, Behavior Drift, or Likely Regression. If the spec lists
    `evaluation.comparators` (the project's own paired metrics), their results are
    returned under `comparators` (each a number or an {estimate, ci_low, ci_high}).
    When the spec sets `embedding_model: none` (outputs are not text) the built-in
    output difference, drift, stability, and verdict come back null and
    `driftEnabled` is false, so the client leans on the configuration diff and the
    comparators instead. With `plot=true` the spec's `evaluation.plots` functions
    render the comparison and dow stores the figures they produce as
    content-addressed artifacts.
    """
    return _run(service.compare, _root(project_dir), name=spec, a=a, b=b, plot=plot)


@mcp.tool()
def dow_explain(
    a: Optional[str] = None,
    b: Optional[str] = None,
    spec: Optional[str] = None,
    project_dir: Optional[str] = None,
) -> dict:
    """Explain WHY behavior changed between two versions (causal attribution).

    Reports the changed field(s) and, when exactly one field changed, names it as
    the cause. Flags `confounded=true` when more than one field changed (so the
    effect cannot be pinned on a single cause). Defaults to the last two versions.
    Any configured `evaluation.comparators` (the project's paired metrics) are
    returned under `comparators` alongside the attribution. With
    `embedding_model: none` the drift and verdict fields are null (`driftEnabled`
    is false); the attribution then rests on the configuration diff and your
    comparators.
    """
    return _run(service.explain, _root(project_dir), name=spec, a=a, b=b)


@mcp.tool()
def dow_eval(
    version: Optional[str] = None,
    rerun: bool = False,
    good_tag: str = "good",
    draft: bool = False,
    spec: Optional[str] = None,
    project_dir: Optional[str] = None,
) -> dict:
    """Run the spec's custom evaluators for a version, vs. the previous and last-good versions.

    Scores come from the evaluators listed under `evaluation.metrics` in the spec.
    Saved results are reused unless `rerun=true`. Set `draft=true` to score the
    current working spec WITHOUT committing a version. `good_tag` selects which
    tag marks the known-good baseline (default "good").
    """
    return _run(
        service.evaluate,
        _root(project_dir),
        name=spec,
        version=version,
        rerun=rerun,
        good_tag=good_tag,
        draft=draft,
    )


@mcp.tool()
def dow_aggregate(
    versions: Optional[list] = None,
    tag: Optional[str] = None,
    plot: bool = False,
    list_bundles: bool = False,
    show: Optional[str] = None,
    spec: Optional[str] = None,
    project_dir: Optional[str] = None,
) -> dict:
    """Aggregate reliability metrics over a COHORT of versions (the N-way sibling of dow_compare).

    Where dow_compare contrasts two versions, this runs the project's own N-way
    aggregators (listed under `evaluation.aggregators`) over a whole cohort - K
    seeds, judges, prompt wordings, or permutations - selected by an explicit
    `versions` list, a `tag`, or (by default) the spec's entire history. Each
    aggregator sees every member aligned per item through its captured payload,
    which is what a reliability coefficient over K raters needs (ICC, Fleiss/Gwet,
    Krippendorff's alpha, ...); dow ships none of them. With `plot=true` the spec's
    `evaluation.plots` functions render the results and dow stores each figure as a
    content-addressed artifact. Every run is saved as a durable, git-tracked
    bundle: set `list_bundles=true` to list them or `show=<id>` to fetch one.
    """
    root = _root(project_dir)
    if list_bundles:
        return _run(service.aggregations, root, name=spec)
    if show:
        return _run(service.get_aggregation, root, name=spec, agg_id=show)
    return _run(service.aggregate, root, name=spec, versions=versions, tag=tag, plot=plot)


@mcp.tool()
def dow_suite(
    name: Optional[str] = None,
    select: str = "all",
    plot: bool = False,
    list_bundles: bool = False,
    show: Optional[str] = None,
    project_dir: Optional[str] = None,
) -> dict:
    """Aggregate versions ACROSS several specs - the cross-spec matrix sibling of dow_aggregate.

    Where dow_aggregate runs the project's N-way aggregators over a cohort within
    ONE spec, this runs them over versions drawn from SEVERAL specs (the
    check x model x domain x temperature matrix) declared in a manifest,
    `specs/<name>.suite.yaml` (its `specs:` list plus `evaluation.aggregators`/
    `plots`). `select` chooses the cohort: "all" (every version of each listed
    spec, the default), "latest" (each spec's newest version), or a tag name
    (each spec's versions carrying that tag). Each member keeps its own captured
    config so an aggregator can bucket by spec/axis; dow ships none of the
    coefficients or the plotting library. With `plot=true` the manifest's plot
    functions render the matrix and dow stores each figure as a content-addressed
    artifact. Every run is a durable, git-tracked suite bundle: set
    `list_bundles=true` to list them or `show=<id>` to fetch one.
    """
    root = _root(project_dir)
    if list_bundles:
        return _run(service.suite_aggregations, root, name=name)
    if show:
        return _run(service.get_suite_aggregation, root, name=name, agg_id=show)
    return _run(service.aggregate_suite, root, name=name, select=select, plot=plot)


# --------------------------------------------------------------------------- #
# history + labels + visualization
# --------------------------------------------------------------------------- #
@mcp.tool()
def dow_history(spec: Optional[str] = None, project_dir: Optional[str] = None) -> dict:
    """List captured versions with stability, tags, per-version change, and eval scores.

    Also reports whether the working spec has uncommitted changes
    (`workingDirty`). Stability is null for specs that set `embedding_model: none`;
    the evaluator scores describe those versions instead.
    """
    return _run(service.history, _root(project_dir), name=spec)


@mcp.tool()
def dow_inspect(
    version: Optional[str] = None,
    spec: Optional[str] = None,
    project_dir: Optional[str] = None,
) -> dict:
    """Show one version's full spec config, runtime capture, sample outputs, tags, and eval.

    Defaults to the latest version. Accepts a version name, "last"/"prev", or a
    tag. Stability is null when the spec sets `embedding_model: none`.
    """
    return _run(service.inspect, _root(project_dir), name=spec, version=version)


@mcp.tool()
def dow_tag(
    label: str,
    version: Optional[str] = None,
    spec: Optional[str] = None,
    project_dir: Optional[str] = None,
) -> dict:
    """Attach a free-form label (e.g. good, golden, baseline, bad) to a version.

    Tags become usable version references (e.g. in dow_compare or as the
    `good_tag` in dow_eval). Defaults to tagging the latest version.
    """
    return _run(service.tag, _root(project_dir), name=spec, label=label, version=version)


@mcp.tool()
def dow_tree(
    spec: Optional[str] = None,
    mermaid: bool = False,
    project_dir: Optional[str] = None,
) -> dict:
    """Return the version-evolution tree: nodes with stability and parent->child drift edges.

    Each edge carries the changed fields plus - when built-in text drift is on -
    semantic drift, stability change, and a verdict; those three are null for
    specs that set `embedding_model: none`. Set `mermaid=true` to also include a
    Mermaid gitGraph string.
    """
    return _run(service.tree, _root(project_dir), name=spec, mermaid=mermaid)


@mcp.tool()
def dow_docs(command: Optional[str] = None) -> dict:
    """Return dow's documentation: the overview, or the help text for one command.

    Call without arguments for the list of documented commands and an overview;
    pass a command name (e.g. "commit") for its detailed docs and examples.
    """
    return _run(service.docs, command)


# --------------------------------------------------------------------------- #
# resources: read-only context an MCP client can attach (docs + live project)
# --------------------------------------------------------------------------- #
# Resources are not per-call: they resolve the project from DOW_PROJECT_DIR or the
# working directory, never a per-tool project_dir argument.
@mcp.resource("dow://overview", name="dow overview", mime_type="text/markdown")
def overview_resource() -> str:
    """dow's purpose, the typical loop, and its data-structure-agnostic design."""
    commands = ", ".join(service._doc_commands())
    return f"{INSTRUCTIONS}\nDocumented commands: {commands}.\n"


@mcp.resource("dow://docs/{command}", name="dow command docs", mime_type="text/plain")
def command_docs_resource(command: str) -> str:
    """Full help text and examples for one dow command (e.g. 'compare')."""
    return service.docs(command)["text"]


@mcp.resource("dow://specs", name="dow project specs", mime_type="application/json")
def specs_resource() -> str:
    """The resolved project's spec index (names, version counts, latest) as JSON."""
    return json.dumps(_run(service.list_specs, _root(None)), indent=2, default=str)


@mcp.resource("dow://spec/{name}", name="dow spec source", mime_type="text/plain")
def spec_source_resource(name: str) -> str:
    """The raw YAML source of one working spec in the resolved project."""
    result = _run(service.read_spec, _root(None), name)
    return result.get("text") or json.dumps(result, default=str)


def main() -> None:
    """Console-script entry point: serve the dow MCP server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
