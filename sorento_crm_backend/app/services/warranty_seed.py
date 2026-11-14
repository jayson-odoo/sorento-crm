"""After-sales P2: seed Sorento Warranty Policy v15 (31 kinds, the policy row, 41 terms, 2 kind rules).

Source: `app/data/warranty_policy_sorento_v15.txt` (v15, March 2026), clause 6 item by item. Policy v15
is backdated to 2000-01-01 and open ended (owner ruling: v15 is retroactive, the only policy on record);
a later version must CLOSE this window (the policy supersede action), not edit this row.

Idempotent on stable keys and "set where it differs": kinds on `code`, the policy on (company, version),
terms on (policy, kind, part), rules on (kind, type, value), defect options on (set, value). Kinds, rules
and the defect set are shared by every company; the policy and its terms are per company. Flushes, never
commits: the caller decides.
"""
from __future__ import annotations

import logging
import uuid
from datetime import date
from pathlib import Path
from typing import Optional

from app.models.lookup import LookupOption, LookupSet
from app.models.warranty import WarrantyKindRule, WarrantyPolicy, WarrantyProductKind, WarrantyTerm

logger = logging.getLogger(__name__)

POLICY_VERSION = "v15"
POLICY_TEXT_PATH = Path(__file__).resolve().parents[1] / "data" / "warranty_policy_sorento_v15.txt"
POLICY_EFFECTIVE_FROM = date(2000, 1, 1)
POLICY_EFFECTIVE_TO = None

DEFECT_TYPE_SET_KEY = "after_sales_defect_type"
DEFECT_TYPE_SET_NAME = "After-sales defect type"

CRACK = "Crack line"
LEAK = "Leakage"
RUST = "Rust"
HOLDER = "Broken holder"

# (value, label, where it comes from)
DEFECT_TYPE_SEED = (
    (CRACK, CRACK, "clause 6, every Ceramic Body row: 'crack line and leaking ONLY'"),
    (LEAK, LEAK, "clause 6, the same rows"),
    (RUST, RUST, "clause 6 items 21 and 23: 'Anti-Rust' / 'Rust Resistant'"),
    (HOLDER, HOLDER, "the policy's golden set row 3, a defect the lifetime body excludes"),
)

MONTHS = {
    "1 year": 12,
    "2 years": 24,
    "3 years": 36,
    "5 years": 60,
    "10 years": 120,
    "25 years": 300,
}

LIFETIME_CERAMIC_QUALIFICATION = "Lifetime Warranty on crack line and leaking ONLY."
LIFETIME_CERAMIC_EXCLUSION = (
    "Any crack line caused by external force and/or willful act is excluded."
)

_INSTALLATION_INCLUDED = "Installation is included."
_INSTALLATION_EXCLUDED = "Installation is excluded."


# ---------------------------------------------------------------------------- #
# Clause 6, item by item.                                                        #
#                                                                                #
# `no` is the document's own numbering, kept as sort_order so any row can be found #
# in the PDF in one step. `source_cell` is the Product(s) column verbatim,         #
# INCLUDING the parts of it the Kind name does not carry.                         #
# ---------------------------------------------------------------------------- #

