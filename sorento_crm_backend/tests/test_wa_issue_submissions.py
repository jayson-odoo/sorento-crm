"""WA-COMPLAINT-INTAKE red tests (core): typed submissions on the ideation path.

UAC: documentation/plans/chatbot/wa-complaint-intake-acceptance-criteria.md (card v2),
plan PLAN-wa-complaint-intake-13nov.md "Design (card v2)" + "Reuse map". Owner answer Q1: the
type is a real Shared Service field (`type`), NO department bridge.

Contract these tests pin (names fixed so the coder can match them):

* `app.services.submission_types`: `SUBMISSION_TYPES` (keys "idea", "issue"), `DEFAULT_TYPE = "idea"`,
  `normalise_type(value) -> str` (unknown/None -> "idea"), `ss_fields_for_type(type) -> dict`
  ("issue" -> {"type": "issue"}, "idea" -> {}), `type_of_idea(idea: dict) -> str` (reads the ss idea
  JSON `type` key, case-insensitive, unknown/missing -> "idea"; never reads `department`).
* `ideation_capture_service.build_create_payload(..., submission_type="idea")`.
* `IdeateExtraction.type` (default "idea"); the extractor JSON schema has `type` enum [idea, issue].
* `handle_capture_turn`: issue reply one fact per line (`Logged as issue <number>` / title /
  `Photos: N` only when N > 0 / link), issue ask-back in en/ms/zh.
* Chat photos: images the contact sent (attachments linked to `chatbot_turn`, uploaded by the contact)
  in the last 30 minutes and after the previous submission, at most 10, newest first, uploaded through
  `app.services.ideation_gateway_service.upload_idea_attachment(db, user, idea_id, filename, content,
  content_type)`, which the staff route `POST /api/v1/ideation/ideas/{id}/attachments` calls too.
  Bytes are read through `storage_router.get_backend(provider).download_file(key)` (the
  `ResourcesService.get_file_content_for` seam), patched here.
* Parser template: CRM/assistant problems route to ideate; product/order complaints stay portal_link.

Postgres only (blank schema via tests/_pg_fixture.py), every test seeds its own chain. The capture
turn harness (`env`) is reused from tests/test_ideation_capture_turn.py: extractor, similar-own and
create are patched there. Names that do not exist yet are reached at call time, so a missing name
fails its test and never the collection.
"""
from __future__ import annotations

import inspect
import re
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

# MUST be the first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from app.models.chatbot_turn import ChatbotTurn
from app.models.entity_attachment import EntityAttachmentLink
from app.models.resources import Attachment
from app.services.chatbot_reply_copy import IDEATION_CAPTURE_ASK_IDEA
from app.services.ideation_extractor import IdeateExtraction
from tests._ideation_ss_fake import FakeSS, configure_embed_settings
from tests._pg_fixture import blank_session
from tests.test_ideation_capture_turn import CRM, PROBLEM, TITLE, Env, env  # noqa: F401  (fixture)
from tests.test_ideation_extractor import _StubProvider, configured, db_session  # noqa: F401  (fixtures)

UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
ISSUE_ASK_EN = "What went wrong? Tell me what you saw and where."
ISSUE_MSG = "the stock page shows a blank screen when I open it on my phone"
IDEA_NUMBER = "IDEA-0184"
UPLOAD_ARGS = ("db", "user", "idea_id", "filename", "content", "content_type")


def _submission_types():
    import app.services.submission_types as st

    return st


# --------------------------------------------------------------------------- #
# Shared photo helpers (also imported by the agent test)                      #
# --------------------------------------------------------------------------- #
def _naive_utc(minutes_ago: float) -> datetime:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).replace(tzinfo=None)


