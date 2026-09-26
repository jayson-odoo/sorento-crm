"""Slice C - ``ideate`` brain-path turn endpoint + service + confirmation gate.

Keys back to ``documentation/plans/ideation/ideation-ideate-intent-acceptance-criteria.md``:

- **AC-10 [BE]** - the service returns ``{ status, reply_text, link?, session_vars }``
  (full updated blob) from one ``create_idea`` call.
- **AC-11 / AC-11b [BE][T]** - the §5.1 input is built deterministically
  (``product_id`` from the workspace binding, ``submitter`` = contact phone E.164)
  and carries the brain-extracted ``{ fields, remove, confirm }`` (D-CONFIRM).
- **AC-12 [BE][T]** - first turn omits ``draft_id`` and persists
  ``session_vars.ideation = { draft_id, status, missing, updated_at }``.
- **AC-12b [BE][T]** - ``review`` KEEPS the pointer (never cleared before confirm),
  even for a one-shot-complete turn that routes through ``review``.
- **AC-13 [BE][T]** - a continuation passes ``draft_id`` through (idempotent enrich).
- **AC-13b [BE][T]** - a revise loop survives ≥3 turns keeping ``review``.
- **AC-13c / AC-14 [BE][T]** - explicit confirm → ``complete`` + ``link``, and ONLY
  then is ``session_vars.ideation`` cleared.
- **AC-15 [BE][T]** - ``duplicate`` clears the pointer and relays the tool's copy.
- **AC-16 [BE][T]** - read-modify-write preserves every other CRM session_vars key.
- **AC-17 [BE][T]** - resume-by-``draft_id`` after an interrupt (open draft intact).
- **AC-19 [BE]** - a shared-service outage returns a graceful reply, never a 500,
  and never mutates session_vars.
- **AC-31 [BE][T]** - no ``ideation_product_id`` → fail-closed, no ``create_idea`` call.
- **AC-20 [BE]** - the endpoint writes an ``integration_log`` on success AND failure.

The brain extractor's LLM output is STUBBED; the httpx ``create_idea`` call is
STUBBED (monkeypatched wrapper). No live LLM, no live shared-service, no real DB
for the service tests - session_vars I/O is faked so the merge logic is asserted
byte-for-byte. AC-11b's live-LLM extraction quality is DEFERRED to the opt-in
harness (the deterministic ``confirm``-guard is tested here).
"""
from __future__ import annotations

import uuid
from dataclasses import replace

import httpx
import pytest

import app.services.ideation_turn_service as svc
from app.models.access import ContactAccessType, RespondContact, respond_contact_access_types
from app.services.ideation_extractor import IdeateExtraction
from app.services.ideation_turn_service import IdeationServiceError, handle_turn
from tests._pg_fixture import blank_session


# --------------------------------------------------------------------------- #
# Fakes / seams                                                               #
# --------------------------------------------------------------------------- #


class _FakeContact:
    def __init__(self, phone_number: str, session_vars: dict, display_name=None, submitter_tier=None):
        self.phone_number = phone_number
        self.session_vars = session_vars
        self.display_name = display_name
        self.submitter_tier = submitter_tier


@pytest.fixture
def wired(monkeypatch):
    """Wire every DB/LLM/HTTP seam of the turn service to in-memory fakes.

    Returns a small harness object exposing:
    - ``store``: the current session_vars blob (mutated on overwrite)
    - ``payloads``: every create_idea payload the service built
    - ``set_contact(phone, session_vars)``
    - ``set_extraction(fields, remove, confirm)``
    - ``set_create_idea(result_or_exc)``
    - ``set_product_id(pid)``
    """

    state = {
        "phone": "+60123456789",
        "display_name": None,
        "submitter_tier": None,
        "store": {},
        "extraction": IdeateExtraction(fields={}, remove=[], confirm=False),
        "create_idea_result": None,
        "product_id": "prod-uuid-1",
        "payloads": [],
        "overwrites": [],
    }

    def _fake_get_contact_row(_db, respond_io_id):  # noqa: ANN001
        return _FakeContact(
            state["phone"],
            dict(state["store"]),
            display_name=state["display_name"],
            submitter_tier=state["submitter_tier"],
        )

    def _fake_resolve_ideation_config(_db):  # noqa: ANN001
        # Base URL + intake key come from settings (so the settings-fallback
        # tests still exercise a blank => fail-closed path); the product binding
        # comes from the harness state (set_product_id / fail-closed tests).
        base_url = (svc.settings.ideation_shared_service_url or "").strip() or None
        api_key = (svc.settings.ideation_intake_api_key or "").strip() or None
        return svc._IdeationConfig(
            base_url=base_url, api_key=api_key, product_id=state["product_id"]
        )

    def _fake_extract(_db, **_kw):  # noqa: ANN001
        # Mirrors the real extractor's derivation (AC-1201/AC-1208/AC-1211):
        # confirm is derived from review_action + status here, not settable
        # directly, so a test's `review_action="submit"` behaves exactly like
        # production once the pointer's status is threaded through.
        base = state["extraction"]
        confirm = bool(base.review_action == "submit" and _kw.get("status") == "review")
        return replace(base, confirm=confirm)

    def _fake_call_create_idea(_base_url, _api_key, payload):  # noqa: ANN001
        state["payloads"].append(payload)
        res = state["create_idea_result"]
        if isinstance(res, Exception):
            raise res
        return res

    # overwrite_for_contact(db, *, respond_io_id, state) - capture + persist so
    # multi-turn chains read the written blob back on the next turn.
    def _overwrite_capture(_db, *, respond_io_id, state):  # noqa: ANN001
        state_copy = dict(state)
        globals_store.clear()
        globals_store.update(state_copy)
        overwrites.append(state_copy)
        return state_copy

    globals_store = state["store"]
    overwrites = state["overwrites"]

    monkeypatch.setattr(svc, "_get_contact_row", _fake_get_contact_row)
    monkeypatch.setattr(svc, "_resolve_ideation_config", _fake_resolve_ideation_config)
    monkeypatch.setattr(svc, "extract_ideate_turn", _fake_extract)
    monkeypatch.setattr(svc, "call_create_idea", _fake_call_create_idea)
    monkeypatch.setattr(svc.settings, "ideation_shared_service_url", "https://shared.test")
    monkeypatch.setattr(svc.settings, "ideation_intake_api_key", "intake-key")

    class _Harness:
        def __init__(self):
            self.store = state["store"]
            self.payloads = state["payloads"]
            self.overwrites = state["overwrites"]

        def set_contact(self, phone, session_vars):
            state["phone"] = phone
            state["store"].clear()
            state["store"].update(session_vars)

        def set_session_vars(self, session_vars):
            state["store"].clear()
            state["store"].update(session_vars)

        def set_extraction(
            self,
            fields=None,
            remove=None,
            skip=None,
            title="",
            review_action="none",
            change_text="",
            duplicate_choice="none",
        ):
            state["extraction"] = IdeateExtraction(
                fields=fields or {},
                remove=remove or [],
                skip=skip or [],
                title=title,
                review_action=review_action,
                change_text=change_text,
                duplicate_choice=duplicate_choice,
            )

        def set_create_idea(self, result):
            state["create_idea_result"] = result

        def set_product_id(self, pid):
            state["product_id"] = pid

        def set_display_name(self, name):
            state["display_name"] = name

        def set_submitter_tier(self, tier):
            state["submitter_tier"] = tier

    harness = _Harness()
    monkeypatch.setattr(svc, "overwrite_for_contact", _overwrite_capture)
    return harness


def _turn(**kw):
    kw.setdefault("respond_io_id", "rio-1")
    kw.setdefault("message_text", "I wish it could remind me before a PO expires")
    return handle_turn(None, **kw)


