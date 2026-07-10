"""Upgrade D: the vLLM provider sends a real bearer token, not a masked
placeholder, when ``VLLM_API_KEY`` is set."""
import io
import json
import urllib.request

from dow.providers import VLLMProvider
from dow.spec import InferenceSpec


class _FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _spec():
    return InferenceSpec.from_dict(
        {"name": "t", "model": {"provider": "vllm", "name": "m", "version": "served-m"}}
    )


def _fake_body():
    return json.dumps(
        {
            "choices": [{"message": {"content": "hi"}}],
            "usage": {"completion_tokens": 1},
            "model": "served-m",
        }
    ).encode("utf-8")


def test_vllm_sends_bearer_token(monkeypatch):
    monkeypatch.setenv("VLLM_API_KEY", "secret-token")
    monkeypatch.setenv("VLLM_BASE_URL", "http://localhost:9/v1")
    captured = {}

    def fake_urlopen(req, *args, **kwargs):
        captured["headers"] = dict(req.headers)
        return _FakeResponse(_fake_body())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    VLLMProvider(_spec()).generate("hello", 0)

    # urllib capitalizes header keys: "Authorization".
    assert captured["headers"].get("Authorization") == "Bearer secret-token"


def test_vllm_omits_auth_header_without_key(monkeypatch):
    monkeypatch.delenv("VLLM_API_KEY", raising=False)
    monkeypatch.setenv("VLLM_BASE_URL", "http://localhost:9/v1")
    captured = {}

    def fake_urlopen(req, *args, **kwargs):
        captured["headers"] = dict(req.headers)
        return _FakeResponse(_fake_body())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    VLLMProvider(_spec()).generate("hello", 0)

    assert "Authorization" not in captured["headers"]
