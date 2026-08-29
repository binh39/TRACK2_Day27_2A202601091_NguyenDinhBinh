from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports" / "latest_metrics.json"
HISTORY = ROOT / "data" / "history" / "metrics_history.csv"

st.set_page_config(
    page_title="Data & AI Reliability Dashboard",
    page_icon="🛡️",
    layout="wide",
)

st.title("🛡️ Data & AI Reliability Observability Center")
st.caption("E-Commerce Pipeline & AI Support Agent Health Monitoring | Game Day Control")

if not REPORT.exists():
    st.warning("⚠️ Chưa tìm thấy báo cáo số liệu. Hãy chạy `python scripts/run_baseline.py` trước.")
    st.stop()

report = json.loads(REPORT.read_text(encoding="utf-8"))

# Top KPI Row
kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)
kpi1.metric("Orders Ingested", f"{report.get('orders_rows', 0):,} rows")
kpi2.metric("Orders Freshness", f"{report.get('orders_freshness_minutes', 0):.1f} min")
kpi3.metric("Contract Action", report.get("orders_action", "allow").upper())
kpi4.metric(
    "Contract SLO Burn Rate",
    f"{report.get('contract_slo', {}).get('burn_rate', 0):.2f}x",
    delta="-Breached" if report.get("contract_slo", {}).get("breached") else "Normal",
    delta_color="inverse" if report.get("contract_slo", {}).get("breached") else "normal",
)
kpi5.metric("KB Freshness", f"{report.get('kb_freshness_minutes', 0):.1f} min")

st.divider()

tab1, tab2, tab3, tab4 = st.tabs(["📊 Observability Signals", "🎯 SLO & Error Budgets", "🌐 Lineage & Blast Radius", "📜 Contract Validations"])

with tab1:
    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("Order Volume Anomaly Detector")
        anom = report.get("row_count_anomaly", {})
        is_anom = anom.get("is_anomaly", False)
        if is_anom:
            st.error(f"🚨 Phát hiện bất thường dung lượng đơn hàng! (Score: {anom.get('score', 0):.2f} | Method: {anom.get('method')})")
        else:
            st.success(f"✅ Dung lượng đơn hàng bình thường. (Score: {anom.get('score', 0):.2f} | Method: {anom.get('method')})")
        st.caption(f"Chi tiết: {anom.get('reason', 'N/A')}")

        if HISTORY.exists():
            history_df = pd.read_csv(HISTORY)
            st.line_chart(history_df.set_index("date")[["row_count"]], height=250)

    with col_b:
        st.subheader("RAG & AI Support Observability")
        rag_len = report.get("kb_text_length_signal", {})
        rag_emb = report.get("kb_embedding_norm_signal", {})

        if rag_len.get("is_anomaly"):
            st.error(f"🚨 Bất thường độ dài văn bản KB: mean={rag_len.get('current_mean', 0):.1f} words (Score: {rag_len.get('score', 0):.2f})")
        else:
            st.success(f"✅ Độ dài văn bản KB bình thường: mean={rag_len.get('current_mean', 0):.1f} words")

        if rag_emb.get("is_anomaly"):
            st.error(f"🚨 Phát hiện trôi dạt vector embedding (Embedding Space Drift)!")
        else:
            st.success("✅ Không gian vector embedding ổn định.")

        if HISTORY.exists():
            history_df = pd.read_csv(HISTORY)
            st.line_chart(history_df.set_index("date")[["mean_text_length", "embedding_norm_mean"]], height=250)

with tab2:
    st.subheader("Service Level Objectives (SLO) & Multi-window Alerting")
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
        st.markdown("### Multi-window Multi-Burn-Rate Alert Evaluation")
        mb = report.get("multiwindow_burn", {})
        if mb.get("page"):
            st.error(f"🔥 CRITICAL PAGE: {mb.get('reason')}")
        elif mb.get("severity") == "warning":
            st.warning(f"⚠️ WARNING: {mb.get('reason')}")
        else:
            st.success(f"✅ OK: {mb.get('reason')}")

with tab3:
    st.subheader("Data Lineage & Incident Blast Radius")
    st.markdown("#### Dataset-level Blast Radius từ `stg_orders`:")
    blast = report.get("sample_blast_radius_from_stg_orders", [])
    st.code(" -> ".join(["raw_orders", "stg_orders"] + blast))

    st.markdown("#### Column-level Blast Radius từ `raw_orders.amount`:")
    col_blast = report.get("column_blast_radius_amount", [])
    st.code(" -> ".join(["raw_orders.amount"] + col_blast))

with tab4:
    st.subheader("Data Contract Compliance Details")
    st.write(f"- **Orders Failed Checks**: {report.get('orders_failed_contract_checks', 0)}")
    st.write(f"- **Orders Critical Failures**: {report.get('orders_critical_failures', 0)}")
    st.write(f"- **Orders Pipeline Action**: `{report.get('orders_action', 'allow')}`")
    st.write(f"- **KB Failed Checks**: {report.get('kb_failed_contract_checks', 0)}")
    st.write(f"- **KB Pipeline Action**: `{report.get('kb_action', 'allow')}`")
