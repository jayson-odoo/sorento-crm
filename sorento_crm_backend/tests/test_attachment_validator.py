"""S2a gate - the core attachment validator (AC-M20 to AC-M25, AC-M27).

Written BEFORE the implementation. Every failure here should name a missing module,
column, constant or function. The guards that pass by construction live in
``tests/test_attachment_validator_guards.py`` so this file's red count reads as real
work outstanding.

**This is not after-sales work.** The validator lives in the ``resources`` module
beside attachments (AC-M21) and ships to every module that already depends on
``resources``. Three slices consume it - S3 (consumer intake evidence), S6
(technician proof), S11 (``rma_readiness`` collection proof) - and none of them
exists yet. What S2a owns is the mechanism plus ONE wiring: the shared
``workflow_submission_attachments`` upload path, which the plan itself names as the
reason the validator reaches complaints, service jobs and the forms platform without
a per-domain path.

Nine things shape this suite, and every one of them is a place the AC is silent or
where the obvious implementation is wrong. They are decided here rather than left to
the implementer, because an answer nobody wrote down gets re-decided by the next
person in the opposite direction.

1. **"Unvalidated" is a DISTINCT state from "scored badly", and AC-M22's five columns
   cannot express it.** A hard timeout degrading to score 0 or to a NULL that the UI
   reads as failure refuses a good photo because the network was slow - a technician
   in a basement at 6pm loses the job he just closed. This is the same property S2's
   ``resolve`` protects by making ``unknown`` a verdict rather than an empty list
   (AC-D17), and the resolution is the same: an EXPLICIT state, never a derived one.
   Two columns are added beyond AC-M22 (``ai_validation_state``,
   ``ai_validation_reason``); see the correction block in the report. One answers "may
   I trust ai_score", the other answers "why not", and the second is the only thing
   that distinguishes "my timeout is too short" from "my provider key is wrong".

2. **The score scale is stated nowhere.** ``min_score`` has to be comparable to
   ``ai_score`` and no AC says whether either is 0-1, 0-100, integer or numeric. Pinned
   as **integer 0-100 on both**: ``min_score`` is admin data entry in the same dialog as
   ``max_file_size_mb``, and an admin who types ``70`` meaning 70% into a 0-1 column sets
   a threshold nothing can ever clear, silently and permanently. The reverse mistake is
   made by the MODEL, so a returned score strictly between 0 and 1 is treated as a scale
   mismatch and degrades to unvalidated rather than rounding to 0 and refusing a good
   photo.

3. **``min_score = 0`` and ``min_score = NULL``.** Same table, same footgun family as
   F2c's ``max_count_per_entity = 0``, which silently means "never attachable" rather
   than "unlimited". Pinned in the permissive direction, both of them: NULL is advisory
   (scored, suggestion shown, nothing ever fails), 0 is a gate every score clears
   because ``score >= 0`` is always true. Neither may ever read as "no photo passes".
   A ``min_score`` outside 0..100 is refused at the WRITE, because 150 bricks a type
   forever and nothing in the UI would say why.

4. **``validate_on_upload = true`` with blank ``validation_guidance``** is a type that
   promises validation with nothing to validate against, and whatever the model returns
   for an empty guidance will look authoritative. Both halves are pinned: the write path
   refuses the configuration, AND the runtime degrades to unvalidated with NO model call
   if such a row exists anyway (a migration, a raw INSERT and another worktree are all
   paths into this table that the write guard does not cover).

5. **"Use anyway requires a reason" is a UI sentence** (AC-M24), and a guard on the
   action routes is not a guard (ADR-0013 rule 7). It is enforced in the service, which
   also refuses an override on a link that did not fail - there is nothing to override,
   and a reason recorded against a passing upload pollutes the one metric AC-M24 exists
   to produce: the override reason is what says the GUIDANCE is wrong rather than the
   uploader.

6. **The file is stored and the link written regardless of score.** AC-M23 and AC-M24
   never say so together. A validator that discards the bytes it judged makes Retake
   free but makes the failure unobservable, and it means a timeout loses a photo that
   was already taken. Nothing in this journey blocks on a nicety - the same rule as
   AC-M27, AC-M38 and AC-C14.

7. **Two different latitude/longitude now exist.** S1 put them on ``complaints`` as the
   Site (AC-B21, ``Numeric(10,7)``); AC-M22 puts them on the LINK row as where THIS
   photo was taken. Same name, different question. Pinned to the same type and precision
   so a reader comparing them is comparing like with like, and pinned as ABSENT from
   ``attachments`` (guards file) so one fact never gets two homes.

8. **The validator receives BYTES, never a URL.** Uploads route through
   ``storage_router`` with ``s3`` and ``r2`` providers and R2 keys are not always public,
   so a validator built on a presigned URL behaves differently per provider and breaks
   for whichever one the tenant is mid-migration on. ``ai_extract`` already sets the
   precedent (``ExtractFile(filename, mime, data)``), and validation runs on upload,
   where the bytes are in hand before anything is stored.

9. **A type that does not opt in must upload EXACTLY as it does today.** This slice
   touches a table every module already uses. ``validate_on_upload = false`` means no
   model call, no latency, no new failure mode, and NULL in every new column.

Everything runs on Postgres via ``blank_session`` - never sqlite. No test calls a real
model: the provider is a spy, patched on the defining module and on the validator
module, because this repo's call sites bind names locally.

Run: venv/bin/python -m pytest tests/test_attachment_validator.py -q -p no:randomly
"""
from __future__ import annotations

import base64
import importlib
import importlib.util
import inspect
import json
import time
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import Boolean, Integer, Numeric, String, Text

from app.models.complaints import Complaint
from app.models.entity_attachment import EntityAttachmentLink
from app.models.resources import Attachment, AttachmentType
from app.models.workflow_forms import WorkflowFormDefinition, WorkflowFormVersion
from app.services.error_handler import AppException
from app.services.llm_provider import ChatResult
from app.status_engine import registry as status_registry

from ._pg_fixture import TEST_PREFIX, blank_session, unique_code

# --------------------------------------------------------------------- contract
#
# Names S2a is expected to add, as constants so the implementer reads the whole
# contract on one screen and a rename is one edit.

# AC-M21: ONE validator, in `resources`, beside the attachment machinery it extends.
# Not app/services/service_jobs/, not app/services/complaints/, not a second copy in
# the portal. `resources` is the module three unrelated slices already depend on.
VALIDATOR_MODULE = "app.services.attachment_validation_service"

# AC-M25: the prompt is registry data, not a string in the service.
#
# NOT `validator`. PROMPT_KEYS already has a key by that name - "Validator -
# confidence-gate the answer before send" (M3a) - and reusing it would put an
# attachment-photo instruction in front of the assistant's answer gate the moment
# M3a activates. Different node, different key.
PROMPT_KEY = "attachment_validator"
PROMPT_VARIABLE = "validation_guidance"

# The one upload path S2a wires. The plan cites workflow_submission_attachments.py
# precisely because it already routes BOTH submission and line attachments through the
# single link table, so wiring it once reaches all three consuming slices.
UPLOAD_MODULE = "app.services.workflow_submission_attachments"

# AC-M20: three columns on the per-type upload policy table. No new tables.
TYPE_COLUMNS = ("validation_guidance", "min_score", "validate_on_upload")

# AC-M22 names five. Two more are added; see finding 1 in the module docstring.
LINK_COLUMNS_FROM_AC = (
    "ai_score",
    "ai_suggestion",
    "override_reason",
    "latitude",
    "longitude",
)
LINK_COLUMNS_ADDED = ("ai_validation_state", "ai_validation_reason")

# Finding 2. One scale, on both sides of the comparison.
SCORE_MIN = 0
SCORE_MAX = 100

# Finding 1. `skipped` is never persisted - a type that does not opt in leaves every
# column NULL, which is the same thing every pre-S2a row says.
STATE_SCORED = "scored"
STATE_UNVALIDATED = "unvalidated"
STATE_SKIPPED = "skipped"

REASON_TIMEOUT = "timeout"
REASON_ERROR = "error"
REASON_NO_GUIDANCE = "no_guidance"
REASON_NO_PROVIDER = "no_provider"
REASON_UNSUPPORTED_MEDIA = "unsupported_media"

# A one-pixel PNG is not needed; nothing here decodes the bytes. What matters is that
# the SAME bytes reach the model, so they carry a recognisable marker.
IMAGE_BYTES = b"\x89PNG\r\n\x1a\n" + b"ZZTPHOTO" * 4
IMAGE_MIME = "image/png"

