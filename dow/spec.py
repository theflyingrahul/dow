"""Inference specification: the fully versioned unit of AI behavior."""
from __future__ import annotations

import dataclasses
import copy
import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml


COHORT_SUFFIX = ".cohort.yaml"
_SAFE_COMPONENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def _safe_component(value: Any, field_name: str) -> str:
    value = str(value or "")
    if value in {".", ".."} or _SAFE_COMPONENT.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a safe component")
    return value


def _merge_mapping(base: dict, overrides: dict) -> dict:
    """Recursively merge mappings; replace every non-mapping value."""
    merged = copy.deepcopy(base)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_mapping(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


@dataclass
class PromptSpec:
    system: str = ""
    template: str = "{input}"
    few_shot: list = field(default_factory=list)


@dataclass
class ModelSpec:
    provider: str = "mock"
    name: str = "mock-model"
    version: str = "mock-1"
    revision: Any = None


@dataclass
class SamplingSpec:
    temperature: float = 0.2
    top_p: float = 1.0
    max_tokens: int = 256
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0
    stop: Any = None
    seed: int = 7


@dataclass
class EvaluationSpec:
    embedding_model: str = "hashing-256"
    samples: int = 3
    metrics: list = field(default_factory=list)
    comparators: list = field(default_factory=list)
    aggregators: list = field(default_factory=list)
    plots: list = field(default_factory=list)
    thresholds: dict = field(
        default_factory=lambda: {"drift_warn": 0.15, "drift_fail": 0.40}
    )


def _build(cls, data):
    """Construct a dataclass, ignoring unknown keys for forward compatibility."""
    names = {f.name for f in dataclasses.fields(cls)}
    return cls(**{k: v for k, v in (data or {}).items() if k in names})


@dataclass
class InferenceSpec:
    name: str = "spec"
    task: str = ""
    spec_version: int = 1
    operation: str = ""
    params: dict = field(default_factory=dict)
    prompt: PromptSpec = field(default_factory=PromptSpec)
    model: ModelSpec = field(default_factory=ModelSpec)
    sampling: SamplingSpec = field(default_factory=SamplingSpec)
    evaluation: EvaluationSpec = field(default_factory=EvaluationSpec)
    inputs: list = field(default_factory=list)

    @staticmethod
    def load(path) -> "InferenceSpec":
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        return InferenceSpec.from_dict(data)

    @staticmethod
    def from_dict(data: dict) -> "InferenceSpec":
        data = data or {}
        return InferenceSpec(
            name=data.get("name", "spec"),
            task=data.get("task", ""),
            spec_version=data.get("spec_version", 1),
            operation=data.get("operation", ""),
            params=dict(data.get("params") or {}),
            prompt=_build(PromptSpec, data.get("prompt")),
            model=_build(ModelSpec, data.get("model")),
            sampling=_build(SamplingSpec, data.get("sampling")),
            evaluation=_build(EvaluationSpec, data.get("evaluation")),
            inputs=list(data.get("inputs") or []),
        )

    def to_dict(self) -> dict:
        return {
            "spec_version": self.spec_version,
            "name": self.name,
            "task": self.task,
            "operation": self.operation,
            "params": dict(self.params),
            "prompt": asdict(self.prompt),
            "model": asdict(self.model),
            "sampling": asdict(self.sampling),
            "evaluation": asdict(self.evaluation),
            "inputs": list(self.inputs),
        }

    def fingerprint(self) -> str:
        """Stable short hash of the full specification."""
        payload = json.dumps(self.to_dict(), sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


@dataclass(frozen=True)
class CohortMember:
    """One labelled override of a cohort's base inference specification."""

    label: str
    message: str = ""
    overrides: dict = field(default_factory=dict)

    @staticmethod
    def from_dict(data: dict) -> "CohortMember":
        if not isinstance(data, dict):
            raise ValueError("cohort member must be a mapping")
        overrides = data.get("overrides") or {}
        if not isinstance(overrides, dict):
            raise ValueError("cohort member overrides must be a mapping")
        return CohortMember(
            label=_safe_component(data.get("label"), "cohort member label"),
            message=str(data.get("message") or ""),
            overrides=copy.deepcopy(overrides),
        )

    def to_dict(self) -> dict:
        value = {"label": self.label, "overrides": copy.deepcopy(self.overrides)}
        if self.message:
            value["message"] = self.message
        return value


@dataclass(frozen=True)
class CohortSpec:
    """An ordered set of variants of one base :class:`InferenceSpec`."""

    name: str
    spec: str
    members: tuple
    spec_version: int = 1

    @staticmethod
    def load(path) -> "CohortSpec":
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        return CohortSpec.from_dict(data)

    @staticmethod
    def from_dict(data: dict) -> "CohortSpec":
        if not isinstance(data, dict):
            raise ValueError("cohort manifest must be a mapping")
        name = _safe_component(data.get("name"), "cohort name")
        spec = _safe_component(data.get("spec"), "cohort base spec")
        raw_members = data.get("members")
        if not isinstance(raw_members, list) or not raw_members:
            raise ValueError("cohort must contain at least one member")
        members = tuple(CohortMember.from_dict(item) for item in raw_members)
        labels = [member.label for member in members]
        if len(set(labels)) != len(labels):
            raise ValueError("cohort member labels must be unique")
        version = data.get("spec_version", 1)
        if not isinstance(version, int) or isinstance(version, bool) or version != 1:
            raise ValueError("cohort spec_version must be 1")
        return CohortSpec(name=name, spec=spec, members=members, spec_version=version)

    def to_dict(self) -> dict:
        return {
            "spec_version": self.spec_version,
            "name": self.name,
            "kind": "cohort",
            "spec": self.spec,
            "members": [member.to_dict() for member in self.members],
        }

    def materialize(self, base: InferenceSpec):
        """Return ordered ``(member, merged spec)`` pairs without mutating ``base``."""
        if base.name != self.spec:
            raise ValueError(
                f"cohort base spec is {self.spec!r}, but loaded spec is {base.name!r}")
        materialized = []
        for member in self.members:
            if "name" in member.overrides:
                raise ValueError("cohort member may not override the base spec name")
            data = _merge_mapping(base.to_dict(), member.overrides)
            materialized.append((member, InferenceSpec.from_dict(data)))
        return materialized

    def fingerprint(self, base: InferenceSpec) -> str:
        """Full SHA-256 binding the base spec and ordered cohort manifest."""
        payload = {"cohort": self.to_dict(), "base_spec": base.to_dict()}
        encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


@dataclass
class SuiteSpec:
    """A cross-spec aggregation manifest: the many-*spec* counterpart of a cohort.

    Where an :class:`InferenceSpec` is versioned and its ``aggregate`` runs over a
    cohort of *versions within one spec* (K seeds / judges / wordings), a suite runs
    the project's own aggregators/plots over versions drawn from *several specs* -
    the check x model x domain x temperature matrix. dow only wires the members in;
    it ships none of the coefficients or the plotting library (``aggregators`` /
    ``plots`` are the project's callables, exactly as for a single spec).

    Selection (``select``): ``all`` (every version of each listed spec, the full
    matrix), ``latest`` (each spec's latest version), or a tag name (every version
    carrying that tag, across the listed specs).
    """

    name: str = "suite"
    task: str = ""
    spec_version: int = 1
    specs: list = field(default_factory=list)
    select: str = "all"
    aggregators: list = field(default_factory=list)
    plots: list = field(default_factory=list)

    @staticmethod
    def load(path) -> "SuiteSpec":
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        return SuiteSpec.from_dict(data)

    @staticmethod
    def from_dict(data: dict) -> "SuiteSpec":
        data = data or {}
        evaluation = data.get("evaluation") or {}
        return SuiteSpec(
            name=data.get("name", "suite"),
            task=data.get("task", ""),
            spec_version=data.get("spec_version", 1),
            specs=[str(s) for s in (data.get("specs") or [])],
            select=str(data.get("select", "all")),
            aggregators=list(evaluation.get("aggregators") or []),
            plots=list(evaluation.get("plots") or []),
        )

    def to_dict(self) -> dict:
        return {
            "spec_version": self.spec_version,
            "name": self.name,
            "task": self.task,
            "kind": "suite",
            "specs": list(self.specs),
            "select": self.select,
            "evaluation": {
                "aggregators": list(self.aggregators),
                "plots": list(self.plots),
            },
        }

    def fingerprint(self) -> str:
        """Stable short hash of the suite manifest."""
        payload = json.dumps(self.to_dict(), sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def flatten(d: dict, prefix: str = "") -> dict:
    """Flatten a nested config into dotted keys, e.g. ``sampling.temperature``."""
    out: dict = {}
    for k, v in d.items():
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            out.update(flatten(v, key))
        else:
            out[key] = v
    return out
