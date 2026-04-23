"""Benchmark Tool-RAG top-k relevance for MCP tool selection."""
from __future__ import annotations

import argparse
import json

from app.api.v1.external.rag import _embed_query
from app.database import SessionLocal
from app.services.embedding_service import EmbeddingReadService


BENCHMARK_CASES = [
    {"query": "check incoming stock for SKU SRTKS6092-BL", "expected": ["crm_procurement_spo_allocations_grouped_by_shipment"]},
    {"query": "show promotion products for promo MIX01", "expected": ["crm_marketing_promotion_products_list"]},
    {"query": "download attachment metadata for product brochure", "expected": ["crm_resource_attachments_metadata"]},
    {"query": "list orders by customer and delivery date", "expected": ["crm_order_management_orders_list"]},
    {"query": "what workflow forms are available for submission", "expected": ["crm_workflow_forms_definitions_published_for_submission"]},
    {"query": "create purchase request form", "expected": ["create_purchase_request"]},
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark mcp_tool retrieval quality")
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()

    db = SessionLocal()
    try:
        svc = EmbeddingReadService(db)
        rows = []
        top3_hits = 0
        top5_hits = 0
        for case in BENCHMARK_CASES:
            vec = _embed_query(case["query"])
            picks = svc.search_tool_candidates(vec, query=case["query"], top_k=args.top_k, include_planned=True)
            names = [p["tool_name"] for p in picks]
            expected = case["expected"]
            hit3 = any(e in names[:3] for e in expected)
            hit5 = any(e in names[:5] for e in expected)
            top3_hits += int(hit3)
            top5_hits += int(hit5)
            rows.append(
                {
                    "query": case["query"],
                    "expected": expected,
                    "returned": names,
                    "hit_top3": hit3,
                    "hit_top5": hit5,
                }
            )
        total = len(BENCHMARK_CASES)
        print(
            json.dumps(
                {
                    "total": total,
                    "top3_hit_rate": round(top3_hits / total, 4) if total else 0.0,
                    "top5_hit_rate": round(top5_hits / total, 4) if total else 0.0,
                    "details": rows,
                },
                indent=2,
            )
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
