"""AGENT-BULK-W4-CONTACTS (PLAN-agent-bulk-w4-contacts-8nov.md, UAC agent-bulk-w4-contacts-8nov-acceptance-criteria.md):
the agent edits contacts from a pasted table, keyed by phone, through `crm_batch_propose` and one confirm card.

Red tests, written before the write exists. Owner answers (8 Nov, "all recs"): Q1 the fields are Name, the
sponsorship switch ("Sponsorship must name a registered project") and the Respond.io Workspace; Q2 the phone is the
key only; Q3 a phone stored on two contacts is refused; Q4 a blank cell is unchanged and nothing is cleared; Q5 only
`user_management.contacts.edit`, the Edit Contact screen's slug. Postgres only; phones, names and workspaces are
invented (public repo).

Assumed shapes: `crm_contact_edit` args `phone`, `name`, `sponsorship_registered_project` (bool), `workspace` (the
workspace's name or space id as written). A row that cannot apply is refused in `read_before` with a 4xx whose
message is the row's reason.
"""
from __future__ import annotations

import uuid

from sqlalchemy import text

from app.models.access import RespondContact
from app.models.audit import AuditLog
from app.models.base import company_scope
from app.models.respond_workspace import RespondWorkspace
from app.utils.field_encryption import encrypt_secret
from tests.chatbot.agent.test_agent_bulk_grant import (  # noqa: F401  (fixtures are used by name)
    BATCH,
    EDIT,
    EDIT_OWN,
    _listeners,
    ctx_of,
    db,
    dealer,
    fake_phone,
    local,
    make_world,
    store,
)
from tests.chatbot.agent.test_agent_writes import answer_, round_of, run_turn, tc

WRITE = "crm_contact_edit"
EVENT = "contact.edit_agent"
READY = "I will make these changes when you confirm:"
NOT_CHANGED = "Not changed:"


def row_(phone, **cells) -> dict:
    return {"phone": phone, **cells}


def propose_rows(db, w, rows, **kw):
    from app.services.chatbot.agent import batch

    return batch.propose_rows(db, ctx_of(db, w), WRITE, rows, seen_ids=set(), **kw)


def reason_of(skipped, n: int) -> str:
    found = [s for s in skipped if s["row"] == n]
    assert found, f"row {n} was not skipped: {skipped}"
    return found[0]["reason"]


def confirm(db, w, steps):
    from app.services.chatbot.agent import actions

    return actions.confirm(db, w.respond_id, str(store(db, w, steps).id), via="console")


def contact(db, pk: str) -> RespondContact:
    db.expire_all()
    with company_scope(db, None):
        return db.get(RespondContact, str(pk))


def workspace_(db, name: str | None) -> RespondWorkspace:
    row = RespondWorkspace(
        id=str(uuid.uuid4()), space_id=f"zzt-space-{uuid.uuid4().hex[:8]}", name=name,
        api_key_ciphertext=encrypt_secret("respond-key"),
    )
    db.add(row)
    db.flush()
    db.commit()
    return row


def say(db, w, rows, text_, final="Done."):
    script = [round_of(tc(BATCH, {"write": WRITE, "rows": rows}, "b1")), answer_(final)]
    return run_turn(db, w, script, text_=text_)[0]


# ------------------------------------------------------------------ 1. registry and exposure (Q5)


def test_01_the_write_is_registered_batchable_under_the_contacts_edit_slug_only():
    from app.services.chatbot.agent import writes

    d = writes.WRITES[WRITE]
    assert d.batchable and d.user_permission == EDIT
    props = d.schema["function"]["parameters"]["properties"]
    assert set(props) == {"phone", "name", "sponsorship_registered_project", "workspace"}
    assert props["sponsorship_registered_project"]["type"] == "boolean"


def test_01_the_batch_tool_offers_it_with_contacts_edit_and_never_with_edit_own(db):
    from app.services.chatbot.agent import batch

    w = make_world(db, slugs=(EDIT,), superadmin=False)
    enum = batch.batch_tool_schema(db, ctx_of(db, w))["function"]["parameters"]["properties"]["write"]["enum"]
    assert WRITE in enum

    own = make_world(db, slugs=(EDIT_OWN,), superadmin=False)
    schema = batch.batch_tool_schema(db, ctx_of(db, own))
    assert schema is None or WRITE not in schema["function"]["parameters"]["properties"]["write"]["enum"]
    steps: list = []
    out = batch.propose(db, ctx_of(db, own), {"write": WRITE, "rows": [row_(fake_phone(), name="X")]}, steps,
                        seen_ids=set())
    assert out.status == "denied" and steps == []


