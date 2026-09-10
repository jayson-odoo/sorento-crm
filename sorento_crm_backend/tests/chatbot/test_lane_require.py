"""Phase 2 RED tests for the attribute-first-asks lane, slices S1-S3 - work items B1,
B2, C4, E1, F1 (S1), D1-D3/F3 (S2), E2/F2 (S3).

`documentation/plans/chatbot/attribute-first-asks-acceptance-criteria.md` AC-1303,
AC-1304, AC-1315, AC-1316, AC-1318, AC-1319, AC-1320, AC-1323, AC-1326.
`documentation/plans/chatbot/PLAN-attribute-first-asks.md` - Shape, Work items
B1/B2/C4/E1/F1/D1-D3/F3/E2/F2.

Written BEFORE `app/services/chatbot/lanes/business/predicate.py` exists. An `ImportError`
naming that module is the expected red reason for the tests that import it directly;
`resolve_gate.py` / `gate.py` / `fetch.py` / `answer.py` are ported and DO exist today, so
tests against them fail on a wrong VALUE (missing dict key, wrong count, wrong text) rather
than an import - each test's own docstring says which.

Every module is imported LOCALLY inside its own test (not at file scope), so one missing
module can only fail the tests that actually depend on it, never the whole file's collection.
"""
from __future__ import annotations

import re
import uuid
from datetime import date
from typing import Any

import pytest

from tests._pg_fixture import blank_session


# --------------------------------------------------------------------------- #
# B1 - AC-1303: derive_require is a pure map off the parser's own output.       #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "parser_output, expected",
    [
        ({"intent_hint": "check_stock"}, {"stock": True}),
        ({"intent_hint": "check_incoming"}, {"incoming": True}),
        ({"intent_hint": "check_promotion"}, {"promotion": True}),
        (
            {
                "intent_hint": "check_product_attachment",
                "entities": [{"hint": "attachment_type", "raw": "cert"}],
            },
            {"certificate": True},
        ),
        (
            {
                "intent_hint": "check_product_attachment",
                "entities": [{"hint": "attachment_type", "raw": "photo"}],
            },
            {"attachment_type": "photo"},
        ),
        ({"intent_hint": "check_order"}, None),
        ({"intent_hint": None}, None),
    ],
)
def test_derive_require_maps_intents_and_entity_hints(parser_output, expected):
    from app.services.chatbot.lanes.business.predicate import derive_require

    assert derive_require(parser_output) == expected


# --------------------------------------------------------------------------- #
# B1/D2 - AC-1303 (S2 half): a scheme word is split off the SAME attachment_type   #
# raw mechanically - no message-text matching beyond `_CERT_RE`, no DB lookup at   #
# parse time (the `certificate_scheme` lookup set is read later, server-side, by   #
# `_leg_certificate`).                                                             #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("pps cert", {"certificate": {"scheme": "pps"}}),
        ("watermark certificate", {"certificate": {"scheme": "watermark"}}),
        # Already asserted by S1 (kept here so the whole scheme-splitting contract
        # lives in one parametrize): the raw IS the cert word alone, nothing left
        # over to name a scheme.
        ("cert", {"certificate": True}),
    ],
)
def test_derive_require_extracts_a_scheme_word_from_the_cert_raw(raw, expected):
    from app.services.chatbot.lanes.business.predicate import derive_require

    parser_output = {
        "intent_hint": "check_product_attachment",
        "entities": [{"hint": "attachment_type", "raw": raw}],
    }
    assert derive_require(parser_output) == expected


# --------------------------------------------------------------------------- #
# B2 - AC-1304 / AC-1322: resolve_entity_body gains require + predicate_words ONLY   #
# when derive_require returns something, every other key stays byte-identical. #
# --------------------------------------------------------------------------- #


def _ctx_for_intent(intent_hint: str | None) -> dict[str, Any]:
    """Two ctx dicts identical except `intent_hint` - domain_hint is held CONSTANT so
    the "every other key equal" assertion is meaningful (a varying domain would also
    vary `body["domain"]`, which is not what this test is about)."""
    return {
        "text": {"message": {"message": {"text": "check"}}},
        "contact": {"id": "1"},
        "parse": {
            "output": {
                "message_type": "business_query",
                "intent_hint": intent_hint,
                "domain_hint": "inventory",
                "match_mode": "or",
                "access_levels": [],
                "entities": [{"raw": "basin", "hint": "product"}],
            }
        },
    }


def test_resolve_entity_body_adds_require_and_predicate_words_only_when_derived():
    from app.services.chatbot.lanes.business.resolve_gate import resolve_entity_body

    body_stock = resolve_entity_body(_ctx_for_intent("check_stock"))
    body_order = resolve_entity_body(_ctx_for_intent("check_order"))

    assert body_stock.get("require") == {"stock": True}
    assert body_stock.get("predicate_words") == ["stock"]
    assert "require" not in body_order
    assert "predicate_words" not in body_order

    keys = (set(body_stock) | set(body_order)) - {"require", "predicate_words"}
    for key in keys:
        assert body_stock.get(key) == body_order.get(key), key


# --------------------------------------------------------------------------- #
# C4 - AC-1326: a qualifying predicate bypasses the ambiguity picker AND the    #
# product_attachment "subject did not resolve" block.                          #
# --------------------------------------------------------------------------- #


