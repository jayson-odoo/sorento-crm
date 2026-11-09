#!/usr/bin/env python3
"""Load flyer combos (name, description, free items, parts, cover picture) from a seed file.

WHY
---
Marketing's flyer holds the combos a dealer orders as one package. The price tag now prints a
combo's own picture, description and options (PLAN-price-tag-combo-template-fields), so the
combos have to exist on their host product first. This loads them once, through the same
`ProductComboService` the Combos card uses.

SEED FORMAT
-----------
A JSON list (written by `flyer_combo_read.py`, or by hand). Per entry: `id`, `host_code`,
`combo_name` (or `title`), `combo_description`, `free_items` [{code, label, note}],
`components` [{code, role}], `choice_groups` [{role, options: [{code, descr, sp}]}],
`topups` [{code, descr, topup}], `lp`, `sp`, `photo` (a file name relative to --photos), `flyer`,
`page`, `unsure` and `guess` (text, listed in the report).

PRICES
------
`lp`/`sp` are the combo's list and selling price, option `sp` the option's own selling price,
`topup` an upgrade's top-up. A price already on the combo is never overwritten without
`--update`. A host whose brand carries no promotion selling price never gets `sp`, option `sp` or
`topup` (`price_note` says so); its list price still loads.

RULES
-----
* Host and part lookup is under the chosen company's scope only (--company, default SRT). A host
  code with no product: `not_loaded_host_missing`.
* A part code with no product (in that company), a component with no code, or a discontinued
  product: that part is not loaded and is listed (`dropped_parts`, `discontinued`), and the combo
  is `unsure`. The combo still loads with the parts that did resolve.
* Components become fixed parts, `choice_groups` become parts sharing a `choice_group`,
  `topups` become parts with `is_upgrade`.
* A combo is matched on host + name; combos under other names are not touched.
* Statuses: `new` (no such combo yet), `matches`, `differs` (the report names each difference),
  `unsure`. The same statuses are reported on `--apply`.
* `--apply` creates, fills what is empty (description, free items, cover, prices) and adds missing
  parts. `--apply --update` also brings a differing combo to the seed: removes parts the seed no
  longer has, regroups and re-flags parts, overwrites the prices. An `unsure` combo is never pruned.
* `--link-templates` links every published template of the company whose needs fit the combo
  (`template_needs.fit_reason`), keeping the links the combo has.
* `--templates` creates and publishes one 105 x 148 starter template per shape in STARTER_SHAPES,
  all from `position_template`, skipping any that already exist by name.

Dry run is the default: nothing is written, photos, links and templates included. A report CSV
(one row per seed entry) is written either way.

USAGE
-----
    cd sorento_crm_backend
    venv/bin/python scripts/import_product_combos.py --file seed.json --photos DIR --report out.csv
    venv/bin/python scripts/import_product_combos.py --file seed.json --photos DIR --report out.csv --apply [--update] [--link-templates] [--templates]

The seed and the photos are real business data and stay outside this repository.
"""
from __future__ import annotations

import argparse
import csv
import json
import mimetypes
import os
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation
from types import SimpleNamespace
from pathlib import Path
from typing import Optional, Sequence, TextIO

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import func  # noqa: E402

from app.audit_context import AuditActor, clear_actor, stamp_actor  # noqa: E402
from app.models.base import company_scope  # noqa: E402
from app.models.company import Company  # noqa: E402
from app.models.dealer_kit import TagTemplate  # noqa: E402
from app.models.product import Product  # noqa: E402
from app.models.accessory import Accessory, ProductComboAccessory  # noqa: E402
from app.models.product_combo import ProductCombo  # noqa: E402
from app.services.accessory_service import AccessoryService  # noqa: E402
from app.services.audit_service import register_audit_listeners  # noqa: E402
from app.services.dealer_kit.pricing import _no_selling_price_product_ids  # noqa: E402
from app.services.dealer_kit.product_tag_template_service import NON_PRICE_TAG_FAMILY_PREFIX  # noqa: E402
from app.services.dealer_kit.template_needs import combo_shape, fit_reason, template_needs  # noqa: E402
from app.utils.tag_rich_text import is_rich, plain_text  # noqa: E402
from app.services.error_handler import AppException  # noqa: E402
from app.services.product_combo_service import ProductComboService  # noqa: E402

JOB_ID = "import_product_combos"
MAX_SEED_BYTES = 20 * 1024 * 1024
#: Without --strict a description is cut off at the old seed limit; --strict takes the service cap.
LEGACY_DESCRIPTION_CAP = 1000
REPORT_COLUMNS = [
    "id", "flyer", "page", "host", "combo", "shape", "status", "differences",
    "dropped_parts", "discontinued", "price_note", "unsure", "guess", "notes",
]
NO_SP_NOTE = "price not loaded: no selling price brand"

S_HOST_MISSING = "not_loaded_host_missing"
S_NEW, S_MATCHES, S_DIFFERS, S_UNSURE = "new", "matches", "differs", "unsure"


# --------------------------------------------------------------------------- seed


def free_item_names(items) -> list[str]:
    """`["ZZTTAP1 Tap", "Waste"]`: the code prefixes the label, a code-less item is its label alone.
    Each becomes one accessory on the combo's list (PRICETAG-ACCESSORIES: the one source)."""
    out: list[str] = []
    for item in items or []:
        text = f"{(item.get('code') or '').strip()} {(item.get('label') or '').strip()}".strip()
        if text and text.lower() not in {name.lower() for name in out}:
            out.append(text)
    return out


