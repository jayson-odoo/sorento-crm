"""Slice C — ``ideate`` brain-path turn endpoint + service + confirmation gate.

Keys back to ``documentation/plans/ideation/ideation-ideate-intent-acceptance-criteria.md``:

- **AC-10 [BE]** — the service returns ``{ status, reply_text, link?, session_vars }``
  (full updated blob) from one ``create_idea`` call.
- **AC-11 / AC-11b [BE][T]** — the §5.1 input is built deterministically
  (``product_id`` from the workspace binding, ``submitter`` = contact phone E.164)
  and carries the brain-extracted ``{ fields, remove, confirm }`` (D-CONFIRM).
- **AC-12 [BE][T]** — first turn omits ``draft_id`` and persists
  ``session_vars.ideation = { draft_id, status, missing, updated_at }``.
- **AC-12b [BE][T]** — ``review`` KEEPS the pointer (never cleared before confirm),
  even for a one-shot-complete turn that routes through ``review``.
- **AC-13 [BE][T]** — a continuation passes ``draft_id`` through (idempotent enrich).
- **AC-13b [BE][T]** — a revise loop survives ≥3 turns keeping ``review``.
- **AC-13c / AC-14 [BE][T]** — explicit confirm → ``complete`` + ``link``, and ONLY
  then is ``session_vars.ideation`` cleared.
- **AC-15 [BE][T]** — ``duplicate`` clears the pointer and relays the tool's copy.
- **AC-16 [BE][T]** — read-modify-write preserves every other CRM session_vars key.
- **AC-17 [BE][T]** — resume-by-``draft_id`` after an interrupt (open draft intact).
- **AC-19 [BE]** — a shared-service outage returns a graceful reply, never a 500,
  and never mutates session_vars.
- **AC-31 [BE][T]** — no ``ideation_product_id`` → fail-closed, no ``create_idea`` call.
- **AC-20 [BE]** — the endpoint writes an ``integration_log`` on success AND failure.

The brain extractor's LLM output is STUBBED; the httpx ``create_idea`` call is
STUBBED (monkeypatched wrapper). No live LLM, no live shared-service, no real DB
for the service tests — session_vars I/O is faked so the merge logic is asserted
byte-for-byte. AC-11b's live-LLM extraction quality is DEFERRED to the opt-in
harness (the deterministic ``confirm``-guard is tested here).
"""
from __future__ import annotations

import httpx
import pytest

import app.services.ideation_turn_service as svc
from app.services.ideation_extractor import IdeateExtraction
from app.services.ideation_turn_service import IdeationServiceError, handle_turn


# --------------------------------------------------------------------------- #
# Fakes / seams                                                               #
# --------------------------------------------------------------------------- #


