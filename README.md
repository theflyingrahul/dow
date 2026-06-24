# aiver - AI Behavior Versioning

Git for AI behavior. Version the complete inference specification (prompt, model
identity and version, sampling settings, evaluation configuration), execute it,
and measure semantic drift, stability, and regressions between versions - with
causal attribution.

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

## Use (mirrors git)

```bash
aiver init                        # initialize a behavior repo (+ example spec)
aiver commit -m "baseline" -t v1  # run the spec and record a behavior snapshot
# edit specs/summarization.yaml (e.g. change temperature)
aiver commit -m "experiment" -t v2
aiver diff v1 v2                  # config diff + output diff + drift + stability + verdict
aiver blame v1 v2                 # attribute the change to a configuration field
aiver log                         # history of snapshots
aiver show v2                     # spec + runtime capture + metrics
aiver status                      # working spec vs last snapshot
```

Runs fully offline by default (mock provider + built-in hashing embedder); no API
key required.
