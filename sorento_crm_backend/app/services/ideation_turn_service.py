"""Brain-path service for `ideate` WhatsApp turns (ideation pipeline, D7/D8, §5.1/§5.2).

Flow per turn (see ``documentation/plans/ideation/PLAN-ideation-ideate-intent.md`` §2c):

  1. resolve the default workspace's ``ideation_product_id`` - fail-closed (no
     ``create_idea`` call) if it or the shared-service config is unset (AC-31);
  2. read the contact's ``session_vars.ideation`` pointer (``draft_id``/``status``);
  3. run the sorento brain extractor → ``{ fields, remove, confirm }`` (D-CONFIRM);
  4. build the §5.1 input deterministically (``product_id`` from the binding,
     ``submitter`` = contact phone E.164, ``draft_id`` omitted on turn 1) and call
     shared-service ``create_idea`` over HTTP (server-to-server httpx - NOT MCP);
  5. read-modify-write ``session_vars``: KEEP ``ideation`` on ``collecting``/``review``,
     DELETE it on ``complete``/``duplicate``, preserving every other CRM key (AC-16);
  6. return ``{ status, reply_text, link?, session_vars }`` (the full updated blob).

Resilience: a shared-service outage returns a graceful ``reply_text`` and NEVER
mutates ``session_vars`` (AC-19) - mirrors the "always fail soft on the send path"
posture. Args are built deterministically, so the LLM UUID-arg coercion used on the
agent path is irrelevant here (AC-18).
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import HTTPException, status as http_status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.services import ai_prompt_registry
from app.services.ai_assistant_service import AIAssistantConfigService
from app.services.conversation_variables_service import (
    _coerce_to_dict,
    overwrite_for_contact,
)
from app.services.ideation_extractor import IdeateExtraction, extract_ideate_turn
from app.services.ideation_media_service import (
    MediaCandidate,
    MediaClients,
    build_menu_text,
    default_clients,
    extract_media_candidates,
    fold_captions_into_text,
    parse_selection,
    snapshot_and_caption,
)
from app.services.llm_provider import get_provider
from app.services.respond_workspace_service import RespondWorkspaceService

logger = logging.getLogger(__name__)

_CREATE_IDEA_PATH = "/ideation/intake/create-idea"
_TIMEOUT_SECONDS = 15

# create_idea statuses that CLOSE the draft → clear the pointer (§5.2). `duplicate`
# is retired (S1); `voted` and `cancelled` are its replacements (AC-1215).
_TERMINAL_STATUSES = {"complete", "voted", "cancelled"}

# Cap the accumulated transcript (WS-B) so a very long conversation can't bloat
# session_vars / the create_idea payload. Keeps the most recent turns.
_TRANSCRIPT_MAX_TURNS = 50

# Intake answer keys the brain extracts into (mirrors the shared-service intake
# target_schema - problem / proposed_solution / impact / department; no module or
# who - business submitters don't know the module, and the submitter identifies who).
_IDEATION_FIELD_LABELS: dict[str, str] = {
    "problem": "Problem statement",
    "proposed_solution": "Proposed solution",
    "impact": "Impact",
    "department": "Department",
}

# S3 - point-form field order for a recap reply (R10, amended by R16 to put
# Problem first): only present fields ever show; a skipped or not-yet-answered
# field is left out, never shown as blank.
_RECAP_FIELD_ORDER: tuple[tuple[str, str], ...] = (
    ("problem", "Problem"),
    ("proposed_solution", "Solution"),
    ("impact", "Impact"),
    ("department", "Department"),
)

_QUESTION_MARKS = "?？"  # ASCII ? and full-width ？ (AC-1302)


def _ideate_reply_facts(result: dict[str, Any]) -> dict[str, Any]:
    """The FACTS block for the S3 composer (R5) - status, title, captured
    answers, the next field to ask, any duplicate candidate, the idea number and
    the link. Never the model's own words: these are read straight off the
    shared-service response."""
    return {
        "status": str(result.get("status") or ""),
        "title": result.get("title") or "",
        "captured": result.get("captured") or {},
        "next_field": result.get("next_field"),
        "duplicate_candidate": result.get("duplicate_candidate") or None,
        "idea_number": result.get("idea_number"),
        "link": result.get("link"),
    }


def _ends_in_one_question(text_out: str) -> bool:
    """AC-1302: exactly one ``?``/``？`` as the last non-space character, no other."""
    stripped = (text_out or "").rstrip()
    if not stripped or stripped[-1] not in _QUESTION_MARKS:
        return False
    return sum(stripped.count(ch) for ch in _QUESTION_MARKS) == 1


def _passes_reply_checks(text_out: str, facts: dict[str, Any]) -> bool:
    """Deterministic acceptance gate for a composed reply (AC-1302 to AC-1304,
    AC-1310, AC-1311). Facts never come from the model - if the number, title,
    or link is missing or altered, this rejects the reply and the caller falls
    back to the shared-service template (R5)."""
    text_out = (text_out or "").strip()
    if not text_out:
        return False

    # AC-1307: the access-denied composition has no facts to verify beyond "the
    # LLM produced something" - the fallback template is the only shape rule.
    if facts.get("denied"):
        return True

    lines = [line.strip() for line in text_out.splitlines() if line.strip()]
    status = facts.get("status")

    if status == "complete":
        # AC-1311: line 1 the title, idea_number verbatim, at most the one URL
        # named by link and no other (R6 as amended by R13).
        title = facts.get("title")
        if title and title not in lines[0]:
            return False
        idea_number = facts.get("idea_number")
        if idea_number and idea_number not in text_out:
            return False
        link = facts.get("link")
        urls = [u.rstrip(".,;:!！)。") for u in re.findall(r"https?://\S+", text_out)]
        if link:
            if link not in text_out or any(u != link for u in urls):
                return False
        elif urls:
            return False
        return True

    if status == "duplicate_candidate":
        # AC-1304: contains the candidate title verbatim; still non-terminal ->
        # ends in the one question (AC-1302).
        candidate = facts.get("duplicate_candidate") or {}
        candidate_title = candidate.get("title")
        if candidate_title and candidate_title not in text_out:
            return False
        return _ends_in_one_question(text_out)

    # collecting / review / anything else non-terminal: AC-1310's point-form shape
    # applies to a RECAP reply - detected here as one whose first line names the
    # title (a plain clarifying answer, e.g. "what do you mean impact?", never
    # opens with the title and is exempt from the field-recap lines, AC-1310).
    title = facts.get("title")
    if title and lines and title in lines[0]:
        captured = facts.get("captured") or {}
        for key, label in _RECAP_FIELD_ORDER:
            value = captured.get(key)
            if not value:
                continue
            if not any(line.startswith(f"{label}:") and value in line for line in lines):
                return False
    return _ends_in_one_question(text_out)


def _call_ideate_reply_llm(db: Session, *, facts: dict[str, Any], user_message: str) -> str | None:
    """The S3 LLM call: same provider plumbing as the extractor, prompt key
    ``ideate_reply``. Returns ``None`` on any failure so the caller falls back to
    the shared-service template (R5) - never raises."""
    try:
        config = AIAssistantConfigService(db).get()
    except Exception:  # noqa: BLE001
        logger.warning("ideate_reply: config read failed; falling back", exc_info=True)
        return None

    api_key = config.api_key_ciphertext or settings.openai_api_key
    if not api_key:
        return None

    try:
        system, _version = ai_prompt_registry.render(db, "ideate_reply")
    except Exception:  # noqa: BLE001
        logger.warning("ideate_reply: prompt render failed; falling back", exc_info=True)
        return None

    fact_lines = [f"status: {facts.get('status') or ''}"]
    if facts.get("denied"):
        fact_lines.append(f"denied_agent: {facts['denied']}")
    if facts.get("title"):
        fact_lines.append(f"title: {facts['title']}")
    captured = facts.get("captured") or {}
    for key, label in _RECAP_FIELD_ORDER:
        value = captured.get(key)
        if value:
            fact_lines.append(f"{label}: {value}")
    if facts.get("next_field"):
        fact_lines.append(f"next_field (the ONE thing to ask next): {facts['next_field']}")
    candidate = facts.get("duplicate_candidate") or None
    if candidate:
        fact_lines.append(f"duplicate_candidate_title: {candidate.get('title')}")
    if facts.get("idea_number"):
        fact_lines.append(f"idea_number: {facts['idea_number']}")
    if facts.get("link"):
        fact_lines.append(f"link: {facts['link']}")

    user_block = (
        "FACTS (never invent, never alter these):\n"
        + "\n".join(fact_lines)
        + f"\n\nUser's latest message (read for LANGUAGE only):\n{user_message or ''}"
    )
    messages_in = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_block},
    ]

    try:
        provider = get_provider(config.provider, api_key, config.model)
        result = provider.chat(messages_in, temperature=0.3, model=config.model, max_tokens=400)
        content = (result.content or "").strip()
    except Exception:  # noqa: BLE001
        logger.warning("ideate_reply: LLM call failed; falling back", exc_info=True)
        return None
    return content or None


def _compose_ideate_reply_from_facts(
    db: Session, *, facts: dict[str, Any], user_message: str, fallback_text: str
) -> str:
    """The composer core (S3, R5): LLM first, deterministic checks, fallback to
    ``fallback_text`` (the shared-service template) on any failure or rejected
    shape (AC-1305)."""
    composed = _call_ideate_reply_llm(db, facts=facts, user_message=user_message)
    if composed is None or not _passes_reply_checks(composed, facts):
        return fallback_text
    return composed


def compose_ideate_reply(db: Session, *, result: dict[str, Any], user_message: str) -> str:
    """S3: compose the WhatsApp reply for a ``create_idea`` response from its
    FACTS (R5), falling back to the shared-service ``reply_text`` template on any
    LLM failure or a reply that fails the deterministic checks (AC-1301 to
    AC-1305, AC-1310, AC-1311)."""
    fallback_text = str(result.get("reply_text") or "")
    facts = _ideate_reply_facts(result)
    return _compose_ideate_reply_from_facts(
        db, facts=facts, user_message=user_message, fallback_text=fallback_text
    )


def compose_ideate_denial_reply(db: Session, *, user_message: str, fallback_text: str) -> str:
    """S3/AC-1307: the ``ideation`` agent's access-denied reply goes through the
    SAME composer, facts ``{denied: "ideation"}``, falling back to the existing
    ``access_denied`` canned text on any failure. Called from
    ``app.services.chatbot.lanes.canned.access_denied_text`` - the one named R18
    seam outside the ideate lane itself."""
    return _compose_ideate_reply_from_facts(
        db,
        facts={"status": "access_denied", "denied": "ideation"},
        user_message=user_message,
        fallback_text=fallback_text,
    )


class IdeationServiceError(Exception):
    """Raised when the shared-service ``create_idea`` call cannot be completed
    (outage/timeout/HTTP error/malformed body). The caller degrades to a graceful
    reply - never a 500 on the n8n send sub-flow (AC-19)."""


class _ContactState:
    __slots__ = ("phone_number", "session_vars", "display_name", "submitter_tier")

    def __init__(
        self,
        phone_number: str,
        session_vars: dict[str, Any],
        display_name: str | None = None,
        submitter_tier: str | None = None,
    ):
        self.phone_number = phone_number
        self.session_vars = session_vars
        # Human name from respond_contacts (WS-A). None when the CRM has no name
        # for this contact → handle_turn falls back to the n8n-supplied name.
        self.display_name = display_name
        # R7/AC-1207: the code of the FIRST ContactAccessType in the contact's
        # access_types relationship order (sort_order, then code). None when the
        # contact holds no access type.
        self.submitter_tier = submitter_tier


def _derive_display_name(name: Any, first_name: Any, last_name: Any) -> str | None:
    """Prefer the full ``name``; else join first+last; else None (never ""). WS-A."""
    full = (name or "").strip()
    if full:
        return full
    parts = " ".join(p for p in ((first_name or "").strip(), (last_name or "").strip()) if p)
    return parts or None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_contact_row(db: Session, respond_io_id: str) -> _ContactState:
    """Load the contact's phone (E.164 submitter), session_vars and submitter tier
    by respond_io_id. 404 when no contact matches (n8n only routes ideate turns for
    known contacts).

    ``submitter_tier`` (R7/AC-1207) is the code of the FIRST ``ContactAccessType``
    in the contact's ``access_types`` relationship order (``sort_order``, then
    ``code``) - a correlated subquery rather than an ORM relationship load, so this
    stays the single query it always was.
    """
    row = db.execute(
        text(
            "SELECT rc.phone_number, rc.name, rc.first_name, rc.last_name, "
            "rc.session_vars, "
            "(SELECT cat.code FROM respond_contact_access_types rcat "
            " JOIN contact_access_types cat ON cat.code = rcat.access_type_code "
            " WHERE rcat.contact_id = rc.id "
            " ORDER BY cat.sort_order, cat.code LIMIT 1) AS submitter_tier "
            "FROM respond_contacts rc WHERE rc.respond_io_id = :cid"
        ),
        {"cid": respond_io_id},
    ).first()
    if row is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Respond contact not found for respond_io_id={respond_io_id!r}.",
        )
    return _ContactState(
        row.phone_number,
        _coerce_to_dict(row.session_vars),
        display_name=_derive_display_name(row.name, row.first_name, row.last_name),
        submitter_tier=row.submitter_tier,
    )


class _IdeationConfig:
    """Resolved ideation shared-service connection for a turn.

    DB (default workspace row) is the source of truth; each field falls back to
    ``app.config`` settings ONLY when the workspace field is blank (keeps legacy
    ``.env`` installs working). Any missing piece => fail-closed (no create_idea).
    """

    __slots__ = ("base_url", "api_key", "product_id")

    def __init__(self, base_url: str | None, api_key: str | None, product_id: str | None):
        self.base_url = base_url
        self.api_key = api_key
        self.product_id = product_id

    @property
    def is_ready(self) -> bool:
        return bool(self.base_url and self.api_key and self.product_id)


def _resolve_ideation_config(db: Session) -> _IdeationConfig:
    """Read base URL, intake API key, and Product binding from the DEFAULT
    workspace (decrypting the key); fall back to ``app.config`` per-field when a
    workspace field is blank. DB wins; settings are the legacy fallback."""
    svc = RespondWorkspaceService(db)
    workspace = svc.get_default()

    base_url = None
    api_key = None
    product_id = None
    if workspace is not None:
        base_url = (getattr(workspace, "ideation_shared_service_url", None) or "").strip() or None
        product_id = (getattr(workspace, "ideation_product_id", None) or "").strip() or None
        api_key = svc.decrypt_ideation_api_key(workspace)

    if not base_url:
        base_url = (settings.ideation_shared_service_url or "").strip() or None
    if not api_key:
        api_key = (settings.ideation_intake_api_key or "").strip() or None

    return _IdeationConfig(base_url=base_url, api_key=api_key, product_id=product_id)


def call_create_idea(base_url: str, api_key: str, payload: dict[str, Any]) -> dict[str, Any]:
    """POST the §5.1 input to shared-service ``create_idea`` (server-to-server HTTP).

    Raises ``IdeationServiceError`` on any transport/HTTP/parse failure so the
    caller can reply gracefully instead of 500ing (AC-19)."""
    url = base_url.rstrip("/") + _CREATE_IDEA_PATH
    try:
        with httpx.Client(timeout=_TIMEOUT_SECONDS) as client:
            resp = client.post(
                url, json=payload, headers={"Authorization": f"Bearer {api_key}"}
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as exc:
        raise IdeationServiceError(f"create_idea request failed: {exc}") from exc
    except (ValueError, json.JSONDecodeError) as exc:
        raise IdeationServiceError(f"create_idea returned a malformed body: {exc}") from exc
    if not isinstance(data, dict):
        raise IdeationServiceError("create_idea returned a non-object body")
    return data


def _graceful(reply_text: str, session_vars: dict[str, Any], *, status: str) -> dict[str, Any]:
    return {"status": status, "reply_text": reply_text, "session_vars": session_vars}


def _default_fetch_recent_messages(db: Session, respond_io_id: str) -> dict[str, Any]:
    """Pull the contact's recent messages from the Respond List Messages API (DC-3).
    Best-effort: any transport/auth failure yields an empty payload → no menu, the
    turn proceeds without lookback (never a 500 on the send sub-flow)."""
    try:
        from app.services.integration_service import RespondClient

        client = RespondClient.for_identifier(db, respond_io_id)
        return client.list_messages(respond_io_id, limit=50)
    except Exception:  # noqa: BLE001 - lookback is a nicety, never fatal
        logger.warning("ideation media lookback failed for respond_io_id=%s", respond_io_id, exc_info=True)
        return {"items": []}


def _candidates_to_state(candidates: list[MediaCandidate]) -> list[dict[str, Any]]:
    return [
        {
            "source_msg_id": c.source_msg_id,
            "kind": c.kind,
            "url": c.url,
            "filename": c.filename,
            "received_at": c.received_at.isoformat() if c.received_at else None,
        }
        for c in candidates
    ]


def _state_to_candidates(rows: list[dict[str, Any]]) -> list[MediaCandidate]:
    out: list[MediaCandidate] = []
    for r in rows or []:
        received = r.get("received_at")
        try:
            received_dt = datetime.fromisoformat(received) if received else None
        except (TypeError, ValueError):
            received_dt = None
        out.append(
            MediaCandidate(
                source_msg_id=str(r.get("source_msg_id") or ""),
                kind=str(r.get("kind") or "file"),
                url=str(r.get("url") or ""),
                filename=r.get("filename"),
                received_at=received_dt,
            )
        )
    return out


def handle_turn(
    db: Session,
    *,
    respond_io_id: str,
    message_text: str,
    submitter_name: str | None = None,
    media_selection: str | None = None,
    is_new_idea: bool | None = None,
    session_vars_in: dict[str, Any] | None = None,
    media_clients: MediaClients | None = None,
    fetch_recent_messages: Any = None,
    is_test: bool = False,
) -> dict[str, Any]:
    """Handle one `ideate` turn. Returns ``{ status, reply_text, link?, session_vars }``.

    ``session_vars`` in the return is always the FULL, updated blob (AC-10).
    ``is_test`` (#1179) marks a chatbot dry-run turn: ``create_idea`` is still called,
    with ``is_test: true`` so the shared service hides the idea from the board, and the
    contact's ``session_vars`` is NOT persisted - the returned blob is the caller's to
    carry. A test pointer written to the real contact row would otherwise be read back
    by the contact's next live turn through the DB fallback below. Symmetrically
    (reviewer Blocking 2, round 1), an incoming pointer - from either
    ``session_vars_in`` or the DB fallback - is only continued when its own stamped
    ``is_test`` matches THIS turn's; a mismatch starts fresh rather than letting a
    test turn read/confirm a live draft or vice versa.
    ``submitter_name`` is the n8n Respond.io-profile fallback used only when the
    CRM's respond_contacts row has no name (WS-A). ``media_selection`` /
    ``is_new_idea`` drive multi-modal capture (Group F); ``media_clients`` and
    ``fetch_recent_messages`` are injectable seams (Respond/storage/vision) that
    default to the real integrations - tests stub them.

    The prior ideation pointer is read from the CALLER-supplied ``session_vars_in``
    first (n8n owns/writes the column and is the last writer each turn), then falls
    back to the contact's DB copy for legacy callers. This is what makes the draft
    accumulate: without it, n8n's nested ``variables.ideation`` shape never matches
    the endpoint's top-level DB read, so every turn minted a fresh ``draft_id``."""
    contact = _get_contact_row(db, respond_io_id)
    session_vars = contact.session_vars
    caller_sv = session_vars_in or {}
    ideation_state = (
        caller_sv.get("ideation")
        or (caller_sv.get("variables") or {}).get("ideation")  # n8n nested shape
        or session_vars.get("ideation")                        # legacy DB fallback
        or {}
    )
    # #1179 blocking 2 (reviewer, round 1): a pointer is continued only when its
    # `is_test` flag matches THIS turn's - a live pointer read by a test turn (or a
    # test pointer read by a live turn, e.g. across a console Reset) is exactly the
    # cross-contamination D14 exists to prevent, so it starts fresh instead. A
    # pointer with no `is_test` key (written before this fix, always by a live turn
    # back then) reads as live.
    if bool(ideation_state.get("is_test")) != bool(is_test):
        ideation_state = {}
    draft_id = ideation_state.get("draft_id")
    prior_status = ideation_state.get("status")
    prior_missing = ideation_state.get("missing") or []
    prior_next_field = ideation_state.get("next_field")
    prior_duplicate_candidate = ideation_state.get("duplicate_candidate") or None
    prior_transcript = ideation_state.get("transcript") or []
    pending_media = ideation_state.get("pending_media") or None
    seen_media_ids: set[str] = set(ideation_state.get("seen_media_ids") or [])

    turn_text = (message_text or "").strip()

    # (0) is_new_idea restart (DC-10): the user started a genuinely different idea
    # while an old draft was open. Discard the old draft, start fresh - reset the
    # pointer, transcript, and any media state so nothing leaks across ideas.
    discard_draft_id: str | None = None
    if is_new_idea and draft_id:
        discard_draft_id = draft_id
        draft_id = None
        prior_status = None
        prior_missing = []
        prior_next_field = None
        prior_duplicate_candidate = None
        prior_transcript = []
        pending_media = None
        seen_media_ids = set()

    # Submitter name: the CRM respond_contacts name wins; the n8n-supplied Respond.io
    # profile name is the fallback (WS-A / AC-CAP-1..3). Never "".
    effective_submitter_name = (
        contact.display_name or (submitter_name or "").strip() or None
    )

    # Cumulative transcript (WS-B / AC-CAP-5..7): append this turn to the running
    # log so the created idea's raw_text is the WHOLE conversation, not just the
    # finalizing "okay i confirm". Bounded to the last _TRANSCRIPT_MAX_TURNS.
    transcript_list = list(prior_transcript)
    if turn_text:
        transcript_list.append(turn_text)
    transcript_list = transcript_list[-_TRANSCRIPT_MAX_TURNS:]
    raw_transcript = "\n".join(transcript_list)

    # (1) fail-closed: no product binding or dormant config → no create_idea call.
    #     Config is DB-driven (default workspace row); .env is only a fallback.
    config = _resolve_ideation_config(db)
    product_id = config.product_id
    base_url = config.base_url
    api_key = config.api_key
    if not config.is_ready:
        return _graceful(
            "Idea capture isn't set up here yet, so I couldn't log that - please try "
            "again later or reach out to the team.",
            session_vars,
            status="unconfigured",
        )

    # (2) multi-modal capture (Group F). Resolve this turn's media into three things:
    #   attachments   → durably-captured picked media to send to create_idea
    #   menu_text      → a media menu to append to this reply (a new lookback)
    #   pending_media/seen_media_ids → the carried state written back below.
    clients = media_clients or default_clients()
    attachments: list[dict[str, Any]] = []
    menu_text: str | None = None

    if media_selection is not None and pending_media:
        # (2a) Selection answer (DC-7): resolve positions → snapshot picked media.
        candidates = _state_to_candidates(pending_media)
        picked = parse_selection(media_selection, candidates)
        if picked:
            attachments = snapshot_and_caption(picked, clients)
        seen_media_ids |= {c.source_msg_id for c in candidates}
        pending_media = None
    elif pending_media:
        # (2b) A menu was outstanding but this turn is not a selection (no position
        # reference) → dismiss it (backward-only, low friction) and proceed normally.
        seen_media_ids |= {str(r.get("source_msg_id") or "") for r in pending_media}
        pending_media = None
    else:
        # (2c) New lookback (DC-1/2/3): pull recent inbound media not already offered.
        fetcher = fetch_recent_messages or (lambda: _default_fetch_recent_messages(db, respond_io_id))
        try:
            payload_msgs = fetcher()
        except Exception:  # noqa: BLE001 - lookback nicety, never fatal
            payload_msgs = {"items": []}
        candidates = [
            c for c in extract_media_candidates(payload_msgs or {})
            if c.source_msg_id not in seen_media_ids
        ]
        if candidates:
            pending_media = _candidates_to_state(candidates)
            menu_text = build_menu_text(candidates)

    # (3) brain extraction (D-CONFIRM): structured update, never free text.
    #     next_field / the duplicate candidate's title ride along as CONTEXT ONLY
    #     (a hint, per R17) - the extractor decides which field a message updates
    #     by its meaning, never by which field was just asked (AC-1219).
    extraction: IdeateExtraction = extract_ideate_turn(
        db,
        message_text=message_text,
        status=prior_status,
        missing=prior_missing,
        next_field=prior_next_field,
        duplicate_candidate_title=(prior_duplicate_candidate or {}).get("title"),
        field_labels=_IDEATION_FIELD_LABELS,
    )

    # (4) build the §5.1 input deterministically. Captions fold into message_text so
    # create_idea's semantic collection/dedup sees the visual content (DC-6/9).
    message_for_intake = fold_captions_into_text(message_text, attachments)
    payload: dict[str, Any] = {
        "product_id": product_id,
        # Shared-service CreateIdeaIn field is ``submitter_contact_id`` (accepts a
        # phone E.164 and find-or-creates the contact copy). Sending the legacy key
        # ``submitter`` silently dropped it → every idea's submitter was "Unknown".
        "submitter_contact_id": contact.phone_number,
        "message_text": message_for_intake,
        "raw_transcript": raw_transcript,
        "fields": extraction.fields,
        "remove": extraction.remove,
        "skip": extraction.skip,
        "confirm": extraction.confirm,
        # Always present, true or false: the shared service keys its board filter on it.
        "is_test": bool(is_test),
    }
    if effective_submitter_name:
        payload["submitter_name"] = effective_submitter_name
    if extraction.title:
        payload["title"] = extraction.title
    if attachments:
        payload["attachments"] = attachments
    if draft_id:  # omitted on turn 1 (AC-12); passed through on continuation (AC-13/17)
        payload["draft_id"] = draft_id
    if discard_draft_id:  # is_new_idea restart (DC-10)
        payload["discard_draft_id"] = discard_draft_id
    # AC-1211: cancel is honoured at ANY draft status, not only review - a user may
    # drop a draft at any step.
    if extraction.review_action == "cancel":
        payload["cancel"] = True
    # AC-1214: only meaningful while the pointer is a duplicate candidate; default
    # to "separate" unless the extractor read an explicit vote (R4 default).
    if prior_status == "duplicate_candidate":
        payload["duplicate_choice"] = (
            "vote" if extraction.duplicate_choice == "vote" else "separate"
        )
    if contact.submitter_tier:
        payload["submitter_tier"] = contact.submitter_tier

    try:
        result = call_create_idea(base_url, api_key, payload)
    except IdeationServiceError:
        logger.warning("ideation create_idea outage for respond_io_id=%s", respond_io_id, exc_info=True)
        return _graceful(
            "Sorry, I couldn't save that idea just now - please try again in a moment.",
            session_vars,
            status="error",
        )

    status_val = str(result.get("status") or "")
    result_draft_id = result.get("draft_id") or draft_id
    # S3: the LLM composes the reply from the response's FACTS, in the user's
    # language, falling back to the shared-service template on any failure (R5).
    reply_text = compose_ideate_reply(db, result=result, user_message=message_text)
    link = result.get("link")

    # The media menu is appended to THIS reply (DC-8) - the create_idea echo first,
    # then "which of these files relate?".
    if menu_text:
        reply_text = f"{reply_text}\n\n{menu_text}" if reply_text else menu_text

    # (5) read-modify-write: only touch the `ideation` key, preserve all others.
    new_session_vars = dict(session_vars)
    if status_val in _TERMINAL_STATUSES:
        new_session_vars.pop("ideation", None)  # AC-13c/14/15
    else:  # collecting or review → keep the pointer (AC-12/12b/13b)
        ideation_blob: dict[str, Any] = {
            "draft_id": result_draft_id,
            "status": status_val,
            "missing": list(result.get("missing") or []),
            # The one optional field to ask next (S1), carried so the NEXT turn's
            # extractor gets it as a hint (R17) and the reply composer (S3) can
            # read it from the pointer too.
            "next_field": result.get("next_field"),
            # Persist the running transcript so the NEXT turn appends to it (WS-B).
            "transcript": transcript_list,
            "updated_at": _now_iso(),
            # #1179 blocking 2: stamped so a LATER turn can refuse to continue this
            # pointer if its own `is_test` does not match (see the read-side guard
            # above).
            "is_test": bool(is_test),
        }
        # AC-1212: while a similar idea is offered, keep the candidate on the
        # pointer so the next turn's extractor/reply have its title to hand.
        if status_val == "duplicate_candidate" and result.get("duplicate_candidate"):
            ideation_blob["duplicate_candidate"] = result.get("duplicate_candidate")
        # Carry the media state (Group F): the outstanding menu + everything already
        # offered, so a later turn resolves the selection and we never re-nag.
        if pending_media:
            ideation_blob["pending_media"] = pending_media
        if seen_media_ids:
            ideation_blob["seen_media_ids"] = sorted(seen_media_ids)
        new_session_vars["ideation"] = ideation_blob
    if not is_test:
        overwrite_for_contact(db, respond_io_id=respond_io_id, state=new_session_vars)

    response: dict[str, Any] = {
        "status": status_val,
        "reply_text": reply_text,
        "session_vars": new_session_vars,
    }
    if link:
        response["link"] = link
    return response
