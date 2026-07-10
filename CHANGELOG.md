# Changelog

All notable changes to dow are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/), and dow adheres to
[Semantic Versioning](https://semver.org/).

## [2.0.0] - 2025

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