LINE_GROUP = "items"

FORM_DOC = {
    "schemaVersion": 1,
    "pages": [
        {
            "id": "p1",
            "title": "Details",
            "sections": [
                {
                    "id": "s1",
                    "title": "Main",
                    "fields": [
                        {
                            "id": "f1",
                            "type": "text",
                            "key": "title",
                            "label": "Title",
                            "required": True,
                        },
                        {
                            "id": "f2",
                            "type": "repeater",
                            "key": LINE_GROUP,
                            "label": "Items",
                            "repeater": {
                                "fields": [
                                    {
                                        "id": "sf1",
                                        "type": "text",
                                        "key": "model",
                                        "label": "Model",
                                    }
                                ]
                            },
                        },
                    ],
                }
            ],
        }
    ],
}


# --------------------------------------------------------------------- helpers


def _optional_module(dotted: str):
    try:
        if importlib.util.find_spec(dotted) is None:
            return None
    except (ImportError, ModuleNotFoundError):
        return None
    return importlib.import_module(dotted)


def _validator():
    """Import the module S2a adds, or fail naming the contract it misses."""
    module = _optional_module(VALIDATOR_MODULE)
    if module is None:
        raise AssertionError(
            f"{VALIDATOR_MODULE} does not exist. AC-M21 puts the validator ONCE, in "
            "the resources module beside attachments, so complaints, service jobs, "
            "the forms platform and every future consumer inherit it instead of "
            "growing a second scorer each. A per-domain validator is how two photo "
            "types end up judged by two different prompts nobody can compare."
        )
    return module


def _attr(name: str, signature: str = ""):
    module = _validator()
    value = getattr(module, name, None)
    assert value is not None, f"{VALIDATOR_MODULE}.{name}{signature} must exist."
    return value


def _fn(name: str, signature: str):
    value = _attr(name, signature)
    assert callable(value), f"{VALIDATOR_MODULE}.{name}{signature} must be callable."
    return value


def _validate(db, **kwargs):
    fn = _fn(
        "validate_upload",
        "(db, *, attachment_type, data, filename=None, content_type=None, timeout=None)",
    )
    return fn(db, **kwargs)


def _columns(model):
    return {c.key: c for c in model.__table__.columns}


def _type_column(name: str):
    columns = _columns(AttachmentType)
    assert name in columns, (
        f"attachment_types.{name} is missing (AC-M20). attachment_types is ALREADY the "
        "per-type upload policy table - allowed_extensions, max_file_size_mb, "
        "max_count_per_entity, supports_field_linkage all live there - so validation "
        "policy joins them rather than founding a second policy table beside it."
    )
    return columns[name]


def _link_column(name: str):
    columns = _columns(EntityAttachmentLink)
    assert name in columns, (
        f"entity_attachment_links.{name} is missing. See the LINK_COLUMNS constants at "
        "the top of this file, and finding 1 in the module docstring for the two that "
        "AC-M22 does not name."
    )
    return columns[name]


def _seed_type(
    db,
    *,
    guidance: str | None = "Show the whole unit, in focus, with the defect visible.",
    min_score: int | None = 60,
    validate_on_upload: bool = True,
    code: str | None = None,
) -> AttachmentType:
    """An attachment type written directly, so the config under test is exact.

    Written with setattr for the new columns so that the FIRST failure of a test about
    behaviour is the behaviour, not the fixture.
    """
    row = AttachmentType(
        id=str(uuid.uuid4()),
        code=(code or unique_code("atype").lower())[:50],
        type_name=f"{TEST_PREFIX} {uuid.uuid4().hex[:8]}",
        allowed_extensions="jpg,jpeg,png,webp,pdf",
        max_file_size_mb=10,
    )
    db.add(row)
    db.flush()
    for field, value in (
        ("validation_guidance", guidance),
        ("min_score", min_score),
        ("validate_on_upload", validate_on_upload),
    ):
        _type_column(field)
        setattr(row, field, value)
    db.flush()
    return row


def _link(db, attachment_type: AttachmentType | None = None) -> EntityAttachmentLink:
    """One attachments row plus one link row, the shape every consumer produces."""
    attachment = Attachment(
        id=str(uuid.uuid4()),
        attachment_type_id=str(attachment_type.id) if attachment_type else None,
        original_filename=f"{unique_code('proof')}.png",
        stored_filename=f"{unique_code('proof')}.png",
        file_path=f"zzt/{uuid.uuid4().hex}.png",
        mime_type=IMAGE_MIME,
    )
    db.add(attachment)
    db.flush()
    row = EntityAttachmentLink(
        id=str(uuid.uuid4()),
        entity_type="zzt_case",
        entity_id=str(uuid.uuid4()),
        attachment_id=str(attachment.id),
    )
    db.add(row)
    db.flush()
    return row


# --------------------------------------------------------------------- fixtures


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


@pytest.fixture(autouse=True)
def _no_queue(monkeypatch):
    """Notification and SLA side effects enqueue RQ work. A live Redis is not a
    dependency of a test about a photo score."""
    import app.services.queue_service as queue_service

    monkeypatch.setattr(queue_service, "enqueue_job", lambda *a, **k: None)
    yield


@pytest.fixture(autouse=True)
def _no_ambient_api_key(monkeypatch):
    """The env key is ambient. Every provider question in this file is answered by the
    spy or by the deliberate absence of one, never by whatever .env happens to hold."""
    from app.config import settings

    monkeypatch.setattr(settings, "openai_api_key", "", raising=False)
    yield


class ModelSpy:
    """Stands in for the configured LLM provider. Records everything sent to it.

    A test that calls a real model is not deterministic and is not offline, and this
    one is also the only place the AC-M25 property is observable: "per-type behaviour
    is data" means the TYPE'S GUIDANCE is what differs between two calls, and nothing
    else does.
    """

    name = "zzt"

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.content: object = json.dumps({"score": 90, "suggestion": ""})
        self.raise_with: Exception | None = None
        self.delay: float = 0.0

    def chat(self, messages, **kwargs) -> ChatResult:
        self.calls.append({"messages": messages, **kwargs})
        if self.delay:
            time.sleep(self.delay)
        if self.raise_with is not None:
            raise self.raise_with
        body = self.content(len(self.calls)) if callable(self.content) else self.content
        return ChatResult(
            content=str(body), prompt_tokens=1, completion_tokens=1, total_tokens=2
        )

    def embed(self, text: str):  # pragma: no cover - protocol completeness
        return [0.0]

    def test_connection(self):  # pragma: no cover - protocol completeness
        return True, "ok", 0

    # -- what the model was shown ------------------------------------------------

    @staticmethod
    def _flatten(content) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return " ".join(
                ModelSpy._flatten(part.get("text", "") if isinstance(part, dict) else part)
                for part in content
            )
        if isinstance(content, dict):
            return ModelSpy._flatten(content.get("text", ""))
        return ""

    def text(self, index: int = -1) -> str:
        """Every string sent to the model on one call, concatenated."""
        call = self.calls[index]
        return " ".join(
            self._flatten(message.get("content"))
            for message in call["messages"]
            if isinstance(message, dict)
        )

    def images(self, index: int = -1) -> list:
        return list(self.calls[index].get("images") or [])


@pytest.fixture
def model(monkeypatch, db):
    """The spy, reachable however the validator resolves its provider.

    Patched on the defining module AND on the validator module, because this repo's
    call sites bind the name at import (ai_extract does exactly that) and patching only
    one of the two silently leaves the real provider in place.
    """
    from app.models.ai_assistant import AIAssistantConfig
    from app.services import llm_provider

    db.add(
        AIAssistantConfig(
            id=str(uuid.uuid4()),
            provider="openai",
            model="gpt-4o",
            api_key_ciphertext=f"{TEST_PREFIX}-key",
            system_prompt="",
        )
    )
    db.flush()

    spy = ModelSpy()
    monkeypatch.setattr(llm_provider, "get_provider", lambda *a, **k: spy)
    module = _optional_module(VALIDATOR_MODULE)
    if module is not None and hasattr(module, "get_provider"):
        monkeypatch.setattr(module, "get_provider", lambda *a, **k: spy)
    return spy