class _FakeContact:
    def __init__(self, phone_number: str, session_vars: dict, display_name=None):
        self.phone_number = phone_number
        self.session_vars = session_vars
        self.display_name = display_name


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
        "store": {},
        "extraction": IdeateExtraction(fields={}, remove=[], confirm=False),
        "create_idea_result": None,
        "product_id": "prod-uuid-1",
        "payloads": [],
        "overwrites": [],
    }

    def _fake_get_contact_row(_db, respond_io_id):  # noqa: ANN001
        return _FakeContact(
            state["phone"], dict(state["store"]), display_name=state["display_name"]
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
        return state["extraction"]

    def _fake_call_create_idea(_base_url, _api_key, payload):  # noqa: ANN001
        state["payloads"].append(payload)
        res = state["create_idea_result"]
        if isinstance(res, Exception):
            raise res
        return res

    # overwrite_for_contact(db, *, respond_io_id, state) — capture + persist so
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

        def set_extraction(self, fields=None, remove=None, confirm=False):
            state["extraction"] = IdeateExtraction(
                fields=fields or {}, remove=remove or [], confirm=confirm
            )

        def set_create_idea(self, result):
            state["create_idea_result"] = result

        def set_product_id(self, pid):
            state["product_id"] = pid

        def set_display_name(self, name):
            state["display_name"] = name

    harness = _Harness()
    monkeypatch.setattr(svc, "overwrite_for_contact", _overwrite_capture)
    return harness


def _turn(**kw):
    kw.setdefault("respond_io_id", "rio-1")
    kw.setdefault("message_text", "I wish it could remind me before a PO expires")
    return handle_turn(None, **kw)


# --------------------------------------------------------------------------- #
# AC-12 — first turn: no draft_id, persist collecting pointer                  #
# --------------------------------------------------------------------------- #
def test_first_turn_collecting_persists_pointer(wired):
    wired.set_session_vars({})
    wired.set_create_idea(
        {
            "draft_id": "d-1",
            "status": "collecting",
            "captured": {"what": "PO expiry reminder"},
            "missing": ["module", "who"],
            "reply_text": "Got it — which module?",
        }
    )
    out = _turn()

    assert out["status"] == "collecting"
    assert out["reply_text"] == "Got it — which module?"
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
# AC-11 / AC-11b — deterministic input shape + brain extraction passthrough    #
# --------------------------------------------------------------------------- #
def test_input_shape_and_extraction_passthrough(wired):
    wired.set_session_vars({})
    wired.set_extraction(fields={"module": "procurement"}, remove=["who"], confirm=False)
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
# WS-A / AC-CAP-1..3 — submitter name from the CRM contact, n8n fallback       #
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
# WS-B / AC-CAP-5..7 — raw_transcript accumulates across turns                 #
# --------------------------------------------------------------------------- #
def test_raw_transcript_accumulates_over_turns(wired):
    """Each turn appends to the transcript; the payload carries the WHOLE convo,
    not just the finalizing message. The pointer persists the running list."""
    # Turn 1 — collecting, transcript = [msg1]
    wired.set_session_vars({})
    wired.set_create_idea(
        {"draft_id": "d-7", "status": "collecting", "captured": {}, "missing": ["impact"], "reply_text": "ok"}
    )
    out1 = _turn(message_text="I want AI to update contractors on delivery")
    assert wired.payloads[-1]["raw_transcript"] == "I want AI to update contractors on delivery"
    assert out1["session_vars"]["ideation"]["transcript"] == [
        "I want AI to update contractors on delivery"
    ]

    # Turn 2 — continuation adds a substantive turn.
    wired.set_create_idea(
        {"draft_id": "d-7", "status": "review", "captured": {}, "missing": [], "reply_text": "confirm?"}
    )
    _turn(message_text="impact is high ROI")
    assert wired.payloads[-1]["raw_transcript"] == (
        "I want AI to update contractors on delivery\nimpact is high ROI"
    )

    # Turn 3 — the finalizing "confirm" turn: transcript still holds the prior turns.
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
# AC-12b — review KEEPS the pointer (one-shot complete still routes review)    #
# --------------------------------------------------------------------------- #
def test_review_keeps_pointer(wired):
    wired.set_session_vars({})
    wired.set_create_idea(
        {
            "draft_id": "d-1",
            "status": "review",
            "captured": {"what": "x", "module": "y", "who": "z"},
            "missing": [],
            "reply_text": "Here's the summary — confirm or revise?",
        }
    )
    out = _turn()

    assert out["status"] == "review"
    assert out["session_vars"]["ideation"]["status"] == "review"
    assert out["session_vars"]["ideation"]["draft_id"] == "d-1"
    assert out["session_vars"]["ideation"]["missing"] == []
    assert "link" not in out


# --------------------------------------------------------------------------- #
# AC-13 — continuation passes draft_id through (idempotent enrich)             #
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
# AC-13b — revise loop survives ≥3 turns keeping review                        #
# --------------------------------------------------------------------------- #
def test_revise_loop_survives_three_turns(wired):
    # turn 1 — incomplete → collecting
    wired.set_session_vars({})
    wired.set_extraction(fields={"what": "reminder"})
    wired.set_create_idea(
        {"draft_id": "d-9", "status": "collecting", "captured": {}, "missing": ["module"], "reply_text": "which module?"}
    )
    o1 = _turn()
    assert o1["session_vars"]["ideation"]["status"] == "collecting"

    # turn 2 — now complete → review
    wired.set_extraction(fields={"module": "procurement"})
    wired.set_create_idea(
        {"draft_id": "d-9", "status": "review", "captured": {}, "missing": [], "reply_text": "confirm?"}
    )
    o2 = _turn(message_text="procurement")
    assert o2["session_vars"]["ideation"]["status"] == "review"

    # turn 3 — revise → stays review
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
# AC-13c / AC-14 — explicit confirm → complete + link, THEN clear             #
# --------------------------------------------------------------------------- #
def test_confirm_completes_and_clears(wired):
    wired.set_session_vars(
        {"ideation": {"draft_id": "d-1", "status": "review", "missing": [], "updated_at": "t"}}
    )
    wired.set_extraction(confirm=True)
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
# AC-15 — duplicate clears the pointer, relays tool copy                       #
# --------------------------------------------------------------------------- #
def test_duplicate_clears_pointer(wired):
    wired.set_session_vars(
        {"ideation": {"draft_id": "d-1", "status": "collecting", "missing": [], "updated_at": "t"}}
    )
    wired.set_create_idea(
        {
            "draft_id": "d-1",
            "status": "duplicate",
            "captured": {},
            "missing": [],
            "reply_text": "This is similar to an existing idea — I upvoted it for you.",
            "duplicate_of": "idea-77",
        }
    )
    out = _turn()

    assert out["status"] == "duplicate"
    assert "upvoted" in out["reply_text"]
    assert "ideation" not in out["session_vars"]


# --------------------------------------------------------------------------- #
# AC-16 — read-modify-write preserves other CRM keys                          #
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
    wired.set_extraction(confirm=True)
    wired.set_create_idea(
        {"draft_id": "d-1", "status": "complete", "captured": {}, "missing": [], "reply_text": "done", "link": "L"}
    )
    out = _turn()

    assert "ideation" not in out["session_vars"]
    assert out["session_vars"]["referenced_result_set"] == [{"id": "x"}]  # untouched


# --------------------------------------------------------------------------- #
# AC-17 — resume-by-draft_id after an interrupt                                #
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
# AC-31 — fail-closed: no product binding → no create_idea call               #
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
# AC-19 — shared-service outage → graceful reply, no 500, no mutation          #
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
# call_create_idea wraps httpx errors into IdeationServiceError (AC-19 layer)  #
# --------------------------------------------------------------------------- #
def test_call_create_idea_wraps_httpx_error(monkeypatch):
    def _boom(self, url, **kw):  # noqa: ANN001
        raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx.Client, "post", _boom)
    with pytest.raises(IdeationServiceError):
        svc.call_create_idea("https://shared.test", "k", {"product_id": "p"})


# --------------------------------------------------------------------------- #
# AC-20 — endpoint writes an integration_log on success AND failure           #
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
# Group F — multi-modal capture (DC-1..DC-10)                                  #
# --------------------------------------------------------------------------- #
from app.services.ideation_media_service import MediaClients  # noqa: E402


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
    # no attachments sent yet — the user hasn't picked
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
        message_text="actually forget that — different idea about dark mode",
        is_new_idea=True,
        fetch_recent_messages=lambda: _respond_payload(),
        media_clients=_stub_media_clients(),
    )
    payload = wired.payloads[-1]
    assert payload["discard_draft_id"] == "old"
    assert "draft_id" not in payload  # fresh draft
    # transcript reset to just this turn
    assert out["session_vars"]["ideation"]["transcript"] == ["actually forget that — different idea about dark mode"]
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
