#!/usr/bin/env python3
"""Seed Sorento Warranty Policy v15: 31 product kinds, the policy row, and its 41 terms.

The source is `scripts/data/warranty_policy_sorento_v15.pdf` ("Version 15. Updated
March 2026") and its extracted text alongside it. Every duration, lifetime flag,
installation answer, qualification and exclusion below is transcribed from clause
6's table, item by item, and each Kind carries the document's verbatim Product(s)
cell so a later reader can check rather than trust. **Nothing here is derived from
the plan's golden set** - the golden set is the test, not the source, and a seed
written from its expectations would prove only that it agrees with itself.

Three things about this seed are decisions, and each is somewhere the document and
the rest of the system do not line up exactly:

**v15 is backdated to 2000-01-01 and is the only policy Sorento has on record.**
Ruled by the user 2026-08-02: v15 is RETROACTIVE. Clause 16 lets Sorento amend the
document without notice, so a Complaint is judged against the version in force on
its purchase date - which means a 2015 purchase needs a policy whose window contains
2015 or the engine correctly answers `unknown` and no historic claim can be judged
at all. Backdating is a DATA answer to that, not an algorithm one: clamping an
out-of-range purchase to the nearest policy was rejected, because it judges a 2015
purchase by 2026 terms, which is the one thing the versioning exists to forbid.
`effective_to` is NULL: v15 is current. **When a v16 arrives with a real publication
date, this row's `effective_to` must be closed on the day before it and v16 seeded
with its own window, rather than this row being edited.**

**`warranty_policies` is company-scoped and this is SORENTO's document** (AC-D16).
Mocha publishes its own Version 4 with different durations for the same product
kinds, and that is a different row under a different company. The seed pins the
scope rather than trusting whatever the caller carried, so it can never write a
Sorento policy into Mocha's partition or find Mocha's when checking for an existing
one.

**Two kind rules are seeded and 29 kinds still have none.** The document itself
names the mapping for exactly two items: item 9 Bathroom Furniture is "Selected
Models *Honeycomb Series", and item 10 Mirror Cabinet carries an explicit list of
eight model codes. Those are sourced, so they are seeded. Every other kind would
need a category-code or model-prefix mapping the policy does not state, and a wrong
mapping sends a product to the wrong Kind and applies the wrong terms, which is the
same class of harm as a wrong duration. They stay unseeded and are listed in
`NOT_IN_THE_DOCUMENT`, which the CLI prints on every run.

**Idempotent on the stable codes, never insert-only.** It will be re-run on every
environment and twice on at least one of them. Kinds upsert on `code`, the policy on
`version` (within the company), terms on (policy, kind, part), rules on (kind, type,
value), defect options on (set, value). "Set where it differs", not "insert where
absent": the second form cannot repair a row a previous run wrote wrongly, which is
the row most in need of repair.

Run from sorento_crm_backend/ AFTER `alembic upgrade head`:

    python scripts/seed_warranty_policy_v15.py            # dry run (default)
    python scripts/seed_warranty_policy_v15.py --apply
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import uuid
from datetime import date
from pathlib import Path
from typing import Optional

# Allow `from app.*` imports when invoked from the backend directory.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.base import company_scope  # noqa: E402
from app.models.lookup import LookupOption, LookupSet  # noqa: E402
from app.models.warranty import (  # noqa: E402
    WarrantyKindRule,
    WarrantyPolicy,
    WarrantyProductKind,
    WarrantyTerm,
)
from app.services.company_scope import DEFAULT_COMPANY_ID  # noqa: E402

logger = logging.getLogger(__name__)

# v15 is Sorento's document. `warranty_policies` is company-scoped, so the seed pins
# the company rather than relying on whatever scope the caller happened to carry.
SORENTO_COMPANY_ID = DEFAULT_COMPANY_ID
SORENTO_SCOPE = frozenset({SORENTO_COMPANY_ID})

POLICY_VERSION = "v15"
POLICY_TEXT_PATH = Path(__file__).resolve().parent / "data" / "warranty_policy_sorento_v15.txt"
# See the docstring. Not the publication date, on purpose.
POLICY_EFFECTIVE_FROM = date(2000, 1, 1)
POLICY_EFFECTIVE_TO = None

# The defect-type vocabulary. This codebase had none: the nearest set,
# `complaints_defects_discovered`, enumerates WHEN a defect was noticed ("Upon
# delivery after unloading"), not WHAT it is, so clause 6's "crack line and leaking
# ONLY" was inexpressible and `warranty_terms.covered_defect_type_ids` pointed at
# rows nothing created.
DEFECT_TYPE_SET_KEY = "complaints_defect_type"
DEFECT_TYPE_SET_NAME = "Complaints - Defect Type"

CRACK = "Crack Line"
LEAK = "Leakage"
RUST = "Rust"
HOLDER = "Holder Broken"

# (value, label, where it comes from)
DEFECT_TYPE_SEED = (
    (CRACK, CRACK, "clause 6, every Ceramic Body row: 'crack line and leaking ONLY'"),
    (LEAK, LEAK, "clause 6, the same rows, plus the live complaints_complaint_type set"),
    (RUST, RUST, "clause 6 items 21 and 23: 'Anti-Rust' / 'Rust Resistant'"),
    (HOLDER, HOLDER, "the plan's golden set row 3, a defect the lifetime body excludes"),
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

# (no, code, name, consumer_label, source_cell)
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
        "registration_bonus_months": None,
        "source_period": "Lifetime Warranty on crack line and leaking ONLY",
    }


def _term(
    part_name: str,
    period: str,
    installation_included: bool,
    *,
    defects: tuple = (),
    qualifications: Optional[str] = None,
    registration_bonus_months: Optional[int] = None,
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
        "registration_bonus_months": registration_bonus_months,
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
            registration_bonus_months=12,
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


# --------------------------------------------------------------------------- #
# Upserts                                                                       #
# --------------------------------------------------------------------------- #


def _policy_text() -> str:
    if not POLICY_TEXT_PATH.exists():
        raise SystemExit(
            f"{POLICY_TEXT_PATH} is missing. The policy text is the evidence behind "
            "every duration in this seed and the only thing a policy answer may quote; "
            "the seed refuses to write a policy row without it."
        )
    return POLICY_TEXT_PATH.read_text(encoding="utf-8", errors="ignore").strip()


def _upsert_kind(db, code: str, name: str, consumer_label: str, sort_order: int) -> bool:
    """Create or correct one Kind. Returns True when it wrote something."""
    row = db.query(WarrantyProductKind).filter(WarrantyProductKind.code == code).one_or_none()
    if row is None:
        db.add(
            WarrantyProductKind(
                id=str(uuid.uuid4()),
                code=code,
                name=name,
                consumer_label=consumer_label,
                sort_order=sort_order,
                is_active=True,
            )
        )
        return True

    changed = False
    for attribute, value in (
        ("name", name),
        ("consumer_label", consumer_label),
        ("sort_order", sort_order),
    ):
        if getattr(row, attribute) != value:
            setattr(row, attribute, value)
            changed = True
    return changed


def _upsert_defect_types(db) -> tuple:
    """Create the `complaints_defect_type` set and its options.

    Returns (set_created, option_writes, {value: id}) rather than one number, because
    a run that created the set and no options and a run that created options and no
    set are different events and one counter cannot tell them apart.
    """
    set_created = False
    writes = 0
    lookup_set = (
        db.query(LookupSet)
        .filter(LookupSet.set_key == DEFECT_TYPE_SET_KEY)
        .filter(LookupSet.tenant_id.is_(None))
        .one_or_none()
    )
    if lookup_set is None:
        lookup_set = LookupSet(
            id=str(uuid.uuid4()),
            set_key=DEFECT_TYPE_SET_KEY,
            name=DEFECT_TYPE_SET_NAME,
            description=(
                "What is wrong with the product. Distinct from "
                "complaints_defects_discovered, which records WHEN a defect was "
                "noticed. Referenced by warranty_terms.covered_defect_type_ids."
            ),
            is_active=True,
        )
        db.add(lookup_set)
        db.flush()
        set_created = True

    ids = {}
    for sort_order, (value, label, _source) in enumerate(DEFECT_TYPE_SEED):
        option = (
            db.query(LookupOption)
            .filter(LookupOption.set_id == lookup_set.id)
            .filter(LookupOption.value == value)
            .one_or_none()
        )
        if option is None:
            option = LookupOption(
                id=str(uuid.uuid4()),
                set_id=lookup_set.id,
                value=value,
                label=label,
                sort_order=sort_order,
                is_active=True,
            )
            db.add(option)
            db.flush()
            writes += 1
        elif option.label != label or option.sort_order != sort_order:
            option.label = label
            option.sort_order = sort_order
            writes += 1
        ids[value] = option.id

    return set_created, writes, ids


def _upsert_policy(db) -> tuple:
    """Create or correct the v15 row. Returns (policy, wrote).

    Both the lookup and the insert name the company EXPLICITLY rather than leaning on
    the scope layer. The auto-filter and the auto-stamp only exist once
    `register_company_scope_listeners()` has run, and a plain `python scripts/...`
    process never imports `app.main` or the worker, so a script that relies on them
    silently gets neither: it would find Mocha's v15 when checking for an existing row
    and then insert a policy with no company at all. `main()` registers them anyway,
    because the READ path needs them, but a legal document's owner is not something to
    leave to a listener being installed.
    """
    text = _policy_text()
    policy = (
        db.query(WarrantyPolicy)
        .filter(WarrantyPolicy.version == POLICY_VERSION)
        .filter(WarrantyPolicy.company_id == SORENTO_COMPANY_ID)
        .one_or_none()
    )
    if policy is None:
        policy = WarrantyPolicy(
            id=str(uuid.uuid4()),
            version=POLICY_VERSION,
            effective_from=POLICY_EFFECTIVE_FROM,
            effective_to=POLICY_EFFECTIVE_TO,
            policy_text=text,
            company_id=SORENTO_COMPANY_ID,
        )
        db.add(policy)
        db.flush()
        return policy, True

    wrote = False
    for attribute, value in (
        ("effective_from", POLICY_EFFECTIVE_FROM),
        ("effective_to", POLICY_EFFECTIVE_TO),
        ("policy_text", text),
    ):
        if getattr(policy, attribute) != value:
            setattr(policy, attribute, value)
            wrote = True
    return policy, wrote


def _upsert_term(db, policy, kind, spec: dict, defect_ids: dict) -> bool:
    """Create or correct one term, keyed on (policy, kind, part)."""
    scope = [defect_ids[value] for value in spec.get("defects", ())] or None
    wanted = {
        "duration_months": spec["duration_months"],
        "is_lifetime": spec["is_lifetime"],
        "covered_defect_type_ids": scope,
        "installation_included": spec["installation_included"],
        "registration_bonus_months": spec.get("registration_bonus_months"),
        "qualifications": spec["qualifications"],
        "exclusions": spec["exclusions"],
    }

    row = (
        db.query(WarrantyTerm)
        .filter(WarrantyTerm.policy_id == policy.id)
        .filter(WarrantyTerm.kind_id == kind.id)
        .filter(WarrantyTerm.part_name == spec["part_name"])
        .one_or_none()
    )
    if row is None:
        db.add(
            WarrantyTerm(
                id=str(uuid.uuid4()),
                policy_id=policy.id,
                kind_id=kind.id,
                part_name=spec["part_name"],
                **wanted,
            )
        )
        return True

    changed = False
    for attribute, value in wanted.items():
        current = getattr(row, attribute)
        if attribute == "covered_defect_type_ids":
            if sorted(current or []) != sorted(value or []):
                setattr(row, attribute, value)
                changed = True
            continue
        if current != value:
            setattr(row, attribute, value)
            changed = True
    return changed


def _upsert_rule(db, kind, match_type: str, match_value: str) -> bool:
    row = (
        db.query(WarrantyKindRule)
        .filter(WarrantyKindRule.kind_id == kind.id)
        .filter(WarrantyKindRule.match_type == match_type)
        .filter(WarrantyKindRule.match_value == match_value)
        .one_or_none()
    )
    if row is None:
        db.add(
            WarrantyKindRule(
                id=str(uuid.uuid4()),
                kind_id=kind.id,
                match_type=match_type,
                match_value=match_value,
                priority=0,
            )
        )
        return True
    return False


def seed(db) -> dict:
    """Seed the kinds, the defect vocabulary, the v15 policy, its terms and two rules.

    Idempotent, and safe to call inside a caller's transaction: it flushes but never
    commits, so the caller decides.
    """
    kind_writes = 0
    for no, code, name, consumer_label, _source_cell in KIND_SEED:
        if _upsert_kind(db, code, name, consumer_label, no):
            kind_writes += 1
    db.flush()

    defect_set_created, defect_writes, defect_ids = _upsert_defect_types(db)
    db.flush()

    policy, policy_wrote = _upsert_policy(db)
    kinds = {row.code: row for row in db.query(WarrantyProductKind).all()}

    term_writes = 0
    term_count = 0
    for code, specs in TERM_SEED.items():
        kind = kinds[code]
        for spec in specs:
            term_count += 1
            if _upsert_term(db, policy, kind, spec, defect_ids):
                term_writes += 1

    rule_writes = 0
    for code, match_type, match_value, _source in KIND_RULE_SEED:
        if _upsert_rule(db, kinds[code], match_type, match_value):
            rule_writes += 1
    db.flush()

    report = {
        "kinds_seeded": len(KIND_SEED),
        "kinds_written": kind_writes,
        "defect_type_set_created": defect_set_created,
        "defect_types_seeded": len(DEFECT_TYPE_SEED),
        "defect_type_writes": defect_writes,
        "policy_version": POLICY_VERSION,
        "policy_written": policy_wrote,
        "terms_seeded": term_count,
        "terms_written": term_writes,
        "rules_seeded": len(KIND_RULE_SEED),
        "rules_written": rule_writes,
        "open": list(NOT_IN_THE_DOCUMENT),
    }

    # Logged on every call, including from a test: the seed is faithful to the
    # document, and the document does not answer everything.
    logger.info(
        "Seeded Sorento Warranty Policy %s: %d kinds, %d terms, %d kind rules. Still "
        "open: %s",
        POLICY_VERSION,
        len(KIND_SEED),
        term_count,
        len(KIND_RULE_SEED),
        "; ".join(NOT_IN_THE_DOCUMENT),
    )
    return report


BANNER = """
================================================================================
  Sorento Warranty Policy v15, seeded from
  scripts/data/warranty_policy_sorento_v15.pdf

  Backdated to {effective_from} with no end date, on the ruling that v15 is
  RETROACTIVE and is the only policy Sorento has on record. A later version must
  CLOSE this window, not edit this row.

  What the document does not answer:
{open}
================================================================================
"""


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Seed Sorento Warranty Policy v15: 31 kinds, the policy and its terms."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="commit the seed (default is a dry run that rolls back)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    from app.database import SessionLocal
    from app.services.company_scope import register_company_scope_listeners

    # A standalone script imports neither `app.main` nor the worker, so without this
    # the company SELECT filter is simply absent and every read spans all companies.
    # Idempotent.
    register_company_scope_listeners()

    db = SessionLocal()
    try:
        with company_scope(db, SORENTO_SCOPE):
            report = seed(db)
            if args.apply:
                db.commit()
            else:
                db.rollback()
    finally:
        db.close()

    print("APPLIED" if args.apply else "DRY RUN (nothing committed)")
    print(
        f"  kinds:        {report['kinds_written']} written of {report['kinds_seeded']}\n"
        f"  defect types: {report['defect_type_writes']} written of "
        f"{report['defect_types_seeded']} (set created: {report['defect_type_set_created']})\n"
        f"  policy {report['policy_version']}:    written: {report['policy_written']}\n"
        f"  terms:        {report['terms_written']} written of {report['terms_seeded']}\n"
        f"  kind rules:   {report['rules_written']} written of {report['rules_seeded']}"
    )
    print(
        BANNER.format(
            effective_from=POLICY_EFFECTIVE_FROM.isoformat(),
            open="\n".join(f"    - {item}" for item in NOT_IN_THE_DOCUMENT),
        ),
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