def seed_chat_photo(
    db,
    *,
    contact_pk: str,
    respond_id: str,
    minutes_ago: float,
    mime: str = "image/jpeg",
    name: str | None = None,
) -> Attachment:
    """One file the contact sent in chat, stored the way `media_tasks._store_media_bytes` stores it:
    an `attachments` row uploaded by the contact, linked to a real `chatbot_turn`."""
    when = _naive_utc(minutes_ago)
    turn = ChatbotTurn(
        id=str(uuid.uuid4()),
        contact_respond_id=respond_id,
        message_id=f"zzt-msg-{uuid.uuid4().hex[:8]}",
        envelope={},
        status="done",
    )
    db.add(turn)
    db.flush()
    ext = "jpg" if mime.startswith("image/") else "pdf"
    stored = name or f"zzt-{uuid.uuid4().hex[:10]}.{ext}"
    att = Attachment(
        id=str(uuid.uuid4()),
        original_filename=stored,
        stored_filename=stored,
        file_path=f"https://cdn.zzt.example/chatbot-media/{stored}",
        file_size_bytes=10,
        mime_type=mime,
        uploader_kind="contact",
        uploaded_by_contact_id=contact_pk,
        uploaded_at=when,
        created_at=when,
        storage_provider="s3",
    )
    db.add(att)
    db.flush()
    db.add(
        EntityAttachmentLink(
            entity_type="chatbot_turn",
            entity_id=str(turn.id),
            attachment_id=att.id,
            created_at=when,
        )
    )
    db.flush()
    return att


class PhotoSeam:
    """The patched upload function + storage reads. `fail_first` makes the first upload raise."""

    def __init__(self) -> None:
        self.uploads: list[dict[str, Any]] = []
        self.reads: list[str] = []
        self.fail_first = False

    def upload(self, *args, **kwargs):
        call = dict(zip(UPLOAD_ARGS, args))
        call.update(kwargs)
        self.uploads.append(call)
        if self.fail_first and len(self.uploads) == 1:
            raise RuntimeError("ss refused the upload")
        return httpx.Response(
            201, json={"id": str(uuid.uuid4())}, request=httpx.Request("POST", "http://ss.zzt.example/x")
        )

    def filenames(self) -> list[str]:
        return [str(c.get("filename")) for c in self.uploads]

    def idea_ids(self) -> set[str]:
        return {str(c.get("idea_id")) for c in self.uploads}


class _FakeBackend:
    def __init__(self, seam: PhotoSeam) -> None:
        self.seam = seam

    def download_file(self, key: str) -> bytes:
        self.seam.reads.append(key)
        return b"\xff\xd8zzt-image-bytes:" + key.encode()


def install_photo_seam(monkeypatch, *extra_modules) -> PhotoSeam:
    """Patch the shared upload function where it lives (and where a caller may have bound it at import)
    and the storage byte read."""
    import app.services.ideation_gateway_service as gateway
    import app.services.storage_router as storage_router

    seam = PhotoSeam()
    backend = _FakeBackend(seam)
    monkeypatch.setattr(gateway, "upload_idea_attachment", seam.upload, raising=False)
    monkeypatch.setattr(storage_router, "get_backend", lambda provider=None: backend)
    for mod in extra_modules:
        monkeypatch.setattr(mod, "upload_idea_attachment", seam.upload, raising=False)
        if hasattr(mod, "get_backend"):
            monkeypatch.setattr(mod, "get_backend", lambda provider=None: backend)
    return seam


def _user_id_of(user: Any) -> str:
    return str(user["id"] if isinstance(user, dict) else getattr(user, "id", user))


# --------------------------------------------------------------------------- #
# T-1 / T-2: the one type table and the one mapping                           #
# --------------------------------------------------------------------------- #
def test_T1_the_type_table_has_idea_and_issue_and_defaults_to_idea():
    st = _submission_types()
    assert set(st.SUBMISSION_TYPES) == {"idea", "issue"}
    assert st.DEFAULT_TYPE == "idea"


@pytest.mark.parametrize(
    "value, expected",
    [("idea", "idea"), ("issue", "issue"), ("ISSUE", "issue"), (" Issue ", "issue"),
     (None, "idea"), ("", "idea"), ("complaint", "idea"), (42, "idea")],
)
def test_T1_normalise_type_unknown_or_missing_is_idea(value, expected):
    assert _submission_types().normalise_type(value) == expected


