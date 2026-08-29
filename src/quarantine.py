"""Automatic Quarantine Manager for Ingestion Pipelines.

Isolates contract-violating records (e.g., duplicate PKs, invalid enums, type mismatches,
out-of-range values) into a designated quarantine store while routing clean records
downstream to protect analytics models from corruption.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_QUARANTINE_DIR = ROOT / "data" / "quarantine"


def quarantine_records(
    df: pd.DataFrame,
    contract: dict[str, Any],
    quarantine_file: str | Path | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Evaluates DataFrame against contract and splits into clean and quarantined datasets.

    Returns:
        (clean_df, quarantined_df, summary_report)
    """
    if df.empty:
        return df.copy(), pd.DataFrame(), {"total_rows": 0, "clean_rows": 0, "quarantined_rows": 0, "reasons": []}

    columns_or_fields = contract.get("columns") or contract.get("fields") or {}
    invalid_mask = pd.Series(False, index=df.index)
    reasons_per_row = {idx: [] for idx in df.index}

    for col, rules in columns_or_fields.items():
        if col not in df.columns:
            if rules.get("required"):
                invalid_mask[:] = True
                for idx in df.index:
                    reasons_per_row[idx].append(f"missing_required_column:{col}")
            continue

        series = df[col]

        # 1. Not Null Check
        if rules.get("required") or rules.get("not_null"):
            null_mask = series.isna()
            invalid_mask |= null_mask
            for idx in df[null_mask].index:
                reasons_per_row[idx].append(f"null_value:{col}")

        # 2. Unique Check (keep='first' so only extra duplicates are quarantined)
        if rules.get("unique"):
            dup_mask = series.duplicated(keep="first")
            invalid_mask |= dup_mask
            for idx in df[dup_mask].index:
                reasons_per_row[idx].append(f"duplicate_key:{col}={series.loc[idx]}")

        # 3. Accepted Values Check
        accepted = rules.get("accepted_values")
        if accepted is not None:
            invalid_val_mask = series.notna() & ~series.isin(accepted)
            invalid_mask |= invalid_val_mask
            for idx in df[invalid_val_mask].index:
                reasons_per_row[idx].append(f"invalid_enum:{col}={series.loc[idx]}; expected={accepted}")

        # 4. Explicit Type Validation
        type_decl = rules.get("type")
        if type_decl:
            type_str = str(type_decl).strip().lower()
            non_null = series.dropna()
            type_mask = pd.Series(False, index=df.index)
            if not non_null.empty:
                if type_str in {"integer", "int", "bigint"}:
                    is_bool = non_null.apply(lambda x: isinstance(x, (bool, np.bool_)))
                    numeric = pd.to_numeric(non_null, errors="coerce")
                    bad = is_bool | numeric.isna() | (numeric % 1 != 0)
                    type_mask.loc[bad[bad].index] = True
                elif type_str in {"number", "float", "double", "numeric"}:
                    is_bool = non_null.apply(lambda x: isinstance(x, (bool, np.bool_)))
                    numeric = pd.to_numeric(non_null, errors="coerce")
                    bad = is_bool | numeric.isna()
                    type_mask.loc[bad[bad].index] = True
                elif type_str in {"datetime", "timestamp"}:
                    dt = pd.to_datetime(non_null, errors="coerce", utc=True)
                    bad = dt.isna()
                    type_mask.loc[bad[bad].index] = True
                elif type_str in {"boolean", "bool"}:
                    valid_bools = {True, False, 1, 0, "true", "false", "True", "False", "1", "0"}
                    bad = ~non_null.isin(valid_bools)
                    type_mask.loc[bad[bad].index] = True

            invalid_mask |= type_mask
            for idx in df[type_mask].index:
                reasons_per_row[idx].append(f"type_mismatch:{col}; expected={type_str}")

        # 5. Range Bounds Check
        if "min" in rules or "max" in rules:
            num = pd.to_numeric(series, errors="coerce")
            range_mask = pd.Series(False, index=df.index)
            if "min" in rules:
                range_mask |= (num < rules["min"])
            if "max" in rules:
                range_mask |= (num > rules["max"])
            range_mask = range_mask.fillna(False)
            invalid_mask |= range_mask
            for idx in df[range_mask].index:
                reasons_per_row[idx].append(f"out_of_range:{col}={series.loc[idx]}")

        # 6. String Length Bounds Check
        if "min_length" in rules or "max_length" in rules:
            str_series = series.dropna().astype(str)
            len_mask = pd.Series(False, index=df.index)
            if "min_length" in rules:
                len_mask |= (str_series.str.len() < rules["min_length"])
            if "max_length" in rules:
                len_mask |= (str_series.str.len() > rules["max_length"])
            invalid_mask |= len_mask
            for idx in df[len_mask].index:
                reasons_per_row[idx].append(f"length_violation:{col}")

    clean_df = df[~invalid_mask].copy()
    quarantined_df = df[invalid_mask].copy()

    if not quarantined_df.empty:
        quarantined_df["_quarantine_reasons"] = [
            "; ".join(reasons_per_row[i]) for i in quarantined_df.index
        ]
        quarantined_df["_quarantined_at"] = datetime.now(timezone.utc).isoformat()

        # Save to quarantine file if requested or use default
        q_path = Path(quarantine_file) if quarantine_file else DEFAULT_QUARANTINE_DIR / "orders_quarantined.csv"
        q_path.parent.mkdir(parents=True, exist_ok=True)
        quarantined_df.to_csv(q_path, index=False)

    all_reasons = []
    for rlist in reasons_per_row.values():
        all_reasons.extend(rlist)

    summary = {
        "total_rows": int(len(df)),
        "clean_rows": int(len(clean_df)),
        "quarantined_rows": int(len(quarantined_df)),
        "quarantine_rate": float(len(quarantined_df) / len(df)) if len(df) > 0 else 0.0,
        "reasons": list(set(all_reasons)),
    }

    return clean_df, quarantined_df, summary
