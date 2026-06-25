"""Serve the web dashboard backed by the live behavior store.

This module turns the captured versions in ``.dow`` into the JSON shape the
React dashboard (``dashboard/``) consumes, and serves both the bundled static
assets (``dow/web``) and that live data over a tiny localhost HTTP server.

The dashboard reflects whatever ``dow commit``/``dow eval`` have captured, and it
can also edit the working spec and capture versions (including the first one
right after ``dow init``) via a small localhost-only write API (``/api/spec`` and
``/api/commit``) that only accepts requests originating from the local machine.
Drift, stability, and verdicts for parent->child edges are computed with the same
engine the CLI uses (``dow.metrics``), so the UI matches ``dow compare`` instead
of re-deriving its own numbers.
"""
from __future__ import annotations

import functools
import json
import os
import subprocess
import sys
import webbrowser
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlparse

from .embeddings import get_embedder
from .evaluators import evaluate_version
from .metrics import output_difference, semantic_drift, stability
from .metrics import verdict as compute_verdict
from .spec import InferenceSpec, flatten
from .store import Store

# Built dashboard assets are bundled here by `npm run build` (Vite outDir).
WEB_DIR = Path(__file__).parent / "web"
SPECS_DIRNAME = "specs"

_VERDICT_LEVEL = {
    "Consistent": "pass",
    "Behavior Drift": "warn",
    "Likely Regression": "fail",
}


# --------------------------------------------------------------------------- #
# spec resolution
# --------------------------------------------------------------------------- #
def _index(store: Store) -> dict:
    if not store.index_path.exists():
        return {"specs": {}}
    return json.loads(store.index_path.read_text(encoding="utf-8"))


def store_specs(root) -> list:
    """Names of specs that have at least one captured version in the store."""
    store = Store(Path(root))
    if not store.is_initialized():
        return []
    specs = _index(store).get("specs", {})
    return [name for name, entry in specs.items() if entry.get("versions")]


def resolve_spec(root, spec: Optional[str] = None) -> Optional[str]:
    """Pick which spec the dashboard should show.

    Considers both committed specs and working spec files, so a project that has
    only run ``dow init`` (no versions captured yet) still resolves. Returns the
    explicit ``spec`` when it exists, otherwise the first available spec, or
    ``None`` when there is no spec at all.
    """
    names = dashboard_specs(root)
    if spec:
        stem = Path(spec).stem
        return stem if stem in names else None
    return names[0] if names else None


def _working_spec_files(root) -> list:
    d = Path(root) / SPECS_DIRNAME
    return sorted(d.glob("*.yaml")) if d.is_dir() else []


def spec_path(root, name: str) -> Path:
    """Filesystem path of a working spec by name."""
    return Path(root) / SPECS_DIRNAME / f"{name}.yaml"


def dashboard_specs(root) -> list:
    """Specs the dashboard can show: committed ones first, then any working spec
    files that have no captured versions yet (so a freshly ``dow init``-ed
    project still appears in the switcher)."""
    names = list(store_specs(root))
    seen = set(names)
    for f in _working_spec_files(root):
        if f.stem not in seen:
            seen.add(f.stem)
            names.append(f.stem)
    return names


def read_spec_text(root, name: Optional[str]) -> Optional[str]:
    """Raw YAML of a working spec file, or None if it does not exist."""
    if not name:
        return None
    try:
        return spec_path(root, name).read_text(encoding="utf-8")
    except OSError:
        return None


# --------------------------------------------------------------------------- #
# helpers: snake_case record -> camelCase dashboard shapes
# --------------------------------------------------------------------------- #
def _camel(token: str) -> str:
    head, *rest = token.split("_")
    return head + "".join(part[:1].upper() + part[1:] for part in rest)


def _camel_path(dotted: str) -> str:
    return ".".join(_camel(part) for part in dotted.split("."))


