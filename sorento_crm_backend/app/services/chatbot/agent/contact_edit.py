"""`crm_contact_edit`: one row of a pasted table edits a contact, found by its phone, as the user
(AGENT-BULK-W4-CONTACTS).

PLAN-agent-bulk-w4-contacts-8nov.md. Owner answers (8 Nov, all recommendations): the row edits the contact's Name,
the sponsorship switch ("Sponsorship must name a registered project") and the Respond.io Workspace, the Edit Contact
form's own fields that no other agent write owns (tags, access types, companies and links have theirs); the phone is
the key only and never changes; a phone held by two contacts is refused (the W1 rule, `contact_grant._find_contact`);
an unknown phone is not found and never created; a blank cell leaves its field as it is and nothing is cleared; only
`user_management.contacts.edit` (the screen's slug, `contacts.py:401`). The change goes through the screen's service
(`ContactService.update_contact`), so its checks and the contact's audit listener apply; one extra audit row per
changed contact names the pasted table. `read_before` refuses (4xx) a row that cannot apply; the batch tool shows
that message as the row's skip reason. Nothing is sent to Respond.io (the screen's save sends nothing either).
"""
from __future__ import annotations

from typing import Any

from app.services.chatbot.agent import writes
from app.services.chatbot.agent.contact_grant import _clean, _find_contact, _refuse

WRITE = "crm_contact_edit"
EDIT = writes.CONTACT_EDIT
EVENT = "contact.edit_agent"
NOTHING = "Nothing to change."
GIVE_ONE = "Give a name, the sponsorship rule or the workspace to change."
OWN = "That is your own contact; change it on the contacts screen."
#: The Edit Contact form's workspace picker reads `/system/respond-workspaces/select` (this slug); without it the
#: picker is empty, so the cell is refused with one message whatever the name (security review S2).
WORKSPACE_VIEW = "system.respond_workspaces.view"
NO_WORKSPACE = "You cannot change a contact's Respond.io workspace."


def _workspace_label(ws) -> str:
    """The workspace as the Edit Contact form lists it."""
    if ws is None:
        return "none"
    return ws.name.strip() if (ws.name or "").strip() else f"Workspace {ws.space_id}"


def _workspace(db, written: str, problems: list[str]):
    """The workspace whose name (case and spaces aside) or space id is exactly what the row wrote."""
    from sqlalchemy import func, or_

    from app.models.respond_workspace import RespondWorkspace

    norm = func.lower(func.regexp_replace(func.trim(func.coalesce(RespondWorkspace.name, "")), r"\s+", " ", "g"))
    # Active only: the screen's picker lists active workspaces (`list_active_select`); an inactive one is not found.
    rows = db.query(RespondWorkspace).filter(
        RespondWorkspace.is_active.is_(True),
        or_(norm == written.lower(), func.lower(func.trim(RespondWorkspace.space_id)) == written.lower()),
    ).order_by(RespondWorkspace.id).limit(2).all()
    if not rows:
        problems.append(f'No Respond.io workspace named "{written}".')
        return None
    if len(rows) > 1:
        problems.append(f'More than one Respond.io workspace is named "{written}"; give its space id.')
        return None
    return rows[0]


def _is_own(db, user: dict, contact_id: str) -> bool:
    from app.models.user import User

    acting = [i for i in (user.get("id"), user.get("operator_user_id")) if i]
    return db.query(User.id).filter(User.id.in_([str(i) for i in acting]), User.respond_contact_id == contact_id).first() is not None


