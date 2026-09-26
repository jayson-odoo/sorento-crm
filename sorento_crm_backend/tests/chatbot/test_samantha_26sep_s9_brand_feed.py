"""Phase 2 RED tests - issue #1262 (the Samantha case), GROUP C brand slice, slice 9
(finding F1a), UAC `chatbot-samantha-slices-26sep-acceptance-criteria.md` AC-S9-1 /
AC-S9-2. Round 3 section 6 steps 1 to 3 (the brand feed): the engine reads the live
`brands` table for the contact's companies and writes one `Known brands:` line into the
parser's user block, at BOTH call sites (first parse and the recall re-parse); the
prompt refers to that line instead of a hard-coded name list.

Written before any of the feed exists - `build_user_block` has no `brands` parameter
today, and neither `engine.py` call site (~1423, ~1496) passes one. No implementation
looked at beyond what is read here to confirm the RED reason.
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text

from app.models.base import set_company_scope
from app.models.product import Brand
from app.services.chatbot.head import parser as parser_mod
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests.chatbot.test_engine import CONTACT_ID, _envelope, _parser_output, stub_access, stub_parser  # noqa: F401


def _seed_brand(session_factory, *, name: str, code: str, is_active: bool = True, company_id: str = DEFAULT_COMPANY_ID) -> str:
    import uuid

    db = session_factory()
    # This harness's sessions default to `UNSET` company scope (fail-closed) unlike the
    # root `tests/conftest.py` Sorento default - stamped explicitly here so the seeded
    # row is both insertable and later queryable by this file's own direct reads
    # (`_active_brand_rows`). A real turn's own session gets its scope from
    # `engine._scoped_factory`/`_contact_company_scope`, never from this helper.
    set_company_scope(db, frozenset({company_id}))
    row = Brand(id=str(uuid.uuid4()), brand_name=name, brand_code=code, is_active=is_active, company_id=company_id)
    db.add(row)
    db.commit()
    return row.id


def _active_brand_rows(session_factory, *, company_ids) -> list[dict[str, Any]]:
    """The read step design step 1 describes: active brands for the given companies,
    freshly queried - no cache, no memoisation. Exercised directly here since no
    production function under this name exists yet; the production wiring is graded
    separately by `TestEngineCallSitesPassBrands` below."""
    db = session_factory()
    set_company_scope(db, frozenset(company_ids))
    rows = (
        db.query(Brand)
        .filter(Brand.is_active.is_(True), Brand.company_id.in_(list(company_ids)))
        .order_by(Brand.brand_name)
        .all()
    )
    return [{"brand_name": r.brand_name, "brand_code": r.brand_code} for r in rows]


class TestKnownBrandsLine:
    """AC-S9-1: one `Known brands:` line, active brands only, built fresh every call."""

    def test_user_block_carries_the_live_brand_list_active_only(self, session_factory) -> None:
        _seed_brand(session_factory, name="Sorento", code="SRT")
        _seed_brand(session_factory, name="Mocha", code="MCH")
        _seed_brand(session_factory, name="Cabana", code="CBN", is_active=False)

        active = _active_brand_rows(session_factory, company_ids=[DEFAULT_COMPANY_ID])
        assert [r["brand_name"] for r in active] == ["Mocha", "Sorento"]

        # `build_user_block` has no `brands` parameter today - this is the missing
        # argument the whole slice adds, not a fixture bug.
        block = parser_mod.build_user_block(
            previous_response=None,
            latest_user_message="brand Sorento",
            pending_kind=None,
            brands=active,
        )
        assert "Known brands: Mocha (MCH), Sorento (SRT)" in block, block
        assert "Cabana" not in block, block

    def test_a_brand_edited_in_the_table_shows_up_on_the_next_build_with_no_restart(
        self, session_factory
    ) -> None:
        brand_id = _seed_brand(session_factory, name="Sorento", code="SRT")
        first = _active_brand_rows(session_factory, company_ids=[DEFAULT_COMPANY_ID])
        block1 = parser_mod.build_user_block(
            previous_response=None, latest_user_message="x", pending_kind=None, brands=first,
        )
        assert "Sorento (SRT)" in block1, block1

        db = session_factory()
        set_company_scope(db, frozenset({DEFAULT_COMPANY_ID}))
        db.query(Brand).filter(Brand.id == brand_id).update({"is_active": False})
        db.commit()

        second = _active_brand_rows(session_factory, company_ids=[DEFAULT_COMPANY_ID])
        block2 = parser_mod.build_user_block(
            previous_response=None, latest_user_message="x", pending_kind=None, brands=second,
        )
        assert "Sorento" not in block2, block2


class TestKnownBrandsLineAbsentWhenEmpty:
    def test_no_brands_no_known_brands_line(self) -> None:
        block = parser_mod.build_user_block(
            previous_response=None, latest_user_message="hi", pending_kind=None, brands=[],
        )
        assert "Known brands" not in block, block
        block_none = parser_mod.build_user_block(
            previous_response=None, latest_user_message="hi", pending_kind=None, brands=None,
        )
        assert "Known brands" not in block_none, block_none


def _seed_contact_with_brand(session_factory) -> None:
    """A contact scoped to Sorento (`DEFAULT_COMPANY_ID`, already seeded on every blank
    schema - `tests/_pg_fixture.py`'s own `after_create` DDL event) - see
    `test_engine_company_scope.py`'s module docstring for the same fact."""
    db = session_factory()
    db.execute(
        text(
            "INSERT INTO respond_contacts (id, respond_io_id, phone_number, session_vars) "
            "VALUES (gen_random_uuid()::text, :cid, :phone, CAST(:sv AS jsonb))"
        ),
        {"cid": str(CONTACT_ID), "phone": "+60000000031", "sv": json.dumps({"variables": {}})},
    )
    db.execute(
        text(
            "INSERT INTO respond_contact_companies (id, respond_contact_id, company_id) "
            "SELECT gen_random_uuid(), id, :company_id FROM respond_contacts WHERE respond_io_id = :cid"
        ),
        {"cid": str(CONTACT_ID), "company_id": DEFAULT_COMPANY_ID},
    )
    db.commit()


class TestEngineCallSitesPassBrands:
    """AC-S9-1's other half: BOTH `engine.py` call sites (first parse ~1423, recall
    re-parse ~1496) must pass the live brand list, not just `build_user_block` accepting
    one. `parser_mod.build_user_block` is monkeypatched to a recorder that forwards to
    the real function filtered to the kwargs it currently accepts, so a turn that
    exercises the ORIGINAL (non-brand-aware) call sites still runs to completion and
    this file can grade what it was actually called with."""

    def _capture(self, monkeypatch) -> list[dict[str, Any]]:
        calls: list[dict[str, Any]] = []
        real = parser_mod.build_user_block

        def _spy(**kwargs: Any) -> str:
            calls.append(dict(kwargs))
            import inspect

            accepted = set(inspect.signature(real).parameters)
            return real(**{k: v for k, v in kwargs.items() if k in accepted})

        monkeypatch.setattr(parser_mod, "build_user_block", _spy)
        return calls

    def test_the_first_parse_passes_brands(
        self, session_factory, stub_parser, stub_access, monkeypatch
    ) -> None:
        _seed_contact_with_brand(session_factory)
        _seed_brand(session_factory, name="Sorento", code="SRT")
        calls = self._capture(monkeypatch)
        stub_parser(_parser_output())
        stub_access()

        from app.services.chatbot import engine as engine_mod

        engine_mod.run_turn(_envelope(), session_factory=session_factory)

        assert calls, "build_user_block was never called"
        assert "brands" in calls[0], (
            f"the first-parse call site must pass `brands`: {calls[0].keys()}"
        )
        assert any(
            isinstance(b, dict) and b.get("brand_name") == "Sorento"
            for b in (calls[0].get("brands") or [])
        ), calls[0].get("brands")

    def test_the_recall_reparse_also_passes_brands(
        self, session_factory, stub_access, monkeypatch
    ) -> None:
        from app.services import embedding_worker as embedding_worker_mod
        from app.models.conversation_frame import ConversationFrame
        from tests.chatbot._turn_helpers import verdict

        _seed_contact_with_brand(session_factory)
        _seed_brand(session_factory, name="Sorento", code="SRT")
        db = session_factory()
        db.execute(
            text("UPDATE respond_contacts SET chatbot_recall_enabled = true WHERE respond_io_id = :cid"),
            {"cid": str(CONTACT_ID)},
        )
        db.commit()
        db.add(
            ConversationFrame(
                contact_id=str(CONTACT_ID),
                contact_respond_id=str(CONTACT_ID),
                space_id="364817",
                channel="whatsapp",
                domain="inventory",
                intent="check_stock",
                summary="ZZT recall summary for brand feed",
                status="closed",
            )
        )
        db.commit()
        monkeypatch.setattr(embedding_worker_mod, "_embed_text_chunks", lambda texts: [[0.1] * 8])

        calls = self._capture(monkeypatch)

        def fake_resolve_config(db, *, current_date, override_version_id=None):
            return parser_mod.ParserConfig(
                system_prompt="stub", prompt_version=1, provider="openai", model="gpt-test", api_key="sk-test",
            )

        monkeypatch.setattr(parser_mod, "resolve_config", fake_resolve_config)
        v = verdict(anaphora={"backward_reference": True})
        monkeypatch.setattr(parser_mod, "parse", lambda config, user_block: v)
        stub_access()

        from app.services.chatbot import engine as engine_mod

        engine_mod.run_turn(_envelope(), session_factory=session_factory)

        assert len(calls) == 2, f"expected first parse + recall re-parse, got {len(calls)}"
        for i, call in enumerate(calls):
            assert "brands" in call, f"call {i} must pass `brands`: {call.keys()}"


class TestPromptHasNoHardCodedBrandList:
    """AC-S9-2: the parser prompt refers to the `Known brands` line instead of
    hard-coding "Sorento, Mocha, or Cabana" - shipped as a new UNLABELLED version of
    `chatbot_semantic_parser` (owner ruling 10, same immutable-versions-plus-movable-
    labels split as migrations 475/480/490/521), never by editing the `production`
    label directly."""

    def test_a_prompt_version_refers_to_known_brands_and_drops_the_hardcoded_list(
        self, session_factory
    ) -> None:
        db = session_factory()
        rows = db.execute(
            text("SELECT template FROM ai_prompt_versions WHERE name = :n"),
            {"n": "chatbot_semantic_parser"},
        ).fetchall()
        assert rows, "no chatbot_semantic_parser prompt versions exist at all"
        matches = [
            r.template
            for r in rows
            if "Known brands" in (r.template or "") and "Sorento, Mocha, or Cabana" not in (r.template or "")
        ]
        assert matches, (
            "no chatbot_semantic_parser version refers to the 'Known brands' line "
            "while dropping the hard-coded 'Sorento, Mocha, or Cabana' list "
            f"(found {len(rows)} version(s) total)"
        )
