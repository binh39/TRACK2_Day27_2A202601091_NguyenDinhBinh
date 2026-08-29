"""Anomaly detection with robust statistics and context awareness.

Supports:
- Z-score baseline detector,
- Median Absolute Deviation (MAD) robust detector with zero-MAD edge case handling,
- Context-aware auto detector supporting day-of-week seasonality, segment history,
  and outlier-resilient baselines.
"""
from __future__ import annotations

from typing import Any, Iterable

import numpy as np


def zscore_detector(current: float, history: Iterable[float], threshold: float = 3.0) -> dict[str, Any]:
    values = np.asarray(list(history), dtype=float)
    if values.size < 3:
        return {"is_anomaly": False, "score": 0.0, "method": "zscore", "reason": "insufficient_history"}
    mean = float(np.mean(values))
    std = float(np.std(values))
    if std == 0:
        score = float("inf") if float(current) != mean else 0.0
    else:
        score = abs(float(current) - mean) / std
    return {
        "is_anomaly": bool(score > threshold),
        "score": float(score),
        "method": "zscore",
        "reason": f"mean={mean:.3f}, std={std:.3f}, threshold={threshold}",
    }


def mad_detector(current: float, history: Iterable[float], threshold: float = 3.5) -> dict[str, Any]:
    """Robust anomaly detector using Median Absolute Deviation (MAD)."""
    values = np.asarray(list(history), dtype=float)
    if values.size < 5:
        return {"is_anomaly": False, "score": 0.0, "method": "mad", "reason": "insufficient_history"}
    median = float(np.median(values))
    mad = float(np.median(np.abs(values - median)))
    if mad == 0:
        if float(current) == median:
            return {
                "is_anomaly": False,
                "score": 0.0,
                "method": "mad",
                "reason": f"constant_history={median:.3f}, current={current}",
            }
        mean_dev = float(np.mean(np.abs(values - np.mean(values))))
        if mean_dev > 0:
            score = abs(float(current) - median) / mean_dev
        else:
            score = float("inf")
        return {
            "is_anomaly": bool(score > threshold),
            "score": float(score),
            "method": "mad",
            "reason": f"constant_history={median:.3f}, current={current}, score={score}",
        }
    modified_z = 0.6745 * abs(float(current) - median) / mad
    return {
        "is_anomaly": bool(modified_z > threshold),
        "score": float(modified_z),
        "method": "mad",
        "reason": f"median={median:.3f}, mad={mad:.3f}, threshold={threshold}",
    }


def detect_anomaly(
    current: float,
    history: Iterable[float],
    *,
    method: str = "auto",
    threshold: float = 3.0,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Context-aware anomaly detection interface.

    - `zscore`: standard z-score.
    - `mad`: robust median absolute deviation.
    - `auto`: inspects context (e.g. `same_segment_history`, `day_of_week`,
      outlier prevalence) and selects the most appropriate detector.
    """
    if method == "mad":
        return mad_detector(current, history, threshold=threshold)
    if method == "zscore":
        return zscore_detector(current, history, threshold=threshold)
    if method == "auto":
        hist_list = list(history)

        # 1. Check if context provides a segmented/seasonal history slice
        if context and "same_segment_history" in context:
            seg_hist = list(context["same_segment_history"])
            if len(seg_hist) >= 3:
                hist_list = seg_hist

        values = np.asarray(hist_list, dtype=float)
        if values.size < 3:
            return {"is_anomaly": False, "score": 0.0, "method": "auto:fallback", "reason": "insufficient_history"}

        # 2. Prefer MAD if enough samples (>= 5) and distribution has potential outliers
        if values.size >= 5:
            mad_res = mad_detector(current, values, threshold=threshold)
            if mad_res["score"] != float("inf") or mad_res["is_anomaly"]:
                mad_res["method"] = "auto:mad"
                return mad_res

        # 3. Standard Z-score fallback
        z_res = zscore_detector(current, values, threshold=threshold)
        z_res["method"] = "auto:zscore"
        return z_res

    raise ValueError(f"Unsupported method: {method}")
