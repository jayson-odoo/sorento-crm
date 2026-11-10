"""COMBO-SEED-FLYER follow-up: the committed seed carries the owner's hand-made combo names as `aka`.

UAC: documentation/plans/dealer-kit/combo-seed-flyer-acceptance-criteria.md (AC-5 to AC-8).
Red until the seed entries gain the `aka` pairing below.
"""
from __future__ import annotations

import io
import json
import uuid

import pytest

from app.models.accessory import Accessory
from app.models.base import company_scope, set_company_scope
from app.models.product_combo import ProductCombo
from app.services.company_scope import DEFAULT_COMPANY_ID

from tests.test_import_product_combos_strict import (
    SEED_FILE, _combos, _count, _lines, _prod, _script,
)
from tests._pg_fixture import blank_session

# (host_code, flyer combo_name, owner's name that must be an aka)
PAIRING = [
    ("SRTBT1860-16", "SRTBT1860-16", "BATHTUB COMBO"),
    ("SRTJC850", "SRTJC850", "BATHTUB COMBO"),
    ("SRTBT1846", "SRTBT1846", "BATHTUB COMBO"),
    ("SRTJC2025", "SRTJC2025", "BATHTUB COMBO"),
    ("SRTJC8030", "SRTJC8030", "BATHTUB COMBO"),
    ("SRTWC6021-SH-UF", "SRTWC6021-SH-UF + SRTFP4001 + SRTFC2043", "WALL HUNG WATER CLOSET COMBO"),
    ("SRTWC6011-RL-BL", "SRTWC6011-RL-BL + SRTFP4001-BL + SRTFC2043", "WALL HUNG WATER CLOSET COMBO"),
    ("SRTWC6022-SH-UF", "SRTWC6022-SH-UF + SRTFP4002 + SRTFC2043", "WALL HUNG WATER CLOSET COMBO"),
    ("SRTWC6021-SH-UF", "SRTWC6021-SH-UF + SRTFV2011 + SRTFC2044", "WALL HUNG WATER CLOSET COMBO 2"),
    ("SRTWC6011-RL-BL", "SRTWC6011-RL-BL + SRTFV2012-BL + SRTFC2044", "WALL HUNG WATER CLOSET COMBO 2"),
    ("SRTWC6022-SH-UF", "SRTWC6022-SH-UF + SRTFV2011 + SRTFC2044", "WALL HUNG WATER CLOSET COMBO 2"),
    ("SRTWC6031-SH-UF", "SRTWC6031-SH-UF + SRTFP4001 + SRTFC2031", "FLOOR STANDING WATER CLOSET COMBO"),
    ("SRTWC6031-SH-UF", "SRTWC6031-SH-UF + SRTFV2011 + SRTFC2031", "FLOOR STANDING WATER CLOSET COMBO 2"),
    ("SRTUB206", "SRTUB206 + SRTUFV101", "URINAL BOWL COMBO"),
    ("SRTUB6503-NEW", "SRTUB6503-NEW + SRTUFV101", "URINAL BOWL COMBO"),
    ("SRTUB6203", "SRTUB6203 + SRTUFV101", "URINAL BOWL COMBO"),
    ("SRTUB6203-BI", "SRTUB6203-BI + SRTFV1001", "URINAL BOWL COMBO"),
    ("SRTUB5202", "SRTUB5202 + SRTUFV101", "URINAL BOWL COMBO"),
    ("SRTBF11412", "SRTBF11412", "BATHROOM FURNITURE COMBO"),
    ("SRTWB1419-GY", "SRTWB1419-GY + ADD ON", "CERAMIC BASIN COMBO"),
    ("SRTBF11834", "SRTBF11834 + SRTMR502-BL (p21)", "SRTBF11834 + SRTMR502-BL"),
]


def _seed():
    return json.loads(SEED_FILE.read_text(encoding="utf-8"))


def _find(seed, host, name):
    hits = [e for e in seed if e["host_code"] == host and e["combo_name"] == name]
    assert len(hits) == 1, f"seed entry {host!r} / {name!r}: {len(hits)} found"
    return hits[0]


def _akas(entry):
    return [a.strip().lower() for a in entry.get("aka") or []]


