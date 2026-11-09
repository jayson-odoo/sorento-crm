"""TAG-UNION: a contact's tag settings are recomputed live, and a person's own changes survive.

Plan `documentation/plans/contacts/PLAN-tag-union-08nov.md`. The merge itself is
`contact_tag_settings.evaluate` (tags add up); the writers are `contact_tag_apply._WRITERS`. This
module adds the snapshot (`respond_contacts.tag_settings_snapshot`, per setting the value the tags
last wrote `v` and the value before tags took it over `base`) and the three-way rule:

* lists: target = (tag value + own additions) - own removals, own = current against `v`;
* anything else: the tag value when nobody changed the setting since the tags wrote it, else the
  person's value;
* a setting no active tag sets any more goes back to `base` by the same rule (unknown base: stays).

Callers seed first (`ensure_seeded`), then change membership or a tag, then `recompute` the settings
the changed tags set. Gates are checked by the caller (adding a tag grants what it sets).
"""
from __future__ import annotations

import logging
from typing import Any, Iterable, Optional

from sqlalchemy.orm import Session

from app.services import contact_tag_settings as cts

logger = logging.getLogger(__name__)

LIVE_TRIGGER = "Tag settings recomputed"
#: An empty list on these columns means EVERY brand / class, so the recompute never writes one.
NEVER_EMPTY = ("brands", "item_classes")
SCRIPT_TRIGGER = "Tag union recompute"


# ------------------------------------------------------------------ keys


def keys_of(settings: Optional[dict]) -> set[tuple[str, str]]:
    """The (section, key) pairs a settings object sets, with the include / exclude sibling of each."""
    out = {(s, k) for s, k, _ in cts.leaves_of(settings)}
    for sec, inc, exc in cts.INCLUDE_EXCLUDE:
        if (sec, inc) in out or (sec, exc) in out:
            out |= {(sec, inc), (sec, exc)}
    return out


def _split(sk: str) -> tuple[str, str]:
    section, key = sk.split("|", 1)
    return section, key


# ------------------------------------------------------------------ seeding (old rule)


def seed_each(db: Session, contacts: Iterable) -> set[str]:
    """`ensure_seeded` one contact at a time, each in its own savepoint; the ids that failed."""
    failed: set[str] = set()
    for c in contacts:
        if c.tag_settings_snapshot is not None:
            continue
        sp = db.begin_nested()
        try:
            ensure_seeded(db, [c])
            sp.commit()
        except Exception as exc:  # noqa: BLE001 - that contact's row reports the failure
            sp.rollback()
            failed.add(str(c.id))
            logger.warning("seeding the tag snapshot of contact %s failed: %s", c.id, exc, exc_info=True)
    return failed


def ensure_seeded(db: Session, contacts: Iterable) -> None:
    """Give every contact whose snapshot is NULL the snapshot the OLD rule (intersect / AND, inactive
    tags counted) would have written, so a value that differs from it is kept as an own change (owner
    Q3) and "Apply settings" can reset it. The pivot lists get an empty `base` (what the contact holds
    outside the old value is an own change, not something underneath the tags). Old-rule conflicts get
    no entry: the union decides them."""
    todo = [c for c in contacts if c.tag_settings_snapshot is None]
    if not todo:
        return
    ids = [str(c.id) for c in todo]
    tag_map = cts.tags_by_contact_with_settings(db, ids, include_inactive=True)
    for c in todo:
        cid = str(c.id)
        groups: dict[tuple[str, str], list] = {}
        for tag in tag_map.get(cid, []):
            try:
                for section, key, value in cts.leaves(tag):
                    groups.setdefault((section, key), []).append(value)
            except Exception:  # noqa: BLE001 - a malformed tag sets nothing (as the old evaluate would fail)
                logger.warning("contact tag %s has malformed settings; not seeded", tag.id)
        for sec, inc, exc in cts.INCLUDE_EXCLUDE:
            if (sec, inc) in groups and (sec, exc) in groups:  # the old rule's conflict: never written
                groups.pop((sec, inc))
                groups.pop((sec, exc))
        snapshot: dict[str, Any] = {}
        for (section, key), vals in groups.items():
            if (section, key) == ("chatbot", "llm"):
                continue  # read live, never written
            expected, conflict = cts._MERGE[cts.legacy_merge_kind(section, key)](vals)
            if conflict:
                continue
            entry: dict[str, Any] = {"v": cts.to_json(expected)}
            if section in cts.PIVOT_SECTIONS and isinstance(expected, frozenset):
                entry["base"] = cts.to_json(frozenset())
            snapshot[cts.snap_key(section, key)] = entry
        c.tag_settings_snapshot = snapshot
    db.flush()


# ------------------------------------------------------------------ recompute


def _three_way(tags: Any, last: Any, current: Any) -> Any:
    if all(isinstance(v, frozenset) for v in (tags, last, current)):
        return (tags | (current - last)) - (last - current)
    return tags if current == last else current


