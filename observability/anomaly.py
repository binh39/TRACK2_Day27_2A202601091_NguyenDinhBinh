"""Anomaly detection with robust statistics and context awareness.

Supports:
- Z-score baseline detector,
- Median Absolute Deviation (MAD) robust detector with zero-MAD edge case handling,
- Exponentially Weighted Moving Average (EWMA) detector for time series trend adaptation,
- Same-weekday / seasonality-aware detector,
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
    """Robust anomaly detector using Median Absolute Deviation (MAD).

    Scales MAD with 0.6745 (Modified Z-score). Handles zero-MAD edge cases cleanly.
    """
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


def ewma_detector(
    current: float,
    history: Iterable[float],
    alpha: float = 0.3,
    threshold: float = 3.0,
) -> dict[str, Any]:
    """Exponentially Weighted Moving Average (EWMA) anomaly detector."""
    values = np.asarray(list(history), dtype=float)
    if values.size < 3:
        return {"is_anomaly": False, "score": 0.0, "method": "ewma", "reason": "insufficient_history"}

    # Compute EWMA series
    ewma = values[0]
    ewma_var = 0.0
    for i in range(1, len(values)):
        diff = values[i] - ewma
        ewma = alpha * values[i] + (1 - alpha) * ewma
        ewma_var = (1 - alpha) * (ewma_var + alpha * (diff**2))

    std_est = np.sqrt(ewma_var) if ewma_var > 0 else float(np.std(values))
    if std_est == 0:
        score = float("inf") if float(current) != ewma else 0.0
    else:
        score = abs(float(current) - ewma) / std_est

    return {
        "is_anomaly": bool(score > threshold),
        "score": float(score),
        "method": "ewma",
        "reason": f"ewma_mean={ewma:.3f}, ewma_std={std_est:.3f}, threshold={threshold}",
    }


def same_weekday_detector(
    current: float,
    history_with_dow: list[tuple[int, float]],
    target_dow: int,
    threshold: float = 3.0,
) -> dict[str, Any]:
    """Slices historical metrics for the target day-of-week and evaluates anomaly."""
    same_dow_values = [val for dow, val in history_with_dow if dow == target_dow]
    if len(same_dow_values) >= 5:
        res = mad_detector(current, same_dow_values, threshold=threshold)
        res["method"] = "same_weekday:mad"
        res["day_of_week"] = target_dow
        return res
    if len(same_dow_values) >= 3:
        res = zscore_detector(current, same_dow_values, threshold=threshold)
        res["method"] = "same_weekday:zscore"
        res["day_of_week"] = target_dow
        return res
    # Fallback to general history
    all_values = [val for _, val in history_with_dow]
    res = zscore_detector(current, all_values, threshold=threshold)
    res["method"] = "same_weekday:fallback_all"
    return res


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
    - `ewma`: exponentially weighted moving average.
    - `auto`: inspects context (e.g. `same_segment_history`, `day_of_week`,
      outlier prevalence) and selects the most appropriate detector.
    """
    if method == "mad":
        return mad_detector(current, history, threshold=threshold)
    if method == "zscore":
        return zscore_detector(current, history, threshold=threshold)
    if method == "ewma":
        return ewma_detector(current, history, threshold=threshold)
    if method == "same_weekday":
        if context and "history_with_dow" in context and "day_of_week" in context:
            return same_weekday_detector(
                current, context["history_with_dow"], context["day_of_week"], threshold=threshold
            )
        if context and "same_segment_history" in context:
            return mad_detector(current, context["same_segment_history"], threshold=threshold)
        return mad_detector(current, history, threshold=threshold)

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