# --------------------------------------------------------------------------- #
# AC-12 - first turn: no draft_id, persist collecting pointer                  #
# --------------------------------------------------------------------------- #
def test_first_turn_collecting_persists_pointer(wired):
    wired.set_session_vars({})
    wired.set_create_idea(
        {
            "draft_id": "d-1",
            "status": "collecting",
            "captured": {"what": "PO expiry reminder"},
            "missing": ["module", "who"],
            "reply_text": "Got it - which module?",
        }
    )
    out = _turn()

    assert out["status"] == "collecting"
    assert out["reply_text"] == "Got it - which module?"
    assert "link" not in out
    # AC-12: draft_id omitted on turn 1
    assert "draft_id" not in wired.payloads[0]
    # AC-12: pointer persisted with the §5.2 shape
    ideation = out["session_vars"]["ideation"]
    assert ideation["draft_id"] == "d-1"
    assert ideation["status"] == "collecting"
    assert ideation["missing"] == ["module", "who"]
    assert "updated_at" in ideation


# --------------------------------------------------------------------------- #
# AC-11 / AC-11b - deterministic input shape + brain extraction passthrough    #
# --------------------------------------------------------------------------- #
def test_input_shape_and_extraction_passthrough(wired):
    wired.set_session_vars({})
    wired.set_extraction(fields={"module": "procurement"}, remove=["who"])
    wired.set_create_idea(
        {"draft_id": "d-1", "status": "collecting", "captured": {}, "missing": [], "reply_text": "ok"}
    )
    _turn(message_text="module is procurement, forget who")

    p = wired.payloads[0]
    assert p["product_id"] == "prod-uuid-1"
    # WS-A: the shared-service CreateIdeaIn field is ``submitter_contact_id`` (accepts
    # a phone E.164). The legacy ``submitter`` key was silently dropped → "Unknown".
    assert p["submitter_contact_id"] == "+60123456789"
    assert "submitter" not in p
    assert p["message_text"] == "module is procurement, forget who"
    assert p["fields"] == {"module": "procurement"}
    assert p["remove"] == ["who"]
    assert p["confirm"] is False


# --------------------------------------------------------------------------- #
# WS-A / AC-CAP-1..3 - submitter name from the CRM contact, n8n fallback       #
# --------------------------------------------------------------------------- #
def test_submitter_name_from_crm_contact(wired):
    """respond_contacts name wins → passed as submitter_name."""
    wired.set_session_vars({})
    wired.set_display_name("Aisha Rahman")
    wired.set_create_idea(
        {"draft_id": "d-1", "status": "collecting", "captured": {}, "missing": [], "reply_text": "ok"}
    )
    _turn(submitter_name="WA Profile Name")  # n8n value present but DB wins
    assert wired.payloads[0]["submitter_name"] == "Aisha Rahman"


def test_submitter_name_falls_back_to_n8n(wired):
    """No CRM name → the n8n Respond.io-profile name is used."""
    wired.set_session_vars({})
    wired.set_display_name(None)
    wired.set_create_idea(
        {"draft_id": "d-1", "status": "collecting", "captured": {}, "missing": [], "reply_text": "ok"}
    )
    _turn(submitter_name="WA Profile Name")
    assert wired.payloads[0]["submitter_name"] == "WA Profile Name"


def test_submitter_name_absent_when_both_blank(wired):
    """Neither source → no submitter_name key (shared-service serializes 'Unknown')."""
    wired.set_session_vars({})
    wired.set_display_name(None)
    wired.set_create_idea(
        {"draft_id": "d-1", "status": "collecting", "captured": {}, "missing": [], "reply_text": "ok"}
    )
    _turn(submitter_name=None)
    assert "submitter_name" not in wired.payloads[0]


# --------------------------------------------------------------------------- #
# WS-B / AC-CAP-5..7 - raw_transcript accumulates across turns                 #
# --------------------------------------------------------------------------- #
def test_raw_transcript_accumulates_over_turns(wired):
    """Each turn appends to the transcript; the payload carries the WHOLE convo,
    not just the finalizing message. The pointer persists the running list."""
    # Turn 1 - collecting, transcript = [msg1]
    wired.set_session_vars({})
    wired.set_create_idea(
        {"draft_id": "d-7", "status": "collecting", "captured": {}, "missing": ["impact"], "reply_text": "ok"}
    )
    out1 = _turn(message_text="I want AI to update contractors on delivery")
    assert wired.payloads[-1]["raw_transcript"] == "I want AI to update contractors on delivery"
    assert out1["session_vars"]["ideation"]["transcript"] == [
        "I want AI to update contractors on delivery"
    ]

    # Turn 2 - continuation adds a substantive turn.
    wired.set_create_idea(
        {"draft_id": "d-7", "status": "review", "captured": {}, "missing": [], "reply_text": "confirm?"}
    )
    _turn(message_text="impact is high ROI")
    assert wired.payloads[-1]["raw_transcript"] == (
        "I want AI to update contractors on delivery\nimpact is high ROI"
    )

    # Turn 3 - the finalizing "confirm" turn: transcript still holds the prior turns.
    wired.set_create_idea(
        {"draft_id": "d-7", "status": "complete", "captured": {}, "missing": [], "reply_text": "done",
         "link": "https://fe-sorento.foundryx.my/ideas/d-7"}
    )
    _turn(message_text="okay i confirm")
    assert wired.payloads[-1]["raw_transcript"] == (
        "I want AI to update contractors on delivery\n"
        "impact is high ROI\n"
        "okay i confirm"
    )


# --------------------------------------------------------------------------- #
# AC-12b - review KEEPS the pointer (one-shot complete still routes review)    #
# --------------------------------------------------------------------------- #
def test_review_keeps_pointer(wired):
    wired.set_session_vars({})
    wired.set_create_idea(
        {
            "draft_id": "d-1",
            "status": "review",
            "captured": {"what": "x", "module": "y", "who": "z"},
            "missing": [],
            "reply_text": "Here's the summary - confirm or revise?",
        }
    )
    out = _turn()

    assert out["status"] == "review"
    assert out["session_vars"]["ideation"]["status"] == "review"
    assert out["session_vars"]["ideation"]["draft_id"] == "d-1"
    assert out["session_vars"]["ideation"]["missing"] == []
    assert "link" not in out


# --------------------------------------------------------------------------- #
# AC-13 - continuation passes draft_id through (idempotent enrich)             #
# --------------------------------------------------------------------------- #
def test_continuation_passes_draft_id(wired):
    wired.set_session_vars(
        {"ideation": {"draft_id": "d-1", "status": "collecting", "missing": ["who"], "updated_at": "t"}}
    )
    wired.set_create_idea(
        {"draft_id": "d-1", "status": "collecting", "captured": {}, "missing": [], "reply_text": "ok"}
    )
    _turn(message_text="the sales team")

    assert wired.payloads[0]["draft_id"] == "d-1"


# --------------------------------------------------------------------------- #
# Continuity - caller-supplied session_vars is trusted over the DB copy        #
# (the accumulation bug: n8n's last-writer PUT nests ideation under            #
# `variables`, so the endpoint's top-level DB read missed it and minted a new  #
# draft every turn). The fix: read the pointer from session_vars_in first.     #
# --------------------------------------------------------------------------- #
def test_caller_session_vars_continues_draft_when_db_copy_empty(wired):
    # DB copy has NO ideation (n8n overwrote the column with its nested shape).
    wired.set_session_vars({})
    wired.set_create_idea(
        {"draft_id": "d-1", "status": "collecting", "captured": {}, "missing": [], "reply_text": "ok"}
    )
    # n8n hands the prior pointer back on the request - top-level shape.
    _turn(
        message_text="department is general",
        session_vars_in={
            "ideation": {"draft_id": "d-1", "status": "collecting", "missing": ["department"]}
        },
    )
    # core assertion: the existing draft continues (no fresh draft minted).
    assert wired.payloads[0]["draft_id"] == "d-1"


