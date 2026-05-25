"""Unit tests for the AI extract service.

Cover:
- ``_attach_images_openai`` / ``_attach_images_anthropic`` shape per provider.
- ``OpenAIProvider.chat`` / ``AnthropicProvider.chat`` carry images through
  in the right native format.
- PDF render path emits one image per page.
- JSON response parsing tolerates fences.
- ``_validate_and_canonicalize`` resolves bound lookups via ``LookupResolverService``
  and drops unresolvable values.
- ``form_schema_registry`` exposes the portal.complaint schema with all FE fields.
"""
from __future__ import annotations

import base64
import json
import sys
import types
from typing import Any

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.services.ai_extract.extract_service import (
    AIExtractService,
    ExtractFile,
)
from app.services.ai_extract.form_schema_registry import (
    FORM_SCHEMAS,
    ExtractFieldSpec,
    get_form_schema,
)
from app.services.llm_provider import (
    AnthropicProvider,
    ImagePart,
    OpenAIProvider,
    _attach_images_anthropic,
    _attach_images_openai,
)


# ---- Helpers --------------------------------------------------------------


@pytest.fixture
def db_session():
    from app.database import Base
    from app.models.lookup import LookupSet, LookupOption, LookupOptionKeyword, LookupBinding

    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _enable_fk(dbapi_connection, _record):
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    Base.metadata.create_all(
        engine,
        tables=[
            LookupSet.__table__,
            LookupOption.__table__,
            LookupOptionKeyword.__table__,
            LookupBinding.__table__,
        ],
    )
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    s = Session()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def seeded_warranty(db_session):
    """Seed a `complaints_within_warranty` lookup with Yes/No/Not sure."""
    from app.schemas.lookup import (
        LookupKeywordIn,
        LookupOptionCreate,
        LookupSetCreate,
    )
    from app.services.lookup_option_service import LookupOptionService
    from app.services.lookup_set_service import LookupSetService

    s = LookupSetService(db_session).create(
        LookupSetCreate(set_key="complaints_within_warranty", name="Within warranty")
    )
    opt_yes = LookupOptionService(db_session).create(
        s.id,
        LookupOptionCreate(
            value="Yes",
            label="Yes",
            keywords=[LookupKeywordIn(keyword="under warranty")],
        ),
    )
    LookupOptionService(db_session).create(
        s.id, LookupOptionCreate(value="No", label="No")
    )
    LookupOptionService(db_session).create(
        s.id, LookupOptionCreate(value="Not sure", label="Not sure")
    )
    return s, opt_yes


# ---- Schema registry ------------------------------------------------------


def test_portal_complaint_schema_has_expected_fields():
    schema = get_form_schema("portal.complaint")
    names = [f.name for f in schema]
    expected = {
        "delivery_order_number",
        "customer_name",
        "contact_person",
        "contact_number",
        "customer_address",
        "customer_type",
        "complaint_date",
        "product_code",
        "product_type",
        "within_warranty",
        "defects_discovered",
        "complaint_type",
        "defect_description",
        "salesperson",
        "project_title",
    }
    assert expected.issubset(set(names))


def test_get_form_schema_unknown_raises():
    with pytest.raises(KeyError):
        get_form_schema("portal.does_not_exist")


def test_form_schemas_keys_namespaced():
    for k in FORM_SCHEMAS.keys():
        assert "." in k, f"form_key should be namespaced (e.g. portal.complaint), got {k!r}"


def test_portal_stock_inquiry_schema_has_quantity_no_do_number():
    """Stock inquiry has quantity (number) but NOT delivery_order_number —
    proves per-form field flexibility (the user's "complaint has DO number
    but stock inquiry doesn't" requirement)."""
    schema = get_form_schema("portal.stock_inquiry")
    names = {f.name for f in schema}
    assert "quantity" in names
    assert "delivery_date" in names
    assert "salesperson" in names
    assert "delivery_order_number" not in names
    assert "within_warranty" not in names
    qty = next(f for f in schema if f.name == "quantity")
    assert qty.kind == "number"


def test_portal_purchase_request_schema_has_no_warranty_or_do_number():
    schema = get_form_schema("portal.purchase_request")
    names = {f.name for f in schema}
    assert "expected_po_date" in names
    assert "external_reference" in names
    assert "delivery_order_number" not in names
    assert "within_warranty" not in names


def test_portal_sponsorship_schema_keeps_total_project_value_as_text():
    """total_project_value must stay 'text' so the LLM doesn't strip
    descriptive fragments like 'BULK ORDER EST RM1.6MIL'."""
    schema = get_form_schema("portal.sponsorship_form")
    fields = {f.name: f for f in schema}
    assert "delivery_address" in fields
    assert "sponsor_subject" in fields
    assert fields["total_project_value"].kind == "text"