def _free_product(db, code: str, company_id) -> Optional[Product]:
    """The product a free item's code names, in the host's company; None for no code or no match."""
    if not code:
        return None
    statement = db.query(Product).filter(func.upper(Product.product_code) == code.upper())
    if company_id is not None:
        statement = statement.filter(Product.company_id == company_id)
    return statement.first()


def _has_free_list(db, combo_id: str) -> bool:
    """The combo already lists its free items: a load never overwrites a list someone set."""
    return (
        db.query(ProductComboAccessory.id).filter(ProductComboAccessory.combo_id == combo_id).first()
        is not None
    )


def free_items_text(items) -> str:
    """The names joined, as the report shows them."""
    return ", ".join(free_item_names(items))


def _money(value) -> Optional[Decimal]:
    """A seed price as money, or None when it is absent, not a number or out of range."""
    if value is None or isinstance(value, bool):
        return None
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None
    return amount if Decimal("0") <= amount <= Decimal("10000000") else None


def wanted_parts(entry) -> list[dict]:
    """The parts the entry asks for, in seed order: `{code, role, group, upgrade, sp, topup}`."""
    parts = []
    for item in entry.get("components") or []:
        parts.append(
            {"code": (item.get("code") or "").strip(), "role": item.get("role") or "",
             "group": None, "upgrade": False, "sp": None, "topup": None}
        )
    for group in entry.get("choice_groups") or []:
        role = (group.get("role") or "").strip()
        for option in group.get("options") or []:
            parts.append(
                {"code": (option.get("code") or "").strip(), "role": role,
                 "group": role or None, "upgrade": False, "sp": _money(option.get("sp")), "topup": None}
            )
    for item in entry.get("topups") or []:
        parts.append(
            {"code": (item.get("code") or "").strip(), "role": "Upgrade",
             "group": None, "upgrade": True, "sp": None, "topup": _money(item.get("topup"))}
        )
    return parts


def read_seed(path: str) -> list[dict]:
    if os.path.getsize(path) > MAX_SEED_BYTES:
        raise ValueError(f"file is over {MAX_SEED_BYTES} bytes")
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, list):
        raise ValueError("the seed must be a JSON list")
    return data


def invalid_entry(entry, legacy_cap: bool = False) -> Optional[str]:
    """Why a seed entry cannot be read, or None. Checked with the reader's own `Combo` model (one
    schema for the seed), against a copy: the entry itself is used as written, `title` standing in
    for a missing `combo_name` as it always has."""
    from scripts.flyer_combo_read import Combo, ValidationError

    if not isinstance(entry, dict):
        return "the entry is not an object"
    try:
        Combo.model_validate({**entry, "combo_name": entry.get("combo_name") or entry.get("title") or "-"})
    except ValidationError as exc:
        first = exc.errors()[0]
        return f"{'.'.join(str(part) for part in first['loc'])}: {first['msg']}"[:300]
    if legacy_cap and len(entry.get("combo_description") or "") > LEGACY_DESCRIPTION_CAP:
        return f"combo_description: too long (over {LEGACY_DESCRIPTION_CAP} without --strict)"
    return None


def photo_path(photos: Optional[Path], name: str) -> Optional[Path]:
    """The photo file for an entry, only when it sits inside the photos folder."""
    if not photos or not name:
        return None
    root = photos.resolve()
    path = (root / name).resolve()
    if root not in path.parents or not path.is_file():
        return None
    return path


# --------------------------------------------------------------------------- products


def products_by_code(db, company_id: str, codes: set[str]) -> dict[str, Product]:
    """Products of THIS company by upper-cased code. Another company's product is not found."""
    wanted = {code.upper() for code in codes if code}
    if not wanted:
        return {}
    with company_scope(db, frozenset({company_id})):
        rows = (
            db.query(Product)
            .filter(Product.company_id == company_id, func.upper(Product.product_code).in_(wanted))
            .all()
        )
    return {row.product_code.upper(): row for row in rows}


# --------------------------------------------------------------------------- entry


def _shape_text(shape: dict) -> str:
    groups = ",".join(str(g["size"]) for g in shape["groups"]) or "0"
    return f"fixed {shape['fixed']}; groups {groups}; upgrades {shape['upgrades']}"


def _shape_of(parts: list[dict]) -> dict:
    """The shape of a list of `{product, group, upgrade}` parts, through the one `combo_shape`."""
    return combo_shape(
        SimpleNamespace(
            parts=[
                SimpleNamespace(part_product=p["product"], is_upgrade=p["upgrade"], choice_group=p["group"])
                for p in parts
            ]
        )
    )


def _show(value) -> str:
    return "none" if value is None else str(value)


def _wanted(existing_value, seed_value, update: bool):
    """What to write over `existing_value`: a seed value fills an empty one, and replaces a
    different one only on `--update`. None = leave as it is."""
    if seed_value is None:
        return None
    if existing_value is None:
        return seed_value
    return seed_value if update and existing_value != seed_value else None