def _map_config(cfg: dict) -> dict:
    """Map a stored (snake_case) spec config to the dashboard SpecConfig shape."""
    prompt = cfg.get("prompt", {}) or {}
    model = cfg.get("model", {}) or {}
    sampling = cfg.get("sampling", {}) or {}
    evaluation = cfg.get("evaluation", {}) or {}
    thresholds = evaluation.get("thresholds", {}) or {}
    inputs = cfg.get("inputs") or []
    return {
        "specVersion": cfg.get("spec_version", 1),
        "name": cfg.get("name", ""),
        "task": cfg.get("task", ""),
        "prompt": {
            "system": prompt.get("system", "") or "",
            "template": prompt.get("template", "") or "",
            "fewShot": list(prompt.get("few_shot", []) or []),
        },
        "model": {
            "provider": model.get("provider", "") or "",
            "name": model.get("name", "") or "",
            "version": model.get("version", "") or "",
            "revision": model.get("revision", None),
        },
        "sampling": {
            "temperature": sampling.get("temperature", 0),
            "topP": sampling.get("top_p", 1.0),
            "maxTokens": sampling.get("max_tokens", 0),
            "frequencyPenalty": sampling.get("frequency_penalty", 0),
            "presencePenalty": sampling.get("presence_penalty", 0),
            "seed": sampling.get("seed", 0),
        },
        "evaluation": {
            "embeddingModel": evaluation.get("embedding_model", "") or "",
            "samples": evaluation.get("samples", 0),
            "metrics": list(evaluation.get("metrics", []) or []),
            "thresholds": {
                "warn": thresholds.get("drift_warn", 0.15),
                "fail": thresholds.get("drift_fail", 0.40),
            },
        },
        "input": (inputs[0] if inputs else cfg.get("input", "")) or "",
    }


def _eval_metrics(record: dict, root: Path) -> dict:
    """Custom evaluator scores for a version (persisted, else computed best-effort)."""
    ev = record.get("eval")
    if isinstance(ev, dict) and isinstance(ev.get("metrics"), dict):
        return {str(k): float(v) for k, v in ev["metrics"].items()}
    refs = record.get("config", {}).get("evaluation", {}).get("metrics", [])
    if refs:
        try:  # evaluators are the user's own code; never let one break the dashboard
            result = evaluate_version(record, root)
            return {str(k): float(v) for k, v in result.get("metrics", {}).items()}
        except Exception:
            return {}
    return {}


def _derived_metrics(record: dict, stab_value: float) -> dict:
    """Always-available numeric signals derived from a version's captured samples."""
    samples = record.get("samples", []) or []
    tokens = [s.get("tokens") for s in samples if isinstance(s.get("tokens"), (int, float))]
    latencies = [s.get("latency_ms") for s in samples if isinstance(s.get("latency_ms"), (int, float))]
    metrics = {"stability": round(float(stab_value), 4)}
    if tokens:
        metrics["tokens"] = round(sum(tokens) / len(tokens), 2)
    if latencies:
        metrics["latencyMs"] = round(sum(latencies) / len(latencies), 2)
    return metrics


def _changed_fields(parent_cfg: Optional[dict], cfg: dict) -> list:
    if not parent_cfg:
        return []
    before, after = flatten(parent_cfg), flatten(cfg)
    return [k for k in sorted(set(before) | set(after)) if before.get(k) != after.get(k)]


def _summary(message: str, parent: Optional[str], fields: list) -> str:
    if message.strip():
        return message.strip()
    if not parent:
        return "Initial version"
    if not fields:
        return "Re-run with unchanged configuration"
    if len(fields) == 1:
        return f"Changed {fields[0]}"
    shown = ", ".join(fields[:3])
    more = f" (+{len(fields) - 3} more)" if len(fields) > 3 else ""
    return f"Changed {shown}{more}"


def _descriptor(key: str, label: str, fmt: str, better: str, values: list, weight: float, desc: str) -> dict:
    nums = [float(v) for v in values if isinstance(v, (int, float))]
    lo, hi = (min(nums), max(nums)) if nums else (0.0, 1.0)
    span = hi - lo
    if fmt == "percent":
        target = 1.0 if better == "higher" else 0.0
        norm = max(0.1, span if span > 0 else 0.4)
    elif fmt in ("ms", "int"):
        target = lo if better == "lower" else hi
        norm = max(1.0, span * 2 if span > 0 else (abs(hi) or 1.0))
    else:  # decimal
        target = hi if better == "higher" else lo
        norm = max(1e-6, span if span > 0 else (abs(hi) or 1.0))
    return {
        "key": key,
        "label": label,
        "short": label[:4],
        "format": fmt,
        "betterWhen": better,
        "target": round(target, 4),
        "driftWeight": weight,
        "normSpan": round(norm, 4),
        "description": desc,
    }