@pytest.fixture
def forbidden_model(monkeypatch):
    """A provider that fails the test if it is reached at all.

    Finding 9: a type that does not opt in must cost nothing. "No model call" is not
    observable by asserting on the result, only by making the call itself a failure.
    """

    def _boom(*_a, **_k):
        raise AssertionError(
            "The validator called the model for a type that did not ask to be "
            "validated. AC-M23 gates the whole thing on validate_on_upload, and this "
            "slice touches a table every module already uploads through."
        )

    from app.services import llm_provider

    monkeypatch.setattr(llm_provider, "get_provider", _boom)
    module = _optional_module(VALIDATOR_MODULE)
    if module is not None and hasattr(module, "get_provider"):
        monkeypatch.setattr(module, "get_provider", _boom)
    return _boom


class FakeBackend:
    """An in-memory bucket. A test that writes to a live bucket is a defect."""

    def __init__(self):
        self.objects: dict[str, bytes] = {}

    def upload_file(self, contents, key, content_type=None, **kwargs):
        self.objects[str(key).lstrip("/")] = contents
        return True

    def file_exists(self, key):
        return str(key).lstrip("/") in self.objects

    def download_file(self, key):
        return self.objects[str(key).lstrip("/")]

    def delete_file(self, key):
        return self.objects.pop(str(key).lstrip("/"), None) is not None

    def get_signed_url(self, key, expires_in=3600):
        return f"https://zzt.invalid/{str(key).lstrip('/')}"

    def get_cdn_base_url(self, key):
        return f"https://zzt.invalid/{str(key).lstrip('/')}"


@pytest.fixture(autouse=True)
def storage(monkeypatch):
    from app.services import image_thumbnailer, storage_router

    backend = FakeBackend()
    monkeypatch.setattr(storage_router, "get_backend", lambda provider=None: backend)
    monkeypatch.setattr(storage_router, "default_provider", lambda: "s3")
    monkeypatch.setattr(
        storage_router, "resolve_signed_url", lambda path, provider=None: str(path)
    )
    monkeypatch.setattr(image_thumbnailer, "store_thumbnail", lambda *a, **k: None)
    return backend


@pytest.fixture(autouse=True)
def _isolate_registry():
    saved = dict(status_registry._REGISTRY)
    yield
    status_registry._REGISTRY.clear()
    status_registry._REGISTRY.update(saved)


@pytest.fixture(autouse=True)
def _isolate_prompt_cache():
    """The prompt registry cache is process-global and TTL'd."""
    from app.services import ai_prompt_registry

    ai_prompt_registry.bust_cache()
    yield
    ai_prompt_registry.bust_cache()


# ============================================================================
# A. Schema - AC-M20, AC-M22
# ============================================================================


@pytest.mark.parametrize("name", TYPE_COLUMNS)
def test_the_per_type_upload_policy_table_carries_the_validation_policy_ac_m20(name):
    """AC-M20. Three columns, no new table.

    A separate `attachment_validation_configs` table keyed on attachment_type_id would
    be a second row that can go missing, and an admin editing "how many, how big, which
    extensions" in one dialog and "how it is judged" in another is how the two drift.
    """
    _type_column(name)


def test_validate_on_upload_is_a_not_null_boolean_defaulting_to_off_ac_m20():
    """Every existing type must keep behaving exactly as it does today.

    NULL as a third state on a switch means "we never decided", and every read site
    then needs its own opinion about what NULL means. There are three today and the
    consuming slices add more.
    """
    column = _type_column("validate_on_upload")
    assert isinstance(column.type, Boolean), (
        "validate_on_upload is a switch, not a mode. A String would invite "
        "'true'/'yes'/'on' from three different callers."
    )
    assert column.nullable is False, (
        "NULL would be a third state on a two-state switch. Every read site would then "
        "need its own opinion about what a NULL means, and they would not agree."
    )
    assert column.server_default is not None, (
        "attachment_types has live rows. Without a server_default the ALTER either "
        "fails or leaves them NULL, and 'do not validate' has to be the answer for "
        "every type that predates this slice."
    )


def test_validation_guidance_is_unbounded_text_not_a_varchar_ac_m20():
    """AC-M26 is three sentences about model, quantity and defect visibility in ONE
    guidance string. A VARCHAR(255) makes the admin edit the requirement to fit the
    column, which is the requirement losing an argument with the schema.
    """
    column = _type_column("validation_guidance")
    assert isinstance(column.type, Text), (
        "validation_guidance is prose an admin writes. AC-M26 alone is three checks in "
        "one string, and R5 is explicitly 'three guidance strings, not three features'."
    )
    assert column.nullable is True, (
        "Every type that predates this slice has no guidance, and a NOT NULL '' would "
        "make 'not configured' and 'configured as empty' indistinguishable - which is "
        "the exact distinction finding 4 turns on."
    )


@pytest.mark.parametrize("name", LINK_COLUMNS_FROM_AC + LINK_COLUMNS_ADDED)
def test_the_link_row_carries_the_verdict_ac_m22(name):
    """AC-M22, plus the two columns it does not name (finding 1).

    The LINK and not the ATTACHMENT: the same file scored against consumer-intake
    guidance and against rma_readiness guidance gets two different scores, and a column
    on `attachments` can only hold one of them.
    """
    _link_column(name)


def test_the_score_and_the_threshold_share_one_integer_scale_no_ac_states_it():
    """Finding 2. Nothing in Group M says whether a score is 0-1 or 0-100.

    `min_score` is admin data entry sitting beside `max_file_size_mb` in the same
    dialog. An admin who types 70 meaning 70% into a 0-1 column has set a threshold
    nothing can ever clear, and the type then refuses every photo forever with no
    message that says why.
    """
    score = _link_column("ai_score")
    threshold = _type_column("min_score")
    for name, column in (("ai_score", score), ("min_score", threshold)):
        assert isinstance(column.type, Integer), (
            f"{name} is an integer 0-100. A Numeric invites 0.85 from one writer and "
            "85 from another into the same comparison."
        )
        assert column.nullable is True, (
            f"{name} must be NULL-able: NULL on ai_score is 'no claim made', NULL on "
            "min_score is 'advisory only'. Neither is expressible with a default of 0."
        )
    assert (_attr("SCORE_MIN"), _attr("SCORE_MAX")) == (SCORE_MIN, SCORE_MAX), (
        "The scale is declared as constants, not spelled 0 and 100 at each of the "
        "comparison, the parser, the write guard and the admin schema."
    )


def test_the_state_is_an_explicit_column_not_a_null_score_finding_1():
    """Finding 1. The single most important column in this slice.

    `ai_score IS NULL` has to mean three different things at once otherwise: the type
    does not validate, the model timed out, and the model was never asked. S2 refused
    the same shortcut for the same reason - `resolve` returns an explicit `unknown`
    verdict rather than an empty list, because an empty list reads as "no cover" to
    every caller (AC-D17). A NULL score read as failure refuses a good photo.
    """
    state = _link_column("ai_validation_state")
    reason = _link_column("ai_validation_reason")
    assert isinstance(state.type, String) and not isinstance(state.type, Text), (
        "A short bounded vocabulary, not free text: this column is branched on."
    )
    assert state.nullable is True, (
        "NULL is the answer for every row that predates the slice AND for every type "
        "that never opted in. Both are honestly 'no claim was made'."
    )
    assert reason.nullable is True, (
        "A scored row has no reason. Only an unvalidated one does."
    )
    assert {_attr("STATE_SCORED"), _attr("STATE_UNVALIDATED"), _attr("STATE_SKIPPED")} == {
        STATE_SCORED,
        STATE_UNVALIDATED,
        STATE_SKIPPED,
    }


def test_the_capture_pin_matches_the_site_pin_in_type_and_precision_ac_m22_ac_b21():
    """Finding 7. Two latitude/longitude pairs now exist and they answer different
    questions - where the Site is (S1, on `complaints`) versus where THIS photo was
    taken (AC-M22, on the link row). They will be read side by side on one screen, so
    a reader comparing them must be comparing like with like.
    """
    site = Complaint.__table__.c.latitude
    for name in ("latitude", "longitude"):
        column = _link_column(name)
        assert isinstance(column.type, Numeric) and not isinstance(
            column.type, Integer
        ), f"{name} is a coordinate, not a count."
        assert (column.type.precision, column.type.scale) == (
            site.type.precision,
            site.type.scale,
        ), (
            f"entity_attachment_links.{name} must match complaints.{name} "
            f"({site.type.precision},{site.type.scale}) from AC-B21. A capture pin "
            "rounded to fewer decimals than the Site pin makes 'the photo was taken at "
            "the site' unanswerable at the precision the question is asked."
        )
        assert column.nullable is True, "AC-M27: coordinates are omitted, never zeroed."


# ============================================================================
# B. The prompt is registry data - AC-M25
# ============================================================================