@pytest.mark.parametrize(
    "form_key,customer_field,project_field",
    [
        ("portal.complaint", "customer_name", "project_title"),
        ("portal.stock_inquiry", "project_customer", "project_name"),
        ("portal.purchase_request", "customer_name", "project_title"),
        ("portal.sponsorship_form", "customer_name", "project_title"),
    ],
)
def test_customer_and_project_fields_have_disambiguating_guidance(
    form_key, customer_field, project_field
):
    fields = {f.name: f for f in get_form_schema(form_key)}
    cust = fields[customer_field]
    proj = fields[project_field]
    # Customer field disambiguates buyer vs supplier/project and carries examples.
    assert cust.examples, f"{form_key}.{customer_field} should provide examples"
    assert cust.note and "NOT" in cust.note
    # Project field tells the model it is not the customer company.
    assert proj.note and "NOT the customer" in proj.note


# ---- Image attachers ------------------------------------------------------


def test_attach_images_openai_appends_image_url_blocks():
    msgs = [
        {"role": "system", "content": "be terse"},
        {"role": "user", "content": "hi"},
    ]
    images = [
        ImagePart(mime="image/png", data_b64="AAAA"),
        ImagePart(mime="image/jpeg", data_b64="BBBB"),
    ]
    out = _attach_images_openai(msgs, images)
    assert out[0] == {"role": "system", "content": "be terse"}
    user = out[1]
    assert user["role"] == "user"
    blocks = user["content"]
    assert isinstance(blocks, list)
    assert blocks[0] == {"type": "text", "text": "hi"}
    assert blocks[1]["type"] == "image_url"
    assert blocks[1]["image_url"]["url"] == "data:image/png;base64,AAAA"
    assert blocks[2]["image_url"]["url"] == "data:image/jpeg;base64,BBBB"
    # original list untouched
    assert msgs[1]["content"] == "hi"


def test_attach_images_anthropic_uses_source_blocks():
    msgs = [{"role": "user", "content": "hi"}]
    images = [ImagePart(mime="image/png", data_b64="AAAA")]
    out = _attach_images_anthropic(msgs, images)
    blocks = out[0]["content"]
    assert blocks[0] == {"type": "text", "text": "hi"}
    assert blocks[1] == {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/png",
            "data": "AAAA",
        },
    }


def test_attach_images_creates_user_message_when_missing():
    out = _attach_images_openai([], [ImagePart("image/png", "AAAA")])
    assert len(out) == 1
    assert out[0]["role"] == "user"
    assert out[0]["content"][0]["type"] == "image_url"


# ---- Provider integration: kwargs propagation ----------------------------


class _StubMsg:
    def __init__(self, content: str | None = "{}", tool_calls: list[Any] | None = None):
        self.content = content
        self.tool_calls = tool_calls or []


class _StubChoice:
    def __init__(self, m: _StubMsg):
        self.message = m


class _StubUsage:
    def __init__(self, p: int, c: int):
        self.prompt_tokens = p
        self.completion_tokens = c
        self.total_tokens = p + c


class _StubCompletion:
    def __init__(self, m: _StubMsg, u: _StubUsage):
        self.choices = [_StubChoice(m)]
        self.usage = u


class _StubOpenAIClient:
    def __init__(self, api_key=None):
        self.api_key = api_key
        self.last_kwargs: dict[str, Any] | None = None

        class _Completions:
            def __init__(inner):
                inner._next = _StubCompletion(_StubMsg('{"customer_name":"ACME"}'), _StubUsage(11, 7))

            def create(inner, **kwargs):
                self.last_kwargs = kwargs
                return inner._next

        class _Chat:
            def __init__(inner):
                inner.completions = _Completions()

        class _Embeds:
            def create(inner, **kwargs):
                return types.SimpleNamespace(data=[types.SimpleNamespace(embedding=[0.0])])

        self.chat = _Chat()
        self.embeddings = _Embeds()


class _AntTextBlock:
    def __init__(self, text: str):
        self.type = "text"
        self.text = text


class _AntUsage:
    def __init__(self, i: int, o: int):
        self.input_tokens = i
        self.output_tokens = o


class _AntResponse:
    def __init__(self, content, usage):
        self.content = content
        self.usage = usage


class _StubAnthropicClient:
    def __init__(self, api_key=None):
        self.api_key = api_key
        self.last_kwargs: dict[str, Any] | None = None

        class _Messages:
            def __init__(inner):
                inner._next = _AntResponse(
                    [_AntTextBlock('{"customer_name":"ACME"}')],
                    _AntUsage(11, 7),
                )

            def create(inner, **kwargs):
                self.last_kwargs = kwargs
                return inner._next

        self.messages = _Messages()


