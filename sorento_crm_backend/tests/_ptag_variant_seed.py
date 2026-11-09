"""Shared seed for the PRICETAG-UPGRADE-VARIANTS suites (not a test module).

Builds the SRTWC8354-SH family and the SRTKS2432 sink combo inside the caller's rolled-back
blank schema, each with its own FK chain (CI's database is empty), spec rows in the production
shape (`{key: {"value": ...}}`). Specs follow the plan:
trap_length 250/150/200/180/250/150/200/300, trap_type s_trap except -P p_trap, seat_material uf
on the -UF branch.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from app.models.product_spec import ProductSpecifications, ProductSpecRegistry

from tests import _ptag_combo_seed as seed
from tests import _ptag_shapes_seed as shapes

D = Decimal
SORENTO = seed.SORENTO

BASE = "SRTWC8354-SH"
#: code -> (parent code, trap_length, trap_type, seat_material or None, list price)
FAMILY = {
    "SRTWC8354-SH": (None, 250, "s_trap", None, "1750.00"),
    "SRTWC8354-SH-150": (BASE, 150, "s_trap", None, "1750.00"),
    "SRTWC8354-SH-200": (BASE, 200, "s_trap", None, "1750.00"),
    "SRTWC8354-SH-P": (BASE, 180, "p_trap", None, "1750.00"),
    "SRTWC8354-SH-UF": (BASE, 250, "s_trap", "uf", "1750.00"),
    "SRTWC8354-SH-UF-150": ("SRTWC8354-SH-UF", 150, "s_trap", "uf", "1750.00"),
    "SRTWC8354-SH-UF-200": ("SRTWC8354-SH-UF", 200, "s_trap", "uf", "1750.00"),
    "SRTWC8354-SH-UF-300": ("SRTWC8354-SH-UF", 300, "s_trap", "uf", "1750.00"),
}
MEMBER_CODES = sorted(code for code in FAMILY if code != BASE)


def registry(db):
    """The three registry keys the family's specs read (own rows; the blank schema has none)."""
    out = {}
    for key, data_type, allowed, unit in (
        ("trap_length", "numeric", [], "mm"),
        ("trap_type", "enum", ["s_trap", "p_trap"], None),
        ("seat_material", "enum", ["uf", "pp"], None),
    ):
        row = db.query(ProductSpecRegistry).filter_by(spec_key=key).first()
        if row is None:
            row = ProductSpecRegistry(
                id=str(uuid.uuid4()), spec_key=key, label=key.replace("_", " ").title(),
                data_type=data_type, allowed_values=allowed, unit=unit, is_active=True,
                source="user",
            )
            db.add(row)
            db.flush()
        out[key] = row
    return out


#: The unit the production writer stores beside a measured value.
UNITS = {"trap_length": "mm"}


def set_specs(db, product, **values):
    """Write a product's reviewed spec row in the shape production stores
    (`{key: {"value": ..., "unit": ...}}`, `product_spec_write`); a value passed as a dict is
    taken as already shaped."""
    shaped = {
        key: value
        if isinstance(value, dict)
        else {"value": value, **({"unit": UNITS[key]} if key in UNITS else {})}
        for key, value in values.items()
    }
    provenance = {key: {"source": "user"} for key in shaped}
    row = db.query(ProductSpecifications).filter_by(product_id=product.id).first()
    if row is None:
        row = ProductSpecifications(
            id=str(uuid.uuid4()), product_id=product.id, values=shaped, provenance=provenance
        )
        db.add(row)
    else:
        row.values = shaped
        row.provenance = provenance
    db.flush()
    return row


def family(db, *, company_id=SORENTO):
    """`{code: product}` for the SRTWC8354 family (owner ruling 9 Nov ~16:05: "All variants" reads
    `family_code`, derived from the code on write). No variant links are set, as on the dev copy."""
    registry(db)
    products: dict[str, object] = {}
    for code, (parent, length, trap, seat, price) in FAMILY.items():
        item = shapes.prod(db, code, list_price=price, company_id=company_id)
        products[code] = item
    for code, (parent, length, trap, seat, price) in FAMILY.items():
        item = products[code]
        values = {"trap_length": length, "trap_type": trap}
        if seat:
            values["seat_material"] = seat
        set_specs(db, item, **values)
    db.flush()
    return products


def sink_combo(db):
    """SRTKS2432 host (LP 1150), fixed SRTKT1862SS, upgrade SRTKT71SS (top-up 150, LP 440), combo SP 949."""
    host = shapes.prod(db, "SRTKS2432", list_price="1150.00")
    fixed = shapes.prod(db, "SRTKT1862SS", list_price="285.00")
    upgrade = shapes.prod(db, "SRTKT71SS", list_price="440.00")
    combo_row = seed.combo(
        db, host, "ZZT sink pack",
        parts=[{"product": fixed}, {"product": upgrade, "is_upgrade": True, "topup_amount": D("150.00")}],
        list_price=D("1150.00"), sell_price=D("949.00"),
    )
    return {"host": host, "combo": combo_row, "fixed": fixed, "upgrade": upgrade}