# (no, code, name, consumer_label (unused), source_cell)
KIND_SEED = (
    (1, "water_closet", "Water Closet", "Water Closet", "Water Closet"),
    (2, "urinal_bowl", "Urinal Bowl", "Urinal Bowl", "Urinal Bowl"),
    (3, "squatting_pan", "Squatting Pan", "Squatting Pan", "Squatting Pan"),
    (4, "electronic_seat_cover", "Electronic Seat Cover", "Electronic Seat Cover",
     "Electronic Seat Cover"),
    (5, "intelligent_water_closet", "Intelligent Water Closet", "Intelligent Water Closet",
     "Intelligent Water Closet"),
    (6, "tankless_water_closet", "Tankless Water Closet", "Tankless Water Closet",
     "Tankless Water Closet"),
    (7, "wash_basin", "Wash Basin", "Wash Basin", "Wash Basin"),
    (8, "led_mirror", "LED Mirror", "LED Mirror", "LED Mirror"),
    (9, "bathroom_furniture", "Bathroom Furniture", "Bathroom Furniture",
     "Bathroom Furniture Selected Models *Honeycomb Series"),
    (10, "mirror_cabinet", "Mirror Cabinet", "Mirror Cabinet",
     "Mirror Cabinet Selected Models SRTMCB8071-BL, SRTMCB6071-BL, SRTMCB6070-BL, "
     "SRTMCB5060-BL, SRTMCB5061-BL, SRTMCB6066-BL, SRTMCB4561-BL, SRTMCB4560-BL"),
    # Item 11's Product(s) cell ends at "Cold" in the source document and reads as
    # truncated. Transcribed as it reads; see NOT_IN_THE_DOCUMENT.
    (11, "concealed_shower_mixer_cold", "Concealed Shower Mixer & Cold",
     "Concealed Shower Mixer & Cold", "Concealed Shower Mixer & Cold"),
    (12, "kitchen_bathroom_cold_tap", "Kitchen & Bathroom Cold Tap",
     "Kitchen & Bathroom Cold Tap", "Kitchen & Bathroom Cold Tap"),
    (13, "stop_valve", "Stop Valve", "Stop Valve", "Stop Valve"),
    (14, "bib_hose_two_way_tap_bidet_set",
     "Bib Tap, Hose Bib Tap, Two Way Tap and Two Way Bidet Set",
     "Bib Tap, Hose Bib Tap, Two Way Tap and Two Way Bidet Set",
     "Bib Tap, Hose Bib Tap, Two Way Tap and Two Way Bidet Set"),
    (15, "exposed_mixer_shower_set", "Exposed Mixer Shower Set", "Exposed Mixer Shower Set",
     "Exposed Mixer Shower Set"),
    (16, "conceal_bath_shower_mixer", "Conceal Bath and Shower Mixer",
     "Conceal Bath and Shower Mixer", "Conceal Bath and Shower Mixer"),
    (17, "conceal_bathroom_mixer", "Conceal Bathroom Mixer", "Conceal Bathroom Mixer",
     "Conceal Bathroom Mixer"),
    (18, "kitchen_bathroom_mixer_tap", "Kitchen & Bathroom Mixer Tap",
     "Kitchen & Bathroom Mixer Tap", "Kitchen & Bathroom Mixer Tap"),
    (19, "exposed_shower_set", "Exposed Shower Set", "Exposed Shower Set",
     "Exposed Shower Set"),
    (20, "bathtub_massage_jet", "Bathtub with Massage jet", "Bathtub with Massage Jet",
     "Bathtub with Massage jet"),
    # `consumer_label` is "Kitchen Sink" on item 21 and "Ceramic Kitchen Sink" on item
    # 22 on purpose: two Kinds whose NAME contains "Kitchen Sink" are otherwise
    # indistinguishable to anything looking one up by the plain term, and the
    # stainless one is what a homeowner means by it. Recorded in the report.
    (21, "kitchen_sink_ss304", "Stainless Steel 304 Kitchen Sink", "Kitchen Sink",
     "Stainless Steel 304 Kitchen Sink"),
    (22, "ceramic_kitchen_sink", "Ceramic Kitchen Sink", "Ceramic Kitchen Sink",
     "Ceramic Kitchen Sink"),
    (23, "kitchen_bathroom_tap_ss304", "Stainless Steel 304 Kitchen and Bathroom Tap",
     "Stainless Steel 304 Kitchen and Bathroom Tap",
     "Stainless Steel 304 Kitchen and Bathroom Tap"),
    (24, "kitchen_mixer_cold_tap", "Kitchen Mixer & Cold Tap", "Kitchen Mixer & Cold Tap",
     "Kitchen Mixer & Cold Tap"),
    (25, "kitchen_mixer_tap", "Kitchen Mixer Tap", "Kitchen Mixer Tap", "Kitchen Mixer Tap"),
    (26, "booster_pump", "Automatic Water Booster Pump", "Automatic Water Booster Pump",
     "Automatic Water Booster Pump"),
    (27, "hand_shower", "Hand Shower", "Hand Shower", "Hand Shower"),
    (28, "hand_bidet", "Hand Bidet", "Hand Bidet", "Hand Bidet"),
    (29, "flush_valves_concealed_cistern",
     "Exposed and Conceal Flush Valves, Concealed Cistern",
     "Flush Valves and Concealed Cistern",
     "Exposed and Conceal Flush Valves, Concealed Cistern"),
    # Named "Sensor Taps" because that is what AC-D1 calls it and what every consumer
    # of this vocabulary matches on. The document's cell covers three more families,
    # kept verbatim in source_cell and in the term's qualifications.
    (30, "sensor_tap", "Sensor Taps", "Sensor Taps",
     "Sensor Taps, Sensor Soap Dispenser, Sensor Hand Dryer, Sensor Flush Valves"),
    (31, "self_closing_tap", "Self-Closing Tap", "Self-Closing Tap", "Self-Closing Tap"),
)


