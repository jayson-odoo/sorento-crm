"""COMBO-SEED-FLYER: `scripts/import_product_combos.py --strict` (red tests, written first).

UAC: documentation/plans/dealer-kit/combo-seed-flyer-acceptance-criteria.md (AC-0 to AC-20).
Per-combo line shape (AC-2): `<VERDICT> | <host> | <name> | p<page> | <details>`.
"""
from __future__ import annotations

import io
import json
import re
import uuid
from decimal import Decimal
from pathlib import Path

import pytest

from app.models.accessory import Accessory, ProductComboAccessory
from app.models.base import company_scope, set_company_scope
from app.models.product import Product
from app.models.product_combo import ProductCombo, ProductComboPart
from app.services.company_scope import DEFAULT_COMPANY_ID

from tests._mc_lookup_seed import product
from tests._pg_fixture import blank_session

VERDICTS = ("CREATE", "UPDATE", "SKIP", "UNMATCHED", "FAILED")
SEED_FILE = Path(__file__).resolve().parents[1] / "scripts" / "data" / "combo_seed_flyer_2026.json"


def _script():
    from scripts import import_product_combos as script

    return script


@pytest.fixture()
def db():
    with blank_session() as session:
        set_company_scope(session, frozenset({DEFAULT_COMPANY_ID}))
        yield session


def _prod(db, code):
    row = product(db, company_id=DEFAULT_COMPANY_ID, code=code)
    row.list_price = Decimal("100.00")
    db.flush()
    db.commit()
    return row


def _entry(host, name, page=1, **extra):
    return {"id": f"{host}-{name}", "host_code": host, "combo_name": name, "page": page, **extra}


def _run(db, tmp_path, entries, *extra, apply=False, strict=True):
    seed = tmp_path / f"seed-{uuid.uuid4().hex[:6]}.json"
    seed.write_text(json.dumps(entries), encoding="utf-8")
    argv = ["--file", str(seed), "--report", str(tmp_path / f"r-{uuid.uuid4().hex[:6]}.csv"), *extra]
    if strict:
        argv.append("--strict")
    if apply:
        argv.append("--apply")
    out = io.StringIO()
    code = _script().main(argv, db=db, out=out)
    return code, out.getvalue()


def _lines(text):
    """Parsed per-combo lines: (verdict, host, name, page, details)."""
    found = []
    for line in text.splitlines():
        cells = [c.strip() for c in line.split(" | ")]
        if len(cells) >= 4 and cells[0].split(" ")[0] in VERDICTS:
            found.append((cells[0], cells[1], cells[2], cells[3], " | ".join(cells[4:])))
    return found


def _line(text, name):
    hits = [row for row in _lines(text) if row[2] == name]
    assert len(hits) == 1, f"one line for {name!r}, got {_lines(text)} in {text!r}"
    return hits[0]


def _count(db, model):
    db.expire_all()
    with company_scope(db, None):
        return db.query(model).count()


def _counts(db):
    return tuple(_count(db, m) for m in (ProductCombo, ProductComboPart, ProductComboAccessory, Accessory))


def _combos(db, host_code, name=None):
    db.expire_all()
    with company_scope(db, None):
        host = db.query(Product).filter(Product.product_code == host_code).one()
        query = db.query(ProductCombo).filter(ProductCombo.host_product_id == host.id)
        if name is not None:
            query = query.filter(ProductCombo.name == name)
        return query.all()


def _parts(db, combo):
    with company_scope(db, None):
        return {
            p.part_product.product_code: p
            for p in db.query(ProductComboPart).filter(ProductComboPart.combo_id == combo.id).all()
        }


def _existing(db, host_code, name, **fields):
    host = db.query(Product).filter(Product.product_code == host_code).one()
    row = ProductCombo(id=str(uuid.uuid4()), host_product_id=host.id, name=name, **fields)
    db.add(row)
    db.commit()
    return row


# --------------------------------------------------------------------------- AC-1


