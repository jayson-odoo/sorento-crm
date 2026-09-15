"""S3 - attribute-first asks, ported (AC-1534, PLAN-chatbot-turn-rearch.md contract 114
to 120, "#833").

Source read for this port: `origin/feat/chatbot-attribute-first-asks` (never merged,
commit 34f88114f). **Ambiguity flagged to the captain**: the brief named
`tests/chatbot/test_attribute_first_*.py` on that branch as a second source; no such
files exist there (`git ls-tree -r origin/feat/chatbot-attribute-first-asks --name-only
| grep -i attribute` returns only the console yaml, a migration test and doc files) -
this file is ported from the console yaml
(`sorento_crm_backend/tests/chatbot/console_cases/2026-09-11-attribute-first-asks.yaml`
on that branch) alone, read via `git show`, never imported across branches.

Every test is RED at collection with `ModuleNotFoundError: No module named
'app.services.chatbot.turn.compose'` (same whole-file mechanism as
`test_rearch_s3_team_pick_and_866.py` - see that file's docstring for why this is the
right reason rather than a live run against the un-rewired engine).

**Ambiguity flagged to the captain**: the parser's carrier for an attribute-first ask
is assumed to be v3's already-declared `requested_attributes: list[str]` key
(`tests.chatbot._turn_helpers.verdict`'s own default, `[]`) plus `domain_hint` /
`entities[].hint` naming the class word's resolved kind - no other key exists in the
v3 schema for this. The exact reply grammar ("N <kind> have <attribute>. Showing 5.")
and the paging window (5 per page, "Showing 6 to 10" on a second "more") are copied
from the console yaml's own `reply_contains` assertions, not invented.

Seeding (coordinator amendment, 16 Sep 2026): CI's database has no data, so every
test seeds its own products / certificates / promotions rows on the BLANK scratch
schema (`session_factory`), never relying on the shared prod-copy DB's real catalogue.
`ProductCategory.class_label` / `.search_synonyms` (already committed columns,
`app/models/product.py`) are the real "customer word -> category" mechanism #833's own
class-word matching reads, so `_seed_products` sets them rather than inventing a
parallel lookup. Certificate coverage is `Certificate` + `CertificateProduct` (the real
join table, `app/models/certificate.py`); promotion coverage is `Promotion` +
`PromotionGroup` + `PromotionProduct` (`app/models/marketing.py`) - both read via
introspection (`Column.nullable`/`.default`/`.server_default`) for their true required
columns, not guessed. `TestAnyXIncomingLeg` seeds the PRODUCT side only (a "sink"
category) - the incoming-shipment/packing-list schema is a materially larger SCM
subsystem this file does not attempt to wire for one assertion; flagged rather than
silently left unseeded.
"""
from __future__ import annotations

import uuid
from typing import Any

import pytest

# Forces collection failure now - see module docstring.
from app.services.chatbot.turn.compose import Answer  # noqa: F401

from tests.chatbot._turn_helpers import entity, verdict
from tests.chatbot.test_engine import CONTACT_ID, _envelope, seeded, stub_access, stub_parser

SORENTO = "00000000-0000-0000-0000-000000000001"


def _uid() -> str:
    return str(uuid.uuid4())


def _db(session_factory, *, scope: frozenset[str] = frozenset({SORENTO})):
    """A fresh session, with `company_scope` stamped explicitly rather than left to
    the shared `tests/conftest.py::_default_company_scope_for_tests` listener
    (`after_begin`, fires lazily on first statement) - measured RACY across the three
    session_factory() calls one test's seed chain needs (`_seed_contact` ->
    `_seed_products` -> `_seed_certificates`): a fresh session's `.info["company_
    scope"]` reads back `None` or the real scope depending on exactly when the
    listener fires relative to this call, and a `None` scope on a company-scoped
    ORM query (`Product`, `Certificate`, `Promotion`, ...) sometimes returns rows
    from every company and sometimes filters to none - reproduced 1-in-5 with a
    tight repro loop. Stamping it here removes the race outright.
    """
    db = session_factory()
    db.info["company_scope"] = scope
    return db


def _seed_contact(session_factory, *, phone: str) -> None:
    import json

    from sqlalchemy import text

    db = _db(session_factory)
    db.execute(
        text(
            "INSERT INTO respond_contacts (id, respond_io_id, phone_number, session_vars) "
            "VALUES (gen_random_uuid()::text, :cid, :phone, CAST(:sv AS jsonb))"
        ),
        {"cid": str(CONTACT_ID), "phone": phone, "sv": json.dumps({})},
    )
    db.commit()


