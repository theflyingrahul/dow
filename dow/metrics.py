"""Behavioral signals: output difference, semantic drift, stability, verdict."""
from __future__ import annotations

import difflib

import numpy as np


def cosine(a, b) -> float:
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def stability(embs) -> float:
    """Mean pairwise self-similarity across N samples of one version."""
    n = len(embs)
    if n < 2:
        return 1.0
    sims = [cosine(embs[i], embs[j]) for i in range(n) for j in range(i + 1, n)]
    return float(np.mean(sims))


def semantic_drift(a_embs, b_embs) -> float:
    """1 - cosine between the mean embedding of each version's outputs.

    What this measures depends on the embedder that produced the vectors: with the
    default hashing (bag-of-words) embedder it is *lexical* drift; with a
    sentence-transformers / OpenAI model it is genuinely *semantic*. Callers label
    it via ``embeddings.drift_label(embedder.kind)`` so the surfaced name is honest.
    """
    a_mean = np.mean(a_embs, axis=0)
    b_mean = np.mean(b_embs, axis=0)
    return float(1.0 - cosine(a_mean, b_mean))


def output_difference(a_texts, b_texts) -> float:
    """1 - mean text-similarity ratio across aligned sample pairs."""
    pairs = list(zip(a_texts, b_texts))
    if not pairs:
        return 0.0
    ratios = [difflib.SequenceMatcher(None, a, b).ratio() for a, b in pairs]
    return float(1.0 - np.mean(ratios))


def verdict(drift: float, stab_a: float, stab_b: float, thresholds: dict) -> str:
    warn = thresholds.get("drift_warn", 0.15)
    fail = thresholds.get("drift_fail", 0.40)
    stab_drop = stab_a - stab_b
    if drift >= fail or stab_drop >= 0.25:
        return "Likely Regression"
    if drift >= warn or stab_drop >= 0.10:
        return "Behavior Drift"
    return "Consistent"
