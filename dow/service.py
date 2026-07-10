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

from pathlib import Path
from typing import Optional

from .embeddings import get_embedder
from .evaluators import evaluate_version
from .metrics import output_difference, semantic_drift, stability
from .metrics import verdict as compute_verdict
from .runner import execute
from .spec import InferenceSpec, flatten
from .store import Store

SPECS_DIR = "specs"
DOCS_DIR = Path(__file__).parent / "docs"
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
    return sorted(d.glob("*.yaml")) if d.is_dir() else []


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


def config_diff(a_cfg: dict, b_cfg: dict) -> dict:
    """Flattened field-by-field difference: ``{dotted_key: (old, new)}``."""
    fa, fb = flatten(a_cfg), flatten(b_cfg)
    diff = {}
    for k in sorted(set(fa) | set(fb)):
        if fa.get(k) != fb.get(k):
            diff[k] = (fa.get(k), fb.get(k))
    return diff


def compare_records(store: Store, name: str, a_id: str, b_id: str) -> dict:
    """Full-precision comparison of two captured versions (the ``dow compare`` core)."""
    a = store.get_record(name, a_id)
    b = store.get_record(name, b_id)
    a_out = [s["output"] for s in a["samples"]]
    b_out = [s["output"] for s in b["samples"]]
    embedder = get_embedder(b["config"]["evaluation"]["embedding_model"])
    a_emb, b_emb = embedder.embed(a_out), embedder.embed(b_out)
    drift = semantic_drift(a_emb, b_emb)
    stab_a, stab_b = stability(a_emb), stability(b_emb)
    outdiff = output_difference(a_out, b_out)
    cfg_diff = config_diff(a["config"], b["config"])
    thresholds = b["config"]["evaluation"]["thresholds"]
    label = compute_verdict(drift, stab_a, stab_b, thresholds)
    return {
        "config_diff": cfg_diff,
        "output_difference": outdiff,
        "semantic_drift": drift,
        "stability_a": stab_a,
        "stability_b": stab_b,
        "verdict": label,
        "thresholds": thresholds,
    }


def build_tree_data(store: Store, name: str) -> dict:
    """Per-version stability and parent->child drift/verdict edges (the ``dow tree`` core)."""
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
            cfg = config_diff(records[p]["config"], records[vid]["config"])
            thresholds = records[vid]["config"]["evaluation"]["thresholds"]
            label = compute_verdict(drift, stab[p], stab[vid], thresholds)
            edges[vid] = {"drift": drift, "ds": stab[vid] - stab[p], "cfg": cfg, "verdict": label}
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
    record = execute(InferenceSpec.load(path))
    note = ""
    if prior and prior[-1]["fingerprint"] == record["spec_fingerprint"]:
        note = f"same configuration as {prior[-1]['id']} - re-running measures non-determinism"
    vid = store.add_version(name, record, message or "", parent=parent)
    runtime = record["runtime"]
    result = {
        "spec": name,
        "version": vid,
        "parent": parent,
        "stability": record["metrics"]["stability"],
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


def compare(root, name: Optional[str] = None, a: Optional[str] = None, b: Optional[str] = None) -> dict:
    """Compare two versions: config diff, output difference, drift, stability, verdict."""
    root = Path(root)
    name = need_spec(root, name)
    store = Store(root)
    a_id, b_id = resolve_pair(store, name, a, b)
    r = compare_records(store, name, a_id, b_id)
    return {
        "spec": name,
        "a": a_id,
        "b": b_id,
        "configDiff": _diff_json(r["config_diff"]),
        "outputDifference": round(r["output_difference"], 4),
        "semanticDrift": round(r["semantic_drift"], 4),
        "stabilityA": round(r["stability_a"], 4),
        "stabilityB": round(r["stability_b"], 4),
        "thresholds": _thresholds_json(r["thresholds"]),
        "verdict": r["verdict"],
    }


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
        "semanticDrift": round(r["semantic_drift"], 4),
        "stabilityChange": round(r["stability_b"] - r["stability_a"], 4),
        "verdict": r["verdict"],
        "note": note,
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
        "stability": rec["metrics"]["stability"],
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
        record = execute(InferenceSpec.load(path))
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
            "stability": round(stab.get(vid, 0.0), 4),
            "tags": list(by_id[vid].get("tags", []) or []),
            "baseline": edge is None,
        }
        if edge:
            node["edge"] = {
                "semanticDrift": round(edge["drift"], 4),
                "stabilityChange": round(edge["ds"], 4),
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
        path = DOCS_DIR / f"{command}.txt"
        if not path.exists():
            raise DowError(f"No documentation for '{command}'. Try one of: {', '.join(_doc_commands())}.")
        return {"command": command, "text": path.read_text(encoding="utf-8")}
    overview = DOCS_DIR / "README.md"
    return {
        "commands": _doc_commands(),
        "text": overview.read_text(encoding="utf-8") if overview.exists() else "",
    }


def _doc_commands() -> list:
    return sorted(p.stem for p in DOCS_DIR.glob("*.txt"))
