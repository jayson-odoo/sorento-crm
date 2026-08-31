"""S2: one code resolver, shared by attachment linking and promotion creation.

The two paths disagree TODAY, before product sets enter the picture:

- `product_attachments._resolve_product_codes` treats a code as a SUBSTRING and
  returns every match, deliberately.
- `promotions._resolve_product_codes` does EXACT match with a `+`-split fallback.

So the same flyer code can link an attachment and fail to create a promotion.
That is a live defect, and it is why this slice replaces both with one function
rather than teaching each of them about sets separately.

Set expansion sits BETWEEN exact and substring, so a set code cannot be shadowed
by an accidental substring hit on some unrelated product.

UAC group F. Plan: `documentation/plans/master-data/PLAN-product-sets.md` section 5.
"""
from __future__ import annotations

import os
import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from fastapi import HTTPException

from app.api.v1.external.product_attachments import (
    _link_attachment_to_products_bulk,
    create_product_attachment,
)
from app.api.v1.external.promotions import create_promotion
from app.database import SessionLocal, engine
from app.models.company import Company
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.product_set import ProductSet, ProductSetMember
from app.models.resources import Attachment
from app.schemas.external.attachments import ProductAttachmentLinkRequestAny
from app.schemas.external.marketing import (
    PromotionHeader,
    PromotionProductItem,
    PromotionRequest,
)
from app.services.company_scope import company_scope, register_company_scope_listeners
from app.services.product_code_resolution import resolve_codes_to_products

register_company_scope_listeners()

pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_LIVE_DB_TESTS") == "1",
    reason="SKIP_LIVE_DB_TESTS=1",
)

# Distinctive enough that no real catalogue row can collide with a substring probe.
STEM = "ZZTPS"


def _uid(stem: str) -> str:
    return f"ZZT-{stem}-{uuid.uuid4().hex[:8]}"


@pytest.fixture()
def db() -> Session:
    """A session whose writes are DISCARDED, even when the code under test commits.

    `SessionLocal()` + `begin_nested()` is not enough and it silently leaks: the
    service calls `db.commit()`, which commits the OUTER transaction rather than
    releasing a savepoint, so the fixture's rollback has nothing left to undo and
    every ZZT row lands in the shared database for good. That is what happened
    here - 99 sets, 407 products and 204 companies had to be swept back out.

    Binding to a connection that already holds a transaction, with
    `join_transaction_mode="create_savepoint"`, is what makes a committing test
    safe: its commits land on a savepoint inside the outer transaction, visible
    to the test and to the code under it, and the outer rollback still discards
    everything. Same approach as `tests/_pg_fixture.blank_session`.
    """
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        with company_scope(session, None):
            yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture()
def world(db: Session):
    """One 8608-shaped family per company, with codes nothing real can match.

    `<STEM>WCX8608<n>` pedestal, `<STEM>WCY8608<n>` cistern, `<STEM>WC8608<n>-SC`
    seat cover, and the set code `<STEM>WC8608<n>-RL` that names all three and is
    NOT itself a product - which is the entire problem.
    """
    tag = uuid.uuid4().hex[:6].upper()
    category = ProductCategory(
        id=str(uuid.uuid4()), category_code=_uid("cat")[:50], category_name=_uid("cat")
    )
    uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=_uid("u")[:20], uom_name=_uid("uom"))
    db.add_all([category, uom])
    db.flush()

    built = {}
    for key in ("a", "b"):
        company = Company(id=str(uuid.uuid4()), name=_uid(f"co-{key}"), code=_uid(f"C{key}")[:20])
        db.add(company)
        db.flush()

        def product(code: str, price: str) -> Product:
            row = Product(
                id=str(uuid.uuid4()),
                product_code=code,
                product_name=code,
                category_id=category.id,
                base_uom_id=uom.id,
                list_price=Decimal(price),
                company_id=company.id,
            )
            db.add(row)
            db.flush()
            return row

        pedestal = product(f"{STEM}WCX8608{tag}", "1180.00")
        cistern = product(f"{STEM}WCY8608{tag}", "0.00")
        seat = product(f"{STEM}WC8608{tag}-SC", "85.00")

        product_set = ProductSet(
            id=str(uuid.uuid4()),
            set_code=f"{STEM}WC8608{tag}-RL",
            name=_uid("set"),
            company_id=company.id,
        )
        db.add(product_set)
        db.flush()
        for index, member in enumerate((pedestal, cistern, seat)):
            db.add(
                ProductSetMember(
                    id=str(uuid.uuid4()),
                    product_set_id=product_set.id,
                    product_id=member.id,
                    quantity=Decimal("1"),
                    contributes_to_price=(index == 0),
                    sort_order=index,
                )
            )
        db.flush()
        built[key] = {
            "company": company,
            "set": product_set,
            "pedestal": pedestal,
            "cistern": cistern,
            "seat": seat,
        }
    return built


