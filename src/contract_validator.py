"""Contract validator for tabular and document datasets.

Supports:
- column/field existence and nullability checks,
- uniqueness constraints,
- accepted value enumerations,
- numeric ranges and string length constraints,
- explicit type validation,
- contract-level dataset freshness checks,
- severity classifications (critical, warning, info) and action mapping.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml


def _issue(
    check: str,
    *,
    column: str | None,
    severity: str,
    passed: bool,
    details: str,
) -> dict[str, Any]:
    return {
        "check": check,
        "column": column,
        "severity": severity,
        "passed": bool(passed),
        "details": details,
    }


def load_contract(path: str | Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def validate_dataframe(
    df: pd.DataFrame,
    contract: dict[str, Any],
    reference_time: datetime | None = None,
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    columns_or_fields = contract.get("columns") or contract.get("fields") or {}

    for column, rules in columns_or_fields.items():
        severity = rules.get("severity", "warning")
        required = bool(rules.get("required", False))

        if column not in df.columns:
            if required:
                issues.append(
                    _issue(
                        "required_column",
                        column=column,
                        severity=severity,
                        passed=False,
                        details=f"Missing required column: {column}",
                    )
                )
            continue

        series = df[column]

        # 1. Not Null Check
        if required or rules.get("not_null"):
            null_count = int(series.isna().sum())
            issues.append(
                _issue(
                    "not_null",
                    column=column,
                    severity=severity,
                    passed=(null_count == 0),
                    details=f"null_count={null_count}",
                )
            )

        # 2. Unique Check
        if rules.get("unique"):
            duplicate_count = int(series.duplicated(keep=False).sum())
            issues.append(
                _issue(
                    "unique",
                    column=column,
                    severity=severity,
                    passed=(duplicate_count == 0),
                    details=f"duplicate_rows={duplicate_count}",
                )
            )

        # 3. Accepted Values Check
        accepted = rules.get("accepted_values")
        if accepted is not None:
            invalid_mask = series.notna() & ~series.isin(accepted)
            invalid_count = int(invalid_mask.sum())
            issues.append(
                _issue(
                    "accepted_values",
                    column=column,
                    severity=severity,
                    passed=(invalid_count == 0),
                    details=f"invalid_count={invalid_count}; accepted={accepted}",
                )
            )

        # 4. Explicit Type Validation
        type_decl = rules.get("type")
        if type_decl:
            type_str = str(type_decl).strip().lower()
            non_null = series.dropna()
            type_passed = True
            type_invalid_count = 0

            if not non_null.empty:
                if type_str in {"integer", "int", "bigint"}:
                    is_bool = non_null.apply(lambda x: isinstance(x, (bool, np.bool_)))
                    numeric = pd.to_numeric(non_null, errors="coerce")
                    invalid_mask = is_bool | numeric.isna() | (numeric % 1 != 0)
                    type_invalid_count = int(invalid_mask.sum())
                    type_passed = (type_invalid_count == 0)
                elif type_str in {"number", "float", "double", "numeric"}:
                    is_bool = non_null.apply(lambda x: isinstance(x, (bool, np.bool_)))
                    numeric = pd.to_numeric(non_null, errors="coerce")
                    invalid_mask = is_bool | numeric.isna()
                    type_invalid_count = int(invalid_mask.sum())
                    type_passed = (type_invalid_count == 0)
                elif type_str in {"datetime", "timestamp"}:
                    dt = pd.to_datetime(non_null, errors="coerce", utc=True)
                    invalid_mask = dt.isna()
                    type_invalid_count = int(invalid_mask.sum())
                    type_passed = (type_invalid_count == 0)
                elif type_str in {"boolean", "bool"}:
                    valid_bools = {True, False, 1, 0, "true", "false", "True", "False", "1", "0"}
                    invalid_mask = ~non_null.isin(valid_bools)
                    type_invalid_count = int(invalid_mask.sum())
                    type_passed = (type_invalid_count == 0)
                elif type_str in {"string", "str", "varchar", "text"}:
                    type_passed = True
                    type_invalid_count = 0

            issues.append(
                _issue(
                    "type",
                    column=column,
                    severity=severity,
                    passed=type_passed,
                    details=f"expected_type={type_str}, invalid_count={type_invalid_count}",
                )
            )

        # 5. Numeric Range Support
        if "min" in rules or "max" in rules:
            numeric = pd.to_numeric(series, errors="coerce")
            invalid = pd.Series(False, index=series.index)
            if "min" in rules:
                invalid |= (numeric < rules["min"])
            if "max" in rules:
                invalid |= (numeric > rules["max"])
            invalid_count = int(invalid.fillna(False).sum())
            issues.append(
                _issue(
                    "range",
                    column=column,
                    severity=severity,
                    passed=(invalid_count == 0),
                    details=f"invalid_count={invalid_count}",
                )
            )

        # 6. String Length Support
        if "min_length" in rules or "max_length" in rules:
            str_series = series.dropna().astype(str)
            invalid = pd.Series(False, index=str_series.index)
            if "min_length" in rules:
                invalid |= (str_series.str.len() < rules["min_length"])
            if "max_length" in rules:
                invalid |= (str_series.str.len() > rules["max_length"])
            invalid_count = int(invalid.sum())
            issues.append(
                _issue(
                    "length",
                    column=column,
                    severity=severity,
                    passed=(invalid_count == 0),
                    details=f"invalid_count={invalid_count}",
                )
            )

    # 7. Dataset-level Freshness Validation
    freshness = contract.get("freshness")
    if freshness and isinstance(freshness, dict):
        col = freshness.get("column")
        max_delay = freshness.get("max_delay_minutes", 60)
        f_severity = freshness.get("severity", "warning")

        if col and col in df.columns:
            ts_series = pd.to_datetime(df[col], utc=True, errors="coerce").dropna()
            if not ts_series.empty:
                latest_ts = ts_series.max()
                ref_time = reference_time or datetime.now(timezone.utc)
                if ref_time.tzinfo is None:
                    ref_time = ref_time.replace(tzinfo=timezone.utc)
                delay_minutes = (pd.Timestamp(ref_time) - latest_ts).total_seconds() / 60.0
                passed = (delay_minutes <= max_delay)
                issues.append(
                    _issue(
                        "freshness",
                        column=col,
                        severity=f_severity,
                        passed=passed,
                        details=f"delay_minutes={delay_minutes:.2f}; max_delay_minutes={max_delay}",
                    )
                )
            else:
                issues.append(
                    _issue(
                        "freshness",
                        column=col,
                        severity=f_severity,
                        passed=False,
                        details="No valid datetime values in freshness column",
                    )
                )
        elif col:
            issues.append(
                _issue(
                    "freshness",
                    column=col,
                    severity=f_severity,
                    passed=False,
                    details=f"Freshness column {col} not found in DataFrame",
                )
            )

    return issues


def failed_issues(issues: list[dict[str, Any]], min_severity: str | None = None) -> list[dict[str, Any]]:
    failed = [i for i in issues if not i.get("passed", False)]
    if min_severity is None:
        return failed
    order = {"info": 0, "warning": 1, "critical": 2}
    threshold = order.get(min_severity.lower(), 1)
    return [i for i in failed if order.get(i.get("severity", "warning").lower(), 1) >= threshold]


def determine_action(issues: list[dict[str, Any]]) -> str:
    """Determine pipeline action based on validation issues: 'block', 'quarantine', 'warn', or 'allow'."""
    failed = [i for i in issues if not i.get("passed", False)]
    if not failed:
        return "allow"
    severities = {i.get("severity", "warning").lower() for i in failed}
    if "critical" in severities:
        return "block"
    if "warning" in severities:
        return "warn"
    return "info"
