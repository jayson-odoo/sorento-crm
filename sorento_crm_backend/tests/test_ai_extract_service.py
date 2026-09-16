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

from app.services.ai_extract.extract_service import (
    AIExtractService,
    ExtractFile,
    _form_has_line_items,
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
from tests._pg_fixture import blank_session


# ---- Helpers --------------------------------------------------------------


@pytest.fixture
def db_session():
    with blank_session() as s:
        yield s


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
        "quantity",
    }
    assert expected.issubset(set(names))


def test_get_form_schema_unknown_raises():
    with pytest.raises(KeyError):
        get_form_schema("portal.does_not_exist")


def test_form_schemas_keys_namespaced():
    for k in FORM_SCHEMAS.keys():
        assert "." in k, f"form_key should be namespaced (e.g. portal.complaint), got {k!r}"


def test_portal_stock_inquiry_schema_has_quantity_no_do_number():
    """Stock inquiry has quantity (number) but NOT delivery_order_number - 
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


# ---- portal.price_tag_request (D7, PLAN-price-tag-r7-request-ux AC-S6-4) --
#
# Review push-back accepted: the price tag request form has no header
# FIELDS to mirror - Customer is a select, not free text, and there is no
# sales order number input at all - only a LINE ITEMS section, so the
# schema is registered with an EMPTY field list. FORMS_WITH_LINE_ITEMS is
# what actually matters here.


def test_price_tag_request_schema_is_empty_no_fields_to_mirror():
    schema = get_form_schema("portal.price_tag_request")
    assert schema == []


def test_price_tag_request_has_line_items():
    assert _form_has_line_items("portal.price_tag_request") is True


def test_price_tag_request_key_is_namespaced_like_every_other_portal_form():
    assert "portal.price_tag_request" in FORM_SCHEMAS


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
        ExtractFile("photo.png", "image/png", b"\x89PNG"),  # not text - ignored
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


def test_fk_product_field_ignores_a_set_code_match_stays_raw(db_session, monkeypatch):
    """S6 (code review): a `fk_product` field (a stock inquiry / purchase
    request product code) resolves against PRODUCTS only - a set code that
    would match `_extract_products`'s own wider {"product", "product_set"}
    scope must stay raw here, since the field can only ever hold a product.

    Re-review finding: the original version of this test seeded the set
    under the SAME code it extracted (`SRTFKSET1` both stored and raw), so
    the canonical code a set match would have produced was byte-identical to
    the raw text kept on a miss - the assertion could not tell the two
    apart and stayed green even with `allowed_entity_types` dropped
    entirely. Stored as `SRT-FKSET1`, extracted as `SRTFKSET1` (the same
    dash-stripped separator normalization `test_ai_extract_resolver_match.py`
    exercises): a set match would answer the STORED form back, which
    disagrees with the raw text, so this only passes when the set is
    genuinely excluded. The `resolve_references` spy pins the actual guard
    (`allowed_entity_types == {"product"}`) directly, the same idiom
    `test_extract_products_calls_resolver_once_with_whole_code_list_exact_only`
    uses for the sales-order path's wider scope.
    """
    import uuid

    import app.services.ai_extract.extract_service as extract_service_mod
    from app.models.base import company_scope
    from app.models.product_set import ProductSet
    from app.services.entity_resolver import resolve_references as real_resolve

    company_id = "00000000-0000-0000-0000-000000000001"
    pset = ProductSet(
        id=str(uuid.uuid4()),
        company_id=company_id,
        set_code="SRT-FKSET1",
        name="ZZT Set",
        is_active=True,
    )
    db_session.add(pset)
    db_session.flush()

    calls: list[dict] = []

    def _spying_resolve_references(db_arg, codes, **kwargs):
        calls.append(kwargs)
        return real_resolve(db_arg, codes, **kwargs)

    monkeypatch.setattr(
        extract_service_mod, "resolve_references", _spying_resolve_references
    )

    schema = [
        ExtractFieldSpec(name="product_code", label="Product code", kind="fk_product"),
    ]
    svc = AIExtractService(db_session)
    with company_scope(db_session, frozenset({company_id})):
        values, per_field = svc._validate_and_canonicalize(
            {"product_code": "SRTFKSET1"}, schema
        )

    # The raw text, unchanged - a set match would have answered "SRT-FKSET1".
    assert values["product_code"] == "SRTFKSET1"
    assert per_field["product_code"].source == "llm"
    assert len(calls) == 1
    assert calls[0].get("allowed_entity_types") == frozenset({"product"})


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
                # purchase_request style - no unit_price/total
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


def test_resolve_provider_uses_the_configured_providers_own_default_model():
    """A provider with no model named gets ITS default, not another vendor's.

    The old two-branch fallback ("gpt-4o if openai else claude-sonnet-4-6") sent a
    Gemini-configured install an Anthropic model id.
    """
    from app.models.ai_assistant import AIAssistantConfig
    from app.services.llm_provider import GeminiProvider

    with blank_session() as db:
        db.add(
            AIAssistantConfig(
                provider="gemini", model="", api_key_ciphertext="ZZT-gemini-key"
            )
        )
        db.commit()

        provider, provider_name, model_name = AIExtractService(db)._resolve_provider()

        assert isinstance(provider, GeminiProvider)
        assert provider_name == "gemini"
        assert model_name == "gemini-2.5-flash"


def test_resolve_provider_reads_the_gemini_key_column_not_the_openai_env_key(monkeypatch):
    """A Gemini install keeps its key in the dedicated column.

    Reading only the generic ``api_key_ciphertext`` left that install with no
    key here and fell through to the OpenAI environment key, which was then
    posted to Google.
    """
    from app.config import settings as app_settings
    from app.models.ai_assistant import AIAssistantConfig
    from app.services.llm_provider import GeminiProvider

    monkeypatch.setattr(app_settings, "openai_api_key", "ZZT-openai-env-key", raising=False)
    monkeypatch.setattr(app_settings, "gemini_api_key", "", raising=False)

    with blank_session() as db:
        db.add(
            AIAssistantConfig(
                provider="gemini",
                model="",
                api_key_ciphertext="",
                gemini_api_key_ciphertext="ZZT-gemini-column-key",
            )
        )
        db.commit()

        provider, provider_name, _ = AIExtractService(db)._resolve_provider()

        assert isinstance(provider, GeminiProvider)
        assert provider_name == "gemini"
        assert provider.api_key == "ZZT-gemini-column-key"


# ---------------------------------------------------------------------------
# Per-form AI extract system prompts
# (PLAN-price-tag-currency-token-extract-prompt.md, owner ruling: the extract
# system prompt is registered ONE PER FORM KEY, not one shared key - a
# production override on the price tag form must not leak into any other
# form's extract.)
# ---------------------------------------------------------------------------


def _all_registered_form_keys() -> list[str]:
    from app.api.v1.master_data.ai_extract_field import _ENTITY_TO_FORM_KEY

    return list(FORM_SCHEMAS.keys()) + list(_ENTITY_TO_FORM_KEY.values())


def test_ac_b1_extract_prompt_key_names_the_form():
    from app.services.ai_extract.extract_service import extract_prompt_key

    assert (
        extract_prompt_key("portal.price_tag_request")
        == "ai_extract_portal_price_tag_request"
    )
    assert (
        extract_prompt_key("master.product_fields") == "ai_extract_master_product_fields"
    )


def test_ac_b1_every_registered_form_key_has_a_prompt_key():
    """AC-B1: PROMPT_KEYS holds one entry per registered form key - the 5
    `portal.*` keys in `form_schema_registry.py` plus the 4 `master.*` keys in
    `_ENTITY_TO_FORM_KEY` - each `active=True`, `variables=[]`, non-empty
    fallback."""
    from app.services.ai_extract.extract_service import extract_prompt_key
    from app.services.ai_prompt_registry import PROMPT_KEYS

    form_keys = _all_registered_form_keys()
    assert len(form_keys) == 9, "9 registered form keys (5 portal.* + 4 master.*)"

    for form_key in form_keys:
        key = extract_prompt_key(form_key)
        assert key in PROMPT_KEYS, f"missing PROMPT_KEYS entry for {key} ({form_key})"
        spec = PROMPT_KEYS[key]
        assert spec.active is True
        assert spec.variables == []
        assert spec.fallback().strip() != ""


def test_ac_b2_only_the_price_tag_forms_fallback_carries_rule_8():
    """AC-B2: only `ai_extract_portal_price_tag_request`'s fallback states rule
    (8) - the word REQUIRED and "every product code". The other 8 keep
    today's rules (1) to (7) verbatim, with no rule (8)."""
    from app.services.ai_extract.extract_service import extract_prompt_key
    from app.services.ai_prompt_registry import PROMPT_KEYS

    price_tag_key = extract_prompt_key("portal.price_tag_request")
    price_tag_text = PROMPT_KEYS[price_tag_key].fallback()
    assert "REQUIRED" in price_tag_text
    assert "every product code" in price_tag_text

    for form_key in _all_registered_form_keys():
        if form_key == "portal.price_tag_request":
            continue
        other_key = extract_prompt_key(form_key)
        other_text = PROMPT_KEYS[other_key].fallback()
        assert "REQUIRED" not in other_text, other_key
        assert "every product code" not in other_text, other_key
        # Rules (1) to (7) are today's shared text, unchanged, on every form.
        assert "(1) Omit any field you cannot find" in other_text, other_key
        assert (
            "(7) Never invent values. Never include explanations or prose."
            in other_text
        ), other_key