def _codes(result) -> set[str]:
    return {match.product.product_code for match in result.matches}


def _resolve_in(db: Session, company, codes, allow_prefix: bool = False):
    """Resolve the way production does: inside exactly one company's scope.

    Both companies carry the same product codes - that is true of the real
    catalogue, where every code exists once under Sorento and once under Mocha -
    so an unscoped resolve legitimately returns two rows per code. The external
    paths are always scoped (the attachment pins the session to its own company),
    and these tests say so rather than asserting against an artificial
    all-companies read.

    ``allow_prefix`` defaults to False, same as ``resolve_codes_to_products``
    itself (tier 5 is OPT-IN): a caller exercising the prefix tier passes
    ``True`` explicitly, the same way the attachment-link path does.
    """
    with company_scope(db, frozenset({str(company.id)})):
        return resolve_codes_to_products(db, codes, allow_prefix=allow_prefix)


# ------------------------------------------------------------------ the tiers


def test_ac_f2_a_set_code_resolves_to_every_member(db: Session, world):
    """AC-F.2 - the code on the flyer names three SKUs, and all three are linked."""
    a = world["a"]
    result = _resolve_in(db, a["company"], [a["set"].set_code])

    assert _codes(result) == {
        a["pedestal"].product_code,
        a["cistern"].product_code,
        a["seat"].product_code,
    }
    assert result.unmatched == []


def test_ac_f3_a_set_expansion_names_the_set_that_produced_it(db: Session, world):
    """AC-F.3 - provenance, so these links can be found and cleaned up later."""
    a = world["a"]
    result = _resolve_in(db, a["company"], [a["set"].set_code])

    assert {m.product_set_id for m in result.matches} == {a["set"].id}
    assert {m.via for m in result.matches} == {"product_set"}


def test_ac_f4_an_ordinary_code_carries_no_set_provenance(db: Session, world):
    """AC-F.4 - null set id is what distinguishes a human link from a fan-out."""
    a = world["a"]
    result = _resolve_in(db, a["company"], [a["cistern"].product_code])

    assert _codes(result) == {a["cistern"].product_code}
    assert [m.product_set_id for m in result.matches] == [None]
    assert [m.via for m in result.matches] == ["exact"]


def test_an_exact_product_code_beats_a_set_that_would_also_match(db: Session, world):
    """A real product wins its own code. Sets fill a gap; they do not shadow rows."""
    a = world["a"]
    # A set deliberately code-named after an existing product, which is a data
    # defect but must not silently redirect that product's own code.
    db.add(
        ProductSet(
            id=str(uuid.uuid4()),
            set_code=a["cistern"].product_code,
            name=_uid("shadow"),
            company_id=a["company"].id,
        )
    )
    db.flush()

    result = _resolve_in(db, a["company"], [a["cistern"].product_code])
    assert _codes(result) == {a["cistern"].product_code}
    assert [m.via for m in result.matches] == ["exact"]


def test_a_set_code_is_not_shadowed_by_a_substring_hit(db: Session, world):
    """Set expansion sits BEFORE substring, or a longer product code steals the set.

    `<set>-RL` is a substring of `<set>-RL-200`, so a substring-first resolver
    would answer with that one unrelated product instead of the set's members.
    """
    a = world["a"]
    decoy = Product(
        id=str(uuid.uuid4()),
        product_code=f"{a['set'].set_code}-200",
        product_name="decoy",
        category_id=a["pedestal"].category_id,
        base_uom_id=a["pedestal"].base_uom_id,
        list_price=Decimal("1.00"),
        company_id=a["company"].id,
    )
    db.add(decoy)
    db.flush()

    result = _resolve_in(db, a["company"], [a["set"].set_code])
    assert decoy.product_code not in _codes(result)
    assert _codes(result) == {
        a["pedestal"].product_code,
        a["cistern"].product_code,
        a["seat"].product_code,
    }


