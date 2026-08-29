"""SLO calculation and Multi-Window Multi-Burn-Rate alerting.

Implements Google SRE Workbook multiwindow burn rate policy:
- Differentiates between sustained fast burn (page=True) and transient spikes (page=False).
"""
from __future__ import annotations

from typing import Any


def calculate_slo(target: float, bad_events: int, total_events: int) -> dict[str, Any]:
    if not 0 < target < 1:
        raise ValueError("target must be between 0 and 1 (exclusive)")
    if bad_events < 0 or total_events < 0 or bad_events > total_events:
        raise ValueError("invalid event counts")
    allowed_bad_rate = 1.0 - target
    if total_events == 0:
        return {
            "target": target,
            "actual_bad_rate": 0.0,
            "allowed_bad_rate": allowed_bad_rate,
            "burn_rate": 0.0,
            "remaining_error_budget_fraction": 1.0,
            "breached": False,
        }
    actual_bad_rate = bad_events / total_events
    burn_rate = actual_bad_rate / allowed_bad_rate if allowed_bad_rate > 0 else float("inf")
    consumed_fraction = min(1.0, actual_bad_rate / allowed_bad_rate) if allowed_bad_rate > 0 else 1.0
    return {
        "target": target,
        "actual_bad_rate": actual_bad_rate,
        "allowed_bad_rate": allowed_bad_rate,
        "burn_rate": burn_rate,
        "remaining_error_budget_fraction": max(0.0, 1.0 - consumed_fraction),
        "breached": bool(actual_bad_rate > allowed_bad_rate),
    }


def evaluate_multiwindow_burn(
    *,
    short_window_burn: float,
    long_window_burn: float,
    policy: str = "sre_multiwindow",
    short_threshold: float = 14.4,
    long_threshold: float = 14.4,
) -> dict[str, Any]:
    """Evaluates multi-window burn rate against SRE alerting policies.

    - Paging alert (page=True, severity='critical'): triggers when BOTH short
      and long windows exceed threshold (sustained fast burn).
    - Transient spike (page=False, severity='warning'): short window high, but
      long window below threshold.
    - Slow burn (page=False, severity='warning'): long window >= 3.0x.
    - Healthy (page=False, severity='ok'): both within acceptable budget.
    """
    s_burn = float(short_window_burn)
    l_burn = float(long_window_burn)

    # Sustained fast burn -> Critical page
    if s_burn >= short_threshold and l_burn >= long_threshold:
        return {
            "page": True,
            "severity": "critical",
            "reason": f"Sustained critical burn rate (short={s_burn:.2f}, long={l_burn:.2f} >= {short_threshold})",
            "short_window_burn": s_burn,
            "long_window_burn": l_burn,
            "policy": policy,
        }

    # Transient spike in short window -> Warning without paging
    if s_burn >= short_threshold and l_burn < long_threshold:
        return {
            "page": False,
            "severity": "warning",
            "reason": f"Transient spike in short window ({s_burn:.2f}); long window ({l_burn:.2f}) remains below threshold",
            "short_window_burn": s_burn,
            "long_window_burn": l_burn,
            "policy": policy,
        }

    # Slow burn in long window -> Non-paging ticket warning
    if l_burn >= 3.0:
        return {
            "page": False,
            "severity": "warning",
            "reason": f"Slow burn rate in long window ({l_burn:.2f} >= 3.0x); ticket for on-call triage",
            "short_window_burn": s_burn,
            "long_window_burn": l_burn,
            "policy": policy,
        }

    return {
        "page": False,
        "severity": "ok",
        "reason": f"Burn rates healthy (short={s_burn:.2f}, long={l_burn:.2f})",
        "short_window_burn": s_burn,
        "long_window_burn": l_burn,
        "policy": policy,
    }
