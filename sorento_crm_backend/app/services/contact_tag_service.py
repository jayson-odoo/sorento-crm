"""Contact tag catalog and tagging (CONTACT-TAGS S1).

Tags are labels staff put on contacts. No code path here (or in sync, the external upsert or
create_contact) assigns a tag on its own; the agent's dealer access tools add or remove the two
Business owner tags (`owner_tag`, `change_tags`) when a user sets that level.
"""
from __future__ import annotations

import uuid
from typing import Iterable, Optional

from sqlalchemy import and_, delete, func, insert, select
from sqlalchemy.orm import Session

from app.models.access import ContactTag, RespondContact, respond_contact_tags
from app.services.error_handler import handle_conflict, handle_not_found, handle_unprocessable

_ORDER = (ContactTag.sort_order.asc(), ContactTag.name.asc())


def tags_by_contact(db: Session, contact_ids: Iterable[str]) -> dict[str, list[dict]]:
    """`{contact_id: [{id, name}]}` ordered by tag sort_order then name; one query for the page."""
    ids = [str(i) for i in contact_ids]
    if not ids:
        return {}
    rows = db.execute(
        select(respond_contact_tags.c.contact_id, ContactTag.id, ContactTag.name)
        .join(ContactTag, ContactTag.id == respond_contact_tags.c.tag_id)
        .where(respond_contact_tags.c.contact_id.in_(ids))
        .order_by(*_ORDER)
    ).all()
    out: dict[str, list[dict]] = {}
    for contact_id, tag_id, name in rows:
        out.setdefault(str(contact_id), []).append({"id": str(tag_id), "name": name})
    return out


def owner_tag(db: Session, company_code: str) -> Optional[ContactTag]:
    """The active Business owner tag of the company (`TEMPLATE["owner_tags"]`, name matched case-insensitively);
    None when it is missing, switched off, or sets anything but exactly the company's template owner types (UAC A15:
    an edited tag never grants more than the template)."""
    from app.services.contact_access_sheet_service import TEMPLATE

    name = TEMPLATE["owner_tags"].get(company_code)
    if not name:
        return None
    tag = (
        db.query(ContactTag)
        .filter(func.lower(ContactTag.name) == name.lower(), ContactTag.is_active.is_(True))
        .order_by(ContactTag.id)
        .first()
    )
    settings = (tag.settings or {}) if tag is not None else {}
    types = settings.get("access_types")
    if set(settings) != {"access_types"} or not isinstance(types, list):
        return None
    return tag if set(types) == set(TEMPLATE["owner_types"][company_code]) else None


def change_tags(
    db: Session, contact: RespondContact, *, add=(), remove=(), actor_id: Optional[str] = None
) -> None:
    """Add and remove tags on ONE contact inside the caller's transaction (no commit, no gates: the caller decided),
    then recompute what the changed tags set (TAG-UNION). A tag already held is not added again; one not held is
    not removed."""
    from app.services import contact_tag_union

    cid = str(contact.id)
    held = {t["id"] for t in tags_by_contact(db, [cid]).get(cid, [])}
    to_add = [t for t in dict.fromkeys(add) if str(t.id) not in held]
    to_remove = [t for t in dict.fromkeys(remove) if str(t.id) in held]
    if not (to_add or to_remove):
        return
    contact_tag_union.ensure_seeded(db, [contact])
    for tag in to_remove:
        db.execute(delete(respond_contact_tags).where(
            and_(respond_contact_tags.c.contact_id == cid, respond_contact_tags.c.tag_id == str(tag.id))
        ))
    if to_add:
        db.execute(
            insert(respond_contact_tags),
            [{"contact_id": cid, "tag_id": str(t.id), "created_by": actor_id} for t in to_add],
        )
    service = ContactTagService(db)
    for tag in to_remove:
        service._audit_membership(cid, tag.name, False, actor_id)
    for tag in to_add:
        service._audit_membership(cid, tag.name, True, actor_id)
    db.flush()
    changed = [*to_add, *to_remove]
    contact_tag_union.recompute(
        db, [contact], keys=_keys(t for t in changed if t.is_active), actor_id=actor_id,
        trigger="Tags changed: " + ", ".join(sorted(t.name for t in changed)),
    )