def test_substring_still_answers_a_partial_code(db: Session, world):
    """The attachments path's deliberate behaviour survives: a code is a substring.

    "WC7601 names MWC7601-RL-S12, IBWC7601-RL-S10 and every other product
    carrying it", and every match is returned because taking one arbitrarily left
    the rest silently uncovered.
    """
    a = world["a"]
    stem = a["pedestal"].product_code[:-2]  # a partial nobody holds exactly
    result = _resolve_in(db, a["company"], [stem])

    assert a["pedestal"].product_code in _codes(result)
    assert all(m.via == "substring" for m in result.matches)


def test_ac_f7_the_plus_split_fallback_survives(db: Session, world):
    """AC-F.7 - promotions' `A+B` behaviour must not be lost in the merge."""
    a = world["a"]
    combined = f"{a['pedestal'].product_code} + {a['seat'].product_code}"
    result = _resolve_in(db, a["company"], [combined])

    assert _codes(result) == {a["pedestal"].product_code, a["seat"].product_code}
    assert all(m.via == "plus_split" for m in result.matches)


def test_ac_f6_a_code_naming_nothing_is_reported_not_dropped(db: Session, world):
    """AC-F.6 - silence is the failure this whole feature exists to remove."""
    result = resolve_codes_to_products(db, ["ZZT-NO-SUCH-CODE-AT-ALL"])
    assert result.matches == []
    assert result.unmatched == ["ZZT-NO-SUCH-CODE-AT-ALL"]


def test_blank_and_duplicate_codes_are_absorbed(db: Session, world):
    """A caller passing the same code twice gets one answer, not two links."""
    a = world["a"]
    result = _resolve_in(
        db, a["company"], [a["cistern"].product_code, "  ", a["cistern"].product_code, ""]
    )
    assert len(result.matches) == 1
    assert result.unmatched == []


def test_a_set_code_is_matched_case_and_space_insensitively(db: Session, world):
    """n8n reads codes off a PDF, so the casing and spacing are whatever printed."""
    a = world["a"]
    scruffy = f" {a['set'].set_code.lower()} "
    result = _resolve_in(db, a["company"], [scruffy])
    assert len(result.matches) == 3


# --------------------------------------------------- tier 5: prefix (S1, R7)
#
# `PLAN-shared-brand-attachments.md` S1: n8n reads a certificate and returns a
# FAMILY description ("SRTBV - BRASS BALL VALVE"), not a real product code. The
# family here is named for that real defect but built from `ZZT-` codes so
# nothing in the real catalogue can collide with a prefix probe.


@pytest.fixture()
def srtbv(db: Session):
    """`ZZT-SRTBV110-DIY` .. `ZZT-SRTBV180-DIY` plus `ZZT-SRTBVB8013` - the same
    shape as the real certificate family, 9 members, one company."""
    category = ProductCategory(
        id=str(uuid.uuid4()), category_code=_uid("cat")[:50], category_name=_uid("cat")
    )
    uom = UnitOfMeasure(id=str(uuid.uuid4()), uom_code=_uid("u")[:20], uom_name=_uid("uom"))
    company = Company(id=str(uuid.uuid4()), name=_uid("co"), code=_uid("C")[:20])
    db.add_all([category, uom, company])
    db.flush()

    def product(code: str) -> Product:
        row = Product(
            id=str(uuid.uuid4()),
            product_code=code,
            product_name=code,
            category_id=category.id,
            base_uom_id=uom.id,
            list_price=Decimal("1.00"),
            company_id=company.id,
        )
        db.add(row)
        db.flush()
        return row

    codes = [f"ZZT-SRTBV{n}-DIY" for n in range(110, 181, 10)] + ["ZZT-SRTBVB8013"]
    members = [product(code) for code in codes]
    return {"company": company, "category": category, "uom": uom, "members": members, "codes": set(codes)}


def test_ac_a1_a_family_head_resolves_via_prefix(db: Session, srtbv):
    """AC-A1 - all 9 members, ordered by product_code, nothing unmatched."""
    result = _resolve_in(
        db, srtbv["company"], ["ZZT-SRTBV - BRASS BALL VALVE"], allow_prefix=True
    )

    assert _codes(result) == srtbv["codes"]
    assert all(m.via == "prefix" for m in result.matches)
    ordered = [m.product.product_code for m in result.matches]
    assert ordered == sorted(ordered)
    assert result.unmatched == []


