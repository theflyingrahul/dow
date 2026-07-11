"""Headless service layer: dow's core operations as plain data.

This module is the single source of truth for the behavioral logic behind the
CLI *and* the MCP server. Every function takes a project ``root`` and returns
JSON-serializable dicts/lists (no Rich, no Typer, no HTTP), so any front end can
drive dow without shelling out or parsing terminal output.

The CLI (``dow.cli``) renders these results with Rich; the MCP server
(``dow.mcp_server``) forwards them to a model. Because both share this layer,
the two surfaces can never drift apart.
"""
from __future__ import annotations

import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .embeddings import get_embedder
from .evaluators import (
    CohortContext,
    CompareContext,
    PlotContext,
    build_eval_context,
    evaluate_version,
    run_aggregators,
    run_comparators,
    run_plotters,
)
from .metrics import output_difference, semantic_drift, stability
from .metrics import verdict as compute_verdict
from .runner import execute
from .spec import InferenceSpec, SuiteSpec, flatten
from .store import Store

SPECS_DIR = "specs"
SUITE_SUFFIX = ".suite.yaml"
DOCS_DIR = Path(__file__).parent / "docs"
EXAMPLE_NAME = "summarization"

EXAMPLE_SPEC = """# specs/summarization.yaml - a fully versioned inference specification
spec_version: 1
name: summarization
task: Summarize a customer support ticket

# operation: ""                     # optional: label a non-generation op (relabel, recluster, subsample, ...)
# params: {}                        # optional: free-form perturbation params - fingerprinted and diff-attributed

prompt:
  system: You are an assistant that writes concise summaries.
  template: |
    Summarize the following ticket:

    {input}
  few_shot: []

model:
  provider: mock                    # mock | openai | ollama | vllm
  name: mock-summarizer             # for vllm: the served model name (--served-model-name)
  version: mock-2024-07-18          # pinned snapshot, never a floating alias
  revision: null                    # model commit or revision hash for open-weight models
  # vllm talks to an OpenAI-compatible server: set VLLM_BASE_URL for a remote host
  # (default http://localhost:8000/v1) and VLLM_API_KEY if it was started with --api-key.

sampling:
  temperature: 0.2
  top_p: 1.0
  max_tokens: 256
  frequency_penalty: 0.0
  presence_penalty: 0.0
  stop: null
  seed: 7

evaluation:
  embedding_model: hashing-256      # text default; a sentence-transformers id; or 'none' if outputs aren't text
  samples: 5
  metrics:                          # your own evaluators: path.py:function (see evals.py)
    - evals.py:avg_word_count
    - evals.py:mentions_order_id
  # comparators:                    # your own PAIRED metrics over two versions (see evals.py).
  #   - evals.py:label_flip_rate    # agreement/reliability coefficients live here (kappa, alpha, ...)
  # aggregators:                    # your own N-WAY metrics over a COHORT of versions (see evals.py).
  #   - evals.py:mean_pairwise_flip # reliability over K raters (ICC, Fleiss/Gwet, Krippendorff, ...)
  # plots:                          # your own plot functions; dow stores the figures (ships no matplotlib).
  #   - evals.py:plot_flip
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


def label_flip_rate(cctx):
    """Example paired COMPARATOR (not run by default).

    A comparator is the paired counterpart of an evaluator: it receives a
    CompareContext with BOTH versions (cctx.a, cctx.b) aligned per item through
    their captured payload - what an agreement/reliability coefficient needs. It
    may return a plain number or an {"estimate": .., "ci_low": .., "ci_high": ..}
    band. Reference it under evaluation.comparators. Needs a provider that
    captures a per-item payload of labels (e.g. the python provider).
    """
    a = (cctx.a.payload or {}).get("labels", [])
    b = (cctx.b.payload or {}).get("labels", [])
    pairs = list(zip(a, b))
    if not pairs:
        return 0.0
    return sum(1 for x, y in pairs if x != y) / len(pairs)


def mean_pairwise_flip(cctx):
    """Example N-way AGGREGATOR (not run by default).

    Where a comparator sees two versions, an aggregator sees the whole cohort:
    cctx.members is one EvalContext per version, aligned per item through their
    captured payloads. This is where a reliability coefficient over K raters
    lives (ICC, Fleiss/Gwet, Krippendorff's alpha, ...); dow ships none of
    them. Here: the mean pairwise label-flip rate across every pair of members.
    """
    grids = [(m.payload or {}).get("labels", []) for m in cctx.members]
    pairs, total = 0, 0.0
    for i in range(len(grids)):
        for j in range(i + 1, len(grids)):
            z = list(zip(grids[i], grids[j]))
            if z:
                total += sum(1 for x, y in z if x != y) / len(z)
                pairs += 1
    return {"mean_pairwise_flip": total / pairs if pairs else 0.0}


def plot_flip(pctx):
    """Example PLOT function (not run by default): dow ships no plotting library.

    A plot receives a PlotContext with the analysis `results` to render and a
    dow-provided `out_dir` to write into, and returns the path(s) it wrote; dow
    stores each as a content-addressed artifact. This stub writes a tiny SVG so
    the example stays dependency-free - a real project would use matplotlib.
    """
    import os
    val = (pctx.results or {}).get("mean_pairwise_flip", 0.0)
    if isinstance(val, dict):
        val = val.get("estimate", 0.0)
    out = os.path.join(pctx.out_dir, f"{pctx.name or 'figure'}.svg")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(
            '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="60">'
            f'<rect width="{max(1, int(val * 200))}" height="30" fill="#0072B2"/>'
            f'<text x="4" y="50" font-size="12">flip={val:.3f}</text></svg>'
        )
    return out
'''


class DowError(ValueError):
    """A user-facing error (bad reference, missing spec, ...).

    Subclasses ``ValueError`` so existing ``except ValueError`` handlers in the
    CLI keep working; the CLI converts it to ``typer.BadParameter`` and the MCP
    server converts it to a structured tool error.
    """


# --------------------------------------------------------------------------- #
# spec discovery / scaffolding
# --------------------------------------------------------------------------- #
def specs_dir(root) -> Path:
    return Path(root) / SPECS_DIR


def spec_path(root, name: str) -> Path:
    return specs_dir(root) / f"{name}.yaml"


def spec_files(root) -> list:
    d = specs_dir(root)
    if not d.is_dir():
        return []
    return sorted(f for f in d.glob("*.yaml") if not f.name.endswith(SUITE_SUFFIX))


def suite_path(root, name: str) -> Path:
    return specs_dir(root) / f"{name}{SUITE_SUFFIX}"


def suite_files(root) -> list:
    d = specs_dir(root)
    return sorted(d.glob(f"*{SUITE_SUFFIX}")) if d.is_dir() else []


def find_suite_name(root, name: Optional[str]) -> Optional[str]:
    if name:
        stem = Path(name).name
        for suffix in (SUITE_SUFFIX, ".yaml"):
            if stem.endswith(suffix):
                stem = stem[: -len(suffix)]
                break
        return stem
    files = suite_files(root)
    if len(files) == 1:
        return files[0].name[: -len(SUITE_SUFFIX)]
    if len(files) > 1:
        names = ", ".join(f.name[: -len(SUITE_SUFFIX)] for f in files)
        raise DowError(f"Multiple suites found; pass suite=NAME. Found: {names}")
    return None


def need_suite(root, name: Optional[str]) -> str:
    resolved = find_suite_name(root, name)
    if not resolved:
        raise DowError(
            "No suite manifest found. Create specs/<name>.suite.yaml "
            "(listing the specs: and evaluation.aggregators: to aggregate across)."
        )
    return resolved


def find_spec_name(root, name: Optional[str]) -> Optional[str]:
    if name:
        return Path(name).stem
    files = spec_files(root)
    if len(files) == 1:
        return files[0].stem
    if len(files) > 1:
        names = ", ".join(f.stem for f in files)
        raise DowError(f"Multiple specs found; pass spec=NAME. Found: {names}")
    return None


def need_spec(root, name: Optional[str]) -> str:
    resolved = find_spec_name(root, name)
    if not resolved:
        raise DowError("No spec found. Run 'dow init' (or the init tool) to get started.")
    return resolved


def render_example_spec(name: str) -> str:
    """Starter spec text with its header and name field set to ``name``."""
    return EXAMPLE_SPEC.replace(
        f"# specs/{EXAMPLE_NAME}.yaml", f"# specs/{name}.yaml", 1
    ).replace(f"name: {EXAMPLE_NAME}", f"name: {name}", 1)


def init_spec(root, name: str = EXAMPLE_NAME) -> dict:
    """Scaffold ``specs/<name>.yaml`` (and ``evals.py`` if absent)."""
    root = Path(root)
    stem = Path(name).stem  # tolerate 'specs/foo.yaml' or 'foo.yaml'
    path = spec_path(root, stem)
    if path.exists():
        raise DowError(
            f"Spec already exists: {SPECS_DIR}/{stem}.yaml (edit it, then 'dow commit')."
        )
    specs_dir(root).mkdir(parents=True, exist_ok=True)
    path.write_text(render_example_spec(stem), encoding="utf-8")
    created = [f"{SPECS_DIR}/{stem}.yaml"]
    evals_path = root / "evals.py"
    if not evals_path.exists():
        evals_path.write_text(EXAMPLE_EVALS, encoding="utf-8")
        created.append("evals.py")
    return {"spec": stem, "created": created, "specPath": f"{SPECS_DIR}/{stem}.yaml"}


def _store_spec_names(store: Store) -> list:
    import json

    if not store.index_path.exists():
        return []
    index = json.loads(store.index_path.read_text(encoding="utf-8"))
    return list(index.get("specs", {}).keys())


def list_specs(root) -> dict:
    """Every spec dow knows about: working files first, then committed-only ones."""
    root = Path(root)
    store = Store(root)
    names: list = [f.stem for f in spec_files(root)]
    for n in _store_spec_names(store):
        if n not in names:
            names.append(n)
    specs = []
    for n in names:
        versions = store.list_versions(n)
        specs.append(
            {
                "name": n,
                "versions": len(versions),
                "latest": versions[-1]["id"] if versions else None,
                "hasWorkingFile": spec_path(root, n).exists(),
            }
        )
    return {"root": str(root), "specs": specs}


def read_spec(root, name: Optional[str] = None) -> dict:
    """Raw YAML text of a working spec file."""
    root = Path(root)
    name = need_spec(root, name)
    path = spec_path(root, name)
    if not path.exists():
        raise DowError(f"Spec not found: {SPECS_DIR}/{name}.yaml")
    return {"spec": name, "path": f"{SPECS_DIR}/{name}.yaml", "text": path.read_text(encoding="utf-8")}


def write_spec(root, name: Optional[str] = None, text: Optional[str] = None) -> dict:
    """Create or overwrite a working spec file, validating it (edit warns, save keeps)."""
    if not isinstance(text, str):
        raise DowError("Spec text is required.")
    root = Path(root)
    stem = Path(name).stem if name else need_spec(root, None)
    path = spec_path(root, stem)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    valid, error = True, None
    try:  # validate so the caller can warn; the edit is saved either way
        InferenceSpec.load(path)
    except Exception as exc:  # noqa: BLE001 - any parse/validation issue is a warning
        valid, error = False, str(exc)
    return {
        "spec": stem,
        "path": f"{SPECS_DIR}/{stem}.yaml",
        "valid": valid,
        "error": error,
    }


# --------------------------------------------------------------------------- #
# version resolution + shared computation (reused by the CLI)
# --------------------------------------------------------------------------- #
def resolve(store: Store, name: str, ref: str) -> str:
    try:
        return store.resolve(name, ref)
    except ValueError as exc:
        raise DowError(str(exc))


def resolve_pair(store: Store, name: str, a: Optional[str], b: Optional[str]):
    versions = store.list_versions(name)
    if a is None and b is None:
        if len(versions) < 2:
            raise DowError(
                "Need at least two versions. Change your spec and run 'dow commit' again."
            )
        return versions[-2]["id"], versions[-1]["id"]
    if b is None:
        return resolve(store, name, a), versions[-1]["id"]
    return resolve(store, name, a), resolve(store, name, b)


def _round(x, n: int = 4):
    """Round a real number; pass ``None`` through - the built-in text-drift
    signals are absent when a spec opts out with ``embedding_model: none``."""
    return round(x, n) if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def config_diff(a_cfg: dict, b_cfg: dict) -> dict:
    """Flattened field-by-field difference: ``{dotted_key: (old, new)}``."""
    fa, fb = flatten(a_cfg), flatten(b_cfg)
    diff = {}
    for k in sorted(set(fa) | set(fb)):
        if fa.get(k) != fb.get(k):
            diff[k] = (fa.get(k), fb.get(k))
    return diff


def run_comparisons(store: Store, a: dict, b: dict, a_id: str, b_id: str, cfg_diff: dict) -> dict:
    """Run the variant's configured paired comparators over both versions.

    Comparators are the project's own callables (agreement/reliability
    coefficients); dow only wires them in. A comparator failure is captured, not
    raised, so ``compare``/``explain`` still return the built-in signals.
    """
    refs = b.get("config", {}).get("evaluation", {}).get("comparators", []) or []
    if not refs:
        return {"comparators": {}, "comparatorRefs": [], "comparatorError": None}
    try:
        cctx = CompareContext(
            a=build_eval_context(a),
            b=build_eval_context(b),
            config_diff=_diff_json(cfg_diff),
            a_id=a_id,
            b_id=b_id,
        )
        results = run_comparators(refs, cctx, store.root)
        return {"comparators": results, "comparatorRefs": list(refs), "comparatorError": None}
    except Exception as exc:  # noqa: BLE001 - a comparator bug must not break compare
        return {"comparators": {}, "comparatorRefs": list(refs), "comparatorError": str(exc)}


def compare_records(store: Store, name: str, a_id: str, b_id: str) -> dict:
    """Full-precision comparison of two captured versions (the ``dow compare`` core)."""
    a = store.get_record(name, a_id)
    b = store.get_record(name, b_id)
    a_out = [s["output"] for s in a["samples"]]
    b_out = [s["output"] for s in b["samples"]]
    embedder = get_embedder(b["config"]["evaluation"]["embedding_model"])
    cfg_diff = config_diff(a["config"], b["config"])
    thresholds = b["config"]["evaluation"]["thresholds"]
    if getattr(embedder, "enabled", True):
        a_emb, b_emb = embedder.embed(a_out), embedder.embed(b_out)
        drift = semantic_drift(a_emb, b_emb)
        stab_a, stab_b = stability(a_emb), stability(b_emb)
        outdiff = output_difference(a_out, b_out)
        label = compute_verdict(drift, stab_a, stab_b, thresholds)
        stab_change = stab_b - stab_a
    else:
        drift = stab_a = stab_b = outdiff = label = stab_change = None
    comp = run_comparisons(store, a, b, a_id, b_id, cfg_diff)
    return {
        "config_diff": cfg_diff,
        "output_difference": outdiff,
        "semantic_drift": drift,
        "stability_a": stab_a,
        "stability_b": stab_b,
        "stability_change": stab_change,
        "verdict": label,
        "drift_enabled": bool(getattr(embedder, "enabled", True)),
        "embedding_model": embedder.name,
        "thresholds": thresholds,
        "comparators": comp["comparators"],
        "comparator_refs": comp["comparatorRefs"],
        "comparator_error": comp["comparatorError"],
    }


# --------------------------------------------------------------------------- #
# N-way cohort aggregation + pluggable plotting
# (project code plugs in the coefficients and the plot functions; dow ships
# neither - it only selects the cohort, wires the callables, and stores results)
# --------------------------------------------------------------------------- #
def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def select_cohort(store: Store, name: str, versions=None, tag: Optional[str] = None) -> list:
    """Resolve the set of versions an aggregation runs over.

    Precedence: an explicit ``versions`` list (each resolved like any ref), else
    every version carrying ``tag``, else the spec's entire version history.
    """
    all_ids = [v["id"] for v in store.list_versions(name)]
    if not all_ids:
        raise DowError("No versions yet. Run 'dow commit' first.")
    if versions:
        return [resolve(store, name, v) for v in versions]
    if tag:
        ids = store.versions_with_tag(name, tag)
        if not ids:
            raise DowError(
                f"No versions tagged '{tag}'. Tag members with 'dow tag {tag} <version>'."
            )
        return ids
    return all_ids


def _member_label(store: Store, name: str, vid: str) -> str:
    tags = store.meta(name, vid).get("tags", []) or []
    return str(tags[0]) if tags else vid


def run_aggregations(store: Store, name: str, records: list, member_ids: list, refs: list, base_dir) -> dict:
    """Run the cohort's configured N-way aggregators over all member versions.

    Aggregators are the project's own callables (reliability coefficients over K
    raters); dow only wires them in. A failure is captured, not raised, so the op
    still returns.
    """
    if not refs:
        return {"aggregators": {}, "aggregatorRefs": [], "aggregatorError": None}
    try:
        members = [build_eval_context(r) for r in records]
        labels = [_member_label(store, name, vid) for vid in member_ids]
        cctx = CohortContext(members=members, ids=list(member_ids), labels=labels, name=name)
        results = run_aggregators(refs, cctx, base_dir)
        return {"aggregators": results, "aggregatorRefs": list(refs), "aggregatorError": None}
    except Exception as exc:  # noqa: BLE001 - an aggregator bug must not break the op
        return {"aggregators": {}, "aggregatorRefs": list(refs), "aggregatorError": str(exc)}


def run_plots(store: Store, refs: list, results: dict, records: list, ids: list, base_dir, kind: str, name: str) -> dict:
    """Run the project's plot callables and store each produced figure.

    dow ships no plotting library. Each plotter writes figure file(s) into a
    dow-provided temp dir and returns their path(s); dow copies each into the
    content-addressed artifact store and returns the references. A failure is
    captured, not raised.
    """
    if not refs:
        return {"figures": [], "plotRefs": [], "plotError": None}
    out_dir = tempfile.mkdtemp(prefix="dow-plot-")
    try:
        pctx = PlotContext(
            results=results or {}, out_dir=out_dir, kind=kind, name=name,
            ids=list(ids), records=records,
        )
        produced = run_plotters(refs, pctx, base_dir)
        figures = [store.store_figure(p) for p in produced if Path(p).exists()]
        return {"figures": figures, "plotRefs": list(refs), "plotError": None}
    except Exception as exc:  # noqa: BLE001 - a plot bug must not break the op
        return {"figures": [], "plotRefs": list(refs), "plotError": str(exc)}
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)


def _cohort_analysis_refs(records: list, key: str) -> list:
    """Read the analysis refs (aggregators/plots) from the cohort's config.

    The analysis block is shared across a cohort (members differ only in the
    perturbed field), so the first member's captured config is authoritative.
    """
    if not records:
        return []
    return records[0].get("config", {}).get("evaluation", {}).get(key, []) or []


def aggregate(root, name: Optional[str] = None, versions=None, tag: Optional[str] = None,
              plot: bool = False, refs=None, plot_refs=None, save: bool = True) -> dict:
    """Run N-way aggregators over a cohort of versions and persist the bundle.

    The many-version counterpart of ``compare``: instead of a single
    baseline-vs-variant pair, it runs the project's reliability coefficients over
    a whole cohort (K seeds / judges / prompt wordings / permutations) selected by
    an explicit list, a ``tag``, or the full history. The structured result
    (aggregator values + any figures + provenance) is saved as a durable,
    git-tracked bundle, so a robustness check becomes a citable, reproducible
    object. dow ships none of the coefficients or the plotting library.
    """
    root = Path(root)
    name = need_spec(root, name)
    store = Store(root)
    store.ensure()
    member_ids = select_cohort(store, name, versions, tag)
    records = [store.get_record(name, vid) for vid in member_ids]
    if refs is None:
        refs = _cohort_analysis_refs(records, "aggregators")
    agg = run_aggregations(store, name, records, member_ids, refs, root)

    figs = {"figures": [], "plotRefs": [], "plotError": None}
    if plot:
        if plot_refs is None:
            plot_refs = _cohort_analysis_refs(records, "plots")
        figs = run_plots(store, plot_refs, agg["aggregators"], records, member_ids, root, "aggregate", name)

    result = {
        "spec": name,
        "members": list(member_ids),
        "labels": [_member_label(store, name, vid) for vid in member_ids],
        "fingerprints": {vid: store.meta(name, vid).get("fingerprint") for vid in member_ids},
        "created": _now_iso(),
        "aggregators": agg["aggregators"],
        "aggregatorRefs": agg["aggregatorRefs"],
        "aggregatorError": agg["aggregatorError"],
        "figures": figs["figures"],
        "plotRefs": figs["plotRefs"],
        "plotError": figs["plotError"],
    }
    if save:
        result["id"] = store.save_aggregation(name, result)
    return result


def aggregations(root, name: Optional[str] = None) -> dict:
    """List the persisted cohort-aggregation bundles for a spec."""
    root = Path(root)
    name = need_spec(root, name)
    store = Store(root)
    return {"spec": name, "aggregations": store.list_aggregations(name)}


def get_aggregation(root, name: Optional[str] = None, agg_id: Optional[str] = None) -> dict:
    """Return one persisted cohort-aggregation bundle by id."""
    root = Path(root)
    name = need_spec(root, name)
    store = Store(root)
    if not agg_id:
        raise DowError("Provide an aggregation id (e.g. a1). List them with 'dow aggregate --list'.")
    try:
        return store.get_aggregation(name, agg_id)
    except (FileNotFoundError, ValueError) as exc:
        raise DowError(str(exc))


# --------------------------------------------------------------------------- #
# suites - aggregate versions across several specs (the check x model x domain
# x temperature matrix). dow only wires the members in; the project supplies the
# aggregators/plots, exactly as for a single-spec aggregate.
# --------------------------------------------------------------------------- #
def load_suite(root, name: Optional[str] = None) -> SuiteSpec:
    """Load and validate a suite manifest (specs/<name>.suite.yaml)."""
    root = Path(root)
    name = need_suite(root, name)
    path = suite_path(root, name)
    if not path.exists():
        raise DowError(f"Suite manifest not found: {SPECS_DIR}/{name}{SUITE_SUFFIX}")
    suite = SuiteSpec.load(path)
    if not suite.specs:
        raise DowError(
            f"Suite '{name}' lists no specs. Add a 'specs:' list of the inference "
            "specs whose versions should be aggregated together."
        )
    if not suite.aggregators:
        raise DowError(
            f"Suite '{name}' declares no evaluation.aggregators. A suite aggregates "
            "with the project's own callables; dow ships none."
        )
    return suite


def list_suites(root) -> dict:
    """Every suite manifest dow knows about, with member-spec counts."""
    root = Path(root)
    store = Store(root)
    suites = []
    for f in suite_files(root):
        sname = f.name[: -len(SUITE_SUFFIX)]
        try:
            suite = SuiteSpec.load(f)
        except Exception:  # noqa: BLE001 - a malformed manifest must not break listing
            suites.append({"name": sname, "specs": [], "valid": False})
            continue
        members = 0
        for spec in suite.specs:
            members += len(store.list_versions(spec))
        suites.append({
            "name": sname,
            "specs": list(suite.specs),
            "select": suite.select,
            "members": members,
            "valid": True,
        })
    return {"root": str(root), "suites": suites}


def select_suite(store: Store, suite: SuiteSpec, select: Optional[str] = None) -> list:
    """Resolve the (spec, version-id) members a suite aggregation runs over.

    ``select`` (overriding the manifest's): ``all`` = every version of each listed
    spec (the full matrix), ``latest`` = each spec's latest version, else a tag name
    = every version carrying that tag across the listed specs. Specs with no matching
    versions are skipped; an entirely empty selection is an error.
    """
    mode = (select or suite.select or "all").strip()
    members: list = []
    for spec in suite.specs:
        vids = [v["id"] for v in store.list_versions(spec)]
        if not vids:
            continue
        if mode == "all":
            chosen = vids
        elif mode == "latest":
            chosen = [vids[-1]]
        else:  # a tag name
            chosen = store.versions_with_tag(spec, mode)
        for vid in chosen:
            members.append((spec, vid))
    if not members:
        raise DowError(
            f"Suite selection '{mode}' matched no versions across {suite.specs}. "
            "Commit the member specs first (or check the tag)."
        )
    return members


def aggregate_suite(root, name: Optional[str] = None, select: Optional[str] = None,
                    plot: bool = False, save: bool = True) -> dict:
    """Run the suite's project aggregators over versions drawn from several specs.

    The cross-spec counterpart of :func:`aggregate`. Each member keeps its own
    captured ``config`` (so the aggregator can bucket by spec / model / domain /
    temperature) and ``payload`` (aligned per item). The structured result is saved
    as a durable, git-tracked suite bundle. dow ships none of the coefficients or
    the plotting library.
    """
    root = Path(root)
    suite = load_suite(root, name)
    store = Store(root)
    store.ensure()
    pairs = select_suite(store, suite, select)
    specs = [s for s, _ in pairs]
    records = [store.get_record(s, v) for s, v in pairs]
    member_ids = [f"{s}:{v}" for s, v in pairs]
    labels = []
    for s, v in pairs:
        tags = store.meta(s, v).get("tags", []) or []
        labels.append(str(tags[0]) if tags else f"{s}:{v}")

    agg_results: dict = {}
    agg_error = None
    try:
        members = [build_eval_context(r) for r in records]
        cctx = CohortContext(
            members=members, ids=list(member_ids), labels=labels,
            name=suite.name, specs=list(specs),
        )
        agg_results = run_aggregators(suite.aggregators, cctx, root)
    except Exception as exc:  # noqa: BLE001 - an aggregator bug must not break the op
        agg_error = str(exc)

    figs = {"figures": [], "plotRefs": [], "plotError": None}
    if plot:
        figs = run_plots(store, suite.plots, agg_results, records, member_ids, root, "suite", suite.name)

    result = {
        "suite": suite.name,
        "spec": suite.name,
        "kind": "suite",
        "specs": list(dict.fromkeys(specs)),
        "select": (select or suite.select or "all"),
        "members": list(member_ids),
        "labels": labels,
        "fingerprints": {f"{s}:{v}": store.meta(s, v).get("fingerprint") for s, v in pairs},
        "created": _now_iso(),
        "aggregators": agg_results,
        "aggregatorRefs": list(suite.aggregators),
        "aggregatorError": agg_error,
        "figures": figs["figures"],
        "plotRefs": figs["plotRefs"],
        "plotError": figs["plotError"],
    }
    if save:
        result["id"] = store.save_suite_aggregation(suite.name, result)
    return result


def suite_aggregations(root, name: Optional[str] = None) -> dict:
    """List the persisted cross-spec suite bundles for a suite."""
    root = Path(root)
    name = need_suite(root, name)
    store = Store(root)
    return {"suite": name, "aggregations": store.list_suite_aggregations(name)}


def get_suite_aggregation(root, name: Optional[str] = None, agg_id: Optional[str] = None) -> dict:
    """Return one persisted suite bundle by id."""
    root = Path(root)
    name = need_suite(root, name)
    store = Store(root)
    if not agg_id:
        raise DowError("Provide a suite aggregation id (e.g. a1). List them with 'dow suite --list'.")
    try:
        return store.get_suite_aggregation(name, agg_id)
    except (FileNotFoundError, ValueError) as exc:
        raise DowError(str(exc))


def build_tree_data(store: Store, name: str) -> dict:
    """Per-version stability and parent->child drift/verdict edges (the ``dow tree`` core)."""
    versions = store.list_versions(name)
    if not versions:
        return {"versions": [], "stab": {}, "parent_of": {}, "edges": {}}
    records = {v["id"]: store.get_record(name, v["id"]) for v in versions}
    last_id = versions[-1]["id"]
    embedder = get_embedder(records[last_id]["config"]["evaluation"]["embedding_model"])
    enabled = bool(getattr(embedder, "enabled", True))
    emb, stab = {}, {}
    for v in versions:
        outs = [s["output"] for s in records[v["id"]]["samples"]]
        if enabled:
            e = embedder.embed(outs)
            emb[v["id"]] = e
            stab[v["id"]] = stability(e)
        else:
            stab[v["id"]] = None
    order = [v["id"] for v in versions]
    parent_of, edges = {}, {}
    for i, v in enumerate(versions):
        vid = v["id"]
        p = v["parent"] if "parent" in v else (order[i - 1] if i > 0 else None)
        parent_of[vid] = p
        if p and (p in emb or not enabled):
            cfg = config_diff(records[p]["config"], records[vid]["config"])
            if enabled:
                drift = semantic_drift(emb[p], emb[vid])
                thresholds = records[vid]["config"]["evaluation"]["thresholds"]
                label = compute_verdict(drift, stab[p], stab[vid], thresholds)
                ds = stab[vid] - stab[p]
            else:
                drift = label = ds = None
            edges[vid] = {"drift": drift, "ds": ds, "cfg": cfg, "verdict": label}
    return {"versions": versions, "stab": stab, "parent_of": parent_of, "edges": edges}


def ensure_eval(store: Store, name: str, vid: str, root, rerun: bool = False):
    """Return a version's eval result, running and saving it if absent (lazy)."""
    rec = store.get_record(name, vid)
    refs = rec.get("config", {}).get("evaluation", {}).get("metrics", [])
    if not refs:
        return None
    if not rerun and isinstance(rec.get("eval"), dict) and rec["eval"].get("metrics"):
        return rec["eval"]
    result = evaluate_version(rec, root)
    store.save_eval(name, vid, result)
    return result


# --------------------------------------------------------------------------- #
# structured operations (front-end facing)
# --------------------------------------------------------------------------- #
def _diff_json(diff: dict) -> dict:
    """Turn ``{key: (old, new)}`` into ``{key: {"from": old, "to": new}}`` for JSON."""
    return {k: {"from": a, "to": b} for k, (a, b) in diff.items()}


def _thresholds_json(thresholds: dict) -> dict:
    return {
        "warn": thresholds.get("drift_warn", 0.15),
        "fail": thresholds.get("drift_fail", 0.40),
    }


# --------------------------------------------------------------------------- #
# regression gate - a pure decision the CLI turns into a process exit code so a
# sweep or CI job fails fast on a regression. dow supplies the built-in text
# verdict; the project supplies any metric threshold. No new numbers are computed.
# --------------------------------------------------------------------------- #
_REGRESSION_VERDICTS = {"Likely Regression"}
_DRIFT_VERDICTS = {"Likely Regression", "Behavior Drift"}


def verdict_gate(verdict: Optional[str], level: str = "regression") -> dict:
    """Decide whether a built-in text-drift verdict trips the regression gate.

    ``level`` is ``regression`` (only a "Likely Regression" trips) or ``drift``
    (either "Likely Regression" or "Behavior Drift" trips). A null verdict - a
    spec with ``embedding_model: none`` - never trips: there is no built-in text
    signal, so gate on a project metric with :func:`threshold_gate` instead.
    """
    level = (level or "regression").strip().lower()
    trip = _DRIFT_VERDICTS if level == "drift" else _REGRESSION_VERDICTS
    breached = verdict in trip
    reason = f"built-in verdict is '{verdict}'" if breached else None
    if verdict is None:
        reason = "built-in text drift is off (embedding_model: none); gate on a project metric instead"
    return {"mode": f"verdict:{level}", "verdict": verdict, "breached": breached, "reason": reason}


def threshold_gate(value, minimum=None, maximum=None, metric: Optional[str] = None) -> dict:
    """Decide whether a metric ``value`` breaches a min/max threshold.

    Fails **closed**: if a threshold is set but the value is missing or non-numeric,
    that is a breach - a CI gate must not silently pass when the metric it guards
    has vanished. With neither bound set the gate never trips.
    """
    gate = {"mode": "threshold", "metric": metric, "value": value,
            "min": minimum, "max": maximum, "breached": False, "reason": None}
    if minimum is None and maximum is None:
        return gate
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        gate["breached"] = True
        gate["reason"] = f"metric '{metric}' is missing or non-numeric"
        return gate
    if minimum is not None and value < minimum:
        gate["breached"] = True
        gate["reason"] = f"{metric or 'value'}={value:g} is below the minimum {float(minimum):g}"
    elif maximum is not None and value > maximum:
        gate["breached"] = True
        gate["reason"] = f"{metric or 'value'}={value:g} is above the maximum {float(maximum):g}"
    return gate


def commit(root, name: Optional[str] = None, message: Optional[str] = None, from_version: Optional[str] = None) -> dict:
    """Run the spec and capture its behavior as a new version."""
    root = Path(root)
    name = need_spec(root, name)
    path = spec_path(root, name)
    if not path.exists():
        raise DowError(f"Spec not found: {SPECS_DIR}/{name}.yaml")
    store = Store(root)
    store.ensure()
    prior = store.list_versions(name)
    parent = resolve(store, name, from_version) if from_version else None
    record = execute(InferenceSpec.load(path), base_dir=root)
    note = ""
    if prior and prior[-1]["fingerprint"] == record["spec_fingerprint"]:
        note = f"same configuration as {prior[-1]['id']} - re-running measures non-determinism"
    vid = store.add_version(name, record, message or "", parent=parent)
    runtime = record["runtime"]
    result = {
        "spec": name,
        "version": vid,
        "parent": parent,
        "stability": record["metrics"].get("stability"),
        "provider": runtime.get("provider"),
        "model": f"{runtime.get('provider')}/{runtime.get('model_version')}",
        "samples": len(record["samples"]),
        "fingerprint": record["spec_fingerprint"],
        "note": note,
        "outputs": [s["output"] for s in record["samples"]],
    }
    refs = record["config"].get("evaluation", {}).get("metrics", [])
    if refs:  # evaluators run automatically at capture time, but never block the commit
        try:
            ev = ensure_eval(store, name, vid, root)
            result["eval"] = (ev or {}).get("metrics", {})
        except Exception as exc:  # noqa: BLE001 - an evaluator bug must not lose the version
            result["evalError"] = str(exc)
    return result


def compare(root, name: Optional[str] = None, a: Optional[str] = None, b: Optional[str] = None,
            plot: bool = False, fail_on: Optional[str] = None) -> dict:
    """Compare two versions: config diff, output difference, drift, stability, verdict.

    When ``fail_on`` is ``regression`` or ``drift``, the result gains a ``gate``
    decision (:func:`verdict_gate`) a caller can turn into a non-zero exit code.
    """
    root = Path(root)
    name = need_spec(root, name)
    store = Store(root)
    a_id, b_id = resolve_pair(store, name, a, b)
    r = compare_records(store, name, a_id, b_id)
    out = {
        "spec": name,
        "a": a_id,
        "b": b_id,
        "configDiff": _diff_json(r["config_diff"]),
        "outputDifference": _round(r["output_difference"]),
        "semanticDrift": _round(r["semantic_drift"]),
        "stabilityA": _round(r["stability_a"]),
        "stabilityB": _round(r["stability_b"]),
        "driftEnabled": r.get("drift_enabled", True),
        "embeddingModel": r.get("embedding_model"),
        "thresholds": _thresholds_json(r["thresholds"]),
        "verdict": r["verdict"],
        "comparators": r.get("comparators", {}),
        "comparatorRefs": r.get("comparator_refs", []),
        "comparatorError": r.get("comparator_error"),
    }
    if fail_on:
        out["gate"] = verdict_gate(r["verdict"], fail_on)
    if plot:
        a_rec, b_rec = store.get_record(name, a_id), store.get_record(name, b_id)
        plot_refs = b_rec.get("config", {}).get("evaluation", {}).get("plots", []) or []
        figs = run_plots(store, plot_refs, r, [a_rec, b_rec], [a_id, b_id], root, "compare", name)
        out["figures"] = figs["figures"]
        out["plotRefs"] = figs["plotRefs"]
        out["plotError"] = figs["plotError"]
    return out


def explain(root, name: Optional[str] = None, a: Optional[str] = None, b: Optional[str] = None) -> dict:
    """Attribute a behavioral change to the configuration difference (causal view)."""
    root = Path(root)
    name = need_spec(root, name)
    store = Store(root)
    a_id, b_id = resolve_pair(store, name, a, b)
    r = compare_records(store, name, a_id, b_id)
    cfg = r["config_diff"]
    confounded = len(cfg) > 1
    cause = None
    if cfg and not confounded:
        key = next(iter(cfg))
        old, new = cfg[key]
        cause = {"field": key, "from": old, "to": new}
    if not cfg:
        note = "Nothing in the configuration changed; any difference is sampling noise (see stability)."
    elif confounded:
        note = "More than one field changed, so the effect cannot be pinned on a single cause. Change one field at a time for a clean answer."
    else:
        note = None
    return {
        "spec": name,
        "a": a_id,
        "b": b_id,
        "changed": _diff_json(cfg),
        "confounded": confounded,
        "cause": cause,
        "semanticDrift": _round(r["semantic_drift"]),
        "stabilityChange": _round(r.get("stability_change")),
        "driftEnabled": r.get("drift_enabled", True),
        "verdict": r["verdict"],
        "note": note,
        "comparators": r.get("comparators", {}),
        "comparatorRefs": r.get("comparator_refs", []),
        "comparatorError": r.get("comparator_error"),
    }


def history(root, name: Optional[str] = None) -> dict:
    """List captured versions with stability, tags, change vs. parent, and eval scores."""
    root = Path(root)
    name = need_spec(root, name)
    store = Store(root)
    versions = store.list_versions(name)
    path = spec_path(root, name)
    work_fp = InferenceSpec.load(path).fingerprint() if path.exists() else None
    out, prev_fp = [], None
    for v in versions:
        if prev_fp is None:
            change = "baseline"
        elif v["fingerprint"] == prev_fp:
            change = "same-config"
        else:
            change = "config-changed"
        out.append(
            {
                "id": v["id"],
                "parent": v.get("parent"),
                "created": v.get("created"),
                "stability": v["stability"],
                "fingerprint": v.get("fingerprint"),
                "tags": list(v.get("tags", []) or []),
                "message": v.get("message") or "",
                "change": change,
                "eval": v.get("eval", {}) or {},
            }
        )
        prev_fp = v["fingerprint"]
    dirty = bool(work_fp is not None and versions and work_fp != versions[-1]["fingerprint"])
    return {
        "spec": name,
        "versions": out,
        "workingFingerprint": work_fp,
        "workingDirty": dirty,
    }


def _numeric_metrics(entry: dict) -> dict:
    """The trackable numeric metrics of one version: the built-in ``stability``
    plus the project's own evaluator scores. Non-numeric values are dropped."""
    vals: dict = {}
    stab = entry.get("stability")
    if isinstance(stab, (int, float)) and not isinstance(stab, bool):
        vals["stability"] = float(stab)
    ev = entry.get("eval")
    if isinstance(ev, dict):
        source = ev.get("metrics") if isinstance(ev.get("metrics"), dict) else ev
        for k, v in source.items():
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                vals[k] = float(v)
    return vals


def trend(root, name: Optional[str] = None, metric: Optional[str] = None,
          plot: bool = False) -> dict:
    """Longitudinal view of a metric across a spec's whole version history.

    Where ``compare`` contrasts exactly two versions, ``trend`` follows one (or
    every) numeric metric across all N versions in commit order - the built-in
    ``stability`` and the project's own evaluator scores - reporting each value
    with its change vs. the previous version and vs. the baseline (v1). It is a
    read-only report; dow computes no new numbers. With ``plot=True`` the spec's
    ``evaluation.plots`` functions render the series (``kind="trend"``).
    """
    root = Path(root)
    name = need_spec(root, name)
    store = Store(root)
    versions = store.list_versions(name)
    if not versions:
        raise DowError("No versions yet. Run 'dow commit' first.")

    rows, prev_fp, metric_keys = [], None, set()
    for v in versions:
        vals = _numeric_metrics(v)
        metric_keys.update(vals)
        if prev_fp is None:
            change = "baseline"
        elif v["fingerprint"] == prev_fp:
            change = "same-config"
        else:
            change = "config-changed"
        rows.append({"id": v["id"], "change": change,
                     "tags": list(v.get("tags", []) or []), "values": vals})
        prev_fp = v["fingerprint"]

    if metric:
        keys = [metric]
    else:  # stability first (if present), then the project metrics alphabetically
        keys = ([k for k in ("stability",) if k in metric_keys]
                + sorted(k for k in metric_keys if k != "stability"))

    series: dict = {}
    for k in keys:
        seq, baseline, last = [], None, None
        for row in rows:
            val = row["values"].get(k)
            d_prev = (val - last) if (val is not None and last is not None) else None
            d_base = (val - baseline) if (val is not None and baseline is not None) else None
            seq.append({"id": row["id"], "change": row["change"], "value": val,
                        "deltaPrev": _round(d_prev), "deltaBaseline": _round(d_base)})
            if val is not None:
                baseline = val if baseline is None else baseline
                last = val
        series[k] = seq

    result = {
        "spec": name,
        "metrics": keys,
        "count": len(versions),
        "rows": rows,
        "series": series,
    }
    if plot:
        records = [store.get_record(name, v["id"]) for v in versions]
        plot_refs = _cohort_analysis_refs(records, "plots")
        figs = run_plots(store, plot_refs, result, records,
                         [v["id"] for v in versions], root, "trend", name)
        result["figures"] = figs["figures"]
        result["plotRefs"] = figs["plotRefs"]
        result["plotError"] = figs["plotError"]
    return result


def inspect(root, name: Optional[str] = None, version: Optional[str] = None) -> dict:
    """One version's spec config, runtime capture, outputs, tags, and eval scores."""
    root = Path(root)
    name = need_spec(root, name)
    store = Store(root)
    vid = resolve(store, name, version or "last")
    rec = store.get_record(name, vid)
    tags = list(store.meta(name, vid).get("tags", []) or [])
    ev = rec.get("eval")
    return {
        "spec": name,
        "version": vid,
        "tags": tags,
        "input": rec.get("input", ""),
        "config": rec.get("config", {}),
        "runtime": rec.get("runtime", {}),
        "stability": rec["metrics"].get("stability"),
        "outputs": [
            {
                "index": i,
                "output": s.get("output", ""),
                "tokens": s.get("tokens"),
                "latencyMs": s.get("latency_ms"),
            }
            for i, s in enumerate(rec.get("samples", []))
        ],
        "eval": ev.get("metrics") if isinstance(ev, dict) else None,
    }


def tag(root, name: Optional[str] = None, label: Optional[str] = None, version: Optional[str] = None) -> dict:
    """Attach a free-form label (good, golden, baseline, ...) to a version."""
    if not label or not str(label).strip():
        raise DowError("A tag label is required (e.g. good, golden, baseline).")
    root = Path(root)
    name = need_spec(root, name)
    store = Store(root)
    vid = resolve(store, name, version or "last")
    store.add_tag(name, vid, label)
    return {
        "spec": name,
        "version": vid,
        "label": label,
        "tags": list(store.meta(name, vid).get("tags", []) or []),
    }


def _eval_payload(name, vid, target, prev_id, prev, good_tag, good_id, good, refs, draft=False) -> dict:
    tmetrics = (target or {}).get("metrics", {})
    pmetrics = (prev or {}).get("metrics", {})
    gmetrics = (good or {}).get("metrics", {})
    metrics = {}
    for m in sorted(tmetrics):
        metrics[m] = {
            "value": tmetrics[m],
            "vsPrevious": round(tmetrics[m] - pmetrics[m], 4) if m in pmetrics else None,
            "vsGood": round(tmetrics[m] - gmetrics[m], 4) if m in gmetrics else None,
        }
    return {
        "spec": name,
        "version": vid,
        "draft": draft,
        "evaluators": list(refs),
        "metrics": metrics,
        "previous": {"id": prev_id, "metrics": pmetrics} if prev_id else None,
        "good": {"tag": good_tag, "id": good_id, "metrics": gmetrics} if good_id else None,
    }


def evaluate(
    root,
    name: Optional[str] = None,
    version: Optional[str] = None,
    rerun: bool = False,
    good_tag: str = "good",
    draft: bool = False,
) -> dict:
    """Run custom evaluators for a version (or the working spec), vs previous and last-good."""
    root = Path(root)
    name = need_spec(root, name)
    store = Store(root)

    if draft:
        path = spec_path(root, name)
        if not path.exists():
            raise DowError(f"Spec not found: {SPECS_DIR}/{name}.yaml")
        record = execute(InferenceSpec.load(path), base_dir=root)
        refs = record["config"]["evaluation"].get("metrics", [])
        if not refs:
            return {
                "spec": name,
                "version": "draft",
                "draft": True,
                "metrics": {},
                "evaluators": [],
                "note": "No evaluators configured. Add 'metrics' under 'evaluation' in the spec.",
            }
        result = evaluate_version(record, root)
        existing = store.list_versions(name)
        prev_id = existing[-1]["id"] if existing else None
        good_id = store.latest_with_tag(name, good_tag)
        prev = ensure_eval(store, name, prev_id, root) if prev_id else None
        good = ensure_eval(store, name, good_id, root) if good_id else None
        return _eval_payload(name, "draft", result, prev_id, prev, good_tag, good_id, good, refs, draft=True)

    versions = store.list_versions(name)
    if not versions:
        raise DowError(
            "No versions yet. Run commit first, or use draft=true to preview the working spec."
        )
    ids = [v["id"] for v in versions]
    vid = resolve(store, name, version or "last")
    refs = store.get_record(name, vid)["config"]["evaluation"].get("metrics", [])
    if not refs:
        return {
            "spec": name,
            "version": vid,
            "draft": False,
            "metrics": {},
            "evaluators": [],
            "note": "No evaluators configured. Add 'metrics' under 'evaluation' in the spec.",
        }
    target = ensure_eval(store, name, vid, root, rerun=rerun)
    idx = ids.index(vid)
    prev_id = ids[idx - 1] if idx > 0 else None
    good_id = store.latest_with_tag(name, good_tag)
    prev = ensure_eval(store, name, prev_id, root) if prev_id else None
    good = ensure_eval(store, name, good_id, root) if good_id else None
    return _eval_payload(name, vid, target, prev_id, prev, good_tag, good_id, good, refs)


def tree(root, name: Optional[str] = None, mermaid: bool = False) -> dict:
    """Version evolution as structured nodes, optionally with a Mermaid gitGraph."""
    root = Path(root)
    name = need_spec(root, name)
    store = Store(root)
    data = build_tree_data(store, name)
    versions = data["versions"]
    stab, parent_of, edges = data["stab"], data["parent_of"], data["edges"]
    by_id = {v["id"]: v for v in versions}
    nodes = []
    for v in versions:
        vid = v["id"]
        edge = edges.get(vid)
        node = {
            "id": vid,
            "parent": parent_of.get(vid),
            "stability": _round(stab.get(vid)),
            "tags": list(by_id[vid].get("tags", []) or []),
            "baseline": edge is None,
        }
        if edge:
            node["edge"] = {
                "semanticDrift": _round(edge["drift"]),
                "stabilityChange": _round(edge["ds"]),
                "changed": _diff_json(edge["cfg"]),
                "verdict": edge["verdict"],
            }
        nodes.append(node)
    result = {"spec": name, "nodes": nodes}
    if mermaid:
        from . import report  # lazy: keeps this module free of the rendering layer

        result["mermaid"] = report.build_mermaid(name, versions, stab, parent_of, edges)
    return result


def docs(command: Optional[str] = None) -> dict:
    """Return dow's documentation: the overview, or one command's help text."""
    if command:
        safe = re.fullmatch(r"[a-z][a-z0-9_-]*", command)
        path = DOCS_DIR / f"{command}.txt"
        if not safe or not path.exists() or path.resolve().parent != DOCS_DIR.resolve():
            raise DowError(f"No documentation for '{command}'. Try one of: {', '.join(_doc_commands())}.")
        return {"command": command, "text": path.read_text(encoding="utf-8")}
    overview = DOCS_DIR / "README.md"
    return {
        "commands": _doc_commands(),
        "text": overview.read_text(encoding="utf-8") if overview.exists() else "",
    }


def _doc_commands() -> list:
    return sorted(p.stem for p in DOCS_DIR.glob("*.txt"))