def _predicate_world() -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    """Three `spec_search`-tier product matches for an unresolved raw ("water tap"),
    plus a qualifying `predicate` block - the exact shape AC-1326 describes."""
    uuids = [str(uuid.uuid4()) for _ in range(3)]
    matches = [
        {
            "uuid": u,
            "entity_type": "product",
            "canonical_code": f"ZZT-BIDET-{i}",
            "match_tier": "spec_search",
        }
        for i, u in enumerate(uuids)
    ]
    resolver = {
        "resolutions": [{"token": "water tap", "resolved": False, "matches": matches}],
        "unresolved_tokens": ["water tap"],
        "predicate": {
            "qualifying_total": 3,
            "truncated": False,
            "unrecognized_terms": [],
            "require": {"certificate": True},
        },
    }
    parser = {
        "domain_hint": "product_attachment",
        "entities": [
            {"hint": "product", "raw": "water tap"},
            {"hint": "attachment_type", "raw": "cert"},
        ],
    }
    return resolver, parser, uuids


def test_gate_bypasses_ambiguity_and_subject_block_when_predicate_present():
    from app.services.chatbot.lanes.business.gate import run_gate

    resolver, parser, uuids = _predicate_world()

    out = run_gate(dict(resolver), parser=parser, resolver=resolver)

    assert out["require_specific"] is False, out.get("gate_reason")
    assert out["gate_passed"] is True, out.get("gate_reason")
    product_entities = [e for e in out["compatible_entities"] if e["entity_type"] == "product"]
    assert {e["uuid"] for e in product_entities} == set(uuids)


# --------------------------------------------------------------------------- #
# E1 - AC-1315: a HAS turn's fetch passes every qualifying id to the SAME domain #
# tool, limit=5.                                                                #
# --------------------------------------------------------------------------- #


def test_has_turn_fetch_passes_all_ids_to_the_domain_tool_with_limit_5():
    from app.services.chatbot.lanes.business import fetch
    from app.services.chatbot.lanes.business.gate import run_gate

    resolver, parser, uuids = _predicate_world()
    gate_out = run_gate(dict(resolver), parser=parser, resolver=resolver)

    args = fetch.entity_ids_transformer(
        {
            "entities": gate_out["compatible_entities"],
            "tool": "crm_master_product_attachments_list",
            "semantic_input": {"contact_id": "1", "space_id": "364817"},
            "predicate": resolver["predicate"],
        }
    )

    assert set(args.get("product_ids") or []) == set(uuids)
    assert args.get("limit") == 5


# --------------------------------------------------------------------------- #
# F1 - AC-1319: qualifying_total=0 enters the existing miss flow, naming the    #
# described set and the predicate.                                             #
# --------------------------------------------------------------------------- #


def test_zero_qualifying_enters_the_existing_miss_flow_naming_the_set():
    """Full lane run (the `_run_lane` pattern from `tests/chatbot/test_warehouse_entity.py`,
    reproduced locally rather than imported across files): three products named
    "* BIDET", none certified, real resolver + real gate, then the render function
    `not_found_error_message` (`answer.py`) named at PLAN work item F1.

    Today `derive_require` is not wired into `resolve_entity_body` at all, so no
    `require` ever reaches the resolver for this turn, the certificate leg never runs,
    and the rendered text carries none of the predicate-shaped copy this AC demands -
    the right red reason for a full-pipeline gap, not a single missing function.
    """
    from app.models.base import set_company_scope
    from app.models.company import Company
    from app.models.product import Product, ProductCategory, UnitOfMeasure
    from app.services.chatbot.lanes.business import resolve_gate
    from app.services.chatbot.lanes.business.answer import not_found_error_message
    from app.services.chatbot.lanes.business.services import ResolveGateServices
    from app.api.v1.system.references import ResolveReferenceRequest, resolve_reference_post
    from app.config import settings
    from tests._pg_fixture import blank_session, unique_code

    codes = ["ACC-BIDET", "CAB-BIDET", "SRT-BIDET"]

    with blank_session() as db:
        company = Company(id=str(uuid.uuid4()), code=unique_code("ZZTBD")[:50], name=unique_code("ZZTBD"))
        db.add(company)
        db.flush()
        category = ProductCategory(
            id=str(uuid.uuid4()),
            category_code=unique_code("CAT")[:50],
            category_name="ZZT bidet category",
            company_id=company.id,
        )
        uom = UnitOfMeasure(
            id=str(uuid.uuid4()), uom_code=unique_code("UOM")[:20], uom_name="Each", company_id=company.id
        )
        db.add_all([category, uom])
        db.flush()

        for code in codes:
            db.add(
                Product(
                    id=str(uuid.uuid4()),
                    product_code=code,
                    product_name=code,
                    description="BIDET SPRAY SET",
                    category_id=category.id,
                    base_uom_id=uom.id,
                    list_price=10,
                    is_active=True,
                    company_id=company.id,
                )
            )
        db.commit()

        set_company_scope(db, frozenset({company.id}))

        def resolve_entity(body: dict[str, Any]) -> dict[str, Any]:
            payload = {**body, "spec_fallback": False, "understand_phrase": False}
            principal = {"id": getattr(settings, "external_api_key_act_as_user_id", None)}
            return resolve_reference_post(
                ResolveReferenceRequest(**payload), current_user=principal, db=db
            )

        services = ResolveGateServices(
            access_types=lambda **_: [], resolve_entity=resolve_entity, probe=lambda **_: None
        )

        ctx = {
            "text": {"message": {"message": {"text": "which sorento bidet has cert"}}},
            "contact": {"id": "999"},
            "parse": {
                "output": {
                    "message_type": "business_query",
                    "intent_hint": "check_product_attachment",
                    "domain_hint": "product_attachment",
                    "match_mode": "or",
                    "access_levels": [],
                    "entities": [
                        {"raw": "bidet", "hint": "product"},
                        {"raw": "cert", "hint": "attachment_type"},
                    ],
                }
            },
        }

        out = resolve_gate.run(ctx, "resolve", {}, services=services, space_id="364817")
        parser = ctx["parse"]["output"]
        resolved = out.get("resolved") or {}
        gate = out.get("gate") or {}

        msg = not_found_error_message({}, parser=parser, resolved=resolved, gate=gate)
        text = (msg.get("escalate_message") or "").strip()

    assert text.startswith("Couldn't find"), text
    assert "certificate" in text.lower(), text
    for code in codes:
        assert code in text, text
    assert "did you mean" in text.lower() or "escalate" in text.lower(), text


