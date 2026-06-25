"""LLM providers behind one interface, including an offline deterministic mock."""
from __future__ import annotations

import hashlib
import importlib
import importlib.util
import random
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class Generation:
    output: str
    tokens: int
    latency_ms: int
    model_version: str
    model_revision: Any
    system_fingerprint: Any


@dataclass
class GenRequest:
    """Everything a local ``python`` provider callable needs to produce one reply."""

    input: str
    system: str
    template: str
    few_shot: list
    temperature: float
    top_p: float
    max_tokens: int
    seed: Any
    sample_index: int
    model_name: str
    model_version: str
    model_revision: Any
    config: dict


class MockProvider:
    """Deterministic, offline provider.

    Output depends on the prompt, model identity and version, and the input, so
    that changing any of them produces semantic drift. Per-sample variation is
    scaled by ``temperature`` so that higher temperature lowers the stability
    score - exactly the behaviour the tool is designed to surface.
    """

    name = "mock"
    VARIANTS = [
        "The customer reports that order {oid} never arrived and support has not responded for a week.",
        "Order {oid} was not delivered, and the customer is frustrated by a week of support silence.",
        "Summary: undelivered order {oid}; no support reply in seven days; customer wants a resolution.",
        "A delivery failure for order {oid}, compounded by an unanswered week-long support ticket.",
        "Ticket: missing order {oid}; support unresponsive for about seven days; escalation likely needed.",
    ]

    def __init__(self, spec):
        self.spec = spec

    def _base_seed(self, input_text: str) -> int:
        m = self.spec.model
        p = self.spec.prompt
        key = "|".join([p.system, p.template, m.name, str(m.version), str(m.revision), input_text])
        return int(hashlib.sha256(key.encode("utf-8")).hexdigest(), 16)

    def generate(self, input_text: str, sample_index: int) -> Generation:
        start = time.perf_counter()
        temp = float(self.spec.sampling.temperature)
        base = self._base_seed(input_text)
        oid = self._extract_oid(input_text)

        if temp <= 0:
            idx = base % len(self.VARIANTS)
        else:
            n_variants = 1 + round(min(max(temp, 0.0), 1.0) * (len(self.VARIANTS) - 1))
            rng = random.Random(base + sample_index * 1000003)
            idx = rng.randrange(n_variants)

        text = self.VARIANTS[idx % len(self.VARIANTS)].format(oid=oid)
        text = " ".join(text.split()[: max(4, int(self.spec.sampling.max_tokens))])
        latency = int((time.perf_counter() - start) * 1000) + 1
        fp = "fp_mock_" + hashlib.sha256(str(self.spec.model.version).encode()).hexdigest()[:8]
        return Generation(
            output=text,
            tokens=len(text.split()),
            latency_ms=latency,
            model_version=self.spec.model.version,
            model_revision=self.spec.model.revision,
            system_fingerprint=fp,
        )

    @staticmethod
    def _extract_oid(text: str) -> str:
        m = re.search(r"#(\d+)", text or "")
        return m.group(1) if m else "N/A"


class OpenAIProvider:
    name = "openai"

    def __init__(self, spec):
        self.spec = spec
        from openai import OpenAI  # lazy import

        self.client = OpenAI()

    def generate(self, input_text: str, sample_index: int) -> Generation:
        s = self.spec
        messages = []
        if s.prompt.system:
            messages.append({"role": "system", "content": s.prompt.system})
        messages.append({"role": "user", "content": s.prompt.template.format(input=input_text)})
        start = time.perf_counter()
        resp = self.client.chat.completions.create(
            model=s.model.version or s.model.name,
            messages=messages,
            temperature=s.sampling.temperature,
            top_p=s.sampling.top_p,
            max_tokens=s.sampling.max_tokens,
            frequency_penalty=s.sampling.frequency_penalty,
            presence_penalty=s.sampling.presence_penalty,
            stop=s.sampling.stop,
            seed=s.sampling.seed,
        )
        latency = int((time.perf_counter() - start) * 1000)
        text = resp.choices[0].message.content or ""
        tokens = resp.usage.completion_tokens if resp.usage else len(text.split())
        return Generation(
            output=text,
            tokens=tokens,
            latency_ms=latency,
            model_version=getattr(resp, "model", s.model.version),
            model_revision=s.model.revision,
            system_fingerprint=getattr(resp, "system_fingerprint", None),
        )


