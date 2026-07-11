# Changelog

All notable changes to dow are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/), and dow adheres to
[Semantic Versioning](https://semver.org/).

## [2.1.0] - 2026-07-11

### Added
- **Cross-spec suites (`dow suite`) — aggregate versions across *several* specs
  (the check × model × domain × temperature matrix).** `dow aggregate` runs a
  project's N-way aggregators over a cohort within a *single* spec, but a
  robustness sweep is often a matrix where each cell is its own spec. A suite is
  declared in a manifest, `specs/<name>.suite.yaml`, listing the participating
  `specs:` plus the project's own `evaluation.aggregators`/`plots`:

  ```yaml
  name: robustness_matrix
  specs: [check_llama, check_qwen, check_mistral]
  select: all            # all | latest | <tag>
  evaluation:
    aggregators: [suite_metrics.py:agg_matrix]
    plots: [suite_plots.py:plot_matrix]
  ```

  `select` chooses the cohort: `all` (every version of each listed spec — the
  full matrix), `latest` (each spec's newest version), or a tag name (each
  spec's versions carrying that tag). Each member keeps its own captured config,
  and the `CohortContext` gains a parallel `specs` list naming each member's
  spec, so an aggregator can bucket by spec / model / domain / temperature.
  Member ids are composite `spec:version`. Suite runs persist as durable,
  git-tracked bundles under `.dow/aggregations/_suites/<name>/` — a **separate
  namespace** from single-spec aggregations — so a manifest never leaks into
  `dow history` or single-spec resolution. `dow suite --list`, `--show <id>`,
  and `--plot` mirror `dow aggregate`. The `.suite.yaml` suffix keeps manifests
  out of the inference-spec code paths (`spec_files` in both the service core and
  the CLI now exclude it). dow still ships **none** of the coefficients or the
  plotting library — the suite only wires in the project's callables.
- **`dow_suite` MCP tool** (the server now exposes **15** tools), plus the
  `suite` command in the generated man page and `dow help suite`.

### Security
- `Store.save_suite_aggregation` / `get_suite_aggregation` validate the suite
  name (and aggregation id) with `_safe_component` on both the write and read
  paths, matching the 2.0.4 store-write hardening; regression test added
  (`tests/test_security.py::test_store_writes_block_traversal_suite_name`).

## [2.0.4] - 2026-07-11

### Security
- **Store write methods now reject a path-traversal spec name / version id /
  aggregation id.** `Store.add_version`, `Store.save_eval`, and
  `Store.save_aggregation` build paths under `.dow/versions/<name>/…` and
  `.dow/aggregations/<name>/…`, but — unlike the already-guarded read methods
  (`get_record`, `get_aggregation`) — they did not validate the component, so a
  name containing `..`, a path separator, an absolute prefix, or a NUL byte
  could write a record or aggregation bundle **outside** the `.dow` store. The
  shipped CLI/MCP surface was not directly reachable (the service layer reduces
  a spec name to `Path(name).stem` before it reaches the store), so this is a
  defense-in-depth fix, not a live exploit — but the store is dow's documented
  security boundary (the same one the read guards protect) and now self-defends
  on every write via `_safe_component`. Regression tests added
  (`tests/test_security.py::test_store_writes_block_traversal_spec_name`).

### Fixed
- **Store writes are now atomic, so a torn write can no longer corrupt the
  store.** `index.json`, per-version records, aggregation bundles, and
  content-addressed artifacts were written in place with `write_text` /
  `write_bytes`; a crash — or a Dropbox/NFS sync landing mid-write — could leave
  a half-written file. A truncated `index.json` breaks the entire version
  history, and a truncated artifact would fail its later sha256 check. Every
  durable write now goes through a temp file in the same directory that is
  flushed, `fsync`ed, and `os.replace`d over the target (an atomic rename), so a
  reader sees either the old bytes or the new bytes, never a mix; on failure the
  temp is removed and the original is left intact. `.dow/.gitignore` now also
  ignores `*.tmp` crash residue (added to existing stores on `ensure`, preserving
  any user lines). Regression tests added (`tests/test_store_atomic.py`).

## [2.0.3] - 2026-07-11

### Added
- **`dow --version` / `dow -V`.** A top-level flag now prints the installed
  version and exits. The version was already computed for the man-page header
  but was not reachable from the command line.

### Fixed
- **Man page dropped any prose line that began with `'` or `.`.** A wrapped
  documentation sentence starting with an apostrophe or period (e.g. init's
  "'dow commit' to capture v1 ...") is a roff *control* line, so troff silently
  swallowed it and warned `macro 'dow' not defined`. The roff generator now
  guards such lines with a leading zero-width `\&`, so every sentence renders.
  Regression tests added (`tests/test_manpage.py`).
- **Regenerated the packaged man page** (`man/dow.1`): its header showed a stale
  `dow 0.1.0` and predated the escaping fix.

## [2.0.2] - 2026-07-11

### Changed
- **Dedicated PyPI long description.** The package now ships a link-free
  `PYPI_README.md` as its PyPI page (the GitHub `README.md`, with its images and
  relative links, stays the repository front page). PyPI does not resolve a
  project's relative links or images, so the previous page showed broken
  references; the PyPI description now uses plain prose with absolute repository
  URLs only and points readers to https://github.com/theflyingrahul/dow for the
  logo, full design notes, demo, and changelog.

### Fixed
- `dow --version` now falls back to the packaged `__version__` (single-sourced)
  instead of a hardcoded placeholder when distribution metadata is unavailable.
- Corrected the recorded release dates for 2.0.0 and 2.0.1 (both 2026-07-10) and
  removed a stale absolute path from the demo runbook.

## [2.0.1] - 2026-07-10

### Fixed
- **Store isolation when nested inside another git repository.** dow keeps its
  behavior store in a hidden `.dow` git repo. When that store lived *inside* a
  project's own repository (the normal deployment - e.g. a project's
  `.../dow_adapter/` folder), `GitStore.is_repo()` walked up to the enclosing
  repo and reported it as dow's store, so `dow commit` / `aggregate` / `tag` ran
  `git add -A` against the **host project repo** and committed the entire project
  tree (including unrelated files) into the project's history. `is_repo()` now
  treats a directory as dow's store only when its own git top-level resolves to
  that exact directory, so dow always creates and uses its own `.dow/.git` and
  never touches the surrounding project repo. Regression tests added
  (`tests/test_gitstore_isolation.py`).

## [2.0.0] - 2026-07-10

First packaged release on PyPI. dow remains a slim, data-structure-agnostic
tracking shell that ships no metric, statistics, or plotting code - projects
plug in their own evaluators, comparators, aggregators, and plot functions.

### Added
- **Pluggable paired comparators** (`evaluation.comparators`): metrics that see
  both versions of a pair and return a number, a `{estimate, ci_low, ci_high}`
  band, or a bag of named metrics (stored verbatim). Computed on demand by
  `dow compare` / `dow explain`.
- **N-way cohort aggregators** (`evaluation.aggregators`) and the `dow aggregate`
  command: run a project's reliability metrics over a cohort of K versions and
  persist a durable, git-tracked result bundle.
- **Pluggable plots** (`evaluation.plots`) via `dow compare --plot` /
  `dow aggregate --plot`: project plot callables receive an output directory and
  return figure paths; dow stores the figure bytes as content-addressed,
  git-ignored artifacts. dow ships no plotting library.
- **Structured payloads + content-addressed artifact storage**: heavy per-item
  data is offloaded from git to `.dow/artifacts/` and rehydrated with sha256
  integrity checks on read.
- **Data-structure-agnostic core**: `embedding_model: none` skips the built-in
  lexical drift/stability/verdict for non-text outputs; payloads persist
  regardless of in-memory type (numpy, sets, dataclasses, ...).
- **Read-only MCP server** (`dow-mcp`): agnostic-aware tools plus context
  resources (`dow://overview`, `dow://docs/{command}`, `dow://specs`,
  `dow://spec/{name}`).
- **Packaging**: PyPI distribution with a single-sourced version, MIT license,
  classifiers, keywords, and project URLs; the manual page and per-command help
  ship in the sdist and wheel.
- **CI/CD**: GitHub Actions for tests (Python 3.9-3.13), ruff, bandit, and
  pip-audit, plus a tag-triggered release workflow (GitHub Release + PyPI via
  Trusted Publishing).
- **Security test suite** (`tests/test_security.py`).

### Fixed
- **Path traversal** in `Store.get_aggregation` and `service.docs`, both
  reachable through the read-only MCP surface: unsanitized ids/names could
  escape the `.dow` store and read arbitrary files. Store ids, spec names, and
  artifact references are now validated as single-segment slugs, and the docs
  command is confined to the packaged documentation directory.

### Security
- `HashingEmbedder` MD5 marked `usedforsecurity=False` (non-cryptographic
  bucketing).
- git is driven strictly as an argv list (never a shell); specs are parsed with
  `yaml.safe_load`. Both are pinned by tests.