def link_fitting_templates(db, combo, published, apply: bool) -> str:
    """Link the published templates whose needs fit this combo (K4's one `fit_reason`), keeping
    the links it has. Returns a note for the report."""
    from app.models.dealer_kit import ComboTagTemplate
    from app.services.dealer_kit import product_tag_template_service

    shape = combo_shape(combo)
    fitting = [t for t, needs in published if fit_reason(needs, shape) is None]
    have = {
        link.template_id
        for link in db.query(ComboTagTemplate).filter(ComboTagTemplate.combo_id == combo.id).all()
    }
    add = [t for t in fitting if t.id not in have]
    if not add:
        return ""
    if apply:
        product_tag_template_service.set_combo_templates(
            db, combo.id, [*have, *(t.id for t in add)], user_id=None
        )
        # The link service only flushes; this process owns the transaction.
        db.commit()
    return f"{'linked' if apply else 'would link'}: {', '.join(t.name for t in add)}"


def process_entry(
    db, entry, host, parts_by_code, photos, apply: bool,
    *, update: bool = False, published=None, no_sp_ids=frozenset(),
) -> dict:
    """Load (or, on a dry run, only judge) one seed entry. Returns its report row."""
    row = {column: "" for column in REPORT_COLUMNS}
    row.update(
        id=str(entry.get("id") or ""),
        flyer=str(entry.get("flyer") or ""),
        page=str(entry.get("page") or ""),
        host=(entry.get("host_code") or "").strip(),
        guess=entry.get("guess") or "",
    )
    if host is None:
        row["status"] = S_HOST_MISSING
        return row

    name = ((entry.get("combo_name") or entry.get("title") or "").strip())[:100]
    row["combo"] = name
    notes: list[str] = []
    dropped: list[str] = []
    discontinued: list[str] = []
    discontinued_codes: list[str] = []
    keep: list[dict] = []
    for part in wanted_parts(entry):
        product = parts_by_code.get(part["code"].upper()) if part["code"] else None
        if not part["code"]:
            dropped.append(f"no code ({part['role'] or 'part'})")
        elif product is None:
            dropped.append(part["code"])
        elif product.is_discontinued:
            discontinued.append(product.product_code)
            discontinued_codes.append(part["code"])
        elif product.id != host.id and not any(k["product"].id == product.id for k in keep):
            # The host listed among the components is the flyer's own layout, not a drop; a
            # product named twice is one part.
            keep.append({**part, "product": product})
    row["dropped_parts"] = "; ".join(dropped)
    row["discontinued"] = "; ".join(discontinued)
    row["shape"] = _shape_text(_shape_of(keep))

    # A product whose brand carries no promotion selling price never gets a selling price: the combo
    # SP for such a host, an option SP or a top-up for a part of such a host or one that is itself
    # such a product. The list price still loads.
    seed_lp = _money(entry.get("lp"))
    seed_sp = _money(entry.get("sp"))
    host_no_sp = host.id in no_sp_ids
    skipped = False
    if host_no_sp:
        skipped = seed_sp is not None
        seed_sp = None
    for k in keep:
        # A no-selling-price host sells its whole combo that way; a part may also be one on its own.
        k["no_sp"] = host_no_sp or k["product"].id in no_sp_ids
        if k["no_sp"]:
            skipped = skipped or k["sp"] is not None or k["topup"] is not None
            k["sp"] = k["topup"] = None
    if skipped:
        row["price_note"] = NO_SP_NOTE

    unsure = []
    if (entry.get("unsure") or "").strip():
        unsure.append(entry["unsure"].strip())
    if dropped:
        unsure.append(f"not loaded: {'; '.join(dropped)}")
    if discontinued:
        unsure.append(f"discontinued: {'; '.join(discontinued)}")
    row["unsure"] = " | ".join(unsure)

    photo_name = (entry.get("photo") or "").strip()
    photo = photo_path(photos, photo_name)
    if photo_name and photo is None:
        notes.append(f"photo file missing: {photo_name}")

    if not name:
        row["status"] = "skipped_no_name"
        row["notes"] = "; ".join(notes)
        return row

    service = ProductComboService(db)
    existing = (
        db.query(ProductCombo)
        .filter(ProductCombo.host_product_id == host.id, func.lower(ProductCombo.name) == name.lower())
        .first()
    )
    have = {part.part_product_id: part for part in existing.parts} if existing else {}
    want = {k["product"].id: k for k in keep}
    # A part the seed lists but that is discontinued is held back, not dropped from the flyer:
    # the existing part stays and is not reported as removed.
    held_back = {parts_by_code[code.upper()].id for code in discontinued_codes if code.upper() in parts_by_code}

    # ---- what differs from the flyer (named by code), judged the same on a dry run
    differences: list[str] = []
    if existing is not None:
        for k in keep:
            part = have.get(k["product"].id)
            code = k["product"].product_code
            if part is None:
                differences.append(f"added {code}")
            elif (part.choice_group or None) != k["group"] or bool(part.is_upgrade) != k["upgrade"]:
                differences.append(f"regrouped {code}")
            else:
                if k["no_sp"]:
                    if part.sell_price is not None:
                        differences.append(f"{code} sell price {part.sell_price} -> none")
                    if part.topup_amount is not None:
                        differences.append(f"{code} top-up {part.topup_amount} -> none")
                    continue
                if _wanted(part.sell_price, k["sp"], True) is not None:
                    differences.append(f"{code} sell price {_show(part.sell_price)} -> {k['sp']}")
                if _wanted(part.topup_amount, k["topup"], True) is not None:
                    differences.append(f"{code} top-up {_show(part.topup_amount)} -> {k['topup']}")
        for product_id, part in have.items():
            if product_id not in want and product_id not in held_back and part.part_product is not None:
                differences.append(f"removed {part.part_product.product_code}")
        if _wanted(existing.list_price, seed_lp, True) is not None:
            differences.append(f"list price {_show(existing.list_price)} -> {seed_lp}")
        if host_no_sp and existing.sell_price is not None:
            differences.append(f"selling price {existing.sell_price} -> none")
        elif _wanted(existing.sell_price, seed_sp, True) is not None:
            differences.append(f"selling price {_show(existing.sell_price)} -> {seed_sp}")

    description = (entry.get("combo_description") or "").strip()
    free_names = free_item_names(entry.get("free_items"))
    fill = {}
    if description and not (existing and (plain_text(existing.description) or "").strip()):
        fill["description"] = description
    want_free = bool(free_names) and not (existing and _has_free_list(db, existing.id))
    want_photo = photo is not None and not (existing and existing.image_attachment_id)
    if existing is not None:
        differences += [f"{field.replace('_', ' ')} to fill" for field in fill]
        if want_free:
            differences.append("free items to fill")
        if want_photo:
            differences.append("cover to load")
    row["differences"] = "; ".join(differences)

    if unsure:
        row["status"] = S_UNSURE
    elif existing is None:
        row["status"] = S_NEW
    else:
        row["status"] = S_DIFFERS if differences else S_MATCHES

    # An unsure combo is never pruned: its dropped codes would otherwise read as "removed".
    prune = update and not unsure

    if apply:
        combo_id = (
            service.create(host.id, name, created_by=None)["id"] if existing is None else existing.id
        )
        update_fields = dict(fill)
        for field, current, seed_value in (
            ("list_price", existing.list_price if existing else None, seed_lp),
            ("sell_price", existing.sell_price if existing else None, seed_sp),
        ):
            target = _wanted(current, seed_value, update)
            if target is not None:
                update_fields[field] = target
        if update and host_no_sp and existing is not None and existing.sell_price is not None:
            update_fields["sell_price"] = None
        if update_fields:
            service.update(combo_id, update_fields)
        if want_free:
            accessories = AccessoryService(db)
            combo_row = db.query(ProductCombo).filter(ProductCombo.id == combo_id).first()
            in_combo = {host.id} | {part.part_product_id for part in (combo_row.parts if combo_row else [])}
            items, seen = [], set()
            for free in entry.get("free_items") or []:
                text = f"{(free.get('code') or '').strip()} {(free.get('label') or '').strip()}".strip()
                if not text:
                    continue
                # Owner, 6 Nov ~10:45: a free item with a catalogue code is that PRODUCT, read live.
                product = _free_product(db, (free.get("code") or "").strip(), host.company_id)
                if product is not None and product.id not in in_combo:
                    key = ("product_id", product.id)
                else:
                    key = ("accessory_id", accessories.find_or_create(text, host.company_id).id)
                if key not in seen:
                    seen.add(key)
                    items.append({key[0]: key[1]})
            accessories.set_combo_list(combo_id, items)
        if prune:
            for product_id, part in have.items():
                if product_id not in want and product_id not in held_back:
                    service.delete_part(part.id)
        for k in keep:
            part = have.get(k["product"].id)
            if part is None:
                # `is_upgrade` goes in with the part, so a crash cannot leave an upgrade as a fixed part.
                created = service.add_part(combo_id, k["product"].id, k["group"], is_upgrade=k["upgrade"])
                part_id, sell, topup = created["id"], None, None
            else:
                part_id, sell, topup = part.id, part.sell_price, part.topup_amount
                if prune and ((part.choice_group or None) != k["group"] or bool(part.is_upgrade) != k["upgrade"]):
                    service.update_part(
                        part_id, {"choice_group": k["group"], "is_upgrade": k["upgrade"]},
                        fields_set={"choice_group"},
                    )
            prices = {}
            if (value := _wanted(sell, k["sp"], update)) is not None:
                prices["sell_price"] = value
            if (value := _wanted(topup, k["topup"], update)) is not None:
                prices["topup_amount"] = value
            if update and k["no_sp"]:
                # A brand with no selling price carries none: clear what an earlier load left.
                if sell is not None:
                    prices["sell_price"] = None
                if topup is not None:
                    prices["topup_amount"] = None
            if prices:
                service.update_part(part_id, prices, fields_set=set(prices))
        if want_photo:
            content_type = mimetypes.guess_type(photo.name)[0]
            try:
                service.upload_image(
                    combo_id, content=photo.read_bytes(), filename=photo.name,
                    content_type=content_type, user_id=None,
                )
            except AppException as exc:
                notes.append(f"photo not loaded: {photo.name} ({exc.message})")

    if published is not None:
        if apply:
            db.expire_all()
            combo = db.query(ProductCombo).filter(ProductCombo.id == combo_id).first()
        else:
            combo = existing
        if combo is not None:
            note = link_fitting_templates(db, combo, published, apply)
        else:
            # A new combo on a dry run: judged on the shape the flyer would give it.
            shape = _shape_of(keep)
            fits = [t.name for t, needs in published if fit_reason(needs, shape) is None]
            note = f"would link: {', '.join(fits)}" if fits else ""
        if note:
            notes.append(note)
    row["notes"] = "; ".join(notes)
    return row


