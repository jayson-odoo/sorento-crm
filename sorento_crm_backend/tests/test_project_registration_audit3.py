"""PROJECT-REG-PORTAL audit round 3, red tests written against head 37421af5 (owner rulings of 25 Oct applied).

Items (coordinator list): 2 portal debtor lookup, 3 rate limits, 4 submit notifies in-app only,
5 M1 non-string fields, 6 M2 control characters in notice titles, 12 the exact-duplicate 409
carries the existing project. Staff projects also use PPF (no numbering switch). Duplicates (1) live in test_project_registration_duplicates.py, the migration downgrade
(7) in test_migration_prreg_0001_project_registrations.py, the front end (8, 10, 11) in vitest.

Rate limit contract these tests bind: a redis counter per contact (INCR + EXPIRE, the
`chatbot/direct_ingress.py` shape), read through `app.services.queue_service.redis_conn` at call
time, FAILING OPEN on any redis error; over the limit the route answers 429 with code
`RATE_LIMITED`. Keys are not named here: every test uses a contact that exists only in its own
schema, and the teardown deletes any key that carries the contact id.
"""
from __future__ import annotations

import pytest

from app.main import app  # noqa: F401  MUST be first app import (circular import)

from ._project_registration_support import (
    CRM,
    FIELD_KEYS,
    KIND,
    PORTAL,
    SUB,
    approve_body,
    as_contact,
    as_user,
    create_draft,
    debtor,
    developer,
    fields,
    pending,
    registration,
    rule_next_value,
    submit,
    world,  # noqa: F401  (fixture)
)

PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0"
    b"\x00\x00\x03\x01\x01\x00\xc9\xfe\x92\xef\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.fixture
def clean_keys(world):
    """Delete whatever rate-limit key the run left for the world's contacts."""
    yield
    from app.services.queue_service import redis_conn

    try:
        for contact_id in (world.a, world.b, world.noagent):
            for key in redis_conn.scan_iter(f"*{contact_id}*"):
                redis_conn.delete(key)
    except Exception:  # noqa: BLE001  (redis down: nothing was written)
        pass


# ------------------------------------------------------------------ 2 portal debtor lookup


def test_the_debtor_lookup_for_this_kind_returns_only_the_agents_own_debtors(world):
    unowned = debtor(world.db, world.company_id)  # no sales agent
    world.db.flush()
    c = as_contact(world, world.a)

    res = c.get(f"{PORTAL}/lookups/debtors", params={"kind": KIND, "q": "debtor", "limit": 50})
    assert res.status_code == 200, res.text
    ids = {row["customer_id"] for row in res.json()}
    # exactly the set the save check accepts: own debtors, not another agent's, not unowned
    assert ids == {world.debtor_a.id}
    assert world.debtor_b.id not in ids and unowned.id not in ids


def test_every_debtor_the_lookup_offers_is_accepted_by_the_save(world):
    c = as_contact(world, world.a)
    rows = c.get(f"{PORTAL}/lookups/debtors", params={"kind": KIND, "limit": 50}).json()
    assert rows
    for row in rows:
        res = c.post(SUB, json={"fields": fields(row["customer_id"])})
        assert res.status_code == 200, res.text


def test_the_debtor_lookup_for_this_kind_follows_the_search_text(world):
    c = as_contact(world, world.a)
    res = c.get(f"{PORTAL}/lookups/debtors", params={"kind": KIND, "q": "no-such-debtor-zzz"})
    assert res.status_code == 200, res.text
    assert res.json() == []


def test_without_kind_the_debtor_lookup_is_unchanged(world):
    unowned = debtor(world.db, world.company_id)
    world.db.flush()
    c = as_contact(world, world.a)
    res = c.get(f"{PORTAL}/lookups/debtors", params={"q": "debtor", "limit": 50})
    assert res.status_code == 200, res.text
    ids = {row["customer_id"] for row in res.json()}
    assert {world.debtor_a.id, world.debtor_b.id, unowned.id} <= ids


def test_another_kind_leaves_the_debtor_lookup_unfiltered(world):
    c = as_contact(world, world.a)
    res = c.get(f"{PORTAL}/lookups/debtors", params={"kind": "purchase_request", "q": "debtor", "limit": 50})
    assert res.status_code == 200, res.text
    assert world.debtor_b.id in {row["customer_id"] for row in res.json()}


# ------------------------------------------------------------------ 3 rate limits


def test_the_31st_save_in_an_hour_is_429_rate_limited_and_every_verb_counts(world, clean_keys):
    c = as_contact(world, world.a)
    first = create_draft(world)  # 1: create
    rid = first["id"]
    for n in range(28):  # 2..29: update
        res = c.put(f"{SUB}/{rid}", json={"fields": fields(world.debtor_a.id, mukim=f"Kulai {n}")})
        assert res.status_code == 200, (n, res.status_code, res.text)
    done = submit(world, rid)  # 30: submit
    assert done.status_code == 200, done.text

    over = c.post(SUB, json={"fields": fields(world.debtor_a.id)})  # 31: create
    assert over.status_code == 429, over.text
    assert over.json()["code"] == "RATE_LIMITED"