def _ceramic_body() -> dict:
    """The lifetime ceramic body, which seven items carry identically.

    A helper rather than seven copies, because seven copies is seven chances for one
    of them to drift by a word.
    """
    return {
        "part_name": "Ceramic Body",
        "is_lifetime": True,
        "duration_months": None,
        "installation_included": True,
        "defects": (CRACK, LEAK),
        "qualifications": f"{LIFETIME_CERAMIC_QUALIFICATION} {_INSTALLATION_INCLUDED}",
        "exclusions": LIFETIME_CERAMIC_EXCLUSION,
        "source_period": "Lifetime Warranty on crack line and leaking ONLY",
    }


def _term(
    part_name: str,
    period: str,
    installation_included: bool,
    *,
    defects: tuple = (),
    qualifications: Optional[str] = None,
) -> dict:
    note = _INSTALLATION_INCLUDED if installation_included else _INSTALLATION_EXCLUDED
    return {
        "part_name": part_name,
        "is_lifetime": False,
        "duration_months": MONTHS[period],
        "installation_included": installation_included,
        "defects": defects,
        "qualifications": f"{qualifications} {note}" if qualifications else note,
        "exclusions": None,
        "source_period": f"{period} from date of purchase",
    }


_RUST_QUALIFICATION_21 = (
    "Anti-Rust against body finishing affected by rust due to manufacturing defect and "
    "subject to the fulfilment of the terms stipulated in Sorento's manual/user guide "
    "(if any)."
)
_RUST_QUALIFICATION_23 = (
    "Rust Resistant against body finishing affected by rust due to manufacturing defect "
    "and subject to the fulfilment of the terms stipulated in Sorento's manual/user "
    "guide (if any)."
)