def test_seed_carries_the_owner_pairing():
    seed = _seed()
    missing = []
    for host, name, owner in PAIRING:
        entry = _find(seed, host, name)
        if owner.lower() not in _akas(entry):
            missing.append((host, name, owner, entry.get("aka")))
    assert not missing, f"aka missing: {missing}"
    # the owner's p21 name is no longer any entry's exact name; p20 is its own package
    p20 = [e for e in seed if e["host_code"] == "SRTBF11834" and e["page"] == 20]
    assert [e["combo_name"] for e in p20] == ["SRTBF11834 + SRTMR502-BL (p20)"]
    assert not p20[0].get("aka")
    assert not [e for e in seed if e["combo_name"] == "SRTBF11834 + SRTMR502-BL"]
    assert [e.get("aka") for e in seed if e["host_code"] == "SRTWB7065"] == [[]] * len(
        [e for e in seed if e["host_code"] == "SRTWB7065"]
    ) or not any(e.get("aka") for e in seed if e["host_code"] == "SRTWB7065")


def test_seed_aka_integrity():
    seed = _seed()
    for host in {e["host_code"] for e in seed}:
        entries = [e for e in seed if e["host_code"] == host]
        names = {e["combo_name"].lower() for e in entries}
        claimed = {}
        for e in entries:
            for a in _akas(e):
                assert a not in names, f"{host}: aka {a!r} equals an entry's exact name"
                assert a not in claimed, f"{host}: aka {a!r} claimed by two entries"
                claimed[a] = e["id"]


@pytest.fixture()
def db():
    with blank_session() as session:
        set_company_scope(session, frozenset({DEFAULT_COMPANY_ID}))
        yield session


def _free_codes(seed):
    codes, labels = set(), set()
    for e in seed:
        codes.add(e["host_code"])
        codes.update(c["code"] for c in e.get("components") or [])
        for g in e.get("choice_groups") or []:
            codes.update(o["code"] for o in g["options"])
        codes.update(t["code"] for t in e.get("topups") or [])
        for f in e.get("free_items") or []:
            if f["kind"] == "product" and f.get("code"):
                codes.add(f["code"])
            elif f["kind"] == "accessory":
                labels.add(f["label"])
    return {c for c in codes if c}, labels


def _run_real(db, tmp_path):
    argv = ["--file", str(SEED_FILE), "--report", str(tmp_path / f"r-{uuid.uuid4().hex[:6]}.csv"),
            "--strict", "--apply"]
    out = io.StringIO()
    _script().main(argv, db=db, out=out)
    return out.getvalue()


def _verdict(lines, host, names):
    hits = [row for row in lines if row[1] == host and row[2] in names]
    assert len(hits) == 1, f"line for {host} {names}: {hits}"
    return hits[0][0].split(" ")[0]


def test_owner_combos_are_matched_not_duplicated(db, tmp_path):
    seed = _seed()
    codes, labels = _free_codes(seed)
    for code in sorted(codes):
        _prod(db, code)
    with company_scope(db, None):
        for label in sorted({l.lower(): l for l in labels}.values()):
            db.add(Accessory(id=str(uuid.uuid4()), name=label, company_id=DEFAULT_COMPANY_ID))
        db.commit()
    from app.models.product import Product

    owner_keys = sorted({(h, o) for h, _n, o in PAIRING})
    with company_scope(db, None):
        for host, owner in owner_keys:
            hid = db.query(Product).filter(Product.product_code == host).one().id
            db.add(ProductCombo(id=str(uuid.uuid4()), host_product_id=hid, name=owner,
                                description="Owner text"))
        db.commit()

    lines = _lines(_run_real(db, tmp_path))
    for host, name, owner in PAIRING:
        assert _verdict(lines, host, {name, owner}) in ("UPDATE", "SKIP"), (host, name)
        kept = _combos(db, host, owner)
        assert len(kept) == 1 and kept[0].description == "Owner text", (host, owner)
        assert _combos(db, host, name) == [] or name == owner, (host, name)
    assert _verdict(lines, "SRTBF11834", {"SRTBF11834 + SRTMR502-BL (p20)"}) == "CREATE"

    total = _count(db, ProductCombo)
    lines = _lines(_run_real(db, tmp_path))
    for host, name, owner in PAIRING:
        assert _verdict(lines, host, {name, owner}) == "SKIP", (host, name)
    assert _count(db, ProductCombo) == total
