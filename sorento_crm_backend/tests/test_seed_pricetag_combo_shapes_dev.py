"""PRICETAG-COMBO-RENDER fix round 3: `scripts/seed_pricetag_combo_shapes_dev.py` (dev only)."""
from __future__ import annotations

import io

import pytest

from app.models.base import company_scope, set_company_scope
from app.models.dealer_kit import ComboTagTemplate, TagTemplate
from app.models.product import Product
from app.models.product_combo import ProductCombo, ProductComboPart
from app.services.company_scope import DEFAULT_COMPANY_ID

from tests import _ptag_shapes_seed as shapes
from tests._pg_fixture import blank_session

CODES = [
    "SRTWB1419-BL", "SRTWT7449-BL", "SRTWT7449-RG", "SRTWT5831-BL", "SRTKS7061", "SRTKT1862SS",
    "SRTKT1863SS", "SRTKT1871SS", "SRTKT71SS", "SRTBF11829", "SRTMCB8083-BL", "SRTWT6203-GM",
]


def _script():
    from scripts import seed_pricetag_combo_shapes_dev as script

    return script


@pytest.fixture()
def db():
    with blank_session() as session:
        set_company_scope(session, frozenset({DEFAULT_COMPANY_ID}))
        yield session


@pytest.fixture()
def catalogue(db):
    rows = {code: shapes.prod(db, code) for code in CODES}
    rows["SRTWT5831-BL"].is_discontinued = True
    db.commit()
    return rows


@pytest.fixture()
def as_dev(monkeypatch):
    monkeypatch.setattr(_script(), "database_name", lambda _db: "sorento_dev_1028")


def _run(db, *flags):
    out = io.StringIO()
    code = _script().main(list(flags), db=db, out=out)
    return code, out.getvalue()


def _count(db, model):
    db.expire_all()
    with company_scope(db, None):
        return db.query(model).count()


def _combo(db, name):
    db.expire_all()
    with company_scope(db, None):
        return db.query(ProductCombo).filter(ProductCombo.name == name).first()


def _parts(db, combo):
    with company_scope(db, None):
        return {
            p.part_product.product_code: p
            for p in db.query(ProductComboPart).filter(ProductComboPart.combo_id == combo.id).all()
        }


@pytest.mark.parametrize("name", ["sorento_main", "sorento", "sorento_staging_1"])
def test_refuses_a_database_with_no_dev_token(db, catalogue, monkeypatch, name):
    monkeypatch.setattr(_script(), "database_name", lambda _db: name)
    code, out = _run(db, "--apply")
    assert code != 0 and name in out
    assert _count(db, ProductCombo) == 0 and _count(db, TagTemplate) == 0


@pytest.mark.parametrize("name", ["sorento_prod", "sorento_dev_production", "prod_dev"])
def test_refuses_production_even_with_a_dev_token(db, catalogue, monkeypatch, name):
    monkeypatch.setattr(_script(), "database_name", lambda _db: name)
    code, _out = _run(db, "--apply")
    assert code != 0
    assert _count(db, ProductCombo) == 0


@pytest.mark.parametrize("name", ["sorento_dev_1028", "sorento_ci", "dev", "sorento-dev"])
def test_accepts_dev_and_ci_tokens(name):
    assert _script().refusal(name) is None


# --confirm-db: an operator names the exact database to skip the name-token check (crew's shared
# dev copy is called sorento_prod_1020). Only an exact match counts; absent keeps the token check.
DEV_COPY = "sorento_prod_1020"


def test_confirm_db_matching_the_connected_name_exactly_is_accepted(db, catalogue, monkeypatch):
    monkeypatch.setattr(_script(), "database_name", lambda _db: DEV_COPY)
    assert _script().refusal(DEV_COPY, confirm_db=DEV_COPY) is None
    code, out = _run(db, "--confirm-db", DEV_COPY)
    assert code == 0 and "DRY RUN" in out


@pytest.mark.parametrize(
    "confirm", ["sorento_prod_1028", "sorento_prod", "SORENTO_PROD_1020", " sorento_prod_1020", "sorento_prod_*", "*"]
)
def test_confirm_db_that_does_not_match_exactly_is_refused(db, catalogue, monkeypatch, confirm):
    monkeypatch.setattr(_script(), "database_name", lambda _db: DEV_COPY)
    assert _script().refusal(DEV_COPY, confirm_db=confirm) is not None
    code, out = _run(db, "--apply", "--confirm-db", confirm)
    assert code != 0 and "does not match" in out
    assert _count(db, ProductCombo) == 0 and _count(db, TagTemplate) == 0


def test_without_confirm_db_the_token_check_still_refuses_a_prod_name(db, catalogue, monkeypatch):
    monkeypatch.setattr(_script(), "database_name", lambda _db: DEV_COPY)
    assert _script().refusal(DEV_COPY) is not None
    code, _out = _run(db, "--apply")
    assert code != 0
    assert _count(db, ProductCombo) == 0


