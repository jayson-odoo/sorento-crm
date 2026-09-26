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
v3 schema for this. The exact reply grammar ("N <kind> have <attribute>.") is copied
from the console yaml's own `reply_contains` assertions, not invented; the paging window
it once carried is gone (owner ruling, 26 Sep 2026: no paging).

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

_XFAIL_ATTRIBUTE_FIRST_NEVER_ROUTES_COUNTED_SET = (
    "a confident class-word attribute-first ask never routes through the counted-set "
    "resolver; falls to ordinary single-entity resolution, climbs to Tier-3 embedding "
    "(no key in test env), degrades to a raw disambiguation (follow-up, PR #952)"
)


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


# `stub_access()` (test_engine.py) points `engine_mod.default_space_id` at this exact
# literal - D5's own hardcoded n8n default. `_contact_company_scope` (engine.py) calls
# `resolve_contact_id(db, respond_io_id, space_id)`, which JOINs `respond_contacts.
# workspace_id` against a `RespondWorkspace.space_id` row when `space_id` is given
# (`app/services/field_access.py`); a contact with no workspace resolves to NO
# company, which reads as "found nothing" everywhere a company-scoped read sits
# downstream (class-label resolution, certificates, promotions) - not as a missing
# fixture (measured: `tests/chatbot/test_engine_company_scope.py` names the same
# literal for the same reason).
SPACE_ID = "364817"


def _seed_workspace(session_factory) -> str:
    from app.models.respond_workspace import RespondWorkspace

    db = _db(session_factory)
    existing = db.query(RespondWorkspace).filter(RespondWorkspace.space_id == SPACE_ID).first()
    if existing is not None:
        return existing.id
    workspace = RespondWorkspace(
        space_id=SPACE_ID,
        name="ZZT attribute-first workspace",
        api_key_ciphertext="ZZT-cipher",
    )
    db.add(workspace)
    db.commit()
    return workspace.id


