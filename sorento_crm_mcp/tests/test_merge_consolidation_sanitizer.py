"""Sanitizer + enrichment coverage for the consolidated (merged) MCP list tools.

- crm_marketing_promotions_list: header-only (row id dropped, header attachment
  internals scrubbed, filename kept) - products are NOT nested.
- crm_master_products_list: confidential cost_price/invoice_price dropped, nested
  attachments[] internal-stripped.
- enrich grouping: child rows nested under the correct parent id.
"""
import asyncio
import json

from sorento_crm_mcp.server import (
    _enrich_products_with_attachments,
    _sanitize_tool_response,
)


# --------------------------------------------------------------------------
# Sanitize half (synchronous)
# --------------------------------------------------------------------------
def test_promotions_list_header_only_keeps_pdf_drops_ids():
    raw = {
        "data": [
            {
                "id": "promo-1",
                "created_by": "user-uuid",
                "description": "Kitchen Sink Promo.pdf",
                "is_active": True,
                "attachments": [
                    {
                        "attachment": {
                            "id": "att-1",
                            "original_filename": "Kitchen Sink Promo.pdf",
                            "full_directory_path": "/internal/path",
                            "storage_provider": "r2",
                        }
                    }
                ],
            }
        ],
        "pagination": {"total": 1, "page": 1, "limit": 50},
    }
    out = json.loads(_sanitize_tool_response("crm_marketing_promotions_list", json.dumps(raw)))
    row = out["data"][0]
    # Row-level UUIDs gone; no products nested.
    assert "id" not in row
    assert "created_by" not in row
    assert "products" not in row
    # Header attachment internals stripped, but the deliverable filename stays.
    att = row["attachments"][0]["attachment"]
    assert att["original_filename"] == "Kitchen Sink Promo.pdf"
    assert "full_directory_path" not in att
    assert "storage_provider" not in att


def test_products_list_drops_confidential_and_strips_attachment_internals():
    raw = {
        "data": [
            {
                "id": "prod-1",
                "product_code": "SRTFC2044",
                "product_name": "Cistern",
                "list_price": 1200.0,
                "cost_price": 800.0,
                "invoice_price": 900.0,
                "attachments": [
                    {
                        "original_filename": "SRTFC2044.jpg",
                        "full_directory_path": "/internal",
                        "storage_provider": "s3",
                        "uploaded_by": "user-uuid",
                        "attachment_type": {"type_name": "Product Photos", "description": "noise"},
                    }
                ],
            }
        ],
        "pagination": {"total": 1, "page": 1, "limit": 50},
    }
    out = json.loads(_sanitize_tool_response("crm_master_products_list", json.dumps(raw)))
    row = out["data"][0]
    # Customer-facing price kept; confidential economics dropped.
    assert row["list_price"] == 1200.0
    assert "cost_price" not in row
    assert "invoice_price" not in row
    # Nested attachment internals scrubbed; filename + type_name kept.
    att = row["attachments"][0]
    assert att["original_filename"] == "SRTFC2044.jpg"
    assert "full_directory_path" not in att
    assert "storage_provider" not in att
    assert "uploaded_by" not in att
    assert att["attachment_type"]["type_name"] == "Product Photos"
    assert "description" not in att["attachment_type"]


# --------------------------------------------------------------------------
# Enrich half (async fan-out) - stub client returns canned child rows
# --------------------------------------------------------------------------
class _StubClient:
    def __init__(self, child_payload):
        self._child_payload = child_payload
        self.calls = []

    async def get(self, path, path_params=None, query=None, tool_name=None):
        self.calls.append((path, dict(query or {})))
        # First page returns the rows; subsequent pages return empty to stop paging.
        if (query or {}).get("page") in (None, "1"):
            return json.dumps(self._child_payload)
        return json.dumps({"data": []})


def test_enrich_products_groups_attachments_under_parent():
    parents = {"data": [{"id": "prod-1"}, {"id": "prod-2"}]}
    children = {
        "data": [
            {"product_id": "prod-1", "attachment": {"original_filename": "a.jpg"}},
            {"product_id": "prod-1", "attachment": {"original_filename": "b.jpg"}},
            {"product_id": "prod-2", "attachment": None},
        ]
    }
    client = _StubClient(children)
    # Nesting only happens when attachment_type_ids is supplied.
    out = json.loads(
        asyncio.run(_enrich_products_with_attachments(client, json.dumps(parents), {"attachment_type_ids": "type-1"}))
    )
    by_id = {r["id"]: r for r in out["data"]}
    assert [a["original_filename"] for a in by_id["prod-1"]["attachments"]] == ["a.jpg", "b.jpg"]
    # None attachment skipped → empty list.
    assert by_id["prod-2"]["attachments"] == []
    # The type filter is forwarded to the child fetch.
    assert client.calls[0][1].get("attachment_type_ids") == "type-1"


def test_enrich_products_no_attachments_without_type_ids():
    parents = {"data": [{"id": "prod-1"}]}
    client = _StubClient({"data": [{"product_id": "prod-1", "attachment": {"original_filename": "a.jpg"}}]})
    out = json.loads(
        asyncio.run(_enrich_products_with_attachments(client, json.dumps(parents), {}))
    )
    # No attachment_type_ids → no child fetch, no attachments key added.
    assert "attachments" not in out["data"][0]
    assert client.calls == []
