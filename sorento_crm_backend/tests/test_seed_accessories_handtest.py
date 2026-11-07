"""PRICETAG-ACCESSORIES crew pass (6 Nov): the dev-only seed that creates the hand-test combos.

Runs `seed()` against the blank test schema with the owner's product codes created first.
"""
from __future__ import annotations

import io

import pytest

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402,F401

from app.services.company_scope import register_company_scope_listeners

from tests import _ptag_combo_seed as seed
from tests import _ptag_r9_seed as r9
from tests._pg_fixture import blank_session

CODES = ["SRTKS7061-BL", "SRTWB7065", "SRTWT7202", "SRTW5000", "SRTKT1632SS"]


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


@pytest.fixture(autouse=True)
def _listeners(monkeypatch):
    register_company_scope_listeners()
    r9.block_respond(monkeypatch)


def _products(db, codes=CODES):
    rows = {}
    for code in codes:
        row = seed.product(db, "ZZSEED")
        row.product_code = code
        row.product_name = code
        rows[code] = row
    db.flush()
    return rows


def _run(db, apply):
    from scripts.seed_accessories_handtest import seed as run_seed

    out = io.StringIO()
    code = run_seed(db, seed.SORENTO, ["SRTWT7202", "SRTKT1632SS"], apply, out)
    return code, out.getvalue()


def _combo(db, host, name):
    from app.models.product_combo import ProductCombo

    return (
        db.query(ProductCombo)
        .filter(ProductCombo.host_product_id == host.id, ProductCombo.name == name)
        .first()
    )


def test_dry_run_writes_nothing(db):
    rows = _products(db)
    code, text = _run(db, apply=False)
    assert code == 0 and "dry run" in text
    assert _combo(db, rows["SRTKS7061-BL"], "Kitchen sink with 1 tap (hand test)") is None


def test_apply_creates_the_three_combos_with_parts_and_free_items(db):
    from app.services.accessory_service import AccessoryService

    rows = _products(db)
    code, _ = _run(db, apply=True)
    assert code == 0
    one = _combo(db, rows["SRTKS7061-BL"], "Kitchen sink with 1 tap (hand test)")
    two = _combo(db, rows["SRTKS7061-BL"], "Kitchen sink with 2 taps (hand test)")
    basin = _combo(db, rows["SRTWB7065"], "Basin with tap (hand test)")
    assert [p.part_product_id for p in one.parts] == [rows["SRTWT7202"].id]
    assert {p.part_product_id for p in two.parts} == {rows["SRTWT7202"].id, rows["SRTKT1632SS"].id}
    assert [p.part_product_id for p in basin.parts] == [rows["SRTWT7202"].id]

    service = AccessoryService(db)
    sink_free = service.combo_list(one.id)
    assert [(e["kind"], e["name"]) for e in sink_free] == [
        ("accessory", "DRAINER"),
        ("accessory", "PULL OUT DRAINER"),
    ]
    assert sink_free[0]["spec"] == "390x300x140, Depth: 160mm"
    (waste,) = service.combo_list(basin.id)
    assert waste["kind"] == "product" and waste["code"] == "SRTW5000"


def test_running_twice_changes_nothing(db):
    from app.models.accessory import Accessory
    from app.models.product_combo import ProductCombo

    rows = _products(db)
    _run(db, apply=True)
    _run(db, apply=True)
    assert db.query(ProductCombo).filter(ProductCombo.host_product_id == rows["SRTKS7061-BL"].id).count() == 2
    assert db.query(Accessory).filter(Accessory.name == "DRAINER").count() == 1
    one = _combo(db, rows["SRTKS7061-BL"], "Kitchen sink with 1 tap (hand test)")
    assert len(one.parts) == 1


def test_a_missing_product_writes_nothing_and_names_it(db):
    _products(db, [c for c in CODES if c != "SRTW5000"])
    code, text = _run(db, apply=True)
    assert code == 1 and "SRTW5000" in text


def test_apply_is_refused_outside_a_dev_environment(monkeypatch):
    from scripts import seed_accessories_handtest as script

    monkeypatch.setattr(script, "_environment", lambda: "production")
    out = io.StringIO()
    assert script.main(["--apply"], db=object(), out=out) == 1
    assert "refused" in out.getvalue()


def test_cleanup_removes_hand_test_combos_and_unused_crew_pass_accessories(db):
    from app.models.accessory import Accessory, ProductAccessory
    from app.models.product_combo import ProductCombo
    from scripts.seed_accessories_handtest import cleanup

    rows = _products(db)
    _run(db, apply=True)
    other = seed.combo(db, rows["SRTKS7061-BL"], "Kept real combo")
    unused = Accessory(name="crew-pass-2211b-acc", company_id=seed.SORENTO)
    used = Accessory(name="crew-pass-used", company_id=seed.SORENTO)
    db.add_all([unused, used])
    db.flush()
    db.add(ProductAccessory(product_id=rows["SRTKS7846"].id if "SRTKS7846" in rows else rows["SRTWB7065"].id, accessory_id=used.id, sort_order=0))
    db.flush()

    out = io.StringIO()
    assert cleanup(db, seed.SORENTO, apply=False, out=out) == 0
    assert db.query(ProductCombo).filter(ProductCombo.name.like("%(hand test)")).count() == 3

    out = io.StringIO()
    assert cleanup(db, seed.SORENTO, apply=True, out=out) == 0
    db.expire_all()
    assert db.query(ProductCombo).filter(ProductCombo.name.like("%(hand test)")).count() == 0
    assert db.query(ProductCombo).filter(ProductCombo.id == other.id).count() == 1
    assert db.query(Accessory).filter(Accessory.name == "crew-pass-2211b-acc").count() == 0
    assert db.query(Accessory).filter(Accessory.name == "crew-pass-used").count() == 1
    assert "keep accessory \"crew-pass-used\"" in out.getvalue()
    assert db.query(Accessory).filter(Accessory.name == "DRAINER").count() == 1, "library rows stay"


def test_apply_gives_colander_its_spec_and_a_picture(db, monkeypatch):
    from app.models.accessory import Accessory
    from app.services import accessory_service, storage_router
    from tests._fake_storage import FakeStorage

    fake = FakeStorage()
    for module in (storage_router, accessory_service):
        monkeypatch.setattr(module, "default_provider", lambda: "s3")
        monkeypatch.setattr(module, "get_backend", lambda provider: fake)
        monkeypatch.setattr(module, "cdn_base_url", lambda provider, key: f"https://cdn.test/{key}")
    _products(db)
    code, _ = _run(db, apply=True)
    assert code == 0
    colander = db.query(Accessory).filter(Accessory.name == "COLANDER").one()
    assert colander.spec == "390x300x140, Depth: 160mm"
    assert colander.image_attachment_id is not None
    assert len(fake.objects) == 1


def test_a_picture_that_cannot_be_stored_is_reported_and_the_rest_stands(db, monkeypatch):
    from app.models.product_combo import ProductCombo
    from app.services import accessory_service

    def broken(provider):
        raise RuntimeError("no storage credentials")

    monkeypatch.setattr(accessory_service, "get_backend", broken)
    rows = _products(db)
    code, text = _run(db, apply=True)
    assert code == 0
    assert "COLANDER picture not stored" in text
    assert db.query(ProductCombo).filter(ProductCombo.host_product_id == rows["SRTWB7065"].id).count() == 1
