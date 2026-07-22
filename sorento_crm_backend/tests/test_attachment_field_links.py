"""Tests for the attachment field-linkage feature.

Covers:
* registry validation (`validate_field_keys` happy/sad paths and grouping).
* ``ProductResponse.field_attachments`` shape via Pydantic ``SimpleNamespace``
  (mirrors ``test_promotion_response_attachments.py``).
* ``AttachmentFieldLinkService.set_links`` idempotent diff and override
  semantics, against an in-memory SQLite session that creates only the
  ``attachment_field_links`` table (no JSONB / FK enforcement).
* ``AIExtractService._run_extract`` narrows the schema by ``field_subset``
  before prompting the LLM.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.models.attachment_field_link import AttachmentFieldLink
from app.services.attachment_field_link_service import AttachmentFieldLinkService
from app.services.field_linkage import (
    SUPPORTED_ENTITY_TYPES,
    field_keys_for,
    get_field_spec,
    get_field_specs,
    validate_field_keys,
)
from tests._pg_fixture import blank_session

# Parent attachment the linkage tests point at. Postgres enforces the
# attachment_field_links.attachment_id FK, so this row must exist.
_ATTACHMENT_ID = "00000000-0000-0000-0000-000000000a01"


# ---------------- Registry ------------------------------------------------


def test_registry_supports_four_entity_types():
    assert set(SUPPORTED_ENTITY_TYPES) == {
        "product",
        "promotion",
        "packing_list",
        "form",
    }


def test_registry_groups_dimensions_under_one_group_key():
    keys = field_keys_for("product")
    assert {"weight", "dimensions_length", "dimensions_width", "dimensions_height"} <= keys

    groups = {
        s.name: s.group_key for s in get_field_specs("product") if s.group_key
    }
    assert groups["dimensions_length"] == "dimensions"
    assert groups["dimensions_width"] == "dimensions"
    assert groups["dimensions_height"] == "dimensions"


def test_registry_units_are_canonical():
    assert get_field_spec("product", "weight").unit == "kg"
    assert get_field_spec("product", "dimensions_length").unit == "mm"
    assert get_field_spec("product", "warranty_months").unit == "months"


def test_validate_field_keys_splits_known_and_unknown():
    ok, unknown = validate_field_keys("product", ["weight", "bogus", "dimensions_length"])
    assert ok == ["weight", "dimensions_length"]
    assert unknown == ["bogus"]


def test_validate_field_keys_unknown_entity_returns_only_unknown():
    ok, unknown = validate_field_keys("not_a_table", ["weight"])
    assert ok == []
    assert unknown == ["weight"]


def test_validate_field_keys_dedupes_and_strips():
    ok, unknown = validate_field_keys("product", ["weight", " weight", "  ", None])  # type: ignore[list-item]
    assert ok == ["weight"]
    assert unknown == []


# ---------------- ProductResponse.field_attachments shape ----------------


def test_product_response_field_attachments_serializes_passthrough():
    """Ensures `field_attachments` round-trips when the service has already
    serialized the inner Attachment dicts. Pydantic should accept the dict
    verbatim and emit it under `field_attachments`."""
    from app.schemas.product import ProductResponse

    sample_attachment = {
        "id": "00000000-0000-0000-0000-000000000a01",
        "original_filename": "tech-spec.pdf",
        "stored_filename": "tech-spec.pdf",
        "file_path": "https://cdn/tech-spec.pdf",
        "file_size_bytes": 12345,
        "mime_type": "application/pdf",
        "uploaded_at": "2026-04-01T12:00:00",
        "created_at": "2026-04-01T12:00:00",
        "attachment_type": None,
        "full_directory_path": None,
        "access_levels": ["dealer", "end_user"],
    }

    product_ns = SimpleNamespace(
        id="prod-1",
        product_code="WC8038",
        product_name="Water Closet 8038",
        description=None,
        category_id="cat-1",
        brand_id=None,
        base_uom_id="uom-1",
        item_type=None,
        list_price=2274.0,
        cost_price=None,
        invoice_price=None,
        currency="MYR",
        weight=None,
        dimensions_length=None,
        dimensions_width=None,
        dimensions_height=None,
        warranty_months=None,
        has_serial_tracking=False,
        has_batch_tracking=False,
        reorder_level=None,
        reorder_quantity=None,
        is_active=True,
        is_discontinued=False,
        created_by=None,
        updated_by=None,
        created_at="2026-04-01T12:00:00",
        updated_at=None,
        category=None,
        brand=None,
        base_uom=None,
        field_attachments={
            "weight": [sample_attachment],
            "dimensions_length": [sample_attachment],
            "dimensions_width": [sample_attachment],
            "dimensions_height": [sample_attachment],
        },
    )

    payload = ProductResponse.model_validate(product_ns).model_dump()

    assert payload["field_attachments"] is not None
    assert set(payload["field_attachments"].keys()) == {
        "weight",
        "dimensions_length",
        "dimensions_width",
        "dimensions_height",
    }
    assert payload["field_attachments"]["weight"][0]["id"] == "00000000-0000-0000-0000-000000000a01"


def test_product_response_field_attachments_defaults_to_none():
    from app.schemas.product import ProductResponse

    product_ns = SimpleNamespace(
        id="prod-1",
        product_code="WC8038",
        product_name="Water Closet 8038",
        description=None,
        category_id="cat-1",
        brand_id=None,
        base_uom_id="uom-1",
        item_type=None,
        list_price=2274.0,
        cost_price=None,
        invoice_price=None,
        currency="MYR",
        weight=None,
        dimensions_length=None,
        dimensions_width=None,
        dimensions_height=None,
        warranty_months=None,
        has_serial_tracking=False,
        has_batch_tracking=False,
        reorder_level=None,
        reorder_quantity=None,
        is_active=True,
        is_discontinued=False,
        created_by=None,
        updated_by=None,
        created_at="2026-04-01T12:00:00",
        updated_at=None,
        category=None,
        brand=None,
        base_uom=None,
        field_attachments=None,
    )
    payload = ProductResponse.model_validate(product_ns).model_dump()
    assert payload["field_attachments"] is None


# ---------------- AttachmentFieldLinkService set_links ------------------


@pytest.fixture
def afl_session():
    """A blank Postgres schema with the one parent attachment seeded.

    Was in-memory SQLite with FK enforcement disabled so orphan
    ``attachment_field_links`` rows could be inserted. Postgres enforces the
    attachment_id FK, so instead of dropping integrity we seed the real parent
    ``attachments`` row the tests link to.
    """
    from app.models.resources import Attachment

    with blank_session() as s:
        s.add(
            Attachment(
                id=_ATTACHMENT_ID,
                original_filename="tech-spec.pdf",
                stored_filename="tech-spec.pdf",
                file_path="https://cdn/tech-spec.pdf",
            )
        )
        s.commit()
        yield s


def test_set_links_inserts_only_known_keys(afl_session):
    svc = AttachmentFieldLinkService(afl_session)
    keys = svc.set_links(
        "product",
        "prod-1",
        "00000000-0000-0000-0000-000000000a01",
        ["weight", "dimensions_length"],
    )
    afl_session.commit()
    assert sorted(keys) == ["dimensions_length", "weight"]
    rows = afl_session.query(AttachmentFieldLink).all()
    assert len(rows) == 2
    assert {r.field_key for r in rows} == {"weight", "dimensions_length"}


def test_set_links_rejects_unknown_field_key(afl_session):
    svc = AttachmentFieldLinkService(afl_session)
    with pytest.raises(Exception) as e:
        svc.set_links("product", "prod-1", "00000000-0000-0000-0000-000000000a01", ["weight", "bogus_field"])
    assert "bogus_field" in str(e.value)


def test_set_links_is_idempotent_and_diffs(afl_session):
    svc = AttachmentFieldLinkService(afl_session)
    svc.set_links("product", "prod-1", "00000000-0000-0000-0000-000000000a01", ["weight", "dimensions_length"])
    afl_session.commit()
    # Replace with a different set: keep weight, drop length, add height.
    svc.set_links(
        "product",
        "prod-1",
        "00000000-0000-0000-0000-000000000a01",
        ["weight", "dimensions_height"],
    )
    afl_session.commit()
    rows = afl_session.query(AttachmentFieldLink).all()
    assert {r.field_key for r in rows} == {"weight", "dimensions_height"}


def test_apply_template_to_row_uses_attachment_template(afl_session):
    """When override_keys=None, apply_template_to_row reads
    ``attachment.target_field_keys`` (and target_entity_type guard)."""
    svc = AttachmentFieldLinkService(afl_session)
    attachment_stub = SimpleNamespace(
        id="00000000-0000-0000-0000-000000000a01",
        target_entity_type="product",
        target_field_keys=["weight", "dimensions_length"],
    )
    keys = svc.apply_template_to_row(
        attachment_stub, "product", "prod-1"
    )
    afl_session.commit()
    assert sorted(keys) == ["dimensions_length", "weight"]


def test_apply_template_to_row_skips_when_target_type_mismatch(afl_session):
    """A product-targeted template must NOT fan out when linked to a
    promotion row."""
    svc = AttachmentFieldLinkService(afl_session)
    attachment_stub = SimpleNamespace(
        id="00000000-0000-0000-0000-000000000a01",
        target_entity_type="product",
        target_field_keys=["weight"],
    )
    keys = svc.apply_template_to_row(
        attachment_stub, "promotion", "promo-1"
    )
    afl_session.commit()
    assert keys == []
    assert afl_session.query(AttachmentFieldLink).count() == 0


def test_apply_template_to_row_override_replaces_template(afl_session):
    """An explicit override_keys=[...] REPLACES the template (does not union)."""
    svc = AttachmentFieldLinkService(afl_session)
    attachment_stub = SimpleNamespace(
        id="00000000-0000-0000-0000-000000000a01",
        target_entity_type="product",
        target_field_keys=["weight", "dimensions_length"],
    )
    keys = svc.apply_template_to_row(
        attachment_stub, "product", "prod-1", override_keys=["weight"]
    )
    afl_session.commit()
    assert keys == ["weight"]
    rows = afl_session.query(AttachmentFieldLink).all()
    assert {r.field_key for r in rows} == {"weight"}


def test_get_field_attachments_for_rows_short_circuits_on_empty_input(afl_session):
    """Empty input returns ``{}`` without ever touching the ``attachments``
    table (which doesn't exist in this minimal SQLite fixture)."""
    svc = AttachmentFieldLinkService(afl_session)
    assert svc.get_field_attachments_for_rows("product", []) == {}
    assert svc.get_field_attachments_for_rows("", ["prod-1"]) == {}


# ---------------- AIExtractService field_subset narrowing ----------------


def test_run_extract_narrows_schema_by_field_subset(monkeypatch):
    """``_run_extract`` should pass only the requested fields into
    ``_build_messages`` so the LLM doesn't waste tokens on unrelated keys."""
    from app.services.ai_extract.extract_service import (
        AIExtractService,
        ExtractFile,
    )
    from app.services.ai_extract import form_schema_registry

    # Force the registry-derived master.product_fields so we can use real keys.
    schema = form_schema_registry.get_form_schema("master.product_fields")
    assert any(s.name == "weight" for s in schema)
    assert any(s.name == "dimensions_length" for s in schema)

    captured: dict = {}

    class _FakeProvider:
        def chat(self, **kwargs):
            from app.services.llm_provider import ChatResult

            return ChatResult(
                content='{"weight": 12.5, "dimensions_length": 800}',
                prompt_tokens=10,
                completion_tokens=5,
                total_tokens=15,
            )

    def _resolve(self):
        return _FakeProvider(), "openai", "gpt-4o"

    def _capture_messages(self, form_key, schema, guidance):
        captured["names"] = [s.name for s in schema]
        return [{"role": "system", "content": "x"}, {"role": "user", "content": "y"}]

    def _no_image(self, files):
        return [object()]  # one ImagePart-equivalent

    def _no_log(self, **kwargs):
        return None

    monkeypatch.setattr(AIExtractService, "_resolve_provider", _resolve)
    monkeypatch.setattr(AIExtractService, "_build_messages", _capture_messages)
    monkeypatch.setattr(AIExtractService, "_render_files", _no_image)
    monkeypatch.setattr(AIExtractService, "_log_usage", _no_log)

    service = AIExtractService(db=None)  # type: ignore[arg-type]
    result = service._run_extract(  # type: ignore[attr-defined]
        "master.product_fields",
        [ExtractFile(filename="x.png", mime="image/png", data=b"\x89PNG")],
        field_subset=["weight"],
        user_id=None,
        portal_contact_id=None,
    )

    assert captured["names"] == ["weight"]
    assert result.values.get("weight") == 12.5
    # Filtered field should NOT leak into values.
    assert "dimensions_length" not in result.values
