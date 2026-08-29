"""OpenLineage Standard Event Emitter.

Generates OpenLineage 1.x compliant RunEvents (START, COMPLETE, FAIL) with Job Facets,
Dataset Schema Facets, Column Lineage Facets, and Data Quality Metrics.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OPENLINEAGE_PATH = ROOT / "reports" / "openlineage_events.json"


def create_openlineage_event(
    *,
    job_name: str = "daily_revenue_pipeline",
    event_type: str = "COMPLETE",
    inputs: list[dict[str, Any]] | None = None,
    outputs: list[dict[str, Any]] | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Builds a valid OpenLineage RunEvent JSON object."""
    event_time = datetime.now(timezone.utc).isoformat()
    r_id = run_id or str(uuid.uuid4())

    default_inputs = inputs or [
        {
            "namespace": "vinai.data_warehouse",
            "name": "raw_orders",
            "facets": {
                "schema": {
                    "_producer": "openlineage-ecom",
                    "_schemaURL": "https://openlineage.io/spec/facets/1-0-0/SchemaDatasetFacet.json",
                    "fields": [
                        {"name": "order_id", "type": "BIGINT", "description": "Primary key"},
                        {"name": "customer_id", "type": "VARCHAR"},
                        {"name": "amount", "type": "DOUBLE"},
                        {"name": "currency", "type": "VARCHAR"},
                        {"name": "status", "type": "VARCHAR"},
                    ],
                },
                "dataSource": {
                    "name": "duckdb_warehouse",
                    "uri": "duckdb://warehouse/game_day.duckdb",
                },
            },
        },
        {
            "namespace": "vinai.data_warehouse",
            "name": "raw_customers",
            "facets": {
                "schema": {
                    "_producer": "openlineage-ecom",
                    "fields": [
                        {"name": "customer_id", "type": "VARCHAR"},
                        {"name": "is_active", "type": "BOOLEAN"},
                        {"name": "valid_from", "type": "TIMESTAMP"},
                    ],
                }
            },
        },
    ]

    default_outputs = outputs or [
        {
            "namespace": "vinai.data_warehouse",
            "name": "fct_daily_revenue",
            "facets": {
                "schema": {
                    "_producer": "openlineage-ecom",
                    "fields": [
                        {"name": "order_date", "type": "DATE"},
                        {"name": "completed_order_rows", "type": "BIGINT"},
                        {"name": "daily_revenue", "type": "DOUBLE"},
                    ],
                },
                "columnLineage": {
                    "_producer": "openlineage-ecom",
                    "_schemaURL": "https://openlineage.io/spec/facets/1-0-0/ColumnLineageDatasetFacet.json",
                    "fields": {
                        "daily_revenue": {
                            "inputFields": [
                                {
                                    "namespace": "vinai.data_warehouse",
                                    "name": "raw_orders",
                                    "field": "amount",
                                }
                            ],
                            "transformationType": "SUM",
                            "transformationDescription": "sum(amount_usd) where status = 'completed'",
                        },
                        "completed_order_rows": {
                            "inputFields": [
                                {
                                    "namespace": "vinai.data_warehouse",
                                    "name": "raw_orders",
                                    "field": "order_id",
                                }
                            ],
                            "transformationType": "COUNT",
                        },
                    },
                },
            },
        }
    ]

    event = {
        "eventType": event_type,
        "eventTime": event_time,
        "run": {
            "runId": r_id,
            "facets": {
                "nominalTime": {
                    "_producer": "openlineage-ecom",
                    "nominalStartTime": event_time,
                }
            },
        },
        "job": {
            "namespace": "vinai.ecom.reliability",
            "name": job_name,
            "facets": {
                "documentation": {
                    "description": "Transforms raw e-commerce orders into daily revenue business marts."
                }
            },
        },
        "inputs": default_inputs,
        "outputs": default_outputs,
        "producer": "https://github.com/OpenLineage/OpenLineage/tree/1.0.0",
        "schemaURL": "https://openlineage.io/spec/1-0-2/OpenLineage.json",
    }
    return event


def emit_openlineage_events(output_path: str | Path | None = None) -> list[dict[str, Any]]:
    """Emits START and COMPLETE OpenLineage standard events and writes to disk."""
    run_id = str(uuid.uuid4())
    start_evt = create_openlineage_event(event_type="START", run_id=run_id)
    complete_evt = create_openlineage_event(event_type="COMPLETE", run_id=run_id)

    events = [start_evt, complete_evt]
    out_file = Path(output_path) if output_path else DEFAULT_OPENLINEAGE_PATH
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(events, indent=2), encoding="utf-8")

    return events