# --------------------------------------------------------------------------- strict (flyer seed)

VERDICT_ORDER = ("CREATE", "UPDATE", "SKIP", "UNMATCHED", "FAILED")


def _entry_name(entry) -> str:
    if not isinstance(entry, dict):
        return ""
    return ((entry.get("combo_name") or entry.get("title") or "").strip())[:100]


def _verdict_row(entry, verdict: str, details: str) -> dict:
    """One strict result: the report row plus the printed `verdict` and `details`."""
    row = {column: "" for column in REPORT_COLUMNS}
    if isinstance(entry, dict):
        row.update(
            id=str(entry.get("id") or ""), flyer=str(entry.get("flyer") or ""),
            page=str(entry.get("page") or ""), host=(entry.get("host_code") or "").strip(),
            combo=_entry_name(entry), guess=entry.get("guess") or "",
        )
    row.update(status=verdict.lower(), differences=details, verdict=verdict, details=details)
    return row


def _free_resolve(db, free: dict, company_id, host, part_ids: set):
    """A strict free item: ('product_id' | 'accessory_id', id), or None when nothing matches.
    Nothing is ever created or guessed."""
    kind = free.get("kind")
    code = (free.get("code") or "").strip()
    label = (free.get("label") or "").strip()
    if kind in (None, "product") and code:
        product = _free_product(db, code, company_id)
        if product is not None and (host is None or product.id != host.id) and product.id not in part_ids:
            return ("product_id", product.id)
    if kind == "accessory" and label:
        accessory = (
            db.query(Accessory)
            .filter(func.lower(Accessory.name) == label.lower(), Accessory.company_id == company_id)
            .first()
        )
        if accessory is not None:
            return ("accessory_id", accessory.id)
    return None