# kind code -> the terms clause 6 gives it. 41 rows across 31 kinds.
TERM_SEED = {
    "water_closet": (
        _ceramic_body(),
        _term("Flushing Fittings", "5 years", False),
        # The document's Warranty Parts cell reads "Seat Cover Soft Close System".
        # Seeded under AC-D4's name, which is the label the gate, the CS panel and the
        # portal all key on. Same part, one trailing noun shorter; flagged in the
        # report so the naming can be settled in one place.
        _term("Seat Cover Soft Close", "2 years", False),
    ),
    "urinal_bowl": (_ceramic_body(),),
    "squatting_pan": (_ceramic_body(),),
    "electronic_seat_cover": (_term("Electronic Components", "1 year", True),),
    "intelligent_water_closet": (
        _ceramic_body(),
        _term("Electronic Components", "1 year", True),
    ),
    "tankless_water_closet": (
        _ceramic_body(),
        # 2 years and installation INCLUDED here, against the Water Closet's 5 years
        # excluded. Same part name, different promise: read per row, never per part.
        _term("Flushing Fittings", "2 years", True),
    ),
    "wash_basin": (_ceramic_body(),),
    "led_mirror": (_term("Circuit Board", "1 year", True),),
    "bathroom_furniture": (
        _term(
            "External Surface Coating",
            "10 years",
            False,
            qualifications="Selected Models: *Honeycomb Series.",
        ),
    ),
    "mirror_cabinet": (
        _term("Hinges", "25 years", True, qualifications="Selected Models only."),
        _term("Aluminum Frame", "10 years", True, qualifications="Selected Models only."),
        _term("Mirror Glass", "2 years", True, qualifications="Selected Models only."),
    ),
    "concealed_shower_mixer_cold": (_term("Cartridge", "5 years", False),),
    "kitchen_bathroom_cold_tap": (_term("Cartridge", "5 years", False),),
    "stop_valve": (_term("Cartridge", "5 years", False),),
    "bib_hose_two_way_tap_bidet_set": (_term("Cartridge", "5 years", False),),
    "exposed_mixer_shower_set": (_term("Cartridge", "10 years", False),),
    "conceal_bath_shower_mixer": (_term("Cartridge", "10 years", False),),
    "conceal_bathroom_mixer": (_term("Cartridge", "10 years", False),),
    "kitchen_bathroom_mixer_tap": (_term("Cartridge", "10 years", False),),
    "exposed_shower_set": (_term("Diverter Cartridge", "5 years", False),),
    "bathtub_massage_jet": (
        _term("Water Pump", "5 years", True),
        _term("Mixer Tap Cartridge", "5 years", True),
        _term("Thermostat Heater", "3 years", True),
        # The document prints "1 years". 12 months either way.
        _term("Digital Control Panel", "1 year", True),
    ),
    "kitchen_sink_ss304": (
        _term(
            "Rust Resistant",
            "25 years",
            False,
            defects=(RUST,),
            qualifications=_RUST_QUALIFICATION_21,
        ),
    ),
    "ceramic_kitchen_sink": (_ceramic_body(),),
    "kitchen_bathroom_tap_ss304": (
        # Item 23 states NO installation answer at all, and the column is NOT NULL.
        # Set to excluded, matching every comparable tap and fitting row (items 11 to
        # 19, 21, 24, 25, 26, 27 to 31). Flagged in NOT_IN_THE_DOCUMENT: this is the
        # one installation value in the seed that was not read off a cell.
        _term(
            "Rust Resistant",
            "10 years",
            False,
            defects=(RUST,),
            qualifications=_RUST_QUALIFICATION_23,
        ),
    ),
    "kitchen_mixer_cold_tap": (
        _term("Pull out Flexible Hose & Flexible Hose", "2 years", False),
    ),
    "kitchen_mixer_tap": (_term("Inlet Flexible Hose", "5 years", False),),
    "booster_pump": (
        # "3 years from date of purchase (2 + 1 year extended warranty with online
        # registration)". The parenthetical decomposes the headline figure, so the
        # base term is 2 years and registration adds the third. Registration only ever
        # LENGTHENS cover and is never a precondition of it (ADR-0010, the BRD over
        # clause 3(b)).
        #
        # Deliberately NOT defect-scoped despite the part being called "Manufacturing
        # Defects": a scoped term answers `unknown` when a claim arrives with no
        # defect type stated, which is routine, and the document names no defect
        # vocabulary here.
        _term(
            "Manufacturing Defects",
            "2 years",
            False,
            qualifications=(
                "3 years from date of purchase (2 + 1 year extended warranty with "
                "online registration)."
            ),
        ),
        _term("PC Auto Controller", "1 year", False),
    ),
    "hand_shower": (_term("PVC Flexible Hose", "5 years", False),),
    "hand_bidet": (_term("PVC Flexible Hose", "5 years", False),),
    "flush_valves_concealed_cistern": (_term("Piston and Lever Mechanism", "1 year", False),),
    "sensor_tap": (
        _term(
            "Sensor Eye and Solenoid Valve",
            "1 year",
            False,
            qualifications=(
                "Applies to Sensor Taps, Sensor Soap Dispenser, Sensor Hand Dryer and "
                "Sensor Flush Valves."
            ),
        ),
    ),
    "self_closing_tap": (_term("Soft Close Mechanism", "1 year", False),),
}