# --------------------------------------------------------------------------- #
# F3 - AC-1321 (S2): a scheme miss names the schemes on file, not a generic "no  #
# certificate matched these".                                                   #
# --------------------------------------------------------------------------- #


def test_scheme_miss_reply_names_the_schemes_on_file():
    """AC-1321: "which item has watermark cert" against a register that holds PPS
    and SPAN (and an EMPTY `certificate_scheme` lookup set, so "watermark" resolves
    to nothing) must answer "no watermark certificates" and name both schemes on
    file, never the generic zero-qualifying miss.

    Full-pipeline red, deliberately: TODAY `derive_require` has not learned to split
    a scheme word off the SAME attachment_type raw (work item B1/D2 above) - "watermark
    cert" maps to a bare `{"certificate": True}`, so the certificate leg runs
    UNSCOPED, both seeded certified products qualify, and the reply this AC describes
    never renders at all (neither "no watermark certificates" nor "PPS"/"SPAN" appear
    anywhere in the text) - the correct red reason for a whole-pipeline gap spanning
    B1, D2 and the scheme-miss copy, not a single missing function.
    """
    from app.models.base import set_company_scope
    from app.models.certificate import Certificate, CertificateProduct
    from app.models.company import Company
    from app.models.lookup import LookupSet
    from app.models.product import Product, ProductCategory, UnitOfMeasure
    from app.services.chatbot.lanes.business import resolve_gate
    from app.services.chatbot.lanes.business.answer import not_found_error_message
    from app.services.chatbot.lanes.business.services import ResolveGateServices
    from app.api.v1.system.references import ResolveReferenceRequest, resolve_reference_post
    from app.config import settings
    from tests._pg_fixture import blank_session, unique_code

    with blank_session() as db:
        company = Company(id=str(uuid.uuid4()), code=unique_code("ZZTSC")[:50], name=unique_code("ZZTSC"))
        db.add(company)
        db.flush()
        category = ProductCategory(
            id=str(uuid.uuid4()),
            category_code=unique_code("CAT")[:50],
            category_name="ZZT scheme category",
            company_id=company.id,
        )
        uom = UnitOfMeasure(
            id=str(uuid.uuid4()), uom_code=unique_code("UOM")[:20], uom_name="Each", company_id=company.id
        )
        db.add_all([category, uom])
        db.flush()

        # D3: the migration ships the set EMPTY - the owner enters options later.
        db.add(
            LookupSet(
                id=str(uuid.uuid4()), tenant_id=None, set_key="certificate_scheme",
                name="Certificate Scheme", is_active=True,
            )
        )
        db.flush()

        for code, scheme in (("ZZT-CERT-PPS", "PPS"), ("ZZT-CERT-SPAN", "SPAN")):
            product = Product(
                id=str(uuid.uuid4()),
                product_code=code,
                product_name=code,
                description="ZZT CERTIFIED ITEM",
                category_id=category.id,
                base_uom_id=uom.id,
                list_price=10,
                is_active=True,
                company_id=company.id,
            )
            db.add(product)
            db.flush()
            cert = Certificate(
                id=str(uuid.uuid4()),
                scheme=scheme,
                certificate_number=unique_code("CERTNO")[:120],
                status="active",
                company_id=company.id,
            )
            db.add(cert)
            db.flush()
            db.add(CertificateProduct(id=str(uuid.uuid4()), certificate_id=cert.id, product_id=product.id))
        db.commit()

        set_company_scope(db, frozenset({company.id}))

        def resolve_entity(body: dict) -> dict:
            payload = {**body, "spec_fallback": False, "understand_phrase": False}
            principal = {"id": getattr(settings, "external_api_key_act_as_user_id", None)}
            return resolve_reference_post(
                ResolveReferenceRequest(**payload), current_user=principal, db=db
            )

        services = ResolveGateServices(
            access_types=lambda **_: [], resolve_entity=resolve_entity, probe=lambda **_: None
        )

        ctx = {
            "text": {"message": {"message": {"text": "which item has watermark cert"}}},
            "contact": {"id": "999"},
            "parse": {
                "output": {
                    "message_type": "business_query",
                    "intent_hint": "check_product_attachment",
                    "domain_hint": "product_attachment",
                    "match_mode": "or",
                    "access_levels": [],
                    "entities": [{"raw": "watermark cert", "hint": "attachment_type"}],
                }
            },
        }

        out = resolve_gate.run(ctx, "resolve", {}, services=services, space_id="364817")
        parser = ctx["parse"]["output"]
        resolved = out.get("resolved") or {}
        gate = out.get("gate") or {}

        msg = not_found_error_message({}, parser=parser, resolved=resolved, gate=gate)
        text = (msg.get("escalate_message") or "").strip()

    assert "no watermark certificates" in text.lower(), text
    assert "PPS" in text, text
    assert "SPAN" in text, text