def test_T2_ss_fields_for_type_issue_is_the_ss_type_field_and_idea_sends_nothing():
    st = _submission_types()
    assert st.ss_fields_for_type("issue") == {"type": "issue"}
    assert st.ss_fields_for_type("idea") == {}
    assert st.ss_fields_for_type("nonsense") == {}


@pytest.mark.parametrize(
    "idea, expected",
    [
        ({"type": "issue"}, "issue"),
        ({"type": "Issue"}, "issue"),
        ({"type": "ISSUE"}, "issue"),
        ({"type": "idea"}, "idea"),
        ({"type": "bug"}, "idea"),
        ({"type": None}, "idea"),
        ({}, "idea"),
        ({"title": "x", "department": "Ops"}, "idea"),
    ],
)
def test_T2_type_of_idea_reads_the_ss_type_key(idea, expected):
    assert _submission_types().type_of_idea(idea) == expected


def test_T2_type_of_idea_never_reads_department():
    # Q1: no department bridge. An idea whose department happens to be "Issue" is still an idea.
    assert _submission_types().type_of_idea({"department": "Issue"}) == "idea"
    assert _submission_types().type_of_idea({"department": "issue", "type": "idea"}) == "idea"


def _payload(**kw):
    from app.services.ideation_capture_service import build_create_payload

    config = SimpleNamespace(product_id="prod-zzt")
    contact = SimpleNamespace(phone_number="+60120000001", submitter_tier=None)
    return build_create_payload(
        config,
        user_id="user-1",
        contact=contact,
        name="USER A",
        fields={"problem": PROBLEM},
        title=TITLE,
        use_cases=[],
        source_text="raw text",
        intake_ref="ref-1",
        is_test=False,
        **kw,
    )


def test_T2_build_create_payload_issue_carries_the_ss_type_and_no_department():
    payload = _payload(submission_type="issue")
    assert payload["type"] == "issue"
    assert "department" not in payload
    assert payload["problem"] == PROBLEM


def test_T2_build_create_payload_idea_is_byte_identical_to_today():
    today = _payload()
    assert "type" not in today and "department" not in today
    assert _payload(submission_type="idea") == today
    # An unknown type is an idea (T-1).
    assert _payload(submission_type="whatever") == today


# --------------------------------------------------------------------------- #
# T-3: the extractor reads the type by meaning (schema enum, model scripted)  #
# --------------------------------------------------------------------------- #
def test_T3_the_extraction_defaults_to_idea():
    assert IdeateExtraction().type == "idea"


def test_T3_the_extractor_schema_has_a_required_type_enum():
    from app.services.ideation_extractor import IDEATE_EXTRACTION_JSON_SCHEMA as schema

    prop = schema["properties"]["type"]
    assert prop["type"] == "string"
    assert sorted(prop["enum"]) == ["idea", "issue"]
    assert prop.get("description"), "the model needs the meaning of each type"
    # OpenAI strict mode: every property is required.
    assert "type" in schema["required"]


def _scripted(db, message: str, model_out: dict) -> IdeateExtraction:
    from unittest.mock import patch

    from app.services.ideation_extractor import extract_ideate_turn

    payload = {
        "fields": [], "remove": [], "skip": [], "title": "", "review_action": "none", "change_text": "",
        "duplicate_choice": "none", "use_cases": [], "has_idea": True, "language": "en", **model_out,
    }
    with patch("app.services.ideation_extractor.get_provider", return_value=_StubProvider(payload)):
        return extract_ideate_turn(db, message_text=message)