def test_ac_a2_a_code_containing_a_space_matches_exact_never_prefix(db: Session, srtbv):
    """AC-A2 - a code with a space is still an exact hit when it names itself."""
    exact_code = f"ZZT-CB {uuid.uuid4().hex[:8]}-2B"
    row = Product(
        id=str(uuid.uuid4()),
        product_code=exact_code,
        product_name=exact_code,
        category_id=srtbv["category"].id,
        base_uom_id=srtbv["uom"].id,
        list_price=Decimal("1.00"),
        company_id=srtbv["company"].id,
    )
    db.add(row)
    db.flush()

    result = _resolve_in(db, srtbv["company"], [exact_code])
    assert _codes(result) == {exact_code}
    assert [m.via for m in result.matches] == ["exact"]


def test_ac_a3_a_head_shorter_than_four_chars_is_unmatched(db: Session, srtbv):
    """AC-A3 - `ZZT` normalises to 3 chars, below PREFIX_MIN_HEAD."""
    code = "ZZT - SOMETHING"
    result = _resolve_in(db, srtbv["company"], [code], allow_prefix=True)
    assert result.matches == []
    assert result.unmatched == [code]


def test_ac_a4_a_fanout_over_the_cap_is_unmatched(db: Session, srtbv):
    """AC-A4 - more than 200 prefix hits: refused outright, no partial link."""
    tag = uuid.uuid4().hex[:6].upper()
    head = f"ZZTFANOUT{tag}"
    for i in range(201):
        db.add(
            Product(
                id=str(uuid.uuid4()),
                product_code=f"{head}-{i:04d}",
                product_name="x",
                category_id=srtbv["category"].id,
                base_uom_id=srtbv["uom"].id,
                list_price=Decimal("1.00"),
                company_id=srtbv["company"].id,
            )
        )
    db.flush()

    code = f"{head} - DESCRIPTION"
    result = _resolve_in(db, srtbv["company"], [code], allow_prefix=True)
    assert result.matches == []
    assert result.unmatched == [code]


def test_ac_a6_link_products_route_reports_via_prefix(db: Session, srtbv):
    """AC-A6 - the /link-products caller surfaces `via` on every linked item."""
    attachment = Attachment(
        id=str(uuid.uuid4()),
        original_filename=_uid("cert") + ".pdf",
        stored_filename=_uid("stored") + ".pdf",
        file_path="zzt://cert",
        company_id=srtbv["company"].id,
    )
    db.add(attachment)
    db.flush()

    response = _link_attachment_to_products_bulk(
        db,
        attachment.id,
        ["ZZT-SRTBV - BRASS BALL VALVE"],
        current_user={"id": str(uuid.uuid4())},
    )

    assert response.skipped_product_codes == []
    assert response.already_linked == []
    assert {item.product_code for item in response.linked} == srtbv["codes"]
    assert all(item.via == "prefix" for item in response.linked)