def plan(db, user: dict, args: dict) -> dict:
    """What the row would change, after every check. Raises the refusal the preview shows otherwise."""
    from app.models.respond_workspace import RespondWorkspace
    from app.services import contact_setup_engine as engine

    problems: list[str] = []
    phone = engine.normalise_phone(args.get("phone"))
    if phone is None:
        problems.append(f"Phone \"{_clean(args.get('phone'))}\" is not a Malaysian mobile number.")
    name = _clean(args.get("name"))[:255]
    rule = args.get("sponsorship_registered_project")
    rule = rule if isinstance(rule, bool) else None
    said_ws = _clean(args.get("workspace"))
    workspace = None
    if said_ws:
        acting = [str(i) for i in (user.get("id"), user.get("operator_user_id")) if i]
        if all(writes.holds(db, i, WORKSPACE_VIEW) for i in acting):
            workspace = _workspace(db, said_ws, problems)
        else:
            problems.append(NO_WORKSPACE)
    if problems:
        raise _refuse("; ".join(p.rstrip(".") for p in problems) + ".")
    contact = _find_contact(db, phone)
    if contact is None:
        raise _refuse(f"No contact with the phone {phone}.")
    cid = str(contact.id)
    if _is_own(db, user, cid):
        raise _refuse(OWN)
    if not name and rule is None and workspace is None:
        raise _refuse(GIVE_ONE)

    fields: dict[str, Any] = {}
    lines: list[str] = []
    old: dict[str, str] = {}
    new: dict[str, str] = {}
    # Spacing alone is the same name; capitals compare exactly, so a lowercase WhatsApp name can be fixed (crew ruling
    # 8 Nov, option b). The card shows every rename before Confirm.
    if name and name != _clean(contact.name):
        fields["name"] = name
        lines.append(f'name "{_clean(contact.name)}" -> "{name}"')
        old["Name"], new["Name"] = _clean(contact.name) or "none", name
    held_rule = bool(contact.requires_registered_project)
    if rule is not None and rule != held_rule:
        fields["requires_registered_project"] = rule
        words = {True: "on", False: "off"}
        lines.append(f"sponsorship rule {words[held_rule]} -> {words[rule]}")
        old["Sponsorship rule"], new["Sponsorship rule"] = words[held_rule], words[rule]
    held_ws = db.get(RespondWorkspace, str(contact.workspace_id)) if contact.workspace_id else None
    if workspace is not None and str(workspace.id) != str(contact.workspace_id or ""):
        fields["workspace_id"] = str(workspace.id)
        lines.append(f"workspace {_workspace_label(held_ws)} -> {_workspace_label(workspace)}")
        old["Workspace"], new["Workspace"] = _workspace_label(held_ws), _workspace_label(workspace)
    if not fields:
        raise _refuse(NOTHING)
    return {
        "contact_id": cid, "phone": contact.phone_number, "name": _clean(contact.name),
        "fields": fields, "lines": lines, "old": old, "new": new,
        "before": {
            "contact_id": cid,
            "name": contact.name,
            "requires_registered_project": held_rule,
            "workspace_id": str(contact.workspace_id) if contact.workspace_id else None,
            # The workspace the card names: a rename or swap before Confirm fails the row (security review N1).
            "to_workspace_id": fields.get("workspace_id"),
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
    from app.schemas.user import RespondContactUpdate
    from app.services import audit_service
    from app.services.contact_service import ContactService

    p = plan(db, user, args)
    # The pasted-table audit row first, so the service's single commit writes it with the change (review N2).
    audit_service.record(
        db,
        event=EVENT,
        entity_type="respond_contacts",
        entity_id=p["contact_id"],
        old_values=p["old"],
        new_values=p["new"],
        description=f"Agent contact edit for {p['phone']} from a pasted table",
    )
    # The Edit Contact screen's service: its checks, its commit, and the contact listener's before / after row.
    ContactService(db).update_contact(p["contact_id"], RespondContactUpdate(**p["fields"]))
    return {"id": p["contact_id"], "after": {"old": p["old"], "new": p["new"]}}


def _changes(args: dict, before: dict, after: dict, shown: dict) -> list[dict]:
    record = f"{shown.get('phone') or ''} {shown.get('name') or ''}".strip()
    old, new = after.get("old") or {}, after.get("new") or {}
    return [{"record": record, "field": f, "before": old.get(f, ""), "after": new[f]} for f in new]


_TEXT = {"type": "string"}

writes.WRITES[WRITE] = writes.WriteDef(
    name=WRITE,
    user_permission=EDIT,
    schema={
        "type": "function",
        "function": {
            "name": WRITE,
            "description": (
                "Edit one contact from a row of a pasted table: its name, whether its sponsorship forms must name a "
                "registered project, and its Respond.io workspace. The contact is found by its phone, which never "
                "changes here; a phone not in the CRM is not created. For a table, use crm_batch_propose with this "
                "write and one row per contact. Use the table's values as written; leave out a column the table "
                "does not have or leaves blank (nothing is cleared here). Tags, access, companies and customer links "
                "are other writes. Nothing changes until the user confirms."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "phone": {**_TEXT, "description": "The contact's phone number exactly as in the table."},
                    "name": {**_TEXT, "description": "The contact's new name from the table, if the table has one."},
                    "sponsorship_registered_project": {
                        "type": "boolean",
                        "description": (
                            "True when the table says the contact's sponsorship forms must name a registered project, "
                            "false when it says they need not. Leave out when the table does not say."
                        ),
                    },
                    "workspace": {**_TEXT, "description": "The Respond.io workspace's name or space id as in the table."},
                },
                # No `required`: a row without a phone is listed as Not changed with the reason.
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
