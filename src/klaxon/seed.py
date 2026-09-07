"""Seed sample incidents for local demos."""

from __future__ import annotations

import asyncio
import logging

from klaxon.db.engine import dispose_engine, get_session_maker, init_db
from klaxon.db.repository import create_issue, search_issues

log = logging.getLogger(__name__)

SEED_ISSUES: list[dict] = [
    {
        "title": "NullPointerException in checkout service",
        "description": "Checkout fails intermittently when cart has a deleted SKU.",
        "kind": "code",
        "status": "open",
        "severity": "critical",
        "source": "upstream",
        "reporter": "payments-monitor",
        "assignee": "alice",
        "labels": ["backend", "payments"],
        "features": {
            "repo": "acme/checkout",
            "file_path": "src/cart.py",
            "language": "python",
            "stack_trace": "NullPointerException at cart.py:142",
        },
    },
    {
        "title": "Auth token refresh race condition",
        "description": "Concurrent refresh requests invalidate valid sessions.",
        "kind": "code",
        "status": "in_progress",
        "severity": "high",
        "source": "upstream",
        "reporter": "auth-service",
        "assignee": "bob",
        "labels": ["auth"],
        "features": {
            "repo": "acme/identity",
            "file_path": "pkg/token/refresh.go",
            "language": "go",
            "stack_trace": "race detected in refresh.go:88",
        },
    },
    {
        "title": "Frontend crash on empty dashboard",
        "description": "React component throws when metrics array is empty.",
        "kind": "code",
        "status": "acknowledged",
        "severity": "medium",
        "source": "api",
        "reporter": "qa",
        "labels": ["frontend"],
        "features": {
            "repo": "acme/web",
            "file_path": "src/Dashboard.tsx",
            "language": "typescript",
        },
    },
    {
        "title": "Worker OOM on large CSV import",
        "description": "Import worker exhausts memory on files > 2GB.",
        "kind": "code",
        "status": "open",
        "severity": "high",
        "source": "upstream",
        "reporter": "batch-jobs",
        "labels": ["data-pipeline"],
        "features": {
            "repo": "acme/batch",
            "file_path": "workers/csv_import.py",
            "language": "python",
            "stack_trace": "MemoryError during chunk load",
        },
    },
    {
        "title": "API rate limiter off-by-one",
        "description": "429 returned one request early under burst traffic.",
        "kind": "code",
        "status": "resolved",
        "severity": "low",
        "source": "api",
        "reporter": "sre",
        "assignee": "carol",
        "labels": ["api"],
        "features": {
            "repo": "acme/gateway",
            "file_path": "middleware/ratelimit.ts",
            "language": "typescript",
        },
    },
    {
        "title": "Webhook retry storm",
        "description": "Failed webhooks retry without jitter, flooding partners.",
        "kind": "code",
        "status": "open",
        "severity": "high",
        "source": "upstream",
        "reporter": "integrations",
        "labels": ["webhooks"],
        "features": {
            "repo": "acme/hooks",
            "file_path": "retry/backoff.py",
            "language": "python",
        },
    },
    {
        "title": "Schema migration locked prod table",
        "description": "ALTER TABLE blocked writers for 12 minutes.",
        "kind": "code",
        "status": "closed",
        "severity": "critical",
        "source": "agent",
        "reporter": "dba",
        "assignee": "dave",
        "labels": ["database"],
        "features": {
            "repo": "acme/migrations",
            "file_path": "2026_03_orders.sql",
            "language": "sql",
        },
    },
    {
        "title": "Null customer_id in orders fact table",
        "description": "DQ rule failed: 1.2% of orders have NULL customer_id.",
        "kind": "data",
        "status": "open",
        "severity": "critical",
        "source": "upstream",
        "reporter": "dq-monitor",
        "assignee": "erin",
        "labels": ["warehouse", "dq"],
        "features": {
            "dataset": "analytics",
            "table_name": "fact_orders",
            "column_name": "customer_id",
            "quality_rule": "not_null",
            "row_count": 14820,
        },
    },
    {
        "title": "Duplicate SKUs in product dimension",
        "description": "Unique constraint violated after catalog merge.",
        "kind": "data",
        "status": "in_progress",
        "severity": "high",
        "source": "upstream",
        "reporter": "catalog-etl",
        "labels": ["catalog"],
        "features": {
            "dataset": "warehouse",
            "table_name": "dim_products",
            "column_name": "sku",
            "quality_rule": "unique",
            "row_count": 420,
        },
    },
    {
        "title": "Late-arriving events skew daily metrics",
        "description": "Events older than 48h landed after daily close.",
        "kind": "data",
        "status": "acknowledged",
        "severity": "medium",
        "source": "api",
        "reporter": "analytics",
        "labels": ["streaming"],
        "features": {
            "dataset": "events",
            "table_name": "raw_clicks",
            "column_name": "event_ts",
            "quality_rule": "freshness",
            "row_count": 90000,
        },
    },
    {
        "title": "Currency mismatch in FX table",
        "description": "GBP rows labeled as EUR after provider swap.",
        "kind": "data",
        "status": "open",
        "severity": "high",
        "source": "upstream",
        "reporter": "finance-etl",
        "assignee": "frank",
        "labels": ["finance"],
        "features": {
            "dataset": "finance",
            "table_name": "fx_rates",
            "column_name": "currency_code",
            "quality_rule": "domain",
            "row_count": 64,
        },
    },
    {
        "title": "PII leaked into training dump",
        "description": "Email addresses present in anonymized export.",
        "kind": "data",
        "status": "open",
        "severity": "critical",
        "source": "upstream",
        "reporter": "security",
        "labels": ["pii", "security"],
        "features": {
            "dataset": "ml",
            "table_name": "user_features_export",
            "column_name": "email",
            "quality_rule": "pii_absent",
            "row_count": 2100,
        },
    },
    {
        "title": "Partition missing for yesterday",
        "description": "Hive partition dt=yesterday not created by nightly job.",
        "kind": "data",
        "status": "resolved",
        "severity": "medium",
        "source": "agent",
        "reporter": "pipeline",
        "assignee": "gina",
        "labels": ["batch"],
        "features": {
            "dataset": "lake",
            "table_name": "sessions",
            "column_name": "dt",
            "quality_rule": "partition_exists",
            "row_count": 0,
        },
    },
    {
        "title": "Negative inventory quantities",
        "description": "Stock on hand went negative after return reverse.",
        "kind": "data",
        "status": "in_progress",
        "severity": "high",
        "source": "api",
        "reporter": "inventory",
        "labels": ["inventory"],
        "features": {
            "dataset": "ops",
            "table_name": "inventory_levels",
            "column_name": "quantity",
            "quality_rule": "non_negative",
            "row_count": 37,
        },
    },
    {
        "title": "Stale referral codes in CRM sync",
        "description": "Codes expired in source but still active in CRM.",
        "kind": "data",
        "status": "open",
        "severity": "low",
        "source": "upstream",
        "reporter": "crm-sync",
        "labels": ["crm"],
        "features": {
            "dataset": "crm",
            "table_name": "referral_codes",
            "column_name": "expires_at",
            "quality_rule": "freshness",
            "row_count": 512,
        },
    },
]


async def seed(*, force: bool = False) -> int:
    await init_db()
    async with get_session_maker()() as session:
        existing = await search_issues(session, limit=1)
        if existing and not force:
            log.info("Database already has issues; skipping seed (pass force=True to reseed).")
            return 0
        created = 0
        for item in SEED_ISSUES:
            await create_issue(session, **item)
            created += 1
        log.info("Seeded %d issues", created)
        return created


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    count = asyncio.run(seed())
    print(f"Seeded {count} issues")
    asyncio.run(dispose_engine())


if __name__ == "__main__":
    main()
