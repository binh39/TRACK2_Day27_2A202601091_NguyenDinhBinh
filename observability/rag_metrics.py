"""RAG quality and drift metrics.

Supports:
- Document token/word length distribution shifts,
- Vector embedding space norm and similarity drift detection,
- Cosine similarity drift against reference baseline centroids,
- Vocabulary / token frequency distribution drift.
"""
from __future__ import annotations

import math
from collections import Counter
from typing import Any, Iterable

import numpy as np

from observability.anomaly import zscore_detector


def approximate_token_lengths(texts: Iterable[str]) -> list[int]:
    """Simple whitespace-based word count proxy for token lengths."""
    return [len(str(t).split()) for t in texts]


def detect_text_length_shift(
    current_texts: Iterable[str],
    baseline_batch_means: Iterable[float],
    *,
    threshold: float = 3.0,
) -> dict[str, Any]:
    """Detects shifts in average document text/token length."""
    lengths = approximate_token_lengths(current_texts)
    current_mean = float(np.mean(lengths)) if lengths else 0.0
    result = zscore_detector(current_mean, baseline_batch_means, threshold=threshold)
    result["metric"] = "mean_text_length"
    result["current_mean"] = current_mean
    return result


def detect_embedding_norm_shift(
    current_norms: Iterable[float],
    baseline_norms: Iterable[float],
    *,
    threshold: float = 3.0,
) -> dict[str, Any]:
    """Detects drift in vector embedding norms distribution."""
    cur = np.asarray(list(current_norms), dtype=float)
    base = np.asarray(list(baseline_norms), dtype=float)

    if cur.size == 0 or base.size == 0:
        return {"is_anomaly": False, "score": 0.0, "method": "embedding_norm_zscore", "reason": "empty_input"}

    cur_mean = float(np.mean(cur))
    result = zscore_detector(cur_mean, base, threshold=threshold)
    result["metric"] = "embedding_norm_mean"
    result["current_mean"] = cur_mean
    result["method"] = "embedding_norm_zscore"
    return result


def detect_embedding_cosine_drift(
    current_embeddings: list[list[float]] | np.ndarray,
    baseline_centroid: list[float] | np.ndarray,
    *,
    drift_threshold: float = 0.20,
) -> dict[str, Any]:
    """Detects semantic drift by evaluating average cosine distance from baseline centroid."""
    cur = np.asarray(current_embeddings, dtype=float)
    centroid = np.asarray(baseline_centroid, dtype=float)

    if cur.size == 0 or centroid.size == 0:
        return {"is_anomaly": False, "score": 0.0, "method": "cosine_drift", "reason": "empty_input"}

    # Reshape 1D vector if needed
    if cur.ndim == 1:
        cur = cur.reshape(1, -1)

    centroid_norm = np.linalg.norm(centroid)
    if centroid_norm == 0:
        return {"is_anomaly": False, "score": 0.0, "method": "cosine_drift", "reason": "zero_centroid"}

    cur_norms = np.linalg.norm(cur, axis=1)
    cur_norms[cur_norms == 0] = 1.0

    # Cosine similarities
    sims = np.dot(cur, centroid) / (cur_norms * centroid_norm)
    # Cosine distance: 1 - cosine_similarity
    distances = 1.0 - sims
    mean_distance = float(np.mean(distances))

    is_anomaly = bool(mean_distance > drift_threshold)
    return {
        "is_anomaly": is_anomaly,
        "score": mean_distance,
        "method": "cosine_distance_drift",
        "threshold": drift_threshold,
        "reason": f"mean_cosine_distance={mean_distance:.4f} vs threshold={drift_threshold:.4f}",
    }


def detect_token_frequency_drift(
    current_texts: Iterable[str],
    baseline_texts: Iterable[str],
    *,
    top_k: int = 50,
    threshold: float = 0.35,
) -> dict[str, Any]:
    """Detects vocabulary/token distribution drift using Total Variation Distance (TVD)."""
    cur_tokens = " ".join([str(t).lower() for t in current_texts]).split()
    base_tokens = " ".join([str(t).lower() for t in baseline_texts]).split()

    if not cur_tokens or not base_tokens:
        return {"is_anomaly": False, "score": 0.0, "method": "token_tvd_drift", "reason": "empty_texts"}

    cur_counts = Counter(cur_tokens)
    base_counts = Counter(base_tokens)

    all_vocab = set(cur_counts.keys()).union(set(base_counts.keys()))
    if not all_vocab:
        return {"is_anomaly": False, "score": 0.0, "method": "token_tvd_drift", "reason": "empty_vocab"}

    n_cur = sum(cur_counts.values())
    n_base = sum(base_counts.values())

    # Total Variation Distance (TVD): 0.5 * sum(|P(w) - Q(w)|)
    tvd = 0.5 * sum(abs((cur_counts.get(w, 0) / n_cur) - (base_counts.get(w, 0) / n_base)) for w in all_vocab)

    return {
        "is_anomaly": bool(tvd > threshold),
        "score": float(tvd),
        "method": "token_tvd_drift",
        "threshold": threshold,
        "reason": f"tvd_score={tvd:.4f}, vocab_size={len(all_vocab)}, threshold={threshold}",
    }
