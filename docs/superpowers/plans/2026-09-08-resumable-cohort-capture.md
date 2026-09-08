# Resumable Cohort Capture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add generic, manifest-driven, resumable cohort capture to `dow`, including deterministic directory-artifact binding and CLI/MCP parity.

**Architecture:** `CohortSpec` validates a `*.cohort.yaml` manifest and recursively overlays each member on one base `InferenceSpec`. The service layer executes missing members sequentially, persists an atomic cohort record after each commit, resumes only an exact prefix, and delegates the final calculation to the existing explicit-version aggregator. The runner binds file or directory inputs without interpreting them.

**Tech Stack:** Python 3.9+, dataclasses, PyYAML, Typer, FastMCP, pytest, existing `dow` Store/service/runner APIs.

**Spec:** `docs/superpowers/specs/2026-09-08-resumable-cohort-capture-design.md`

## Global Constraints

- `dow` remains data-structure agnostic and contains no project-specific metrics or vocabulary.
- Existing single-version specs and suite manifests remain backward compatible.
- Cohort resume accepts only the exact same base spec and ordered member manifest.
- Member metadata must not pollute the scientific configuration diff.
- Directory hashing rejects symlinks and is deterministic across traversal order.
- CLI and MCP call the same service-layer implementation.

---

### Task 1: Cohort manifest contract

**Files:**
- Modify: `dow/spec.py`
- Test: `tests/test_cohort.py`

**Interfaces:**
- Produces: `COHORT_SUFFIX`, `CohortMember`, and `CohortSpec.load/from_dict/to_dict/fingerprint`.
- Consumes: the existing `InferenceSpec.from_dict` for merged member validation.

- [ ] Write failing tests for safe unique labels, required members/spec, recursive mapping merge, scalar/list/null replacement, base-name immutability, and stable fingerprints.
- [ ] Run `pytest -q tests/test_cohort.py` and confirm the missing cohort types fail.
- [ ] Implement the minimal dataclasses, validation, canonical serialization, and recursive override helper in `dow/spec.py`.
- [ ] Re-run `pytest -q tests/test_cohort.py` and confirm the contract tests pass.
- [ ] Commit the manifest contract.

### Task 2: Deterministic directory artifact binding

**Files:**
- Modify: `dow/runner.py`
- Test: `tests/test_cohort.py`
- Test: `tests/test_store_payload.py`

**Interfaces:**
- Produces: artifact records with `kind`, `sha256`, `bytes`, and `files` for directories.
- Consumes: `runner.input_artifacts(spec, base_dir)`.

- [ ] Add failing tests showing directory digests are stable under creation order, change when a nested byte changes, include counts, and reject symlinks.
- [ ] Run the focused tests and confirm directory handling fails before implementation.
- [ ] Implement ordered tree hashing while preserving the current file-artifact record fields.
- [ ] Re-run focused artifact tests and existing runner/store tests.
- [ ] Commit directory binding.

### Task 3: Resumable service-layer cohort capture

**Files:**
- Modify: `dow/service.py`
- Modify: `dow/store.py`
- Test: `tests/test_cohort.py`

**Interfaces:**
- Produces: `service.capture_cohort(root, name=None, resume=False, plot=False)` and `service.read_cohort(root, name)`.
- Consumes: `CohortSpec`, `InferenceSpec`, `runner.execute`, `Store.add_version`, and `service.aggregate`.

- [ ] Add failing tests for ordered commits, exact explicit aggregation membership, atomic checkpoint after each member, exact-prefix resume, changed-manifest refusal, non-prefix/foreign-version refusal, and concurrent-lock refusal.
- [ ] Run the focused tests and verify failures are caused by the missing service API.
- [ ] Add atomic cohort-record helpers and an exclusive lock in `Store`; lock payload contains PID, hostname, and creation timestamp and is always removed by the owning context.
- [ ] Add an internal commit-from-`InferenceSpec` helper so cohort capture never rewrites the user's base YAML.
- [ ] Implement capture/read using runtime cohort metadata and explicit version ids.
- [ ] Re-run `tests/test_cohort.py`, `tests/test_store_atomic.py`, and `tests/test_gitstore_isolation.py`.
- [ ] Commit resumable capture.

### Task 4: CLI, MCP, documentation, and release identity

**Files:**
- Modify: `dow/cli.py`
- Modify: `dow/mcp_server.py`
- Create: `dow/docs/cohort.txt`
- Modify: `README.md`
- Modify: `PYPI_README.md`
- Modify: `PROJECT_PLAN.md`
- Modify: `CHANGELOG.md`
- Modify: `dow/__init__.py`
- Modify: `man/dow.1`
- Test: `tests/test_cohort.py`
- Test: `tests/test_mcp.py`
- Test: `tests/test_manpage.py`

**Interfaces:**
- Produces: `dow cohort`, `dow_capture_cohort`, and package version `2.3.0`.
- Consumes: `service.capture_cohort` and `service.read_cohort` only.

- [ ] Add failing CLI and MCP tests that exercise one real two-member cohort and resume.
- [ ] Run focused tests and confirm both public interfaces are absent.
- [ ] Add the CLI command and MCP tool as thin service wrappers.
- [ ] Add one source-of-truth command document, update overview/release prose, and regenerate the man page with the repository's existing generator.
- [ ] Re-run CLI/MCP/man-page tests.
- [ ] Run `python -m pytest -q`, ruff over changed Python files, and `git diff --check`.
- [ ] Commit and push the generic dow feature before any downstream science dependency is changed.
