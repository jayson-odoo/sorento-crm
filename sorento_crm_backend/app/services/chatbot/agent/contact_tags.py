"""`crm_contact_tags`: one row of a pasted table adds / removes contact tags, applied as the user (AGENT-BULK-W2-TAGS).

PLAN-agent-bulk-w2-tags-8nov.md. The row names its contact by phone only (the #2241 lookup, both stored forms) and
its tags by EXACT name (case and spaces aside); a name that is not a tag but sits inside active tag names makes the row
wait for the user's pick (`contact_grant.NeedsChoice`), nothing is auto-picked. The change is the bulk-tag dialog's,
through the same service (`ContactTagService.bulk_tag`): membership, plus the ADDED tags' settings applied
(`contact_tag_apply.apply_settings`, the dialog's default), each setting section gated as on screen and limited to
what both the linked user and the console operator may write. Removing a tag leaves settings as they are (screen
rule). A tag row never creates a contact or a tag. `read_before` refuses (4xx) a row that cannot apply; the batch tool
shows that message as the row's skip reason.
"""
from __future__ import annotations

from typing import Any, Callable

from app.services.chatbot.agent import writes
from app.services.chatbot.agent.contact_grant import NeedsChoice, _clean, _find_contact, _fits, _refuse

TAGS = "crm_contact_tags"
EDIT = writes.CONTACT_EDIT
EVENT = "contact.tags_agent"
MAX_TAGS = 10
MAX_CHOICES = 10
NOT_APPLIED = "not applied (needs more access)"


def _fold(text: Any) -> str:
    return _clean(text).lower()


def _gates(db, user: dict) -> tuple[Callable[[str], bool], Callable[[], bool]]:
    """(can, is_superadmin) of the tag screens (`contact_tags._gates`), true only when EVERY acting person passes: the
    linked user and the console operator (the #2241 rule, security review B1)."""
    from app.api.v1.system.companies import _is_superadmin
    from app.services.user_service import UserPermissionService

    perms = UserPermissionService(db)
    acting = list(dict.fromkeys(i for i in (str(user["id"]), user.get("operator_user_id")) if i))
    return (
        lambda slug: all(perms.check_user_has_permission(i, slug) for i in acting),
        lambda: all(_is_superadmin(db, i) for i in acting),
    )


def _resolve(db, written: list[str], problems: list[str], choices: list[dict], kept: list[str]) -> dict[str, Any]:
    """{tag id: tag} for the names written; a name that is not exact records a problem or a choice."""
    from sqlalchemy import func

    from app.models.access import ContactTag

    norm = func.lower(func.regexp_replace(func.trim(ContactTag.name), r"\s+", " ", "g"))
    out: dict[str, Any] = {}
    for name in dict.fromkeys(_clean(n) for n in written):
        if not name:
            continue
        exact = db.query(ContactTag).filter(norm == name.lower()).first()
        if exact is not None:
            if not exact.is_active:
                problems.append(f'Tag "{exact.name}" is inactive.')
            else:
                out[str(exact.id)] = exact
                kept.append(_fold(exact.name))
            continue
        found = (
            db.query(ContactTag.name)
            .filter(ContactTag.is_active.is_(True), func.strpos(norm, name.lower()) > 0)
            .order_by(func.lower(ContactTag.name))
            .limit(MAX_CHOICES + 1)
            .all()
        )
        if found:
            choices.append({
                "written": name, "company": "", "noun": "tag",
                "candidates": [{"code": n, "name": ""} for (n,) in found[:MAX_CHOICES]],
                "more": len(found) > MAX_CHOICES,
            })
        else:
            problems.append(f'No tag named "{name}".')
    return out


def _texts(value: Any) -> list[str]:
    return [str(v) for v in value] if isinstance(value, list) else []


