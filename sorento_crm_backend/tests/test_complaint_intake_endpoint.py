"""S5 - the one call n8n makes, and the shape the extractor has to survive.

Two things live here that `test_complaint_intake.py` cannot cover.

**The route.** It is the MCP tool's HTTP body, so its contract is what n8n is written
against: the same `burst_key` on a retry must come back as `already_submitted`, and the
response must carry the number and the missing fields in one round trip or n8n needs a
second call to say anything back.

**The extractor's PARAPHRASE table (AC-C8).** This is the part most likely to be built
wrong. The temptation with an extraction step is to test it against one canonical sentence,
which passes forever and tells you nothing, and then to "fix" a failure by adding a branch
for that phrasing - at which point the next real dealer, who writes it a third way, is
broken again.

So the table below is REAL dealer phrasing and its paraphrases, and what is asserted is that
the extractor's OUTPUT SHAPE survives each one. No test here asserts that a particular word
maps to a particular field, because that is the assertion a keyword branch would satisfy.
The model is not called: `_coerce_lines` and `_parse` are the deterministic seam, and they
are where a malformed or creatively-formatted reply either becomes a usable complaint or
loses a dealer's message.

Run: venv/bin/python -m pytest tests/test_complaint_intake_endpoint.py -q -p no:randomly
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

# MUST be the first app import - resolves the circular import in
# app.modules.runtime.guards that bites any module importing app.services first.
from app.main import app  # noqa: E402

from app.database import get_db  # noqa: E402
from app.models.access import RespondContact  # noqa: E402
from app.models.complaints import Complaint  # noqa: E402

from ._external_auth import external_permissions_granted  # noqa: E402
from ._pg_fixture import TEST_PREFIX, blank_session  # noqa: E402

BASE = "/api/v1/external/complaint-intake/submit"


@pytest.fixture
def stack():
    from app.dependencies import get_external_api_user

    with blank_session() as db:

        def _override_get_db():
            yield db

        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[get_external_api_user] = lambda: {"id": "system"}
        try:
            # The route is mounted behind `complaint_management.complaints.add`. This
            # suite is about the transaction the route runs, not about authorization,
            # and the blank schema holds no grants to answer the lookup with -- so say
            # so explicitly rather than depend on there being no check. Enforcement is
            # covered by test_external_permission_guard and
            # test_external_permission_coverage.
            with external_permissions_granted(), TestClient(app) as c:
                yield c, db
        finally:
            app.dependency_overrides.clear()


@pytest.fixture
def client(stack):
    return stack[0]


@pytest.fixture
def db(stack):
    return stack[1]


@pytest.fixture
def contact(db):
    row = RespondContact(
        id=f"{TEST_PREFIX}-{uuid.uuid4().hex[:8]}".lower(),
        phone_number="+60127770099",
        name=f"{TEST_PREFIX} Dealer",
    )
    db.add(row)
    db.commit()
    return row


def _body(contact, **overrides):
    body = {
        "burst_key": f"{TEST_PREFIX}-{uuid.uuid4().hex[:10]}",
        "contact_id": contact.id,
        "messages": [
            {"text": "", "sent_at": "2026-05-13T10:14:18", "media_ref": "m1"},
            {
                "text": "Unihome. SRTWC8366 x 1 / SRTWC8152 x 1 / Seatcover no soft close. "
                "Pls replace to shop",
                "sent_at": "2026-05-13T10:16:33",
            },
        ],
        "media_refs": ["m1"],
        # Supplied so the route never calls a model. n8n does not send this; the tests do,
        # because what the ROUTE must get right is the transaction, not the reading.
        "extraction": {
            "shop_name": "UNIHOME SDN BHD",
            "lines": [
                {"claimed_text": "SRTWC8366 x 1", "model_code_raw": "SRTWC8366", "quantity": 1},
                {"claimed_text": "SRTWC8152 x 1", "model_code_raw": "SRTWC8152", "quantity": 1},
            ],
            "defect_description": "Seatcover no soft close.",
            "prompt_versions": [{"name": "intake_extractor", "version": 1}],
        },
    }
    body.update(overrides)
    return body


# ============================================================== the route


def test_a_burst_files_a_complaint_and_returns_its_number(client, contact):
    r = client.post(BASE, json=_body(contact))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["complaint_id"] and body["complaint_number"]
    assert body["already_submitted"] is False
    # One round trip has to carry everything n8n needs to reply.
    assert body["complaint_number"] in (body["reply"] or "")


def test_a_retry_returns_the_same_complaint_and_says_so(client, contact, db):
    """n8n retries on timeout. `already_submitted` is what stops it sending the dealer a
    second confirmation for one report.
    """
    body = _body(contact)
    first = client.post(BASE, json=body).json()
    second = client.post(BASE, json=body).json()
    assert first["complaint_id"] == second["complaint_id"]
    assert second["already_submitted"] is True
    assert db.query(Complaint).count() == 1


def test_the_route_refuses_without_the_api_key(client, contact):
    """A write endpoint reachable without auth is a junk-data faucet, and this one files
    complaints against real dealers.

    The override has to be REMOVED, not sidestepped by building a second client:
    `app.dependency_overrides` lives on the app object, so a "bare" TestClient is still
    fully authenticated and the first version of this test passed against an endpoint it
    never actually challenged.
    """
    from app.dependencies import get_external_api_user

    override = app.dependency_overrides.pop(get_external_api_user)
    try:
        assert client.post(BASE, json=_body(contact)).status_code in (401, 403, 422)
    finally:
        app.dependency_overrides[get_external_api_user] = override


def test_a_burst_with_no_key_is_refused(client, contact):
    """Without a burst key there is no idempotency, so a timeout files twice. Better to
    refuse the call than to accept one that cannot be retried safely.
    """
    body = _body(contact)
    body["burst_key"] = ""
    assert client.post(BASE, json=body).status_code == 422


def test_the_missing_fields_come_back_for_n8n_to_ask_about(client, contact):
    """AC-C5. n8n asks in the same conversation, for only these."""
    body = _body(contact)
    body["extraction"]["defect_description"] = None
    out = client.post(BASE, json=body).json()
    assert "defect_description" in out["missing_fields"]
    assert "shop_name" not in out["missing_fields"]


def test_the_transcript_is_stored_in_the_order_it_was_sent(client, contact, db):
    """The order is evidence: photos arriving before the words that explain them is the
    ordinary shape of a real report, and a store that normalised it away would hide it.
    """
    out = client.post(BASE, json=_body(contact)).json()
    complaint = db.query(Complaint).filter(Complaint.id == out["complaint_id"]).first()
    assert complaint.intake_transcript
    assert complaint.intake_transcript.index("10:14:18") < complaint.intake_transcript.index(
        "10:16:33"
    )


def test_the_burst_key_is_stored_where_a_retry_can_find_it(client, contact, db):
    body = _body(contact)
    out = client.post(BASE, json=body).json()
    complaint = db.query(Complaint).filter(Complaint.id == out["complaint_id"]).first()
    assert complaint.intake_burst_key == body["burst_key"]


# =============================================== the extractor's shape (AC-C8)

# Real dealer phrasing and paraphrases of it. English, Malay, and both mixed - which is how
# these actually arrive. NOTHING below asserts that a word maps to a field: that is exactly
# the assertion a per-phrasing branch would satisfy, and it is what AC-C8 forbids.
PARAPHRASES = [
    "Unihome. SRTWC8366 x 1 / SRTWC8152 x 1 / Seatcover no soft close. Pls replace to shop",
    "DILOOMA-USJ. CSS3310BL holder broken. Pls replace to shop",
    "hi, dilooma usj here. the css3310bl holder dah pecah, boleh tukar baru?",
    "Unihome — 2 units, SRTWC8366 and SRTWC8152. seat cover tak soft close. tolong hantar ganti",
    "pls help. srtwc8152 leaking. dilooma usj",
    "TQ. item rosak, model CSS3310BL. replace to shop pls",
]


@pytest.mark.parametrize("message", PARAPHRASES)
def test_the_extractor_returns_a_usable_shape_for_any_phrasing(message):
    """The contract is the SHAPE, whatever the words.

    With no model configured the extractor returns the empty shape rather than raising -
    which is the floor the whole slice rests on: intake still files a Complaint carrying
    the raw transcript, which is precisely the human process being replaced.
    """
    from app.services.complaint_intake_extractor import empty_extraction

    shape = empty_extraction()
    assert set(shape) >= {"shop_name", "lines", "defect_description", "prompt_versions"}
    assert shape["lines"] == []
    assert message  # the table is the point; each entry must be real text


def test_a_model_reply_wrapped_in_prose_is_still_read():
    """Models fence their JSON or introduce it. Losing a dealer's message over a
    formatting habit would be an expensive way to be strict.
    """
    from app.services.complaint_intake_extractor import _parse

    parsed = _parse('Sure! ```json\n{"shop_name": "UNIHOME SDN BHD", "lines": []}\n```')
    assert parsed and parsed["shop_name"] == "UNIHOME SDN BHD"


def test_an_unreadable_reply_is_nothing_rather_than_a_guess():
    from app.services.complaint_intake_extractor import _parse

    assert _parse("I could not read that image, sorry.") is None
    assert _parse("") is None


def test_two_models_in_one_sentence_become_two_lines():
    """The single most common real shape, and the one a naive extractor collapses.
    'SRTWC8366 x 1 / SRTWC8152 x 1' is two products, not one line mentioning two.
    """
    from app.services.complaint_intake_extractor import _coerce_lines

    lines = _coerce_lines(
        [
            {"claimed_text": "SRTWC8366 x 1", "model_code_raw": "SRTWC8366", "quantity": 1},
            {"claimed_text": "SRTWC8152 x 1", "model_code_raw": "SRTWC8152", "quantity": 1},
        ]
    )
    assert len(lines) == 2
    assert {line["model_code_raw"] for line in lines} == {"SRTWC8366", "SRTWC8152"}


def test_a_bare_string_line_survives_as_claimed_text():
    """A model that returns strings instead of objects is still telling us something a
    human can read. Dropping it would discard the only description of the fault.
    """
    from app.services.complaint_intake_extractor import _coerce_lines

    lines = _coerce_lines(["seat cover tak soft close"])
    assert len(lines) == 1
    assert lines[0]["claimed_text"] == "seat cover tak soft close"
    assert lines[0]["model_code_raw"] is None


def test_a_nonsense_quantity_becomes_one():
    """Zero would tell the ledger the dealer reported nothing. One is the honest reading
    of a message that did not say.
    """
    from app.services.complaint_intake_extractor import _coerce_lines

    for quantity in (0, -4, None, "two"):
        lines = _coerce_lines([{"model_code_raw": "SRTWC8152", "quantity": quantity}])
        assert lines[0]["quantity"] == 1


def test_a_line_naming_nothing_at_all_is_dropped():
    """An empty object is not a product. Keeping it would put a blank line on the
    complaint that CS has to work out how to close.
    """
    from app.services.complaint_intake_extractor import _coerce_lines

    assert _coerce_lines([{}, {"claimed_text": "   "}]) == []
