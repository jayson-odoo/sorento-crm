"""Gold set for the price tag paste extraction (PRICETAG-LPSP, AC-17).

Eight messages a salesperson could paste into the price tag form's AI extract:
the owner's 4 Nov paste split by section (four messages) and four requests
re-typed from real data (E2, E3, E3b, E4/E5 of the card). The outlet name is
fake everywhere; no real dealer, contact or phone number appears.

Each case carries:

* ``text``       - the pasted message;
* ``model_json`` - the answer a well-behaved model gives (what the stubbed
                   provider returns in the offline run; what the opt-in live run
                   is checked against by its parsed lines);
* ``expected``   - the parsed lines `_extract_products` must produce from it.
                   A key absent from an expected dict is NOT asserted, so an
                   unmatched row pins only what the contract promises for it.

``CATALOGUE`` is every product code the cases resolve (seeded fresh by the
test, scratch schema); ``COMBOS`` the stored combos (host + fixed parts) that a
"+" line may match. A "+" line with no stored combo is an UNMATCHED row
(owner ruling 4 Nov): ``match`` None, ``combo_id`` None.

Expected keys: ``product_code`` (canonical, or the raw text on a miss),
``match``, ``price_type``, ``typed_list_price``, ``typed_sell_price``,
``set_parts`` (canonical part codes, in the order written), ``combo_name``
(the stored combo's name, or None), ``notes_contains``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

OUTLET = "Outlet Example Sdn Bhd"

# code -> list price. Every code a case resolves; nothing else is seeded.
CATALOGUE: dict[str, str] = {
    # G1 / G4: the five distinct SRTSH2626 finishes and plain items
    "SRTSH2626-GY": "108.00",
    "SRTSH2626-GRY": "120.00",
    "SRTSH2626-RG": "230.00",
    "SRTSH2626-GM": "190.00",
    "SRTSS3240": "85.00",
    "SRTW1200-BL": "150.00",
    "SRTSS5726": "99.00",
    "SRTSS5726-GM": "109.00",
    "SRTKS1101": "310.00",
    "SRTKS1102-BL": "320.00",
    "SRTWB3301": "270.00",
    "SRTMR502-BL": "140.00",
    "SRTWT7445": "260.00",
    # G2: the four sets of the owner's paste (LP is the exact sum of the parts)
    "SRTBF11850": "1150.00",
    "SRTMCB8083-BL": "610.00",
    "SRTWT6204-MBL": "395.00",
    "SRTBF11839": "1500.00",
    "SRTWT5904": "700.00",
    "SRTMCB8081-WH": "479.00",
    "SRTBF11840": "1700.00",
    "SRTWT8301-GMB": "611.00",
    "SRTBF11851": "900.00",
    "SRTWT6201": "485.00",
    # G3: singles
    "SRTWC8518-SH": "520.00",
    "SRTWC8519-SH": "580.00",
    "SRTWC8520-SH": "480.00",
    "SRTWC8521-SH": "610.00",
    "SRTWC8522-SH": "640.00",
    "SRTWC8523-SH": "700.00",
    "SRTWC8524-SH": "720.00",
    "SRTWC8525-SH": "760.00",
    # the family of the unresolvable "Srtwc8152 (6,8,10,P)": none of -6/-8/-10/-P exists
    "SRTWC8152-SH": "800.00",
    "SRTWC8152-SH-150": "810.00",
    "SRTWC8152-RL-P": "830.00",
    # G5 / G6 / G7 / G8
    "SRTWC286-SH": "330.00",
    "SRTWT8203": "410.00",
    "SRTSH6641": "290.00",
    "SRTBF31414": "1400.00",
    "SRTBF11831": "1000.00",
    "SRTWT6202-RG": "300.00",
    "SRTWC7614": "560.00",
    "SRTBF11709": "830.00",
    "CBNSK2001": "450.00",
    "SRTWC8066-S-UF": "650.00",
}

# Stored combos: name -> host + FIXED parts. The names follow the catalogue's
# "HOST + PART + PART" convention.
COMBOS: list[dict[str, Any]] = [
    {
        "name": "SRTBF11850 + SRTMCB8083-BL + SRTWT6204-MBL",
        "host": "SRTBF11850",
        "parts": ["SRTMCB8083-BL", "SRTWT6204-MBL"],
    },
    {
        "name": "SRTBF11839 + SRTWT5904 + SRTMCB8081-WH",
        "host": "SRTBF11839",
        "parts": ["SRTWT5904", "SRTMCB8081-WH"],
    },
    {
        "name": "SRTBF11831 + SRTMR502-BL + SRTWT6202-RG",
        "host": "SRTBF11831",
        "parts": ["SRTMR502-BL", "SRTWT6202-RG"],
    },
]


@dataclass(frozen=True)
class GoldCase:
    id: str
    text: str
    model_json: dict[str, Any]
    expected: list[dict[str, Any]] = field(default_factory=list)


def _entry(code, price_type=None, list_price=None, sell_price=None, set_codes=None, notes=None):
    return {
        "product_code": code,
        "product_name": None,
        "notes": notes,
        "price_type": price_type,
        "typed_list_price": list_price,
        "typed_sell_price": sell_price,
        "set_codes": set_codes or [],
    }


def _exp(code, *, price_type=None, typed_list=None, typed_sell=None, match="product",
         set_parts=None, combo_name=None, notes_contains=None):
    row: dict[str, Any] = {
        "product_code": code,
        "match": match,
        "price_type": price_type,
        "typed_list_price": typed_list,
        "typed_sell_price": typed_sell,
        "combo_name": combo_name,
    }
    if set_parts is not None:
        row["set_parts"] = set_parts
    if notes_contains is not None:
        row["notes_contains"] = notes_contains
    return row


# --------------------------------------------------------------------------- G1
G1 = GoldCase(
    id="owner_lp_block",
    text=(
        f"{OUTLET}\nLP\n"
        "Srtsh2626 GY\nSrtsh2626 GRY\nSrtsh2626 RG\nSrtsh2626 GM\n"
        "SRTSS3240\nSrtw1200 BL\nSrtss5726\nSrtss5726 GM\n"
    ),
    model_json={
        "products": [
            _entry("Srtsh2626 GY", "list"),
            _entry("Srtsh2626 GRY", "list"),
            _entry("Srtsh2626 RG", "list"),
            _entry("Srtsh2626 GM", "list"),
            _entry("SRTSS3240", "list"),
            _entry("Srtw1200 BL", "list"),
            _entry("Srtss5726", "list"),
            _entry("Srtss5726 GM", "list"),
        ]
    },
    expected=[
        _exp("SRTSH2626-GY", price_type="list"),
        _exp("SRTSH2626-GRY", price_type="list"),
        _exp("SRTSH2626-RG", price_type="list"),
        _exp("SRTSH2626-GM", price_type="list"),
        _exp("SRTSS3240", price_type="list"),
        _exp("SRTW1200-BL", price_type="list"),
        _exp("SRTSS5726", price_type="list"),
        _exp("SRTSS5726-GM", price_type="list"),
    ],
)

# --------------------------------------------------------------------------- G2
G2 = GoldCase(
    id="owner_sp_sets",
    text=(
        "SP\n"
        "Srtbf11850 +srtmcb8083 BL + srtwt6204 MBL  LP rm2155 SP RM1729\n"
        "Srtbf11839 + srtwt5904 + srtmcb8081 WH  LP rm2679 SP RM2149\n"
        "Srtbf11840 + srtwt8301 GMB + srtmcb8083 BL  LP rm2911 SP RM2299 LP rm2149\n"
        "Srtbf11851 + srtwt6201 + srtmcb8081 WH  LP rm1864 SP RM1499\n"
    ),
    model_json={
        "products": [
            _entry("Srtbf11850", "selling", 2155, 1729, ["srtmcb8083 BL", "srtwt6204 MBL"]),
            _entry("Srtbf11839", "selling", 2679, 2149, ["srtwt5904", "srtmcb8081 WH"]),
            _entry("Srtbf11840", "selling", 2911, 2299, ["srtwt8301 GMB", "srtmcb8083 BL"],
                   notes="second LP rm2149"),
            _entry("Srtbf11851", "selling", 1864, 1499, ["srtwt6201", "srtmcb8081 WH"]),
        ]
    },
    expected=[
        # stored combos: a matched row carrying the combo
        _exp("SRTBF11850", price_type="selling", typed_list=2155.0, typed_sell=1729.0,
             set_parts=["SRTMCB8083-BL", "SRTWT6204-MBL"],
             combo_name="SRTBF11850 + SRTMCB8083-BL + SRTWT6204-MBL"),
        _exp("SRTBF11839", price_type="selling", typed_list=2679.0, typed_sell=2149.0,
             set_parts=["SRTWT5904", "SRTMCB8081-WH"],
             combo_name="SRTBF11839 + SRTWT5904 + SRTMCB8081-WH"),
        # no stored combo for these two: UNMATCHED rows, the user picks by hand
        _exp(None, match=None, price_type="selling", typed_list=2911.0, typed_sell=2299.0,
             notes_contains="2149"),
        _exp(None, match=None, price_type="selling", typed_list=1864.0, typed_sell=1499.0),
    ],
)

# --------------------------------------------------------------------------- G3
_SINGLES = [
    ("Srtwc8518 SH", "SRTWC8518-SH", 499.0),
    ("Srtwc8519 SH", "SRTWC8519-SH", 549.0),
    ("Srtwc8521 SH", "SRTWC8521-SH", 569.0),
    ("Srtwc8522 SH", "SRTWC8522-SH", 599.0),
    ("Srtwc8523 SH", "SRTWC8523-SH", 649.0),
    ("Srtwc8524 SH", "SRTWC8524-SH", 669.0),
    ("Srtwc8525 SH", "SRTWC8525-SH", 699.0),
]
G3 = GoldCase(
    id="owner_sp_singles",
    text=(
        "SP\n"
        + "".join(f"{raw} SP Rm{int(price)}\n" for raw, _code, price in _SINGLES)
        + "Srtwc8520 SH SP Rm449 (was SP Rm479)\n"
        + "Srtwc8152 (6,8,10,P) SP Rm729\n"
    ),
    model_json={
        "products": [
            *[_entry(raw, "selling", None, price) for raw, _code, price in _SINGLES],
            _entry("Srtwc8520 SH", "selling", None, 449, notes="was SP Rm479"),
            _entry("Srtwc8152 (6,8,10,P)", "selling", None, 729),
        ]
    },
    expected=[
        *[
            _exp(code, price_type="selling", typed_sell=price)
            for _raw, code, price in _SINGLES
        ],
        _exp("SRTWC8520-SH", price_type="selling", typed_sell=449.0, notes_contains="479"),
        # no -6/-8/-10/-P exists: one unresolved row, never a silent guess
        _exp("Srtwc8152 (6,8,10,P)", match=None, price_type="selling", typed_sell=729.0),
    ],
)

# --------------------------------------------------------------------------- G4
G4 = GoldCase(
    id="owner_final_lp",
    text="LP\nSrtks1101\nSrtks1102 BL\nSrtwb3301\nSrtmr502 BL\nSrtwt7445\n",
    model_json={
        "products": [
            _entry("Srtks1101", "list"),
            _entry("Srtks1102 BL", "list"),
            _entry("Srtwb3301", "list"),
            _entry("Srtmr502 BL", "list"),
            _entry("Srtwt7445", "list"),
        ]
    },
    expected=[
        _exp("SRTKS1101", price_type="list"),
        _exp("SRTKS1102-BL", price_type="list"),
        _exp("SRTWB3301", price_type="list"),
        _exp("SRTMR502-BL", price_type="list"),
        _exp("SRTWT7445", price_type="list"),
    ],
)

# --------------------------------------------------------------------------- G5 (E2)
G5 = GoldCase(
    id="e2_no_header",
    text=f"{OUTLET}\nSRTWC286-SH\nSRTWT7445\n",
    model_json={"products": [_entry("SRTWC286-SH"), _entry("SRTWT7445")]},
    expected=[
        _exp("SRTWC286-SH", price_type=None),
        _exp("SRTWT7445", price_type=None),
    ],
)

# --------------------------------------------------------------------------- G6 (E3)
G6 = GoldCase(
    id="e3_selling_no_prices",
    text="SP\nSRTWT8203\nSRTSH6641\n",
    model_json={
        "products": [_entry("SRTWT8203", "selling"), _entry("SRTSH6641", "selling")]
    },
    expected=[
        _exp("SRTWT8203", price_type="selling"),
        _exp("SRTSH6641", price_type="selling"),
    ],
)

# --------------------------------------------------------------------------- G7 (E3b)
G7 = GoldCase(
    id="e3b_mixed_with_combo",
    text=(
        "SP\n"
        "SRTBF31414 5 in 1 combo Rm1299\n"
        "SRTBF11831 + SRTMR502-BL + SRTWT6202-RG  SP Rm1099\n"
        "srtwc7614\n"
        "LP\n"
        "SRTBF11709\n"
    ),
    model_json={
        "products": [
            _entry("SRTBF31414", "selling", None, 1299, notes="5 in 1 combo"),
            _entry("SRTBF11831", "selling", None, 1099, ["SRTMR502-BL", "SRTWT6202-RG"]),
            _entry("srtwc7614", "selling"),
            _entry("SRTBF11709", "list"),
        ]
    },
    expected=[
        _exp("SRTBF31414", price_type="selling", typed_sell=1299.0, combo_name=None),
        _exp("SRTBF11831", price_type="selling", typed_sell=1099.0,
             set_parts=["SRTMR502-BL", "SRTWT6202-RG"],
             combo_name="SRTBF11831 + SRTMR502-BL + SRTWT6202-RG"),
        _exp("SRTWC7614", price_type="selling"),
        _exp("SRTBF11709", price_type="list"),
    ],
)

# --------------------------------------------------------------------------- G8 (E4, E5)
G8 = GoldCase(
    id="e4_e5_typed_selling",
    text=(
        f"{OUTLET}\nSP\n"
        "CBNSK2001\n"
        "Srtwc8066 S UF SP Rm599\n"
    ),
    model_json={
        "products": [
            _entry("CBNSK2001", "selling"),
            _entry("Srtwc8066 S UF", "selling", None, 599),
        ]
    },
    expected=[
        _exp("CBNSK2001", price_type="selling", typed_sell=None),
        _exp("SRTWC8066-S-UF", price_type="selling", typed_sell=599.0),
    ],
)

CASES: list[GoldCase] = [G1, G2, G3, G4, G5, G6, G7, G8]