def test_prints_host_and_database_before_writing(db, catalogue, monkeypatch):
    monkeypatch.setattr(_script(), "database_name", lambda _db: DEV_COPY)
    monkeypatch.setattr(_script(), "database_host", lambda _db: "db.example.internal")
    _code, out = _run(db, "--confirm-db", DEV_COPY)
    first = out.splitlines()[0]
    assert "db.example.internal" in first and DEV_COPY in first


def test_prints_the_database_name_it_will_write_to(db, catalogue, as_dev):
    _code, out = _run(db)
    assert "sorento_dev_1028" in out


def test_dry_run_writes_nothing(db, catalogue, as_dev):
    code, out = _run(db)
    assert code == 0 and "DRY RUN" in out
    assert _count(db, ProductCombo) == 0 and _count(db, TagTemplate) == 0 and _count(db, ComboTagTemplate) == 0


def test_apply_creates_the_shapes_the_starters_and_the_links(db, catalogue, as_dev):
    code, out = _run(db, "--apply")
    assert code == 0, out
    assert set(_parts(db, _combo(db, "Basin + tap"))) == {"SRTWT7449-BL"}
    colour = _combo(db, "Basin + tap colour")
    parts = _parts(db, colour)
    assert set(parts) == {"SRTWT7449-BL", "SRTWT7449-RG"} and parts["SRTWT7449-RG"].choice_group == "Tap colour"
    sink = _combo(db, "Sink + taps with top-up")
    sink_parts = _parts(db, sink)
    assert {"SRTKT1862SS", "SRTKT1863SS", "SRTKT1871SS", "SRTKT71SS"} == set(sink_parts)
    assert sink_parts["SRTKT71SS"].is_upgrade and sink_parts["SRTKT71SS"].topup_amount == 150
    assert sink.sell_price == 849
    flagged = _parts(db, _combo(db, "Basin + tap colour (discontinued option)"))
    assert "SRTWT5831-BL" in flagged and flagged["SRTWT5831-BL"].part_product.is_discontinued
    assert _count(db, TagTemplate) == 4
    db.expire_all()
    with company_scope(db, None):
        linked = {(r.combo_id, r.template_id) for r in db.query(ComboTagTemplate).all()}
        sink_links = {t for c, t in linked if c == sink.id}
    assert sink_links, "the sink combo has at least one starter that fits it"


def test_a_rerun_changes_nothing(db, catalogue, as_dev):
    _run(db, "--apply")
    before = (_count(db, ProductCombo), _count(db, ProductComboPart), _count(db, TagTemplate), _count(db, ComboTagTemplate))
    code, _out = _run(db, "--apply")
    assert code == 0
    after = (_count(db, ProductCombo), _count(db, ProductComboPart), _count(db, TagTemplate), _count(db, ComboTagTemplate))
    assert before == after


def test_a_missing_code_is_reported_and_never_created(db, catalogue, as_dev):
    products_before = _count(db, Product)
    with company_scope(db, None):
        gone = db.query(Product).filter(Product.product_code == "SRTKT1863SS").one()
        db.delete(gone)
        db.commit()
    products_before -= 1
    code, out = _run(db, "--apply")
    assert code == 0
    assert "SRTKT1863SS" in out
    assert _count(db, Product) == products_before
    assert "SRTKT1863SS" not in _parts(db, _combo(db, "Sink + taps with top-up"))


def test_without_a_discontinued_product_the_fourth_combo_is_not_seeded(db, catalogue, as_dev):
    with company_scope(db, None):
        db.query(Product).filter(Product.product_code == "SRTWT5831-BL").one().is_discontinued = False
        db.commit()
    _code, out = _run(db, "--apply")
    assert "no discontinued option seeded" in out
    assert _combo(db, "Basin + tap colour (discontinued option)") is None


def test_it_extends_a_group_from_the_hosts_existing_combo(db, catalogue, as_dev):
    from tests import _ptag_combo_seed as seed

    extra = shapes.prod(db, "SRTKT1880SS")
    seed.combo(
        db, catalogue["SRTKS7061"], "Existing sink pack",
        parts=[{"product": catalogue["SRTKT1862SS"], "group": "Kitchen tap"}, {"product": extra, "group": "Kitchen tap"}],
    )
    db.commit()
    _run(db, "--apply")
    assert "SRTKT1880SS" in _parts(db, _combo(db, "Sink + taps with top-up"))


def test_a_discontinued_option_of_the_existing_combo_is_not_carried_into_the_new_one(db, catalogue, as_dev):
    from tests import _ptag_combo_seed as seed

    old = shapes.prod(db, "SRTKT1892SS")
    old.is_discontinued = True
    seed.combo(
        db, catalogue["SRTKS7061"], "Existing sink pack",
        parts=[{"product": catalogue["SRTKT1862SS"], "group": "Kitchen tap"}, {"product": old, "group": "Kitchen tap"}],
    )
    db.commit()
    _code, out = _run(db, "--apply")
    assert "SRTKT1892SS" not in _parts(db, _combo(db, "Sink + taps with top-up"))
    assert "sink-taps-topup: new" in out, "not reported unsure for another combo's discontinued option"