# --------------------------------------------------------------------------- #
# payload
# --------------------------------------------------------------------------- #
def build_payload(root, spec: Optional[str] = None, editable: bool = False) -> dict:
    """Build the full dashboard dataset from the live store for one spec."""
    root = Path(root)
    name = resolve_spec(root, spec)
    base = {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "live": True,
        "editable": editable,
        "specName": name,
        "specPath": f"{SPECS_DIRNAME}/{name}.yaml" if name else None,
        "specText": read_spec_text(root, name),
        "specs": dashboard_specs(root),
        "versions": [],
        "metricDescriptors": [],
        "headlineMetrics": [],
        "comparisons": {},
        "typicalDrift": 0.0,
        "headId": None,
        "defaultSelectedId": None,
        "defaultCompareFromId": None,
        "defaultCompareToId": None,
    }
    if not name:
        return base

    store = Store(root)
    if not store.is_initialized():
        return base
    metas = store.list_versions(name)
    if not metas:
        return base
    records = {m["id"]: store.get_record(name, m["id"]) for m in metas}
    ids = [m["id"] for m in metas]
    last = ids[-1]

    embedder = get_embedder(records[last]["config"]["evaluation"]["embedding_model"])
    embeddings, stab = {}, {}
    for m in metas:
        outs = [s["output"] for s in records[m["id"]]["samples"]]
        e = embedder.embed(outs)
        embeddings[m["id"]] = e
        stab[m["id"]] = stability(e)

    # custom evaluator metrics (union of keys across versions)
    evals = {m["id"]: _eval_metrics(records[m["id"]], root) for m in metas}
    custom_keys: list = []
    for scores in evals.values():
        for k in scores:
            if k not in custom_keys:
                custom_keys.append(k)

    metrics_by_v = {}
    for m in metas:
        vid = m["id"]
        recorded_stab = records[vid].get("metrics", {}).get("stability", stab[vid])
        values = _derived_metrics(records[vid], recorded_stab)
        for k in custom_keys:
            if k in evals[vid]:  # only versions that actually measured it
                values[k] = round(float(evals[vid][k]), 4)
        metrics_by_v[vid] = values

    # metric descriptors (dynamic — reflect what this project actually tracks)
    descriptors = [
        _descriptor(
            "stability", "Stability", "percent", "higher",
            [metrics_by_v[v]["stability"] for v in ids], 1.0,
            "Mean pairwise self-similarity across the samples of this version.",
        )
    ]
    if any("latencyMs" in metrics_by_v[v] for v in ids):
        descriptors.append(
            _descriptor(
                "latencyMs", "Latency", "ms", "lower",
                [metrics_by_v[v].get("latencyMs", 0) for v in ids], 0.3,
                "Mean end-to-end response time per sample.",
            )
        )
    if any("tokens" in metrics_by_v[v] for v in ids):
        descriptors.append(
            _descriptor(
                "tokens", "Tokens", "int", "lower",
                [metrics_by_v[v].get("tokens", 0) for v in ids], 0.2,
                "Mean completion tokens emitted per sample.",
            )
        )
    for key in custom_keys:
        series = [metrics_by_v[v][key] for v in ids if key in metrics_by_v[v]]
        is_ratio = bool(series) and all(0.0 <= x <= 1.0 for x in series)
        descriptors.append(
            _descriptor(
                key, key.replace("_", " ").title(), "percent" if is_ratio else "decimal",
                "higher", series, 0.6,
                f"Custom evaluator (evaluation.metrics → {key}).",
            )
        )

    headline = ["stability"] + [k for k in custom_keys][:2]
    for extra in ("latencyMs", "tokens"):
        if len(headline) >= 4:
            break
        if any(extra in metrics_by_v[v] for v in ids):
            headline.append(extra)

    # parent->child comparisons via the real engine (matches `dow compare`)
    comparisons = {}
    edge_drifts = []
    for m in metas:
        vid, parent = m["id"], m.get("parent")
        if parent and parent in embeddings:
            drift = semantic_drift(embeddings[parent], embeddings[vid])
            out_a = [s["output"] for s in records[parent]["samples"]]
            out_b = [s["output"] for s in records[vid]["samples"]]
            outdiff = output_difference(out_a, out_b)
            thresholds = records[vid]["config"]["evaluation"]["thresholds"]
            label = compute_verdict(drift, stab[parent], stab[vid], thresholds)
            comparisons[f"{parent}>{vid}"] = {
                "outputDifference": round(outdiff, 4),
                "semanticDrift": round(drift, 4),
                "stabilityFrom": round(stab[parent], 4),
                "stabilityTo": round(stab[vid], 4),
                "verdict": _VERDICT_LEVEL.get(label, "pass"),
                "verdictLabel": label,
            }
            edge_drifts.append(drift)
    typical = round(sum(edge_drifts) / len(edge_drifts), 4) if edge_drifts else 0.0

    versions = []
    for m in metas:
        vid, parent = m["id"], m.get("parent")
        record = records[vid]
        parent_cfg = records[parent]["config"] if parent and parent in records else None
        fields = _changed_fields(parent_cfg, record["config"])
        tags = list(m.get("tags", []) or [])
        outputs = [
            {
                "id": f"s{i + 1}",
                "output": s.get("output", ""),
                "tokens": s.get("tokens", 0),
                "latencyMs": s.get("latency_ms", 0),
            }
            for i, s in enumerate(record.get("samples", []) or [])
        ]
        versions.append(
            {
                "id": vid,
                "label": f"{vid} · {tags[0]}" if tags else vid,
                "parentId": parent,
                "createdAt": record.get("run_id") or m.get("created"),
                "author": "you",
                "summary": _summary(m.get("message", "") or "", parent, fields),
                "changedField": _camel_path(fields[0]) if fields else None,
                "tags": tags,
                "status": "captured",
                "config": _map_config(record["config"]),
                "outputs": outputs,
                "metrics": metrics_by_v[vid],
            }
        )

    default_from = metas[-1].get("parent") or (ids[-2] if len(ids) > 1 else last)
    base.update(
        {
            "versions": versions,
            "metricDescriptors": descriptors,
            "headlineMetrics": headline,
            "comparisons": comparisons,
            "typicalDrift": typical,
            "headId": last,
            "defaultSelectedId": last,
            "defaultCompareFromId": default_from,
            "defaultCompareToId": last,
        }
    )
    return base