def _item(cat, section: str, key: str, target: Any, current: Any) -> dict:
    """A write item for a setting no tag sets any more (the evaluate item shape the writers read)."""
    label = cts._label(cat, section, key)
    return {
        "section": section, "key": key, "label": label, "redacted": False, "decided_by": [],
        "current": cts._display(cat, section, key, current), "expected": cts._display(cat, section, key, target),
        "_raw": {
            "expected": target, "current": current, "decided_by": [],
            "current_text": cts._display(cat, section, key, current),
            "expected_text": cts._display(cat, section, key, target),
        },
    }


def _with_target(item: dict, cat, target: Any) -> dict:
    out = dict(item)
    raw = dict(item["_raw"])
    raw["expected"] = target
    raw["expected_text"] = cts._display(cat, item["section"], item["key"], target)
    out["_raw"] = raw
    out["expected"] = raw["expected_text"]
    return out


def plan_contact(db: Session, contact, evaluated: dict, keys: Optional[set], cat, reader) -> tuple[list[dict], dict]:
    """(write items, new snapshot) for one seeded contact. Nothing is written here."""
    cid = str(contact.id)
    snapshot = dict(contact.tag_settings_snapshot or {})
    todo: list[dict] = []
    seen: set[str] = set()
    for item in evaluated["items"]:
        section, key = item["section"], item["key"]
        sk = cts.snap_key(section, key)
        seen.add(sk)
        if keys is not None and (section, key) not in keys:
            continue
        if (section, key) == ("chatbot", "llm") or item["conflict"] or item.get("blocked_reason"):
            continue
        tags, current = item["_raw"]["expected"], item["_raw"]["current"]
        entry = snapshot.get(sk)
        if entry is None:  # the tags take this setting over: remember what it was
            base = current
            if section in cts.PIVOT_SECTIONS and isinstance(tags, frozenset) and isinstance(current, frozenset):
                tags = tags | current
            target = tags
        else:
            base = cts.from_json(entry["base"]) if "base" in entry else None
            target = _three_way(tags, cts.from_json(entry.get("v")), current)
        if section in NEVER_EMPTY and target == frozenset():
            # Own removals took every brand / class away: an empty list would mean ALL of them
            # (contact_brand_scope), so the contact keeps what it holds (fail closed).
            target = current
        new_entry = {"v": cts.to_json(tags)}
        if entry is None or "base" in entry:
            new_entry["base"] = cts.to_json(base)
        snapshot[sk] = new_entry
        if target != current:
            todo.append(_with_target(item, cat, target))
    resolved_away = {
        cts.snap_key(sec, inc) for sec, inc, exc in cts.INCLUDE_EXCLUDE if cts.snap_key(sec, exc) in seen
    }
    for sk in [k for k in snapshot if k not in seen]:
        section, key = _split(sk)
        if keys is not None and (section, key) not in keys:
            continue
        entry = snapshot.pop(sk)
        if "base" not in entry:
            continue  # what it was before the tags is unknown: the value stays, as the contact's own
        if sk in resolved_away:
            # The tags' include and exclude lists were folded into one exclude list (one rule per row):
            # the include list's old base cannot sit beside it, so it is dropped, not written back.
            continue
        current = reader.current(cid, section, key, cat)
        target = _three_way(cts.from_json(entry["base"]), cts.from_json(entry.get("v")), current)
        if section in NEVER_EMPTY and target == frozenset():
            target = current  # an empty list means every brand / class: keep what the contact holds
        if target != current:
            todo.append(_item(cat, section, key, target, current))
    return todo, snapshot


def _write(db: Session, contact, todo: list[dict], actor_id: Optional[str], trigger: str) -> None:
    from app.services.audit_service import log_audit
    from app.services.contact_tag_apply import _WRITERS

    for section in cts.SECTIONS:
        group = [i for i in todo if i["section"] == section]
        if group:
            _WRITERS[section](db, contact, group, actor_id)
    labels = [i["label"] for i in todo]
    log_audit(
        db,
        "respond_contacts",
        str(contact.id),
        "UPDATE",
        user_id=actor_id,
        description=f"{trigger}: {', '.join(labels)}",
        new_values={i["label"]: i["_raw"]["expected_text"] for i in todo},
        old_values={i["label"]: i["_raw"]["current_text"] for i in todo},
    )