def process_entry_strict(
    db, entry, host, parts_by_code, company_id, apply: bool, *, update: bool = False,
    no_sp_ids=frozenset(),
) -> dict:
    """Judge (and on `--apply` write) one flyer seed entry under `--strict`. An entry whose host,
    part or free item has no match writes nothing. Nothing is ever deleted."""
    name = _entry_name(entry)
    missing: list[str] = []
    if host is None:
        missing.append((entry.get("host_code") or "").strip() or "no host code")
    keep: list[dict] = []
    held_back: set = set()
    for part in wanted_parts(entry):
        product = parts_by_code.get(part["code"].upper()) if part["code"] else None
        if not part["code"]:
            missing.append(f"no code ({part['role'] or 'part'})")
        elif product is None:
            missing.append(part["code"])
        elif product.is_discontinued:
            held_back.add(product.id)
        elif (host is None or product.id != host.id) and not any(k["product"].id == product.id for k in keep):
            keep.append({**part, "product": product})
    part_ids = {k["product"].id for k in keep} | held_back
    free_keys, seen = [], set()
    for free in entry.get("free_items") or []:
        resolved = _free_resolve(db, free, company_id, host, part_ids)
        if resolved is None:
            label = (free.get("code") or "").strip() if free.get("kind") != "accessory" else ""
            missing.append(label or (free.get("label") or "").strip() or "free item")
        elif resolved not in seen:
            seen.add(resolved)
            free_keys.append(resolved)
    if missing or host is None:
        unique = list(dict.fromkeys(missing))
        return _verdict_row(entry, "UNMATCHED", f"missing: {', '.join(unique)}")

    seed_lp, seed_sp = _money(entry.get("lp")), _money(entry.get("sp"))
    host_no_sp = host.id in no_sp_ids
    if host_no_sp:
        seed_sp = None
    for k in keep:
        if host_no_sp or k["product"].id in no_sp_ids:
            k["sp"] = k["topup"] = None

    names = {name.lower(), *((a or "").strip().lower() for a in entry.get("aka") or [])} - {""}
    host_combos = (
        db.query(ProductCombo).filter(ProductCombo.host_product_id == host.id).order_by(ProductCombo.name).all()
    )
    existing = next((c for c in host_combos if (c.name or "").lower() in names), None)
    if existing is None:
        others = ", ".join(f'"{c.name}"' for c in host_combos)
        details = f"host also has: {others}" if others else ""
    else:
        description = (entry.get("combo_description") or "").strip()
        fill: dict = {}
        if description and not (plain_text(existing.description) or "").strip():
            fill["description"] = description
        fields: list[str] = []
        kept: list[str] = []
        for field, label, current, seed_value in (
            ("list_price", "list price", existing.list_price, seed_lp),
            ("sell_price", "selling price", existing.sell_price, seed_sp),
        ):
            target = _wanted(current, seed_value, update)
            if target is not None:
                fill[field] = target
            elif seed_value is not None and current is not None and current != seed_value:
                kept.append(f"{label} {current} (flyer {seed_value})")
        on_file = (existing.description or "").strip()
        if "description" in fill:
            fields.append("description")
        elif description and on_file != description and not is_rich(on_file):
            # A plain-text description with the flyer's own words gets the flyer's bold; no word changes.
            if " ".join(plain_text(on_file).split()) == " ".join(plain_text(description).split()):
                fill["description"] = description
                fields.append("description bold")
            else:
                kept.append("description differs from flyer")
        elif description and on_file != description:
            kept.append("description differs from flyer")
        fields += [label for label, field in (("list price", "list_price"), ("selling price", "sell_price")) if field in fill]
        want_free = bool(free_keys) and not _has_free_list(db, existing.id)
        if want_free:
            fields.append("free items")
        have = {part.part_product_id: part for part in existing.parts}
        part_fills = []
        if not have:
            # Parts are written only to a combo that has none; adding next to someone's own
            # differently grouped parts would leave a mixed combo.
            part_fills = [k["product"].product_code for k in keep]
        else:
            seed_set = {k["product"].id: (k["group"], k["upgrade"]) for k in keep}
            file_set = {
                pid: ((part.choice_group or None), bool(part.is_upgrade))
                for pid, part in have.items() if pid not in held_back
            }
            if seed_set != file_set:
                def listing(groups: dict) -> str:
                    return "; ".join(
                        f"{label}: {', '.join(sorted(codes))}" for label, codes in sorted(groups.items())
                    )

                def grouped(pairs) -> dict:
                    out_groups: dict = {}
                    for code, (group, upgrade) in pairs:
                        label = "upgrade" if upgrade else (group or "fixed")
                        out_groups.setdefault(label, []).append(code)
                    return out_groups

                flyer_pairs = [(k["product"].product_code, seed_set[k["product"].id]) for k in keep]
                file_pairs = [
                    (part.part_product.product_code, file_set[pid])
                    for pid, part in have.items() if pid in file_set and part.part_product is not None
                ]
                if set(seed_set) == set(file_set):
                    kept.append(
                        f"parts grouped differently (flyer: {listing(grouped(flyer_pairs))}; "
                        f"on file: {listing(grouped(file_pairs))})"
                    )
                else:
                    flyer_codes = ", ".join(sorted(code for code, _ in flyer_pairs))
                    on_file = ", ".join(sorted(code for code, _ in file_pairs))
                    kept.append(f"parts differ (flyer: {flyer_codes}; on file: {on_file})")
        if part_fills:
            fields.append(f"parts {' '.join(part_fills)}")
        if fields:
            verdict, details = "UPDATE", f"fills: {', '.join(fields)}"
        else:
            verdict, details = "SKIP", f"kept: {'; '.join(kept)}" if kept else ""

    if apply and (existing is None or fields):
        service = ProductComboService(db)
        combo_id = service.create(host.id, name, created_by=None)["id"] if existing is None else existing.id
        have = {part.part_product_id: part for part in existing.parts} if existing else {}
        update_fields: dict = {}
        if existing is None:
            if (entry.get("combo_description") or "").strip():
                update_fields["description"] = entry["combo_description"].strip()
            for field, value in (("list_price", seed_lp), ("sell_price", seed_sp)):
                if value is not None:
                    update_fields[field] = value
        else:
            update_fields = dict(fill)
        if update_fields:
            service.update(combo_id, update_fields)
        if free_keys and (existing is None or want_free):
            AccessoryService(db).set_combo_list(combo_id, [{key: value} for key, value in free_keys])
        for k in (keep if not have else []):
            created = service.add_part(combo_id, k["product"].id, k["group"], is_upgrade=k["upgrade"])
            prices = {}
            if k["sp"] is not None:
                prices["sell_price"] = k["sp"]
            if k["topup"] is not None:
                prices["topup_amount"] = k["topup"]
            if prices:
                service.update_part(created["id"], prices, fields_set=set(prices))
    if existing is None:
        return _verdict_row(entry, "CREATE", details)
    return _verdict_row(entry, verdict, details)