# --------------------------------------------------------------------------- #
# S3 - AC-1316, AC-1318, AC-1320, AC-1323 (work items E2, F2).
#
# Written BEFORE `answer.build_set_header` / `answer.set_noun_for` exist. Every full
# lane-run test below is expected to fail for a WHOLE-PIPELINE reason, spelled out in
# its own docstring, the same convention `test_zero_qualifying_enters_the_existing_
# miss_flow_naming_the_set` (S1) and `test_scheme_miss_reply_names_the_schemes_on_file`
# (S2) above use: `answer.build_set_header` does not exist (ImportError on the two
# direct unit tests), AND `lanes/business/__init__.py::run_fetch`'s own trigger dict
# (built at "the read", ~line 327) never reads `gate.get("predicate")` at all - only
# `fetch.entity_ids_transformer`'s OWN `trig.get("predicate")` branch honours it
# (S1's own `test_has_turn_fetch_passes_all_ids_to_the_domain_tool_with_limit_5` proves
# the transformer alone, by calling it directly rather than through `run_fetch`). So
# through the real production seam a HAS turn's fetch never learns `require` /
# `qualifying_total` at all today: no `limit=5` is ever applied, and there is nothing
# for a header to be built FROM even once `build_set_header` exists. Both gaps are S3's
# own E2 work, not a separate slice's: `qualifying_total` and the actually-shown count
# must reconcile in the SAME header line, so threading the predicate through
# `run_fetch`'s trigger is what makes the header possible at all.
#
# CONTRACT CONTRADICTION (see `test_unknown_term_clarifies_with_nearest_names`'s own
# docstring for the full measurement): a bare CLASS word with no product entity
# ("which tap has cert") does not actually bind to class "Tap" anywhere in the current
# pipeline - `resolve_product_set` counts EVERY active product satisfying the `require`
# leg when neither `product_ids` nor a `filter_specs` clause describes the set, which is
# what happens here. The cert/stock counts the tests below assert (7, 3, 1, 2) are
# therefore right for the WRONG reason - every product this suite seeds happens to be a
# class-Tap product, so "no class filter" and "class = Tap" are indistinguishable. This
# is a real gap in AC-1306/C2 (S1), surfaced here because S3's header text is the first
# place a class NOUN is ever read back to the customer; it is not this slice's to fix,
# but the coder should know the qualifying_total these tests exercise is not proof the
# class scoping itself works.
# --------------------------------------------------------------------------- #


def _seed_registry(db) -> None:
    """The class / product_type vocabulary the described-set binding reads
    (`product_spec_search.filter_specs` -> `ProductSpecifications.values`), seeded
    exactly as `tests/test_product_predicate_service.py`'s own fixture does. No custom
    company is created and no `company_id` is ever passed below - every owned row relies
    on the `before_insert` auto-stamp against the single-company default test scope
    (`tests/conftest.py::_default_company_scope_for_tests`, Sorento), the same
    convention that file's fixture already uses successfully."""
    from app.services.product_class_signal import backfill_category_signals
    from app.services.product_spec_registry import seed_spec_registry

    backfill_category_signals(db)
    seed_spec_registry(db)


def _seed_category_and_uom(db) -> tuple[str, str]:
    from app.models.product import ProductCategory, UnitOfMeasure
    from tests._pg_fixture import unique_code

    category = ProductCategory(
        id=str(uuid.uuid4()), category_code=unique_code("CAT")[:50], category_name="ZZT category"
    )
    uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=unique_code("UOM")[:20], uom_name="Each")
    db.add_all([category, uom])
    db.flush()
    return category.id, uom.id


def _tap_product(db, *, category_id: str, uom_id: str, code: str | None = None):
    """A product whose DESCRIPTION contains the class-Tap trigger word ("TAP"), so
    `derive_for_code` - the same real spec-derivation pipeline `resolve_product_set`
    reads through `ProductSpecifications.values["class"]` - binds it to class "Tap"
    with no hand-built spec row (`product_spec_derivation.py`'s `("TAP", "Tap")` rule)."""
    from app.models.product import Product
    from app.services.product_spec_derivation import derive_for_code
    from tests._pg_fixture import unique_code

    code = code or unique_code("ZZTAP")[:50]
    row = Product(
        id=str(uuid.uuid4()),
        product_code=code,
        product_name=code,
        description=f"{code} CHROME BASIN TAP",
        category_id=category_id,
        base_uom_id=uom_id,
        list_price=10,
        is_active=True,
    )
    db.add(row)
    db.flush()
    derive_for_code(db, code)
    return row