@pytest.mark.parametrize(
    "message, model_out, expected",
    [
        ("The order page crashes every time I press save",
         {"type": "issue", "fields": [{"key": "problem", "value": "The order page crashes on save"}]}, "issue"),
        ("bot tak bgi jawapn bila sy tanya stok",
         {"type": "issue", "language": "ms",
          "fields": [{"key": "problem", "value": "bot tak bagi jawapan bila tanya stok"}]}, "issue"),
        ("It would be great if the stock list showed the nearest warehouse first",
         {"type": "idea", "fields": [{"key": "problem", "value": "The stock list is long"}]}, "idea"),
        ("Hi good morning, the assistant gave me the wrong price for the basin",
         {"type": "issue", "fields": [{"key": "problem", "value": "The assistant gave a wrong price"}]}, "issue"),
    ],
    ids=["en_bug", "ms_bug_typo", "feature_request", "greeting_prefixed_report"],
)
def test_T3_the_models_type_lands_on_the_extraction(configured, message, model_out, expected):  # noqa: F811
    got = _scripted(configured, message, model_out)
    assert got.failed is False
    assert got.type == expected


@pytest.mark.parametrize("raw", ["complaint", None, 7])
def test_T3_an_unknown_model_type_reads_as_idea(configured, raw):  # noqa: F811
    got = _scripted(configured, ISSUE_MSG, {"type": raw, "fields": [{"key": "problem", "value": "x"}]})
    assert got.type == "idea"


# --------------------------------------------------------------------------- #
# I-1 / I-3: the bot lane files an issue and replies one fact per line         #
# --------------------------------------------------------------------------- #
def _issue(e: Env, text: str = ISSUE_MSG, *, language: str | None = None) -> str:
    e.idea_message(text, language=language)
    e.extractions[text].type = "issue"
    return text


def _lines(reply: str) -> list[str]:
    return [line.strip() for line in reply.splitlines() if line.strip()]


def test_I1_an_issue_creates_at_once_with_the_ss_type_field(env):  # noqa: F811
    env.ready()
    env.created()
    out = env.turn(_issue(env))
    assert out["status"] == "complete"
    (payload,) = env.create_calls
    assert payload["type"] == "issue"
    assert "department" not in payload
    assert payload["problem"] == PROBLEM


def test_I3_the_issue_reply_is_one_fact_per_line_in_english(env):  # noqa: F811
    env.ready()
    idea_id = env.created()
    out = env.turn(_issue(env, language="en"))
    lines = _lines(out["reply_text"])
    assert f"Logged as issue {IDEA_NUMBER}" in lines
    assert TITLE in lines
    assert f"{CRM}/ideas/{idea_id}" in lines
    # No photos sent: no Photos line at all.
    assert not any(line.startswith("Photos") for line in lines)
    # No id outside the link line.
    assert not [line for line in lines if UUID_RE.search(line) and not line.startswith(CRM)]


def test_I3_an_idea_keeps_todays_reply_and_payload(env):  # noqa: F811
    env.ready()
    idea_id = env.created()
    text = env.idea_message(language="en")
    env.extractions[text].type = "idea"
    out = env.turn(text)
    assert out["status"] == "complete"
    assert out["reply_text"] == (
        f"Idea {IDEA_NUMBER} is in: {TITLE}\n"
        "Open it to add what I didn't catch:\n"
        "- Desired outcome\n- Use cases\n- Current workaround\n- Photos or files\n"
        f"{CRM}/ideas/{idea_id}"
    )
    (payload,) = env.create_calls
    assert "type" not in payload and "department" not in payload


def test_I3_a_malay_issue_is_answered_in_malay(env):  # noqa: F811
    env.ready()
    idea_id = env.created()
    out = env.turn(_issue(env, "skrin stok kosong bila buka kat phone", language="ms"))
    assert out["status"] == "complete"
    assert out["language"] == "ms"
    lines = _lines(out["reply_text"])
    assert not any("Logged as issue" in line for line in lines), "the English line in a Malay reply"
    assert any(IDEA_NUMBER in line for line in lines)
    assert TITLE in lines
    assert f"{CRM}/ideas/{idea_id}" in lines
    (payload,) = env.create_calls
    assert payload["type"] == "issue"