def run_strict(db, entries, problems, found, company_id, args, no_sp_ids, out: TextIO) -> list[dict]:
    """Every entry through `process_entry_strict`, one transaction per host on `--apply`:
    inside a host block the session's `commit` only flushes, one real commit closes the block, and
    any error rolls the whole host back (its entries read FAILED) before the next host loads."""
    results: dict[int, dict] = {}
    blocks: dict[str, list[int]] = {}
    for index, (entry, problem) in enumerate(zip(entries, problems)):
        if problem:
            results[index] = _verdict_row(entry, "FAILED", f"invalid entry: {problem}")
        else:
            blocks.setdefault((entry.get("host_code") or "").strip().upper(), []).append(index)

    for indexes in blocks.values():
        real_commit = db.commit
        if args.apply:
            db.commit = db.flush
        try:
            block = []
            for index in indexes:
                entry = entries[index]
                host = found.get((entry.get("host_code") or "").strip().upper())
                block.append(
                    process_entry_strict(
                        db, entry, host, found, company_id, args.apply,
                        update=args.update, no_sp_ids=no_sp_ids,
                    )
                )
            if args.apply:
                real_commit()
            for index, row in zip(indexes, block):
                results[index] = row
        except Exception as exc:  # the whole host is rolled back; the next host still loads
            db.rollback()
            for index in indexes:
                results[index] = _verdict_row(entries[index], "FAILED", str(exc)[:300])
        finally:
            if args.apply:
                del db.commit
    return [results[index] for index in range(len(entries))]