class ContactTagService:
    def __init__(self, db: Session):
        self.db = db

    # ---------------------------------------------------------------- catalog
    def _counts(self, tag_ids: list[str]) -> dict[str, int]:
        if not tag_ids:
            return {}
        rows = self.db.execute(
            select(respond_contact_tags.c.tag_id, func.count())
            .where(respond_contact_tags.c.tag_id.in_(tag_ids))
            .group_by(respond_contact_tags.c.tag_id)
        ).all()
        return {str(t): int(n) for t, n in rows}

    def _with_count(self, tags: list[ContactTag], counts_on: bool = True) -> list[dict]:
        from app.services import contact_tag_settings as cts

        counts = self._counts([str(t.id) for t in tags])
        return [
            {
                "id": str(t.id),
                "name": t.name,
                "description": t.description,
                "is_active": t.is_active,
                "sort_order": t.sort_order,
                "settings": t.settings or {},
                "contact_count": counts.get(str(t.id), 0),
                "differs_count": self._differs(cts, t, counts_on),
                "created_at": t.created_at,
                "updated_at": t.updated_at,
            }
            for t in tags
        ]

    def _differs(self, cts, tag: ContactTag, counts_on: bool) -> Optional[int]:
        """Holders whose status differs on this tag's keys; null when not asked for or too many to evaluate."""
        if not counts_on:
            return None
        if not cts.leaves_of(tag.settings):
            return 0
        return cts.differs_count(self.db, str(tag.id))

    _SORTABLE = {
        "name": ContactTag.name,
        "sort_order": ContactTag.sort_order,
        "is_active": ContactTag.is_active,
        "created_at": ContactTag.created_at,
    }

    def list_tags(
        self,
        page: int,
        limit: int,
        search: Optional[str],
        is_active: Optional[bool],
        sort: Optional[str] = None,
        direction: Optional[str] = None,
        counts: bool = True,
    ):
        q = self.db.query(ContactTag)
        if search and search.strip():
            q = q.filter(ContactTag.name.ilike(f"%{search.strip()}%"))
        if is_active is not None:
            q = q.filter(ContactTag.is_active.is_(is_active))
        total = q.count()
        column = self._SORTABLE.get(sort or "")
        order = _ORDER
        if column is not None:
            order = (column.desc() if direction == "desc" else column.asc(), ContactTag.name.asc())
        rows = q.order_by(*order).offset((page - 1) * limit).limit(limit).all()
        return self._with_count(rows, counts), total

    def get_tag(self, tag_id: str) -> ContactTag:
        row = self._find(tag_id)
        if row is None:
            raise handle_not_found("Contact tag", tag_id)
        return row

    def _find(self, tag_id: str) -> Optional[ContactTag]:
        try:
            key = str(uuid.UUID(str(tag_id)))
        except ValueError:
            return None  # a malformed id cannot be a tag
        return self.db.query(ContactTag).filter(ContactTag.id == key).first()

    def get_tag_dict(self, tag_id: str) -> dict:
        return self._with_count([self.get_tag(tag_id)])[0]

    def _assert_name_free(self, name: str, own_id: Optional[str] = None) -> None:
        clash = self.db.query(ContactTag).filter(func.lower(ContactTag.name) == name.lower()).first()
        if clash is not None and str(clash.id) != str(own_id or ""):
            raise handle_conflict(f'A tag named "{clash.name}" already exists.')

    def _check_settings(self, old: dict, new: dict, gates) -> None:
        """Validate (422) first, then gate (403) the sections that changed."""
        from app.services import contact_tag_settings as cts

        cts.validate_settings(self.db, new)
        if gates is not None:
            cts.assert_gates(old, new, *gates)

    def create_tag(self, data: dict, actor_id: Optional[str], gates=None) -> dict:
        self._assert_name_free(data["name"])
        self._check_settings({}, data.get("settings") or {}, gates)
        row = ContactTag(
            name=data["name"],
            description=data.get("description"),
            is_active=data.get("is_active", True),
            sort_order=data.get("sort_order", 0),
            settings=data.get("settings") or {},
            created_by=actor_id,
            updated_by=actor_id,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return self._with_count([row])[0]

    def update_tag(self, tag_id: str, data: dict, actor_id: Optional[str], gates=None) -> dict:
        from app.services import contact_tag_settings as cts, contact_tag_union

        row = self.get_tag(tag_id)
        old_settings = dict(row.settings or {})
        if data.get("settings") is not None:
            self._check_settings(old_settings, data["settings"], gates)
        toggled = data.get("is_active") is not None and bool(data["is_active"]) != bool(row.is_active)
        if toggled:
            # Switching a tag on grants what it sets to every holder; off takes it away (TAG-UNION D4).
            assert_tag_gates([old_settings, data.get("settings") or {}], gates)
        if data.get("name") is not None:
            self._assert_name_free(data["name"], own_id=str(row.id))
        settings_changed = data.get("settings") is not None and data["settings"] != old_settings
        holders = cts.holders_of(self.db, str(row.id)) if (settings_changed or toggled) else []
        contact_tag_union.ensure_seeded(self.db, holders)  # before the change: the old rule's value
        for key in ("name", "description", "is_active", "sort_order", "settings"):
            if key in data and (data[key] is not None or key == "description"):
                setattr(row, key, data[key])
        row.updated_by = actor_id
        self.db.flush()
        if holders:
            new_settings = row.settings or {}
            if toggled:  # gated above on every section the tag sets, old and new
                keys = contact_tag_union.keys_of(old_settings) | contact_tag_union.keys_of(new_settings)
            else:  # only the sections that changed: exactly what assert_gates checked
                changed = {s for s in set(old_settings) | set(new_settings) if old_settings.get(s) != new_settings.get(s)}
                keys = contact_tag_union.keys_of({s: old_settings[s] for s in changed if s in old_settings}) | (
                    contact_tag_union.keys_of({s: new_settings[s] for s in changed if s in new_settings})
                )
            for chunk in _chunks(holders):
                contact_tag_union.recompute(
                    self.db, chunk, keys=keys, actor_id=actor_id,
                    trigger=f"Tag {'switched ' + ('on' if row.is_active else 'off') if toggled else 'edited'}: {row.name}",
                )
        self.db.commit()
        self.db.refresh(row)
        return self._with_count([row])[0]

    def delete_tag(self, tag_id: str, gates=None, actor_id: Optional[str] = None) -> None:
        """Remove the tag; its contact links go by cascade, and every holder loses what only it granted.

        Deleting clears every section the tag sets, so it needs the same gates as clearing them by PATCH."""
        from app.services import contact_tag_settings as cts, contact_tag_union

        row = self.get_tag(tag_id)
        if gates is not None:
            cts.assert_gates(row.settings or {}, {}, *gates)
        holders = cts.holders_of(self.db, str(row.id)) if row.is_active else []
        contact_tag_union.ensure_seeded(self.db, holders)
        keys, name = contact_tag_union.keys_of(row.settings or {}), row.name
        self.db.execute(delete(ContactTag).where(ContactTag.id == str(row.id)))
        self.db.flush()
        for chunk in _chunks(holders):
            contact_tag_union.recompute(
                self.db, chunk, keys=keys, actor_id=actor_id, trigger=f"Tag deleted: {name}"
            )
        self.db.commit()

    # ---------------------------------------------------------------- tagging
    def _require_tags(self, tag_ids: Iterable[str]) -> dict[str, ContactTag]:
        wanted = list(dict.fromkeys(str(t) for t in tag_ids))
        found: dict[str, ContactTag] = {}
        for tag_id in wanted:
            row = self._find(tag_id)
            if row is None:
                raise handle_unprocessable(f"Unknown tag: {tag_id}")
            found[tag_id] = row
        return found

    def _audit_membership(self, contact_id: str, tag_name: str, added: bool, actor_id: Optional[str]) -> None:
        """One audit row per contact per tag added or removed (the junction writes bypass the ORM listener)."""
        from app.services.audit_service import log_audit

        log_audit(
            self.db,
            "respond_contacts",
            contact_id,
            "UPDATE",
            user_id=actor_id,
            description=f"Tag {'added' if added else 'removed'}: {tag_name}",
        )

    def set_contact_tags(
        self, contact_id: str, tag_ids: list[str], actor_id: Optional[str], gates=None
    ) -> list[dict]:
        from app.services import contact_tag_union

        contact = self.db.query(RespondContact).filter(RespondContact.id == contact_id).first()
        if contact is None:
            raise handle_not_found("Contact", contact_id)
        wanted = self._require_tags(tag_ids)
        before = {t["id"]: t["name"] for t in tags_by_contact(self.db, [contact_id]).get(contact_id, [])}
        changed = [t for t in wanted if t not in before] + [t for t in before if t not in wanted]
        changed_rows = self._require_tags(changed)
        assert_tag_gates([r.settings for r in changed_rows.values() if r.is_active], gates)
        contact_tag_union.ensure_seeded(self.db, [contact])
        self.db.execute(delete(respond_contact_tags).where(respond_contact_tags.c.contact_id == contact_id))
        if wanted:
            self.db.execute(
                insert(respond_contact_tags),
                [{"contact_id": contact_id, "tag_id": t, "created_by": actor_id} for t in wanted],
            )
        for tag_id, name in before.items():
            if tag_id not in wanted:
                self._audit_membership(contact_id, name, False, actor_id)
        for tag_id, row in wanted.items():
            if tag_id not in before:
                self._audit_membership(contact_id, row.name, True, actor_id)
        self.db.flush()
        if changed_rows:
            contact_tag_union.recompute(
                self.db, [contact], keys=_keys(r for r in changed_rows.values() if r.is_active), actor_id=actor_id,
                trigger="Tags changed: " + ", ".join(sorted(r.name for r in changed_rows.values())),
            )
        self.db.commit()
        return tags_by_contact(self.db, [contact_id]).get(contact_id, [])

    def bulk_tag(
        self,
        contact_ids: list[str],
        add_tag_ids: list[str],
        remove_tag_ids: list[str],
        dry_run: bool,
        actor_id: Optional[str],
        apply_settings: bool = False,
        gates=None,
    ) -> dict:
        from app.services import contact_tag_union

        add = self._require_tags(add_tag_ids)
        remove = self._require_tags(remove_tag_ids)
        assert_tag_gates([r.settings for r in {**add, **remove}.values() if r.is_active], gates)
        ids = list(dict.fromkeys(contact_ids))
        contacts = {
            str(c.id): c
            for c in self.db.query(RespondContact).filter(RespondContact.id.in_(ids)).all()
        }
        held = tags_by_contact(self.db, contacts.keys())
        all_names = {t: row.name for t, row in {**add, **remove}.items()}

        results: list[dict] = []
        inserts: list[dict] = []
        deletes: list[tuple[str, str]] = []
        counts = {"changed": 0, "unchanged": 0, "failed": 0}
        for cid in ids:
            contact = contacts.get(cid)
            if contact is None:
                counts["failed"] += 1
                results.append(
                    {"contact_id": cid, "label": cid, "status": "failed", "tags_before": [],
                     "tags_after": [], "error": "Contact not found"}
                )
                continue
            current = {t["id"]: t["name"] for t in held.get(cid, [])}
            after = {k: v for k, v in current.items() if k not in remove}
            for tag_id in add:
                after.setdefault(tag_id, all_names[tag_id])
            to_add = [t for t in add if t not in current]
            to_remove = [t for t in remove if t in current]
            changed = bool(to_add or to_remove)
            counts["changed" if changed else "unchanged"] += 1
            inserts += [{"contact_id": cid, "tag_id": t, "created_by": actor_id} for t in to_add]
            deletes += [(cid, t) for t in to_remove]
            results.append(
                {
                    "contact_id": cid,
                    "label": contact.name or contact.phone_number or cid,
                    "status": "changed" if changed else "unchanged",
                    "tags_before": sorted(current.values()),
                    "tags_after": sorted(after.values()),
                    "error": None,
                }
            )

        def write_tags() -> None:
            for cid, tag_id in deletes:
                self.db.execute(
                    delete(respond_contact_tags).where(
                        and_(respond_contact_tags.c.contact_id == cid, respond_contact_tags.c.tag_id == tag_id)
                    )
                )
            if inserts:
                self.db.execute(insert(respond_contact_tags), inserts)
            names = {**{k: v.name for k, v in add.items()}, **{k: v.name for k, v in remove.items()}}
            for cid, tag_id in deletes:
                self._audit_membership(cid, names[tag_id], False, actor_id)
            for row in inserts:
                self._audit_membership(row["contact_id"], names[row["tag_id"]], True, actor_id)
            self.db.flush()

        # TAG-UNION: a tag change recomputes the settings the changed tags set, always (apply_settings is
        # kept for old callers and no longer decides anything). A preview runs the same change inside a
        # savepoint it then rolls back (preview equals apply).
        touched_ids = list(dict.fromkeys([c for c, _ in deletes] + [r["contact_id"] for r in inserts]))
        touched = [contacts[cid] for cid in touched_ids]
        if inserts or deletes:
            savepoint = self.db.begin_nested()
            try:
                contact_tag_union.ensure_seeded(self.db, touched)
                write_tags()
                rows = contact_tag_union.recompute(
                    self.db, touched, keys=_keys(r for r in {**add, **remove}.values() if r.is_active),
                    actor_id=actor_id, trigger="Tags changed: " + ", ".join(sorted(all_names.values())),
                )
            except Exception:
                savepoint.rollback()
                raise
            if dry_run:
                savepoint.rollback()
                self.db.expire_all()
            else:
                savepoint.commit()
                self.db.commit()
            by_contact = {r["contact_id"]: r for r in rows}
            for r in results:
                r["settings"] = by_contact.get(r["contact_id"])
        return {"dry_run": dry_run, "results": results, "counts": counts}


def _keys(tags) -> set[tuple[str, str]]:
    from app.services import contact_tag_union

    out: set[tuple[str, str]] = set()
    for tag in tags:
        out |= contact_tag_union.keys_of(tag.settings or {})
    return out


def _chunks(items: list, size: int = 200):
    for i in range(0, len(items), size):
        yield items[i:i + size]


_GATE_WORDS = {
    "companies": "Companies",
    "stock_visibility": "Stock visibility",
    "agents": "Chatbot agents",
    "agent_fields": "Agent field access",
    "outbound_enabled": "Messaging (outbound)",
}


def assert_tag_gates(settings_list, gates) -> None:
    """TAG-UNION D4 (owner Q4): adding or removing a tag (or switching it on or off) grants or takes away
    what it sets, so it needs the gate of every gated section the tag sets. 403 naming the section."""
    if gates is None:
        return
    from app.services import contact_tag_settings as cts
    from app.services.error_handler import AppException

    can, is_superadmin = gates
    for settings in settings_list:
        # The AI model a tag puts its holders on spends AI quota (the same right as setting it on a tag).
        if ((settings or {}).get("chatbot") or {}).get("llm") is not None and not can(cts.AI_SETTINGS_EDIT):
            raise AppException(
                status_code=403,
                message="You may not add or remove a tag that sets the AI model.",
                code="FORBIDDEN",
            )
        for section in (settings or {}):
            if section not in cts._GATES or (settings or {}).get(section) is None:
                continue
            slug = cts._GATES[section]
            if not (is_superadmin() if slug is None else can(slug)):
                raise AppException(
                    status_code=403,
                    message=f"You may not add or remove a tag that sets {_GATE_WORDS.get(section, section)}.",
                    code="FORBIDDEN",
                )