# --------------------------------------------------------------------------- #
# I-2: an issue with no description asks once, then gives up                  #
# --------------------------------------------------------------------------- #
def _empty_issue(e: Env, text: str, language: str) -> str:
    e.extraction(text, fields={}, language=language)
    e.extractions[text].type = "issue"
    e.extractions[text].has_idea = False
    return text


def test_I2_an_issue_with_no_description_asks_what_went_wrong(env):  # noqa: F811
    env.ready()
    out = env.turn(_empty_issue(env, "I want to report a problem", "en"))
    assert out["status"] == "ask_idea"
    assert out["reply_text"] == ISSUE_ASK_EN
    assert env.create_calls == []


@pytest.mark.parametrize("language", ["ms", "zh"])
def test_I2_the_issue_ask_back_exists_in_malay_and_chinese(env, language):  # noqa: F811
    env.ready()
    out = env.turn(_empty_issue(env, f"report problem {language}", language))
    assert out["status"] == "ask_idea"
    reply = out["reply_text"]
    assert reply.strip()
    assert reply != ISSUE_ASK_EN
    # Its own copy, not the idea ask-back.
    assert reply != IDEATION_CAPTURE_ASK_IDEA[language]


def test_I2_a_second_empty_answer_gives_up(env):  # noqa: F811
    env.ready()
    out = env.turn_ask(_empty_issue(env, "something is wrong", "en"))
    assert out["status"] == "ask_idea_gave_up"
    assert out["reply_text"] != ISSUE_ASK_EN
    assert env.create_calls == []


# --------------------------------------------------------------------------- #
# P-1 / P-2 / P-3 / I-5: chat photos onto the new item                         #
# --------------------------------------------------------------------------- #
@pytest.fixture
def photos(env, monkeypatch):  # noqa: F811
    return install_photo_seam(monkeypatch, env.svc)


def _seed(e: Env, **kw) -> Attachment:
    return seed_chat_photo(e.db, contact_pk=e.contact.id, respond_id=e.rio, **kw)


def test_P1_the_recent_images_are_uploaded_to_the_new_item_as_the_user(env, photos):
    env.ready()
    idea_id = env.created()
    recent_a = _seed(env, minutes_ago=2)
    recent_b = _seed(env, minutes_ago=5)
    old = _seed(env, minutes_ago=45)
    pdf = _seed(env, minutes_ago=3, mime="application/pdf")
    # Another contact's photo is never theirs to send.
    other = RespondContactFactory.make(env.db)
    stranger = seed_chat_photo(env.db, contact_pk=other.id, respond_id=other.respond_io_id, minutes_ago=1)

    out = env.turn(_issue(env))

    assert out["status"] == "complete"
    assert len(photos.uploads) == 2, photos.uploads
    assert photos.idea_ids() == {idea_id}
    assert sorted(photos.filenames()) == sorted([recent_a.original_filename, recent_b.original_filename])
    for name in (old.original_filename, pdf.original_filename, stranger.original_filename):
        assert name not in photos.filenames()
    for call in photos.uploads:
        assert _user_id_of(call["user"]) == str(env.user.id)
        assert str(call["content_type"]).startswith("image/")
        assert call["content"].startswith(b"\xff\xd8zzt-image-bytes:")
    assert "Photos: 2" in _lines(out["reply_text"])


def test_P1_at_most_ten_newest_first(env, photos):
    env.ready()
    env.created()
    seeded = [_seed(env, minutes_ago=1 + i) for i in range(12)]  # seeded[0] is the newest
    out = env.turn(_issue(env))
    assert out["status"] == "complete"
    assert photos.filenames() == [a.original_filename for a in seeded[:10]]
    assert "Photos: 10" in _lines(out["reply_text"])


def test_P2_a_failed_upload_never_fails_the_filing(env, photos):
    env.ready()
    env.created()
    _seed(env, minutes_ago=2)
    _seed(env, minutes_ago=4)
    photos.fail_first = True
    out = env.turn(_issue(env))
    assert out["status"] == "complete"
    assert len(photos.uploads) == 2
    lines = _lines(out["reply_text"])
    assert f"Logged as issue {IDEA_NUMBER}" in lines
    assert "Photos: 1" in lines


