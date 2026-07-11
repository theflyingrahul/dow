# dow - Drift Observation Workbench

Git for AI behavior. Track how your AI's behavior changes across versions.

Full documentation, logo, design notes, demo, and issue tracker live in the
source repository: https://github.com/theflyingrahul/dow

Version the complete inference specification (prompt, model identity and version,
sampling settings, evaluation configuration), execute it, and measure semantic
drift, stability, and regressions between versions - with causal attribution.
Versioning is automatic and Git is a hidden storage backend; you never run git
commands.

dow is deliberately slim and **data-structure agnostic**. Its job is to be
extremely reliable at tracking *what you changed* (prompt, model, sampling,
params) and *the metrics you care about* - and nothing more. It ships no
coefficients and no plotting library (you plug those in), it carries any per-item
data in an opaque `payload` it never interprets, and if your captured output is
not text you set `embedding_model: none` to skip the built-in lexical drift. How
your project represents or stores its data never dictates dow's design.

## Install

```bash
pip install dow
```

Optional providers:

```bash
pip install "dow[openai]"         # hosted models and embeddings
pip install "dow[local]"          # local sentence-transformers embeddings
pip install "dow[mcp]"            # Model Context Protocol server (dow-mcp)
```

## Use

```bash
dow init           # scaffold specs/summarization.yaml + evals.py
# edit specs/summarization.yaml (your prompt, model, sampling, metrics)
dow commit         # captures v1
# edit specs/summarization.yaml again (e.g. change temperature)
dow commit         # captures v2 (custom metrics run automatically)
dow compare        # v1 vs v2: output diff + drift + stability + verdict (defaults to last two)
dow explain        # why behavior changed: attributes it to a config field
dow tag good v1    # label a version (good, golden, baseline, bad, ...)
dow eval           # run your custom metrics; compare vs previous and last-good
dow history        # list captured versions, stability, and tags
dow inspect v1     # one version's spec, runtime capture, outputs, tags, eval
dow tree           # visualize how behavior evolves across versions
dow tree -o evolution.md   # export a Mermaid diagram; open the Markdown preview
```

Versions are named automatically (v1, v2, ...); refer to them by name, the
shortcuts `last` and `prev`, or any label you applied with `dow tag`. They form
a tree - `dow commit --from v1` branches from an earlier version. Runs fully
offline by default (mock provider + built-in hashing embedder); no API key
required.

## Backends

The model sits behind one provider interface, selected by `model.provider` in the
spec. dow runs fully offline by default and never requires a backend.

| `provider` | Backend | Notes |
|---|---|---|
| `mock` | Deterministic offline mock (default) | No network or keys; ideal for demos and golden tests |
| `python` | A local Python callable (`path.py:function`) | Version your own generator, fully offline |
| `openai` | OpenAI hosted models | `pip install "dow[openai]"`; set `OPENAI_API_KEY` |
| `ollama` | Local Ollama runtime | Talks to `http://localhost:11434` |
| `vllm` | vLLM OpenAI-compatible server, local or remote | HTTP only - no extra dependency |

### vLLM (local or remote)

