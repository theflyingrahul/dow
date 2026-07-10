# dow - Drift Observation Workbench

<p align="center">
  <img src="logo.png" alt="dow - Drift Observation Workbench" width="480">
</p>

Track how your AI's behavior changes across versions. Version the complete
inference specification (prompt, model identity and version, sampling settings,
evaluation configuration), execute it, and measure semantic drift, stability, and
regressions between versions - with causal attribution. Versioning is automatic
and Git is a hidden storage backend; you never run git commands.

dow is deliberately slim and **data-structure agnostic**. Its job is to be
extremely reliable at tracking *what you changed* (prompt, model, sampling,
params) and *the metrics you care about* - and nothing more. It ships no
coefficients and no plotting library (you plug those in), it carries any per-item
data in an opaque `payload` it never interprets, and if your captured output is
not text you set `embedding_model: none` to skip the built-in lexical drift. How
your project represents or stores its data never dictates dow's design.

See [PROJECT_PLAN.md](PROJECT_PLAN.md) for the full design.

## Install

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows
pip install -e .
```

Optional providers:

```bash
pip install -e ".[openai]"        # hosted models and embeddings
pip install -e ".[local]"         # local sentence-transformers embeddings
pip install -e ".[mcp]"           # Model Context Protocol server (dow-mcp)
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
| `openai` | OpenAI hosted models | `pip install -e ".[openai]"`; set `OPENAI_API_KEY` |
| `ollama` | Local Ollama runtime | Talks to `http://localhost:11434` |
| `vllm` | vLLM OpenAI-compatible server, local or remote | HTTP only - no extra dependency (see below) |

### vLLM (local or remote)

`provider: vllm` talks to a [vLLM](https://docs.vllm.ai) server over its
OpenAI-compatible HTTP API, so dow itself needs no GPU or vLLM library - just a
reachable server. One provider covers both deployments; only the endpoint changes.

Local server:

```bash
pip install vllm                                 # on the machine with the GPU/model
vllm serve meta-llama/Llama-3.1-8B-Instruct      # serves http://localhost:8000/v1
```

```yaml
model:
  provider: vllm
  name: meta-llama/Llama-3.1-8B-Instruct         # informational
  version: meta-llama/Llama-3.1-8B-Instruct      # sent as the request "model" (the served name)
```

Remote server - point dow at it with an environment variable:

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

### Pluggable plots

dow can render results to figures without shipping a plotting library: reference your
own plot functions under `evaluation.plots`. Each receives a `PlotContext` (the analysis
`results` plus an `out_dir` to write into) and returns the figure path(s):

```yaml
evaluation:
  plots:
    - plots.py:forest_plot          # your matplotlib (or any) code; dow ships none
```

Run `dow compare --plot` or `dow aggregate --plot`. dow copies each figure into the
content-addressed artifact store (`.dow/artifacts/`, git-ignored) and records its hash
and size; for an aggregation the figure is referenced from the persisted bundle, so it
stays regenerable while the bytes stay out of git.

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
the [Model Context Protocol](https://modelcontextprotocol.io) (stdio), so an MCP
client can scaffold specs, capture versions, and compare/explain drift on your
behalf. It runs on the same engine as the CLI - both call into
[dow/service.py](dow/service.py), so the two surfaces never drift apart - and
works fully offline by default (mock provider + built-in embedder).

```bash
pip install -e ".[mcp]"   # or: pip install "dow[mcp]"
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

Each tool resolves its project directory from the `project_dir` argument, else
the `DOW_PROJECT_DIR` environment variable, else the server's current directory.
The 14 tools mirror the CLI: `dow_list_specs`, `dow_init`, `dow_read_spec`,
`dow_write_spec`, `dow_commit`, `dow_compare`, `dow_explain`, `dow_eval`,
`dow_aggregate`, `dow_history`, `dow_inspect`, `dow_tag`, `dow_tree`, and
`dow_docs`. They return structured JSON (config diffs, metrics, comparator and
aggregator results, the version tree, and Mermaid - plus, for text outputs, drift
scores and verdicts), so a client can run the full edit -> commit -> compare loop.

Because dow is data-structure agnostic, the analysis tools tell the client when
the built-in text signals do not apply: with `embedding_model: none`,
`dow_compare`/`dow_explain` return `driftEnabled: false` and null
`semanticDrift`/`verdict`, so the client leans on the configuration diff and the
project's own comparators/aggregators instead.

Alongside the tools, the server exposes read-only **resources** an MCP client can
attach as context: `dow://overview` (this workbench's guide and design),
`dow://docs/<command>` (a command's full help), `dow://specs` (the project's spec
index), and `dow://spec/<name>` (a spec's raw YAML). Resources are not per-call,
so they resolve the project from `DOW_PROJECT_DIR` or the working directory (they
take no `project_dir`).

## Documentation and the manual page

Each command's description and examples live in a single editable text file under
`dow/docs/<command>.txt`. That one source feeds both `dow help <command>` (in the
terminal) and the Unix man page, so they never drift apart. To document a new command
or revise an existing one, edit (or add) its `dow/docs/<command>.txt` - no code changes
needed - and both surfaces update automatically. (Options and arguments are read from
the command's own definition, so those stay correct on their own.)

`dow` also ships a Unix man page generated from those docs:

- On Linux, macOS, or WSL, run `man dow` for the full documentation. A regular
  `pip install` places the page on the man path; for an editable install
  (`pip install -e .`), run `dow man --install` once to copy it to
  `~/.local/share/man/man1`.
- `dow man` prints the page (roff) to stdout - pipe it anywhere, e.g. `dow man | less`.
- After editing docs, refresh the committed page with `dow man --install --dir man`.

On Windows PowerShell, `man` is an alias for `Get-Help` and will not render this
page; use WSL or Git Bash for `man dow`, or read it directly with `dow man`.
