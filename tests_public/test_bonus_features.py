"""Comprehensive Unit Tests for All 10 Bonus Points (+43 Points).

1. MAD & Same-weekday Anomaly (+3)
2. dbt Native Unit Tests (+3)
3. Great Expectations Severity & Actions (+3)
4. Automatic Quarantine (+3)
5. Soda Data Contract (+5)
6. Elementary OSS Observability (+5)
7. OpenLineage Standard Dataset Lineage (+5)
8. Column Lineage Transitive Traversal (+7)
9. Multi-window Multi-Burn-Rate SRE Policy (+7)
10. RAG Embedding & Token Drift Metrics (+7)
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from gx.validate_orders import build_and_run_gx_checkpoint
from observability.anomaly import (
    detect_anomaly,
    ewma_detector,
    mad_detector,
    same_weekday_detector,
)
from observability.lineage import build_ecom_column_lineage_graph, get_column_downstream
from observability.openlineage_emitter import create_openlineage_event, emit_openlineage_events
from observability.rag_metrics import (
    detect_embedding_cosine_drift,
    detect_embedding_norm_shift,
    detect_text_length_shift,
    detect_token_frequency_drift,
)
from observability.slo import calculate_slo, evaluate_multiwindow_burn
from src.contract_validator import load_contract
from src.elementary_reporter import generate_elementary_observability_report
from src.quarantine import quarantine_records
from src.soda_validator import load_soda_contract, validate_soda_contract

ROOT = Path(__file__).resolve().parents[1]
ORDERS_CONTRACT = ROOT / "contracts" / "orders_contract.yaml"
SODA_CONTRACT = ROOT / "contracts" / "soda_orders_contract.yml"


def sample_df():
    now_iso = datetime.now(timezone.utc).isoformat()
    return pd.DataFrame([
        {
            "order_id": 101,
            "customer_id": "C001",
            "amount": 50.0,
            "currency": "USD",
            "status": "completed",
            "created_at": now_iso,
            "updated_at": now_iso,
        },
        {
            "order_id": 102,
            "customer_id": "C002",
            "amount": 75.0,
            "currency": "USD",
            "status": "pending",
            "created_at": now_iso,
            "updated_at": now_iso,
        },
    ])


# 1. Bonus +3: MAD & Same-weekday Anomaly
def test_bonus_1_mad_and_seasonality():
    # Outlier-contaminated history where Z-score fails but MAD succeeds
    history_with_outlier = [100.0, 101.0, 99.0, 102.0, 100.0, 98.0, 5000.0]
    mad_res = mad_detector(101.0, history_with_outlier)
    assert mad_res["is_anomaly"] is False

    # Constant history zero-MAD edge case
    constant_hist = [100.0, 100.0, 100.0, 100.0, 100.0]
    assert mad_detector(100.0, constant_hist)["is_anomaly"] is False
    assert mad_detector(300.0, constant_hist)["is_anomaly"] is True

    # Same weekday seasonality
    history_with_dow = [(0, 600.0), (1, 610.0), (5, 250.0), (5, 245.0), (5, 255.0), (5, 250.0), (5, 248.0)]
    sw_res = same_weekday_detector(600.0, history_with_dow, target_dow=5)
    assert sw_res["is_anomaly"] is True

    # EWMA detector
    ewma_res = ewma_detector(100.0, [100.0, 99.0, 101.0, 100.0, 98.0])
    assert ewma_res["is_anomaly"] is False


# 2. Bonus +3: dbt Native Unit Tests
def test_bonus_2_dbt_native_unit_tests():
    unit_tests_file = ROOT / "dbt_project" / "models" / "marts" / "unit_tests.yml"
    assert unit_tests_file.exists()
    content = unit_tests_file.read_text(encoding="utf-8")
    assert "unit_tests:" in content
    assert "test_completed_orders_sum_to_expected_revenue" in content
    assert "test_multiple_active_customer_versions_does_not_inflate_revenue" in content


# 3. Bonus +3: Great Expectations Severity & Actions
def test_bonus_3_gx_severity_and_actions():
    df_clean = sample_df()
    res_clean = build_and_run_gx_checkpoint(df_clean)
    assert res_clean["success"] is True
    assert res_clean["action"] == "allow"

    df_bad = sample_df()
    df_bad.loc[1, "order_id"] = 101  # Duplicate PK (critical)
    res_bad = build_and_run_gx_checkpoint(df_bad)
    assert res_bad["success"] is False
    assert res_bad["action"] == "block"
    assert res_bad["has_critical_failure"] is True


# 4. Bonus +3: Automatic Quarantine
def test_bonus_4_automatic_quarantine(tmp_path):
    df = sample_df()
    # Inject bad rows: duplicate order_id, invalid currency, negative amount
    bad_row1 = {
        "order_id": 101,  # Duplicate
        "customer_id": "C003",
        "amount": -10.0,  # Negative
        "currency": "EUR",  # Invalid enum
        "status": "completed",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    df = pd.concat([df, pd.DataFrame([bad_row1])], ignore_index=True)
    contract = load_contract(ORDERS_CONTRACT)

    q_file = tmp_path / "quarantine.csv"
    clean_df, quarantined_df, summary = quarantine_records(df, contract, quarantine_file=q_file)

    assert len(clean_df) == 2
    assert len(quarantined_df) == 1
    assert summary["quarantined_rows"] == 1
    assert q_file.exists()
    assert "_quarantine_reasons" in quarantined_df.columns


# 5. Bonus +5: Soda Data Contract
def test_bonus_5_soda_data_contract():
    assert SODA_CONTRACT.exists()
    soda_spec = load_soda_contract(SODA_CONTRACT)
    df = sample_df()
    results = validate_soda_contract(df, soda_spec)
    failed = [r for r in results if not r["passed"]]
    assert len(failed) == 0

    # Test failure on duplicate
    df_dup = sample_df()
    df_dup.loc[1, "order_id"] = 101
    results_dup = validate_soda_contract(df_dup, soda_spec)
    assert any(r["check"] == "soda:duplicate_count" and not r["passed"] for r in results_dup)


# 6. Bonus +5: Elementary OSS Observability Report
def test_bonus_6_elementary_oss_reporting(tmp_path):
    report_file = tmp_path / "elementary_report.json"
    df = sample_df()
    report = generate_elementary_observability_report(orders_df=df, output_path=report_file)

    assert report_file.exists()
    assert "metadata" in report
    assert "tables" in report
    assert "table_anomalies" in report
    assert "dbt_test_runs" in report
    assert report["metadata"]["generator"] == "elementary_oss_adapter"


# 7. Bonus +5: OpenLineage Standard Dataset Lineage
def test_bonus_7_openlineage_events(tmp_path):
    evt_file = tmp_path / "openlineage_events.json"
    events = emit_openlineage_events(output_path=evt_file)

    assert evt_file.exists()
    assert len(events) == 2
    assert events[0]["eventType"] == "START"
    assert events[1]["eventType"] == "COMPLETE"
    assert "inputs" in events[1]
    assert "outputs" in events[1]
    assert events[1]["outputs"][0]["facets"]["columnLineage"] is not None


# 8. Bonus +7: Column Lineage Transitive Traversal
def test_bonus_8_column_lineage():
    graph = build_ecom_column_lineage_graph()
    downstream = get_column_downstream(graph, "raw_orders.amount")
    assert downstream == [
        "stg_orders.amount_usd",
        "fct_daily_revenue.daily_revenue",
        "ceo_revenue_dashboard.revenue",
    ]


# 9. Bonus +7: Multi-window Multi-Burn-Rate SRE Policy
def test_bonus_9_multiwindow_burn_rate():
    # Sustained fast burn -> Critical page
    res_page = evaluate_multiwindow_burn(short_window_burn=15.0, long_window_burn=15.0)
    assert res_page["page"] is True
    assert res_page["severity"] == "critical"

    # Transient spike -> Warning without page
    res_spike = evaluate_multiwindow_burn(short_window_burn=16.0, long_window_burn=1.5)
    assert res_spike["page"] is False
    assert res_spike["severity"] == "warning"

    # Slow burn in long window -> Non-paging ticket warning
    res_slow = evaluate_multiwindow_burn(short_window_burn=2.0, long_window_burn=3.5)
    assert res_slow["page"] is False
    assert res_slow["severity"] == "warning"

    # Healthy
    res_ok = evaluate_multiwindow_burn(short_window_burn=0.5, long_window_burn=0.5)
    assert res_ok["page"] is False
    assert res_ok["severity"] == "ok"


# 10. Bonus +7: RAG Embedding & Token Drift Metrics
def test_bonus_10_rag_metrics_comprehensive():
    # 1. Text Length Shift
    baseline_batch_means = [40, 42, 39, 41, 43, 40, 42]
    current_texts = ["short one", "two words"]
    res_len = detect_text_length_shift(current_texts, baseline_batch_means)
    assert res_len["is_anomaly"] is True

    # 2. Embedding Norm Shift
    res_norm = detect_embedding_norm_shift([2.5, 2.6], [1.0, 1.01, 0.99, 1.0, 1.02])
    assert res_norm["is_anomaly"] is True

    # 3. Cosine Drift
    res_cosine_ok = detect_embedding_cosine_drift(
        current_embeddings=[[0.1, 0.9, 0.4], [0.12, 0.88, 0.41]],
        baseline_centroid=[0.11, 0.89, 0.40],
    )
    assert res_cosine_ok["is_anomaly"] is False

    res_cosine_drift = detect_embedding_cosine_drift(
        current_embeddings=[[-0.9, -0.1, -0.4], [-0.88, -0.12, -0.41]],
        baseline_centroid=[0.11, 0.89, 0.40],
    )
    assert res_cosine_drift["is_anomaly"] is True

    # 4. Token Frequency Shift
    base_docs = ["standard return policy 7 days", "domestic shipping takes 3 days"]
    drifted_docs = ["crypto blockchain trading wallet tokens buy bitcoin"]
    res_token_drift = detect_token_frequency_drift(drifted_docs, base_docs)
    assert res_token_drift["is_anomaly"] is True