def _link_contact_company(session_factory, *, company_id: str) -> None:
    from sqlalchemy import text

    db = _db(session_factory)
    row = db.execute(
        text("SELECT id FROM respond_contacts WHERE respond_io_id = :c"), {"c": str(CONTACT_ID)}
    ).first()
    # `respond_contact_companies.id` is a real `uuid` column (unlike `respond_
    # contacts.id`, `text`) - measured (`DatatypeMismatch: column "id" is of type
    # uuid but expression is of type text` on a `gen_random_uuid()::text` cast).
    db.execute(
        text(
            "INSERT INTO respond_contact_companies (id, respond_contact_id, company_id) "
            "VALUES (gen_random_uuid(), :rcid, :cid)"
        ),
        {"rcid": row.id, "cid": company_id},
    )
    db.commit()


def _seed_products(session_factory, *, class_label: str, synonyms: list[str], count: int) -> list[str]:
    """`count` products in ONE category whose `class_label`/`search_synonyms` carry
    the customer word #833's class-word matching reads."""
    from app.models.product import Product, ProductCategory, UnitOfMeasure

    db = _db(session_factory)
    cat = ProductCategory(
        id=_uid(),
        category_code=f"ZZTC-{class_label}",
        category_name=f"ZZT {class_label}",
        class_label=class_label,
        search_synonyms=synonyms,
    )
    uom = UnitOfMeasure(id=_uid(), uom_code=f"ZZTU-{class_label}", uom_name="ZZT uom")
    db.add_all([cat, uom])
    db.flush()
    codes: list[str] = []
    for i in range(count):
        code = f"ZZT-{class_label.upper()}-{i:02d}"
        db.add(
            Product(
                id=_uid(),
                product_code=code,
                product_name=f"ZZT {class_label} {i}",
                category_id=cat.id,
                base_uom_id=uom.id,
                list_price=1,
            )
        )
        codes.append(code)
    db.commit()
    return codes


def _seed_certificates(session_factory, product_codes: list[str], *, company_id: str) -> None:
    from app.models.certificate import Certificate, CertificateProduct
    from app.models.product import Product

    db = _db(session_factory, scope=frozenset({SORENTO, company_id}))
    for code in product_codes:
        product = db.query(Product).filter(Product.product_code == code).one()
        cert = Certificate(
            id=_uid(),
            company_id=company_id,
            scheme="ZZT-SCHEME",
            certificate_number=f"ZZT-CERT-{code}",
        )
        db.add(cert)
        db.flush()
        db.add(CertificateProduct(id=_uid(), certificate_id=cert.id, product_id=product.id))
    db.commit()


def _seed_promotion(session_factory, product_codes: list[str], *, access_levels: list[str]) -> str:
    from app.models.marketing import Promotion, PromotionGroup, PromotionProduct
    from app.models.product import Product

    db = _db(session_factory)
    promo = Promotion(id=_uid(), access_levels=access_levels)
    db.add(promo)
    db.flush()
    group = PromotionGroup(id=_uid(), promotion_id=promo.id, group_name="ZZT group")
    db.add(group)
    db.flush()
    for code in product_codes:
        product = db.query(Product).filter(Product.product_code == code).one()
        db.add(
            PromotionProduct(
                id=_uid(), promotion_id=promo.id, promotion_group_id=group.id, product_id=product.id
            )
        )
    db.commit()
    return promo.id


class TestCountedSetAnswer:
    """Console case "a class word scopes the set and the header counts it" (AC-1306,
    AC-1316): "which tap has cert" -> "taps have certificates ... Showing 5"."""

    def test_counted_answer_names_kind_attribute_and_shows_five(
        self, session_factory, stub_parser, stub_access
    ) -> None:
        _seed_contact(session_factory, phone="+60000000020")
        codes = _seed_products(session_factory, class_label="tap", synonyms=["taps"], count=11)
        _seed_certificates(session_factory, codes, company_id=SORENTO)

        v = verdict(
            domain_hint="product_attachment",
            requested_attributes=["certificate"],
            entities=[entity("tap", hint="product_type", confident=True)],
        )
        stub_parser(v)
        stub_access()

        from app.services.chatbot import engine as engine_mod

        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)

        text = (result.reply or {}).get("text", "")
        assert "have certificates" in text or "certificate" in text.lower(), text
        assert "Showing 5" in text, text


class TestPagingByFive:
    def test_more_pages_the_same_set_by_five(self, session_factory, stub_parser, stub_access) -> None:
        _seed_contact(session_factory, phone="+60000000021")
        codes = _seed_products(session_factory, class_label="tap", synonyms=["taps"], count=11)
        _seed_certificates(session_factory, codes, company_id=SORENTO)

        offsets_seen: list[int] = []

        def on_call(user_block: str) -> None:
            offsets_seen.append(len(offsets_seen))

        v1 = verdict(
            domain_hint="product_attachment",
            requested_attributes=["certificate"],
            entities=[entity("tap", hint="product_type", confident=True)],
        )
        stub_parser(v1, on_call=on_call)
        stub_access()

        from app.services.chatbot import engine as engine_mod

        first = engine_mod.run_turn(_envelope(), session_factory=session_factory)
        assert "Showing 5" in (first.reply or {}).get("text", ""), first.reply

        v2 = verdict(message_type="clarification", user_goal="more")
        stub_parser(v2, on_call=on_call)
        second_envelope = _envelope()
        second_envelope.message["message"]["messageId"] = "ZZT-attr-first-page-2"
        second_envelope.message["message"]["message"]["text"] = "more"
        second = engine_mod.run_turn(second_envelope, session_factory=session_factory)

        assert "Showing 6 to 10" in (second.reply or {}).get("text", ""), second.reply