def test_a_submit_over_the_limit_is_refused_and_the_draft_stays_a_draft(world, clean_keys):
    c = as_contact(world, world.a)
    rid = create_draft(world)["id"]  # 1
    for n in range(29):  # 2..30
        assert c.put(f"{SUB}/{rid}", json={"fields": fields(world.debtor_a.id, mukim=f"K{n}")}).status_code == 200
    res = submit(world, rid)  # 31
    assert res.status_code == 429, res.text
    assert res.json()["code"] == "RATE_LIMITED"
    assert registration(world, rid).status == "draft"


def test_reads_and_other_contacts_are_not_limited(world, clean_keys):
    c = as_contact(world, world.a)
    rid = create_draft(world)["id"]
    for n in range(30):
        c.put(f"{SUB}/{rid}", json={"fields": fields(world.debtor_a.id, mukim=f"K{n}")})
    assert c.post(SUB, json={"fields": fields(world.debtor_a.id)}).status_code == 429
    assert c.get(f"{SUB}/{rid}").status_code == 200
    assert c.get(f"{PORTAL}/submissions", params={"type": KIND}).status_code == 200
    other = as_contact(world, world.b).post(SUB, json={"fields": fields(world.debtor_b.id)})
    assert other.status_code == 200, other.text


def test_the_save_limit_fails_open_when_redis_is_down(world, monkeypatch):
    """A redis blip must never refuse a registration (direct_ingress `fail_open`)."""
    from app.services import queue_service

    class Down:
        def __getattr__(self, name):
            raise ConnectionError("redis is down")

    monkeypatch.setattr(queue_service, "redis_conn", Down())
    res = as_contact(world, world.a).post(SUB, json={"fields": fields(world.debtor_a.id)})
    assert res.status_code == 200, res.text


@pytest.fixture
def stub_extract(monkeypatch):
    from app.api.v1.public import ai_extract as route
    from app.services.error_handler import AppException

    def refuse(self, *args, **kwargs):
        raise AppException(status_code=502, message="stubbed extract")

    monkeypatch.setattr(route.AIExtractService, "extract", refuse)


def _extract(c, form_key):
    return c.post(
        f"{PORTAL}/ai-extract",
        data={"form_key": form_key},
        files=[("files", ("zzt.png", PNG, "image/png"))],
    )


def test_the_11th_ai_extract_in_ten_minutes_is_429(world, stub_extract, clean_keys):
    c = as_contact(world, world.a)
    for n in range(10):
        res = _extract(c, "portal.project_registration")
        assert res.status_code != 429, (n, res.text)
    over = _extract(c, "portal.project_registration")
    assert over.status_code == 429, over.text
    assert over.json()["code"] == "RATE_LIMITED"


def test_the_ai_extract_limit_is_this_forms_only(world, stub_extract, clean_keys):
    c = as_contact(world, world.a)
    for _ in range(11):
        _extract(c, "portal.complaint")
    assert _extract(c, "portal.complaint").status_code != 429
    assert _extract(c, "portal.project_registration").status_code != 429


def test_the_ai_extract_limit_is_per_contact(world, stub_extract, clean_keys):
    for _ in range(11):
        _extract(as_contact(world, world.a), "portal.project_registration")
    assert _extract(as_contact(world, world.b), "portal.project_registration").status_code != 429


# ------------------------------------------------------------------ 4 and 6 notifications


def test_submit_notifies_approvers_in_app_only_never_by_email(world):
    pending(world)
    sent = [kw for kw in world.sent_kw if kw["type"] == "project_registration_submitted"]
    assert {kw["user_id"] for kw in sent} == {world.approver}
    for kw in sent:
        assert kw["send_in_app"] is True
        assert kw["send_email"] is False
        assert not kw.get("send_whatsapp") and not kw.get("send_web_push")


def test_approve_and_reject_still_notify_the_applicant_in_app_and_by_email(world):
    c = as_user(world, world.approver)
    ok = pending(world)
    world.sent_kw.clear()
    assert c.post(f"{CRM}/{ok}/approve", json=approve_body(world, ok)).status_code == 200
    no = pending(world)
    world.sent_kw.clear()
    assert c.post(f"{CRM}/{no}/reject", json={"reason": "not ours"}).status_code == 200
    rejected = [kw for kw in world.sent_kw if kw["type"] == "project_registration_rejected"]
    assert [kw["user_id"] for kw in rejected] == [world.applicant_user]
    assert rejected[0]["send_in_app"] is True and rejected[0]["send_email"] is True