def _certificate_for(db, *, product_id: str, valid_until=None, scheme: str = "ZZT-CERT"):
    from app.models.certificate import Certificate, CertificateProduct, CertificateRevision
    from tests._pg_fixture import unique_code

    cert = Certificate(
        id=str(uuid.uuid4()),
        scheme=scheme,
        certificate_number=unique_code("CERTNO")[:60],
        status="active",
    )
    db.add(cert)
    db.flush()
    if valid_until is not None:
        rev = CertificateRevision(
            id=str(uuid.uuid4()), certificate_id=cert.id, revision_no=1, valid_until=valid_until
        )
        db.add(rev)
        db.flush()
        cert.current_revision_id = rev.id
        db.flush()
    db.add(CertificateProduct(id=str(uuid.uuid4()), certificate_id=cert.id, product_id=product_id))
    db.flush()
    return cert


def _warehouse(db):
    from app.models.inventory import Warehouse
    from tests._pg_fixture import unique_code

    row = Warehouse(
        id=str(uuid.uuid4()),
        warehouse_code=unique_code("WH")[:50],
        warehouse_name="ZZT Warehouse",
        is_active=True,
    )
    db.add(row)
    db.flush()
    return row


def _stock_for(db, *, product_id: str, warehouse_id: str, on_hand: int = 10):
    from app.models.inventory import Stock

    row = Stock(
        id=str(uuid.uuid4()),
        product_id=product_id,
        warehouse_id=warehouse_id,
        quantity_on_hand=on_hand,
        quantity_reserved=0,
    )
    db.add(row)
    db.flush()
    return row


def _run_has_lane(db, ctx: dict[str, Any], *, fake_call_tool) -> tuple[dict[str, Any], dict[str, Any]]:
    """resolve -> gate -> fetch, the real production seams (`resolve_gate.run` then
    `lanes.business.run_fetch`), with only the MCP call stubbed. Returns
    `(resolve_gate_output, fetch_fragment)`."""
    from app.services.chatbot.lanes import business
    from app.services.chatbot.lanes.business import resolve_gate
    from app.services.chatbot.lanes.business.services import FetchServices, ResolveGateServices
    from app.api.v1.system.references import ResolveReferenceRequest, resolve_reference_post
    from app.config import settings

    def resolve_entity(body: dict[str, Any]) -> dict[str, Any]:
        payload = {**body, "spec_fallback": False, "understand_phrase": False}
        principal = {"id": getattr(settings, "external_api_key_act_as_user_id", None)}
        return resolve_reference_post(ResolveReferenceRequest(**payload), current_user=principal, db=db)

    services = ResolveGateServices(
        access_types=lambda **_: [], resolve_entity=resolve_entity, probe=lambda **_: None
    )
    out = resolve_gate.run(ctx, "resolve", {}, services=services, space_id="364817")

    fetch_services = FetchServices(mcp_call=fake_call_tool)
    fragment = business.run_fetch(out, services=fetch_services, dry_run=False, space_id="364817")
    return out, fragment


def _cert_fake_call_tool(db):
    """Mirrors `sorento_crm_mcp.presenters._product_attachments`' field labels for a
    certificate-bearing row (Product Code / Attachment Type / File Name / Certificate
    Number / Valid Until / Validity), over the seeded register - no MCP server, no
    network."""
    import json

    from app.models.certificate import Certificate, CertificateProduct, CertificateRevision
    from app.models.product import Product

    def fake_call_tool(name: str, args: dict[str, Any]) -> str:
        product_ids = list(args.get("product_ids") or [])
        rows = (
            db.query(Product, Certificate, CertificateRevision)
            .join(CertificateProduct, CertificateProduct.product_id == Product.id)
            .join(Certificate, Certificate.id == CertificateProduct.certificate_id)
            .outerjoin(CertificateRevision, CertificateRevision.id == Certificate.current_revision_id)
            .filter(Product.id.in_(product_ids))
            .order_by(Product.product_code)
            .all()
        )
        limit = args.get("limit")
        if isinstance(limit, int):
            rows = rows[:limit]
        items = []
        for product, cert, revision in rows:
            valid_until = revision.valid_until if revision is not None else None
            expired = bool(valid_until and valid_until < date.today())
            items.append(
                {
                    "title": product.product_code,
                    "fields": [
                        {"key": "product_code", "label": "Product Code", "value": product.product_code},
                        {"key": "attachment_type", "label": "Attachment Type", "value": "Certification"},
                        {"key": "file_name", "label": "File Name", "value": f"{product.product_code}.pdf"},
                        {
                            "key": "certificate_number",
                            "label": "Certificate Number",
                            "value": cert.certificate_number,
                        },
                        {
                            "key": "valid_until",
                            "label": "Valid Until",
                            "value": valid_until.isoformat() if valid_until else None,
                        },
                        {"key": "validity", "label": "Validity", "value": "Expired" if expired else "Valid"},
                    ],
                    "flags": {"expired": expired},
                }
            )
        return json.dumps(
            {
                "result_type": "product_attachments",
                "intro": "I have attached the file(s) below.",
                "items": items,
                "has_result": bool(items),
            }
        )

    return fake_call_tool


