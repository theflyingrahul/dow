# Resumable Cohort Capture Design

## Purpose

`dow` already captures one inference specification at a time and aggregates an explicit
set of captured versions. Projects currently have to write their own loops to turn an
ordered sensitivity grid into those versions, bind the grid to immutable inputs, and
resume safely after an interruption. This feature makes that orchestration a reusable
`dow` capability without moving any project statistic, domain schema, or plotting code
into `dow`.

## Scope and ownership

`dow` will own only the generic mechanics:

- a declarative cohort manifest;
- deterministic recursive overrides of a base inference specification;
- ordered, single-process capture with exact-prefix resume;
- immutable manifest and input-artifact binding;
- deterministic hashing of file and directory artifacts;
- aggregation over exactly the versions created by the manifest; and
- CLI, service, and MCP parity.

Consuming projects continue to own provider operations, metrics, comparators,
aggregators, plots, scientific labels, and decision rules. `dow` must contain no
references to LDT, fine-tuning, retrieval, particular model families, or thesis logic.

## Cohort manifest

A cohort lives at `specs/<name>.cohort.yaml` and has this schema:

```yaml
name: seed_sweep
spec: fine_tune_probe
members:
  - label: seed-10
    message: training seed 10
    overrides:
      params:
        training_seed: 10
      inputs:
        - artifact: /absolute/or/project-relative/run-10
  - label: seed-20
    overrides:
      params:
        training_seed: 20
      inputs:
        - artifact: /absolute/or/project-relative/run-20
```

The base spec remains `specs/fine_tune_probe.yaml`. Each member is produced by a
recursive mapping merge: mappings merge recursively; lists and scalar values replace
the base value; explicit `null` replaces the base value. A member may not change the
base spec's `name`. Labels must be unique safe components.

The cohort fingerprint binds the normalized cohort manifest and the base spec. Member
order is part of the identity. `dow` records cohort id and member label in runtime
metadata rather than in the inference config, so `dow explain` sees only scientific
configuration changes.

## Capture and resume

`service.capture_cohort(root, name, resume=False, plot=False)` will:

1. load and validate the cohort and base specs;
2. compute the cohort fingerprint before executing a member;
3. acquire an exclusive cohort lock;
4. create or validate `.dow/cohorts/<name>.json`;
5. validate any previously completed members as an exact prefix with matching labels,
   member fingerprints, and version records;
6. execute and commit each missing member in order;
7. update the cohort record atomically after every committed member;
8. aggregate exactly the recorded version ids, never global history; and
9. save the aggregation id back into the cohort record.

Without `resume=True`, an existing cohort record is an error. Resume fails if the base
spec, member order, overrides, inputs, or existing version bindings differ. A failed
member leaves earlier committed members resumable and never marks the failed member
complete. If the process dies after a version commit but before the progress record is
updated, resume authenticates and adopts that one exact next member from its captured
cohort metadata; more than one unrecorded member fails closed. The lock is advisory to
this workflow and prevents two cohort commands from writing the same cohort
concurrently; it does not claim SLURM liveness, stale-lock recovery, or distributed job
scheduling.

## Artifact binding

Existing file artifacts retain their SHA-256 and byte count. A directory artifact is
hashed as an ordered stream of relative POSIX path, file size, and file bytes. The
record includes `kind: directory`, total bytes, and file count. Symlinks anywhere in a
directory artifact fail closed so the digest cannot silently depend on content outside
the declared tree. Missing artifacts remain represented by `missing: true` for backward
compatibility with ordinary single-version capture; a project provider may impose a
stricter contract.

## Public interfaces

- Python: `dow.service.capture_cohort(...)` and `dow.service.read_cohort(...)`.
- CLI: `dow cohort [NAME] [--resume] [--plot]`.
- MCP: `dow_capture_cohort(project_dir, name, resume, plot)`.
- Discovery ignores `*.cohort.yaml` when resolving ordinary inference specs, as it
  already ignores `*.suite.yaml`.

The command returns the cohort id, ordered member/version mapping, completion state,
and aggregation result. It does not materialize project-specific report files.

## Compatibility and release

The change is additive. Existing specs, stores, commits, suites, and aggregations remain
valid. The package version advances from 2.2.0 to 2.3.0. The changelog, README, command
documentation, man page, CLI tests, MCP tests, artifact tests, resume tests, and full
offline suite are updated together.

## Out of scope

- project-specific source snapshots or model resolution;
- distributed locks, scheduler polling, retry-attempt receipts, or job submission;
- automatic interpretation of payloads;
- statistics, thresholds, or plots;
- migration of an external workflow's private text into `.dow`.