def test_ac_1_strict_dry_run_writes_nothing(db, tmp_path):
    _prod(db, "ZZSH1")
    _prod(db, "ZZSP1")
    entries = [
        _entry("ZZSH1", "Pack A", 3, components=[{"code": "ZZSP1", "role": "Part"}], lp=200, sp=150,
               combo_description="<p>x</p>"),
        _entry("ZZSH1", "Pack B", 4),
    ]
    before = _counts(db)
    code, out = _run(db, tmp_path, entries)
    assert code == 0
    assert _counts(db) == before
    lines = _lines(out)
    assert [(v, n) for v, _h, n, _p, _d in lines] == [("CREATE", "Pack A"), ("CREATE", "Pack B")]
    assert lines[0][1] == "ZZSH1" and lines[0][3] == "p3"
    assert "CREATE: 2" in out


# --------------------------------------------------------------------------- AC-4


def test_ac_4_second_apply_is_all_skip_and_writes_nothing(db, tmp_path):
    _prod(db, "ZZSH2")
    _prod(db, "ZZSP2")
    _prod(db, "ZZSP3")
    with company_scope(db, None):
        db.add(Accessory(id=str(uuid.uuid4()), name="Board", company_id=DEFAULT_COMPANY_ID))
        db.commit()
    entries = [
        _entry("ZZSH2", "Pack A", 1, components=[{"code": "ZZSP2", "role": "Part"}],
               choice_groups=[{"role": "Pick", "options": [{"code": "ZZSP3", "sp": 10}]}],
               free_items=[{"kind": "accessory", "label": "board"}],
               combo_description="<p>d</p>", lp=200, sp=150),
    ]
    _run(db, tmp_path, entries, apply=True)
    assert len(_combos(db, "ZZSH2", "Pack A")) == 1
    combo = _combos(db, "ZZSH2", "Pack A")[0]
    stamp = combo.updated_at
    counts = _counts(db)
    code, out = _run(db, tmp_path, entries, apply=True)
    assert [v for v, *_ in _lines(out)] == ["SKIP"]
    assert _counts(db) == counts
    assert _combos(db, "ZZSH2", "Pack A")[0].updated_at == stamp


# --------------------------------------------------------------------------- AC-9 / AC-10


def test_ac_9_ac_10_fixed_choice_and_upgrade_parts(db, tmp_path):
    for code in ("ZZPH1", "ZZPF1", "ZZPO1", "ZZPO2", "ZZPU1"):
        _prod(db, code)
    entries = [
        _entry("ZZPH1", "Pack", 1, components=[{"code": "ZZPF1", "role": "Fixed"}],
               choice_groups=[{"role": "Basin", "options": [{"code": "ZZPO1", "sp": 11}, {"code": "ZZPO2", "sp": 22}]}],
               topups=[{"code": "ZZPU1", "topup": 33}]),
    ]
    _run(db, tmp_path, entries, apply=True)
    parts = _parts(db, _combos(db, "ZZPH1", "Pack")[0])
    assert parts["ZZPF1"].choice_group is None and not parts["ZZPF1"].is_upgrade
    assert parts["ZZPO1"].choice_group == parts["ZZPO2"].choice_group == "Basin"
    assert parts["ZZPO1"].sell_price == Decimal("11") and parts["ZZPO2"].sell_price == Decimal("22")
    assert parts["ZZPU1"].is_upgrade is True
    assert parts["ZZPU1"].topup_amount == Decimal("33") and parts["ZZPU1"].choice_group is None


# --------------------------------------------------------------------------- AC-12 / AC-13


def test_ac_12_ac_13_free_items_product_and_library_accessory(db, tmp_path):
    _prod(db, "ZZFH1")
    free = _prod(db, "ZZFREE1")
    lib_id = str(uuid.uuid4())
    with company_scope(db, None):
        db.add(Accessory(id=lib_id, name="CHOPPING BOARD", company_id=DEFAULT_COMPANY_ID))
        db.commit()
    entries = [
        _entry("ZZFH1", "Pack", 1, free_items=[
            {"kind": "product", "code": "ZZFREE1", "label": "Tap"},
            {"kind": "accessory", "label": "chopping board"},
        ]),
    ]
    accessories_before = _count(db, Accessory)
    _run(db, tmp_path, entries, apply=True)
    combo = _combos(db, "ZZFH1", "Pack")[0]
    with company_scope(db, None):
        rows = db.query(ProductComboAccessory).filter(ProductComboAccessory.combo_id == combo.id).all()
        got = {(r.item_product_id, r.accessory_id) for r in rows}
    assert got == {(free.id, None), (None, lib_id)}
    assert _count(db, Accessory) == accessories_before