def test_openai_chat_passes_response_format_and_image_blocks(monkeypatch):
    stub = _StubOpenAIClient()
    monkeypatch.setattr("openai.OpenAI", lambda api_key=None: stub)
    p = OpenAIProvider("k", default_model="gpt-4o-mini")
    p.chat(
        [{"role": "user", "content": "hi"}],
        images=[ImagePart("image/png", "AAAA")],
        response_format={"type": "json_object"},
        max_tokens=128,
    )
    kwargs = stub.last_kwargs
    assert kwargs is not None
    assert kwargs["response_format"] == {"type": "json_object"}
    user = kwargs["messages"][0]
    assert user["role"] == "user"
    assert isinstance(user["content"], list)
    assert any(b.get("type") == "image_url" for b in user["content"])
    assert any(b.get("type") == "text" for b in user["content"])


def test_anthropic_chat_passes_images_and_emulates_json_mode(monkeypatch):
    stub = _StubAnthropicClient()
    fake = types.SimpleNamespace(Anthropic=lambda api_key=None: stub)
    monkeypatch.setitem(sys.modules, "anthropic", fake)
    p = AnthropicProvider("k")
    p.chat(
        [
            {"role": "system", "content": "be terse"},
            {"role": "user", "content": "hi"},
        ],
        images=[ImagePart("image/png", "AAAA")],
        response_format={"type": "json_object"},
    )
    kwargs = stub.last_kwargs
    assert kwargs is not None
    sysprompt = kwargs["system"]
    assert "be terse" in sysprompt
    assert "JSON object" in sysprompt
    user_blocks = kwargs["messages"][0]["content"]
    assert any(b.get("type") == "image" for b in user_blocks)
    img = next(b for b in user_blocks if b.get("type") == "image")
    assert img["source"]["media_type"] == "image/png"
    assert img["source"]["data"] == "AAAA"


# ---- PDF rendering --------------------------------------------------------


def test_render_pdf_returns_one_image_per_page():
    fitz = pytest.importorskip("fitz")
    # Build a tiny 2-page PDF in memory.
    doc = fitz.open()
    for text in ("Page one", "Page two"):
        page = doc.new_page()
        page.insert_text((72, 72), text, fontsize=12)
    pdf_bytes = doc.tobytes()
    doc.close()

    svc = AIExtractService(db=None)  # type: ignore[arg-type] - render_pdf doesn't touch DB
    parts = svc._render_pdf(pdf_bytes, remaining=12)
    assert len(parts) == 2
    for p in parts:
        assert p.mime == "image/png"
        decoded = base64.b64decode(p.data_b64)
        assert decoded[:8] == b"\x89PNG\r\n\x1a\n"


def test_render_files_caps_at_pdf_max_pages():
    fitz = pytest.importorskip("fitz")
    doc = fitz.open()
    for _ in range(20):
        doc.new_page()
    pdf_bytes = doc.tobytes()
    doc.close()
    svc = AIExtractService(db=None)  # type: ignore[arg-type]
    files = [ExtractFile("big.pdf", "application/pdf", pdf_bytes)]
    parts = svc._render_files(files)
    assert 0 < len(parts) <= 12  # PDF_MAX_PAGES


# ---- Pasted text path -----------------------------------------------------


def test_collect_text_decodes_txt_uploads():
    svc = AIExtractService(db=None)  # type: ignore[arg-type]
    files = [
        ExtractFile("pasted-1.txt", "text/plain", b"  hello from paste  "),
        ExtractFile("note.TXT", "", "second\nblock".encode("utf-8")),
        ExtractFile("photo.png", "image/png", b"\x89PNG"),  # not text — ignored
    ]
    out = svc._collect_text(files)
    assert "hello from paste" in out
    assert "second\nblock" in out
    assert "PNG" not in out


def test_collect_text_empty_when_no_text_files():
    svc = AIExtractService(db=None)  # type: ignore[arg-type]
    assert svc._collect_text([ExtractFile("x.png", "image/png", b"\x89PNG")]) == ""


def test_build_messages_appends_pasted_text():
    svc = AIExtractService(db=None)  # type: ignore[arg-type]
    schema = [ExtractFieldSpec(name="customer_name", label="Customer", kind="text")]
    messages = svc._build_messages(
        "portal.complaint", schema, {}, has_line_items=False, pasted_text="ACME Corp order 42"
    )
    user = next(m for m in messages if m["role"] == "user")
    assert "ACME Corp order 42" in user["content"]