`provider: vllm` talks to a vLLM server (https://docs.vllm.ai) over its
OpenAI-compatible HTTP API, so dow itself needs no GPU or vLLM library - just a
reachable server. One provider covers both deployments; only the endpoint changes.

Point dow at a remote server with an environment variable:

```bash
export VLLM_BASE_URL="https://vllm.internal.example.com/v1"
export VLLM_API_KEY="..."     # only if the server was started with --api-key
dow commit
```

`VLLM_BASE_URL` defaults to `http://localhost:8000/v1`. The spec's `model.version`
(falling back to `model.name`) is sent as the request's `model` and must match the
server's `--served-model-name`.

## Custom metrics

Plug in your own evaluators - plain functions that receive an `EvalContext` and
return a score or named scores - and reference them from the spec:

```yaml
evaluation:
  metrics:
    - evals.py:avg_word_count      # local file : function
    - my_pkg.metrics:accuracy      # importable module : function
```

```python
# evals.py
def avg_word_count(ctx):
    return sum(len(o.split()) for o in ctx.outputs) / max(1, len(ctx.outputs))
```

`dow eval` runs them, saves the scores with the version, and compares against
the previous version and the last one you tagged (`dow tag good`). Evaluation
is automatic on `dow commit` and reused thereafter unless you pass `--rerun`.

### Paired comparators

Some metrics compare one version **against another**, item by item - agreement
and reliability coefficients (weighted kappa, Krippendorff's alpha, Gwet AC2,
ICC, flip rate) and their confidence intervals. dow ships none of them: you plug
in your own paired callables under `evaluation.comparators`. A comparator receives
a `CompareContext` with both versions (`a` = baseline, `b` = variant), each
exposing its per-item `payload`, and may return a number or a
`{estimate, ci_low, ci_high}` band:

```yaml
evaluation:
  comparators:
    - metrics.py:weighted_kappa    # local file : function
```

```python
# metrics.py
def flip_rate(cctx):
    a, b = cctx.a.payload["labels"], cctx.b.payload["labels"]
    return sum(x != y for x, y in zip(a, b)) / len(a)
```

Comparators run on `dow compare` and `dow explain`, so the same attribution that
pins a change to a single field also reports how far the coefficient moved. The
`payload` a comparator reads is any structured per-item data a `python` provider
returns alongside its text output; dow keeps it out of git (content-addressed
under `.dow/artifacts/`) and rehydrates it on read.

### Cohort aggregators (N-way)

Some checks compare a whole **set** of versions at once - the agreement of a label
across K seeds, K judges, or K prompt wordings (ICC, Fleiss/Gwet AC2, Krippendorff's
alpha over K raters, with bootstrap CIs). Comparators see two versions; aggregators
see the whole cohort. Plug your own in under `evaluation.aggregators`; dow ships none
of the coefficients:

```yaml
evaluation:
  aggregators:
    - metrics.py:seed_reliability   # ICC / AC2 / alpha over K seeds
```

An aggregator receives a `CohortContext` whose `members` is one context per version
(each with its `payload`), aligns them by your own key, and returns the same shapes as
a comparator. `dow aggregate` selects the cohort (an explicit version list, every
version carrying a `--tag`, or all of them), runs the aggregators, and saves a durable,
git-tracked bundle under `.dow/aggregations/`; `dow aggregate --list` and `--show <id>`
retrieve past results.

### Cross-spec suites (the matrix)

`dow aggregate` works within a single spec. A robustness sweep often spans a whole
matrix - the same check across several models, domains, or temperatures, where each cell
is its own spec. `dow suite` aggregates versions drawn from several specs at once. You
declare the participating specs and the project's own aggregators/plots in a manifest,
`specs/<name>.suite.yaml`:

```yaml
# specs/robustness_matrix.suite.yaml
name: robustness_matrix
specs: [check_llama, check_qwen, check_mistral]
select: all              # all | latest | <tag>
evaluation:
  aggregators: [suite_metrics.py:agg_matrix]      # your callables; dow ships none
  plots: [suite_plots.py:plot_matrix]
```

Each member keeps its own captured `config` (and the `CohortContext` carries a parallel
`specs` list), so your aggregator can bucket by spec / model / domain / temperature.
Member ids are composite `spec:version`. `select` chooses the cohort: `all` (the full
matrix), `latest` (each spec's newest version), or a tag name. Runs persist as durable,
git-tracked suite bundles, separate from single-spec aggregations, so they never leak
into `dow history`; `dow suite --list`, `--show <id>`, and `--plot` work as for aggregate.

### Pluggable plots

dow can render results to figures without shipping a plotting library: reference your
own plot functions under `evaluation.plots`. Each receives a `PlotContext` (the analysis
`results` plus an `out_dir` to write into) and returns the figure path(s):

```yaml
evaluation:
  plots:
    - plots.py:forest_plot          # your matplotlib (or any) code; dow ships none
```

Run `dow compare --plot`, `dow aggregate --plot`, or `dow suite --plot`. dow copies each
figure into the content-addressed artifact store (`.dow/artifacts/`, git-ignored) and
records its hash and size; for an aggregation or suite the figure is referenced from the
persisted bundle, so it stays regenerable while the bytes stay out of git.

### Non-text outputs

dow's built-in signals - semantic drift, stability, output difference - assume the
captured output is text. When a version's behavior is *not* free text (an aligned
vector of ordinal labels, a cluster assignment, a numeric score), set
`embedding_model: none`:

```yaml
evaluation:
  embedding_model: none    # outputs aren't text; skip dow's built-in lexical drift
```

dow then tracks the specification change (prompt, model, sampling, params) and runs
your own metrics, comparators, and aggregators, without inventing a meaningless
lexical number; `compare`, `history`, `tree`, and `inspect` simply omit the built-in
drift. The structured per-item data rides in the `payload` a `python` provider
returns, and dow persists it **whatever its in-memory type** - numpy arrays, sets,
dataclasses, and numpy scalars all degrade to a faithful JSON-native form. Your
project never has to pre-convert its data to satisfy dow.

## MCP server

Prefer to drive dow from an AI agent? `dow-mcp` exposes the core workbench over
the Model Context Protocol (https://modelcontextprotocol.io) over stdio, so an MCP
client can scaffold specs, capture versions, and compare/explain drift on your
behalf. It runs on the same engine as the CLI, so the two surfaces never drift
apart, and works fully offline by default (mock provider + built-in embedder).

```bash
pip install "dow[mcp]"    # install the server
dow-mcp                    # serve over stdio (usually launched by your MCP client)
```

Point an MCP client at the `dow-mcp` command and set the project directory it
should operate on:

```json
{
  "mcpServers": {
    "dow": {
      "command": "dow-mcp",
      "env": { "DOW_PROJECT_DIR": "/path/to/your/project" }
    }
  }
}
```

The 15 tools mirror the CLI: `dow_list_specs`, `dow_init`, `dow_read_spec`,
`dow_write_spec`, `dow_commit`, `dow_compare`, `dow_explain`, `dow_eval`,
`dow_aggregate`, `dow_suite`, `dow_history`, `dow_inspect`, `dow_tag`, `dow_tree`,
and `dow_docs`. They return structured JSON (config diffs, metrics, comparator and
aggregator results, the version tree, and Mermaid - plus, for text outputs, drift
scores and verdicts), so a client can run the full edit, commit, compare loop.
The server also exposes read-only resources an MCP client can attach as context:
`dow://overview`, `dow://docs/<command>`, `dow://specs`, and `dow://spec/<name>`.

## Documentation and the manual page

Each command's help lives in a single editable text file that feeds both
`dow help <command>` (in the terminal) and the Unix man page, so they never drift
apart. `dow` ships that man page: after a normal `pip install` run `man dow`, or
run `dow man` to print it (roff) to stdout and pipe it anywhere.

The full design (PROJECT_PLAN.md), the changelog, the runnable demo, and the
architecture notes live in the source repository:
https://github.com/theflyingrahul/dow

## License

MIT. The full license text ships in the package (LICENSE) and is available in the
repository: https://github.com/theflyingrahul/dow
