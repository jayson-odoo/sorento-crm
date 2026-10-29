#!/usr/bin/env python3
"""Move the former PROMPT_SYNONYMS words from code into the data the lookup lists read.

WHY THIS EXISTS
---------------
`lookup_lists.PROMPT_SYNONYMS` (the v63 prompt's category translations and file type words) was code that
merged extra words into a row's texts. LOOKUP-EMBED-CENTRAL removes it: row texts now come from data only
(`product_categories.search_synonyms`, the `attachment_type_alias` lookup set). This script writes the 11 former
entries into that data so nothing the parser used to match is lost.

WHAT IT DOES
------------
A category word is added to `search_synonyms` of every ACTIVE category of that class (class label, or the
category's own name, case aside). A file type word is added as a keyword of that type's option in the
`attachment_type_alias` set (the option and the set are created when missing). A word already on the row is
skipped, so a second `--apply` adds nothing. Append only: no word is ever removed.

Dry run is the DEFAULT; nothing is written without `--apply`. The caller commits.

Run from sorento_crm_backend/:
    venv/bin/python scripts/move_prompt_synonyms.py
    venv/bin/python scripts/move_prompt_synonyms.py --apply
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import Any, Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.lookup import LookupOption, LookupOptionKeyword, LookupSet
from app.models.product import ProductCategory
from app.models.resources import AttachmentType

# The 11 former PROMPT_SYNONYMS entries: row label (case aside) -> extra words.
CATEGORY_WORDS: dict[str, tuple[str, ...]] = {
    "water tap": ("paip air", "kepala paip", "水龙头"),
    "water closet": ("tandas", "mangkuk tandas", "马桶"),
    "kitchen sink": ("sinki dapur", "厨房水槽"),
}
FILE_TYPE_WORDS: dict[str, tuple[str, ...]] = {
    "photo": ("gambar", "foto", "image", "picture", "imej"),
    "image": ("imej", "gambar", "foto", "picture"),
    "video": ("videos",),
    "drawing": ("lukisan",),
    "technical drawing": ("lukisan teknikal", "lukisan", "cad", "blueprint"),
    "3d model": ("model 3d",),
    "installation guide": ("installation manual",),
    "certificate": ("sijil", "cert", "ikram"),
}
# A label that names a class under a shorter class label.
CLASS_ALIASES: dict[str, tuple[str, ...]] = {"water tap": ("water tap", "tap")}
ALIAS_SET_KEY = "attachment_type_alias"


def _folded(value: Any) -> str:
    return str(value or "").strip().casefold()


def _category_entries(db: Session) -> List[Dict[str, Any]]:
    cats = (
        db.query(ProductCategory)
        .filter(ProductCategory.is_active.is_(True))
        .order_by(ProductCategory.category_code)
        .all()
    )
    entries: List[Dict[str, Any]] = []
    for label, words in CATEGORY_WORDS.items():
        names = set(CLASS_ALIASES.get(label, (label,)))
        for cat in cats:
            if _folded(cat.class_label) not in names and _folded(cat.category_name) != label:
                continue
            have = {_folded(w) for w in (cat.search_synonyms or [])}
            add = [w for w in words if _folded(w) not in have]
            if add:
                entries.append(
                    {"list": "category", "id": str(cat.id), "category_code": cat.category_code, "label": label, "add": add}
                )
    return entries


def _attachment_type(db: Session, label: str):
    """The attachment type a former file type entry names: its code or its name, case aside."""
    return (
        db.query(AttachmentType)
        .filter(or_(func.lower(AttachmentType.code) == label, func.lower(AttachmentType.type_name) == label))
        .first()
    )


def _alias_option(db: Session, atype):
    """The type's option in the alias set, keyed by its name or its code."""
    return (
        db.query(LookupOption)
        .join(LookupSet, LookupSet.id == LookupOption.set_id)
        .filter(LookupSet.set_key == ALIAS_SET_KEY)
        .filter(func.lower(LookupOption.value).in_([_folded(atype.type_name), _folded(atype.code)]))
        .first()
    )


def _file_type_entries(db: Session) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    for label, words in FILE_TYPE_WORDS.items():
        atype = _attachment_type(db, label)
        if atype is None:
            # No such type here: nothing to attach the words to, and none is invented.
            entries.append({"list": "file_type", "label": label, "unmatched": True, "add": list(words)})
            continue
        option = _alias_option(db, atype)
        have = {_folded(k.keyword) for k in (option.keywords if option is not None else [])}
        add = [w for w in words if _folded(w) not in have]
        if add:
            entries.append({"list": "file_type", "label": label, "type_id": str(atype.id), "add": add})
    return entries


def plan(db: Session) -> List[Dict[str, Any]]:
    """One entry per category / file type missing at least one of its former words (unmatched types flagged)."""
    return [*_category_entries(db), *_file_type_entries(db)]


def _ensure_option(db: Session, atype) -> LookupOption:
    option = _alias_option(db, atype)
    if option is not None:
        return option
    alias_set = db.query(LookupSet).filter(LookupSet.set_key == ALIAS_SET_KEY).first()
    if alias_set is None:
        alias_set = LookupSet(set_key=ALIAS_SET_KEY, name="Attachment type aliases", is_active=True)
        db.add(alias_set)
        db.flush()
    option = LookupOption(set_id=alias_set.id, value=atype.type_name, label=atype.type_name, is_active=True)
    db.add(option)
    db.flush()
    return option


def run(db: Session, *, apply: bool = False) -> Dict[str, Any]:
    """Report (and with `apply`, write) the former words each row is missing. The caller commits."""
    entries = plan(db)
    added = 0
    unmatched = [e["label"] for e in entries if e.get("unmatched")]
    for entry in entries:
        if entry.get("unmatched"):
            print(f"  {entry['list']:<10} {entry['label']:<22} unmatched: no attachment type of that name or code")
            continue
        who = entry.get("category_code") or entry["label"]
        print(f"  {entry['list']:<10} {who:<22} + {', '.join(entry['add'])}")
        if not apply:
            continue
        if entry["list"] == "category":
            row = db.get(ProductCategory, entry["id"])
            row.search_synonyms = [*(row.search_synonyms or []), *entry["add"]]
        else:
            option = _ensure_option(db, db.get(AttachmentType, entry["type_id"]))
            for word in entry["add"]:
                db.add(LookupOptionKeyword(option_id=option.id, keyword=word))
            db.flush()
            db.expire(option, ["keywords"])
        added += len(entry["add"])
    if apply:
        db.flush()
    return {"plan": [e for e in entries if not e.get("unmatched")], "added": added, "unmatched": unmatched}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="Write the words. Without it the script only reports.")
    args = parser.parse_args()

    from app.database import SessionLocal
    from app.models.base import set_company_scope

    db = SessionLocal()
    set_company_scope(db, None)
    try:
        result = run(db, apply=args.apply)
        if args.apply:
            db.commit()
        mode = "applied" if args.apply else "dry-run"
        print(f"{mode}: {len(result['plan'])} rows, {result['added']} words written")
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
