#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from observability.anomaly import detect_anomaly
from observability.lineage import get_column_downstream, get_downstream_assets
from observability.rag_metrics import detect_embedding_norm_shift, detect_text_length_shift
from observability.slo import calculate_slo, evaluate_multiwindow_burn
from src.contract_validator import determine_action, failed_issues, load_contract, validate_dataframe
from src.io_utils import load_jsonl


def main() -> None:
    orders = pd.read_csv(ROOT / "data" / "incoming" / "orders.csv")
    history = pd.read_csv(ROOT / "data" / "history" / "metrics_history.csv")
    orders_contract = load_contract(ROOT / "contracts" / "orders_contract.yaml")
    kb_contract = load_contract(ROOT / "contracts" / "kb_contract.yaml")

    # 1. Validate Orders Contract
    orders_issues = validate_dataframe(orders, orders_contract)
    orders_failed = failed_issues(orders_issues)
    orders_critical = failed_issues(orders_issues, min_severity="critical")
    orders_action = determine_action(orders_issues)

    # 2. Anomaly Detection on Order Volume
    current_dow = datetime.now().weekday()
    segment = history.loc[history["day_of_week"] == current_dow, "row_count"].tail(8).tolist()
    row_result = detect_anomaly(
        len(orders),
        history["row_count"].tail(14).tolist(),
        method="auto",
        context={"metric_name": "row_count", "day_of_week": current_dow, "same_segment_history": segment},
    )

    # 3. Orders Freshness
    updated = pd.to_datetime(orders["updated_at"], utc=True, errors="coerce")
    orders_freshness_minutes = (
        pd.Timestamp(datetime.now(timezone.utc)) - updated.max()
    ).total_seconds() / 60.0

    # 4. Knowledge Base Validation & Freshness
    docs = load_jsonl(ROOT / "data" / "incoming" / "kb_documents.jsonl")
    kb_df = pd.DataFrame(docs)
    kb_issues = validate_dataframe(kb_df, kb_contract)
    kb_failed = failed_issues(kb_issues)
    kb_action = determine_action(kb_issues)

    kb_published = pd.to_datetime(kb_df["published_at"], utc=True, errors="coerce")
    kb_freshness_minutes = (
        pd.Timestamp(datetime.now(timezone.utc)) - kb_published.max()
    ).total_seconds() / 60.0

    # 5. RAG Observability Signals
    text_result = detect_text_length_shift(
        [d["content"] for d in docs], history["mean_text_length"].tail(14).tolist()
    )
    mock_current_norms = [1.0, 0.99, 1.01]
    embedding_result = detect_embedding_norm_shift(
        mock_current_norms, history["embedding_norm_mean"].tail(14).tolist()
    )

    # 6. SLO Calculations
    bad_orders = 1 if orders_critical else 0
    orders_contract_slo = calculate_slo(0.999, bad_events=bad_orders, total_events=1)

    bad_kb = 1 if kb_freshness_minutes > 60 else 0
    kb_freshness_slo = calculate_slo(0.99, bad_events=bad_kb, total_events=1)

    # Multi-window Burn Rate Evaluation
    multiwindow_res = evaluate_multiwindow_burn(
        short_window_burn=orders_contract_slo["burn_rate"],
        long_window_burn=orders_contract_slo["burn_rate"],
    )

    # 7. Lineage & Blast Radius
    with open(ROOT / "data" / "baseline" / "lineage_graph.json", "r", encoding="utf-8") as f:
        graph_data = json.load(f)
    dataset_lineage = graph_data.get("dataset_lineage", {})
    column_lineage = graph_data.get("column_lineage", {})

    blast_radius = get_downstream_assets(dataset_lineage, "stg_orders")
    col_blast_radius = get_column_downstream(column_lineage, "raw_orders.amount")

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "orders_rows": int(len(orders)),
        "orders_failed_contract_checks": len(orders_failed),
        "orders_critical_failures": len(orders_critical),
        "orders_action": orders_action,
        "orders_freshness_minutes": orders_freshness_minutes,
        "kb_docs_count": len(docs),
        "kb_failed_contract_checks": len(kb_failed),
        "kb_action": kb_action,
        "kb_freshness_minutes": kb_freshness_minutes,
        "row_count_anomaly": row_result,
        "kb_text_length_signal": text_result,
        "kb_embedding_norm_signal": embedding_result,
        "contract_slo": orders_contract_slo,
        "kb_freshness_slo": kb_freshness_slo,
        "multiwindow_burn": multiwindow_res,
        "sample_blast_radius_from_stg_orders": blast_radius,
        "column_blast_radius_amount": col_blast_radius,
        "failed_contract_checks": len(orders_failed),
        "critical_contract_failures": len(orders_critical),
        "freshness_minutes": orders_freshness_minutes,
    }
    out = ROOT / "reports" / "latest_metrics.json"
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    print("=== DATA RELIABILITY OBSERVABILITY BASELINE ===")
    print(f"Orders rows              : {len(orders)}")
    print(f"Orders failed checks     : {len(orders_failed)} (critical: {len(orders_critical)}, action: {orders_action})")
    print(f"Orders freshness (min)   : {orders_freshness_minutes:.1f}")
    print(f"KB docs count            : {len(docs)} (failed: {len(kb_failed)}, freshness: {kb_freshness_minutes:.1f}m, action: {kb_action})")
    print(f"Row-count anomaly        : {row_result['is_anomaly']} ({row_result['method']}, score={row_result['score']:.2f})")
    print(f"KB text length anomaly   : {text_result['is_anomaly']}")
    print(f"KB embedding drift       : {embedding_result['is_anomaly']}")
    print(f"Contract SLO Burn Rate   : {orders_contract_slo['burn_rate']:.2f} (breached: {orders_contract_slo['breached']})")
    print(f"Multiwindow Burn Page    : {multiwindow_res['page']} ({multiwindow_res['severity']})")
    print(f"Sample Blast Radius      : {' -> '.join(['stg_orders'] + blast_radius)}")
    print(f"Report saved             : {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