def test_build_messages_omits_text_section_when_blank():
    svc = AIExtractService(db=None)  # type: ignore[arg-type]
    schema = [ExtractFieldSpec(name="customer_name", label="Customer", kind="text")]
    messages = svc._build_messages("portal.complaint", schema, {}, has_line_items=False)
    user = next(m for m in messages if m["role"] == "user")
    assert "pasted the following text" not in user["content"]


# ---- JSON parsing ---------------------------------------------------------


def test_parse_json_strips_code_fences():
    svc = AIExtractService(db=None)  # type: ignore[arg-type]
    out = svc._parse_json('```json\n{"a": 1}\n```')
    assert out == {"a": 1}


def test_parse_json_finds_object_in_prose():
    svc = AIExtractService(db=None)  # type: ignore[arg-type]
    out = svc._parse_json('Sure! Here you go: {"a": 1} hope this helps')
    assert out == {"a": 1}


def test_parse_json_raises_on_non_object():
    from app.services.error_handler import AppException

    svc = AIExtractService(db=None)  # type: ignore[arg-type]
    with pytest.raises(AppException):
        svc._parse_json("[1,2,3]")


# ---- Validation / canonicalization ----------------------------------------


def test_validate_canonicalizes_lookup_via_keyword(db_session, seeded_warranty):
    schema = [
        ExtractFieldSpec(
            name="within_warranty",
            label="Within warranty",
            kind="lookup",
            set_key="complaints_within_warranty",
        ),
    ]
    svc = AIExtractService(db_session)
    parsed = {"within_warranty": "under warranty"}
    values, per_field = svc._validate_and_canonicalize(parsed, schema)
    assert values == {"within_warranty": "Yes"}
    assert per_field["within_warranty"].source == "lookup_resolved"


def test_validate_drops_unresolvable_lookup(db_session, seeded_warranty):
    schema = [
        ExtractFieldSpec(
            name="within_warranty",
            label="Within warranty",
            kind="lookup",
            set_key="complaints_within_warranty",
        ),
    ]
    svc = AIExtractService(db_session)
    parsed = {"within_warranty": "purple banana"}
    values, _ = svc._validate_and_canonicalize(parsed, schema)
    assert "within_warranty" not in values


def test_validate_do_number_coerces_string_to_list():
    svc = AIExtractService(db=None)  # type: ignore[arg-type]
    schema = [
        ExtractFieldSpec(name="delivery_order_number", label="DO", kind="do_number"),
    ]
    values, _ = svc._validate_and_canonicalize(
        {"delivery_order_number": "PS202603-0071, PO2509-013"},
        schema,
    )
    assert values["delivery_order_number"] == ["PS202603-0071", "PO2509-013"]


def test_extract_products_carries_unit_price_and_total():
    svc = AIExtractService(db=None)  # type: ignore[arg-type]
    parsed = {
        "products": [
            {
                "product_code": "ABC-1",
                "product_name": "Widget",
                "quantity": 2,
                "unit_price": 199.5,
                "total": 399.0,
                "notes": "with caps",
            },
            {
                # purchase_request style — no unit_price/total
                "product_code": "DEF-2",
                "quantity": 1,
                "notes": "spare",
            },
        ]
    }
    out = svc._extract_products(parsed)
    assert len(out) == 2
    assert out[0].product_code == "ABC-1"
    assert out[0].unit_price == 199.5
    assert out[0].total == 399.0
    assert out[0].quantity == 2.0
    assert out[1].unit_price is None
    assert out[1].total is None


def test_extract_products_coerces_strings_and_drops_garbage():
    svc = AIExtractService(db=None)  # type: ignore[arg-type]
    parsed = {
        "products": [
            {"product_code": "X", "quantity": "3", "unit_price": "10.5", "total": "31.5"},
            {"product_code": "Y", "unit_price": "n/a"},  # bad number → None
        ]
    }
    out = svc._extract_products(parsed)
    assert out[0].quantity == 3.0
    assert out[0].unit_price == 10.5
    assert out[0].total == 31.5
    assert out[1].unit_price is None


def test_validate_drops_empty_and_blank_fields():
    svc = AIExtractService(db=None)  # type: ignore[arg-type]
    schema = [
        ExtractFieldSpec(name="a", label="A", kind="text"),
        ExtractFieldSpec(name="b", label="B", kind="text"),
        ExtractFieldSpec(name="c", label="C", kind="text"),
    ]
    parsed = {"a": "value", "b": "", "c": None}
    values, _ = svc._validate_and_canonicalize(parsed, schema)
    assert values == {"a": "value"}


# End-to-end happy-path coverage (real DB + provider config) lives in the
# Playwright e2e spec at sorento_crm_frontend/e2e/portal-ai-extract.spec.ts.
# Keeping that path here would require Postgres-only tables (JSONB) which the
# unit suite does not stand up.