def test_an_approve_notice_is_in_app_and_email_to_the_applicant(world):
    ok = pending(world)
    world.sent_kw.clear()
    as_user(world, world.approver).post(f"{CRM}/{ok}/approve", json=approve_body(world, ok))
    approved = [kw for kw in world.sent_kw if kw["type"] == "project_registration_approved"]
    assert [kw["user_id"] for kw in approved] == [world.applicant_user]
    assert approved[0]["send_in_app"] is True and approved[0]["send_email"] is True


def test_a_title_with_newlines_and_tabs_gives_a_one_line_notice_title(world):
    messy = "TOWER A\n\tBLOCK B\r\n  PHASE 2"
    pending(world, title=messy)
    sent = [kw for kw in world.sent_kw if kw["type"] == "project_registration_submitted"]
    assert sent
    for kw in sent:
        for part in (kw["title"], kw["body"]):
            assert not any(ch in part for ch in "\n\r\t"), repr(part)
        assert kw["title"] == "Project registration waits for your approval: TOWER A BLOCK B PHASE 2"


def test_a_decision_notice_title_is_one_line_too(world):
    rid = pending(world, title="TOWER C\nBLOCK D\tPHASE 3")
    c = as_user(world, world.approver)
    world.sent_kw.clear()
    assert c.post(f"{CRM}/{rid}/reject", json={"reason": "no"}).status_code == 200
    for kw in world.sent_kw:
        assert not any(ch in kw["title"] for ch in "\n\r\t"), repr(kw["title"])
    assert "TOWER C BLOCK D PHASE 3" in world.sent_kw[0]["title"]


# ------------------------------------------------------------------ 5 M1 non-string fields

BAD_VALUES = [5, 2.5, ["x"], {"a": 1}]
VERBS = ["create", "update", "submit"]


def _names_the_field(res, key: str) -> bool:
    text = res.text.lower()
    return key in text or key.replace("_", " ") in text


@pytest.mark.parametrize("verb", VERBS)
@pytest.mark.parametrize("key", sorted(FIELD_KEYS))
def test_m1_a_non_string_value_is_422_naming_the_field_never_500(world, clean_keys, verb, key):
    c = as_contact(world, world.a)
    good = fields(world.debtor_a.id)
    rid = None if verb == "create" else create_draft(world)["id"]
    before = world.db.execute(__import__("sqlalchemy").text("select count(*) from projects.project_registrations")).scalar()
    failures = []
    for bad in BAD_VALUES:
        body = dict(good, **{key: bad})
        if verb == "create":
            res = c.post(SUB, json={"fields": body})
        elif verb == "update":
            res = c.put(f"{SUB}/{rid}", json={"fields": body})
        else:
            res = c.post(f"{SUB}/{rid}/submit", json={"fields": body})
        if res.status_code != 422 or not _names_the_field(res, key):
            failures.append((repr(bad), res.status_code, res.text[:120]))
    assert not failures, failures
    world.db.expire_all()
    after = world.db.execute(__import__("sqlalchemy").text("select count(*) from projects.project_registrations")).scalar()
    assert after == before + (0 if verb != "create" else 0)
    if rid:
        assert registration(world, rid).status == "draft"


# ------------------------------------------------------------------ 12 exact duplicate carries the project


def _existing_project(body: dict):
    """`existing_project` at the top of the error body or under its `details` (the
    AppException `details` mechanism): either serialises through the global handler."""
    if isinstance(body.get("existing_project"), dict):
        return body["existing_project"]
    details = body.get("details")
    return details.get("existing_project") if isinstance(details, dict) else None


def test_the_exact_duplicate_409_carries_the_existing_project_as_data(world):
    from ._project_registration_support import project

    dev = developer(world.db, world.company_id, "Setia Example Group")
    existing = project(world.db, world.company_id, "Setia Alam Phase 3B", developer_party=dev, code="PPF2609001")
    rid = pending(world, title="  SETIA ALAM   phase 3b ")
    res = as_user(world, world.approver).post(
        f"{CRM}/{rid}/approve", json=approve_body(world, rid, developer_party_id=dev.id)
    )
    assert res.status_code == 409, res.text
    body = res.json()
    assert body["code"] == "project_registration_exact_duplicate"
    assert _existing_project(body) == {
        "project_id": existing.id,
        "project_code": "PPF2609001",
        "title": "Setia Alam Phase 3B",
    }
    assert "PPF2609001" in body["message"]  # the sentence still names it
    assert registration(world, rid).status == "pending"
    assert rule_next_value(world.db, world.rule_id) == 5


def test_possible_duplicates_never_block_and_carry_no_existing_project(world):
    from ._project_registration_support import project

    dev = developer(world.db, world.company_id, "Setia Example Group")
    near = project(world.db, world.company_id, "Setia Alam Phase 3B", developer_party=dev)
    world.semantic.append((near.id, 0.95))
    rid = pending(world, title="Setia Alam Ph 3B")
    res = as_user(world, world.approver).post(
        f"{CRM}/{rid}/approve", json=approve_body(world, rid, developer_party_id=dev.id)
    )
    assert res.status_code == 200, res.text