# The only two mappings clause 6 states outright.
# (kind_code, match_type, match_value, where it comes from)
KIND_RULE_SEED = (
    (
        "bathroom_furniture",
        "series",
        "Honeycomb",
        "item 9 Product(s) cell: 'Selected Models *Honeycomb Series'",
    ),
    (
        "mirror_cabinet",
        "model_list",
        "SRTMCB8071-BL, SRTMCB6071-BL, SRTMCB6070-BL, SRTMCB5060-BL, SRTMCB5061-BL, "
        "SRTMCB6066-BL, SRTMCB4561-BL, SRTMCB4560-BL",
        "item 10 Product(s) cell: the explicit Selected Models list",
    ),
)

# What the document does not answer. Printed on every run: a seed that is 95 percent
# complete is how the last 5 percent ends up on nobody's worklist.
NOT_IN_THE_DOCUMENT = (
    "kind rules for 29 of the 31 kinds. Clause 6 states the mapping for item 9 "
    "(*Honeycomb Series) and item 10 (an explicit model list) and for nothing else, so "
    "which product categories and model prefixes reach which Kind is still unmapped "
    "and unreviewed (AC-D2)",
    "item 11's Product(s) cell ends at 'Concealed Shower Mixer & Cold' in the source "
    "document and reads as truncated. Transcribed verbatim rather than completed",
    "item 23 (Stainless Steel 304 Kitchen and Bathroom Tap) states no installation "
    "answer at all. installation_included is set to excluded to match every comparable "
    "fitting row, and it is the one installation value here not read off a cell",
    "consumer_label and consumer_icon. The labels are the internal names (except the "
    "two kitchen sinks) and there is no icon anywhere; the tiled picture chooser needs "
    "Sorento's own wording and an image per kind (S3)",
    "the defect-type vocabulary beyond the four that clause 6 and the golden set name. "
    "A real complaint taxonomy is wider than crack, leak, rust and a broken holder",
    "whether a v16 exists. This row is open-ended (effective_to NULL) and backdated to "
    "2000-01-01 on the retroactivity ruling; a later version must CLOSE this window "
    "rather than edit this row",
)


# ------------------------------------------------------------------ upserts


def _policy_text() -> str:
    return POLICY_TEXT_PATH.read_text(encoding="utf-8", errors="ignore").strip()


def _upsert_kind(db, code: str, name: str, sort_order: int) -> None:
    row = db.query(WarrantyProductKind).filter(WarrantyProductKind.code == code).one_or_none()
    if row is None:
        db.add(WarrantyProductKind(id=str(uuid.uuid4()), code=code, name=name, sort_order=sort_order, is_active=True))
        return
    for attribute, value in (("name", name), ("sort_order", sort_order)):
        if getattr(row, attribute) != value:
            setattr(row, attribute, value)


