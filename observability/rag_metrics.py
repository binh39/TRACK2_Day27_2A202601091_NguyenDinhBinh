"""RAG quality and drift metrics.

Supports:
- Document token/word length distribution shifts,
- Vector embedding space norm and similarity drift detection.
"""
from __future__ import annotations

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
    """Detects drift in vector embedding norms or similarity distributions."""
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