# --------------------------------------------------------------------------- AC-14 / AC-15


def test_ac_14_ac_15_unmatched_holds_the_whole_combo(db, tmp_path):
    for code in ("ZZUH1", "ZZUH2", "ZZUH3", "ZZUH4", "ZZUH5", "ZZUP1", "ZZUP2", "ZZUF1"):
        _prod(db, code)
    entries = [
        _entry("ZZUMISSINGHOST", "No host", 1),
        _entry("ZZUH2", "Bad part", 2, components=[{"code": "ZZUP1", "role": "A"}, {"code": "ZZUNOPART", "role": "B"}]),
        _entry("ZZUH3", "Bad free product", 3, free_items=[{"kind": "product", "code": "ZZUNOFREE", "label": "Tap"}]),
        _entry("ZZUH4", "Bad accessory", 4, free_items=[{"kind": "accessory", "label": "no such library item"}]),
        _entry("ZZUH5", "Good", 5, components=[{"code": "ZZUP2", "role": "A"}],
               free_items=[{"kind": "product", "code": "ZZUF1", "label": "Tap"}]),
    ]
    accessories_before = _count(db, Accessory)
    _, dry = _run(db, tmp_path, entries)
    _, out = _run(db, tmp_path, entries, apply=True)
    for text in (dry, out):
        for name, missing in (
            ("No host", "ZZUMISSINGHOST"), ("Bad part", "ZZUNOPART"),
            ("Bad free product", "ZZUNOFREE"), ("Bad accessory", "no such library item"),
        ):
            verdict, _h, _n, _p, details = _line(text, name)
            assert verdict.startswith("UNMATCHED")
            assert f"missing: {missing}" in details or missing in verdict
        assert _line(text, "Good")[0] in ("CREATE", "SKIP")
    assert _line(dry, "Good")[0] == "CREATE"
    assert _combos(db, "ZZUH2") == [] and _combos(db, "ZZUH3") == [] and _combos(db, "ZZUH4") == []
    assert _count(db, Accessory) == accessories_before
    with company_scope(db, None):
        assert db.query(ProductComboAccessory).count() == 1
    assert len(_combos(db, "ZZUH5", "Good")) == 1


# --------------------------------------------------------------------------- AC-16 / AC-17


def test_ac_16_rich_description_stored_exactly_with_bold(db, tmp_path):
    _prod(db, "ZZDH1")
    html = "<p><strong>SRTX1</strong> (CABINET)</p><p>L400xW345xH390mm</p>"
    _run(db, tmp_path, [_entry("ZZDH1", "Pack", 1, combo_description=html)], apply=True)
    stored = _combos(db, "ZZDH1", "Pack")[0].description
    assert stored == html and "<strong>" in stored


def test_ac_17_long_description_loads_uncut(db, tmp_path):
    _prod(db, "ZZDH2")
    html = "<p>" + ("a" * 2993) + "</p>"
    assert len(html) == 3000
    _, out = _run(db, tmp_path, [_entry("ZZDH2", "Long", 1, combo_description=html)], apply=True)
    combos = _combos(db, "ZZDH2", "Long")
    assert len(combos) == 1, out
    assert len(combos[0].description) == 3000


# --------------------------------------------------------------------------- AC-5 / AC-6


def test_ac_5_ac_6_existing_combo_only_gets_what_it_lacks(db, tmp_path):
    _prod(db, "ZZEH1")
    _existing(db, "ZZEH1", "Pack A", description="<p>mine</p>")
    entries = [_entry("ZZEH1", "pack a", 2, combo_description="<p>seed</p>", sp=459)]
    _, out = _run(db, tmp_path, entries, apply=True)
    combos = _combos(db, "ZZEH1")
    assert len(combos) == 1
    assert combos[0].description == "<p>mine</p>"
    assert combos[0].sell_price == Decimal("459")
    verdict, _h, _n, _p, details = _lines(out)[0]
    assert verdict == "UPDATE"
    assert details.startswith("fills:") and "selling price" in details and "description" not in details