def test_the_validator_prompt_is_a_registry_key_ac_m25():
    """AC-M25. Registered in PROMPT_KEYS, so it is versioned, labelled, editable in the
    FE prompt editor and covered by the hardcoded fallback when the DB is unreachable.

    A prompt string inside the service is none of those things: retuning it is a
    deploy, and a DB outage that takes the prompt out takes every upload with it.
    """
    from app.services.ai_prompt_registry import PROMPT_KEYS

    assert PROMPT_KEY in PROMPT_KEYS, (
        f"PROMPT_KEYS['{PROMPT_KEY}'] is missing. AC-M25 puts the prompt in the "
        "registry, and the registry is what makes 'a new photo type is admin data "
        "entry, not a deployment' true for the prompt as well as for the guidance."
    )
    spec = PROMPT_KEYS[PROMPT_KEY]
    assert spec.active is True, (
        "Dormant keys are seeded but have no call site. This one has a call site on "
        "day one."
    )
    assert list(spec.variables) == [PROMPT_VARIABLE], (
        "The type's guidance reaches the model as a DECLARED variable, not by string "
        "concatenation. Declared is what makes validate_template refuse a saved "
        "version that forgot the token, which would otherwise ship a prompt that "
        "judges every photo against nothing."
    )
    assert spec.fallback().strip(), (
        "The fallback is the single source for the prompt text and is what answers "
        "when the DB is unreachable (UAC B2). An empty one turns a database blip into "
        "every photo being judged by an empty instruction."
    )


def test_the_fallback_prompt_declares_the_token_it_promises_ac_m25():
    """A key whose fallback body omits its own declared variable renders a prompt with
    the guidance silently dropped - the model then judges the photo against nothing and
    returns a confident number anyway."""
    from app.services.ai_prompt_registry import PROMPT_KEYS, extract_tokens

    spec = PROMPT_KEYS[PROMPT_KEY]
    assert PROMPT_VARIABLE in extract_tokens(spec.fallback()), (
        f"The {PROMPT_KEY} fallback must contain {{{{{PROMPT_VARIABLE}}}}}. Declaring "
        "the variable without a slot for it is the failure mode where per-type "
        "behaviour stops being data and nothing reports it."
    )


def test_the_guidance_reaches_the_model_substituted_not_literal_ac_m25(db, model):
    """The end of the chain AC-M25 describes: the admin's string is what the model is
    told, and the token is gone by the time the request leaves."""
    guidance = f"{TEST_PREFIX} the flush valve must be visible and in focus"
    attachment_type = _seed_type(db, guidance=guidance)

    _validate(db, attachment_type=attachment_type, data=IMAGE_BYTES, content_type=IMAGE_MIME)

    assert model.calls, "The model was never called for a type that opted in."
    sent = model.text()
    assert guidance in sent, (
        "The type's validation_guidance is what the model scores against (AC-M25). If "
        "it is not in the payload, per-type behaviour is not data."
    )
    assert f"{{{{{PROMPT_VARIABLE}}}}}" not in sent, (
        "The literal token reached the model, so render() was not used. The guidance "
        "was never substituted and the model is scoring against a placeholder."
    )


def test_two_types_differ_only_by_their_guidance_ac_m25(db, model):
    """AC-M25's real property, stated as behaviour rather than as source shape.

    Two types created at RUNTIME with codes no source file could know. If anything
    other than the guidance differs between the two payloads, something is branching on
    a type rather than reading its data.
    """
    first = _seed_type(db, guidance=f"{TEST_PREFIX} guidance ALPHA the model badge")
    second = _seed_type(db, guidance=f"{TEST_PREFIX} guidance BRAVO the quantity")

    _validate(db, attachment_type=first, data=IMAGE_BYTES, content_type=IMAGE_MIME)
    _validate(db, attachment_type=second, data=IMAGE_BYTES, content_type=IMAGE_MIME)

    alpha, bravo = model.text(0), model.text(1)
    assert "ALPHA" in alpha and "BRAVO" not in alpha
    assert "BRAVO" in bravo and "ALPHA" not in bravo
    assert alpha.replace("ALPHA the model badge", "") == bravo.replace(
        "BRAVO the quantity", ""
    ), (
        "Two types produced two prompts that differ by more than their guidance. "
        "AC-M25 says per-type behaviour is DATA: everything except the guidance string "
        "must be identical, or a new photo type is a deployment after all."
    )


def test_a_type_the_source_has_never_heard_of_is_validated_ac_m25(db, model):
    """"A new photo type is admin data entry, not a deployment."

    The code is generated here. No branch, table or constant in the repo can match it,
    so a validator that only works for the codes it knows fails this outright.
    """
    attachment_type = _seed_type(db, code=unique_code("brandnew").lower())
    outcome = _validate(
        db, attachment_type=attachment_type, data=IMAGE_BYTES, content_type=IMAGE_MIME
    )
    assert outcome.state == STATE_SCORED
    assert model.calls, "An unknown type was silently skipped rather than scored."


# ============================================================================
# C. Scoring on upload - AC-M23
# ============================================================================


def test_validation_runs_synchronously_and_returns_a_score_ac_m23(db, model):
    """AC-M23. Synchronous is the point: the score has to be on screen while the phone
    is still in the uploader's hand, or Retake is not an affordance, it is a chore."""
    model.content = json.dumps({"score": 82, "suggestion": "Move a step closer."})
    attachment_type = _seed_type(db, min_score=60)

    outcome = _validate(
        db, attachment_type=attachment_type, data=IMAGE_BYTES, content_type=IMAGE_MIME
    )

    assert outcome.state == STATE_SCORED
    assert outcome.score == 82
    assert outcome.suggestion == "Move a step closer."
    assert outcome.passed is True
    assert outcome.reason is None


def test_the_validator_is_given_the_bytes_not_a_url_finding_8(db, model):
    """Finding 8. Uploads route through storage_router across `s3` and `r2`, and R2 keys
    are not always public - a validator built on a presigned URL behaves differently per
    provider and breaks for whichever one a tenant is mid-migration on. ai_extract
    already sets the precedent, and on upload the bytes are in hand anyway.
    """
    attachment_type = _seed_type(db)
    _validate(db, attachment_type=attachment_type, data=IMAGE_BYTES, content_type=IMAGE_MIME)

    images = model.images()
    assert images, (
        "No image reached the model. A scorer that was handed only a filename or a URL "
        "is scoring metadata, and it will answer confidently either way."
    )
    encoded = base64.b64encode(IMAGE_BYTES).decode("ascii")
    assert any(getattr(part, "data_b64", None) == encoded for part in images), (
        "The bytes sent to the model are not the bytes that were uploaded."
    )

    signature = inspect.signature(_fn("validate_upload", "(...)"))
    assert "data" in signature.parameters, (
        "validate_upload takes the bytes. A signature taking attachment_id or file_url "
        "makes the validator re-download what the caller already has, and makes it "
        "provider-dependent."
    )


def test_a_score_below_the_threshold_is_reported_with_its_suggestion_ac_m24(db, model):
    """AC-M24's data half. The suggestion is the whole reason a low score is useful:
    "too dark" is actionable, "42" is a rebuke."""
    model.content = json.dumps(
        {"score": 20, "suggestion": "The label is cut off - include the whole badge."}
    )
    attachment_type = _seed_type(db, min_score=60)

    outcome = _validate(
        db, attachment_type=attachment_type, data=IMAGE_BYTES, content_type=IMAGE_MIME
    )

    assert outcome.state == STATE_SCORED
    assert outcome.passed is False
    assert outcome.suggestion == "The label is cut off - include the whole badge."


def test_a_type_that_did_not_opt_in_is_skipped_with_no_model_call_ac_m23(
    db, forbidden_model
):
    """Finding 9. This slice touches a table every module already uploads through.

    `validate_on_upload = false` must cost nothing: no latency, no new failure mode, no
    provider dependency. `forbidden_model` fails the test if the model is reached.
    """
    attachment_type = _seed_type(db, validate_on_upload=False, guidance="ignored")

    outcome = _validate(
        db, attachment_type=attachment_type, data=IMAGE_BYTES, content_type=IMAGE_MIME
    )

    assert outcome.state == STATE_SKIPPED
    assert outcome.score is None
    assert outcome.passed is None, (
        "`skipped` is not a pass and not a failure. A caller that renders "
        "`passed is False` as 'Retake' would put a Retake button on every upload of "
        "every type that never asked to be validated."
    )


