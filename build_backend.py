"""In-tree PEP 517 build backend: build the dashboard, then delegate to setuptools.

`python -m build` / `pip wheel .` call these hooks. Before setuptools packages the
project we compile the React dashboard (dashboard/ -> dow/web/) so a wheel always
ships fresh UI assets that `dow dashboard` can serve. Everything else is handled by
setuptools' own ``build_meta`` backend, which this module re-exports.

Escape hatch: set ``DOW_SKIP_DASHBOARD_BUILD=1`` to skip the npm build entirely
(e.g. CI that builds the UI in a separate step, or a Node-less machine where the
assets are already present).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

# Delegate the actual packaging to setuptools; it is provided by
# ``[build-system].requires`` and so is importable inside the build environment.
from setuptools import build_meta as _orig

_ROOT = Path(__file__).parent
_DASHBOARD = _ROOT / "dashboard"
_WEB_INDEX = _ROOT / "dow" / "web" / "index.html"


def _log(msg: str) -> None:
    print(f"[dow build] {msg}", file=sys.stderr, flush=True)


def _run(cmd: list[str], cwd: Path) -> None:
    _log(f"$ {' '.join(str(c) for c in cmd)}  (cwd={cwd})")
    subprocess.run(cmd, cwd=str(cwd), check=True)


def _build_dashboard(*, require: bool) -> None:
    """Compile the dashboard into dow/web.

    require=True  (wheel/sdist): a missing toolchain is fatal unless assets already
                  exist; release artifacts must contain the UI.
    require=False (editable): best effort - only build when assets are missing and
                  never fail the install over a JS build problem.
    """
    if os.environ.get("DOW_SKIP_DASHBOARD_BUILD"):
        _log("DOW_SKIP_DASHBOARD_BUILD set; skipping dashboard build.")
        return

    if not _DASHBOARD.is_dir():
        # Building from an sdist that ships prebuilt dow/web but not the UI sources.
        if require and not _WEB_INDEX.exists():
            _log("dashboard/ sources absent and dow/web is empty; wheel will lack the UI.")
        return

    if not require and _WEB_INDEX.exists():
        return  # editable reinstall: keep the assets already on disk

    npm = shutil.which("npm")
    if npm is None:
        msg = (
            "Node.js/npm not found on PATH; cannot build the dashboard. "
            "Install Node 18+ or set DOW_SKIP_DASHBOARD_BUILD=1."
        )
        if require and not _WEB_INDEX.exists():
            raise RuntimeError(msg)
        _log(msg + " Using existing dow/web assets.")
        return

    try:
        if not (_DASHBOARD / "node_modules").is_dir():
            lock = _DASHBOARD / "package-lock.json"
            _run([npm, "ci"] if lock.exists() else [npm, "install"], _DASHBOARD)
        # Start from an empty output dir so no stale hashed bundles survive.
        web = _WEB_INDEX.parent
        if web.exists():
            shutil.rmtree(web, ignore_errors=True)
        _run([npm, "run", "build"], _DASHBOARD)
        _log("dashboard built -> dow/web")
    except (subprocess.CalledProcessError, OSError) as exc:
        if require and not _WEB_INDEX.exists():
            raise
        _log(f"dashboard build failed ({exc}); using existing dow/web assets.")


def _clean_build_staging() -> None:
    """Drop setuptools' build/lib staging so stale package data (e.g. old hashed
    dashboard bundles from a previous build) cannot leak into the artifact."""
    staging = _ROOT / "build" / "lib"
    if staging.exists():
        _log("removing stale build/lib staging")
        shutil.rmtree(staging, ignore_errors=True)


# --------------------------------------------------------------------------- #
# PEP 517 / PEP 660 hooks
# --------------------------------------------------------------------------- #
# Pass-through hooks that need no extra work.
get_requires_for_build_wheel = _orig.get_requires_for_build_wheel
get_requires_for_build_sdist = _orig.get_requires_for_build_sdist
prepare_metadata_for_build_wheel = _orig.prepare_metadata_for_build_wheel

# Editable hooks (PEP 660) are optional; only expose them if setuptools provides
# them, so the frontend's hasattr() checks stay accurate.
if hasattr(_orig, "get_requires_for_build_editable"):
    get_requires_for_build_editable = _orig.get_requires_for_build_editable
if hasattr(_orig, "prepare_metadata_for_build_editable"):
    prepare_metadata_for_build_editable = _orig.prepare_metadata_for_build_editable


def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):
    _build_dashboard(require=True)
    _clean_build_staging()
    return _orig.build_wheel(wheel_directory, config_settings, metadata_directory)


def build_sdist(sdist_directory, config_settings=None):
    _build_dashboard(require=True)
    _clean_build_staging()
    return _orig.build_sdist(sdist_directory, config_settings)


def build_editable(wheel_directory, config_settings=None, metadata_directory=None):
    _build_dashboard(require=False)
    return _orig.build_editable(wheel_directory, config_settings, metadata_directory)
