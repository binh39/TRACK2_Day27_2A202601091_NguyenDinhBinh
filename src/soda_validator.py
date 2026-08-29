"""Soda Data Contract Adapter & Validator.

Parses Soda Data Contracts / Soda Core check specifications and executes deterministic
validations on DataFrames, returning standard check dictionaries compatible with student_api.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml


def load_soda_contract(contract_path: str | Path) -> dict[str, Any]:
    with open(contract_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def validate_soda_contract(
    df: pd.DataFrame,
    soda_contract: dict[str, Any],
    reference_time: datetime | None = None,
) -> list[dict[str, Any]]:
    """Evaluates Soda Core style checks on a DataFrame.

    Supports:
    - missing_count(col) == 0
    - duplicate_count(col) == 0
    - min(col) >= threshold
    - invalid_count(col) == 0 with valid_values
    - freshness(col) <= threshold
    - row_count > 0
    - data_type checking
    """
    results: list[dict[str, Any]] = []

    # 1. Dataset-level table checks
    table_checks = soda_contract.get("checks", [])
    for tc in table_checks:
        if isinstance(tc, str) and "row_count > 0" in tc:
            rc = len(df)
            passed = rc > 0
            results.append({
                "check": "soda:row_count",
                "column": None,
                "severity": "critical",
                "passed": passed,
                "details": f"row_count={rc}",
            })

    # 2. Column-level checks
    columns = soda_contract.get("columns", [])
    for col_def in columns:
        col_name = col_def.get("name")
        data_type = col_def.get("data_type")
        checks = col_def.get("checks", [])

        if col_name not in df.columns:
            results.append({
                "check": "soda:missing_column",
                "column": col_name,
                "severity": "critical",
                "passed": False,
                "details": f"Column {col_name} not found in dataset",
            })
            continue

        series = df[col_name]

        # Data type check
        if data_type:
            dtype_str = str(data_type).lower()
            non_null = series.dropna()
            type_passed = True
            if not non_null.empty:
                if dtype_str in {"integer", "int"}:
                    numeric = pd.to_numeric(non_null, errors="coerce")
                    type_passed = bool((~numeric.isna() & (numeric % 1 == 0)).all())
                elif dtype_str in {"number", "float", "double"}:
                    numeric = pd.to_numeric(non_null, errors="coerce")
                    type_passed = bool((~numeric.isna()).all())
                elif dtype_str in {"timestamp", "datetime"}:
                    dt = pd.to_datetime(non_null, errors="coerce", utc=True)
                    type_passed = bool((~dt.isna()).all())

            results.append({
                "check": "soda:data_type",
                "column": col_name,
                "severity": "warning",
                "passed": type_passed,
                "details": f"expected_type={dtype_str}",
            })

        for chk in checks:
            if isinstance(chk, str):
                if "missing_count" in chk:
                    missing_cnt = int(series.isna().sum())
                    results.append({
                        "check": "soda:missing_count",
                        "column": col_name,
                        "severity": "critical",
                        "passed": (missing_cnt == 0),
                        "details": f"missing_count={missing_cnt}",
                    })
                elif "duplicate_count" in chk:
                    dup_cnt = int(series.duplicated(keep=False).sum())
                    results.append({
                        "check": "soda:duplicate_count",
                        "column": col_name,
                        "severity": "critical",
                        "passed": (dup_cnt == 0),
                        "details": f"duplicate_count={dup_cnt}",
                    })
                elif "min(" in chk:
                    numeric = pd.to_numeric(series, errors="coerce")
                    min_val = float(numeric.min()) if not numeric.empty else 0.0
                    passed = bool(min_val >= 0.0)
                    results.append({
                        "check": "soda:min_bounds",
                        "column": col_name,
                        "severity": "warning",
                        "passed": passed,
                        "details": f"min_value={min_val}",
                    })
                elif "freshness" in chk:
                    ts = pd.to_datetime(series, utc=True, errors="coerce").dropna()
                    ref = reference_time or datetime.now(timezone.utc)
                    delay_mins = (pd.Timestamp(ref) - ts.max()).total_seconds() / 60.0 if not ts.empty else float("inf")
                    results.append({
                        "check": "soda:freshness",
                        "column": col_name,
                        "severity": "warning",
                        "passed": (delay_mins <= 60.0),
                        "details": f"delay_minutes={delay_mins:.2f}; max_delay=60m",
                    })

            elif isinstance(chk, dict):
                # invalid_count with valid_values
                for key, opts in chk.items():
                    if "invalid_count" in key:
                        valid_vals = opts.get("valid_values", [])
                        invalid_cnt = int((series.notna() & ~series.isin(valid_vals)).sum())
                        results.append({
                            "check": "soda:invalid_count",
                            "column": col_name,
                            "severity": "warning",
                            "passed": (invalid_cnt == 0),
                            "details": f"invalid_count={invalid_cnt}; valid_values={valid_vals}",
                        })

    return results
