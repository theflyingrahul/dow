"""Embedders behind one interface. The default is offline and dependency-free."""
from __future__ import annotations

import hashlib
import re

import numpy as np

_WORD = re.compile(r"[a-z0-9]+")


class HashingEmbedder:
    """Offline bag-of-words hashing embedder. No model download required.

    Captures lexical overlap, which is enough to demonstrate drift and stability
    fully offline. Swap in ``sentence-transformers`` for true semantic distance.
    """

    def __init__(self, dim: int = 256):
        self.dim = dim
        self.name = f"hashing-{dim}"

    def embed(self, texts):
        vecs = np.zeros((len(texts), self.dim), dtype=np.float64)
        for i, t in enumerate(texts):
            for tok in _WORD.findall((t or "").lower()):
                h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)
                vecs[i, h % self.dim] += 1.0
            norm = np.linalg.norm(vecs[i])
            if norm > 0:
                vecs[i] /= norm
        return vecs


class SentenceTransformerEmbedder:
    def __init__(self, model_name: str):
        from sentence_transformers import SentenceTransformer  # lazy import

        self.model = SentenceTransformer(model_name)
        self.name = model_name

    def embed(self, texts):
        return np.asarray(
            self.model.encode(list(texts), normalize_embeddings=True), dtype=np.float64
        )


class OpenAIEmbedder:
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