def _stock_fake_call_tool(db):
    """Mirrors `sorento_crm_mcp.presenters._stock`'s field labels (Product Code /
    Warehouse / System Location / Quantity On Hand); never emits a Sellable /
    Outstanding field, matching a contact with no `inventory.sellable` field reveal."""
    import json

    from app.models.inventory import Stock, Warehouse
    from app.models.product import Product

    def fake_call_tool(name: str, args: dict[str, Any]) -> str:
        product_ids = list(args.get("product_ids") or [])
        rows = (
            db.query(Product, Stock, Warehouse)
            .join(Stock, Stock.product_id == Product.id)
            .join(Warehouse, Warehouse.id == Stock.warehouse_id)
            .filter(Product.id.in_(product_ids))
            .order_by(Product.product_code)
            .all()
        )
        items = [
            {
                "title": product.product_code,
                "fields": [
                    {"key": "product_code", "label": "Product Code", "value": product.product_code},
                    {"key": "warehouse", "label": "Warehouse", "value": warehouse.warehouse_name},
                    {"key": "system_location", "label": "System Location", "value": warehouse.warehouse_code},
                    {"key": "quantity_on_hand", "label": "Quantity On Hand", "value": stock.quantity_on_hand},
                ],
                "flags": {},
            }
            for product, stock, warehouse in rows
        ]
        return json.dumps(
            {
                "result_type": "stock",
                "intro": "Stock details found for the requested products.",
                "items": items,
                "has_result": bool(items),
            }
        )

    return fake_call_tool


_ITEM_NUM_RE = re.compile(r"^\d+\.\s+")


def _block_for(text: str, code: str) -> str:
    """The item paragraph naming `code` ("*Product Code:* <code>" through the next
    blank line), position number stripped - two replies numbering the SAME product
    differently (1 vs 2 items on the page) must not fail this on the number alone."""
    for chunk in text.split("\n\n"):
        if f"*Product Code:* {code}" in chunk:
            lines = chunk.strip().split("\n")
            lines[0] = _ITEM_NUM_RE.sub("", lines[0])
            return "\n".join(lines)
    raise AssertionError(f"no item block for {code!r} in reply: {text!r}")


def _cert_ctx(text: str, entities: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "text": {"message": {"message": {"text": text}}},
        "contact": {"id": "999"},
        "parse": {
            "output": {
                "message_type": "business_query",
                "intent_hint": "check_product_attachment",
                "domain_hint": "product_attachment",
                "match_mode": "or",
                "access_levels": [],
                "entities": entities,
            }
        },
    }


@pytest.mark.parametrize(
    "qualifying_total, shown, set_noun, require, expected",
    [
        (1256, 5, "taps", {"certificate": True}, "1,256 taps have certificates. Showing 5."),
        (3, 3, "taps", {"certificate": True}, "3 taps have certificates."),
        (1, 1, "tap", {"certificate": True}, "1 tap has certificates."),
        (7, 5, "taps", {"stock": True}, "7 taps have stock. Showing 5."),
        (2, 2, "taps", {"attachment_type": "Product Photos"}, "2 taps have product photos."),
        (4, 4, "sinks", {"incoming": True}, "4 sinks have incoming stock."),
        (4, 4, "sinks", {"promotion": True}, "4 sinks have a promotion."),
        (
            9,
            5,
            "taps",
            {"certificate": True, "stock": True},
            "9 taps have certificates and stock. Showing 5.",
        ),
    ],
)
def test_build_set_header_strings(qualifying_total, shown, set_noun, require, expected):
    """AC-1316 (S3, work item E2): the header line, as a pure string function.

    RED: `answer.build_set_header` does not exist - `ImportError`.
    """
    from app.services.chatbot.lanes.business.answer import build_set_header

    assert build_set_header(qualifying_total, shown, set_noun, require) == expected


@pytest.mark.parametrize(
    "class_labels, expected",
    [
        (["Tap"], "taps"),
        (["Wash Basin"], "wash basins"),
        (["Water Closet"], "water closets"),
        ([], "products"),
        (["Tap", "Shower"], "products"),
    ],
)
def test_set_noun_for(class_labels, expected):
    """AC-1316 (S3, work item E2): the header's noun, off the described set's class
    label(s) - two classes fall back to the generic "products" (D5's set answer has no
    single noun to say).

    RED: `answer.set_noun_for` does not exist - `ImportError`.
    """
    from app.services.chatbot.lanes.business.answer import set_noun_for

    assert set_noun_for(class_labels) == expected


def test_set_answer_carries_the_header_and_shows_five():
    """AC-1316: a HAS turn's reply opens with "<qualifying_total> <set noun> have
    <predicate noun>. Showing <n>." before the existing certificate block, and the
    shown count must actually BE `n` - seven certified class-Tap products, no explicit
    product entity at all (the described set comes purely from the class binding on
    "which tap has cert", per AC-1306/C2).

    RED (see the module-section docstring above): today's reply's first line is the
    tool's own `intro` ("I have attached the file(s) below."), never a header, and the
    render shows all 7 products (no limit was ever threaded through `run_fetch`), not 5.
    """
    with blank_session() as db:
        _seed_registry(db)
        category_id, uom_id = _seed_category_and_uom(db)
        for _ in range(7):
            product = _tap_product(db, category_id=category_id, uom_id=uom_id)
            _certificate_for(db, product_id=product.id)
        db.commit()

        ctx = _cert_ctx(
            "which tap has cert", [{"raw": "cert", "hint": "attachment_type"}]
        )
        out, fragment = _run_has_lane(db, ctx, fake_call_tool=_cert_fake_call_tool(db))

        assert out.get("_exit_kind") == "continue", out.get("gate_reason")
        reply = (fragment.get("fetch") or {}).get("response") or ""

    lines = reply.splitlines()
    assert lines and lines[0] == "7 taps have certificates. Showing 5.", reply
    assert reply.count("*Product Code:*") == 5, reply