def test_ac_b3_build_messages_system_content_equals_get_prompt_for_that_form(
    db_session,
):
    from app.services.ai_extract.extract_service import extract_prompt_key
    from app.services.ai_prompt_registry import bust_cache, get_prompt

    bust_cache()
    svc = AIExtractService(db=db_session)
    schema = [ExtractFieldSpec(name="customer_name", label="Customer", kind="text")]

    messages = svc._build_messages("portal.complaint", schema, {}, has_line_items=False)
    system = next(m for m in messages if m["role"] == "system")

    assert system["content"] == get_prompt(
        db_session, extract_prompt_key("portal.complaint")
    ).text


def test_ac_b3_an_override_on_the_price_tag_form_does_not_leak_into_another_form(
    db_session,
):
    """AC-B3: a production-label override seeded on
    `ai_extract_portal_price_tag_request` changes what THAT form's extract
    sends, and a `portal.purchase_request` build must not pick it up - each
    form owns its own key."""
    from app.services.ai_extract.extract_service import extract_prompt_key
    from app.services.ai_prompt_registry import bust_cache
    from app.services.ai_prompt_seed import seed_prompt_registry
    from app.services.ai_prompt_service import AIPromptService

    seed_prompt_registry(db_session.get_bind())
    bust_cache()

    price_tag_key = extract_prompt_key("portal.price_tag_request")
    marker = "ZZT OVERRIDE FOR THE PRICE TAG FORM ONLY"
    svc = AIPromptService(db_session)
    saved = svc.save_version(
        price_tag_key, template=marker, commit_message="zzt test override", user_id=None
    )
    svc.set_label(
        price_tag_key, label="production", version_id=saved["id"], user_id=None
    )
    bust_cache()

    extract_svc = AIExtractService(db=db_session)
    schema = [ExtractFieldSpec(name="customer_name", label="Customer", kind="text")]

    price_tag_messages = extract_svc._build_messages(
        "portal.price_tag_request", schema, {}, has_line_items=True
    )
    other_messages = extract_svc._build_messages(
        "portal.purchase_request", schema, {}, has_line_items=True
    )

    price_tag_system = next(m for m in price_tag_messages if m["role"] == "system")
    other_system = next(m for m in other_messages if m["role"] == "system")

    assert price_tag_system["content"] == marker
    assert other_system["content"] != marker


