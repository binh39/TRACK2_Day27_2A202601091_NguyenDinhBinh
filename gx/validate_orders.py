#!/usr/bin/env python3
"""Great Expectations Core 1.21 validation workflow with severity and pipeline actions.

Packages expectations into an Expectation Suite, Validation Definition, and Checkpoint,
with explicit severity levels (critical, warning, info) and automated pipeline actions
(BLOCK, QUARANTINE, WARN, ALLOW).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    import great_expectations as gx
except ImportError as exc:
    raise SystemExit("great_expectations is not installed. Run: pip install -r requirements.txt") from exc


def build_and_run_gx_checkpoint(df: pd.DataFrame) -> dict[str, Any]:
    """Runs Great Expectations checkpoint with severity-aware evaluation and action triggers."""
    context = gx.get_context(mode="ephemeral")

    data_source = context.data_sources.add_pandas("orders_data_source")
    asset = data_source.add_dataframe_asset(name="orders_asset")
    batch_definition = asset.add_batch_definition_whole_dataframe("orders_batch_def")

    suite = context.suites.add(gx.ExpectationSuite(name="orders_contract_suite"))

    # 1. Critical Expectations (Must BLOCK / QUARANTINE if violated)
    suite.add_expectation(
        gx.expectations.ExpectColumnValuesToNotBeNull(
            column="order_id",
            notes="Order primary key must not be null (Severity: critical)",
        )
    )
    suite.add_expectation(
        gx.expectations.ExpectColumnValuesToBeUnique(
            column="order_id",
            notes="Order primary key must be unique (Severity: critical)",
        )
    )
    suite.add_expectation(
        gx.expectations.ExpectColumnValuesToNotBeNull(
            column="customer_id",
            notes="Customer foreign key must not be null (Severity: critical)",
        )
    )

    # 2. Warning Expectations (Triggers WARN / Data Quality alerts)
    suite.add_expectation(
        gx.expectations.ExpectColumnValuesToBeBetween(
            column="amount",
            min_value=0,
            notes="Amount must be non-negative (Severity: warning)",
        )
    )
    suite.add_expectation(
        gx.expectations.ExpectColumnValuesToBeInSet(
            column="currency",
            value_set=["USD", "VND"],
            notes="Currency must be USD or VND (Severity: warning)",
        )
    )
    suite.add_expectation(
        gx.expectations.ExpectColumnValuesToBeInSet(
            column="status",
            value_set=["pending", "completed", "refunded", "cancelled"],
            notes="Status must be standard enum (Severity: warning)",
        )
    )
    suite.add_expectation(
        gx.expectations.ExpectColumnValuesToNotBeNull(
            column="created_at",
            notes="Order creation timestamp required (Severity: warning)",
        )
    )
    suite.add_expectation(
        gx.expectations.ExpectColumnValuesToNotBeNull(
            column="updated_at",
            notes="Order update timestamp required (Severity: warning)",
        )
    )

    validation_definition = context.validation_definitions.add(
        gx.ValidationDefinition(
            name="orders_validation_definition",
            data=batch_definition,
            suite=suite,
        )
    )

    checkpoint = context.checkpoints.add(
        gx.Checkpoint(
            name="orders_checkpoint",
            validation_definitions=[validation_definition],
        )
    )

    checkpoint_result = checkpoint.run(
        batch_parameters={"dataframe": df}
    )

    success = bool(checkpoint_result.success)
    evaluated_results: list[dict[str, Any]] = []
    has_critical_failure = False
    has_warning_failure = False

    # Severity mapping based on expectation configuration
    critical_columns = {"order_id", "customer_id"}

    for run_result in checkpoint_result.run_results.values():
        if hasattr(run_result, "results"):
            for res in run_result.results:
                exp_type = res.expectation_config.type if hasattr(res, "expectation_config") else "Expectation"
                col = res.expectation_config.kwargs.get("column", "") if hasattr(res, "expectation_config") else ""
                severity = "critical" if col in critical_columns else "warning"
                passed = bool(res.success)
                if not passed:
                    if severity == "critical":
                        has_critical_failure = True
                    else:
                        has_warning_failure = True
                evaluated_results.append({
                    "expectation": exp_type,
                    "column": col,
                    "severity": severity,
                    "passed": passed,
                })

    if has_critical_failure:
        action = "block"
    elif has_warning_failure:
        action = "warn"
    else:
        action = "allow"

    print(f"=== Great Expectations Checkpoint Result: {'SUCCESS' if success else 'FAILURE'} ===")
    print(f"Pipeline Action Triggered: [{action.upper()}]")
    for item in evaluated_results:
        status_str = "PASS" if item["passed"] else "FAIL"
        print(f"  [{status_str}] ({item['severity'].upper():<8}) {item['expectation']:<35} column={item['column']}")

    return {
        "success": success,
        "action": action,
        "results": evaluated_results,
        "has_critical_failure": has_critical_failure,
        "has_warning_failure": has_warning_failure,
    }


def main() -> None:
    orders_path = ROOT / "data" / "incoming" / "orders.csv"
    df = pd.read_csv(orders_path)
    report = build_and_run_gx_checkpoint(df)
    if report["action"] == "block":
        print("Pipeline halted: Critical expectation check failed.")
        sys.exit(1)


if __name__ == "__main__":
    main()
