from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports" / "latest_metrics.json"
ELEMENTARY_REPORT = ROOT / "reports" / "elementary_report.json"
OPENLINEAGE_REPORT = ROOT / "reports" / "openlineage_events.json"
HISTORY = ROOT / "data" / "history" / "metrics_history.csv"
QUARANTINE_FILE = ROOT / "data" / "quarantine" / "orders_quarantined.csv"

st.set_page_config(
    page_title="Data & AI Reliability Dashboard",
    page_icon="🛡️",
    layout="wide",
)

st.title("🛡️ Data & AI Reliability Observability Center")
st.caption("E-Commerce Pipeline, Data Contracts, OpenLineage, Elementary OSS & AI Support Agent Observability")

if not REPORT.exists():
    st.warning("⚠️ Chưa tìm thấy báo cáo số liệu. Hãy chạy `python scripts/run_baseline.py` trước.")
    st.stop()

report = json.loads(REPORT.read_text(encoding="utf-8"))

# Top KPI Row
kpi1, kpi2, kpi3, kpi4, kpi5, kpi6 = st.columns(6)
kpi1.metric("Orders Ingested", f"{report.get('orders_rows', 0):,} rows")
q_sum = report.get("quarantine_summary", {})
kpi2.metric("Clean / Quarantined", f"{q_sum.get('clean_rows', report.get('orders_rows', 0))} / {q_sum.get('quarantined_rows', 0)}")
kpi3.metric("Orders Freshness", f"{report.get('orders_freshness_minutes', 0):.1f} min")
kpi4.metric("Contract Action", report.get("orders_action", "allow").upper())
kpi5.metric(
    "SLO Burn Rate",
    f"{report.get('contract_slo', {}).get('burn_rate', 0):.2f}x",
    delta="-Breached" if report.get("contract_slo", {}).get("breached") else "Normal",
    delta_color="inverse" if report.get("contract_slo", {}).get("breached") else "normal",
)
kpi6.metric("KB Freshness", f"{report.get('kb_freshness_minutes', 0):.1f} min")

st.divider()

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 Observability Signals & Drift",
    "🎯 SLO & Multi-window Alerts",
    "🌐 Lineage & OpenLineage",
    "📜 Contracts & Quarantine",
    "🩺 Elementary OSS Monitoring",
])

with tab1:
    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("Order Volume Anomaly Detector (MAD / Seasonality)")
        anom = report.get("row_count_anomaly", {})
        is_anom = anom.get("is_anomaly", False)
        if is_anom:
            st.error(f"🚨 Phát hiện bất thường dung lượng đơn hàng! (Score: {anom.get('score', 0):.2f} | Method: {anom.get('method')})")
        else:
            st.success(f"✅ Dung lượng đơn hàng bình thường. (Score: {anom.get('score', 0):.2f} | Method: {anom.get('method')})")
        st.caption(f"Chi tiết thuật toán: {anom.get('reason', 'N/A')}")

        if HISTORY.exists():
            history_df = pd.read_csv(HISTORY)
            st.line_chart(history_df.set_index("date")[["row_count"]], height=240)

    with col_b:
        st.subheader("RAG & AI Support Multi-Metric Observability")
        rag_len = report.get("kb_text_length_signal", {})
        rag_emb = report.get("kb_embedding_norm_signal", {})
        rag_cos = report.get("kb_cosine_drift_signal", {})

        if rag_len.get("is_anomaly"):
            st.error(f"🚨 Bất thường độ dài văn bản KB: mean={rag_len.get('current_mean', 0):.1f} words (Score: {rag_len.get('score', 0):.2f})")
        else:
            st.success(f"✅ Độ dài văn bản KB bình thường: mean={rag_len.get('current_mean', 0):.1f} words")

        if rag_emb.get("is_anomaly"):
            st.error(f"🚨 Phát hiện trôi dạt vector embedding norm (Norm Drift)!")
        else:
            st.success("✅ Không gian vector embedding norm ổn định.")

        if rag_cos.get("is_anomaly"):
            st.error(f"🚨 Phát hiện trôi dạt góc Cosine Semantic Drift (Score: {rag_cos.get('score', 0):.4f} > {rag_cos.get('threshold', 0):.4f})")
        else:
            st.success(f"✅ Cosine Semantic Distance ổn định ({rag_cos.get('score', 0):.4f} <= {rag_cos.get('threshold', 0.20):.2f}).")

        if HISTORY.exists():
            history_df = pd.read_csv(HISTORY)
            st.line_chart(history_df.set_index("date")[["mean_text_length", "embedding_norm_mean"]], height=240)