def test_an_attachment_with_no_type_at_all_is_skipped(db, forbidden_model):
    """`attachments.attachment_type_id` is nullable and set to NULL on delete. A
    validator that assumes a type raises AttributeError inside an upload."""
    outcome = _validate(
        db, attachment_type=None, data=IMAGE_BYTES, content_type=IMAGE_MIME
    )
    assert outcome.state == STATE_SKIPPED


# ============================================================================
# D. Degradation - finding 1, the whole risk of the slice
# ============================================================================


def test_a_timeout_degrades_to_unvalidated_never_to_a_bad_score(db, model):
    """The single most important test in this file.

    "A validator that can block a technician closing a job at 6pm in a basement is
    worse than no validator." The failure mode being pinned is subtler than blocking:
    a timeout that lands as score 0, or as a NULL the UI reads as failure, REFUSES a
    good photo because the network was slow. The photo is fine. The connection was not.
    """
    model.delay = 1.0
    attachment_type = _seed_type(db, min_score=60)

    started = time.monotonic()
    outcome = _validate(
        db,
        attachment_type=attachment_type,
        data=IMAGE_BYTES,
        content_type=IMAGE_MIME,
        timeout=0.15,
    )
    elapsed = time.monotonic() - started

    assert outcome.state == STATE_UNVALIDATED
    assert outcome.reason == REASON_TIMEOUT
    assert outcome.score is None, (
        "A timeout produced a score. There is no score - nothing was judged."
    )
    assert outcome.passed is not False, (
        "A timeout was reported as a FAILED validation. The upload path cannot tell "
        "this apart from a genuinely bad photo, so it shows Retake for a photo that "
        "was never looked at."
    )
    assert elapsed < 0.9, (
        f"The call took {elapsed:.2f}s against a 0.15s timeout, so the timeout is not "
        "enforced here - it is being delegated to the provider SDK, which is exactly "
        "what fails on a stalled mobile connection where no response ever arrives."
    )


def test_the_timeout_is_a_declared_constant_within_a_human_wait(db):
    """A number nobody declared is a number nobody can tune when the field reports that
    uploads hang. The bound is what a person will hold a phone still for."""
    timeout = _attr("VALIDATION_TIMEOUT_SECONDS")
    assert isinstance(timeout, (int, float)) and 0 < timeout <= 20, (
        f"VALIDATION_TIMEOUT_SECONDS is {timeout!r}. Synchronous means somebody is "
        "waiting: over ~20s they have already decided the app is broken, and 0 or "
        "None means no ceiling at all."
    )


def test_the_module_constant_is_the_default_not_a_hardcoded_call_site(db, model):
    """The constant has to be READ at call time. A default argument bound at import, or
    a literal at the call site, means the declared constant is decoration and tuning it
    changes nothing.
    """
    module = _validator()
    model.delay = 1.0
    attachment_type = _seed_type(db)

    original = module.VALIDATION_TIMEOUT_SECONDS
    try:
        module.VALIDATION_TIMEOUT_SECONDS = 0.15
        outcome = _validate(
            db, attachment_type=attachment_type, data=IMAGE_BYTES, content_type=IMAGE_MIME
        )
    finally:
        module.VALIDATION_TIMEOUT_SECONDS = original

    assert outcome.state == STATE_UNVALIDATED and outcome.reason == REASON_TIMEOUT


def test_a_provider_error_degrades_to_unvalidated_not_to_zero(db, model):
    """A 429, a revoked key, a model deprecation. None of them is evidence about the
    photograph, and all of them are things that happen on a Tuesday afternoon."""
    model.raise_with = RuntimeError("429 rate limited")
    attachment_type = _seed_type(db, min_score=60)

    outcome = _validate(
        db, attachment_type=attachment_type, data=IMAGE_BYTES, content_type=IMAGE_MIME
    )

    assert outcome.state == STATE_UNVALIDATED
    assert outcome.reason == REASON_ERROR
    assert outcome.score is None
    assert outcome.passed is not False


def test_no_configured_provider_degrades_instead_of_raising(db, monkeypatch):
    """`ai_extract` raises AppException 400 when no API key is configured. Copied into
    an upload path, that turns every photo upload on a fresh install, a local dev
    machine, or a tenant that never bought an AI subscription into a 400 - for a
    feature that is meant to be advisory.
    """
    attachment_type = _seed_type(db)

    outcome = _validate(
        db, attachment_type=attachment_type, data=IMAGE_BYTES, content_type=IMAGE_MIME
    )

    assert outcome.state == STATE_UNVALIDATED
    assert outcome.reason == REASON_NO_PROVIDER


def test_validate_on_upload_with_blank_guidance_never_calls_the_model_finding_4(
    db, forbidden_model
):
    """Finding 4, runtime half. The type says validate; the data says there is nothing
    to validate against. Scoring against an empty guidance is scoring against nothing,
    and whatever comes back will look authoritative because it is a number.

    The write guard below is not enough on its own: a migration, a raw INSERT and
    another worktree are all paths into this table.
    """
    for guidance in (None, "", "   "):
        attachment_type = _seed_type(db, guidance=guidance, validate_on_upload=True)
        outcome = _validate(
            db, attachment_type=attachment_type, data=IMAGE_BYTES, content_type=IMAGE_MIME
        )
        assert outcome.state == STATE_UNVALIDATED, (
            f"guidance={guidance!r} produced state {outcome.state!r}. Not `skipped`: "
            "the type DID ask to be validated and was not, and that misconfiguration "
            "has to be visible rather than looking like a type that opted out."
        )
        assert outcome.reason == REASON_NO_GUIDANCE


def test_a_non_json_reply_degrades_rather_than_scoring_zero(db, model):
    """Models return prose when they feel like it. `int(...)` on a refusal raises, and
    a bare `except: score = 0` refuses a good photo for a parsing accident."""
    model.content = "I'm sorry, I can't help with images of people."
    attachment_type = _seed_type(db, min_score=60)

    outcome = _validate(
        db, attachment_type=attachment_type, data=IMAGE_BYTES, content_type=IMAGE_MIME
    )

    assert outcome.state == STATE_UNVALIDATED
    assert outcome.reason == REASON_ERROR
    assert outcome.score is None


@pytest.mark.parametrize("returned", [0.82, 0.5, 0.999])
def test_a_zero_to_one_score_is_a_scale_mismatch_not_a_rounding_problem(
    db, model, returned
):
    """Finding 2, the model's half of it.

    0.82 means "very good" on the scale half the world uses. Rounded onto 0-100 it
    becomes 1 and the photo is refused. Rounding here is silent and always wrong in the
    direction that rejects, so the value is refused as unparseable instead.
    """
    model.content = json.dumps({"score": returned, "suggestion": ""})
    attachment_type = _seed_type(db, min_score=60)

    outcome = _validate(
        db, attachment_type=attachment_type, data=IMAGE_BYTES, content_type=IMAGE_MIME
    )

    assert outcome.state == STATE_UNVALIDATED, (
        f"score={returned} was accepted. On a 0-100 scale it is either a scale "
        "mismatch or noise, and both round to a refusal of a photo nobody judged badly."
    )
    assert outcome.reason == REASON_ERROR


@pytest.mark.parametrize("returned", [-5, 101, 1000])
def test_an_out_of_range_score_is_refused_not_clamped(db, model, returned):
    """Clamping 1000 to 100 passes a photo on a reply nobody can explain, and clamping
    -5 to 0 fails one. Neither number came from the scale we asked for."""
    model.content = json.dumps({"score": returned, "suggestion": ""})
    attachment_type = _seed_type(db, min_score=60)

    outcome = _validate(
        db, attachment_type=attachment_type, data=IMAGE_BYTES, content_type=IMAGE_MIME
    )

    assert outcome.state == STATE_UNVALIDATED
    assert outcome.reason == REASON_ERROR


@pytest.mark.parametrize("returned", [0, 1, 100])
def test_the_ends_of_the_scale_are_legitimate_scores(db, model, returned):
    """The corollary of the two tests above, and the reason they are written as narrow
    rules. 0 is a real score for a photograph of a thumb."""
    model.content = json.dumps({"score": returned, "suggestion": "s"})
    attachment_type = _seed_type(db, min_score=60)

    outcome = _validate(
        db, attachment_type=attachment_type, data=IMAGE_BYTES, content_type=IMAGE_MIME
    )

    assert outcome.state == STATE_SCORED and outcome.score == returned


