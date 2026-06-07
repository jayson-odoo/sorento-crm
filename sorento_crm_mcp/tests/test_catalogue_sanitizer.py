import json

from sorento_crm_mcp.server import (
    _RESOURCE_ATTACHMENT_CATALOGUE_KEEP_KEYS,
    _sanitize_tool_response,
    _slim_resource_attachment_catalogue_rows,
)


def _raw_catalogue_row():
    return {
        "id": "att-1",
        "original_filename": "Sorento LITE @ DIY Catalog 2026.pdf",
        "stored_filename": "Sorento LITE  DIY Catalog 2026.pdf",
        "file_path": "https://cdn-sorento.com/catalogue/x.pdf?sig=abc",
        "file_size_bytes": 16016896,
        "mime_type": "application/pdf",
        "file_hash": "f7510de6",
        "entity_type": None,
        "description": None,
        "access_levels": ["sorento_office", "dealer"],
        "sort_order": None,
        "target_entity_type": None,
        "target_field_keys": None,
        "upload_batch_id": None,
        "uploaded_by_user": {"name": "Am", "email": "am@example.com"},
        "uploaded_at": "2026-05-15T03:18:25.004877",
        "created_at": "2026-05-15T03:18:25.004877",
        "is_deleted": False,
        "deleted_at": None,
        "deleted_by": None,
        "attachment_type": {"type_name": "Catalogue"},
        "entity_display_name": None,
        "linked_products": [],
        "linked_promotions": [],
        "linked_form": None,
        "linked_packing_lists": [],
    }


def _raw_response():
    return {
        "data": [_raw_catalogue_row()],
        "pagination": {"total": 1, "page": 1, "limit": 50},
        "empty": False,
        "fallback_used": False,
        "resolved_entities": None,
    }


def test_catalogue_rows_slimmed_to_keep_list():
    out = _slim_resource_attachment_catalogue_rows(_raw_response())
    row = out["data"][0]
    assert set(row) == _RESOURCE_ATTACHMENT_CATALOGUE_KEEP_KEYS
    assert row["stored_filename"] == "Sorento LITE  DIY Catalog 2026.pdf"
    assert row["file_path"].startswith("https://cdn-sorento.com/")
    assert row["attachment_type"] == {"type_name": "Catalogue"}


def test_catalogue_envelope_untouched():
    out = _slim_resource_attachment_catalogue_rows(_raw_response())
    assert out["pagination"] == {"total": 1, "page": 1, "limit": 50}
    assert out["empty"] is False
    assert out["fallback_used"] is False
    assert out["resolved_entities"] is None


def test_catalogue_end_to_end_sanitize():
    raw = json.dumps(_raw_response())
    out = json.loads(
        _sanitize_tool_response("crm_resource_attachments_catalogue", raw)
    )
    row = out["data"][0]
    for dropped in (
        "id",
        "original_filename",
        "file_size_bytes",
        "file_hash",
        "uploaded_by_user",
        "created_at",
        "is_deleted",
        "deleted_at",
        "deleted_by",
        "linked_products",
        "linked_promotions",
        "linked_form",
        "linked_packing_lists",
        "entity_display_name",
        "upload_batch_id",
        "target_entity_type",
        "target_field_keys",
        "sort_order",
        "entity_type",
        "description",
    ):
        assert dropped not in row
    assert row["mime_type"] == "application/pdf"
    assert row["access_levels"] == ["sorento_office", "dealer"]
    assert row["uploaded_at"] == "2026-05-15T03:18:25.004877"


def test_non_dict_rows_pass_through():
    out = _slim_resource_attachment_catalogue_rows({"data": ["oops"], "empty": True})
    assert out["data"] == ["oops"]