def write_verdicts(rows: list[dict], out: TextIO) -> None:
    for row in rows:
        out.write(f"{row['verdict']} | {row['host']} | {row['combo']} | p{row['page']} | {row['details']}\n")
    for verdict in VERDICT_ORDER:
        count = sum(1 for row in rows if row["verdict"] == verdict)
        if count:
            out.write(f"{verdict}: {count}\n")


# --------------------------------------------------------------------------- templates

#: The approved mock's type, in points. The combo's price is the figure of the tag; every
#: position's own list price is smaller.
SELL_COLOUR = "#8c7355"

#: One starter per combo shape: (template name, fixed parts, picks per group, upgrades). The name
#: is data (what marketing calls it); the layout is `position_template` for every one of them.
STARTER_SHAPES = [
    ("Combo 105 x 148: 5 picks and an upgrade", 0, [5], 1),
    ("Combo 105 x 148: 1 fixed part", 1, [], 0),
    ("Combo 105 x 148: 2 picks", 0, [2], 0),
    ("Combo 105 x 148: 2 fixed parts", 2, [], 0),
]
STARTER_FAMILY = "combo"
TAG_WIDTH_MM, TAG_HEIGHT_MM = 105, 148


def position_template(name: str, fixed: int, groups, upgrades: int) -> dict:
    """A 105 x 148 document with one row per position: the main product, `fixed` fixed parts,
    `groups[g]` picks of group g, and `upgrades` upgrades. Each row is a picture, a code and the
    position's own list price, all reading that position through `subjectSlot`.
    Unbound placeholders are empty on purpose: a position the line has not filled, or a combo with
    no price, prints nothing."""
    from scripts.tag_template_seed_docs import _Doc

    doc = _Doc(name, TAG_WIDTH_MM, TAG_HEIGHT_MM)

    def at_slot(slot: dict) -> None:
        doc.layers[-1]["props"]["subjectSlot"] = slot

    doc.text("combo-name", 4, 4, 97, 10, "", size=14, weight=700, slot="combo_name")
    def with_currency() -> None:
        doc.layers[-1]["props"]["showCurrency"] = True

    doc.text("list-price", 4, 17, 46, 7, "", size=11, slot="list_price")
    with_currency()
    doc.text("sell-price", 50, 14, 51, 14, "", size=24, weight=700, color=SELL_COLOUR, align="right", slot="sell_price")
    with_currency()

    slots = [{"kind": "main"}]
    slots += [{"kind": "fixed", "index": i} for i in range(fixed)]
    slots += [{"kind": "pick", "group": g, "index": i} for g, size in enumerate(groups) for i in range(size)]
    slots += [{"kind": "upgrade", "index": i} for i in range(upgrades)]
    top, bottom = 32, TAG_HEIGHT_MM - 8
    row_h = min(20, (bottom - top) / len(slots))
    for n, slot in enumerate(slots):
        y = top + n * row_h
        doc.image(f"pic-{n}", 4, y, row_h - 2, row_h - 2, slot="product_image")
        at_slot(slot)
        doc.text(f"code-{n}", 4 + row_h, y, 55, row_h - 2, "", size=9.5, slot="code")
        at_slot(slot)
        doc.text(f"price-{n}", 70, y, 31, row_h - 2, "", size=9.5, align="right", slot="list_price")
        at_slot(slot)
        with_currency()
    return doc.build()


def create_templates(db, company_id: str, apply: bool, out: TextIO) -> None:
    """Create and publish the starter templates (STARTER_SHAPES) in the chosen company.

    This script runs as its own process and never installs the company-scope listeners, so
    nothing stamps `company_id` or filters a query here: both are done explicitly. A starter
    already in this company is left exactly as it is. One of that name with NO company (an
    earlier run wrote them that way) is claimed for this company, its doc and versions
    untouched. A starter of that name in another company is not touched and not claimed.
    """
    from app.services.dealer_kit import tag_template_service
    from scripts.tag_template_seed_docs import print_size_of

    for name, fixed, groups, upgrades in STARTER_SHAPES:
        family = STARTER_FAMILY
        with company_scope(db, None):
            rows = db.query(TagTemplate).filter(TagTemplate.name == name).all()
        mine = [row for row in rows if row.company_id == company_id]
        unowned = [row for row in rows if row.company_id is None]
        if mine:
            out.write(f"template exists, left alone: {name}\n")
        elif unowned:
            if apply:
                with company_scope(db, None):
                    unowned[0].company_id = company_id
                    db.commit()
            out.write(f"{'claimed' if apply else 'would claim'} template with no company: {name}\n")
        elif not apply:
            out.write(f"would create and publish template: {name}\n")
        else:
            doc = position_template(name, fixed, groups, upgrades)
            with company_scope(db, frozenset({company_id})):
                created = tag_template_service.create_and_publish(
                    db, name=name, family=family, doc=doc, print_size=print_size_of(doc)
                )
                # create_and_publish builds the row with no company; stamp it here too, since
                # this process has no auto-stamp.
                created.company_id = company_id
                db.commit()
            out.write(f"created and published template: {name}\n")


# --------------------------------------------------------------------------- report / main