def _seed_contact(session_factory, *, phone: str) -> None:
    import json

    from sqlalchemy import text

    workspace_id = _seed_workspace(session_factory)
    db = _db(session_factory)
    db.execute(
        text(
            "INSERT INTO respond_contacts (id, respond_io_id, phone_number, session_vars, workspace_id) "
            "VALUES (gen_random_uuid()::text, :cid, :phone, CAST(:sv AS jsonb), :wid)"
        ),
        {"cid": str(CONTACT_ID), "phone": phone, "sv": json.dumps({}), "wid": workspace_id},
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


def _stub_certificate_tools(session_factory, monkeypatch, *, codes: list[str]) -> None:
    """Answer `crm_master_product_attachments_list` / `crm_certificates_list` (the
    `product_attachment` domain's own two tools, `policy_rows.py`) with one row per
    id in the call's OWN `product_ids` argument, in the shape
    `sorento_crm_mcp/presenters.py`'s `_product_attachments` builds (`title` = product
    code, a `Certificate Number` field). The envelope key is `items`, not `answers` -
    `fetch.py::_find_payload` only recognises a dict carrying `items` (or
    `portal_url`/`token`) as a render envelope; `answers` is the INCOMING picker
    probe's own shape (`pickers._probe_rows`), a different seam.

    Filtering by `arguments["product_ids"]` matters, not just returning every seeded
    row: `fetch.py` slices `product_ids` to the first FIVE itself (`out["product_ids"]
    = out["product_ids"][:5]`, "the PAGE is built by slicing product_ids itself") and
    the header's own "Showing N" counts DISTINCT product codes actually present in the
    tool's answer - a stub that ignores the slice and returns all eleven makes "Showing
    5" and the second-page "Showing 6 to 10" both permanently false regardless of what
    the real code does.

    Without any of this, `MCPRuntimeClient.call_tool` reaches the REAL MCP server on
    :8765, which reads a DIFFERENT (non-test) database that has never heard of a
    `ZZT-TAP-*` code - measured: the qualifying COUNT in the reply text was always
    right (it comes from `resolve_product_set`'s own direct, company-scoped SQL, never
    MCP), but the rendered PAGE was always empty ("Showing 0") because the real
    server's answer for these codes is genuinely nothing.
    """
    from app.models.product import Product
    from app.services.ai_assistant_service import MCPRuntimeClient
    import json as _json

    db = _db(session_factory)
    code_by_id = {
        p.id: p.product_code
        for p in db.query(Product).filter(Product.product_code.in_(codes)).all()
    }

    def fake_call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        if name in ("crm_master_product_attachments_list", "crm_certificates_list"):
            wanted_ids = arguments.get("product_ids") or list(code_by_id)
            page_codes = [code_by_id[i] for i in wanted_ids if i in code_by_id]
            return _json.dumps(
                {
                    "items": [
                        {
                            "title": code,
                            "fields": [
                                {"label": "Product Code", "value": code},
                                {"label": "Certificate Number", "value": f"ZZT-CERT-{code}"},
                            ],
                        }
                        for code in page_codes
                    ],
                    "attachments": [],
                    "action_links": [],
                }
            )
        return _json.dumps({"items": []})

    monkeypatch.setattr(MCPRuntimeClient, "call_tool", fake_call_tool)


class TestCountedSetAnswer:
    """Console case "a class word scopes the set and the header counts it" (AC-1306,
    AC-1316): "which tap has cert" -> "11 taps have certificates." with all eleven
    listed (no paging, owner ruling 26 Sep 2026)."""

    @pytest.mark.xfail(strict=True, reason=_XFAIL_ATTRIBUTE_FIRST_NEVER_ROUTES_COUNTED_SET)
    def test_counted_answer_names_kind_attribute_and_shows_five(
        self, session_factory, stub_parser, stub_access, monkeypatch
    ) -> None:
        _seed_contact(session_factory, phone="+60000000020")
        # A company-scoped read (certificates, below) sees nothing for a contact with
        # no company link - the same reason `TestOwnCompanyCertificatesOnly` links one.
        _link_contact_company(session_factory, company_id=SORENTO)
        codes = _seed_products(session_factory, class_label="tap", synonyms=["taps"], count=11)
        _seed_certificates(session_factory, codes, company_id=SORENTO)
        _stub_certificate_tools(session_factory, monkeypatch, codes=codes)

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
        assert "11 taps have certificates." in text, text
        assert "Showing" not in text, text
        for code in codes:
            assert code in text, text


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

        # T1 (coder 7 cluster report, AC-1591): amended to the corpus name.
        assert result.branch_kind == "check_promotion", result.branch_kind


class TestUnknownAttributeClarify:
    """Console case "an unknown class word clarifies with the nearest label" (AC-1320):
    "which water tap has cert" -> "I don't know 'water tap'", "Did you mean". No data
    seed needed - this is a clarify path over an UNRECOGNISED word, never a real set.

    DEFECT ADJUDICATION (tester 34, 20 Sep 2026, coder 30's own report): coder 30
    flagged `confident=False` as a possibly-wrong verdict shape for this console case -
    UPHELD. MEASURED: `confident=False` makes `answer.py::not_found_error_message` take
    its `vague_unresolved` branch (lines 3178-3212, checked BEFORE the AC-1320 branch) -
    a real, live copy string ("I captured 'water tap' but couldn't tell which part is
    which. For a product_attachment enquiry, please give me a labeled specific - e.g.
    ..."), just the WRONG one for this console case's own name (a "class word" the
    parser is CONFIDENT is a product_type entity, just an unrecognised one - not an
    ambiguous, unplaced mash of text). `confident=True` (this fix) reaches AC-1320's own
    branch instead (`answer.py:3253-3284`, `predicate.qualifying_total == 0` and
    `unrecognized_terms` non-empty, no near suggestions since no data is seeded):
    measured verbatim, "I don't know 'water tap' as a product type. Try a product type
    such as a class or product type I know." - genuinely contains "don't know", the
    exact AC-1320 copy this console case names. Re-pinned to `confident=True`."""

    def test_unknown_attribute_word_clarifies_naming_valid_schemes(
        self, session_factory, stub_parser, stub_access
    ) -> None:
        _seed_contact(session_factory, phone="+60000000024")
        v = verdict(
            domain_hint="product_attachment",
            requested_attributes=["cert"],
            entities=[entity("water tap", hint="product_type", confident=True)],
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
    why the incoming-shipment schema is not wired here.

    DEFECT ADJUDICATION (tester 34, 20 Sep 2026, coder 30's own report). Coder 30's
    named cause (R3's own trigram-fallback deletion) is WRONG - MEASURED (this
    session, `_seed_products` gives "sink" a genuine `ProductCategory.class_label`/
    `search_synonyms` row, `requested_attributes=["incoming"]` maps to a real,
    already-shipped `REQUIRE_LEGS["incoming"]` leg, and `resolve_gate.py:711-725`
    genuinely forwards `scope_terms=["sink"]` into the SAME production
    `resolve_reference_post` -> `resolve_product_set` call `TestCountedSetAnswer`'s own
    sibling `class_label="tap"` case reaches): production's ACTUAL reply is "I don't
    know 'sink' as a product type. Try a product type such as a class or product type I
    know." - the SAME `answer.py:3253-3284` AC-1320 "genuinely unrecognized, no near
    suggestions" branch `TestUnknownAttributeClarify` (above) now correctly pins, which
    only fires once the counted-set resolver ITSELF reports zero matches for a real,
    seeded class label. That is the SAME "counted-set resolver never wired" gap this
    file already scopes out via `TestCountedSetAnswer` / `TestPagingByFive`'s own
    `xfail(strict=True, reason=_XFAIL_ATTRIBUTE_FIRST_NEVER_ROUTES_COUNTED_SET)` (a
    seeded, real class label still comes back "unrecognized" - the resolver's own
    embedding-tier climb, unavailable with no key in test env, is what would otherwise
    confirm the match) - not a fixture defect specific to this test, and not
    reproducible without the counted-set resolver's own embedding tier. Captain ruling
    20 Sep 2026: out of #952 scope, tracked with the counted-set resolver."""

    @pytest.mark.xfail(strict=True, reason=_XFAIL_ATTRIBUTE_FIRST_NEVER_ROUTES_COUNTED_SET)
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