def recompute(
    db: Session,
    contacts: list,
    *,
    keys: Optional[set[tuple[str, str]]] = None,
    actor_id: Optional[str] = None,
    trigger: str = LIVE_TRIGGER,
) -> list[dict]:
    """Recompute (and write) the given contacts; one apply-shaped row per contact. `keys` limits the
    settings touched to those the changed tags set (None = every setting). Raises on a failed write:
    the caller's tag change and the access it grants commit or fail together."""
    from app.services.contact_access_copy_service import contact_label
    from app.services.contact_tag_apply import _change, _row

    if not contacts:
        return []
    ensure_seeded(db, contacts)
    evaluated = cts.evaluate(db, contacts)
    cat = cts.Catalog(db, scope_brands=True)
    reader = cts._Reader(db, contacts)
    rows: list[dict] = []
    for contact in contacts:
        cid = str(contact.id)
        todo, snapshot = plan_contact(db, contact, evaluated[cid], keys, cat, reader)
        conflicts = [
            {"label": i["label"], "tags": i["conflict_tags"]}
            for i in evaluated[cid]["items"]
            if i["conflict"] and (keys is None or (i["section"], i["key"]) in keys)
        ]
        if todo:
            _write(db, contact, todo, actor_id, trigger)
        contact.tag_settings_snapshot = snapshot
        rows.append(
            _row(cid, contact_label(contact), "changed" if todo else "unchanged",
                 [_change(cat, i) for i in todo], conflicts)
        )
    db.flush()
    return rows


# ------------------------------------------------------------------ one-off recompute (script)


def _grew(item: dict) -> Optional[bool]:
    before, after = item["_raw"]["current"], item["_raw"]["expected"]
    if isinstance(before, frozenset) and isinstance(after, frozenset):
        if after > before:
            return True
        if after < before:
            return False
        return None
    if before is False and after is True:
        return True
    if before is True and after is False:
        return False
    return None


def run(db: Session, *, apply: bool, expect: Optional[int], contact_ids: Optional[list[str]] = None) -> dict:
    """Seed and recompute every tagged contact (or `contact_ids`). Dry run writes nothing (everything
    happens inside a savepoint that is rolled back); `apply` refuses unless `expect` equals the number
    of contacts that change. The caller commits."""
    from sqlalchemy import select

    from app.models.access import RespondContact, respond_contact_tags as pivot
    from app.models.company import RespondContactCompany

    if apply and expect is None:
        raise ValueError("--apply needs --expect N (the changed count of the dry run)")
    if contact_ids is None:
        ids = [str(c) for (c,) in db.execute(select(pivot.c.contact_id).distinct())]
        ids += [
            str(c) for (c,) in db.query(RespondContact.id).filter(RespondContact.tag_settings_snapshot.isnot(None))
        ]
        ids = sorted(set(ids))
    else:
        ids = list(dict.fromkeys(str(i) for i in contact_ids))
    contacts = db.query(RespondContact).filter(RespondContact.id.in_(ids)).order_by(RespondContact.id).all()

    report: dict[str, Any] = {
        "contacts": len(contacts), "changed": 0, "failed": 0, "widened": 0, "narrowed": 0,
        "empty_companies_today": 0, "own_changes": 0, "inactive_only": 0, "by_setting": {},
    }
    # Facts about today, before anything moves.
    active = cts.tags_by_contact_with_settings(db, ids)
    every = cts.tags_by_contact_with_settings(db, ids, include_inactive=True)
    with_companies = {
        str(c) for (c,) in db.query(RespondContactCompany.respond_contact_id)
        .filter(RespondContactCompany.respond_contact_id.in_(ids)).distinct()
    }
    for cid in ids:
        if any("companies" in (t.settings or {}) for t in active.get(cid, [])) and cid not in with_companies:
            report["empty_companies_today"] += 1
        if every.get(cid) and not active.get(cid):
            report["inactive_only"] += 1

    outer = db.begin_nested()
    cat = cts.Catalog(db, scope_brands=True)
    try:
        for contact in contacts:
            sp = db.begin_nested()
            try:
                ensure_seeded(db, [contact])
                evaluated = cts.evaluate(db, [contact])
                reader = cts._Reader(db, [contact])
                todo, snapshot = plan_contact(db, contact, evaluated[str(contact.id)], None, cat, reader)
                if todo:
                    report["changed"] += 1
                    grew = [_grew(i) for i in todo]
                    report["widened"] += int(any(g is True for g in grew))
                    report["narrowed"] += int(any(g is False for g in grew))
                    for i in todo:
                        report["by_setting"][i["label"]] = report["by_setting"].get(i["label"], 0) + 1
                    _write(db, contact, todo, None, SCRIPT_TRIGGER)
                contact.tag_settings_snapshot = snapshot
                db.flush()
                after = cts.evaluate(db, [contact])[str(contact.id)]
                if any(i["differs"] for i in after["items"]):
                    report["own_changes"] += 1
                sp.commit()
            except Exception as exc:  # noqa: BLE001 - one contact's failure is counted, not fatal
                sp.rollback()
                report["failed"] += 1
                logger.warning("tag union recompute of contact %s failed: %s", contact.id, exc, exc_info=True)
        if apply and expect != report["changed"]:
            raise ValueError(f"expected {expect} changed contacts, the run changes {report['changed']}; nothing written")
    except Exception:
        outer.rollback()
        raise
    if apply:
        outer.commit()
    else:
        outer.rollback()
        db.expire_all()
    report["applied"] = apply
    return report