def test_caller_session_vars_nested_under_variables(wired):
    # n8n's real persisted shape nests everything under `variables`.
    wired.set_session_vars({})
    wired.set_create_idea(
        {"draft_id": "d-1", "status": "collecting", "captured": {}, "missing": [], "reply_text": "ok"}
    )
    _turn(
        message_text="department is general",
        session_vars_in={
            "variables": {
                "ideation": {"draft_id": "d-1", "status": "collecting", "missing": ["department"]}
            }
        },
    )
    assert wired.payloads[0]["draft_id"] == "d-1"


# --------------------------------------------------------------------------- #
# AC-13b - revise loop survives ≥3 turns keeping review                        #
# --------------------------------------------------------------------------- #
def test_revise_loop_survives_three_turns(wired):
    # turn 1 - incomplete → collecting
    wired.set_session_vars({})
    wired.set_extraction(fields={"what": "reminder"})
    wired.set_create_idea(
        {"draft_id": "d-9", "status": "collecting", "captured": {}, "missing": ["module"], "reply_text": "which module?"}
    )
    o1 = _turn()
    assert o1["session_vars"]["ideation"]["status"] == "collecting"

    # turn 2 - now complete → review
    wired.set_extraction(fields={"module": "procurement"})
    wired.set_create_idea(
        {"draft_id": "d-9", "status": "review", "captured": {}, "missing": [], "reply_text": "confirm?"}
    )
    o2 = _turn(message_text="procurement")
    assert o2["session_vars"]["ideation"]["status"] == "review"

    # turn 3 - revise → stays review
    wired.set_extraction(fields={"module": "inventory"})
    wired.set_create_idea(
        {"draft_id": "d-9", "status": "review", "captured": {}, "missing": [], "reply_text": "confirm?"}
    )
    o3 = _turn(message_text="actually make it inventory")
    assert o3["session_vars"]["ideation"]["status"] == "review"
    assert o3["session_vars"]["ideation"]["draft_id"] == "d-9"
    # every continuation carried the draft_id
    assert all(p.get("draft_id") == "d-9" for p in wired.payloads[1:])


# --------------------------------------------------------------------------- #
# AC-13c / AC-14 - explicit confirm → complete + link, THEN clear             #
# --------------------------------------------------------------------------- #
def test_confirm_completes_and_clears(wired):
    wired.set_session_vars(
        {"ideation": {"draft_id": "d-1", "status": "review", "missing": [], "updated_at": "t"}}
    )
    wired.set_extraction(review_action="submit")
    wired.set_create_idea(
        {
            "draft_id": "d-1",
            "status": "complete",
            "captured": {},
            "missing": [],
            "reply_text": "Logged! Track it here.",
            "link": "https://fe-sorento.foundryx.my/ideas/123",
        }
    )
    out = _turn(message_text="yes that's correct")

    assert out["status"] == "complete"
    assert out["link"] == "https://fe-sorento.foundryx.my/ideas/123"
    assert wired.payloads[0]["confirm"] is True
    # AC-14: pointer cleared only now
    assert "ideation" not in out["session_vars"]


# --------------------------------------------------------------------------- #
# AC-1215 - voted/cancelled clear the pointer too; `duplicate` is retired      #
# --------------------------------------------------------------------------- #
def test_voted_clears_pointer(wired):
    wired.set_session_vars(
        {
            "ideation": {
                "draft_id": "d-1",
                "status": "duplicate_candidate",
                "missing": [],
                "updated_at": "t",
                "duplicate_candidate": {"idea_number": "IDEA-0077", "title": "Existing idea"},
            }
        }
    )
    wired.set_extraction(duplicate_choice="vote")
    wired.set_create_idea(
        {
            "draft_id": "d-1",
            "status": "voted",
            "captured": {},
            "missing": [],
            "reply_text": "Got it - I've voted for the existing idea.",
            "idea_number": "IDEA-0077",
        }
    )
    out = _turn(message_text="vote for that one")

    assert out["status"] == "voted"
    assert wired.payloads[0]["duplicate_choice"] == "vote"
    assert "ideation" not in out["session_vars"]


def test_cancelled_clears_pointer(wired):
    wired.set_session_vars(
        {"ideation": {"draft_id": "d-1", "status": "collecting", "missing": [], "updated_at": "t"}}
    )
    wired.set_extraction(review_action="cancel")
    wired.set_create_idea(
        {
            "draft_id": "d-1",
            "status": "cancelled",
            "captured": {},
            "missing": [],
            "reply_text": "No worries, I've dropped that idea.",
        }
    )
    out = _turn(message_text="actually never mind, cancel")

    assert out["status"] == "cancelled"
    assert wired.payloads[0]["cancel"] is True
    assert "ideation" not in out["session_vars"]


# =============================================================================
# S2 - sorento payload, title, duplicate ask, semantic review
# documentation/plans/ideation/ideation-intake-redesign-24sep-acceptance-criteria.md
# =============================================================================


# --------------------------------------------------------------------------- #
# AC-1203 - skip rides the payload untouched from the extraction               #
# --------------------------------------------------------------------------- #
def test_skip_passthrough_on_payload(wired):
    wired.set_session_vars(
        {"ideation": {"draft_id": "d-1", "status": "collecting", "missing": [], "next_field": "impact", "updated_at": "t"}}
    )
    wired.set_extraction(skip=["impact"])
    wired.set_create_idea(
        {"draft_id": "d-1", "status": "review", "captured": {}, "missing": [], "reply_text": "ok"}
    )
    _turn(message_text="dunno lah, can skip this one?")
    assert wired.payloads[0]["skip"] == ["impact"]


# --------------------------------------------------------------------------- #
# AC-1206 - department rides fields as typed free text, no lookup              #
# --------------------------------------------------------------------------- #
def test_department_passthrough_as_typed_free_text(wired):
    wired.set_session_vars({})
    wired.set_extraction(fields={"problem": "stock alerts", "department": "warehouse team"})
    wired.set_create_idea(
        {"draft_id": "d-1", "status": "collecting", "captured": {}, "missing": [], "reply_text": "ok"}
    )
    _turn(message_text="i have an idea, our warehouse team needs stock alerts")
    assert wired.payloads[0]["fields"]["department"] == "warehouse team"


# --------------------------------------------------------------------------- #
# AC-1207 - submitter_tier is the first access-type code, omitted when none    #
# --------------------------------------------------------------------------- #
def test_submitter_tier_included_when_contact_has_one(wired):
    wired.set_session_vars({})
    wired.set_submitter_tier("dealer")
    wired.set_create_idea(
        {"draft_id": "d-1", "status": "collecting", "captured": {}, "missing": [], "reply_text": "ok"}
    )
    _turn()
    assert wired.payloads[0]["submitter_tier"] == "dealer"


def test_submitter_tier_omitted_when_contact_has_none(wired):
    wired.set_session_vars({})
    wired.set_submitter_tier(None)
    wired.set_create_idea(
        {"draft_id": "d-1", "status": "collecting", "captured": {}, "missing": [], "reply_text": "ok"}
    )
    _turn()
    assert "submitter_tier" not in wired.payloads[0]


# --------------------------------------------------------------------------- #
# AC-1208 / AC-1211 - submit only counts in review; cancel at any status       #
# --------------------------------------------------------------------------- #
def test_submit_word_confirms_only_in_review(wired):
    wired.set_session_vars(
        {"ideation": {"draft_id": "d-1", "status": "review", "missing": [], "updated_at": "t"}}
    )
    wired.set_extraction(review_action="submit")
    wired.set_create_idea(
        {"draft_id": "d-1", "status": "complete", "captured": {}, "missing": [], "reply_text": "done", "link": "L"}
    )
    _turn(message_text="can you just submit it already")
    assert wired.payloads[0]["confirm"] is True