def test_set_answer_header_omits_showing_when_all_fit():
    """AC-1316: when `qualifying_total` is 5 or fewer the header omits "Showing" -
    three certified class-Tap products, all three render.

    RED: the header line is entirely absent from today's reply (see the module-section
    docstring above).
    """
    with blank_session() as db:
        _seed_registry(db)
        category_id, uom_id = _seed_category_and_uom(db)
        for _ in range(3):
            product = _tap_product(db, category_id=category_id, uom_id=uom_id)
            _certificate_for(db, product_id=product.id)
        db.commit()

        ctx = _cert_ctx(
            "which tap has cert", [{"raw": "cert", "hint": "attachment_type"}]
        )
        out, fragment = _run_has_lane(db, ctx, fake_call_tool=_cert_fake_call_tool(db))

        assert out.get("_exit_kind") == "continue", out.get("gate_reason")
        reply = (fragment.get("fetch") or {}).get("response") or ""

    lines = reply.splitlines()
    assert lines and lines[0] == "3 taps have certificates.", reply
    assert "Showing" not in reply, reply


def test_expired_only_certificate_still_counts_and_is_flagged():
    """AC-1318: "has cert" counts any ACTIVE register certificate regardless of date
    validity (D6) - one class-Tap product whose only certificate's current revision
    expired years ago still qualifies, and the render keeps flagging it exactly as
    today (`fetch._item_line`'s existing "(EXPIRED)" flag and the presenter's own
    "Validity: Expired" field - neither is new in this slice).

    RED: only the header line is missing (a single qualifying product never hits the
    limit-wiring gap the other tests above name), so this is the cleanest single-reason
    red of the set - `lines[0]` is the tool's `intro`, not "1 tap has certificates.".
    """
    with blank_session() as db:
        _seed_registry(db)
        category_id, uom_id = _seed_category_and_uom(db)
        product = _tap_product(db, category_id=category_id, uom_id=uom_id)
        _certificate_for(db, product_id=product.id, valid_until=date(2020, 1, 1))
        db.commit()

        ctx = _cert_ctx(
            "which tap has cert", [{"raw": "cert", "hint": "attachment_type"}]
        )
        out, fragment = _run_has_lane(db, ctx, fake_call_tool=_cert_fake_call_tool(db))

        assert out.get("_exit_kind") == "continue", out.get("gate_reason")
        reply = (fragment.get("fetch") or {}).get("response") or ""

    lines = reply.splitlines()
    assert lines and lines[0] == "1 tap has certificates.", reply
    assert "*Validity:* Expired" in reply, reply
    assert "(EXPIRED)" in reply, reply


def test_unknown_term_clarifies_with_nearest_names():
    """AC-1320 (work item F2): a HAS turn whose free term binds NO class /
    product_type / brand (AC-1301's own "water tap" example - "tap" alone is a class
    keyword, but the two-word phrase as a whole is not) must clarify with the nearest
    vocabulary, never answer the generic miss copy.

    RED, and NOT for the reason this docstring first guessed (kept below as a
    CONTRACT CONTRADICTION for the coder, per the tester brief): `unrecognized_terms`
    is EMPTY in production for this turn, not `["water tap"]`. Measured directly
    (`resolve_gate.run(...)["resolved"]["predicate"]` == `{"require": {"certificate":
    True}, "qualifying_total": 0, "truncated": False, "unrecognized_terms": []}`).
    Root cause: `app/api/v1/system/references.py`'s require branch calls
    `derive_search_inputs(db, query_text, specs=[], free_terms=[], ...)` and DELIBERATELY
    drops the function's own returned free terms (its comment: "merging that in fed the
    raw sentence to filter_specs's honesty check... reporting 'which kitchen sinks have
    stock' itself as unrecognized"), then calls `resolve_product_set(..., free_terms=
    payload.free_terms)` - and `resolve_entity_body` never populates a `free_terms` key
    on the resolve body at all, so this is `[]` on every chatbot turn. A bare class word
    like "tap" is bound only through `filter_specs`'s OWN `free_terms` argument
    (`resolve_classes_for_term`, exercised by `test_filter_specs_resolves_a_class_term`
    directly) - which this call path never reaches either. So for THIS turn `specs=[]`
    AND `free_terms=[]`, `described_given` is False, and `resolve_product_set` falls to
    its "nothing was given to describe the set" branch, which - for a `require`-only
    call with no described-set input at all - counts every ACTIVE product satisfying the
    leg with NO restriction (measured: `product_predicate_service.py` ~line 292-303,
    the `described = []` case skips the `query.filter(...)` call entirely). That is what
    also makes `test_set_answer_carries_the_header_and_shows_five` and its siblings above
    "pass" their product count today - every certified/stocked product THIS suite seeds
    happens to be a class-Tap product, so "count everything, no class filter" and "count
    only taps" are indistinguishable there. Here the world has ONLY class-Tap products
    too (by design - AC-1320 needs "tap" in the vocabulary for its "Did you mean"
    suggestion), so `qualifying_total` is 0 regardless, and the actual reply is
    "Couldn't find a water tap with a certificate. Would you like me to escalate to
    customer service team?" - AC-1319's S1 honest-zero copy, not AC-1320's. F2 cannot be
    "just" a new clarify-copy branch: it also has to make a bare class word reach
    `unrecognized_terms` at all (a content-word extraction over `query_text`, fed to
    `filter_specs`'s `free_terms` - NOT the raw derive_search_inputs echo the S1 comment
    above correctly refuses to use, which flags whole phrases like "which kitchen sinks
    have stock" as unrecognized whole-cloth).
    """
    with blank_session() as db:
        _seed_registry(db)
        category_id, uom_id = _seed_category_and_uom(db)
        _tap_product(db, category_id=category_id, uom_id=uom_id)
        _tap_product(db, category_id=category_id, uom_id=uom_id)
        db.commit()

        from app.services.chatbot.lanes.business import resolve_gate
        from app.services.chatbot.lanes.business.answer import not_found_error_message
        from app.services.chatbot.lanes.business.services import ResolveGateServices
        from app.api.v1.system.references import ResolveReferenceRequest, resolve_reference_post
        from app.config import settings

        def resolve_entity(body: dict[str, Any]) -> dict[str, Any]:
            payload = {**body, "spec_fallback": False, "understand_phrase": False}
            principal = {"id": getattr(settings, "external_api_key_act_as_user_id", None)}
            return resolve_reference_post(
                ResolveReferenceRequest(**payload), current_user=principal, db=db
            )

        services = ResolveGateServices(
            access_types=lambda **_: [], resolve_entity=resolve_entity, probe=lambda **_: None
        )

        ctx = _cert_ctx(
            "which water tap has cert",
            [
                {"raw": "water tap", "hint": "product"},
                {"raw": "cert", "hint": "attachment_type"},
            ],
        )
        out = resolve_gate.run(ctx, "resolve", {}, services=services, space_id="364817")
        parser = ctx["parse"]["output"]
        resolved = out.get("resolved") or {}
        gate = out.get("gate") or {}

        msg = not_found_error_message({}, parser=parser, resolved=resolved, gate=gate)
        text = (msg.get("escalate_message") or "").strip()

    assert "I don't know 'water tap' as a product type" in text, text
    assert "Did you mean" in text, text
    assert "Couldn't find" not in text, text