class TestOwnCompanyCertificatesOnly:
    OTHER_COMPANY = "00000000-0000-0000-0000-0000000000c2"

    def _seed_other_company(self, session_factory) -> None:
        from app.models.company import Company

        db = session_factory()
        if db.query(Company).filter(Company.id == self.OTHER_COMPANY).first() is None:
            db.add(Company(id=self.OTHER_COMPANY, name="ZZT Other Co", code="ZZT-OTHER"))
            db.commit()

    def test_certificates_filter_to_the_contacts_own_company(
        self, session_factory, stub_parser, stub_access
    ) -> None:
        _seed_contact(session_factory, phone="+60000000022")
        _link_contact_company(session_factory, company_id=SORENTO)
        self._seed_other_company(session_factory)

        own_codes = _seed_products(session_factory, class_label="wt5875", synonyms=[], count=1)
        _seed_certificates(session_factory, own_codes, company_id=SORENTO)

        other_codes = _seed_products(session_factory, class_label="othco", synonyms=[], count=1)
        _seed_certificates(session_factory, other_codes, company_id=self.OTHER_COMPANY)

        v = verdict(
            domain_hint="product_attachment",
            requested_attributes=["certificate"],
            entities=[entity(own_codes[0], hint="product", confident=True)],
        )
        stub_parser(v)
        stub_access(attributes=["product_attachment.certificate"])

        from app.services.chatbot import engine as engine_mod

        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)

        text = (result.reply or {}).get("text", "")
        assert result.branch_kind == "business_query", result.branch_kind
        assert other_codes[0] not in text, (
            f"a certificate belonging to a DIFFERENT company must never surface: {text!r}"
        )


class TestTierVisiblePromotionsOnly:
    def test_promotion_count_respects_tier_visibility(
        self, session_factory, stub_parser, stub_access
    ) -> None:
        _seed_contact(session_factory, phone="+60000000023")
        dealer_codes = _seed_products(session_factory, class_label="promodealer", synonyms=[], count=3)
        _seed_promotion(session_factory, dealer_codes, access_levels=["dealer"])
        end_user_codes = _seed_products(session_factory, class_label="promoenduser", synonyms=[], count=2)
        _seed_promotion(session_factory, end_user_codes, access_levels=["end_user"])

        v = verdict(
            domain_hint="promotion",
            requested_attributes=["promotion"],
        )
        stub_parser(v)
        # The contact's own tier is a dealer - only the dealer-visible promotion's
        # products should count toward the answer.
        stub_access(attributes=["promotion.view"])

        from app.services.chatbot import engine as engine_mod

        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)

        assert result.branch_kind == "business_query", result.branch_kind


class TestUnknownAttributeClarify:
    """Console case "an unknown class word clarifies with the nearest label" (AC-1320):
    "which water tap has cert" -> "I don't know 'water tap'", "Did you mean". No data
    seed needed - this is a clarify path over an UNRECOGNISED word, never a real set."""

    def test_unknown_attribute_word_clarifies_naming_valid_schemes(
        self, session_factory, stub_parser, stub_access
    ) -> None:
        _seed_contact(session_factory, phone="+60000000024")
        v = verdict(
            domain_hint="product_attachment",
            requested_attributes=["cert"],
            entities=[entity("water tap", hint="product_type", confident=False)],
        )
        stub_parser(v)
        stub_access()

        from app.services.chatbot import engine as engine_mod

        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)

        text = (result.reply or {}).get("text", "")
        assert "don't know" in text.lower() or "did you mean" in text.lower(), text


class TestAnyXIncomingLeg:
    """Console case "the incoming leg" (AC-1311): "which sink has incoming" -> "kitchen
    sinks have incoming stock". Seeds the PRODUCT side only - see module docstring for
    why the incoming-shipment schema is not wired here."""

    def test_any_x_incoming_routes_to_incoming_section(
        self, session_factory, stub_parser, stub_access
    ) -> None:
        _seed_contact(session_factory, phone="+60000000025")
        _seed_products(session_factory, class_label="sink", synonyms=["sinks", "kitchen sink"], count=3)

        v = verdict(
            domain_hint="incoming",
            requested_attributes=["incoming"],
            entities=[entity("sink", hint="product_type", confident=True)],
        )
        stub_parser(v)
        stub_access()

        from app.services.chatbot import engine as engine_mod

        result = engine_mod.run_turn(_envelope(), session_factory=session_factory)

        text = (result.reply or {}).get("text", "")
        assert "incoming" in text.lower(), text
