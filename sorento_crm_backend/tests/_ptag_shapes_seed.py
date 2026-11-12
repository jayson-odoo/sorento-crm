"""Shared seed for the PRICETAG-COMBO-RENDER suites (not a test module).

One builder per combo shape of the reference flyer (UAC S1 to S5), with the exact system
product codes. Everything is created inside the caller's rolled-back blank schema with its
own FK chain; a product is looked up by code first, so two shapes in one test share the
product they have in common (SRTWB1419-BL hosts both S2 and S3).

Codes carry no product-type words in helper names: shapes are numbered.
"""
from __future__ import annotations

from decimal import Decimal

from app.models.product import Product

from tests import _ptag_combo_seed as seed

D = Decimal

GROUP_S1 = "Kitchen tap"
GROUP_S3 = "Tap colour"

S1_HOST = "SRTKS7061"
S1_OPTIONS = ["SRTKT1862SS", "SRTKT1863SS", "SRTKT1871SS", "SRTKT1880SS", "SRTKT1892SS"]
S1_UPGRADE = "SRTKT71SS"
S2_HOST = "SRTWB1419-BL"
S2_FIXED = "SRTWT7449-BL"
S3_HOST = "SRTWB1419-BL"
S3_OPTIONS = ["SRTWT7449-BL", "SRTWT7449-RG"]
S4_HOST = "SRTBF11829"
S4_FIXED = ["SRTMCB8083-BL", "SRTWT6203-GM"]


def prod(db, code: str, *, list_price: str = "100.00", company_id: str = seed.SORENTO):
    """The product with this exact code in the company, created on first use."""
    row = (
        db.query(Product)
        .filter(Product.product_code == code, Product.company_id == company_id)
        .first()
    )
    if row is not None:
        return row
    row = seed.product(db, "ZZS", list_price=list_price, company_id=company_id)
    row.product_code = code
    row.product_name = code
    db.flush()
    return row


def _shape(host, combo_row, by_code):
    return {"host": host, "combo": combo_row, **by_code}


def s1(db, name: str = "ZZT S1", **combo_fields):
    """Main + one choice group of five + one upgrade (top-up 150)."""
    host = prod(db, S1_HOST, list_price="2000.00")
    options = [
        prod(db, code, list_price=str(100 * (index + 1)) + ".00")
        for index, code in enumerate(S1_OPTIONS)
    ]
    upgrade = prod(db, S1_UPGRADE, list_price="600.00")
    parts = [{"product": item, "group": GROUP_S1} for item in options]
    parts.append({"product": upgrade, "is_upgrade": True, "topup_amount": D("150.00")})
    combo_row = seed.combo(db, host, name, parts=parts, **combo_fields)
    return {
        "host": host,
        "combo": combo_row,
        "options": options,
        "upgrade": upgrade,
        "group": GROUP_S1,
    }


def s2(db, name: str = "ZZT S2", **combo_fields):
    """Main + one fixed part (the free item is a template picture, not data)."""
    host = prod(db, S2_HOST, list_price="500.00")
    fixed = prod(db, S2_FIXED, list_price="150.00")
    combo_row = seed.combo(db, host, name, parts=[{"product": fixed}], **combo_fields)
    return {"host": host, "combo": combo_row, "fixed": [fixed]}


def s3(db, name: str = "ZZT S3", **combo_fields):
    """Main + one choice group of two finishes."""
    host = prod(db, S3_HOST, list_price="500.00")
    options = [prod(db, code, list_price="150.00") for code in S3_OPTIONS]
    parts = [{"product": item, "group": GROUP_S3} for item in options]
    combo_row = seed.combo(db, host, name, parts=parts, **combo_fields)
    return {"host": host, "combo": combo_row, "options": options, "group": GROUP_S3}


def s4(db, name: str = "ZZT S4", **combo_fields):
    """Main + two fixed parts, nothing to pick."""
    host = prod(db, S4_HOST, list_price="3000.00")
    fixed = [prod(db, code, list_price="400.00") for code in S4_FIXED]
    parts = [{"product": item} for item in fixed]
    combo_row = seed.combo(db, host, name, parts=parts, **combo_fields)
    return {"host": host, "combo": combo_row, "fixed": fixed}


def pick_parts(group: str, *picked):
    """Resolved line parts sharing a group role, in the order given (pick order)."""
    return [{"product_id": item.id, "role": group} for item in picked]


def fixed_parts(*fixed):
    return [{"product_id": item.id} for item in fixed]


def upgrade_part(upgrade):
    """The dealer ticked the Upgrade row: a resolved part with the upgrade row's role."""
    return {"product_id": upgrade.id, "role": "Upgrade"}


def codes(rows) -> list[str]:
    return [row["code"] for row in rows]
