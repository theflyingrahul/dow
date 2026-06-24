# aiver - AI Behavior Versioning

Track how your AI's behavior changes across versions. Version the complete
inference specification (prompt, model identity and version, sampling settings,
evaluation configuration), execute it, and measure semantic drift, stability, and
regressions between versions - with causal attribution. Versioning is automatic
and Git is a hidden storage backend; you never run git commands.

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
```

## Use

```bash
aiver run            # first run scaffolds specs/summarization.yaml; run again to capture v1
# edit specs/summarization.yaml (e.g. change temperature)
aiver run            # captures v2
aiver compare        # v1 vs v2: output diff + drift + stability + verdict (defaults to last two)
aiver explain        # why behavior changed: attributes it to a config field
aiver history        # list captured versions and their stability
aiver inspect v1     # one version's spec, runtime capture, and outputs
aiver tree           # visualize how behavior evolves across versions
aiver tree -o evolution.md   # export a Mermaid diagram; open the Markdown preview
```

Versions are named automatically (v1, v2, ...); refer to them by name or the
shortcuts `last` and `prev`. They form a tree - `aiver run --from v1` branches
from an earlier version. Runs fully offline by default (mock provider +
built-in hashing embedder); no API key required.