def _upsert_defect_types(db) -> dict:
    lookup_set = (
        db.query(LookupSet)
        .filter(LookupSet.set_key == DEFECT_TYPE_SET_KEY, LookupSet.tenant_id.is_(None))
        .one_or_none()
    )
    if lookup_set is None:
        lookup_set = LookupSet(
            id=str(uuid.uuid4()),
            set_key=DEFECT_TYPE_SET_KEY,
            name=DEFECT_TYPE_SET_NAME,
            description="What is wrong with the product. Referenced by warranty_terms.covered_defect_type_ids.",
            is_active=True,
        )
        db.add(lookup_set)
        db.flush()
    ids = {}
    for sort_order, (value, label, _source) in enumerate(DEFECT_TYPE_SEED):
        option = (
            db.query(LookupOption)
            .filter(LookupOption.set_id == lookup_set.id, LookupOption.value == value)
            .one_or_none()
        )
        if option is None:
            option = LookupOption(
                id=str(uuid.uuid4()), set_id=lookup_set.id, value=value, label=label, sort_order=sort_order, is_active=True
            )
            db.add(option)
            db.flush()
        elif option.label != label or option.sort_order != sort_order:
            option.label = label
            option.sort_order = sort_order
        ids[value] = option.id
    return ids


def _upsert_policy(db, company_id: str) -> WarrantyPolicy:
    text = _policy_text()
    policy = (
        db.query(WarrantyPolicy)
        .filter(WarrantyPolicy.version == POLICY_VERSION, WarrantyPolicy.company_id == company_id)
        .one_or_none()
    )
    if policy is None:
        policy = WarrantyPolicy(
            id=str(uuid.uuid4()),
            version=POLICY_VERSION,
            effective_from=POLICY_EFFECTIVE_FROM,
            effective_to=POLICY_EFFECTIVE_TO,
            policy_text=text,
            company_id=company_id,
        )
        db.add(policy)
        db.flush()
        return policy
    # An existing row is left alone: an owner may have closed its window or edited its text.
    return policy


def _upsert_term(db, policy, kind, spec: dict, defect_ids: dict) -> None:
    wanted = {
        "duration_months": spec["duration_months"],
        "is_lifetime": spec["is_lifetime"],
        "covered_defect_type_ids": [defect_ids[v] for v in spec.get("defects", ())] or None,
        "installation_included": spec["installation_included"],
        "qualifications": spec["qualifications"],
        "exclusions": spec["exclusions"],
    }
    row = (
        db.query(WarrantyTerm)
        .filter(WarrantyTerm.policy_id == policy.id, WarrantyTerm.kind_id == kind.id, WarrantyTerm.part_name == spec["part_name"])
        .one_or_none()
    )
    if row is None:
        db.add(WarrantyTerm(id=str(uuid.uuid4()), policy_id=policy.id, kind_id=kind.id, part_name=spec["part_name"], **wanted))
        return
    # An existing term is left alone for the same reason as the policy row.


def _upsert_rule(db, kind, match_type: str, match_value: str) -> None:
    exists = (
        db.query(WarrantyKindRule.id)
        .filter(
            WarrantyKindRule.kind_id == kind.id,
            WarrantyKindRule.match_type == match_type,
            WarrantyKindRule.match_value == match_value,
        )
        .first()
    )
    if exists is None:
        db.add(WarrantyKindRule(id=str(uuid.uuid4()), kind_id=kind.id, match_type=match_type, match_value=match_value, priority=0))


def seed_warranty_policy_v15(db, company_id: str) -> None:
    """Seed the shared kinds, defect set and rules, and `company_id`'s v15 policy with its terms."""
    for no, code, name, _label, _cell in KIND_SEED:
        _upsert_kind(db, code, name, no)
    db.flush()
    defect_ids = _upsert_defect_types(db)
    policy = _upsert_policy(db, company_id)
    kinds = {row.code: row for row in db.query(WarrantyProductKind).all()}
    for code, specs in TERM_SEED.items():
        for spec in specs:
            _upsert_term(db, policy, kinds[code], spec, defect_ids)
    for code, match_type, match_value, _source in KIND_RULE_SEED:
        _upsert_rule(db, kinds[code], match_type, match_value)
    db.flush()
    logger.info("Seeded warranty policy %s for company %s", POLICY_VERSION, company_id)