def test_submit_word_outside_review_does_not_confirm(wired):
    """AC-1211 (existing AC-11b guard, kept): review_action='submit' emitted
    outside review must never set confirm=True."""
    wired.set_session_vars(
        {"ideation": {"draft_id": "d-1", "status": "collecting", "missing": [], "updated_at": "t"}}
    )
    wired.set_extraction(review_action="submit")
    wired.set_create_idea(
        {"draft_id": "d-1", "status": "collecting", "captured": {}, "missing": [], "reply_text": "ok"}
    )
    _turn(message_text="submit")
    assert wired.payloads[0]["confirm"] is False


def test_cancel_honoured_outside_review(wired):
    """AC-1211: a user may drop a draft at any step, not only while reviewing."""
    wired.set_session_vars(
        {"ideation": {"draft_id": "d-1", "status": "collecting", "missing": ["impact"], "updated_at": "t"}}
    )
    wired.set_extraction(review_action="cancel")
    wired.set_create_idea(
        {"draft_id": "d-1", "status": "cancelled", "captured": {}, "missing": [], "reply_text": "dropped"}
    )
    _turn(message_text="actually never mind, cancel")
    assert wired.payloads[0]["cancel"] is True


# --------------------------------------------------------------------------- #
# AC-1209 - a review-turn change request carries confirm=false                 #
# --------------------------------------------------------------------------- #
def test_change_request_in_review_does_not_confirm(wired):
    wired.set_session_vars(
        {"ideation": {"draft_id": "d-1", "status": "review", "missing": [], "updated_at": "t"}}
    )
    wired.set_extraction(
        fields={"impact": "faster checkout"},
        review_action="change",
        change_text="change the impact to faster checkout",
    )
    wired.set_create_idea(
        {"draft_id": "d-1", "status": "review", "captured": {}, "missing": [], "reply_text": "updated"}
    )
    _turn(message_text="change the impact to faster checkout")
    assert wired.payloads[0]["confirm"] is False
    assert wired.payloads[0]["fields"]["impact"] == "faster checkout"


# --------------------------------------------------------------------------- #
# AC-1212 - duplicate_candidate keeps the pointer, carries the candidate       #
# --------------------------------------------------------------------------- #
def test_duplicate_candidate_keeps_pointer_and_candidate(wired):
    wired.set_session_vars({})
    wired.set_create_idea(
        {
            "draft_id": "d-1",
            "status": "duplicate_candidate",
            "captured": {},
            "missing": [],
            "next_field": None,
            "duplicate_candidate": {"idea_number": "IDEA-0077", "title": "Show promo price in red"},
            "reply_text": "Similar idea exists: Show promo price in red",
        }
    )
    out = _turn()

    assert out["status"] == "duplicate_candidate"
    ideation = out["session_vars"]["ideation"]
    assert ideation["status"] == "duplicate_candidate"
    assert ideation["duplicate_candidate"] == {
        "idea_number": "IDEA-0077",
        "title": "Show promo price in red",
    }


# --------------------------------------------------------------------------- #
# AC-1213 / AC-1214 - duplicate_choice: explicit vote vs. default separate     #
# --------------------------------------------------------------------------- #
def test_duplicate_choice_vote_when_extracted(wired):
    wired.set_session_vars(
        {
            "ideation": {
                "draft_id": "d-1",
                "status": "duplicate_candidate",
                "missing": [],
                "updated_at": "t",
                "duplicate_candidate": {"idea_number": "IDEA-0077", "title": "Existing"},
            }
        }
    )
    wired.set_extraction(duplicate_choice="vote")
    wired.set_create_idea(
        {"draft_id": "d-1", "status": "voted", "captured": {}, "missing": [], "reply_text": "voted", "idea_number": "IDEA-0077"}
    )
    _turn(message_text="vote for that one")
    assert wired.payloads[0]["duplicate_choice"] == "vote"


def test_duplicate_choice_defaults_to_separate(wired):
    wired.set_session_vars(
        {
            "ideation": {
                "draft_id": "d-1",
                "status": "duplicate_candidate",
                "missing": [],
                "updated_at": "t",
                "duplicate_candidate": {"idea_number": "IDEA-0077", "title": "Existing"},
            }
        }
    )
    # A new detail about their own idea, not a vote - defaults to keep-separate (R4).
    wired.set_extraction(fields={"problem": "mine also covers the online store price"})
    wired.set_create_idea(
        {"draft_id": "d-1", "status": "collecting", "captured": {}, "missing": [], "reply_text": "ok"}
    )
    _turn(message_text="keep mine separate, mine also covers the online store price")
    assert wired.payloads[0]["duplicate_choice"] == "separate"


def test_duplicate_choice_omitted_outside_duplicate_candidate(wired):
    wired.set_session_vars({})
    wired.set_create_idea(
        {"draft_id": "d-1", "status": "collecting", "captured": {}, "missing": [], "reply_text": "ok"}
    )
    _turn()
    assert "duplicate_choice" not in wired.payloads[0]


# --------------------------------------------------------------------------- #
# AC-1219 (R17) - next_field/candidate title reach the extractor as a HINT,    #
# never as a routing key (the model's own semantic guard is pytest-covered   #
# with a stubbed provider in tests/test_ideation_extractor.py; this pins only #
# that handle_turn threads the hint through)                                  #
# --------------------------------------------------------------------------- #
def test_next_field_and_candidate_title_threaded_to_extractor(wired, monkeypatch):
    wired.set_session_vars(
        {
            "ideation": {
                "draft_id": "d-1",
                "status": "collecting",
                "missing": [],
                "next_field": "proposed_solution",
                "updated_at": "t",
            }
        }
    )
    seen_kwargs = {}
    real_fake = svc.extract_ideate_turn

    def _capture(_db, **kw):
        seen_kwargs.update(kw)
        return real_fake(_db, **kw)

    monkeypatch.setattr(svc, "extract_ideate_turn", _capture)
    wired.set_create_idea(
        {"draft_id": "d-1", "status": "collecting", "captured": {}, "missing": [], "reply_text": "ok"}
    )
    _turn(message_text="it happens most during month end")
    assert seen_kwargs["next_field"] == "proposed_solution"


# --------------------------------------------------------------------------- #
# Reviewer Blocking 2 (round 1, PR #1222 at 720bb8f5): the draft's captured    #
# answers and the stored title must reach the extractor too (not only         #
# next_field/candidate title), so the model can EXTEND a field instead of     #
# losing the earlier text, and keep the title stable across turns.            #
# --------------------------------------------------------------------------- #
def test_captured_and_prior_title_threaded_to_extractor(wired, monkeypatch):
    wired.set_session_vars(
        {
            "ideation": {
                "draft_id": "d-1",
                "status": "collecting",
                "missing": [],
                "next_field": "proposed_solution",
                "title": "Dealers check order status by calling",
                "captured": {"problem": "dealers keep calling to check order status"},
                "updated_at": "t",
            }
        }
    )
    seen_kwargs = {}
    real_fake = svc.extract_ideate_turn

    def _capture(_db, **kw):
        seen_kwargs.update(kw)
        return real_fake(_db, **kw)

    monkeypatch.setattr(svc, "extract_ideate_turn", _capture)
    wired.set_create_idea(
        {"draft_id": "d-1", "status": "collecting", "captured": {}, "missing": [], "reply_text": "ok"}
    )
    _turn(message_text="it happens most during month end")
    assert seen_kwargs["captured"] == {"problem": "dealers keep calling to check order status"}
    assert seen_kwargs["prior_title"] == "Dealers check order status by calling"


def test_captured_answers_persisted_onto_the_pointer(wired):
    """The pointer must carry `captured` forward (from the create_idea response)
    so the NEXT turn can thread it to the extractor as context."""
    wired.set_session_vars({})
    wired.set_create_idea(
        {
            "draft_id": "d-1",
            "status": "collecting",
            "captured": {"problem": "dealers keep calling to check order status"},
            "missing": [],
            "next_field": "proposed_solution",
            "reply_text": "ok",
        }
    )
    out = _turn(message_text="dealers keep calling to check order status")
    ideation = out["session_vars"]["ideation"]
    assert ideation["captured"] == {"problem": "dealers keep calling to check order status"}