class OllamaProvider:
    name = "ollama"

    def __init__(self, spec):
        self.spec = spec

    def generate(self, input_text: str, sample_index: int) -> Generation:
        import json as _json
        import urllib.request

        s = self.spec
        prompt = (s.prompt.system + "\n\n" if s.prompt.system else "") + s.prompt.template.format(
            input=input_text
        )
        body = {
            "model": s.model.version or s.model.name,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": s.sampling.temperature,
                "top_p": s.sampling.top_p,
                "num_predict": s.sampling.max_tokens,
                "seed": s.sampling.seed,
            },
        }
        start = time.perf_counter()
        req = urllib.request.Request(
            "http://localhost:11434/api/generate",
            data=_json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req) as r:
            data = _json.loads(r.read().decode("utf-8"))
        latency = int((time.perf_counter() - start) * 1000)
        text = data.get("response", "")
        return Generation(
            output=text,
            tokens=len(text.split()),
            latency_ms=latency,
            model_version=s.model.version,
            model_revision=s.model.revision,
            system_fingerprint=data.get("digest"),
        )


def _load_provider_callable(ref: str, base_dir: Path):
    """Load a ``path/to/file.py:function`` or ``module:function`` callable.

    SECURITY: like custom evaluators, a ``python`` provider executes arbitrary
    local Python in-process. Treat a shared spec's ``model.name`` as code.
    """
    if not ref or ":" not in ref:
        raise ValueError(
            "provider 'python' needs model.name = 'path/to/file.py:function' "
            f"or 'module:function' (got {ref!r})."
        )
    target, func_name = ref.rsplit(":", 1)
    target, func_name = target.strip(), func_name.strip()
    if target.endswith(".py") or "/" in target or "\\" in target:
        path = (Path(base_dir) / target).resolve()
        if not path.exists():
            raise FileNotFoundError(f"Provider file not found: {path}")
        module_spec = importlib.util.spec_from_file_location(path.stem, path)
        module = importlib.util.module_from_spec(module_spec)
        sys.modules[module_spec.name] = module  # let dataclasses/typing resolve __module__
        module_spec.loader.exec_module(module)  # executes the user's provider file
    else:
        module = importlib.import_module(target)
    if not hasattr(module, func_name):
        raise AttributeError(f"Provider callable '{func_name}' not found in {target}.")
    return getattr(module, func_name)


class PythonProvider:
    """Offline provider backed by a local Python callable.

    With ``provider: python`` the model identity ``model.name`` is a reference
    ``path/to/file.py:function`` to a callable that receives a :class:`GenRequest`
    and returns the reply - a string, or a dict with an ``output`` key (and an
    optional ``tokens`` count). This versions and evaluates a real, self-contained
    generator (e.g. a rule-based chatbot) fully offline, just like ``mock`` but
    with behavior you control. Per-sample variation is up to the callable, which
    can scale it with ``temperature`` to drive the stability score.
    """

    name = "python"

    def __init__(self, spec, base_dir=None):
        self.spec = spec
        self.base_dir = Path(base_dir) if base_dir else Path.cwd()
        self._fn = _load_provider_callable(spec.model.name, self.base_dir)

    def generate(self, input_text: str, sample_index: int) -> Generation:
        s = self.spec
        req = GenRequest(
            input=input_text,
            system=s.prompt.system,
            template=s.prompt.template,
            few_shot=list(s.prompt.few_shot),
            temperature=float(s.sampling.temperature),
            top_p=float(s.sampling.top_p),
            max_tokens=int(s.sampling.max_tokens),
            seed=s.sampling.seed,
            sample_index=sample_index,
            model_name=s.model.name,
            model_version=s.model.version,
            model_revision=s.model.revision,
            config=s.to_dict(),
        )
        start = time.perf_counter()
        result = self._fn(req)
        if isinstance(result, dict):
            text = str(result.get("output", ""))
            tokens = int(result.get("tokens", len(text.split())))
        else:
            text = str(result)
            tokens = len(text.split())
        latency = int((time.perf_counter() - start) * 1000) + 1
        fp = "fp_python_" + hashlib.sha256(str(s.model.name).encode()).hexdigest()[:8]
        return Generation(
            output=text,
            tokens=tokens,
            latency_ms=latency,
            model_version=s.model.version,
            model_revision=s.model.revision,
            system_fingerprint=fp,
        )


def get_provider(spec):
    provider = (spec.model.provider or "mock").lower()
    if provider == "mock":
        return MockProvider(spec)
    if provider == "openai":
        return OpenAIProvider(spec)
    if provider == "ollama":
        return OllamaProvider(spec)
    if provider == "python":
        return PythonProvider(spec)
    raise ValueError(f"Unknown provider: {provider}")