def test_ac_a6_link_products_http_route_reports_via_prefix_on_the_json_body(
    db: Session, srtbv
):
    """AC-A6, over real HTTP.

    The test above calls ``_link_attachment_to_products_bulk`` directly, so it
    only proves the ``via`` attribute exists on the Python object -- FastAPI's
    ``response_model=ProductAttachmentBulkLinkResponse`` on the actual route can
    still drop an undeclared/mis-serialized field on the way out to JSON
    (LESSONS-LEARNT: "`response_model` silently drops undeclared fields.
    Assert the field in a test."). This drives the real mounted route,
    ``POST /api/v1/external/product-attachments/link-products``, through
    ``TestClient`` with a real ``X-API-Key`` header, and asserts ``via`` on the
    decoded JSON body rather than the ORM/pydantic object.

    Authorization itself is out of scope here (covered by
    ``test_external_permission_guard.py``), so the permission check is granted
    via the sanctioned ``tests._external_auth.external_permissions_granted``
    helper -- the key still resolves to a real, freshly seeded integration
    principal, so the request genuinely authenticates via ``X-API-Key``.
    """
    from app.main import app  # imported here, not at module top: app.main must
    # load after app.modules.runtime.guards has a chance to resolve its own
    # circular import, exactly as tests/test_certificate_api.py does.
    from app.database import get_db
    from app.models.integration import Integration
    from app.models.resources import Attachment
    from app.models.user import User
    from app.services.company_scope import set_company_scope
    from app.services.company_scope_resolver import apply_company_scope
    from app.services.integration_key_service import IntegrationKeyService
    from tests._external_auth import external_permissions_granted

    attachment = Attachment(
        id=str(uuid.uuid4()),
        original_filename=_uid("cert-http") + ".pdf",
        stored_filename=_uid("stored-http") + ".pdf",
        file_path="zzt://cert-http",
        company_id=srtbv["company"].id,
    )
    db.add(attachment)
    db.flush()

    # A real integration principal, seeded fresh in this test's own
    # savepoint-scoped transaction -- never an existing/borrowed row.
    api_user = User(
        id=str(uuid.uuid4()),
        email=f"{_uid('integration').lower()}@zzt.test",
        name="ZZT link-products integration",
        status="ACTIVE",
    )
    db.add(api_user)
    db.flush()
    integration = Integration(
        id=str(uuid.uuid4()),
        name=_uid("integration"),
        type="zzt_test",
        act_as_user_id=api_user.id,
        is_active=True,
    )
    db.add(integration)
    db.flush()
    api_key = IntegrationKeyService(db).issue_key(integration)

    def _override_get_db():
        yield db

    # The company-scope resolver's X-API-Key branch only recognizes the legacy
    # shared `EXTERNAL_API_KEY` env value (a separate mechanism from the
    # per-integration keys `IntegrationKeyService` issues), so a freshly minted
    # key here resolves to `UNSET` (fail-closed, 0 rows) rather than "all
    # companies" -- the same override `tests/test_certificate_api.py` uses to
    # pin scope explicitly rather than depending on that legacy path.
    def _override_company_scope():
        set_company_scope(db, frozenset({str(srtbv["company"].id)}))
        return frozenset({str(srtbv["company"].id)})

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[apply_company_scope] = _override_company_scope
    try:
        with external_permissions_granted():
            with TestClient(app) as client:
                response = client.post(
                    "/api/v1/external/product-attachments/link-products",
                    json={
                        "attachment_id": attachment.id,
                        "products": ["ZZT-SRTBV - BRASS BALL VALVE"],
                    },
                    headers={"X-API-Key": api_key},
                )
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(apply_company_scope, None)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["skipped_product_codes"] == []
    assert {item["product_code"] for item in body["linked"]} == srtbv["codes"]
    assert all(item["via"] == "prefix" for item in body["linked"])


# ------------------- N4: a spaced non-code does not fan out on an unrelated head


def test_a_spaced_code_missing_every_tier_does_not_fan_out_on_its_head(
    db: Session, srtbv
):
    """N4 - `ZZT-CB 90024E2-2B` is not an exact product here (unlike AC-A2, no
    such row exists), and its head (`ZZT-CB`, first whitespace token, >= 4
    chars) has no family in this fixture. Even with the prefix tier explicitly
    enabled, it must not fan out onto some unrelated family (`ZZT-SRTBV*`)."""
    code = "ZZT-CB 90024E2-2B"
    result = _resolve_in(db, srtbv["company"], [code], allow_prefix=True)
    assert result.matches == []
    assert result.unmatched == [code]


# --------------------- opt-in: every OTHER caller stays four-tier (S1 fix round)


def test_ac_a_packing_list_a_family_head_is_reported_missing_not_linked(
    db: Session, srtbv
):
    """S1 ruling: packing lists never pass `allow_prefix=True`, so the same
    family head AC-A1 resolves for the attachment-link path stays in
    `skipped_product_codes` here - never silently linked to all 9 members."""
    attachment = _attachment_for(db, srtbv["company"])

    response = _create_packing_list(
        db, attachment, [("ZZT-SRTBV - BRASS BALL VALVE", 5)]
    )

    assert response.skipped_product_codes == ["ZZT-SRTBV - BRASS BALL VALVE"]
    assert (response.shipment.shipment_lines or []) == []