# ------------------------------------------------------------------ 2. preview then confirm, audit


def test_02_a_name_by_local_phone_previews_then_confirm_changes_it_and_audits(db):
    w = make_world(db)
    person = dealer(db, w, name="ZZT ALI HW")
    steps, skipped, waiting = propose_rows(db, w, [row_(local(person.phone_number), name="ZZT Ali Hardware Sdn Bhd")])
    assert skipped == [] and waiting == [] and len(steps) == 1
    cells = steps[0]["cells"]
    assert cells["Phone"] == person.phone_number
    assert 'name "ZZT ALI HW" -> "ZZT Ali Hardware Sdn Bhd"' in cells["Will change"]
    assert contact(db, person.id).name == "ZZT ALI HW"  # nothing before Confirm

    outcome = confirm(db, w, steps)
    assert outcome.status == "executed"
    assert contact(db, person.id).name == "ZZT Ali Hardware Sdn Bhd"
    rows = db.query(AuditLog).filter(AuditLog.event == EVENT, AuditLog.entity_id == str(person.id)).all()
    assert len(rows) == 1 and "from a pasted table" in rows[0].description
    assert person.phone_number in rows[0].description


def test_02_the_sponsorship_switch_and_the_workspace_change_and_the_name_stays(db):
    w = make_world(db)
    old_ws, new_ws = workspace_(db, f"ZZT Old WS {uuid.uuid4().hex[:4]}"), workspace_(db, f"ZZT New WS {uuid.uuid4().hex[:4]}")
    person = dealer(db, w, name="ZZT Same Name")
    with company_scope(db, None):
        db.get(RespondContact, person.id).workspace_id = old_ws.id
    db.commit()

    steps, skipped, _ = propose_rows(db, w, [row_(
        person.phone_number, name="zzt same  name", sponsorship_registered_project=True, workspace=new_ws.name.upper(),
    )])
    assert skipped == [] and len(steps) == 1
    change = steps[0]["cells"]["Will change"]
    assert "sponsorship rule off -> on" in change
    assert f"workspace {old_ws.name} -> {new_ws.name}" in change
    assert 'name "' not in change  # case and spacing only: the same name

    assert confirm(db, w, steps).status == "executed"
    after = contact(db, person.id)
    assert after.requires_registered_project is True
    assert str(after.workspace_id) == str(new_ws.id)
    assert after.name == "ZZT Same Name"


def test_02_a_workspace_by_space_id_is_that_workspace(db):
    w = make_world(db)
    ws = workspace_(db, None)
    person = dealer(db, w)
    steps, skipped, _ = propose_rows(db, w, [row_(person.phone_number, workspace=ws.space_id)])
    assert skipped == [] and len(steps) == 1
    assert confirm(db, w, steps).status == "executed"
    assert str(contact(db, person.id).workspace_id) == str(ws.id)


# ------------------------------------------------------------------ 3. phone rules (Q2, Q3) and not changed


def test_03_unknown_invalid_shared_and_repeated_phones_are_not_changed_and_nothing_is_created(db):
    w = make_world(db)
    shared = fake_phone()
    dealer(db, w, phone=shared)
    dealer(db, w, phone=local(shared))
    once = dealer(db, w)
    nobody = fake_phone()
    steps, skipped, _ = propose_rows(db, w, [
        row_(nobody, name="ZZT Nobody"),
        row_("12345", name="ZZT Short"),
        row_(shared, name="ZZT Shared"),
        row_(once.phone_number, name="ZZT Once"),
        row_(local(once.phone_number), name="ZZT Once Again"),
    ])
    assert [s["row"] for s in steps] == [4]
    assert reason_of(skipped, 1) == f"No contact with the phone {nobody}."
    assert "not a Malaysian mobile number" in reason_of(skipped, 2)
    assert "More than one contact has this phone number" in reason_of(skipped, 3)
    assert reason_of(skipped, 5) == "Same as row 4."
    with company_scope(db, None):
        digits = nobody.lstrip("+")
        assert db.query(RespondContact).filter(
            text("regexp_replace(respond_contacts.phone_number, '\\D', '', 'g') = :d")
        ).params(d=digits).count() == 0