def test_stock_set_answer_matches_forward_block_for_a_dealer():
    """AC-1323: field-reveal gating is unchanged between a forward turn and a HAS
    turn - a dealer contact with NO field reveals (`ctx["access"]` absent, so
    `include_sellable` never sets and the render never carries a Sellable /
    Outstanding field either way) sees the SAME stock block for the same product on
    both. Two class-Tap products with stock in one warehouse; the forward turn types
    a real code (predicate skipped per AC-1305, byte-identical to today), the HAS turn
    asks "which tap has stock" (predicate runs, both qualify).

    RED: the two blocks already match today (nothing in this slice touches the block
    body), so the only failing assertion is the header - the HAS reply's first line is
    the tool's own `intro`, never "2 taps have stock.".
    """
    with blank_session() as db:
        _seed_registry(db)
        category_id, uom_id = _seed_category_and_uom(db)
        p1 = _tap_product(db, category_id=category_id, uom_id=uom_id)
        p2 = _tap_product(db, category_id=category_id, uom_id=uom_id)
        warehouse = _warehouse(db)
        _stock_for(db, product_id=p1.id, warehouse_id=warehouse.id)
        _stock_for(db, product_id=p2.id, warehouse_id=warehouse.id)
        db.commit()

        fake_call_tool = _stock_fake_call_tool(db)

        ctx_forward = {
            "text": {"message": {"message": {"text": f"{p1.product_code} stock"}}},
            "contact": {"id": "998"},
            "parse": {
                "output": {
                    "message_type": "business_query",
                    "intent_hint": "check_stock",
                    "domain_hint": "inventory",
                    "match_mode": "and",
                    "access_levels": [],
                    "entities": [
                        {
                            "raw": p1.product_code,
                            "hint": "product",
                            "canonical_code": p1.product_code,
                            "confident": True,
                        }
                    ],
                }
            },
        }
        ctx_has = {
            "text": {"message": {"message": {"text": "which tap has stock"}}},
            "contact": {"id": "998"},
            "parse": {
                "output": {
                    "message_type": "business_query",
                    "intent_hint": "check_stock",
                    "domain_hint": "inventory",
                    "match_mode": "or",
                    "access_levels": [],
                    "entities": [{"raw": "tap", "hint": "product"}],
                }
            },
        }

        out_forward, fragment_forward = _run_has_lane(db, ctx_forward, fake_call_tool=fake_call_tool)
        out_has, fragment_has = _run_has_lane(db, ctx_has, fake_call_tool=fake_call_tool)

        assert out_forward.get("_exit_kind") == "continue", out_forward.get("gate_reason")
        assert out_has.get("_exit_kind") == "continue", out_has.get("gate_reason")

        reply_forward = (fragment_forward.get("fetch") or {}).get("response") or ""
        reply_has = (fragment_has.get("fetch") or {}).get("response") or ""

    block_forward = _block_for(reply_forward, p1.product_code)
    block_has = _block_for(reply_has, p1.product_code)

    assert block_forward == block_has, (reply_forward, reply_has)
    assert "Sellable" not in reply_forward, reply_forward
    assert "Sellable" not in reply_has, reply_has
    lines_has = reply_has.splitlines()
    assert lines_has and lines_has[0] == "2 taps have stock.", reply_has