def test_ac_a_promotion_a_family_head_is_reported_missing_not_linked(
    db: Session, srtbv
):
    """S1 ruling: promotions never pass `allow_prefix=True` either, so the same
    family head lands in `unknown_product_codes`, never silently linked."""
    payload = PromotionRequest(
        promotions=PromotionHeader(
            description=_uid("promo"),
            start_date="2026-09-01",
            end_date="2026-09-30",
        ),
        promotion_products=[
            PromotionProductItem(product_code="ZZT-SRTBV - BRASS BALL VALVE")
        ],
    )
    with company_scope(db, frozenset({str(srtbv["company"].id)})):
        response = create_promotion(
            payload=payload, current_user={"id": str(uuid.uuid4())}, db=db
        )

    assert response.unknown_product_codes == ["ZZT-SRTBV - BRASS BALL VALVE"]


def test_ac_a_single_code_create_still_400s_on_a_family_head(db: Session, srtbv):
    """S1 ruling: the single-code `POST /` route keeps the four-tier default
    too, so a family head only the prefix tier could answer still 400s exactly
    as before - no accidental widening for this caller either."""
    attachment = Attachment(
        id=str(uuid.uuid4()),
        original_filename=_uid("single") + ".pdf",
        stored_filename=_uid("stored") + ".pdf",
        file_path="zzt://single",
        company_id=srtbv["company"].id,
    )
    db.add(attachment)
    db.flush()

    payload = ProductAttachmentLinkRequestAny(
        attachment_id=attachment.id,
        product_code="ZZT-SRTBV - BRASS BALL VALVE",
    )
    with pytest.raises(HTTPException) as exc_info:
        create_product_attachment(
            payload=payload, current_user={"id": str(uuid.uuid4())}, db=db
        )
    assert exc_info.value.status_code == 400


# ------------------------------------------------------------------ isolation


def test_ac_f8_a_set_resolves_only_within_the_scoped_company(db: Session, world):
    """AC-F.8 - an attachment pinned to one company never links another's members."""
    a, b = world["a"], world["b"]

    result = _resolve_in(db, b["company"], [b["set"].set_code])

    # By ROW, never by code. Both companies carry identical product codes - that
    # is the whole reason sets are company-scoped - so comparing code strings
    # would pass no matter which company's rows came back.
    resolved_ids = {m.product.id for m in result.matches}
    assert resolved_ids == {
        b["pedestal"].id,
        b["cistern"].id,
        b["seat"].id,
    }
    assert a["pedestal"].id not in resolved_ids


def test_the_other_companys_set_code_is_unmatched_not_borrowed(db: Session, world):
    """Fail-closed: an unknown-here code is reported, never silently satisfied."""
    a, b = world["a"], world["b"]
    # Give company A's set a code company B does not carry at all.
    a["set"].set_code = f"{STEM}-ONLY-A-{uuid.uuid4().hex[:6]}"
    db.flush()

    result = _resolve_in(db, b["company"], [a["set"].set_code])

    assert result.matches == []
    assert result.unmatched == [a["set"].set_code]


# ------------------------------------------------------- the callers agree now


def test_ac_f1_both_external_paths_use_this_one_function(db: Session, world):
    """AC-F.1 - one helper, one behaviour, asserted at the import site.

    Guards the actual regression: someone re-adding a private `_resolve_product_codes`
    to either router is what let the two drift apart in the first place.
    """
    from app.api.v1.external import product_attachments, promotions

    assert product_attachments._resolve_codes is resolve_codes_to_products
    assert promotions._resolve_codes is resolve_codes_to_products


# --------------------------------------------- the provenance column is written


def test_the_link_schema_carries_set_provenance_to_the_row():
    """AC-F.3 - the value has to survive the schema, or the column is never set.

    `ProductAttachmentService` builds the row from `model_dump()`, so a field the
    schema does not declare is dropped silently between the router and the table -
    the same class of defect as `response_model` dropping an undeclared field on
    the way out.
    """
    from app.schemas.product import ProductAttachmentCreate

    payload = ProductAttachmentCreate(
        product_id=str(uuid.uuid4()),
        attachment_id=str(uuid.uuid4()),
        linked_via_set_id="set-123",
    )
    assert payload.model_dump()["linked_via_set_id"] == "set-123"


def test_both_link_tables_can_hold_set_provenance(db: Session, world):
    """AC-F.3 / AC-F.4 - the column exists on both, and NULL is a legal answer."""
    from sqlalchemy import inspect as sa_inspect

    from app.models.marketing import PromotionProduct
    from app.models.product import ProductAttachment

    for model in (ProductAttachment, PromotionProduct):
        assert "linked_via_set_id" in sa_inspect(model).columns
        column = sa_inspect(model).columns["linked_via_set_id"]
        assert column.nullable, "a hand-made link legitimately has no set"