def test_ac_b4_line_items_clause_has_no_optionally_and_references_rule_8_for_price_tag(
    db_session,
):
    svc = AIExtractService(db=db_session)
    schema = [ExtractFieldSpec(name="customer_name", label="Customer", kind="text")]

    messages = svc._build_messages(
        "portal.price_tag_request", schema, {}, has_line_items=True
    )
    user = next(m for m in messages if m["role"] == "user")

    assert "Optionally" not in user["content"]
    assert "rule (8)" in user["content"] or "rule 8" in user["content"]


def test_ac_b4_line_items_clause_for_other_line_item_forms_drops_optionally_but_not_rule_8(
    db_session,
):
    """A line-items form that is NOT the price tag one loses "Optionally" too
    (D3 wording change applies to every line-items clause), but has no reason
    to name rule (8) - that rule only exists on the price tag form's own
    prompt."""
    svc = AIExtractService(db=db_session)
    schema = [ExtractFieldSpec(name="customer_name", label="Customer", kind="text")]

    messages = svc._build_messages(
        "portal.purchase_request", schema, {}, has_line_items=True
    )
    user = next(m for m in messages if m["role"] == "user")

    assert "Optionally" not in user["content"]
    assert "rule (8)" not in user["content"]
    assert "rule 8" not in user["content"]


def test_ac_b4_a_form_with_no_line_items_still_forbids_the_products_array():
    svc = AIExtractService(db=None)  # type: ignore[arg-type]
    schema = [ExtractFieldSpec(name="customer_name", label="Customer", kind="text")]

    messages = svc._build_messages(
        "portal.stock_inquiry", schema, {}, has_line_items=False
    )
    user = next(m for m in messages if m["role"] == "user")

    assert "Do NOT include a top-level" in user["content"]
    assert "products" in user["content"]