def test_ac_6_list_price_kept_without_update(db, tmp_path):
    _prod(db, "ZZEH2")
    _existing(db, "ZZEH2", "Pack A", list_price=Decimal("100"))
    _run(db, tmp_path, [_entry("ZZEH2", "Pack A", 1, lp=200)], apply=True)
    assert _combos(db, "ZZEH2", "Pack A")[0].list_price == Decimal("100")


# --------------------------------------------------------------------------- AC-7 / AC-8


def test_ac_7_aka_matches_old_name(db, tmp_path):
    _prod(db, "ZZAH1")
    _existing(db, "ZZAH1", "Old Name")
    _run(db, tmp_path, [_entry("ZZAH1", "New Name", 1, aka=["old name"])], apply=True)
    combos = _combos(db, "ZZAH1")
    assert [c.name for c in combos] == ["Old Name"]


def test_ac_8_create_line_lists_other_combos_on_host(db, tmp_path):
    _prod(db, "ZZAH2")
    _existing(db, "ZZAH2", "Other")
    _, out = _run(db, tmp_path, [_entry("ZZAH2", "Brand New", 1)])
    verdict, _h, _n, _p, details = _line(out, "Brand New")
    assert verdict == "CREATE"
    assert 'host also has: "Other"' in details


# --------------------------------------------------------------------------- AC-3


def test_ac_3_a_host_failure_rolls_back_the_whole_host(db, tmp_path, monkeypatch):
    from app.services.product_combo_service import ProductComboService

    for code in ("ZZTH1", "ZZTH2"):
        _prod(db, code)
    real = ProductComboService.create

    def create(self, host_id, name, *args, **kwargs):
        if name == "H1 second":
            raise RuntimeError("boom")
        return real(self, host_id, name, *args, **kwargs)

    monkeypatch.setattr(ProductComboService, "create", create)
    entries = [_entry("ZZTH1", "H1 first", 1), _entry("ZZTH1", "H1 second", 2), _entry("ZZTH2", "H2 only", 3)]
    _, out = _run(db, tmp_path, entries, apply=True)
    assert _combos(db, "ZZTH1") == []
    assert _line(out, "H1 first")[0].startswith("FAILED")
    assert _line(out, "H1 second")[0].startswith("FAILED")
    assert len(_combos(db, "ZZTH2", "H2 only")) == 1


# --------------------------------------------------------------------------- AC-18


def test_ac_18_extra_part_is_never_removed(db, tmp_path):
    _prod(db, "ZZXH1")
    extra = _prod(db, "ZZXP1")
    combo = _existing(db, "ZZXH1", "Pack")
    with company_scope(db, None):
        db.add(ProductComboPart(id=str(uuid.uuid4()), combo_id=combo.id, part_product_id=extra.id))
        db.commit()
    _run(db, tmp_path, [_entry("ZZXH1", "Pack", 1)], apply=True)
    assert "ZZXP1" in _parts(db, _combos(db, "ZZXH1", "Pack")[0])


# --------------------------------------------------------------------------- AC-19 / AC-20


def test_ac_19_ac_20_the_seed_file(db):
    assert SEED_FILE.exists(), "the flyer seed file is not created yet"
    data = json.loads(SEED_FILE.read_text(encoding="utf-8"))
    assert isinstance(data, list) and data
    script = _script()
    for entry in data:
        assert script.invalid_entry(entry) is None, entry
        assert isinstance(entry["page"], int) and not isinstance(entry["page"], bool)
    text = SEED_FILE.read_text(encoding="utf-8")
    assert not re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text), "email in seed"
    assert not re.search(r"(?<![\w.])\+?\d[\d \-()]{8,}\d(?![\w.])", text), "phone number in seed"


# --------------------------------------------------------------------------- AC-0


def test_ac_0_without_strict_the_output_has_no_strict_lines(db, tmp_path):
    _prod(db, "ZZLH1")
    code, out = _run(db, tmp_path, [_entry("ZZLH1", "Legacy", 1), _entry("ZZLMISSING", "Gone", 2)], strict=False)
    assert code == 0
    assert _lines(out) == []
    assert not any(line.startswith(VERDICTS) for line in out.splitlines())
