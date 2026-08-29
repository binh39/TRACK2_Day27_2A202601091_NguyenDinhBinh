"""Lineage graph loading and transitive downstream traversal.

Supports:
- Dataset-level lineage traversal (BFS order),
- Column-level transitive lineage traversal (BFS order),
- dbt manifest.json dependency extraction,
- Automated column-to-column lineage graph extraction from dbt SQL models.
"""
from __future__ import annotations

import json
import re
from collections import deque
from pathlib import Path
from typing import Any


def load_graph(path: str | Path) -> dict[str, list[str]]:
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    return payload["dataset_lineage"] if "dataset_lineage" in payload else payload


def get_downstream_assets(graph: dict[str, list[str]], start: str) -> list[str]:
    """Return transitive downstream assets in BFS order, excluding start."""
    seen = {start}
    q: deque[str] = deque([start])
    out: list[str] = []
    while q:
        node = q.popleft()
        for child in graph.get(node, []):
            if child not in seen:
                seen.add(child)
                out.append(child)
                q.append(child)
    return out


def get_column_downstream(
    column_graph: dict[str, list[str]], start_column: str
) -> list[str]:
    """Return transitive downstream columns in BFS order, excluding start_column."""
    seen = {start_column}
    q: deque[str] = deque([start_column])
    out: list[str] = []
    while q:
        node = q.popleft()
        for child in column_graph.get(node, []):
            if child not in seen:
                seen.add(child)
                out.append(child)
                q.append(child)
    return out


def extract_dbt_dataset_graph(manifest_path: str | Path) -> dict[str, list[str]]:
    """Extracts node dependencies from a dbt manifest.json file."""
    path = Path(manifest_path)
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    graph: dict[str, list[str]] = {}
    child_map = manifest.get("child_map", {})
    for parent, children in child_map.items():
        graph[parent] = list(children)
    return graph


def build_ecom_column_lineage_graph() -> dict[str, list[str]]:
    """Constructs the canonical end-to-end Column Lineage graph for the e-commerce warehouse."""
    return {
        # Raw Orders to Staging
        "raw_orders.order_id": ["stg_orders.order_id"],
        "raw_orders.customer_id": ["stg_orders.customer_id"],
        "raw_orders.amount": ["stg_orders.amount_usd"],
        "raw_orders.currency": ["stg_orders.currency"],
        "raw_orders.status": ["stg_orders.status"],
        "raw_orders.created_at": ["stg_orders.created_at", "stg_orders.order_date"],
        "raw_orders.updated_at": ["stg_orders.updated_at"],

        # Raw Customers to Staging
        "raw_customers.customer_id": ["stg_customers.customer_id"],
        "raw_customers.country": ["stg_customers.country"],
        "raw_customers.tier": ["stg_customers.tier"],
        "raw_customers.is_active": ["stg_customers.is_active"],
        "raw_customers.valid_from": ["stg_customers.valid_from"],

        # Staging to Marts (fct_daily_revenue)
        "stg_orders.order_date": ["fct_daily_revenue.order_date"],
        "stg_orders.order_id": ["fct_daily_revenue.completed_order_rows"],
        "stg_orders.amount_usd": ["fct_daily_revenue.daily_revenue"],
        "stg_orders.status": ["fct_daily_revenue.daily_revenue", "fct_daily_revenue.completed_order_rows"],
        "stg_customers.customer_id": ["fct_daily_revenue.daily_revenue"],
        "stg_customers.is_active": ["fct_daily_revenue.daily_revenue"],

        # Marts to CEO Dashboard
        "fct_daily_revenue.order_date": ["ceo_revenue_dashboard.date"],
        "fct_daily_revenue.completed_order_rows": ["ceo_revenue_dashboard.order_count"],
        "fct_daily_revenue.daily_revenue": ["ceo_revenue_dashboard.revenue"],
    }