def test_P3_a_second_filing_does_not_resend_photos(env, photos):
    env.ready()
    env.created()
    _seed(env, minutes_ago=2)
    _seed(env, minutes_ago=3)
    first = env.turn(_issue(env))
    assert first["status"] == "complete" and len(photos.uploads) == 2

    photos.uploads.clear()
    env.created()
    second = env.turn(_issue(env, "the search box also freezes on the order page"))
    assert second["status"] == "complete"
    assert photos.uploads == []
    assert not any(line.startswith("Photos") for line in _lines(second["reply_text"]))


def test_P3_a_photo_sent_after_the_previous_filing_goes_with_the_next(env, photos):
    env.ready()
    env.created()
    _seed(env, minutes_ago=2)
    env.turn(_issue(env))
    photos.uploads.clear()

    newer = _seed(env, minutes_ago=0)
    second_id = env.created()
    out = env.turn(_issue(env, "and the totals on the invoice page are wrong"))
    assert photos.filenames() == [newer.original_filename]
    assert photos.idea_ids() == {second_id}
    assert "Photos: 1" in _lines(out["reply_text"])


def test_I5_a_test_turn_uploads_no_photos(env, photos):
    env.ready()
    env.created()
    _seed(env, minutes_ago=2)
    out = env.turn(_issue(env), is_test=True)
    assert out["status"] == "complete"
    assert env.create_calls[0]["is_test"] is True
    assert env.create_calls[0]["type"] == "issue"
    assert photos.uploads == []
    assert not any(line.startswith("Photos") for line in _lines(out["reply_text"]))


def test_P1_an_idea_whose_photos_landed_does_not_ask_for_photos(env, photos):  # noqa: F811
    env.ready()
    env.created()
    _seed(env, minutes_ago=2)
    out = env.turn(env.idea_message(language="en"))
    assert out["status"] == "complete"
    assert len(photos.uploads) == 1
    assert "- Photos or files" not in _lines(out["reply_text"])
    assert "- Desired outcome" in _lines(out["reply_text"])


def test_P2_an_idea_whose_photos_all_failed_still_asks_for_photos(env, photos):  # noqa: F811
    env.ready()
    env.created()
    _seed(env, minutes_ago=2)
    photos.fail_first = True
    out = env.turn(env.idea_message(language="en"))
    assert out["status"] == "complete"
    assert "- Photos or files" in _lines(out["reply_text"])


class RespondContactFactory:
    @staticmethod
    def make(db):
        from app.models.access import RespondContact

        c = RespondContact(
            id=str(uuid.uuid4()),
            phone_number=f"+6013{uuid.uuid4().int % 10**8:08d}",
            name="CONTACT B",
            respond_io_id=f"rio-{uuid.uuid4().hex[:10]}",
            session_vars={},
        )
        db.add(c)
        db.flush()
        return c


# --------------------------------------------------------------------------- #
# The staff gateway: one upload function, `type` forwarded                     #
# --------------------------------------------------------------------------- #
BASE = "/api/v1/ideation"
IDEA = "7c1d0b7e-0000-4000-8000-00000000b001"


@pytest.fixture
def gw(monkeypatch):
    """The `/api/v1/ideation` gateway with ss faked at httpx (as tests/test_ideation_gateway.py)."""
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.models.user import User
    from app.services import ideation_gateway_service
    from app.services.company_scope_resolver import apply_company_scope
    from app.services.user_service import UserPermissionService

    configure_embed_settings(monkeypatch)
    fake = FakeSS().install(monkeypatch)
    allow = {"ideation.board.view", "ideation.ideas.manage"}
    monkeypatch.setattr(UserPermissionService, "check_user_has_permission", lambda self, uid, slug: slug in allow)
    monkeypatch.setattr(UserPermissionService, "get_user_permission_slugs", lambda self, uid: list(allow))
    ideation_gateway_service.clear_token_cache()

    with blank_session() as db:
        uid = str(uuid.uuid4())
        email = f"zzt-{uid[:8]}@example.test"
        db.add(User(id=uid, email=email, name="Alice Tan", status="ACTIVE"))
        db.commit()
        user = {"id": uid, "email": email, "name": "Alice Tan"}

        def _db():
            yield db

        app.dependency_overrides[get_db] = _db
        app.dependency_overrides[get_current_user] = lambda: dict(user)
        app.dependency_overrides[get_current_user_or_api_key] = lambda: dict(user)
        app.dependency_overrides[apply_company_scope] = lambda: None
        try:
            yield SimpleNamespace(
                client=TestClient(app, raise_server_exceptions=False), fake=fake, db=db, user=user
            )
        finally:
            app.dependency_overrides.clear()
            ideation_gateway_service.clear_token_cache()


