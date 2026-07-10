"""Model Context Protocol (MCP) server for dow.

Exposes dow's core behavior-versioning workflow - scaffold a spec, capture
versions, compare/explain drift, evaluate, tag, and visualize evolution - as MCP
tools so an AI client can drive dow directly, at full parity with the CLI.

It runs over stdio (the standard MCP transport). Every tool acts on a dow
project directory, resolved in this order:

1. the tool's ``project_dir`` argument, when given;
2. the ``DOW_PROJECT_DIR`` environment variable;
3. the server process's current working directory.

All behavior comes from :mod:`dow.service`, the same headless core the CLI uses,
so these tools stay in lock-step with ``dow`` on the command line. Everything
runs fully offline by default (mock provider + built-in hashing embedder).
"""
from __future__ import annotations

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
and inputs - and measures how AI behavior changes across versions, attributing
each change to a specific configuration field.

Typical loop:
  1. dow_list_specs / dow_init            - find or scaffold a spec
  2. dow_read_spec -> edit -> dow_write_spec  - change ONE field for clean attribution
  3. dow_commit                           - capture a new version (v1, v2, ...)
  4. dow_compare / dow_explain            - drift, stability, verdict, and cause
  5. dow_eval / dow_tag / dow_tree / dow_history / dow_inspect

Refer to versions by name (v1, v2), the shortcuts "last"/"prev", or any label
applied with dow_tag (e.g. "good"). dow_commit(from_version=...) branches from an
earlier version. If a project has a single spec, the `spec` argument can be
omitted. Change one spec field per commit so dow_explain can attribute drift to a
single cause.
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
    dow_commit next. Change one field at a time for clean drift attribution.
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
    custom-evaluator scores (evaluators run automatically). Set `from_version`
    (e.g. "v1") to branch from an earlier version instead of the latest. Add a
    short `message` to describe the change.
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
    project_dir: Optional[str] = None,
) -> dict:
    """Compare two versions: config diff, output difference, semantic drift, stability, verdict.

    Defaults to the last two versions when `a`/`b` are omitted. Accepts version
    names (v1, v2), "last"/"prev", or tags (e.g. "good"). The verdict is one of
    Consistent, Behavior Drift, or Likely Regression.
    """
    return _run(service.compare, _root(project_dir), name=spec, a=a, b=b)


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


# --------------------------------------------------------------------------- #
# history + labels + visualization
# --------------------------------------------------------------------------- #
@mcp.tool()
def dow_history(spec: Optional[str] = None, project_dir: Optional[str] = None) -> dict:
    """List captured versions with stability, tags, per-version change, and eval scores.

    Also reports whether the working spec has uncommitted changes
    (`workingDirty`).
    """
    return _run(service.history, _root(project_dir), name=spec)


@mcp.tool()
def dow_inspect(
    version: Optional[str] = None,
    spec: Optional[str] = None,
    project_dir: Optional[str] = None,
) -> dict:
    """Show one version's full spec config, runtime capture, sample outputs, tags, and eval.

    Defaults to the latest version. Accepts a version name, "last"/"prev", or a tag.
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

    Each edge carries semantic drift, stability change, changed fields, and a
    verdict. Set `mermaid=true` to also include a Mermaid gitGraph string.
    """
    return _run(service.tree, _root(project_dir), name=spec, mermaid=mermaid)


@mcp.tool()
def dow_docs(command: Optional[str] = None) -> dict:
    """Return dow's documentation: the overview, or the help text for one command.

    Call without arguments for the list of documented commands and an overview;
    pass a command name (e.g. "commit") for its detailed docs and examples.
    """
    return _run(service.docs, command)


def main() -> None:
    """Console-script entry point: serve the dow MCP server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