def plan(db, user: dict, args: dict) -> dict:
    """What the row would change, after every check (a dry run of the screen's bulk tag). Raises the refusal the
    preview shows otherwise."""
    from app.services import contact_setup_engine as engine
    from app.services.contact_tag_service import ContactTagService, tags_by_contact

    problems: list[str] = []
    choices: list[dict] = []
    kept: list[str] = []
    said_phone = _clean(args.get("phone"))
    phone = engine.normalise_phone(args.get("phone")) if said_phone else None
    if not said_phone:
        problems.append("Give the phone.")
    elif phone is None:
        problems.append(f'Phone "{said_phone}" is not a Malaysian mobile number.')
    add_written, remove_written = _texts(args.get("tags_add")), _texts(args.get("tags_remove"))
    if not any(_clean(n) for n in add_written + remove_written):
        problems.append("Name the tag(s) to add or remove.")
    add = _resolve(db, add_written, problems, choices, kept)
    remove = _resolve(db, remove_written, problems, choices, kept)
    for tag_id in add.keys() & remove.keys():
        problems.append(f'Tag "{add[tag_id].name}" is both added and removed.')
    contact = None
    if phone is not None:
        contact = _find_contact(db, phone)
        if contact is None:
            problems.append(f'No contact has the phone "{said_phone}"; add the contact first.')
    if problems:
        problems += [_fits(c) for c in choices]
        raise _refuse("; ".join(p.rstrip(".") for p in problems) + ".")
    if choices:
        for c in choices:
            c["kept"] = kept
        raise NeedsChoice(choices)

    cid = str(contact.id)
    result = ContactTagService(db).bulk_tag(
        [cid], list(add), list(remove), True, str(user["id"]), apply_settings=bool(add), gates=_gates(db, user),
    )["results"][0]
    settings = result.get("settings") or {}
    current = {t["id"] for t in tags_by_contact(db, [cid]).get(cid, [])}
    lines = [f"add tag {t.name}" for i, t in add.items() if i not in current]
    lines += [f"remove tag {t.name}" for i, t in remove.items() if i in current]
    changed = list(dict.fromkeys(c["label"] for c in settings.get("changes") or []))
    if changed:
        lines.append("settings: " + ", ".join(changed))
    blocked = list(dict.fromkeys(n["label"] for n in settings.get("not_applied") or []))
    conflicts = list(dict.fromkeys(c["label"] for c in settings.get("conflicts") or []))
    if not lines:
        extra = f"; {NOT_APPLIED}: {', '.join(blocked)}" if blocked else ""
        raise _refuse(f"Already tagged; nothing to change{extra}.")
    if blocked:
        lines.append(f"{NOT_APPLIED}: " + ", ".join(blocked))
    if conflicts:
        lines.append("tags disagree, not changed: " + ", ".join(conflicts))
    return {
        "phone": phone, "name": _clean(args.get("name"))[:255] or contact.name or "", "contact_id": cid,
        "add": add, "remove": remove, "lines": lines,
        "before": {
            "contact_id": cid, "tags": sorted(current), "targets": sorted(add) + sorted(remove),
            # The setting changes the user saw: a tag edited between preview and confirm fails the row.
            "settings": [[c["label"], str(c["before"]), str(c["after"])] for c in settings.get("changes") or []],
        },
    }


def _read_before(db, user: dict, args: dict) -> dict:
    p = plan(db, user, args)
    return {**p["before"], "_show": {"phone": p["phone"], "name": p["name"], "changes": p["lines"]}}


def _summary(args: dict, before: dict) -> str:
    who = f"{writes._line(before['phone'])} {writes._line(before['name'])}".strip()
    return f"{who}: " + "; ".join(writes._line(c) for c in before["changes"])


def _preview(args: dict, shown: dict | None) -> dict:
    if shown is None:
        return {"Phone": _clean(args.get("phone")), "Name": _clean(args.get("name"))}
    return {"Phone": shown.get("phone") or "", "Name": shown.get("name") or "",
            "Will change": "; ".join(shown.get("changes") or [])}


def _batch_key(args: dict) -> str | None:
    from app.services.contact_setup_engine import normalise_phone

    return normalise_phone(args.get("phone")) if isinstance(args, dict) else None


def _execute(db, user: dict, args: dict) -> dict:
    from app.services import audit_service
    from app.services.contact_tag_service import ContactTagService

    p = plan(db, user, args)
    cid = p["contact_id"]
    # Recorded first: the screen's service commits the membership, its own audit rows and this row together.
    audit_service.record(
        db,
        event=EVENT,
        entity_type="respond_contacts",
        entity_id=cid,
        old_values={"Tags": p["before"]["tags"]},
        new_values={"Changes": p["lines"]},
        description=f"Agent tag change for {p['phone']} from a pasted table",
    )
    ContactTagService(db).bulk_tag(
        [cid], list(p["add"]), list(p["remove"]), False, str(user["id"]),
        apply_settings=bool(p["add"]), gates=_gates(db, user),
    )
    db.commit()
    return {"id": cid, "after": {"changes": p["lines"]}}


def _changes(args: dict, before: dict, after: dict, shown: dict) -> list[dict]:
    record = f"{shown.get('phone') or ''} {shown.get('name') or ''}".strip()
    return [{"record": record, "field": "Tags", "before": "", "after": c} for c in after.get("changes") or []]


_NAMES = {"type": "array", "items": {"type": "string"}, "maxItems": MAX_TAGS}

writes.WRITES[TAGS] = writes.WriteDef(
    name=TAGS,
    user_permission=EDIT,
    schema={
        "type": "function",
        "function": {
            "name": TAGS,
            "description": (
                "Add and / or remove contact tags for one contact, from a row of a pasted table. Adding a tag also "
                "applies the tag's settings, as the contacts screen does. The contact is found by phone; a tag by its "
                "name. For a table, use crm_batch_propose with this write and one row per contact. Use the table's "
                "values as written: never invent a phone or a tag name. Nothing changes until the user confirms."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "phone": {"type": "string", "description": "The contact's phone exactly as in the table."},
                    "name": {"type": "string", "description": "The contact's name from the table."},
                    "tags_add": {**_NAMES, "description": "Tag names to add, as written in the table."},
                    "tags_remove": {**_NAMES, "description": "Tag names to remove, as written in the table."},
                },
                # No `required`: a row without a phone is listed as Not changed "Give the phone" (crew Q3).
            },
        },
    },
    read_before=_read_before,
    summary=_summary,
    execute=_execute,
    record_key="",
    changes=_changes,
    batchable=True,
    preview=_preview,
    batch_key=_batch_key,
)
