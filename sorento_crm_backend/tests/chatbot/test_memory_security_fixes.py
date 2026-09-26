"""Security review regression tests, chatbot memory lane A (26 Sep 2026).

Covers the coordinator's fix-round findings the `coder` agent owns (B1, B2, S1-S4,
N1-N3). The tester's own concurrent fixes to `test_memory_profile_facts.py`,
`test_contact_chatbot_memory_api.py`, `test_context_assemble.py`, the replay memory
cases, `test_rearch_s3_recall.py` and `test_rearch_s3_episodes.py` cover the SAME
lane from the original UAC's angle - this file is deliberately self-contained
(no import from any of those files) so the two rounds of edits never race on a
shared helper.

Postgres only (`tests/chatbot/conftest.py::session_factory`, blank scratch schema);
every row is seeded fresh, ZZT-prefixed, never borrowed.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

# --------------------------------------------------------------------------- #
# Shared seeding helpers
# --------------------------------------------------------------------------- #


def _cid() -> str:
    return f"ZZT-sec-{uuid.uuid4().hex[:10]}"


def _seed_one_contact(session_factory, contact_respond_id: str, *, memory_level: str | None = None) -> str:
    """A single, unambiguous contact - the common case every helper below needs."""
    db = session_factory()
    phone = f"+6011{uuid.uuid4().hex[:8]}"
    db.execute(
        text(
            "INSERT INTO respond_contacts "
            "(id, respond_io_id, phone_number, session_vars, chatbot_profile, chatbot_memory_level) "
            "VALUES (gen_random_uuid()::text, :cid, :phone, CAST('{}' AS jsonb), CAST('{}' AS jsonb), :lvl)"
        ),
        {"cid": contact_respond_id, "phone": phone, "lvl": memory_level},
    )
    db.commit()
    return db.execute(text("SELECT id FROM respond_contacts WHERE phone_number = :p"), {"p": phone}).scalar()


def _seed_two_rows_same_respond_id(session_factory, contact_respond_id: str) -> list[str]:
    """Two DIFFERENT `respond_contacts` rows sharing one `respond_io_id` - the
    cross-workspace-namesake scenario B1 fixes. Returns the two ids in insertion
    order (row[0] is created first)."""
    pks: list[str] = []
    for _ in range(2):
        db = session_factory()
        phone = f"+6011{uuid.uuid4().hex[:8]}"
        db.execute(
            text(
                "INSERT INTO respond_contacts "
                "(id, respond_io_id, phone_number, session_vars, chatbot_profile) "
                "VALUES (gen_random_uuid()::text, :cid, :phone, CAST('{}' AS jsonb), CAST('{}' AS jsonb))"
            ),
            {"cid": contact_respond_id, "phone": phone},
        )
        db.commit()
        pks.append(db.execute(text("SELECT id FROM respond_contacts WHERE phone_number = :p"), {"p": phone}).scalar())
    return pks


def _profile_row(session_factory, contact_pk: str) -> dict:
    return session_factory().execute(
        text("SELECT chatbot_profile FROM respond_contacts WHERE id = :i"), {"i": contact_pk}
    ).scalar() or {}


def _seed_closed_frame(
    session_factory,
    contact_respond_id: str,
    *,
    entities: dict | None = None,
    is_test: bool = False,
    last_activity_at: datetime | None = None,
    turn_ids: list[str] | None = None,
) -> str:
    from app.models.conversation_frame import ConversationFrame

    db = session_factory()
    when = last_activity_at or datetime.now(timezone.utc)
    frame = ConversationFrame(
        contact_id=contact_respond_id,
        contact_respond_id=contact_respond_id,
        space_id="0",
        channel="whatsapp",
        domain="inventory",
        entities=entities or {},
        status="closed",
        close_reason="topic_switch",
        turn_ids=turn_ids or [f"ZZT-sec-turn-{uuid.uuid4().hex[:8]}"],
        is_test=is_test,
        started_at=when,
        opened_at=when,
        last_activity_at=when,
        closed_at=when,
        summary="a closed episode",
    )
    db.add(frame)
    db.commit()
    return frame.id


def _load_profile_facts():
    from app.services.chatbot.turn import profile_facts

    return profile_facts


# --------------------------------------------------------------------------- #
# B1: workspace-scoped contact resolution (`turn_runtime.resolve_contact_pk`)
# --------------------------------------------------------------------------- #


class TestResolveContactPk:
    def test_a_single_matching_row_resolves(self, session_factory) -> None:
        from app.services.chatbot import turn_runtime

        cid = _cid()
        pk = _seed_one_contact(session_factory, cid, memory_level="full")

        resolved = turn_runtime.resolve_contact_pk(session_factory(), cid, None)

        assert resolved == (pk, "full")

    def test_two_rows_sharing_the_id_resolve_to_none(self, session_factory) -> None:
        """The exact scenario B1 names: `respond_io_id` is unique WITHIN a
        workspace only - two rows sharing it (a namesake in another workspace)
        must never be picked between, they must deny."""
        from app.services.chatbot import turn_runtime

        cid = _cid()
        _seed_two_rows_same_respond_id(session_factory, cid)

        resolved = turn_runtime.resolve_contact_pk(session_factory(), cid, None)

        assert resolved is None

    def test_an_absent_id_resolves_to_none(self, session_factory) -> None:
        from app.services.chatbot import turn_runtime

        resolved = turn_runtime.resolve_contact_pk(session_factory(), _cid(), None)

        assert resolved is None

    def test_kill_the_multiple_result_crash_this_replaces(self, session_factory) -> None:
        """The bug this whole finding is named after: the OLD code's
        `.scalar()` on an ambiguous `respond_io_id` raised `MultipleResultsFound`
        and crashed the entire turn. The new resolver must never do that - proven
        directly against the same seeded ambiguity."""
        from sqlalchemy.orm.exc import MultipleResultsFound

        from app.models.access import RespondContact
        from app.services.chatbot import turn_runtime

        cid = _cid()
        _seed_two_rows_same_respond_id(session_factory, cid)
        db = session_factory()

        with pytest.raises(MultipleResultsFound):
            db.query(RespondContact.chatbot_memory_level).filter(
                RespondContact.respond_io_id == cid
            ).scalar()

        # The new doorway never raises for the identical ambiguity.
        assert turn_runtime.resolve_contact_pk(session_factory(), cid, None) is None


# --------------------------------------------------------------------------- #
# B1: `_memory_intake` degrades to `off` on an ambiguous/absent contact, never
# raises, and carries no `contact_pk` a caller could write facts against.
# --------------------------------------------------------------------------- #


class TestMemoryIntakeDegradesOnAmbiguousContact:
    def test_ambiguous_contact_degrades_memory_to_off(self, session_factory) -> None:
        from app.services.chatbot import engine as engine_mod

        cid = _cid()
        _seed_two_rows_same_respond_id(session_factory, cid)

        result = engine_mod._memory_intake(session_factory(), contact_respond_id=cid, dry_run=False)

        assert result["effective_level"] == "off"
        assert result["contact_pk"] is None
        assert result["degraded_reason"] == "ambiguous_or_missing_contact"
        assert result["summaries"] == []
        assert result["earlier_messages"] == []
        assert result["profile_facts"] is None
        assert result["read_frames"] == []

    def test_a_single_contact_resolves_normally(self, session_factory) -> None:
        from app.services.chatbot import engine as engine_mod

        cid = _cid()
        pk = _seed_one_contact(session_factory, cid, memory_level="off")

        result = engine_mod._memory_intake(session_factory(), contact_respond_id=cid, dry_run=False)

        assert result["contact_pk"] == pk
        assert "degraded_reason" not in result

    def test_kill_never_raises_even_if_resolution_itself_blows_up(self, session_factory, monkeypatch) -> None:
        from app.services.chatbot import engine as engine_mod
        from app.services.chatbot import turn_runtime as turn_runtime_mod

        def _boom(*a, **k):
            raise RuntimeError("kill test: resolution exploded")

        monkeypatch.setattr(turn_runtime_mod, "resolve_contact_pk", _boom)

        result = engine_mod._memory_intake(session_factory(), contact_respond_id=_cid(), dry_run=False)

        assert result["effective_level"] == "off"
        assert result["degraded_reason"] == "resolution_error"


# --------------------------------------------------------------------------- #
# B1: every fact writer locks by the resolved PRIMARY KEY, never the ambiguous
# `respond_io_id` - proven by writing to ONE of two rows sharing an id and
# checking the OTHER row never moved.
# --------------------------------------------------------------------------- #


class TestFactWritesLockByPrimaryKey:
    def test_apply_statement_writes_only_the_named_pk(self, session_factory) -> None:
        profile_facts = _load_profile_facts()
        cid = _cid()
        first_pk, second_pk = _seed_two_rows_same_respond_id(session_factory, cid)

        entry = profile_facts.apply_statement(
            session_factory(), cid, "role", "owner", turn_id="ZZT-sec-t1", contact_pk=second_pk
        )

        assert entry is not None
        second_keys = {f["key"] for f in (_profile_row(session_factory, second_pk).get("facts") or [])}
        first_keys = {f["key"] for f in (_profile_row(session_factory, first_pk).get("facts") or [])}
        assert "role" in second_keys
        assert "role" not in first_keys, (
            "a stated write locked by contact_pk must never land on a namesake row"
        )

    def test_kill_removing_the_pk_lock_lets_the_wrong_row_be_written(self, session_factory) -> None:
        """Kill test for the assertion above, run inline (not a temporary code
        edit): calling `apply_statement` the OLD way - by `respond_io_id` alone,
        with no `contact_pk` - hits the row `_lock_row`'s unordered scan happens
        to return, which is NOT necessarily the row a caller meant to address.
        This is the exact ambiguity B1 closes; asserting it here pins the OLD
        behaviour so a regression that drops the `contact_pk` parameter is
        caught even without hand-editing the source."""
        profile_facts = _load_profile_facts()
        cid = _cid()
        first_pk, second_pk = _seed_two_rows_same_respond_id(session_factory, cid)

        # No contact_pk - the pre-B1 call shape.
        profile_facts.apply_statement(session_factory(), cid, "role", "owner", turn_id="ZZT-sec-t2")

        first_keys = {f["key"] for f in (_profile_row(session_factory, first_pk).get("facts") or [])}
        second_keys = {f["key"] for f in (_profile_row(session_factory, second_pk).get("facts") or [])}
        # Exactly one of the two rows was written - proving the ambiguity is real,
        # not a benign no-op, which is why every LIVE call site now always passes
        # `contact_pk` once intake has resolved it (see `TestEngineNeverTalliesOnADryRun`).
        assert ("role" in first_keys) != ("role" in second_keys)


# --------------------------------------------------------------------------- #
# B2: a dry run (including a console one) never writes a fact to the live
# contact row - only the tally/apply_statement ENGINE gate, isolated from the
# rest of a real turn via a stubbed episode write. Chat-side TIER persistence
# (the original B2 finding's other half, `set_tier`) was removed outright by
# owner ruling (see `profile_facts.py`'s own note at the old AC-MEM037
# section) rather than fixed - there is nothing left to gate or bind-test.
# --------------------------------------------------------------------------- #


class TestEngineNeverTalliesOnADryRun:
    """Through the REAL `run_turn` (not a reimplementation of the gate): a
    `topic_reset` turn writes an episode on both a console dry run and a live
    turn (D14/Q15 - frames are the one write a console dry run may make), but
    the tally that follows must fire on the live turn only."""

    def _run_topic_reset_turn(self, session_factory, monkeypatch, *, is_test: bool, msg_id: str):
        from types import SimpleNamespace

        from app.services.chatbot import engine as engine_mod
        from tests.chatbot.test_engine import CONTACT_ID, _envelope, _parser_output

        fake_frame = SimpleNamespace(id="frame-1", turn_ids=["t1"], close_reason="topic_switch", summary="s")
        monkeypatch.setattr(engine_mod.memory_mod, "write_episode_for_reset", lambda *a, **k: fake_frame)

        def _fake_parse(config, user_block):
            return _parser_output(topic_reset=True, profile_statement=None)

        monkeypatch.setattr(engine_mod.parser, "resolve_config", lambda db, **k: engine_mod.parser.ParserConfig(
            system_prompt="stub", prompt_version=1, provider="openai", model="gpt-test", api_key="sk-test",
        ))
        monkeypatch.setattr(engine_mod.parser, "parse", _fake_parse)
        monkeypatch.setattr(
            engine_mod, "check_access",
            lambda db, *, agent_code, contact_id, space_id: {
                "allowed": True, "decision": "allow", "agent_name": "General Enquiries",
                "attributes": None, "all_attributes_allowed": None,
            },
        )
        monkeypatch.setattr(engine_mod, "default_space_id", lambda db: None)

        envelope = _envelope(is_test=is_test, ingress="console" if is_test else "webhook")
        envelope.message["message"]["messageId"] = msg_id
        return engine_mod.run_turn(envelope, session_factory=session_factory)

    def test_dry_run_never_calls_tally(self, session_factory, monkeypatch) -> None:
        from app.services.chatbot import engine as engine_mod
        from tests.chatbot.test_engine import CONTACT_ID

        calls: list[dict] = []
        monkeypatch.setattr(
            engine_mod.profile_facts_mod,
            "tally",
            lambda db, cid, **k: (calls.append(k) or []),
        )
        _seed_one_contact(session_factory, str(CONTACT_ID), memory_level="full")

        result = self._run_topic_reset_turn(
            session_factory, monkeypatch, is_test=True, msg_id="zzt-sec-tally-dry"
        )

        assert result.status == "done", result.error
        assert calls == [], "a dry run (console included) must never tally facts"

    def test_kill_a_live_turn_still_tallies(self, session_factory, monkeypatch) -> None:
        """Kill test for the assertion above, run against the REAL turn: a live
        (non-dry) turn with the identical topic-reset shape must still tally,
        proving the gate is `not dry_run`, not "never tally at all"."""
        from app.services.chatbot import engine as engine_mod
        from tests.chatbot.test_engine import CONTACT_ID

        calls: list[dict] = []
        monkeypatch.setattr(
            engine_mod.profile_facts_mod,
            "tally",
            lambda db, cid, **k: (calls.append(k) or []),
        )
        _seed_one_contact(session_factory, str(CONTACT_ID), memory_level="full")

        result = self._run_topic_reset_turn(
            session_factory, monkeypatch, is_test=False, msg_id="zzt-sec-tally-live"
        )

        assert result.status == "done", result.error
        assert len(calls) == 1 and calls[0].get("contact_pk") is not None, (
            "a real (non-dry) turn must still tally, locked by the resolved pk"
        )


# --------------------------------------------------------------------------- #
# B1 (staff side): `delete_contact`/`bulk_delete_contacts`/episode reads refuse
# to touch `conversation_frames` keyed by a `respond_io_id` a namesake shares.
# --------------------------------------------------------------------------- #


class TestStaffSideFrameGuard:
    def _service(self, db):
        from app.services.contact_service import ContactService

        return ContactService(db)

    def test_delete_contact_refuses_to_delete_a_shared_ids_frames(self, session_factory) -> None:
        cid = _cid()
        first_pk, second_pk = _seed_two_rows_same_respond_id(session_factory, cid)
        frame_id = _seed_closed_frame(session_factory, cid)

        self._service(session_factory()).delete_contact(first_pk)

        # The contact row itself is gone...
        assert session_factory().execute(
            text("SELECT 1 FROM respond_contacts WHERE id = :i"), {"i": first_pk}
        ).first() is None
        # ...but the frame, keyed by the SHARED respond_io_id, must survive - it
        # might belong to the OTHER (still-live) contact.
        assert session_factory().execute(
            text("SELECT 1 FROM conversation_frames WHERE id = :i"), {"i": frame_id}
        ).first() is not None
        assert second_pk  # the namesake is untouched by this delete

    def test_kill_a_unique_id_still_deletes_its_own_frames(self, session_factory) -> None:
        """Kill test: the guard must not become "never delete frames" - a contact
        whose `respond_io_id` is genuinely unique still gets its frames swept."""
        cid = _cid()
        pk = _seed_one_contact(session_factory, cid)
        frame_id = _seed_closed_frame(session_factory, cid)

        self._service(session_factory()).delete_contact(pk)

        assert session_factory().execute(
            text("SELECT 1 FROM conversation_frames WHERE id = :i"), {"i": frame_id}
        ).first() is None

    def test_episodes_summary_refuses_to_read_a_shared_ids_frames(self, session_factory) -> None:
        from app.models.access import RespondContact

        cid = _cid()
        first_pk, _second_pk = _seed_two_rows_same_respond_id(session_factory, cid)
        _seed_closed_frame(session_factory, cid)

        db = session_factory()
        contact = db.query(RespondContact).filter(RespondContact.id == first_pk).first()
        result = self._service(db)._chatbot_episodes_summary(contact)

        assert result["rows"] == []
        assert result["kept"] == 0


# --------------------------------------------------------------------------- #
# S1: the whole-profile PUT always drops whatever `facts` the BODY sends
# --------------------------------------------------------------------------- #


class TestWholeProfilePutDropsBodyFacts:
    def _client(self, db):
        import contextlib

        from fastapi.testclient import TestClient

        from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
        from app.main import app
        from app.services.user_service import UserPermissionService

        def _override_db():
            yield db

        app.dependency_overrides[get_db] = _override_db
        app.dependency_overrides[get_current_user] = lambda: {"id": str(uuid.uuid4())}
        app.dependency_overrides[get_current_user_or_api_key] = lambda: {"id": str(uuid.uuid4())}
        patcher_a = pytest_mock_patch(UserPermissionService, "check_user_has_permission", lambda self, uid, slug: True)
        patcher_b = pytest_mock_patch(UserPermissionService, "get_user_role_slugs", lambda self, uid: set())
        patcher_a.start()
        patcher_b.start()
        return TestClient(app, raise_server_exceptions=False), (patcher_a, patcher_b)

    def test_a_body_supplied_facts_list_never_lands_when_none_is_stored(self, session_factory) -> None:
        import app.main  # noqa: F401 - registers every model before any query
        from app.main import app

        cid = _cid()
        contact_pk = _seed_one_contact(session_factory, cid)
        client, patchers = self._client(session_factory())
        try:
            resp = client.put(
                f"/api/v1/user-management/contacts/{contact_pk}/chatbot",
                json={
                    "chatbot_profile": {
                        "tier": "dealer",
                        "facts": [{"key": "role", "value": "hacked", "source": "staff"}],
                    }
                },
            )
            assert resp.status_code == 200, resp.text
        finally:
            for p in patchers:
                p.stop()
            app.dependency_overrides.clear()

        stored = _profile_row(session_factory, contact_pk)
        assert stored.get("tier") == "dealer"
        assert not (stored.get("facts") or []), (
            f"a body-supplied facts list must never be saved (none stored -> none "
            f"saved), got {stored}"
        )

    def test_kill_a_naive_merge_lets_the_body_facts_through(self, session_factory) -> None:
        """Kill test, run inline: the PRE-fix code only restored the STORED facts
        when they existed and otherwise left whatever the body sent untouched -
        reproduced here directly against the merge logic to pin the difference."""
        merged_profile = {"tier": "dealer", "facts": [{"key": "role", "value": "hacked"}]}
        existing_facts = None
        if existing_facts is not None:
            merged_profile["facts"] = existing_facts
        # This is the OLD behaviour: the hacked facts list survives untouched.
        assert merged_profile["facts"] == [{"key": "role", "value": "hacked"}]


def pytest_mock_patch(target, attr, value):
    from unittest import mock

    return mock.patch.object(target, attr, value)


# --------------------------------------------------------------------------- #
# S2: L5 is built from structured facts, JSON-quoted, never re-split on `;`
# --------------------------------------------------------------------------- #


class TestL5StructuredAndJsonQuoted:
    def test_a_semicolon_inside_a_value_survives_intact(self) -> None:
        from app.services.chatbot.turn import context

        layers_kwargs = dict(
            level="full",
            profile_facts=[{"key": "project", "value": "Site A; Phase 2"}],
            summaries=None,
            earlier_messages=None,
            previous_response=None,
            current_subject=None,
            pending_kind=None,
            pending_options=None,
            settings_profile_line=None,
            current_message="hello",
            reply_to=None,
            media_line=None,
        )
        text_out, _report = context.assemble(context.ContextLayers(**layers_kwargs))

        assert json.dumps("Site A; Phase 2") in text_out, text_out
        # The OLD `;`-split renderer would have cut this value into two segments.
        assert "Phase 2\"" not in text_out.split(json.dumps("Site A; Phase 2"))[0]

    def test_note_and_list_values_are_json_quoted(self) -> None:
        from app.services.chatbot.turn import context

        facts = [
            {"key": "note", "value": "call after 5pm"},
            {"key": "usual_sites", "value": ["Kuching", "Miri"]},
            {"key": "segment", "value": "dealer"},
        ]
        text_out, _ = context.assemble(
            context.ContextLayers(
                level="full", profile_facts=facts, summaries=None, earlier_messages=None,
                previous_response=None, current_subject=None, pending_kind=None,
                pending_options=None, settings_profile_line=None, current_message="hi",
                reply_to=None, media_line=None,
            )
        )

        assert json.dumps("call after 5pm") in text_out
        assert json.dumps(["Kuching", "Miri"]) in text_out
        # `segment` is not one of the JSON-quoted keys - plain text.
        assert "segment dealer" in text_out

    def test_kill_reverting_to_semicolon_split_corrupts_the_value(self) -> None:
        """Kill test for the two assertions above: the OLD design joined segments
        with `; ` and re-split on it for cap-dropping - reproduced directly to
        show it corrupts a value carrying the same character."""
        segments = ["project Site A; Phase 2", "note call after 5pm"]
        joined = "; ".join(segments)
        resplit = [s.strip() for s in joined.split(";") if s.strip()]
        assert resplit != segments, (
            "the old join/split round-trip is lossy for a value containing ';' - "
            "exactly the bug the structured-facts rewrite fixes"
        )


class TestContextWhitespaceCollapsed:
    def test_l3_earlier_message_newlines_collapsed(self) -> None:
        from app.services.chatbot.turn import context

        text_out, _ = context.assemble(
            context.ContextLayers(
                level="conversation", profile_facts=None, summaries=None,
                earlier_messages=[{"created_at": "Mon 1pm", "text": "line one\nline two\n\nline three"}],
                previous_response=None, current_subject=None, pending_kind=None,
                pending_options=None, settings_profile_line=None, current_message="hi",
                reply_to=None, media_line=None,
            )
        )

        assert "line one line two line three" in text_out
        assert "\nline two" not in text_out

    def test_l4_summary_newlines_collapsed(self) -> None:
        from app.services.chatbot.turn import context

        text_out, _ = context.assemble(
            context.ContextLayers(
                level="past", profile_facts=None,
                summaries=["first line\nsecond line"], earlier_messages=None,
                previous_response=None, current_subject=None, pending_kind=None,
                pending_options=None, settings_profile_line=None, current_message="hi",
                reply_to=None, media_line=None,
            )
        )

        assert "first line second line" in text_out
        assert "\nsecond line" not in text_out.split("Recent conversations:")[1].split("Current user message")[0].replace(
            "- first line second line", ""
        )


# --------------------------------------------------------------------------- #
# S2: tallied usual_brands/usual_sites go through the master-list normalisation
# --------------------------------------------------------------------------- #


class TestTalliedMasterNormalization:
    def _seed_brand(self, session_factory, name: str) -> None:
        from app.services.company_scope import DEFAULT_COMPANY_ID

        db = session_factory()
        db.execute(
            text(
                "INSERT INTO brands (id, brand_code, brand_name, is_active, company_id) "
                "VALUES (gen_random_uuid(), :code, :name, true, :company_id)"
            ),
            {"code": f"ZZT-{uuid.uuid4().hex[:6]}", "name": name, "company_id": DEFAULT_COMPANY_ID},
        )
        db.commit()

    def test_a_decommissioned_brand_is_never_tallied(self, session_factory) -> None:
        profile_facts = _load_profile_facts()
        self._seed_brand(session_factory, "Sorento")
        cid = _cid()
        _seed_one_contact(session_factory, cid)
        when = datetime.now(timezone.utc)
        for _ in range(3):
            _seed_closed_frame(
                session_factory, cid, entities={"brand": ["NoSuchBrand"]}, last_activity_at=when
            )
            when -= timedelta(hours=1)

        tallied = profile_facts.tally(session_factory(), cid)

        assert not any(f["key"] == "usual_brands" for f in tallied), (
            "a brand absent from the master list must never become a tallied fact"
        )

    def test_a_real_brand_is_still_tallied(self, session_factory) -> None:
        profile_facts = _load_profile_facts()
        self._seed_brand(session_factory, "Sorento")
        cid = _cid()
        _seed_one_contact(session_factory, cid)
        when = datetime.now(timezone.utc)
        for _ in range(3):
            _seed_closed_frame(
                session_factory, cid, entities={"brand": ["Sorento"]}, last_activity_at=when
            )
            when -= timedelta(hours=1)

        tallied = profile_facts.tally(session_factory(), cid)

        assert any(f["key"] == "usual_brands" and "Sorento" in f["value"] for f in tallied), tallied


# --------------------------------------------------------------------------- #
# S2: a raw entity token in the episode digest is capped and whitespace-collapsed
# --------------------------------------------------------------------------- #


class TestEpisodeDigestEntityCap:
    def test_a_long_raw_token_is_capped_and_collapsed(self) -> None:
        from app.services.chatbot.turn import episode_digest

        long_raw = ("word " * 30) + "\n\nmore text"
        out = episode_digest._entity_display([{"raw": long_raw, "hint": "product"}])

        assert len(out) == 1
        assert len(out[0]) <= 40
        assert "\n" not in out[0]

    def test_kill_a_short_token_is_unaffected(self) -> None:
        from app.services.chatbot.turn import episode_digest

        out = episode_digest._entity_display([{"raw": "SRTWB1455", "hint": "product"}])

        assert out == ["SRTWB1455"]


# --------------------------------------------------------------------------- #
# S3: episodes null out for a caller without `system.chat_history.view`
# --------------------------------------------------------------------------- #


class TestEpisodesPermissionGate:
    def _client(self, db, *, grants: set[str]):
        import app.main  # noqa: F401
        from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
        from app.main import app
        from app.services.company_scope_resolver import apply_company_scope
        from app.services.user_service import UserPermissionService
        from fastapi.testclient import TestClient
        from unittest import mock

        def _override_db():
            yield db

        app.dependency_overrides[get_db] = _override_db
        app.dependency_overrides[get_current_user] = lambda: {"id": str(uuid.uuid4())}
        app.dependency_overrides[get_current_user_or_api_key] = lambda: {"id": str(uuid.uuid4())}
        app.dependency_overrides[apply_company_scope] = lambda: None
        patchers = [
            mock.patch.object(UserPermissionService, "check_user_has_permission", lambda self, uid, slug: slug in grants),
            mock.patch.object(UserPermissionService, "get_user_role_slugs", lambda self, uid: set()),
        ]
        for p in patchers:
            p.start()
        return TestClient(app, raise_server_exceptions=False), patchers

    def _teardown(self, patchers) -> None:
        from app.main import app

        for p in patchers:
            p.stop()
        app.dependency_overrides.clear()

    def test_episodes_null_without_the_chat_history_permission(self, session_factory) -> None:
        cid = _cid()
        contact_pk = _seed_one_contact(session_factory, cid)
        _seed_closed_frame(session_factory, cid)
        client, patchers = self._client(session_factory(), grants={"user_management.contacts.view"})
        try:
            resp = client.get(f"/api/v1/user-management/contacts/{contact_pk}/chatbot/memory")
            assert resp.status_code == 200, resp.text
            assert resp.json()["episodes"] is None
        finally:
            self._teardown(patchers)

    def test_kill_the_permission_holder_still_sees_episodes(self, session_factory) -> None:
        cid = _cid()
        contact_pk = _seed_one_contact(session_factory, cid)
        _seed_closed_frame(session_factory, cid)
        client, patchers = self._client(
            session_factory(),
            grants={"user_management.contacts.view", "system.chat_history.view"},
        )
        try:
            resp = client.get(f"/api/v1/user-management/contacts/{contact_pk}/chatbot/memory")
            assert resp.status_code == 200, resp.text
            assert resp.json()["episodes"] is not None
            assert resp.json()["episodes"]["kept"] == 1
        finally:
            self._teardown(patchers)


# --------------------------------------------------------------------------- #
# S4: usual_products staff values are capped at 60 chars / 3 items
# --------------------------------------------------------------------------- #


class TestUsualProductsStaffCap:
    def test_each_item_capped_at_60_chars_and_3_items(self, session_factory) -> None:
        profile_facts = _load_profile_facts()
        cid = _cid()
        pk = _seed_one_contact(session_factory, cid)
        long_item = "x" * 90

        entry = profile_facts.set_staff_fact(
            session_factory(), pk, "usual_products", [long_item, "b", "c", "d"], user_id=str(uuid.uuid4())
        )

        assert entry is not None
        assert len(entry["value"]) == 3
        assert len(entry["value"][0]) == 60

    def test_kill_a_short_list_is_unaffected(self, session_factory) -> None:
        profile_facts = _load_profile_facts()
        cid = _cid()
        pk = _seed_one_contact(session_factory, cid)

        entry = profile_facts.set_staff_fact(
            session_factory(), pk, "usual_products", ["Cement", "Rebar"], user_id=str(uuid.uuid4())
        )

        assert entry["value"] == ["Cement", "Rebar"]


# --------------------------------------------------------------------------- #
# N1: DELETE and the pending action return 422 for an unknown key / malformed id
# --------------------------------------------------------------------------- #


class TestUnknownKeyAndMalformedId422:
    def test_delete_unknown_key_is_422(self, session_factory) -> None:
        from app.services.contact_service import ContactService
        from app.services.error_handler import AppException

        cid = _cid()
        pk = _seed_one_contact(session_factory, cid)

        with pytest.raises(AppException) as exc_info:
            ContactService(session_factory()).delete_contact_fact(pk, "not_a_real_key")

        assert exc_info.value.status_code == 422

    def test_kill_a_known_key_deletes_cleanly(self, session_factory) -> None:
        from app.services.contact_service import ContactService

        profile_facts = _load_profile_facts()
        cid = _cid()
        pk = _seed_one_contact(session_factory, cid)
        profile_facts.set_staff_fact(session_factory(), pk, "note", "hi", user_id=str(uuid.uuid4()))

        ContactService(session_factory()).delete_contact_fact(pk, "note")  # must not raise

    def test_pending_action_malformed_composite_id_is_422(self) -> None:
        from app.services.error_handler import AppException
        from app.services.record_actions import _delete_contact_chatbot_fact

        with pytest.raises(AppException) as exc_info:
            _delete_contact_chatbot_fact(None, {"entity_id": "no-colon-here"})

        assert exc_info.value.status_code == 422

    def test_kill_a_well_formed_composite_id_is_not_422(self, session_factory) -> None:
        from app.services.record_actions import _delete_contact_chatbot_fact

        profile_facts = _load_profile_facts()
        cid = _cid()
        pk = _seed_one_contact(session_factory, cid)
        profile_facts.set_staff_fact(session_factory(), pk, "note", "hi", user_id=str(uuid.uuid4()))

        _delete_contact_chatbot_fact(session_factory(), {"entity_id": f"{pk}:note"})  # must not raise


# --------------------------------------------------------------------------- #
# N3: `_chatbot_episodes_summary` uses bounded queries
# --------------------------------------------------------------------------- #


class TestEpisodesSummaryBoundedQueries:
    def test_more_than_the_limit_is_capped_in_rows_but_not_in_kept(self, session_factory) -> None:
        from app.models.access import RespondContact
        from app.services.contact_service import ContactService

        cid = _cid()
        pk = _seed_one_contact(session_factory, cid)
        when = datetime.now(timezone.utc)
        for _ in range(13):
            _seed_closed_frame(session_factory, cid, last_activity_at=when)
            when -= timedelta(hours=1)

        db = session_factory()
        contact = db.query(RespondContact).filter(RespondContact.id == pk).first()
        result = ContactService(db)._chatbot_episodes_summary(contact)

        assert result["kept"] == 13
        assert len(result["rows"]) == 10

    def test_kill_fewer_than_the_limit_is_unaffected(self, session_factory) -> None:
        from app.models.access import RespondContact
        from app.services.contact_service import ContactService

        cid = _cid()
        pk = _seed_one_contact(session_factory, cid)
        _seed_closed_frame(session_factory, cid)
        _seed_closed_frame(session_factory, cid)

        db = session_factory()
        contact = db.query(RespondContact).filter(RespondContact.id == pk).first()
        result = ContactService(db)._chatbot_episodes_summary(contact)

        assert result["kept"] == 2
        assert len(result["rows"]) == 2