# ----------------------------------------------------- a third caller: packing lists
#
# `packing_lists.create_packing_list` used to call the bare exact-match
# `get_products_by_code`, so a set code fell straight into `skipped_product_codes`.
# It now goes through the same `resolve_codes_to_products` the two callers above
# use - one helper, one behaviour (D11) - so these exercise the real route, not
# just the shared function again.


def _attachment_for(db: Session, company) -> "Attachment":
    from app.models.resources import Attachment

    row = Attachment(
        id=str(uuid.uuid4()),
        original_filename=_uid("packing-list") + ".pdf",
        stored_filename=_uid("stored") + ".pdf",
        file_path="zzt://packing-list",
        company_id=company.id,
    )
    db.add(row)
    db.flush()
    return row


def _create_packing_list(db: Session, attachment, items: list[tuple[str, int]]):
    from app.api.v1.external.packing_lists import create_packing_list
    from app.schemas.external.procurement import (
        PackingListHeader,
        PackingListProduct,
        PackingListRequest,
    )

    payload = PackingListRequest(
        packing_list=PackingListHeader(
            shipment_number=_uid("shp"),
            attachment_id=attachment.id,
            shipment_date="2026-08-24",
        ),
        packing_list_products=[
            PackingListProduct(product_code=code, quantity=qty) for code, qty in items
        ],
    )
    return create_packing_list(
        payload=payload, current_user={"id": str(uuid.uuid4())}, db=db
    )


def test_a_packing_list_set_code_lands_a_line_for_every_member(db: Session, world):
    """A set code on the slip creates one shipment line PER MEMBER - the same
    quantity the slip stated for the set code, on every member, not split or
    scaled by `ProductSetMember.quantity`. See the route's own comment for why:
    nothing on the slip says "how many complete sets" versus "how many of this
    one part", so scaling would invent a number nobody wrote."""
    a = world["a"]
    attachment = _attachment_for(db, a["company"])

    response = _create_packing_list(db, attachment, [(a["set"].set_code, 5)])

    assert response.skipped_product_codes == []
    lines = {
        line.product.product_code: line.quantity_shipped
        for line in response.shipment.shipment_lines or []
    }
    assert lines == {
        a["pedestal"].product_code: 5,
        a["cistern"].product_code: 5,
        a["seat"].product_code: 5,
    }


def test_a_packing_list_ordinary_code_behaves_as_before(db: Session, world):
    """An exact product code still resolves to exactly its own one line."""
    a = world["a"]
    attachment = _attachment_for(db, a["company"])

    response = _create_packing_list(db, attachment, [(a["cistern"].product_code, 12)])

    assert response.skipped_product_codes == []
    lines = {
        line.product.product_code: line.quantity_shipped
        for line in response.shipment.shipment_lines or []
    }
    assert lines == {a["cistern"].product_code: 12}


def test_a_packing_list_unknown_code_is_still_reported_skipped(db: Session, world):
    """AC-F.6's guarantee carried through to the packing-list route."""
    a = world["a"]
    attachment = _attachment_for(db, a["company"])

    response = _create_packing_list(db, attachment, [("ZZT-NO-SUCH-CODE-AT-ALL", 3)])

    assert response.skipped_product_codes == ["ZZT-NO-SUCH-CODE-AT-ALL"]
    assert (response.shipment.shipment_lines or []) == []


def test_a_packing_list_set_code_only_links_the_scoped_companys_members(db: Session, world):
    """AC-F.8's guarantee, through the actual route: the attachment's own company
    pins the scope, so the resolver cannot receive the wrong company's members -
    the same guarantee product-attachment / promotion linking already have.

    Both companies carry the SAME codes on purpose (`world` builds one 8608
    family per company with an identical tag) - asserted by ROW, never by code,
    same as `test_ac_f8_a_set_resolves_only_within_the_scoped_company` above."""
    a, b = world["a"], world["b"]
    attachment = _attachment_for(db, b["company"])

    response = _create_packing_list(db, attachment, [(b["set"].set_code, 2)])

    product_ids = {line.product.id for line in response.shipment.shipment_lines or []}
    assert product_ids == {b["pedestal"].id, b["cistern"].id, b["seat"].id}
    assert a["pedestal"].id not in product_ids
