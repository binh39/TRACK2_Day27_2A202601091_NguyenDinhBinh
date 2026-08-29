#!/usr/bin/env python3
"""Great Expectations Core 1.21 validation workflow.

Packages expectations into an Expectation Suite, Validation Definition, and Checkpoint,
with severity-aware reporting and pipeline actions.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    import great_expectations as gx
except ImportError as exc:
    raise SystemExit("great_expectations is not installed. Run: pip install -r requirements.txt") from exc


def build_and_run_gx_checkpoint(df: pd.DataFrame) -> bool:
    context = gx.get_context(mode="ephemeral")

    data_source = context.data_sources.add_pandas("orders_data_source")
    asset = data_source.add_dataframe_asset(name="orders_asset")
    batch_definition = asset.add_batch_definition_whole_dataframe("orders_batch_def")

    suite = context.suites.add(gx.ExpectationSuite(name="orders_contract_suite"))
    suite.add_expectation(
        gx.expectations.ExpectColumnValuesToNotBeNull(column="order_id")
    )
    suite.add_expectation(
        gx.expectations.ExpectColumnValuesToBeUnique(column="order_id")
    )
    suite.add_expectation(
        gx.expectations.ExpectColumnValuesToNotBeNull(column="customer_id")
    )
    suite.add_expectation(
        gx.expectations.ExpectColumnValuesToBeBetween(column="amount", min_value=0)
    )
    suite.add_expectation(
        gx.expectations.ExpectColumnValuesToBeInSet(column="currency", value_set=["USD", "VND"])
    )
    suite.add_expectation(
        gx.expectations.ExpectColumnValuesToBeInSet(
            column="status", value_set=["pending", "completed", "refunded", "cancelled"]
        )
    )
    suite.add_expectation(
        gx.expectations.ExpectColumnValuesToNotBeNull(column="created_at")
    )
    suite.add_expectation(
        gx.expectations.ExpectColumnValuesToNotBeNull(column="updated_at")
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

    success = checkpoint_result.success
    print(f"=== Great Expectations Checkpoint Result: {'SUCCESS' if success else 'FAILURE'} ===")
    for run_result in checkpoint_result.run_results.values():
        if hasattr(run_result, "results"):
            for res in run_result.results:
                exp_type = res.expectation_config.type if hasattr(res, "expectation_config") else "Expectation"
                col = res.expectation_config.kwargs.get("column", "") if hasattr(res, "expectation_config") else ""
                status_str = "PASS" if res.success else "FAIL"
                print(f"  [{status_str}] {exp_type:<35} column={col}")

    return bool(success)


def main() -> None:
    orders_path = ROOT / "data" / "incoming" / "orders.csv"
    df = pd.read_csv(orders_path)
    success = build_and_run_gx_checkpoint(df)
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