def write_payload(root, spec: Optional[str], path) -> dict:
    """Write the live dashboard dataset to ``path`` as JSON and return it."""
    payload = build_payload(root, spec)
    Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


# --------------------------------------------------------------------------- #
# static + data HTTP server
# --------------------------------------------------------------------------- #
class _Handler(SimpleHTTPRequestHandler):
    """Serves the bundled SPA, a freshly-built ``/data.json``, and a small write
    API (``/api/spec`` read/save, ``/api/commit``) so the first version can be
    captured from the UI."""

    payload_provider: Callable[[], dict]

    def __init__(self, *args, payload_provider: Callable[[], dict], root, spec, **kwargs):
        self.payload_provider = payload_provider
        self._root = Path(root)
        self._spec = spec
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    # ---- response helpers ---------------------------------------------- #
    def _json(self, obj: dict, status: int = 200) -> None:
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            return json.loads(raw or b"{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}

    def _current_name(self) -> Optional[str]:
        return resolve_spec(self._root, self._spec)

    def _is_local(self) -> bool:
        # The write API mutates local files; only honor genuinely same-host
        # requests to blunt cross-site / DNS-rebinding POSTs from web pages.
        local = {"127.0.0.1", "localhost", "::1"}
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]")
        if host and host not in local:
            return False
        origin = self.headers.get("Origin")
        if origin and (urlparse(origin).hostname or "") not in local:
            return False
        return True

    # ---- GET ----------------------------------------------------------- #
    def do_GET(self) -> None:  # noqa: N802 (http.server API)
        path = self.path.split("?", 1)[0]
        if path == "/data.json":
            self._send_data()
            return
        if path == "/api/spec":
            self._get_spec()
            return
        # SPA fallback: unknown non-asset paths return index.html
        rel = path.lstrip("/")
        target = (WEB_DIR / rel) if rel else (WEB_DIR / "index.html")
        if rel and not target.is_file():
            self.path = "/index.html"
        super().do_GET()

    def _get_spec(self) -> None:
        name = self._current_name()
        if not name:
            self._json({"error": "No spec found. Run 'dow init' first."}, status=404)
            return
        self._json(
            {
                "name": name,
                "path": f"{SPECS_DIRNAME}/{name}.yaml",
                "text": read_spec_text(self._root, name) or "",
            }
        )

    # ---- POST ---------------------------------------------------------- #
    def do_POST(self) -> None:  # noqa: N802 (http.server API)
        path = self.path.split("?", 1)[0]
        if path not in ("/api/spec", "/api/commit"):
            self._json({"error": "Not found."}, status=404)
            return
        if not self._is_local():
            self._json({"ok": False, "error": "Forbidden."}, status=403)
            return
        if path == "/api/spec":
            self._save_spec()
        else:
            self._commit()

    def _save_spec(self) -> None:
        name = self._current_name()
        if not name:
            self._json({"ok": False, "error": "No spec to save."}, status=400)
            return
        text = self._read_json_body().get("text")
        if not isinstance(text, str):
            self._json({"ok": False, "error": "Missing spec text."}, status=400)
            return
        path = spec_path(self._root, name)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        except OSError as exc:
            self._json({"ok": False, "error": f"Could not write spec: {exc}"}, status=500)
            return
        # Validate so the UI can warn; the edit is saved either way.
        valid, error = True, None
        try:
            InferenceSpec.load(path)
        except Exception as exc:  # noqa: BLE001 - any parse/validation issue is a warning
            valid, error = False, str(exc)
        self._json({"ok": True, "valid": valid, "error": error})

    def _commit(self) -> None:
        name = self._current_name()
        if not name:
            self._json({"ok": False, "error": "No spec to commit. Run 'dow init' first."}, status=400)
            return
        path = spec_path(self._root, name)
        if not path.exists():
            self._json({"ok": False, "error": f"Spec not found: {SPECS_DIRNAME}/{name}.yaml"}, status=400)
            return
        try:
            InferenceSpec.load(path)
        except Exception as exc:  # noqa: BLE001 - surface invalid spec before committing
            self._json({"ok": False, "error": f"Spec is invalid: {exc}"}, status=400)
            return
        message = (self._read_json_body().get("message") or "").strip()
        argv = [sys.executable, "-m", "dow", "commit", name]
        if message:
            argv += ["-m", message]
        try:
            proc = subprocess.run(
                argv,
                cwd=str(self._root),
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                timeout=300,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            self._json({"ok": False, "error": f"Could not run dow commit: {exc}"}, status=500)
            return
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip()
            self._json({"ok": False, "error": detail or "dow commit failed."}, status=500)
            return
        try:
            vid = Store(self._root).list_versions(name)[-1]["id"]
        except Exception:  # noqa: BLE001 - commit succeeded; id is best-effort
            vid = None
        self._json({"ok": True, "versionId": vid})

    def _send_data(self) -> None:
        try:
            body = json.dumps(self.payload_provider()).encode("utf-8")
        except Exception as exc:  # surface a readable error to the UI console
            body = json.dumps({"error": str(exc), "versions": []}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args) -> None:  # keep the terminal clean
        return


def serve(
    root,
    spec: Optional[str] = None,
    host: str = "127.0.0.1",
    port: int = 0,
    open_browser: bool = True,
    on_start: Optional[Callable[[str], None]] = None,
) -> None:
    """Serve the dashboard and live data until interrupted (Ctrl+C)."""
    if not (WEB_DIR / "index.html").exists():
        raise FileNotFoundError(
            "Dashboard assets not found. Build the UI first:\n"
            "  cd dashboard && npm install && npm run build"
        )
    provider = functools.partial(build_payload, root, spec, True)  # editable: served live
    handler = functools.partial(_Handler, payload_provider=provider, root=root, spec=spec)
    httpd = ThreadingHTTPServer((host, port), handler)
    actual_port = httpd.server_address[1]
    url = f"http://{host}:{actual_port}/"
    if on_start:
        on_start(url)
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