def test_03_the_phone_is_the_key_only(db):
    """Q2 (b): there is no new-phone argument; the row's phone never changes."""
    from app.services.chatbot.agent import writes

    props = writes.WRITES[WRITE].schema["function"]["parameters"]["properties"]
    assert not any("new" in p for p in props)
    w = make_world(db)
    person = dealer(db, w)
    steps, _, _ = propose_rows(db, w, [row_(local(person.phone_number), name="ZZT Renamed")])
    assert confirm(db, w, steps).status == "executed"
    assert contact(db, person.id).phone_number == person.phone_number


def test_03_a_row_with_nothing_to_change_and_blank_cells_are_not_changed(db):
    """Q4 (a): a blank cell is unchanged; a row whose every cell matches is Nothing to change."""
    w = make_world(db)
    person = dealer(db, w, name="ZZT Steady")
    steps, skipped, _ = propose_rows(db, w, [
        row_(person.phone_number, name="ZZT Steady", sponsorship_registered_project=False),
        row_(fake_phone()),
    ])
    assert steps == []
    assert reason_of(skipped, 1) == "Nothing to change."
    assert reason_of(skipped, 2).startswith("No contact with the phone")

    blank = dealer(db, w, name="ZZT Keep Me")
    steps, skipped, _ = propose_rows(db, w, [row_(blank.phone_number, name="  ", workspace="")])
    assert steps == [] and reason_of(skipped, 1) == "Give a name, the sponsorship rule or the workspace to change."
    assert contact(db, blank.id).name == "ZZT Keep Me"


def test_03_an_unknown_or_ambiguous_workspace_is_not_changed(db):
    w = make_world(db)
    twin = f"ZZT Twin WS {uuid.uuid4().hex[:4]}"
    workspace_(db, twin)
    workspace_(db, twin)
    person = dealer(db, w)
    steps, skipped, _ = propose_rows(db, w, [
        row_(person.phone_number, workspace="ZZT No Such Space"),
        row_(dealer(db, w).phone_number, workspace=twin),
    ])
    assert steps == []
    assert reason_of(skipped, 1) == 'No Respond.io workspace named "ZZT No Such Space".'
    assert reason_of(skipped, 2) == f'More than one Respond.io workspace is named "{twin}"; give its space id.'


def test_03_the_users_own_contact_is_refused(db):
    w = make_world(db)
    mine = fake_phone()
    with company_scope(db, None):
        db.get(RespondContact, w.contact["pk"]).phone_number = mine
    db.commit()
    steps, skipped, _ = propose_rows(db, w, [row_(mine, name="ZZT Me Renamed")])
    assert steps == [] and reason_of(skipped, 1) == "That is your own contact; change it on the contacts screen."


# ------------------------------------------------------------------ 4. confirm-time checks


def test_04_a_contact_changed_on_screen_since_the_preview_fails_alone(db):
    w = make_world(db)
    moved, steady = dealer(db, w, name="ZZT Moved"), dealer(db, w, name="ZZT Steady Two")
    steps, _, _ = propose_rows(db, w, [
        row_(moved.phone_number, name="ZZT Moved New"),
        row_(steady.phone_number, name="ZZT Steady New"),
    ])
    with company_scope(db, None):
        db.get(RespondContact, moved.id).name = "ZZT Moved On Screen"
    db.commit()

    outcome = confirm(db, w, steps)
    assert outcome.status == "partial"
    assert [s["status"] for s in outcome.steps] == ["failed", "done"]
    assert contact(db, moved.id).name == "ZZT Moved On Screen"
    assert contact(db, steady.id).name == "ZZT Steady New"


def test_04_the_slug_removed_before_confirm_fails_every_row_and_writes_nothing(db):
    from app.services.user_service import invalidate_rbac_cache

    w = make_world(db, slugs=(EDIT,), superadmin=False)
    person = dealer(db, w, name="ZZT Before")
    steps, _, _ = propose_rows(db, w, [row_(person.phone_number, name="ZZT After")])
    action_steps = steps
    db.execute(text(
        "DELETE FROM user_role_permissions WHERE role_id IN "
        "(SELECT role_id FROM user_role_assignments WHERE user_id = :u)"
    ), {"u": w.user_id})
    db.commit()
    invalidate_rbac_cache()
    outcome = confirm(db, w, action_steps)
    assert outcome.status == "rejected"
    assert contact(db, person.id).name == "ZZT Before"