# --------------------------------------------------------------------------- #
# Reviewer Nit 2 (round 2): a response that legitimately returns `captured: {}`#
# (a `remove` emptied the draft) must NOT have the prior turn's stale answers  #
# carried forward - `or` treats an empty dict the same as a missing key.      #
# --------------------------------------------------------------------------- #
def test_empty_captured_in_response_is_not_replaced_by_stale_prior_answers(wired):
    wired.set_session_vars(
        {
            "ideation": {
                "draft_id": "d-1",
                "status": "collecting",
                "captured": {"problem": "dealers keep calling to check order status"},
                "missing": [],
                "updated_at": "t",
                "is_test": False,
            }
        }
    )
    wired.set_create_idea(
        {
            "draft_id": "d-1",
            "status": "collecting",
            "captured": {},
            "missing": [],
            "next_field": "problem",
            "reply_text": "ok",
        }
    )
    out = _turn(message_text="actually forget the problem")
    ideation = out["session_vars"]["ideation"]
    assert ideation["captured"] == {}


# --------------------------------------------------------------------------- #
# Reviewer Nit 3 - cancelling during duplicate_candidate omits duplicate_choice#
# (precedence is shared-service's call; don't send a stale "separate" too)    #
# --------------------------------------------------------------------------- #
def test_cancel_during_duplicate_candidate_omits_duplicate_choice(wired):
    wired.set_session_vars(
        {
            "ideation": {
                "draft_id": "d-1",
                "status": "duplicate_candidate",
                "missing": [],
                "updated_at": "t",
                "duplicate_candidate": {"idea_number": "IDEA-0077", "title": "Existing"},
            }
        }
    )
    wired.set_extraction(review_action="cancel")
    wired.set_create_idea(
        {"draft_id": "d-1", "status": "cancelled", "captured": {}, "missing": [], "reply_text": "dropped"}
    )
    _turn(message_text="actually never mind, cancel")
    assert wired.payloads[0]["cancel"] is True
    assert "duplicate_choice" not in wired.payloads[0]


# --------------------------------------------------------------------------- #
# Reviewer Should fix 7 (round 1, PR #1222 at 720bb8f5): the submitter_tier    #
# SQL (join + ORDER BY sort_order, code) must actually run against Postgres,  #
# not just get set on a monkeypatched contact row (AC-1207).                  #
# --------------------------------------------------------------------------- #
def test_submitter_tier_sql_orders_by_sort_order_then_code():
    with blank_session() as db:
        db.add_all(
            [
                ContactAccessType(code="dealer", name="Dealer", sort_order=2),
                ContactAccessType(code="end_user", name="End user", sort_order=1),
            ]
        )
        db.flush()
        contact = RespondContact(
            id=str(uuid.uuid4()),
            respond_io_id=str(uuid.uuid4()),
            phone_number=f"+601{uuid.uuid4().int % 10**8:08d}",
            session_vars={},
        )
        db.add(contact)
        db.flush()
        db.execute(
            respond_contact_access_types.insert().values(
                [
                    {"contact_id": contact.id, "access_type_code": "dealer"},
                    {"contact_id": contact.id, "access_type_code": "end_user"},
                ]
            )
        )
        db.commit()

        state = svc._get_contact_row(db, contact.respond_io_id)
        assert state.submitter_tier == "end_user"  # lower sort_order wins over dealer

        contact_no_tier = RespondContact(
            id=str(uuid.uuid4()),
            respond_io_id=str(uuid.uuid4()),
            phone_number=f"+601{uuid.uuid4().int % 10**8:08d}",
            session_vars={},
        )
        db.add(contact_no_tier)
        db.commit()

        state_none = svc._get_contact_row(db, contact_no_tier.respond_io_id)
        assert state_none.submitter_tier is None


# --------------------------------------------------------------------------- #
# AC-1403 (S4) - a reply after the reminder drops reminded_at and moves        #
# updated_at, restarting the 24h clock. The pointer is already rebuilt from   #
# scratch every turn, so this is a test, not a code change (plan S4).         #
# --------------------------------------------------------------------------- #
def test_reply_after_reminder_drops_reminded_at(wired):
    wired.set_session_vars(
        {
            "ideation": {
                "draft_id": "d-1",
                "status": "collecting",
                "missing": [],
                "updated_at": "2020-01-01T00:00:00+00:00",
                "reminded_at": "2020-01-02T00:00:00+00:00",
            }
        }
    )
    wired.set_create_idea(
        {"draft_id": "d-1", "status": "collecting", "captured": {}, "missing": [], "reply_text": "ok"}
    )
    out = _turn(message_text="sorry, still working on it")

    ideation = out["session_vars"]["ideation"]
    assert "reminded_at" not in ideation
    assert ideation["updated_at"] != "2020-01-01T00:00:00+00:00"


# --------------------------------------------------------------------------- #
# AC-16 - read-modify-write preserves other CRM keys                          #
# --------------------------------------------------------------------------- #
def test_preserves_other_crm_keys_on_write(wired):
    wired.set_session_vars(
        {
            "referenced_result_set": [{"id": "x"}],
            "some_other_blob": {"a": 1},
            "ideation": {"draft_id": "d-1", "status": "collecting", "missing": ["who"], "updated_at": "t"},
        }
    )
    wired.set_create_idea(
        {"draft_id": "d-1", "status": "collecting", "captured": {}, "missing": ["who"], "reply_text": "ok"}
    )
    out = _turn()

    sv = out["session_vars"]
    assert sv["referenced_result_set"] == [{"id": "x"}]
    assert sv["some_other_blob"] == {"a": 1}
    assert sv["ideation"]["draft_id"] == "d-1"


def test_preserves_other_crm_keys_on_clear(wired):
    wired.set_session_vars(
        {
            "referenced_result_set": [{"id": "x"}],
            "ideation": {"draft_id": "d-1", "status": "review", "missing": [], "updated_at": "t"},
        }
    )
    wired.set_extraction(review_action="submit")
    wired.set_create_idea(
        {"draft_id": "d-1", "status": "complete", "captured": {}, "missing": [], "reply_text": "done", "link": "L"}
    )
    out = _turn()

    assert "ideation" not in out["session_vars"]
    assert out["session_vars"]["referenced_result_set"] == [{"id": "x"}]  # untouched


# --------------------------------------------------------------------------- #
# AC-17 - resume-by-draft_id after an interrupt                                #
# --------------------------------------------------------------------------- #
def test_resume_by_draft_id_after_interrupt(wired):
    # A CRM interrupt turn is NOT this endpoint; it left session_vars.ideation intact.
    wired.set_session_vars(
        {
            "referenced_result_set": [{"crm": "interrupt happened"}],
            "ideation": {"draft_id": "d-42", "status": "collecting", "missing": ["who"], "updated_at": "t"},
        }
    )
    wired.set_create_idea(
        {"draft_id": "d-42", "status": "collecting", "captured": {}, "missing": [], "reply_text": "resumed"}
    )
    out = _turn(message_text="the CS team")

    assert wired.payloads[0]["draft_id"] == "d-42"  # resumed the SAME draft
    assert out["session_vars"]["ideation"]["draft_id"] == "d-42"
    assert out["session_vars"]["referenced_result_set"] == [{"crm": "interrupt happened"}]


# --------------------------------------------------------------------------- #
# AC-31 - fail-closed: no product binding → no create_idea call               #
# --------------------------------------------------------------------------- #
def test_no_product_binding_fails_closed(wired):
    wired.set_session_vars({"unrelated": 1})
    wired.set_product_id(None)
    out = _turn()

    assert wired.payloads == []  # no create_idea call
    assert wired.overwrites == []  # no session_vars mutation
    assert out["session_vars"] == {"unrelated": 1}
    assert "reply_text" in out and out["reply_text"]


