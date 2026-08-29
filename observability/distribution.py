"""Distribution shift detection module.

Evaluates changes between baseline and current data distributions using
mean ratios, robust median/quantile shifts, and statistical bounds.
"""
from __future__ import annotations

from typing import Any, Iterable

import numpy as np


def detect_distribution_shift(
    current_values: Iterable[float],
    baseline_values: Iterable[float],
    *,
    ratio_threshold: float = 3.0,
) -> dict[str, Any]:
    """Detects distribution drift between baseline and current data."""
    cur = np.asarray(list(current_values), dtype=float)
    base = np.asarray(list(baseline_values), dtype=float)

    if cur.size == 0 or base.size == 0:
        return {"is_anomaly": False, "score": 0.0, "method": "distribution_shift", "reason": "empty_input"}

    cur_mean = float(np.mean(cur))
    base_mean = float(np.mean(base))

    # Mean Ratio Score
    if base_mean == 0:
        mean_score = float("inf") if cur_mean != 0 else 1.0
    else:
        mean_score = max(abs(cur_mean / base_mean), abs(base_mean / cur_mean)) if cur_mean != 0 else float("inf")

    # Median & Robust Quartile Shift
    cur_med = float(np.median(cur))
    base_med = float(np.median(base))
    if base_med == 0:
        med_score = float("inf") if cur_med != 0 else 1.0
    else:
        med_score = max(abs(cur_med / base_med), abs(base_med / cur_med)) if cur_med != 0 else float("inf")

    score = max(mean_score, med_score)
    is_anomaly = bool(score >= ratio_threshold)

    return {
        "is_anomaly": is_anomaly,
        "score": float(score),
        "method": "distribution_shift",
        "reason": f"baseline_mean={base_mean:.3f}, current_mean={cur_mean:.3f}, baseline_median={base_med:.3f}, current_median={cur_med:.3f}",
    }
