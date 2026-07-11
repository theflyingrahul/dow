"""Embedders behind one interface. The default is offline and dependency-free."""
from __future__ import annotations

import hashlib
import re

import numpy as np

_WORD = re.compile(r"[a-z0-9]+")

_EMBEDDING_OFF = {"", "none", "off", "null", "false", "no", "0"}

_DRIFT_LABEL = {"lexical": "Lexical drift", "semantic": "Semantic drift"}


def drift_label(kind, *, capitalized: bool = True) -> str:
    """Honest human label for the built-in drift signal, keyed on the embedder.

    The built-in drift is ``1 - cosine`` of the two versions' mean output
    embeddings, so *what* it measures depends entirely on the embedder: the
    default :class:`HashingEmbedder` is bag-of-words, so the number is **lexical**
    (word overlap), not semantic; a sentence-transformers / OpenAI model makes it
    genuinely **semantic**. Callers pass ``embedder.kind`` so the label never
    over-claims. Unknown/absent kinds fall back to a neutral ``"Drift"``.
    """
    label = _DRIFT_LABEL.get(kind, "Drift")
    return label if capitalized else label[0].lower() + label[1:]


def embedding_disabled(name) -> bool:
    """True when a spec opts out of dow's built-in text-embedding signals.

    dow's built-in behavioral signals - semantic drift, stability, output
    difference - assume the captured output is *text*. A project whose behavior
    is not free text (e.g. an aligned vector of ordinal labels carried in the
    payload) sets ``embedding_model: none`` so dow tracks the spec change and the
    project's own plugged-in metrics without computing a meaningless lexical
    number. This keeps dow agnostic to how the project represents its data.
    """
    return str(name).strip().lower() in _EMBEDDING_OFF


class NullEmbedder:
    """Sentinel for ``embedding_model: none`` - dow computes no text signal."""

    name = "none"
    enabled = False
    kind = "none"

    def embed(self, texts):
        import numpy as np

        return np.zeros((len(list(texts)), 0), dtype=np.float64)


class HashingEmbedder:
    """Offline bag-of-words hashing embedder. No model download required.

    Captures lexical overlap, which is enough to demonstrate drift and stability
    fully offline. Swap in ``sentence-transformers`` for true semantic distance.
    """

    kind = "lexical"

    def __init__(self, dim: int = 256):
        self.dim = dim
        self.name = f"hashing-{dim}"

    def embed(self, texts):
        vecs = np.zeros((len(texts), self.dim), dtype=np.float64)
        for i, t in enumerate(texts):
            for tok in _WORD.findall((t or "").lower()):
                h = int(hashlib.md5(tok.encode("utf-8"), usedforsecurity=False).hexdigest(), 16)
                vecs[i, h % self.dim] += 1.0
            norm = np.linalg.norm(vecs[i])
            if norm > 0:
                vecs[i] /= norm
        return vecs


class SentenceTransformerEmbedder:
    kind = "semantic"

    def __init__(self, model_name: str):
        from sentence_transformers import SentenceTransformer  # lazy import

        self.model = SentenceTransformer(model_name)
        self.name = model_name

    def embed(self, texts):
        return np.asarray(
            self.model.encode(list(texts), normalize_embeddings=True), dtype=np.float64
        )


class OpenAIEmbedder:
    kind = "semantic"

    def __init__(self, model_name: str):
        from openai import OpenAI  # lazy import

        self.client = OpenAI()
        self.name = model_name

    def embed(self, texts):
        resp = self.client.embeddings.create(model=self.name, input=list(texts))
        v = np.asarray([d.embedding for d in resp.data], dtype=np.float64)
        v /= np.clip(np.linalg.norm(v, axis=1, keepdims=True), 1e-12, None)
        return v


def get_embedder(name: str):
    if embedding_disabled(name):
        return NullEmbedder()
    n = (name or "hashing-256").lower()
    if n.startswith("hashing"):
        dim = 256
        if "-" in n:
            try:
                dim = int(n.split("-")[1])
            except ValueError:
                pass
        return HashingEmbedder(dim)
    if n.startswith("text-embedding"):
        return OpenAIEmbedder(name)
    try:
        return SentenceTransformerEmbedder(name)
    except Exception:
        return HashingEmbedder(256)