def test_no_config_fails_closed(wired, monkeypatch):
    wired.set_session_vars({})
    monkeypatch.setattr(svc.settings, "ideation_shared_service_url", None)
    out = _turn()
    assert wired.payloads == []
    assert wired.overwrites == []
    assert "reply_text" in out


# --------------------------------------------------------------------------- #
# AC-19 - shared-service outage → graceful reply, no 500, no mutation          #
# --------------------------------------------------------------------------- #
def test_outage_returns_graceful_reply(wired):
    wired.set_session_vars(
        {"ideation": {"draft_id": "d-1", "status": "collecting", "missing": ["who"], "updated_at": "t"}}
    )
    wired.set_create_idea(IdeationServiceError("connect timeout"))
    out = _turn()

    assert out["status"] == "error"
    assert out["reply_text"]  # a friendly message
    assert wired.overwrites == []  # session_vars untouched
    assert out["session_vars"]["ideation"]["draft_id"] == "d-1"  # unchanged


# --------------------------------------------------------------------------- #
# Reviewer round 1 (PR #1230): `_graceful` echoed the contact's raw DB         #
# `session_vars`, not the pointer THIS turn actually read. On a dry run       #
# carrying a TEST pointer via `session_vars_in`, an outage therefore handed   #
# back the contact's REAL stored pointer (possibly `is_test: false`) instead  #
# of the carried test one - a test draft silently swapped for a live draft.  #
# --------------------------------------------------------------------------- #
def test_outage_on_a_dry_run_keeps_the_carried_pointer_not_the_db_one(wired):
    wired.set_session_vars(
        {"ideation": {"draft_id": "d-live-db", "status": "collecting", "missing": ["who"], "updated_at": "t"}}
    )
    carried_pointer = {
        "draft_id": "d-test-carried",
        "status": "collecting",
        "missing": ["impact"],
        "updated_at": "t2",
        "is_test": True,
    }
    wired.set_create_idea(IdeationServiceError("connect timeout"))
    out = _turn(is_test=True, session_vars_in={"ideation": carried_pointer})

    assert out["status"] == "error"
    assert wired.overwrites == []  # session_vars untouched
    assert out["session_vars"]["ideation"] == carried_pointer


# --------------------------------------------------------------------------- #
# Issue #1179 - `is_test` rides the create_idea payload (AC-1..AC-3 of         #
# `documentation/plans/chatbot/ideation-is-test-turns-acceptance-criteria.md`) #
# --------------------------------------------------------------------------- #
_COLLECTING = {
    "draft_id": "d-test-1",
    "status": "collecting",
    "captured": {},
    "missing": ["impact"],
    "reply_text": "Here's what I've got so far",
}


def test_test_turn_payload_carries_is_test_true(wired):
    """AC-1: a test turn tells the shared service so the idea is hidden from the board."""
    wired.set_session_vars({})
    wired.set_create_idea(dict(_COLLECTING))
    _turn(is_test=True)
    assert wired.payloads[0]["is_test"] is True


def test_live_turn_payload_carries_is_test_false(wired):
    """AC-2: the key is always present, false on a live turn (the default)."""
    wired.set_session_vars({})
    wired.set_create_idea(dict(_COLLECTING))
    _turn()
    assert wired.payloads[0]["is_test"] is False


def test_test_turn_returns_the_pointer_but_never_persists_it(wired):
    """AC-3: the caller carries the draft pointer; the contact row is untouched.

    A test pointer written to the real `respond_contacts` row would be read back by the
    contact's next LIVE turn through the DB fallback in `handle_turn`, so a test idea
    would silently continue as a live one."""
    wired.set_session_vars({"other_key": "kept"})
    wired.set_create_idea(dict(_COLLECTING))
    out = _turn(is_test=True)

    assert out["status"] == "collecting"
    assert out["reply_text"] == "Here's what I've got so far"
    assert out["session_vars"]["ideation"]["draft_id"] == "d-test-1"
    assert out["session_vars"]["other_key"] == "kept"
    assert wired.overwrites == [], "a test turn must not write respond_contacts.session_vars"
    assert wired.store == {"other_key": "kept"}


# --------------------------------------------------------------------------- #
# Reviewer Blocking A (PR #1182 round 2): the pointer the service RETURNS/     #
# writes must itself carry the `is_test` stamp the round-1 guard reads, and   #
# the guard must be exercised through that real written pointer - not a      #
# hand-built one - or a dropped stamp shows green everywhere else.            #
# --------------------------------------------------------------------------- #
def test_test_turn_returns_a_pointer_stamped_is_test_true(wired):
    wired.set_session_vars({})
    wired.set_create_idea(dict(_COLLECTING))
    out = _turn(is_test=True)
    assert out["session_vars"]["ideation"]["is_test"] is True


def test_live_turn_returns_a_pointer_stamped_is_test_false(wired):
    wired.set_session_vars({})
    wired.set_create_idea(dict(_COLLECTING))
    out = _turn()
    assert out["session_vars"]["ideation"]["is_test"] is False


def test_two_test_turns_continue_through_the_real_written_pointer(wired):
    """The round-1 guard must accept a MATCHING pointer that the service itself
    wrote and returned - not one the test hand-built - or a dropped write-side
    stamp would look identical to a matching one everywhere else."""
    wired.set_session_vars({})
    wired.set_create_idea(dict(_COLLECTING))
    out1 = _turn(is_test=True)
    assert out1["session_vars"]["ideation"]["draft_id"] == "d-test-1"

    wired.set_create_idea(dict(_COLLECTING))
    _turn(is_test=True, session_vars_in=out1["session_vars"])
    assert wired.payloads[1]["draft_id"] == "d-test-1"


def test_a_live_turn_does_not_continue_the_real_written_test_pointer(wired):
    """Mismatch direction of the same guard, exercised through a REAL test-turn
    pointer (not hand-built): a live turn must not pick up a genuinely-written
    test draft_id."""
    wired.set_session_vars({})
    wired.set_create_idea(dict(_COLLECTING))
    out1 = _turn(is_test=True)
    assert out1["session_vars"]["ideation"]["draft_id"] == "d-test-1"

    wired.set_create_idea(dict(_COLLECTING))
    _turn(session_vars_in=out1["session_vars"])
    assert "draft_id" not in wired.payloads[1]


# --------------------------------------------------------------------------- #
# Reviewer Blocking 2 (PR #1182 round 1): a pointer's `is_test` flag must      #
# match the turn's, or a test turn can continue (and confirm) the contact's   #
# LIVE draft - exactly the cross-contamination D14 exists to prevent.         #
# --------------------------------------------------------------------------- #
def test_stored_live_pointer_is_not_continued_by_a_test_turn(wired):
    """A live pointer already sitting in the contact's DB row (no `is_test` key,
    i.e. written before this fix or by a live turn) must not be picked up by a
    later test turn - it starts fresh instead of sending the live draft_id."""
    wired.set_session_vars(
        {"ideation": {"draft_id": "ZZT-live-draft-1", "status": "collecting", "missing": ["impact"]}}
    )
    wired.set_create_idea(dict(_COLLECTING))
    _turn(is_test=True)
    assert "draft_id" not in wired.payloads[0]


def test_test_flagged_pointer_is_not_continued_by_a_live_turn(wired):
    """The reverse direction: a pointer stamped `is_test: true` (from an earlier
    test turn) must not be continued by a live turn - the customer's real turn
    starts its own draft rather than resuming a test one."""
    wired.set_session_vars(
        {"ideation": {"draft_id": "ZZT-test-draft-1", "status": "collecting", "is_test": True}}
    )
    wired.set_create_idea(dict(_COLLECTING))
    _turn()
    assert "draft_id" not in wired.payloads[0]