def test_P1_the_shared_upload_function_posts_multipart_to_ss_as_the_user(gw):
    from app.services.ideation_gateway_service import upload_idea_attachment

    gw.fake.route("POST", f"/embed/ideas/{IDEA}/attachments", status=201, json_body={"id": "a"})
    upload_idea_attachment(gw.db, gw.user, IDEA, "screen.jpg", b"zzt-jpeg", "image/jpeg")
    (call,) = gw.fake.calls
    assert call["method"] == "POST" and call["path"] == f"/embed/ideas/{IDEA}/attachments"
    assert call["headers"]["content-type"].startswith("multipart/form-data")
    assert b'filename="screen.jpg"' in call["content"]
    assert b"zzt-jpeg" in call["content"]


def test_P1_the_shared_upload_function_signature_is_fixed():
    from app.services.ideation_gateway_service import upload_idea_attachment

    assert tuple(inspect.signature(upload_idea_attachment).parameters)[:6] == UPLOAD_ARGS


def test_P1_the_staff_upload_route_calls_the_shared_upload_function(gw, monkeypatch):
    import app.api.v1.ideation.ideas as ideas_route

    seam = install_photo_seam(monkeypatch, ideas_route)
    resp = gw.client.post(
        f"{BASE}/ideas/{IDEA}/attachments", files={"file": ("brief.png", b"zzt-png", "image/png")}
    )
    assert len(seam.uploads) == 1, (resp.status_code, resp.text)
    (call,) = seam.uploads
    assert str(call["idea_id"]) == IDEA
    assert call["filename"] == "brief.png"
    assert call["content"] == b"zzt-png"
    assert call["content_type"] == "image/png"
    assert _user_id_of(call["user"]) == gw.user["id"]
    assert gw.fake.calls == [], "the route must not post to ss itself any more"


def test_B_the_staff_create_forwards_type(gw):
    gw.fake.route("POST", "/embed/ideas", status=201, json_body={"id": IDEA})
    gw.client.post(f"{BASE}/ideas", json={"problem": "p", "type": "issue", "productId": "other"})
    assert gw.fake.calls[0]["json"] == {"problem": "p", "type": "issue"}


def test_B_the_staff_create_still_forwards_department_unchanged(gw):
    gw.fake.route("POST", "/embed/ideas", status=201, json_body={"id": IDEA})
    gw.client.post(f"{BASE}/ideas", json={"problem": "p", "department": "Ops"})
    assert gw.fake.calls[0]["json"] == {"problem": "p", "department": "Ops"}


def test_B_the_list_forwards_the_type_filter(gw):
    gw.fake.route("GET", "/embed/ideas", json_body=[])
    gw.client.get(f"{BASE}/ideas", params={"type": "issue", "filter": "archived", "search": "stock"})
    assert gw.fake.calls[0]["query"] == {"type": "issue", "filter": "archived", "search": "stock"}


def test_B_the_list_without_type_is_unchanged(gw):
    gw.fake.route("GET", "/embed/ideas", json_body=[])
    gw.client.get(f"{BASE}/ideas", params={"filter": "archived", "colour": "red"})
    assert gw.fake.calls[0]["query"] == {"filter": "archived"}
