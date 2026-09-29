"""Finance S0-20: a full batch of 1000 billing documents x 5 lines in one push (#1309).

Runs through the real route on the blank schema, like the rest of the suite. "Inside the
route's existing timeout" is taken as the production batch budget the ingest routes were
sized against (the 2026-09-07 incident note in `ingest.py`: gunicorn's 120s worker
timeout); the assertion here is well inside it, so a regression that makes the batch
quadratic fails loudly instead of flaking.
"""
from __future__ import annotations

import time

from sqlalchemy import text

from tests.test_ingest_billing_documents import (  # noqa: F401 - pytest fixture reuse
    MARKER,
    env,
)

__all__ = ["env"]

BUDGET_SECONDS = 120


def _document(n: int) -> dict:
    ref = f"SRT_DB:IV:{700000 + n}"
    lines = [
        {
            "source_ref": f"{ref}:{i}",
            "line_number": i,
            "product_code": "ZZFIN-P1" if i % 2 else "ZZFIN-P2",
            "description": "batch line",
            "uom": "PCS",
            "quantity": i,
            "unit_price": 10,
            "discount_amount": 0,
            "net_amount": 10 * i,
            "tax_code": "SV-10",
            "tax_rate": 10,
            "tax_amount": i,
            "line_total": 11 * i,
        }
        for i in range(1, 6)
    ]
    return {
        "source_ref": ref,
        "document_type": "invoice",
        "doc_no": f"IV-BATCH/{n:05d}",
        "doc_date": "2026-09-15",
        "status": "posted",
        "source_modified_at": "2026-09-15T09:00:00",
        "customer_code": "ZZFIN-C1",
        "agent_code": "ZZFIN-AG1",
        "currency_code": "MYR",
        "currency_rate": 1,
        "net_total": 150,
        "tax_total": 15,
        "total": 165,
        "local_net_total": 150,
        "lines": lines,
    }


def test_1000_by_5_lands_inside_the_budget(env):
    records = [_document(n) for n in range(1000)]
    started = time.monotonic()
    res = env.push(records)
    elapsed = time.monotonic() - started

    assert res.status_code == 200, res.text[:500]
    summary = res.json()["summary"]
    assert summary["created"] == 1000, summary
    assert summary["failed"] == 0
    assert elapsed < BUDGET_SECONDS, f"{elapsed:.1f}s"
    assert (
        env.db.execute(
            text(
                "SELECT count(*) FROM integration_references "
                "WHERE entity_type = 'billing_documents' AND source_ref LIKE 'SRT_DB:IV:7%'"
            )
        ).scalar()
        == 1000
    )
    assert env.counts()["lines"] == 5000
