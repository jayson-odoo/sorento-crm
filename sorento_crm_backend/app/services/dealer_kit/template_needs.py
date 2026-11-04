"""PRICETAG-COMBO-RENDER K4: what a tag template reads from a combo, and whether a combo fits.

Pure functions. A layer points at a position with ``props.subjectSlot``
(``main`` | ``fixed`` | ``pick`` | ``upgrade``); the template's needs are the
highest position it reads, per kind. The same words are built on the frontend
(``lib/dealer-kit/combo-slots.ts``).
"""
from __future__ import annotations

from typing import Optional


def template_needs(doc: Optional[dict]) -> dict:
    fixed = 0
    upgrades = 0
    groups: list[int] = []
    for layer in (doc or {}).get("layers") or []:
        slot = ((layer or {}).get("props") or {}).get("subjectSlot")
        if not isinstance(slot, dict):
            continue
        kind = slot.get("kind")
        index = slot.get("index")
        if not isinstance(index, int) or index < 0:
            continue
        if kind == "fixed":
            fixed = max(fixed, index + 1)
        elif kind == "upgrade":
            upgrades = max(upgrades, index + 1)
        elif kind == "pick":
            group = slot.get("group")
            if not isinstance(group, int) or group < 0:
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
    for part in combo.parts or []:
        if part.part_product is None:
            continue
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
    """None when the combo has what the template reads, else the first shortfall in the combo's words."""
    if needs["fixed"] > shape["fixed"]:
        return f"Needs {_plural(needs['fixed'], 'fixed part')}; this combo has {shape['fixed']}"
    for index, need in enumerate(needs["groups"]):
        if need <= 0:
            continue
        if index >= len(shape["groups"]):
            return f"Needs choice group {index + 1}; this combo has {len(shape['groups'])}"
        group = shape["groups"][index]
        if need > group["size"]:
            return f"Needs {need} from choice group {index + 1}; {group['role']} has {group['size']}"
    if needs["upgrades"] > shape["upgrades"]:
        return f"Needs {_plural(needs['upgrades'], 'upgrade')}; this combo has {shape['upgrades']}"
    return None