def test_an_unsupported_media_type_degrades_rather_than_refusing_the_upload(db, model):
    """A .docx or a .heic the provider will not accept. The type's own
    allowed_extensions already decided whether the file may be uploaded at all
    (check_quota); the validator's opinion about whether it can LOOK at it must not
    re-litigate that and take the file down with it.
    """
    attachment_type = _seed_type(db)

    outcome = _validate(
        db,
        attachment_type=attachment_type,
        data=b"PK\x03\x04zzt",
        filename="report.docx",
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )

    assert outcome.state == STATE_UNVALIDATED
    assert outcome.reason == REASON_UNSUPPORTED_MEDIA


def test_the_validator_never_raises_whatever_the_model_does(db, model):
    """The contract every caller depends on. An upload path that has to wrap the
    validator in its own try/except has three copies of that try/except within a
    release, and the third one forgets to roll back the session.
    """
    attachment_type = _seed_type(db)
    for boom in (
        RuntimeError("boom"),
        TimeoutError("stalled"),
        ValueError("bad request"),
        KeyError("model"),
    ):
        model.raise_with = boom
        outcome = _validate(
            db, attachment_type=attachment_type, data=IMAGE_BYTES, content_type=IMAGE_MIME
        )
        assert outcome.state == STATE_UNVALIDATED, f"{boom!r} escaped the validator."


# ============================================================================
# E. Thresholds - finding 3
# ============================================================================


def test_min_score_zero_passes_everything_it_does_not_fail_everything(db, model):
    """Finding 3, and the F2c lesson repeated on the same table.

    `max_count_per_entity = 0` on this very table silently means "never attachable"
    rather than "unlimited". "No photo ever passes" is an equally plausible reading of
    `min_score = 0`, and an admin who types 0 meaning "off" would then break every
    upload of that type with no message that says why.
    """
    model.content = json.dumps({"score": 0, "suggestion": "Blurred."})
    attachment_type = _seed_type(db, min_score=0)

    outcome = _validate(
        db, attachment_type=attachment_type, data=IMAGE_BYTES, content_type=IMAGE_MIME
    )

    assert outcome.score == 0
    assert outcome.passed is True, (
        "min_score=0 means `score >= 0`, which every score satisfies. Reading 0 as "
        "'nothing passes' turns a plausible admin typo into a type nobody can upload "
        "to."
    )


def test_min_score_null_scores_and_advises_but_never_fails(db, model):
    """The advisory mode, and the one an admin reaches for first: show me the suggestion,
    do not gate anything on it yet. Without it, opting a type in at all forces a
    threshold to be invented on the spot."""
    model.content = json.dumps({"score": 3, "suggestion": "Too dark."})
    attachment_type = _seed_type(db, min_score=None)

    outcome = _validate(
        db, attachment_type=attachment_type, data=IMAGE_BYTES, content_type=IMAGE_MIME
    )

    assert outcome.state == STATE_SCORED
    assert outcome.score == 3
    assert outcome.suggestion == "Too dark."
    assert outcome.passed is True, (
        "No threshold means nothing to fail. NULL must not be coerced to 0 or to any "
        "other number - both invent a gate the admin did not set."
    )


@pytest.mark.parametrize("score,threshold,expected", [(60, 60, True), (59, 60, False)])
def test_the_threshold_is_inclusive(db, model, score, threshold, expected):
    """`>=`, not `>`. An admin who sets 60 means "sixty is good enough", and the one-off
    reading refuses exactly the photo that met the bar."""
    model.content = json.dumps({"score": score, "suggestion": ""})
    attachment_type = _seed_type(db, min_score=threshold)
    outcome = _validate(
        db, attachment_type=attachment_type, data=IMAGE_BYTES, content_type=IMAGE_MIME
    )
    assert outcome.passed is expected


@pytest.mark.parametrize("bad", [-1, 101, 150])
def test_a_min_score_outside_the_scale_is_refused_at_the_write(db, bad):
    """Finding 3's other half. 150 is a plausible slip on a 0-100 field and it bricks
    the type permanently: every photo fails, the uploader is told to retake, the retake
    fails too. Refused where it is typed, not discovered in the field.
    """
    from app.schemas.resources import AttachmentTypeCreate
    from app.services.resources_service import AttachmentTypeService

    assert "min_score" in AttachmentTypeCreate.model_fields, (
        "AttachmentTypeCreate has no min_score field, so the value below is dropped "
        "before the service ever sees it. AC-M20's column needs a schema field on the "
        "create as well as the model."
    )
    payload = AttachmentTypeCreate(
        type_name=f"{TEST_PREFIX} {uuid.uuid4().hex[:8]}",
        allowed_extensions="jpg,png",
        min_score=bad,
    )
    with pytest.raises(AppException) as caught:
        AttachmentTypeService(db).create_type(payload)
    assert caught.value.status_code in (400, 422)


def test_opting_in_with_no_guidance_is_refused_at_the_write_finding_4(db):
    """Finding 4, write half. The guard is in the SERVICE, not on the route: the admin
    dialog, a seed, a bulk edit and a future import all land here, and a guard on the
    action route is not a guard (ADR-0013 rule 7).
    """
    from app.schemas.resources import AttachmentTypeCreate
    from app.services.resources_service import AttachmentTypeService

    missing = [
        f
        for f in ("validate_on_upload", "validation_guidance")
        if f not in AttachmentTypeCreate.model_fields
    ]
    assert not missing, (
        f"AttachmentTypeCreate has no {missing}, so the values below are dropped before "
        "the service ever sees them and the guard cannot be reached."
    )
    payload = AttachmentTypeCreate(
        type_name=f"{TEST_PREFIX} {uuid.uuid4().hex[:8]}",
        allowed_extensions="jpg,png",
        validate_on_upload=True,
        validation_guidance="   ",
    )
    with pytest.raises(AppException) as caught:
        AttachmentTypeService(db).create_type(payload)
    assert caught.value.status_code in (400, 422)


def test_the_admin_surface_carries_all_three_new_fields_ac_m20(db):
    """"validation_guidance / min_score / validate_on_upload join the existing
    attachment type dialog, the same way max_count_per_entity did."

    This repo has been bitten twice by a manual builder that silently drops a new
    column - `get_user`/`get_me` and the `system_settings` GET - and the symptom is
    always the same: the toggle renders its default and never the saved value.
    `is_direct_access` is on this very model today and reaches no schema at all.
    """
    from app.schemas.resources import (
        AttachmentTypeCreate,
        AttachmentTypeResponse,
        AttachmentTypeUpdate,
    )

    for schema in (AttachmentTypeCreate, AttachmentTypeUpdate, AttachmentTypeResponse):
        missing = [f for f in TYPE_COLUMNS if f not in schema.model_fields]
        assert not missing, (
            f"{schema.__name__} is missing {missing}. Inheriting the column is not "
            "enough - the field has to be on the create, the update AND the read, or "
            "the admin saves a value they can never see again."
        )


# ============================================================================
# F. Use anyway requires a reason, enforced - AC-M24
# ============================================================================


def test_use_anyway_without_a_reason_is_refused_by_the_service_ac_m24(db, model):
    """AC-M24 is written as a UI sentence and a guard on the action routes is not a
    guard (ADR-0013 rule 7). The portal, the CRM panel and the technician app are three
    callers; the reason is required in one place, where all three pass through.
    """
    model.content = json.dumps({"score": 10, "suggestion": "Retake in daylight."})
    attachment_type = _seed_type(db, min_score=60)
    link = _link(db, attachment_type)
    outcome = _validate(
        db, attachment_type=attachment_type, data=IMAGE_BYTES, content_type=IMAGE_MIME
    )
    _fn("apply_outcome", "(link, outcome)")(link, outcome)
    db.flush()

    override = _fn("record_override", "(db, *, link_id, reason, user_id=None)")
    for empty in (None, "", "   ", "\n\t "):
        with pytest.raises(AppException) as caught:
            override(db, link_id=str(link.id), reason=empty)
        assert caught.value.status_code in (400, 422)


def test_a_too_short_reason_is_refused_against_a_declared_minimum_ac_m24(db, model):
    """"." gets past a non-empty check and defeats the whole point. The threshold is a
    declared constant rather than a literal, because it is the sort of number somebody
    will want to change once real overrides start arriving.
    """
    minimum = _attr("OVERRIDE_REASON_MIN_LENGTH")
    assert isinstance(minimum, int) and minimum >= 3, (
        f"OVERRIDE_REASON_MIN_LENGTH is {minimum!r}. Below 3 characters, '.' and 'ok' "
        "both pass and the override reason stops being a metric."
    )

    model.content = json.dumps({"score": 10, "suggestion": "s"})
    attachment_type = _seed_type(db, min_score=60)
    link = _link(db, attachment_type)
    outcome = _validate(
        db, attachment_type=attachment_type, data=IMAGE_BYTES, content_type=IMAGE_MIME
    )
    _fn("apply_outcome", "(link, outcome)")(link, outcome)
    db.flush()

    with pytest.raises(AppException):
        _fn("record_override", "(db, *, link_id, reason, user_id=None)")(
            db, link_id=str(link.id), reason="." * (minimum - 1)
        )