with tab2:
    st.subheader("Service Level Objectives (SLO) & Multi-window Burn Rate Policy")
    slo_col1, slo_col2 = st.columns(2)
    
    with slo_col1:
        st.markdown("### Orders Contract Pass SLO (Target: 99.9%)")
        c_slo = report.get("contract_slo", {})
        st.write(f"- **Allowed Bad Rate**: {c_slo.get('allowed_bad_rate', 0):.5f}")
        st.write(f"- **Actual Bad Rate**: {c_slo.get('actual_bad_rate', 0):.5f}")
        st.write(f"- **Burn Rate**: {c_slo.get('burn_rate', 0):.2f}x")
        st.write(f"- **Remaining Error Budget**: {c_slo.get('remaining_error_budget_fraction', 1.0) * 100:.2f}%")
        st.progress(max(0.0, min(1.0, c_slo.get("remaining_error_budget_fraction", 1.0))))

    with slo_col2:
        st.markdown("### Multi-window Multi-Burn-Rate Alert Evaluation (Google SRE)")
        mb = report.get("multiwindow_burn", {})
        if mb.get("page"):
            st.error(f"🔥 CRITICAL PAGE: {mb.get('reason')}")
        elif mb.get("severity") == "warning":
            st.warning(f"⚠️ WARNING: {mb.get('reason')}")
        else:
            st.success(f"✅ OK: {mb.get('reason')}")

with tab3:
    st.subheader("Data Lineage & OpenLineage Standard")
    col_lin1, col_lin2 = st.columns(2)
    with col_lin1:
        st.markdown("#### Dataset-level Blast Radius từ `stg_orders`:")
        blast = report.get("sample_blast_radius_from_stg_orders", [])
        st.code(" -> ".join(["raw_orders", "stg_orders"] + blast))

        st.markdown("#### Column-level Blast Radius từ `raw_orders.amount`:")
        col_blast = report.get("column_blast_radius_amount", [])
        st.code(" -> ".join(["raw_orders.amount"] + col_blast))

    with col_lin2:
        st.markdown("#### OpenLineage 1.x Standard RunEvents:")
        if OPENLINEAGE_REPORT.exists():
            st.json(json.loads(OPENLINEAGE_REPORT.read_text(encoding="utf-8"))[:1])

with tab4:
    st.subheader("Data Contract Compliance & Automatic Quarantine")
    st.write(f"- **Orders Failed Checks**: {report.get('orders_failed_contract_checks', 0)}")
    st.write(f"- **Orders Critical Failures**: {report.get('orders_critical_failures', 0)}")
    st.write(f"- **Orders Pipeline Action**: `{report.get('orders_action', 'allow')}`")
    st.write(f"- **Soda Contract Failed Checks**: {report.get('soda_failed_checks', 0)}")
    
    if QUARANTINE_FILE.exists():
        st.markdown("#### Quarantined Invalid Records Store (`data/quarantine/`):")
        q_df = pd.read_csv(QUARANTINE_FILE)
        st.dataframe(q_df, use_container_width=True)

with tab5:
    st.subheader("Elementary OSS Observability Report Integration")
    if ELEMENTARY_REPORT.exists():
        elem_data = json.loads(ELEMENTARY_REPORT.read_text(encoding="utf-8"))
        st.write(f"- **Elementary Status**: `{elem_data.get('summary', {}).get('status', 'healthy').upper()}`")
        st.write(f"- **Total Anomalies Detected**: {elem_data.get('summary', {}).get('total_anomalies', 0)}")
        st.markdown("#### dbt Test Executions Recorded:")
        st.dataframe(pd.DataFrame(elem_data.get("dbt_test_runs", [])), use_container_width=True)
        st.markdown("#### Table Anomalies:")
        st.json(elem_data.get("table_anomalies", []))
