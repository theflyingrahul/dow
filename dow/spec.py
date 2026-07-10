"""Inference specification: the fully versioned unit of AI behavior."""
from __future__ import annotations

import dataclasses
import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml


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