def test_a_real_reason_is_accepted_and_persists_ac_m24(db, model):
    """"The override reason is itself the metric that says the guidance is wrong rather
    than the uploader." A reason that is validated and then discarded produces the
    friction with none of the signal."""
    model.content = json.dumps({"score": 10, "suggestion": "Include the whole unit."})
    attachment_type = _seed_type(db, min_score=60)
    link = _link(db, attachment_type)
    outcome = _validate(
        db, attachment_type=attachment_type, data=IMAGE_BYTES, content_type=IMAGE_MIME
    )
    _fn("apply_outcome", "(link, outcome)")(link, outcome)
    db.flush()

    reason = f"{TEST_PREFIX} the unit is built into a cabinet, this is the only angle"
    _fn("record_override", "(db, *, link_id, reason, user_id=None)")(
        db, link_id=str(link.id), reason=reason
    )
    db.flush()
    db.refresh(link)

    assert link.override_reason == reason
    assert link.ai_score == 10, (
        "The score survives the override. Clearing it makes the override invisible to "
        "the very report AC-M24 exists to feed - you can no longer tell WHICH scores "
        "people are overriding."
    )
    assert link.ai_suggestion == "Include the whole unit."


def test_an_override_on_a_passing_upload_is_refused_ac_m24(db, model):
    """There is nothing to override. Accepting one puts reasons in the column for
    uploads that never failed, and the "is the guidance wrong" metric then measures
    whatever the FE happened to send.
    """
    model.content = json.dumps({"score": 95, "suggestion": ""})
    attachment_type = _seed_type(db, min_score=60)
    link = _link(db, attachment_type)
    outcome = _validate(
        db, attachment_type=attachment_type, data=IMAGE_BYTES, content_type=IMAGE_MIME
    )
    _fn("apply_outcome", "(link, outcome)")(link, outcome)
    db.flush()

    with pytest.raises(AppException):
        _fn("record_override", "(db, *, link_id, reason, user_id=None)")(
            db, link_id=str(link.id), reason=f"{TEST_PREFIX} looks fine to me"
        )


def test_an_override_on_an_unvalidated_upload_is_refused(db, model):
    """Finding 1 again, at the other end of the slice. A timed-out upload was never
    refused, so nothing was overridden - and counting it as an override would report a
    network problem as a disagreement with the guidance.
    """
    model.raise_with = RuntimeError("429")
    attachment_type = _seed_type(db, min_score=60)
    link = _link(db, attachment_type)
    outcome = _validate(
        db, attachment_type=attachment_type, data=IMAGE_BYTES, content_type=IMAGE_MIME
    )
    _fn("apply_outcome", "(link, outcome)")(link, outcome)
    db.flush()

    with pytest.raises(AppException):
        _fn("record_override", "(db, *, link_id, reason, user_id=None)")(
            db, link_id=str(link.id), reason=f"{TEST_PREFIX} using it anyway"
        )


def test_apply_outcome_writes_the_state_and_not_only_the_score(db, model):
    """The persistence contract. One function does the write so the three consuming
    slices cannot each invent their own mapping from outcome to columns."""
    apply_outcome = _fn("apply_outcome", "(link, outcome)")
    attachment_type = _seed_type(db, min_score=60)

    model.content = json.dumps({"score": 71, "suggestion": "ok"})
    scored_link = _link(db, attachment_type)
    apply_outcome(
        scored_link,
        _validate(db, attachment_type=attachment_type, data=IMAGE_BYTES, content_type=IMAGE_MIME),
    )

    model.raise_with = RuntimeError("boom")
    failed_link = _link(db, attachment_type)
    apply_outcome(
        failed_link,
        _validate(db, attachment_type=attachment_type, data=IMAGE_BYTES, content_type=IMAGE_MIME),
    )
    db.flush()

    assert (scored_link.ai_validation_state, scored_link.ai_score) == (STATE_SCORED, 71)
    assert scored_link.ai_validation_reason is None
    assert failed_link.ai_validation_state == STATE_UNVALIDATED
    assert failed_link.ai_score is None
    assert failed_link.ai_validation_reason == REASON_ERROR


def test_a_skipped_outcome_leaves_every_new_column_null(db, forbidden_model):
    """Finding 9's persistence half. `skipped` is never written: a row from a type that
    never opted in must be indistinguishable from every row that predates this slice,
    or a reader has two spellings of "nothing to say here"."""
    attachment_type = _seed_type(db, validate_on_upload=False)
    link = _link(db, attachment_type)
    _fn("apply_outcome", "(link, outcome)")(
        link,
        _validate(db, attachment_type=attachment_type, data=IMAGE_BYTES, content_type=IMAGE_MIME),
    )
    db.flush()

    for column in ("ai_score", "ai_suggestion", "ai_validation_state", "ai_validation_reason"):
        assert getattr(link, column) is None, f"{column} was written for a skipped type."


# ============================================================================
# G. Geolocation never blocks - AC-M27
# ============================================================================


def test_no_coordinates_at_all_is_normal_ac_m27(db):
    """AC-M27. Denied or unavailable is the DEFAULT case indoors, on a desktop, and on
    any device where the customer said no once a year ago."""
    latitude, longitude = _fn("normalize_coordinates", "(latitude, longitude)")(None, None)
    assert (latitude, longitude) == (None, None)


@pytest.mark.parametrize(
    "latitude,longitude",
    [
        (3.139, None),
        (None, 101.6869),
    ],
)
def test_half_a_fix_is_not_a_fix(db, latitude, longitude):
    """A lone latitude is not a place. Stored alone it renders as a pin on the prime
    meridian, off the coast of Ghana, presented as where the photo was taken."""
    assert _fn("normalize_coordinates", "(latitude, longitude)")(latitude, longitude) == (
        None,
        None,
    )


@pytest.mark.parametrize(
    "latitude,longitude",
    [
        (91.0, 101.6869),
        (-90.1, 101.6869),
        (3.139, 181.0),
        (3.139, -180.5),
        ("not-a-number", "also-not"),
        (float("nan"), float("nan")),
    ],
)
def test_an_impossible_fix_is_dropped_and_never_raises_ac_m27(db, latitude, longitude):
    """AC-M27 says never blocking, so a browser handing us a bad fix is just another
    spelling of "unavailable". Refusing the upload over it would block a photo on a
    nicety, and storing it would put a pin in the Pacific on a Malaysian service call.
    """
    assert _fn("normalize_coordinates", "(latitude, longitude)")(latitude, longitude) == (
        None,
        None,
    )


def test_null_island_is_treated_as_a_failed_fix(db):
    """Exactly (0, 0) is the classic no-fix sentinel. Sorento operates in Malaysia, so
    the odds this is a real reading are nil and the odds it is a device reporting
    failure are high. DECISION, no AC states it - flagged for review.
    """
    assert _fn("normalize_coordinates", "(latitude, longitude)")(0, 0) == (None, None)


def test_a_real_fix_is_kept_at_the_column_precision(db):
    """Kuala Lumpur, to the seven decimals AC-B21 chose for the Site pin.

    The longitude expectation was ``101.6869`` as first written, which no scale can
    satisfy alongside the latitude: ``101.6868999`` already carries exactly seven
    decimals, so at the pinned scale it is unchanged, and reaching ``101.6869`` needs
    quantizing at four to six places, which would truncate the latitude to
    ``3.139012``. Scale 7 is the one this file pins elsewhere against
    ``complaints.latitude`` (AC-B21), so the longitude is corrected here rather than
    the scale being loosened to fit a miscounted decimal.
    """
    latitude, longitude = _fn("normalize_coordinates", "(latitude, longitude)")(
        3.1390123456, 101.6868999
    )
    assert latitude is not None and longitude is not None
    assert Decimal(str(latitude)) == Decimal("3.1390123")
    assert Decimal(str(longitude)) == Decimal("101.6868999")


# ============================================================================
# H. The one wiring - AC-M21, AC-M23
# ============================================================================