# ------------------------------------------------------------------ 5. one turn, one card


def test_05_a_turn_shows_ready_and_not_changed_tables_and_writes_nothing(db):
    w = make_world(db)
    person = dealer(db, w, name="ZZT Turn Old")
    nobody = fake_phone()
    r = say(db, w, [
        {**row_(person.phone_number, name="ZZT Turn New"), "row": 1},
        {**row_(nobody, name="ZZT Ghost"), "row": 2},
    ], "update these contacts")
    assert r.reply_text.startswith("Rows from your table: 1 ready to confirm, 1 not changed.")
    assert READY in r.reply_text and NOT_CHANGED in r.reply_text
    assert f"No contact with the phone {nobody}." in r.reply_text.split(NOT_CHANGED, 1)[1]
    assert r.pending_action is not None and len(r.pending_action["lines"]) == 1
    assert contact(db, person.id).name == "ZZT Turn Old"


def test_05_the_write_is_named_in_the_tool_labels():
    from app.services.chatbot.agent import tools

    assert tools.TOOL_LABELS[WRITE] == "edit contacts from a pasted table"


# ------------------------------------------------------------------ 6. security review (8 Nov): workspace gates

WS_VIEW = "system.respond_workspaces.view"
NO_WS = "You cannot change a contact's Respond.io workspace."


def test_06_an_inactive_workspace_is_never_offered(db):
    """S1: the screen's picker lists active workspaces only; an inactive one reads as not found."""
    w = make_world(db)
    ws = workspace_(db, f"ZZT Retired WS {uuid.uuid4().hex[:4]}")
    with company_scope(db, None):
        db.get(RespondWorkspace, ws.id).is_active = False
    db.commit()
    person = dealer(db, w)
    steps, skipped, _ = propose_rows(db, w, [row_(person.phone_number, workspace=ws.name),
                                             row_(dealer(db, w).phone_number, workspace=ws.space_id)])
    assert steps == []
    assert reason_of(skipped, 1) == f'No Respond.io workspace named "{ws.name}".'
    assert reason_of(skipped, 2) == f'No Respond.io workspace named "{ws.space_id}".'


def test_06_the_workspace_needs_the_workspace_view_slug_and_the_refusal_says_nothing_about_the_name(db):
    """S2: without the slug the screen's picker is empty; the agent refuses the cell with one fixed message, the
    same whether the name exists or not. The other cells of a user without it still apply."""
    w = make_world(db, slugs=(EDIT,), superadmin=False)
    ws = workspace_(db, f"ZZT Real WS {uuid.uuid4().hex[:4]}")
    a, b, c = dealer(db, w), dealer(db, w), dealer(db, w, name="ZZT Old C")
    steps, skipped, _ = propose_rows(db, w, [
        row_(a.phone_number, workspace=ws.name),
        row_(b.phone_number, workspace="ZZT No Such Space"),
        row_(c.phone_number, name="ZZT New C"),
    ])
    assert [s["row"] for s in steps] == [3]
    assert reason_of(skipped, 1) == NO_WS and reason_of(skipped, 2) == NO_WS

    seen = make_world(db, slugs=(EDIT, WS_VIEW), superadmin=False)
    steps, skipped, _ = propose_rows(db, seen, [row_(dealer(db, seen).phone_number, workspace=ws.name)])
    assert skipped == [] and len(steps) == 1


def test_06_a_target_workspace_renamed_before_confirm_fails_the_row(db):
    """N1: the card's target workspace is part of the confirm re-check."""
    w = make_world(db)
    first, other = workspace_(db, f"ZZT First WS {uuid.uuid4().hex[:4]}"), workspace_(db, f"ZZT Other WS {uuid.uuid4().hex[:4]}")
    person = dealer(db, w)
    steps, _, _ = propose_rows(db, w, [row_(person.phone_number, workspace=first.name)])
    with company_scope(db, None):
        name = first.name
        db.get(RespondWorkspace, first.id).name = f"{name} Old"
        db.get(RespondWorkspace, other.id).name = name
    db.commit()
    outcome = confirm(db, w, steps)
    assert outcome.status != "executed"
    assert contact(db, person.id).workspace_id is None