def test_console_reset_does_not_leak_the_stored_live_draft_into_a_test_turn(wired):
    """The console Reset path: `session_vars_in={"ideation": None}` (an explicit
    None, not an absent key - `engine._inject_harness_session` writes exactly this
    shape) must not fall through to the contact's stored LIVE pointer either."""
    wired.set_session_vars(
        {"ideation": {"draft_id": "ZZT-live-draft-2", "status": "collecting", "missing": ["impact"]}}
    )
    wired.set_create_idea(dict(_COLLECTING))
    _turn(is_test=True, session_vars_in={"ideation": None})
    assert "draft_id" not in wired.payloads[0]


# --------------------------------------------------------------------------- #
# call_create_idea wraps httpx errors into IdeationServiceError (AC-19 layer)  #
# --------------------------------------------------------------------------- #
def test_call_create_idea_wraps_httpx_error(monkeypatch):
    def _boom(self, url, **kw):  # noqa: ANN001
        raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx.Client, "post", _boom)
    with pytest.raises(IdeationServiceError):
        svc.call_create_idea("https://shared.test", "k", {"product_id": "p"})


# --------------------------------------------------------------------------- #
# Reviewer Should fix 3 (round 2): the HTTP status -> `status_code` mapping    #
# itself has to be driven through an actual `httpx.HTTPStatusError`, not      #
# monkeypatched directly - otherwise deleting the mapping code leaves every   #
# sweep test green while production silently retries every 4xx forever.      #
# --------------------------------------------------------------------------- #
def test_call_create_idea_maps_http_status_error_status_code(monkeypatch):
    def _respond(self, url, **kw):  # noqa: ANN001
        return httpx.Response(404, json={"error": "not found"}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.Client, "post", _respond)
    with pytest.raises(IdeationServiceError) as exc_info:
        svc.call_create_idea("https://shared.test", "k", {"product_id": "p"})
    assert exc_info.value.status_code == 404


