"""PRICETAG-COMBO-RENDER K4: what a tag template reads from a combo, and whether a combo fits.

Pure functions. A layer points at a position with ``props.subjectSlot``
(``main`` | ``fixed`` | ``pick`` | ``upgrade``); the template's needs are the
highest position it reads, per kind. The same words are built on the frontend
(``lib/dealer-kit/combo-slots.ts``).
"""
from __future__ import annotations

import re
from typing import Optional


#: A stored document is data: positions beyond these are not real and are skipped, so a damaged or
#: hostile document cannot make the list long.
MAX_GROUP = 32
MAX_INDEX = 64


def _position(value, limit: int) -> Optional[int]:
    """`value` when it is a real int (not a bool) in [0, limit), else None."""
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < limit:
        return None
    return value


_TOKEN = re.compile(r"\{\{\s*([A-Za-z0-9_.]+)\s*\}\}")


def _token_slot(path: str) -> Optional[dict]:
    """The 0-based position a ``slot.<kind>.<n>[.<k>].<field>`` token names (1-based in the text),
    or None for any other token or a malformed one. The same grammar as ``parseSlotToken`` in
    ``lib/dealer-kit/merge-fields.ts``."""
    parts = path.split(".")
    if len(parts) < 4 or parts[0] != "slot" or parts[1] not in ("fixed", "upgrade", "pick"):
        return None  # `slot.main.<field>` is the main product, which is never counted
    kind, numbers = parts[1], parts[2:-1]
    if not all(re.fullmatch(r"[1-9][0-9]*", n) for n in numbers):
        return None
    n = [int(x) - 1 for x in numbers]
    if kind in ("fixed", "upgrade") and len(n) == 1:
        return {"kind": kind, "index": n[0]}
    if kind == "pick" and len(n) == 2:
        return {"kind": "pick", "group": n[0], "index": n[1]}
    return None


def _slots_of(layer) -> list:
    """Every position a layer reads: its ``subjectSlot`` and any ``{{slot.*}}`` token in its text."""
    props = layer.get("props") if isinstance(layer, dict) else None
    found = []
    slot = props.get("subjectSlot") if isinstance(props, dict) else None
    if isinstance(slot, dict):
        found.append(slot)
    if isinstance(layer, dict):
        for text in (layer.get("text_override"), props.get("text") if isinstance(props, dict) else None):
            if isinstance(text, str):
                found += [s for s in (_token_slot(m) for m in _TOKEN.findall(text)) if s]
    return found


def template_needs(doc) -> dict:
    fixed = 0
    upgrades = 0
    groups: list[int] = []
    layers = doc.get("layers") if isinstance(doc, dict) else None
    for layer in layers if isinstance(layers, list) else []:
        for slot in _slots_of(layer):
            kind = slot.get("kind")
            index = _position(slot.get("index"), MAX_INDEX)
            if index is None:
                continue
            if kind == "fixed":
                fixed = max(fixed, index + 1)
            elif kind == "upgrade":
                upgrades = max(upgrades, index + 1)
            elif kind == "pick":
                group = _position(slot.get("group"), MAX_GROUP)
                if group is None:
                    continue
                while len(groups) <= group:
                    groups.append(0)
                groups[group] = max(groups[group], index + 1)
    return {"fixed": fixed, "groups": groups, "upgrades": upgrades}


def combo_shape(combo) -> dict:
    """A combo's fixed-part count, choice groups (name, option count) in part order, upgrade count."""
    fixed = 0
    upgrades = 0
    sizes: dict[str, int] = {}
    # Counted by the part ROWS, never through the joined `part_product`: the company-scope loader
    # criteria on a scoped session reach that join and return None for a product the session
    # cannot see, which used to drop every part. `part_product_id` is NOT NULL with a RESTRICT
    # foreign key, so a row always has its product.
    for part in combo.parts or []:
        if part.is_upgrade:
            upgrades += 1
        elif part.choice_group:
            sizes[part.choice_group] = sizes.get(part.choice_group, 0) + 1
        else:
            fixed += 1
    return {
        "fixed": fixed,
        "groups": [{"role": role, "size": size} for role, size in sizes.items()],
        "upgrades": upgrades,
    }


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def fit_reason(needs: dict, shape: dict) -> Optional[str]:
    """None when the combo fits, else the first shortfall in the combo's words.

    Checked in this order: choice groups, fixed parts, upgrades. A choice group and the upgrades
    are at most what the combo has (a pick of k from n, an offer); fixed parts are always in the
    box, so a template must print every one.

    A plain template (no combo position read at all) prints the combo as one product and fits
    every combo (PRICETAG-COMBO-FIT-HOTFIX)."""
    if not needs["fixed"] and not needs["upgrades"] and not any(n > 0 for n in needs["groups"]):
        return None
    for index, need in enumerate(needs["groups"]):
        if need <= 0:
            continue
        if index >= len(shape["groups"]):
            if not shape["groups"]:
                return "Needs a choice group; this combo has none"
            return f"Needs choice group {index + 1}; this combo has {len(shape['groups'])}"
        group = shape["groups"][index]
        if need > group["size"]:
            return f"Needs {need} from {group['role']}; this combo has {group['size']}"
    if needs["fixed"] < shape["fixed"]:
        return f"Prints {needs['fixed']} of this combo's {_plural(shape['fixed'], 'fixed part')}"
    if needs["fixed"] > shape["fixed"]:
        return f"Needs {_plural(needs['fixed'], 'fixed part')}; this combo has {shape['fixed']}"
    if needs["upgrades"] > shape["upgrades"]:
        return f"Needs {_plural(needs['upgrades'], 'upgrade')}; this combo has {shape['upgrades']}"
    return None


def missing_positions(needs: dict, combo, parts) -> list[str]:
    """What a line still owes the template it prints with, as the form words it (N1).

    ``parts`` is the line's ``(role, product_id)`` pairs (``product_id`` None for an open row).
    Judged against the template's needs and the combo, not against the rows present: a deleted
    choice group row owes every pick. A group the template reads one from is satisfied by an open
    row (marketing lists the options); upgrades are never checked, the tag prints the combo's own.
    """
    out: list[str] = []
    rows = [(role, product_id) for role, product_id in parts]
    groups = combo_shape(combo)["groups"]
    for index, need in enumerate(needs.get("groups") or []):
        if need <= 0 or index >= len(groups):
            continue
        role = groups[index]["role"]
        mine = [row for row in rows if row[0] == role]
        picked = sum(1 for _role, product_id in mine if product_id)
        if picked >= need or (mine and need == 1):
            continue
        out.append(f"{role}: pick {need - picked} more.")
    fixed = [
        p for p in combo.parts or [] if not p.is_upgrade and not p.choice_group
    ]
    held = {product_id for _role, product_id in rows if product_id}
    for part in fixed[: needs.get("fixed") or 0]:
        if part.part_product_id not in held:
            code = part.part_product.product_code if part.part_product is not None else ""
            out.append(f"Template needs {code}.")
    return out