def published_templates(db, company_id: str) -> list[tuple[TagTemplate, dict]]:
    """The company's published price tag templates with what each reads from a combo."""
    with company_scope(db, frozenset({company_id})):
        rows = (
            db.query(TagTemplate)
            .filter(TagTemplate.company_id == company_id, TagTemplate.published_version_id.isnot(None))
            .filter(~TagTemplate.family.startswith(NON_PRICE_TAG_FAMILY_PREFIX))
            .all()
        )
        return [(row, template_needs(row.published_version.doc)) for row in rows]


def write_report(path: Path, rows: list[dict]) -> None:
    def safe(cell):
        # A cell a spreadsheet would run as a formula gets a leading quote.
        if isinstance(cell, str) and cell[:1] in ("=", "+", "-", "@", "\t", "\r"):
            return "'" + cell
        return cell

    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerow(REPORT_COLUMNS)
        for row in rows:
            writer.writerow(safe(row[column]) for column in REPORT_COLUMNS)


def main(argv: Optional[Sequence[str]] = None, db=None, out: Optional[TextIO] = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--file", required=True, help="the combos seed (JSON list)")
    parser.add_argument("--photos", default=None, help="folder the seed's photo names are relative to")
    parser.add_argument("--company", default="SRT", help="company code (default SRT)")
    parser.add_argument("--apply", action="store_true", help="write (default: dry run)")
    parser.add_argument("--report", default=None, help="report CSV path (default: next to the seed)")
    parser.add_argument("--update", action="store_true", help="with --apply: bring a differing combo to the seed")
    parser.add_argument("--link-templates", action="store_true", help="link the published templates that fit each combo")
    parser.add_argument("--strict", action="store_true", help="flyer seed rules: hold unmatched, aka, kind, one transaction per host")
    parser.add_argument("--templates", action="store_true", help="also create the starter templates")
    args = parser.parse_args(list(argv) if argv is not None else None)
    out = out or sys.stdout

    try:
        entries = read_seed(args.file)
    except Exception as exc:
        out.write(f"cannot read {args.file}: {exc}\n")
        return 1

    owns_session = db is None
    if owns_session:
        from app.database import SessionLocal

        db = SessionLocal()
    try:
        with company_scope(db, None):
            company = db.query(Company).filter(func.upper(Company.code) == args.company.upper()).first()
            company_id = company.id if company else None
        if company_id is None:
            out.write(f"unknown company code: {args.company}\n")
            return 1

        photos = Path(args.photos) if args.photos else None
        problems = [invalid_entry(entry, legacy_cap=not args.strict) for entry in entries]
        codes: set[str] = set()
        for entry, problem in zip(entries, problems):
            if problem:
                continue
            codes.add((entry.get("host_code") or "").strip())
            codes.update(part["code"] for part in wanted_parts(entry))
        found = products_by_code(db, company_id, codes)

        found_ids = [product.id for product in found.values()]
        no_sp_ids = (
            frozenset(db.execute(_no_selling_price_product_ids(found_ids)).scalars().all())
            if found_ids
            else frozenset()
        )
        published = published_templates(db, company_id) if args.link_templates else None

        register_audit_listeners()
        stamp_actor(AuditActor(actor_type="system", job_id=JOB_ID), db=db)
        rows = []
        try:
            with company_scope(db, frozenset({company_id})):
                if args.strict:
                    rows = run_strict(db, entries, problems, found, company_id, args, no_sp_ids, out)
                for entry, problem in ([] if args.strict else zip(entries, problems)):
                    if problem:
                        rows.append(
                            {**{column: "" for column in REPORT_COLUMNS},
                             "id": str(entry.get("id") or "") if isinstance(entry, dict) else "",
                             "status": "invalid_entry", "notes": problem}
                        )
                        continue
                    host = found.get((entry.get("host_code") or "").strip().upper())
                    try:
                        rows.append(
                            process_entry(
                                db, entry, host, found, photos, args.apply,
                                update=args.update, published=published, no_sp_ids=no_sp_ids,
                            )
                        )
                    except Exception as exc:  # one bad entry must not stop the rest
                        db.rollback()
                        rows.append(
                            {**{column: "" for column in REPORT_COLUMNS},
                             "id": str(entry.get("id") or ""), "status": "failed",
                             "guess": entry.get("guess") or "", "notes": str(exc)[:300]}
                        )
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            report = Path(args.report) if args.report else Path(args.file).with_name(
                f"{Path(args.file).stem}-report-{'apply' if args.apply else 'dryrun'}-{stamp}.csv"
            )
            # The report first: a template failure must not lose it.
            write_report(report, rows)
            if args.templates:
                create_templates(db, company_id, args.apply, out)
            if not args.apply:
                db.rollback()
        finally:
            clear_actor(db)

        if args.strict:
            write_verdicts(rows, out)
            out.write(f"report: {report}\n")
            if not args.apply:
                out.write("DRY RUN: nothing written. Run with --apply to load.\n")
            return 0
        for status in sorted({row["status"] for row in rows}):
            out.write(f"{status}: {sum(1 for row in rows if row['status'] == status)}\n")
        guesses = sum(1 for row in rows if row["guess"])
        out.write(f"entries with a guess: {guesses}\nreport: {report}\n")
        if not args.apply:
            out.write("DRY RUN: nothing written. Run with --apply to load.\n")
        return 0
    finally:
        if owns_session:
            db.close()


if __name__ == "__main__":
    sys.exit(main())