# --------------------------------------------------------------------------- #
# AC-20 - endpoint writes an integration_log on success AND failure           #
# --------------------------------------------------------------------------- #
@pytest.fixture
def api_client(monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app
    from app.dependencies import get_db, get_external_api_user

    logs: list = []

    def _capture_log(self, log_data, request_payload_dict=None):  # noqa: ANN001
        logs.append(log_data)
        return None

    monkeypatch.setattr(
        "app.api.v1.external.ideation.IntegrationLogService.create_integration_log",
        _capture_log,
    )
    app.dependency_overrides[get_db] = lambda: None
    app.dependency_overrides[get_external_api_user] = lambda: {"id": "system"}
    try:
        # Authorization is out of scope here (get_db is stubbed to None);
        # enforcement is covered by test_external_permission_guard/_coverage.
        with external_permissions_granted():
            yield TestClient(app), logs, monkeypatch
    finally:
        app.dependency_overrides.clear()


_TURN_URL = "/api/v1/external/ideation/turn"
_TURN_BODY = {"respond_io_id": "rio-1", "message_text": "idea: bulk-tag complaints"}


def test_endpoint_logs_on_success(api_client):
    client, logs, mp = api_client
    mp.setattr(
        "app.api.v1.external.ideation.handle_turn",
        lambda *a, **k: {"status": "collecting", "reply_text": "ok", "session_vars": {}},
    )
    resp = client.post(_TURN_URL, json=_TURN_BODY)
    assert resp.status_code == 200
    assert resp.json()["status"] == "collecting"
    assert len(logs) == 1
    assert logs[0].status == "success"
    assert logs[0].direction == "inbound"
    assert logs[0].external_reference == "rio-1"


@pytest.mark.parametrize(
    "body,expected",
    [
        ({**_TURN_BODY, "is_test": True}, True),
        (_TURN_BODY, False),
    ],
    ids=["is_test-true", "absent-defaults-false"],
)
def test_endpoint_forwards_is_test_to_the_service(api_client, body, expected):
    """AC-4 (#1179): the flag the MCP tool posts reaches `handle_turn`."""
    client, _logs, mp = api_client
    seen: list = []

    def _capture(*a, **k):  # noqa: ANN001
        seen.append(k)
        return {"status": "collecting", "reply_text": "ok", "session_vars": {}}

    mp.setattr("app.api.v1.external.ideation.handle_turn", _capture)
    resp = client.post(_TURN_URL, json=body)
    assert resp.status_code == 200
    assert seen[0]["is_test"] is expected


def test_endpoint_logs_on_failure(api_client):
    client, logs, mp = api_client

    def _boom(*a, **k):  # noqa: ANN001
        raise RuntimeError("kaboom")

    mp.setattr("app.api.v1.external.ideation.handle_turn", _boom)
    resp = client.post(_TURN_URL, json=_TURN_BODY)
    assert resp.status_code == 500
    assert len(logs) == 1
    assert logs[0].status == "failed"
    assert logs[0].status_code == 500


# --------------------------------------------------------------------------- #
# Group F - multi-modal capture (DC-1..DC-10)                                  #
# --------------------------------------------------------------------------- #
from app.services.ideation_media_service import MediaClients  # noqa: E402
from tests._external_auth import external_permissions_granted


def _stub_media_clients(caption="a sketch of an export button"):
    return MediaClients(
        fetch_bytes=lambda url: (b"rawbytes", "image/jpeg"),
        store_bytes=lambda data, key, ct: f"https://durable.cdn/{key}",
        caption_image=lambda data, ct: caption,
    )


def _respond_payload(*items):
    return {"items": list(items)}


def _media_item(mid, kind, url, *, ts=1_721_000_000_000, filename=None):
    return {
        "messageId": mid,
        "traffic": "incoming",
        "status": [{"timestamp": ts}],
        "message": {"type": kind, kind: {"url": url, "filename": filename}},
    }


def test_first_turn_lookback_offers_menu_and_sets_pending(wired):
    wired.set_session_vars({})
    wired.set_create_idea(
        {"draft_id": "d1", "status": "collecting", "missing": ["impact"], "reply_text": "Got it. What's the impact?"}
    )
    out = _turn(
        message_text="I have an idea about exporting orders",
        fetch_recent_messages=lambda: _respond_payload(
            _media_item("m1", "image", "https://respond/1.jpg", filename="mockup.jpg", ts=2000),
            _media_item("m2", "video", "https://respond/2.mp4", ts=1000),
        ),
        media_clients=_stub_media_clients(),
    )
    # menu appended to the create_idea reply (DC-8)
    assert "which relate to this idea" in out["reply_text"]
    assert "mockup.jpg" in out["reply_text"]
    pending = out["session_vars"]["ideation"]["pending_media"]
    assert [p["source_msg_id"] for p in pending] == ["m1", "m2"]
    # no attachments sent yet - the user hasn't picked
    assert "attachments" not in wired.payloads[-1]


def test_no_recent_media_no_menu(wired):
    wired.set_session_vars({})
    wired.set_create_idea({"draft_id": "d1", "status": "collecting", "missing": ["impact"], "reply_text": "ok"})
    out = _turn(
        message_text="idea: dark mode",
        fetch_recent_messages=lambda: _respond_payload(),
        media_clients=_stub_media_clients(),
    )
    assert "pending_media" not in out["session_vars"]["ideation"]
    assert "which relate" not in out["reply_text"]


def test_selection_snapshots_and_attaches(wired):
    wired.set_session_vars(
        {
            "ideation": {
                "draft_id": "d1",
                "status": "collecting",
                "missing": ["impact"],
                "transcript": ["I have an idea about exporting orders"],
                "pending_media": [
                    {"source_msg_id": "m1", "kind": "image", "url": "https://respond/1.jpg", "filename": "mockup.jpg", "received_at": None},
                    {"source_msg_id": "m2", "kind": "video", "url": "https://respond/2.mp4", "filename": None, "received_at": None},
                ],
            }
        }
    )
    wired.set_create_idea({"draft_id": "d1", "status": "collecting", "missing": ["impact"], "reply_text": "attached."})
    out = _turn(message_text="1", media_selection="1", media_clients=_stub_media_clients())
    payload = wired.payloads[-1]
    assert "attachments" in payload
    atts = payload["attachments"]
    assert [a["source_msg_id"] for a in atts] == ["m1"]
    assert atts[0]["type"] == "image" and atts[0]["url"].startswith("https://durable.cdn/")
    # caption folded into message_text (DC-6/9)
    assert "(attached image: a sketch of an export button)" in payload["message_text"]
    # pending cleared; both offered ids marked seen so they never re-nag
    ideation = out["session_vars"]["ideation"]
    assert "pending_media" not in ideation
    assert set(ideation["seen_media_ids"]) == {"m1", "m2"}


def test_selection_none_attaches_nothing(wired):
    wired.set_session_vars(
        {"ideation": {"draft_id": "d1", "status": "collecting", "missing": [], "pending_media": [
            {"source_msg_id": "m1", "kind": "image", "url": "u", "filename": None, "received_at": None}]}}
    )
    wired.set_create_idea({"draft_id": "d1", "status": "review", "missing": [], "reply_text": "ok"})
    out = _turn(message_text="none", media_selection="none", media_clients=_stub_media_clients())
    assert "attachments" not in wired.payloads[-1]
    assert "pending_media" not in out["session_vars"]["ideation"]
    assert out["session_vars"]["ideation"]["seen_media_ids"] == ["m1"]


def test_non_selection_turn_dismisses_pending(wired):
    wired.set_session_vars(
        {"ideation": {"draft_id": "d1", "status": "collecting", "missing": ["impact"], "pending_media": [
            {"source_msg_id": "m1", "kind": "image", "url": "u", "filename": None, "received_at": None}]}}
    )
    wired.set_create_idea({"draft_id": "d1", "status": "collecting", "missing": [], "reply_text": "ok"})
    # user answers the impact question, not the media menu (no media_selection)
    out = _turn(message_text="it saves 30 minutes a day", media_clients=_stub_media_clients())
    ideation = out["session_vars"]["ideation"]
    assert "pending_media" not in ideation
    assert ideation["seen_media_ids"] == ["m1"]
    assert "attachments" not in wired.payloads[-1]


def test_is_new_idea_discards_old_and_starts_fresh(wired):
    wired.set_session_vars(
        {"ideation": {"draft_id": "old", "status": "collecting", "missing": ["impact"],
                      "transcript": ["exporting orders idea"], "seen_media_ids": ["m9"]}}
    )
    wired.set_create_idea({"draft_id": "new", "status": "collecting", "missing": ["impact"], "reply_text": "new idea noted"})
    out = _turn(
        message_text="actually forget that - different idea about dark mode",
        is_new_idea=True,
        fetch_recent_messages=lambda: _respond_payload(),
        media_clients=_stub_media_clients(),
    )
    payload = wired.payloads[-1]
    assert payload["discard_draft_id"] == "old"
    assert "draft_id" not in payload  # fresh draft
    # transcript reset to just this turn
    assert out["session_vars"]["ideation"]["transcript"] == ["actually forget that - different idea about dark mode"]
    assert out["session_vars"]["ideation"]["draft_id"] == "new"


def test_seen_media_not_reoffered(wired):
    wired.set_session_vars(
        {"ideation": {"draft_id": "d1", "status": "collecting", "missing": ["impact"], "seen_media_ids": ["m1"]}}
    )
    wired.set_create_idea({"draft_id": "d1", "status": "collecting", "missing": ["impact"], "reply_text": "ok"})
    out = _turn(
        message_text="continuing",
        fetch_recent_messages=lambda: _respond_payload(_media_item("m1", "image", "https://respond/1.jpg")),
        media_clients=_stub_media_clients(),
    )
    assert "pending_media" not in out["session_vars"]["ideation"]
    assert "which relate" not in out["reply_text"]


# --------------------------------------------------------------------------- #
# #1277 (issue) - W1+W3 at the turn level: the exact recap shape from the    #
# owner's console transcript, reply LLM unavailable (db=None -> config read  #
# fails -> _call_ideate_reply_llm returns None -> the shared-service         #
# TEMPLATE fallback is what handle_turn's reply_text formats).               #
# --------------------------------------------------------------------------- #
def test_1277_recap_replay_bolds_labels_and_drops_title(wired):
    wired.set_session_vars({"ideation": {"draft_id": "d1", "status": "collecting", "missing": ["department"]}})
    fallback_reply = (
        '"sales order KPI tracking"\n'
        "Problem: track sales order kpi\n"
        "Solution: dashboard widget\n"
        "Impact: faster visibility\n"
        "Department: sales\n"
        "Is that right?"
    )
    wired.set_create_idea(
        {
            "draft_id": "d1",
            "status": "review",
            "title": "sales order KPI tracking",
            "captured": {
                "problem": "track sales order kpi",
                "proposed_solution": "dashboard widget",
                "impact": "faster visibility",
                "department": "sales",
            },
            "missing": [],
            "reply_text": fallback_reply,
        }
    )
    out = _turn(message_text="yes that's right")
    assert out["reply_text"] == (
        "*Problem:* track sales order kpi\n"
        "*Solution:* dashboard widget\n"
        "*Impact:* faster visibility\n"
        "*Department:* sales\n"
        "Is that right?"
    )


# --------------------------------------------------------------------------- #
# #1277 - W4: `offered_media` on the turn that builds a media menu.          #
# --------------------------------------------------------------------------- #
def test_offered_media_lists_images_in_menu_order(wired):
    wired.set_session_vars({})
    wired.set_create_idea(
        {"draft_id": "d1", "status": "collecting", "missing": ["impact"], "reply_text": "Got it. What's the impact?"}
    )
    out = _turn(
        message_text="I have an idea about exporting orders",
        fetch_recent_messages=lambda: _respond_payload(
            _media_item("m1", "image", "https://respond/1.jpg", filename="mockup.jpg", ts=2000),
            _media_item("m2", "image", "https://respond/2.jpg", filename="sketch.jpg", ts=1000),
        ),
        media_clients=_stub_media_clients(),
    )
    assert out["offered_media"] == [
        {"position": 1, "kind": "image", "url": "https://respond/1.jpg", "filename": "mockup.jpg"},
        {"position": 2, "kind": "image", "url": "https://respond/2.jpg", "filename": "sketch.jpg"},
    ]


def test_offered_media_empty_when_no_candidates(wired):
    wired.set_session_vars({})
    wired.set_create_idea({"draft_id": "d1", "status": "collecting", "missing": ["impact"], "reply_text": "ok"})
    out = _turn(
        message_text="idea: dark mode",
        fetch_recent_messages=lambda: _respond_payload(),
        media_clients=_stub_media_clients(),
    )
    assert out["offered_media"] == []


def test_offered_media_empty_on_selection_turn(wired):
    wired.set_session_vars(
        {
            "ideation": {
                "draft_id": "d1",
                "status": "collecting",
                "missing": ["impact"],
                "pending_media": [
                    {"source_msg_id": "m1", "kind": "image", "url": "u", "filename": None, "received_at": None}
                ],
            }
        }
    )
    wired.set_create_idea({"draft_id": "d1", "status": "collecting", "missing": [], "reply_text": "attached."})
    out = _turn(message_text="1", media_selection="1", media_clients=_stub_media_clients())
    assert out["offered_media"] == []


def test_ideation_turn_response_schema_keeps_offered_media():
    """`response_model` silently drops undeclared fields (repo lesson) - the
    schema must declare `offered_media` or it never reaches n8n/the console."""
    from app.schemas.external.ideation import IdeationTurnResponse

    result = {
        "status": "collecting",
        "reply_text": "x",
        "session_vars": {},
        "offered_media": [{"position": 1, "kind": "image", "url": "u", "filename": "f"}],
    }
    dumped = IdeationTurnResponse(**result).model_dump()
    assert dumped.get("offered_media") == result["offered_media"]