def _seed_upload_type(db, **kwargs) -> AttachmentType:
    module = importlib.import_module(UPLOAD_MODULE)
    module.seed_workflow_submission_attachment_type(db)
    db.flush()
    row = (
        db.query(AttachmentType)
        .filter(AttachmentType.code == module.ATTACHMENT_TYPE_CODE)
        .one()
    )
    for field, value in kwargs.items():
        _type_column(field)
        setattr(row, field, value)
    db.flush()
    return row


def _submission(db):
    from app.services.workflow_forms_service import WorkflowFormsService
    from app.services.workflow_submission_line_status_graph import (
        register_workflow_submission_line_status_entity,
        seed_workflow_submission_line_status_graph,
    )
    from app.services.workflow_submission_status_graph import (
        register_workflow_submission_status_entity,
        seed_workflow_submission_status_graph,
    )

    seed_workflow_submission_status_graph(db)
    seed_workflow_submission_line_status_graph(db)
    db.flush()
    register_workflow_submission_status_entity()
    register_workflow_submission_line_status_entity()

    definition = WorkflowFormDefinition(
        id=str(uuid.uuid4()),
        code=unique_code("wfdef").lower(),
        name=f"{unique_code('Form')} definition",
        draft_schema=FORM_DOC,
    )
    db.add(definition)
    db.flush()
    version = WorkflowFormVersion(
        id=str(uuid.uuid4()),
        definition_id=definition.id,
        version_number=1,
        schema=FORM_DOC,
    )
    db.add(version)
    db.flush()
    definition.published_version_id = version.id
    db.flush()
    return WorkflowFormsService(db).create_submission(
        str(definition.id),
        {"title": f"{TEST_PREFIX} answer"},
        [{"line_group_id": LINE_GROUP, "row_data": {"model": f"{TEST_PREFIX}-1"}}],
        None,
    )


def _upload(db, submission, **extra):
    module = importlib.import_module(UPLOAD_MODULE)
    return module.WorkflowSubmissionAttachmentService(db).upload(
        submission_id=str(submission.id),
        contents=IMAGE_BYTES,
        filename="proof.png",
        content_type=IMAGE_MIME,
        notify=False,
        **extra,
    )


def _link_for(db, submission) -> EntityAttachmentLink:
    return (
        db.query(EntityAttachmentLink)
        .filter(EntityAttachmentLink.entity_id == str(submission.id))
        .one()
    )


def test_the_shared_upload_path_scores_and_stamps_the_link_ac_m21_ac_m23(db, model):
    """AC-M21 plus AC-M23, wired once.

    The plan names this path specifically: it already routes BOTH submission and line
    attachments through the one link table, so wiring the validator here reaches S3's
    consumer intake, S6's technician proof and S11's rma_readiness collection proof
    without any of the three growing its own path.
    """
    model.content = json.dumps({"score": 35, "suggestion": "Step back, include it all."})
    _seed_upload_type(
        db,
        validate_on_upload=True,
        validation_guidance=f"{TEST_PREFIX} the whole unit, in focus",
        min_score=60,
    )
    submission = _submission(db)

    result = _upload(db, submission)

    assert result["attachment_id"], (
        "A below-threshold upload did not complete. Finding 6: the bytes are kept "
        "whatever the score, or a timeout loses a photo somebody already took."
    )
    link = _link_for(db, submission)
    assert link.ai_score == 35
    assert link.ai_validation_state == STATE_SCORED
    assert link.ai_suggestion == "Step back, include it all."


def test_the_upload_response_carries_the_verdict_ac_m24(db, model):
    """AC-M24 is a UI shape, and the FE cannot render it from the persisted columns
    alone - it does not know the type's min_score, so it cannot work out whether 35 is
    a pass. The upload response is the only place the comparison is already made.
    """
    model.content = json.dumps({"score": 35, "suggestion": "Step back."})
    _seed_upload_type(
        db, validate_on_upload=True, validation_guidance="whole unit", min_score=60
    )
    submission = _submission(db)

    result = _upload(db, submission)

    assert result["ai_score"] == 35
    assert result["ai_suggestion"] == "Step back."
    assert result["ai_validation_state"] == STATE_SCORED
    assert result["validation_passed"] is False


def test_an_unvalidated_upload_still_completes_and_says_so(db, model):
    """The 6pm basement, end to end. The job closes, the photo is kept, and the record
    says honestly that nobody looked at it."""
    model.raise_with = RuntimeError("connection reset")
    _seed_upload_type(
        db, validate_on_upload=True, validation_guidance="whole unit", min_score=60
    )
    submission = _submission(db)

    result = _upload(db, submission)

    assert result["attachment_id"]
    assert result["ai_validation_state"] == STATE_UNVALIDATED
    assert result["validation_passed"] is not False
    link = _link_for(db, submission)
    assert link.ai_score is None
    assert link.ai_validation_reason == REASON_ERROR


def test_the_existing_upload_path_is_untouched_for_a_type_that_opted_out(
    db, forbidden_model
):
    """Finding 9, end to end. Every module in this repo uploads through some path that
    ends in this link table. A type that never opted in must behave exactly as it did
    the day before this slice landed - same latency, same failure modes, NULL columns.
    """
    _seed_upload_type(db, validate_on_upload=False)
    submission = _submission(db)

    result = _upload(db, submission)

    assert result["attachment_id"]
    link = _link_for(db, submission)
    for column in ("ai_score", "ai_suggestion", "ai_validation_state", "ai_validation_reason"):
        assert getattr(link, column) is None


def test_the_upload_accepts_a_capture_pin_and_stores_it_on_the_link_ac_m22(db, model):
    """AC-M22's coordinates arrive with the upload - that is the only moment the device
    knows where it is. A later PATCH would be a pin recorded from wherever the person
    happened to be when they got round to it."""
    _seed_upload_type(db, validate_on_upload=False)
    submission = _submission(db)

    _upload(db, submission, latitude=3.1390123, longitude=101.6869)

    link = _link_for(db, submission)
    assert Decimal(str(link.latitude)) == Decimal("3.1390123")
    assert Decimal(str(link.longitude)) == Decimal("101.6869")


def test_a_denied_or_broken_fix_never_fails_the_upload_ac_m27(db, model):
    """AC-M27, stated the way it will actually be met: the browser said no, or handed
    back nonsense, and the upload completed anyway with the columns left empty."""
    _seed_upload_type(db, validate_on_upload=False)

    for latitude, longitude in ((None, None), (999, 999), ("", "")):
        submission = _submission(db)
        result = _upload(db, submission, latitude=latitude, longitude=longitude)
        assert result["attachment_id"], (
            f"latitude={latitude!r} longitude={longitude!r} blocked the upload. "
            "AC-M27: never blocking."
        )
        link = _link_for(db, submission)
        assert (link.latitude, link.longitude) == (None, None)


# ============================================================================
# I. The read surface
# ============================================================================


def test_serialize_link_exposes_the_verdict_and_the_override(db, model):
    """`serialize_link` is the ONE shape every attachment list renders from - the CRM
    panels and the public /view pages both read it. A score that never reaches it is a
    score no screen can show, and "used anyway, because ..." is exactly the thing a
    reviewer needs to see on a listing rather than by opening a row.

    Same family as the two manual builders this repo has already been bitten by
    (`get_user`/`get_me`, the `system_settings` GET): inheriting the column is not
    enough.
    """
    from app.services.entity_attachment_service import EntityAttachmentService

    model.content = json.dumps({"score": 12, "suggestion": "Too dark."})
    attachment_type = _seed_type(db, min_score=60)
    link = _link(db, attachment_type)
    _fn("apply_outcome", "(link, outcome)")(
        link,
        _validate(db, attachment_type=attachment_type, data=IMAGE_BYTES, content_type=IMAGE_MIME),
    )
    db.flush()
    _fn("record_override", "(db, *, link_id, reason, user_id=None)")(
        db, link_id=str(link.id), reason=f"{TEST_PREFIX} built in, only possible angle"
    )
    db.flush()
    db.refresh(link)

    payload = EntityAttachmentService(db).serialize_link(link, "entity_id")

    assert payload["ai_score"] == 12
    assert payload["ai_suggestion"] == "Too dark."
    assert payload["ai_validation_state"] == STATE_SCORED
    assert payload["override_reason"].startswith(TEST_PREFIX)
    for key in ("latitude", "longitude", "ai_validation_reason"):
        assert key in payload, (
            f"serialize_link drops {key}. Every one of the AC-M22 columns has a reader "
            "or it should not have been added."
        )
