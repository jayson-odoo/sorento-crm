"""AGENT-BULK-W2-TAGS (PLAN-agent-bulk-w2-tags-8nov.md, UAC agent-bulk-w2-tags-8nov-acceptance-criteria.md): the agent
adds / removes contact tags from a pasted table through `crm_batch_propose` over a new batchable row write,
`crm_contact_tags`.

Red tests, written before the code. Test numbers in the names are the UAC's brackets (01..09). Seeding and turn
helpers come from the #2226 / #2241 modules. Postgres only (blank schema); every test seeds its own chain. Tag and
person names and phones are invented (public repo).

Pinned shapes:
- `crm_contact_tags` args: `phone`, `name`, `tags_add`, `tags_remove` (tag names as written).
- A row that cannot apply is refused in `read_before` (4xx) with every reason joined by "; ". A tag name that is not
  exact but is contained in active tag names makes the row wait: `contact_grant.NeedsChoice` with choices
  {"written", "company": "", "candidates": [{"code": <tag name>, "name": ""}], "more", "noun": "tag", "kept": [...]}.
- The step's summary / "Will change" cell: "add tag X", "remove tag Y", "settings: <labels>",
  "not applied (needs more access): <section titles>".
- Confirm writes membership + settings through `ContactTagService.bulk_tag` (the screen's path) and records one
  `contact.tags_agent` audit row per contact.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.models.access import AccessAgent, ContactAgentAccess, ContactTag, RespondContact, respond_contact_tags
from app.models.audit import AuditLog
from tests.chatbot.agent.test_agent_bulk_grant import (  # noqa: F401  (fixtures are used by name)
    AGENTS_EDIT,
    BATCH,
    EDIT,
    EDIT_OWN,
    GRANT,
    _listeners,
    ctx_of,
    db,
    dealer,
    fake_phone,
    local,
    make_world,
    store,
)
from tests.chatbot.agent.test_agent_writes import action_rows, answer_, round_of, run_turn, tc

TAGS = "crm_contact_tags"
EVENT = "contact.tags_agent"
NEEDS = "Needs your choice:"
NOT_CHANGED = "Not changed:"
READY = "I will make these changes when you confirm:"
TAG_TAIL = "Reply with the tag name(s) for each row under Needs your choice, all, or skip."


def stem() -> str:
    return f"ZZT {uuid.uuid4().hex[:6]}"


def tag_(db, name: str, settings: dict | None = None, *, active: bool = True) -> ContactTag:
    row = ContactTag(id=str(uuid.uuid4()), name=name, settings=settings or {}, is_active=active)
    db.add(row)
    db.flush()
    db.commit()
    return row


def hold(db, contact, *tags) -> None:
    from sqlalchemy import insert

    db.execute(insert(respond_contact_tags), [{"contact_id": str(contact.id), "tag_id": str(t.id)} for t in tags])
    db.commit()


def held(db, contact) -> list[str]:
    db.expire_all()
    return sorted(
        name for (name,) in db.execute(
            select(ContactTag.name).join(respond_contact_tags, respond_contact_tags.c.tag_id == ContactTag.id)
            .where(respond_contact_tags.c.contact_id == str(contact.id))
        )
    )


def fresh(db, contact) -> RespondContact:
    db.expire_all()
    return db.get(RespondContact, str(contact.id))


def row_(phone, *, name="ZZT Person", add=(), remove=()) -> dict:
    out = {"phone": phone, "name": name}
    if add:
        out["tags_add"] = list(add)
    if remove:
        out["tags_remove"] = list(remove)
    return out


def propose_rows(db, w, rows, **kw):
    from app.services.chatbot.agent import batch

    return batch.propose_rows(db, ctx_of(db, w), TAGS, rows, seen_ids=set(), **kw)


def reason_of(skipped, n: int) -> str:
    found = [s for s in skipped if s["row"] == n]
    assert found, f"row {n} was not skipped: {skipped}"
    return found[0]["reason"]


def confirm(db, w, steps):
    from app.services.chatbot.agent import actions

    action = store(db, w, steps)
    return actions.confirm(db, w.respond_id, str(action.id), via="console")


def say(db, w, rows, text_, final="Done."):
    script = [round_of(tc(BATCH, {"write": TAGS, "rows": rows}, "b1")), answer_(final)]
    return run_turn(db, w, script, text_=text_)[0]


def numbered(row: dict, n: int) -> dict:
    return {**row, "row": n}


# ------------------------------------------------------------------ T1 (01) registry and exposure


def test_01_the_tags_write_is_registered_batchable_with_the_contacts_edit_slug():
    from app.services.chatbot.agent import writes

    d = writes.WRITES[TAGS]
    assert d.batchable is True and d.user_permission == EDIT and d.runs_as == "user"
    props = d.schema["function"]["parameters"]["properties"]
    assert {"phone", "name", "tags_add", "tags_remove"} <= set(props)
    for key in ("tags_add", "tags_remove"):
        assert props[key]["type"] == "array" and props[key]["items"] == {"type": "string"}


def test_01_the_batch_tool_offers_both_writes_with_the_slug_and_neither_without(db):
    from app.services.chatbot.agent import batch

    w = make_world(db, superadmin=False)
    enum = batch.schema_for(db, ctx_of(db, w))["function"]["parameters"]["properties"]["write"]["enum"]
    assert set(enum) == {GRANT, TAGS}

    own = make_world(db, slugs=(EDIT_OWN,), superadmin=False)
    assert batch.schema_for(db, ctx_of(db, own)) is None
    steps = []
    out = batch.propose(db, ctx_of(db, own), {"write": TAGS, "rows": [row_(fake_phone(), add=["x"])]}, steps,
                        seen_ids=set())
    assert out.status == "denied" and steps == []


# ------------------------------------------------------------------ T2 (02) add / remove end to end


def test_02_add_by_local_phone_previews_then_confirm_writes_membership_and_audit(db):
    w = make_world(db)
    t = tag_(db, f"{stem()} Office Staff")
    person = dealer(db, w)

    steps, skipped, waiting = propose_rows(db, w, [row_(local(person.phone_number), add=[t.name.upper()])])

    assert skipped == [] and waiting == [] and len(steps) == 1
    step = steps[0]
    assert f"add tag {t.name}" in step["summary"]
    assert step["cells"]["Phone"] == person.phone_number and f"add tag {t.name}" in step["cells"]["Will change"]
    assert held(db, person) == []  # nothing written by a preview

    outcome = confirm(db, w, steps)
    assert outcome.status == "executed", outcome.steps
    assert held(db, person) == [t.name]
    audits = db.query(AuditLog).filter(AuditLog.entity_id == str(person.id)).all()
    assert any((a.description or "") == f"Tag added: {t.name}" for a in audits)
    assert len([a for a in audits if a.event == EVENT]) == 1


def test_02_remove_drops_only_that_tag_and_leaves_settings(db):
    w = make_world(db)
    keep = tag_(db, f"{stem()} Office Staff")
    drop = tag_(db, f"{stem()} Project Salesperson", {"chatbot": {"chatbot_stock_allowed": True}})
    person = dealer(db, w)
    hold(db, person, keep, drop)
    person = fresh(db, person)
    person.chatbot_stock_allowed = True
    db.commit()

    steps, skipped, _ = propose_rows(db, w, [row_(person.phone_number, remove=[drop.name])])
    assert skipped == [] and f"remove tag {drop.name}" in steps[0]["summary"]
    assert "settings" not in steps[0]["summary"]

    assert confirm(db, w, steps).status == "executed"
    assert held(db, person) == [keep.name]
    assert fresh(db, person).chatbot_stock_allowed is True


# ------------------------------------------------------------------ T3 (03) exact name wins


def test_03_an_exact_name_wins_over_longer_names_that_contain_it(db):
    w = make_world(db)
    s = stem()
    short = tag_(db, f"{s} Mocha Dealer")
    tag_(db, f"{s} Mocha Dealer Tag")
    person = dealer(db, w)

    written = f"  {s.lower()}  mocha DEALER "
    steps, skipped, waiting = propose_rows(db, w, [row_(person.phone_number, add=[written])])

    assert waiting == [] and skipped == [] and len(steps) == 1
    assert steps[0]["summary"].count("add tag") == 1 and f"add tag {short.name}" in steps[0]["summary"]
    assert f"{short.name} Tag" not in steps[0]["summary"]


# ------------------------------------------------------------------ T4 (04) a contained name is a pick


def test_04_a_contained_name_waits_with_the_active_tags_by_name_and_writes_nothing(db):
    w = make_world(db)
    s = stem()
    retail = tag_(db, f"{s} Retail Salesperson")
    project = tag_(db, f"{s} Project Salesperson")
    tag_(db, f"{s} Old Salesperson", active=False)
    person = dealer(db, w)

    steps, skipped, waiting = propose_rows(db, w, [row_(person.phone_number, add=["Salesperson"])])

    assert steps == [] and skipped == []
    mine = [x for x in waiting if x["row"] == 1]
    assert len(mine) == 1
    item = mine[0]
    names = [c["code"] for c in item["candidates"]]
    assert project.name in names and retail.name in names
    assert f"{s} Old Salesperson" not in names
    assert names == sorted(names, key=str.lower)
    assert item["written"] == "Salesperson" and item["noun"] == "tag"
    assert held(db, person) == []


def test_04_one_containing_tag_still_waits_and_is_never_auto_picked(db):
    w = make_world(db)
    only = tag_(db, f"{stem()} Unique Gadget")
    person = dealer(db, w)

    steps, skipped, waiting = propose_rows(db, w, [row_(person.phone_number, add=["unique gadget"])])

    assert steps == [] and skipped == []
    assert [c["code"] for c in waiting[0]["candidates"]] == [only.name]


def test_04_more_than_ten_containing_tags_list_ten_and_say_more(db):
    w = make_world(db)
    s = stem()
    for i in range(12):
        tag_(db, f"{s} Zebra {i:02d}")
    person = dealer(db, w)

    _, _, waiting = propose_rows(db, w, [row_(person.phone_number, add=[f"{s} zebra"])])

    assert len(waiting[0]["candidates"]) == 10 and waiting[0]["more"] is True


def test_04_a_waiting_row_keeps_its_exact_tags_so_a_repropose_needs_no_retyping(db):
    w = make_world(db)
    s = stem()
    exact = tag_(db, f"{s} Office Staff")
    pick = tag_(db, f"{s} Retail Salesperson")
    tag_(db, f"{s} Project Salesperson")
    person = dealer(db, w)

    first = [numbered(row_(person.phone_number, add=[exact.name, "salesperson"]), 1)]
    r1 = say(db, w, first, "tag these people")
    assert r1.pending_action is None and NEEDS in r1.reply_text and TAG_TAIL in r1.reply_text

    second = [numbered(row_(person.phone_number, add=[exact.name, pick.name]), 1)]
    r2 = say(db, w, second, f"row 1: {pick.name}")
    assert r2.pending_action is not None and len(r2.pending_action["lines"]) == 1
    step = action_rows(db, w.respond_id)[-1].steps[0]
    assert f"add tag {exact.name}" in step["summary"] and f"add tag {pick.name}" in step["summary"]


def test_04_a_tag_neither_listed_nor_kept_nor_typed_is_not_changed(db):
    w = make_world(db)
    s = stem()
    tag_(db, f"{s} Retail Salesperson")
    tag_(db, f"{s} Project Salesperson")
    other = tag_(db, f"{s} Admin")
    person = dealer(db, w)

    say(db, w, [numbered(row_(person.phone_number, add=["salesperson"]), 1)], "tag this person")
    result = say(db, w, [numbered(row_(person.phone_number, add=[other.name]), 1)], "ok go ahead")

    assert result.pending_action is None
    assert f'"{other.name}" was not in the list' in result.reply_text
    assert held(db, person) == []


# ------------------------------------------------------------------ T5 (05) every reason, Not changed


def test_05_hard_problems_are_not_changed_with_every_reason(db):
    w = make_world(db)
    s = stem()
    old = tag_(db, f"{s} Retired", active=False)
    both = tag_(db, f"{s} Both")
    have = tag_(db, f"{s} Have")
    person, holder = dealer(db, w), dealer(db, w)
    hold(db, holder, have)
    nobody = fake_phone()

    steps, skipped, waiting = propose_rows(db, w, [
        {"name": "ZZT No Phone", "tags_add": [both.name]},
        row_(nobody, add=[both.name]),
        row_(person.phone_number, add=[f"{s} Gold", old.name]),
        row_(person.phone_number.replace("+6019", "+6017"), add=[both.name], remove=[both.name]),
        row_(holder.phone_number),
    ])

    assert steps == [] and waiting == []
    assert "Give the phone" in reason_of(skipped, 1)
    assert "No contact has the phone" in reason_of(skipped, 2)
    r3 = reason_of(skipped, 3)
    assert f'No tag named "{s} Gold"' in r3 and f'Tag "{old.name}" is inactive' in r3
    assert f'Tag "{both.name}" is both added and removed' in reason_of(skipped, 4)
    assert "Name the tag(s) to add or remove" in reason_of(skipped, 5)


def test_05_already_tagged_with_matching_settings_is_nothing_to_change(db):
    w = make_world(db)
    have = tag_(db, f"{stem()} Have", {"chatbot": {"chatbot_stock_allowed": False}})
    holder = dealer(db, w)
    hold(db, holder, have)
    fresh(db, holder).chatbot_stock_allowed = False
    db.commit()

    steps, skipped, _ = propose_rows(db, w, [row_(holder.phone_number, add=[have.name])])

    assert steps == [] and "Already tagged; nothing to change" in reason_of(skipped, 1)


def test_05_a_missing_tag_next_to_an_ambiguous_one_is_not_changed_not_waiting(db):
    w = make_world(db)
    s = stem()
    tag_(db, f"{s} Retail Salesperson")
    tag_(db, f"{s} Project Salesperson")
    person = dealer(db, w)

    steps, skipped, waiting = propose_rows(db, w, [row_(person.phone_number, add=[f"{s} Gold", "salesperson"])])

    assert steps == [] and waiting == []
    r = reason_of(skipped, 1)
    assert f'No tag named "{s} Gold"' in r and "fits 2 tags" in r


# ------------------------------------------------------------------ T6 (06) add applies the tag's settings


def test_06_add_applies_the_tags_settings_listed_in_the_preview(db):
    w = make_world(db)
    t = tag_(db, f"{stem()} Office Staff", {"chatbot": {"chatbot_stock_allowed": False}})
    person = dealer(db, w)
    fresh(db, person).chatbot_stock_allowed = True
    db.commit()

    steps, skipped, _ = propose_rows(db, w, [row_(person.phone_number, add=[t.name])])
    assert skipped == []
    assert "settings: Stock checks" in steps[0]["summary"]
    assert fresh(db, person).chatbot_stock_allowed is True  # a preview writes nothing

    assert confirm(db, w, steps).status == "executed"
    assert fresh(db, person).chatbot_stock_allowed is False and held(db, person) == [t.name]


def test_06_a_section_the_user_may_not_write_is_not_applied_and_not_written(db):
    from app.services.contact_tag_settings import SECTION_TITLES

    w = make_world(db, slugs=(EDIT,), superadmin=False)  # no access_agents.edit
    agent = AccessAgent(code=f"zzt_{uuid.uuid4().hex[:8]}", name="ZZT agent")
    db.add(agent)
    db.flush()
    t = tag_(db, f"{stem()} Dealer", {"chatbot": {"chatbot_stock_allowed": False}, "agents": {str(agent.id): True}})
    person = dealer(db, w)
    fresh(db, person).chatbot_stock_allowed = True
    db.commit()

    steps, skipped, _ = propose_rows(db, w, [row_(person.phone_number, add=[t.name])])
    assert skipped == []
    summary = steps[0]["summary"]
    assert f"not applied (needs more access): {SECTION_TITLES['agents']}" in summary
    assert "Stock checks" in summary

    assert confirm(db, w, steps).status == "executed"
    assert fresh(db, person).chatbot_stock_allowed is False
    assert db.query(ContactAgentAccess).filter(ContactAgentAccess.respond_contact_id == str(person.id)).count() == 0


# ------------------------------------------------------------------ T7 (07) per-row confirm and recheck


def test_07_a_row_changed_since_the_preview_fails_alone_and_the_others_apply(db):
    w = make_world(db)
    t = tag_(db, f"{stem()} Office Staff")
    other = tag_(db, f"{stem()} Admin")
    a, b = dealer(db, w), dealer(db, w)

    steps, skipped, _ = propose_rows(db, w, [row_(a.phone_number, add=[t.name]), row_(b.phone_number, add=[t.name])])
    assert skipped == [] and len(steps) == 2
    hold(db, a, other)  # someone tags A on the screen before the confirm

    outcome = confirm(db, w, steps)
    assert outcome.status == "partial", outcome.steps
    assert held(db, a) == [other.name]
    assert held(db, b) == [t.name]


def test_07_the_same_phone_twice_is_same_as_the_earlier_row(db):
    w = make_world(db)
    t = tag_(db, f"{stem()} Office Staff")
    a = dealer(db, w)

    steps, skipped, _ = propose_rows(db, w, [row_(a.phone_number, add=[t.name]), row_(local(a.phone_number), add=[t.name])])

    assert len(steps) == 1 and "Same as row 1" in reason_of(skipped, 2)


# ------------------------------------------------------------------ T8 (08) the code-built tables


def test_08_the_reply_is_the_code_built_tables_with_tag_wording(db):
    w = make_world(db)
    s = stem()
    ready = tag_(db, f"{s} Office Staff")
    tag_(db, f"{s} Retail Salesperson")
    tag_(db, f"{s} Project Salesperson")
    a, b, c = dealer(db, w), dealer(db, w), dealer(db, w)
    rows = [
        numbered(row_(a.phone_number, add=[ready.name]), 1),
        numbered(row_(b.phone_number, add=["salesperson"]), 2),
        numbered(row_(c.phone_number, add=[f"{s} Gold"]), 3),
    ]

    result = say(db, w, rows, "tag these people", final="SENTINEL MODEL TEXT")

    reply = result.reply_text
    assert reply.startswith("Rows from your table: 1 ready to confirm, 1 need your choice, 1 not changed.")
    assert "SENTINEL" not in reply
    for heading in (READY, NEEDS, NOT_CHANGED):
        assert reply.count(heading) == 1
    needs = reply[reply.index(NEEDS):reply.index(NOT_CHANGED)]
    assert "| Tag |" in needs and "| Account |" not in needs
    assert reply.rstrip().endswith(f"{TAG_TAIL} Or reply yes to confirm the ready rows now.")


def test_08_the_grant_wording_is_unchanged():
    from app.services.chatbot.agent import batch

    wait = {"row": 1, "cells": {"Phone": "+60190000000"}, "written": "X", "company": "MCH", "more": False,
            "candidates": [{"code": "C1", "name": "N1"}]}
    block = batch.preview_block([], [], [wait])
    assert "| Account |" in block and "C1 N1" in block
    assert block.endswith("Reply with the account code(s) for each row under Needs your choice, all, or skip.")


# ------------------------------------------------------------------ T9 (09) not-found wording is backed


def test_09_a_no_tag_named_skip_backs_the_claim_for_that_term_only():
    from app.services.chatbot.agent import batch
    from app.services.chatbot.agent.loop import _not_found_backed

    def backed(what: str) -> bool:
        ledger = {"b1": {"name": batch.BATCH, "status": "invalid", "args": {},
                         "data": {"skipped": [{"row": 1, "reason": 'No tag named "ZZT Gold".'}]}}}
        return _not_found_backed(what, "b1", ledger, set())

    assert backed("ZZT Gold") is True
    assert backed('No tag named "ZZT Gold"') is True
    assert backed("ZZT Silver") is False


# ------------------------------------------------------------------ fix round 1 (crew live x3 + reviewer + security)


def _operator(db, w, slugs=(EDIT,)):
    import dataclasses

    from app.models.company import UserCompany
    from tests.chatbot.agent._seed import seed_user

    operator = seed_user(db, contact_pk=None, slugs=slugs)
    for company_id in (w.srt, w.mch):
        db.add(UserCompany(user_id=operator, company_id=company_id))
    db.commit()
    return operator, dataclasses.replace(ctx_of(db, w), operator_user_id=operator)


def test_r1_a_remove_row_whose_tag_is_already_gone_says_not_tagged(db):
    w = make_world(db)
    t = tag_(db, f"{stem()} Project Salesperson")
    person = dealer(db, w)

    steps, skipped, _ = propose_rows(db, w, [row_(person.phone_number, remove=[t.name])])

    assert steps == [] and reason_of(skipped, 1) == "Not tagged; nothing to remove."


def test_r1_the_agent_audit_row_names_the_tags_before_and_after(db):
    w = make_world(db)
    keep = tag_(db, f"{stem()} Office Staff")
    new = tag_(db, f"{stem()} Retail Salesperson")
    person = dealer(db, w)
    hold(db, person, keep)

    steps, _, _ = propose_rows(db, w, [row_(person.phone_number, add=[new.name])])
    assert confirm(db, w, steps).status == "executed"

    row = db.query(AuditLog).filter(AuditLog.entity_id == str(person.id), AuditLog.event == EVENT).one()
    assert row.old_values["Tags"] == [keep.name]
    assert sorted(row.new_values["Tags"]) == sorted([keep.name, new.name])
    assert str(keep.id) not in str(row.old_values) and str(new.id) not in str(row.new_values)


def test_r1_every_table_starts_with_number_phone_name_whatever_the_stored_key_order():
    from app.services.chatbot.agent import batch

    step = {"row": 1, "summary": "s", "cells": {"Will change": "add tag X", "Name": "N", "Phone": "+60190000001"}}
    wait = {"row": 2, "cells": {"Name": "N", "Phone": "+60190000002"}, "written": "x", "company": "", "noun": "tag",
            "more": False, "candidates": [{"code": "X", "name": ""}]}
    skip = {"row": 3, "reason": "r", "cells": {"Name": "N", "Phone": "+60190000003"}}

    block = batch.preview_block([step], [skip], [wait])

    heads = [line for line in block.splitlines() if line.startswith("| #")]
    assert len(heads) == 3
    for head in heads:
        assert head.startswith("| # | Phone | Name |"), head


def test_r1_settings_edited_after_the_preview_fail_that_row_and_the_other_applies(db):
    w = make_world(db)
    t = tag_(db, f"{stem()} Office Staff", {"chatbot": {"chatbot_stock_allowed": False}})
    a, b = dealer(db, w), dealer(db, w)
    for c in (a, b):
        fresh(db, c).chatbot_stock_allowed = True
    db.commit()
    other = tag_(db, f"{stem()} Plain")

    steps, skipped, _ = propose_rows(db, w, [row_(a.phone_number, add=[t.name]), row_(b.phone_number, add=[other.name])])
    assert skipped == [] and len(steps) == 2
    row = db.get(ContactTag, str(t.id))
    row.settings = {"chatbot": {"chatbot_stock_allowed": True}}  # an admin edits the tag after the preview
    db.commit()

    outcome = confirm(db, w, steps)
    assert outcome.status == "partial", outcome.steps
    assert held(db, a) == [] and fresh(db, a).chatbot_stock_allowed is True
    assert held(db, b) == [other.name]


def test_r1_a_console_operator_without_the_agents_gate_leaves_agents_not_applied(db):
    from app.services.chatbot.agent import actions, batch
    from app.services.contact_tag_settings import SECTION_TITLES

    w = make_world(db)  # the linked user: superadmin with the agents slug
    operator, ctx = _operator(db, w)
    agent = AccessAgent(code=f"zzt_{uuid.uuid4().hex[:8]}", name="ZZT agent")
    db.add(agent)
    db.flush()
    t = tag_(db, f"{stem()} Dealer", {"chatbot": {"chatbot_stock_allowed": False}, "agents": {str(agent.id): True}})
    person = dealer(db, w)
    fresh(db, person).chatbot_stock_allowed = True
    db.commit()

    steps, skipped, _ = batch.propose_rows(db, ctx, TAGS, [row_(person.phone_number, add=[t.name])], seen_ids=set())
    assert skipped == []
    assert f"not applied (needs more access): {SECTION_TITLES['agents']}" in steps[0]["summary"]
    action = store(db, w, steps)
    outcome = actions.confirm(db, w.respond_id, str(action.id), via="console", operator_user_id=operator)

    assert outcome.status == "executed", outcome.steps
    assert fresh(db, person).chatbot_stock_allowed is False
    assert db.query(ContactAgentAccess).filter(ContactAgentAccess.respond_contact_id == str(person.id)).count() == 0


def test_r1_a_failed_settings_write_is_reported_as_not_saved_not_as_done(db):
    from sqlalchemy import text

    w = make_world(db)
    t = tag_(db, f"{stem()} Office Staff", {"chatbot": {"chatbot_stock_allowed": False}})
    person = dealer(db, w)
    fresh(db, person).chatbot_stock_allowed = True
    db.commit()
    steps, _, _ = propose_rows(db, w, [row_(person.phone_number, add=[t.name])])
    db.execute(text("CREATE FUNCTION zzt_boom_tags() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'zzt boom'; END $$"))
    db.execute(text(
        f"CREATE TRIGGER zzt_boom_tags BEFORE UPDATE ON respond_contacts FOR EACH ROW "
        f"WHEN (OLD.id = '{person.id}') EXECUTE FUNCTION zzt_boom_tags()"
    ))
    db.commit()

    outcome = confirm(db, w, steps)

    db.execute(text("DROP TRIGGER zzt_boom_tags ON respond_contacts"))
    db.commit()
    afters = [c["after"] for c in outcome.steps[0]["changes"]]
    assert any("settings not saved" in a for a in afters)
    assert not any(a.startswith("settings: ") for a in afters)
    assert held(db, person) == [t.name]  # the screen's service keeps the membership
    assert fresh(db, person).chatbot_stock_allowed is True


def test_r1_two_tags_that_differ_only_in_inner_spaces_are_never_picked_at_random(db):
    w = make_world(db)
    s = stem()
    one = tag_(db, f"{s} Office Staff")
    tag_(db, f"{s} Office  Staff")  # differs only in an inner space
    person = dealer(db, w)

    steps, _, _ = propose_rows(db, w, [row_(person.phone_number, add=[one.name])])
    assert steps[0]["before"]["targets"] == [str(one.id)]

    double = f"{s} Office  Staff"
    two = db.query(ContactTag).filter(ContactTag.name == double).one()
    steps, _, _ = propose_rows(db, w, [row_(person.phone_number, add=[double.upper()])])
    assert steps[0]["before"]["targets"] == [str(two.id)]  # the summary collapses spaces; the target does not

    steps, _, waiting = propose_rows(db, w, [row_(person.phone_number, add=[f"{s} Office   Staff"])])
    assert steps == [] and sorted(c["code"] for c in waiting[0]["candidates"]) == sorted([one.name, double])


def test_r1_the_name_is_the_crm_contacts_with_the_tables_when_they_differ(db):
    w = make_world(db)
    t = tag_(db, f"{stem()} Office Staff")
    person = dealer(db, w, name="ZZT Siti")

    same, _, _ = propose_rows(db, w, [row_(person.phone_number, name="zzt siti", add=[t.name])])
    other, _, _ = propose_rows(db, w, [row_(person.phone_number, name="ZZT Ahmad", add=[t.name])])

    assert same[0]["cells"]["Name"] == "ZZT Siti"
    assert other[0]["cells"]["Name"] == "ZZT Siti (table says ZZT Ahmad)"


def test_r1_a_user_who_may_not_list_contacts_gets_no_tag_candidates(db):
    w = make_world(db, slugs=(EDIT,), superadmin=False)  # contacts.edit without contacts.view
    s = stem()
    tag_(db, f"{s} Retail Salesperson")
    tag_(db, f"{s} Project Salesperson")
    person = dealer(db, w)

    steps, skipped, waiting = propose_rows(db, w, [row_(person.phone_number, add=["salesperson"])])

    assert steps == [] and waiting == []
    reason = reason_of(skipped, 1)
    assert reason == 'No tag named "salesperson".' and "Retail" not in reason


# ------------------------------------------------------------------ after #2250: decided tag rows stay closed


def test_r2_a_cancelled_tag_card_does_not_bring_its_rows_back_on_the_next_table(db):
    from app.services.chatbot.agent import actions, batch

    w = make_world(db)
    t = tag_(db, f"{stem()} Office Staff")
    a, b, c = dealer(db, w), dealer(db, w), dealer(db, w)
    first = say(db, w, [numbered(row_(a.phone_number, add=[t.name]), 1), numbered(row_(b.phone_number, add=[t.name]), 2)],
                "tag these two")
    actions.cancel(db, w.respond_id, first.pending_action["id"])

    rows = [numbered(row_(x.phone_number, add=[t.name]), n) for n, x in enumerate((a, b, c), 1)]
    second = say(db, w, rows, "and tag the third one too")

    step_rows = [s["row"] for s in action_rows(db, w.respond_id)[-1].steps]
    assert step_rows == [3]
    assert second.reply_text.count(batch.CLOSED_CANCELLED) == 2
    assert held(db, a) == [] and held(db, b) == [] and held(db, c) == []
