"""PRICETAG-ALA-CARTE backend: one product on two lines, told apart by package.

Contract: `documentation/plans/dealer-kit/pricetag-ala-carte-acceptance-criteria.md`,
AC-12, AC-13, AC-14, AC-16 and AC-17. "Package" of a product line = its `combo_id`; None =
ala carte. Set lines have no package.

Written test-FIRST (PRINCIPLES.md Phase 2). Today `_raise_on_duplicate_line` keys a product
line on `product_id` alone and the table's `uq_ptag_line_request_product` constraint does the
same, so every request below that holds one product twice is refused with DUPLICATE_LINE
before the assertion that matters runs: that is the red reason.

Postgres only (`tests/_pg_fixture.blank_session`), every row seeded here with its own FK
chain (`tests/_ptag_combo_seed.py`). Codes and prices are synthetic.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

import pytest
from fastapi import HTTPException

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402,F401

from app.models.price_tag import PriceTagRequestLine
from app.services.price_tag_request_service import PriceTagRequestService

from tests import _ptag_combo_seed as seed
from tests import _ptag_r9_seed as r9
from tests._pg_fixture import blank_session, unique_code

SORENTO = seed.SORENTO
ALA_CARTE = "Ala carte"


@pytest.fixture()
def db():
    with blank_session() as session:
        yield session


@pytest.fixture(autouse=True)
def _quiet(monkeypatch):
    r9.block_respond(monkeypatch)
    with patch("app.services.queue_service.enqueue_job", return_value=None):
        yield


def _lines_of(db, request_id):
    db.expire_all()
    return (
        db.query(PriceTagRequestLine)
        .filter(PriceTagRequestLine.request_id == request_id)
        .order_by(PriceTagRequestLine.sort_order.asc(), PriceTagRequestLine.id.asc())
        .all()
    )


def _code_of(exc) -> str | None:
    code = getattr(exc, "code", None)
    if code:
        return code
    detail = getattr(exc, "detail", None)
    return detail.get("code") if isinstance(detail, dict) else None


def _message_of(exc) -> str:
    message = getattr(exc, "message", None)
    if message:
        return message
    detail = getattr(exc, "detail", None)
    return str(detail.get("message")) if isinstance(detail, dict) else str(exc)


def _host_with_one_combo(db, *, list_price="100.00", combo_list_price=None, name=None):
    host = seed.product(db, "P-ALA", list_price=list_price)
    combo = seed.combo(
        db, host, name or unique_code("ZZT Pkg A"), list_price=combo_list_price
    )
    return host, combo


# =========================================================================== AC-12 create


def test_ac12_one_product_ala_carte_and_on_its_combo_is_two_lines(db):
    host, combo = _host_with_one_combo(db)

    request = seed.submit(
        db, [seed.line_dict(host, combo), seed.line_dict(host, None)]
    )

    lines = _lines_of(db, request.id)
    assert len(lines) == 2
    assert {line.product_id for line in lines} == {host.id}
    assert sorted(str(line.combo_id) for line in lines) == sorted([str(combo.id), "None"])


def test_ac12_one_product_on_two_different_combos_is_two_lines(db):
    host, first = _host_with_one_combo(db)
    second = seed.combo(db, host, unique_code("ZZT Pkg B"))

    request = seed.submit(
        db, [seed.line_dict(host, first), seed.line_dict(host, second)]
    )

    lines = _lines_of(db, request.id)
    assert len(lines) == 2
    assert {str(line.combo_id) for line in lines} == {str(first.id), str(second.id)}


def test_ac12_same_product_same_combo_twice_is_422_duplicate_line_naming_the_code(db):
    host, combo = _host_with_one_combo(db)

    with pytest.raises(HTTPException) as exc_info:
        seed.submit(db, [seed.line_dict(host, combo), seed.line_dict(host, combo)])

    assert exc_info.value.status_code == 422
    assert _code_of(exc_info.value) == "DUPLICATE_LINE"
    assert host.product_code in _message_of(exc_info.value)


def test_ac12_same_product_ala_carte_twice_is_422_duplicate_line(db):
    host, _combo = _host_with_one_combo(db)

    with pytest.raises(HTTPException) as exc_info:
        seed.submit(db, [seed.line_dict(host, None), seed.line_dict(host, None)])

    assert exc_info.value.status_code == 422
    assert _code_of(exc_info.value) == "DUPLICATE_LINE"
    assert host.product_code in _message_of(exc_info.value)


def test_ac12_the_same_set_twice_is_still_422(db):
    product_set = r9.seed_product_set(db)
    set_line = {"line_type": "product_set", "product_set_id": product_set.id, "quantity": 1}

    with pytest.raises(HTTPException) as exc_info:
        seed.submit(db, [dict(set_line), dict(set_line)])

    assert exc_info.value.status_code == 422
    assert _code_of(exc_info.value) == "DUPLICATE_LINE"
    assert product_set.set_code in _message_of(exc_info.value)


def test_ac12_update_with_the_same_pair_twice_is_422_and_two_packages_save(db):
    """replace_lines (the draft PUT / post-submit PUT) runs the same keyed check."""
    host, combo = _host_with_one_combo(db)
    request = seed.submit(db, [seed.line_dict(host, None)])

    with pytest.raises(HTTPException) as exc_info:
        PriceTagRequestService.replace_lines(
            db, request, [seed.line_dict(host, combo), seed.line_dict(host, combo)]
        )
    assert _code_of(exc_info.value) == "DUPLICATE_LINE"

    PriceTagRequestService.replace_lines(
        db, request, [seed.line_dict(host, None), seed.line_dict(host, combo)]
    )
    assert len(_lines_of(db, request.id)) == 2


# =========================================================================== AC-13 replace_lines


def _tag(line):
    return r9.tags_of(line)[0]


def test_ac13_re_save_keeps_each_lines_own_tags_and_overrides(db):
    host, combo = _host_with_one_combo(db)
    request = seed.submit(
        db,
        [
            seed.line_dict(host, None, quantity=2),
            seed.line_dict(host, combo, quantity=3),
        ],
    )
    lines = _lines_of(db, request.id)
    ala = next(line for line in lines if line.combo_id is None)
    pkg = next(line for line in lines if line.combo_id is not None)
    ala_tag, pkg_tag = _tag(ala), _tag(pkg)
    ala_tag.marketing_price_override = Decimal("11.00")
    ala_tag.marketing_override_reason = "ZZT ala carte override"
    pkg_tag.marketing_price_override = Decimal("22.00")
    pkg_tag.marketing_override_reason = "ZZT package override"
    ala_tag_id, pkg_tag_id = ala_tag.id, pkg_tag.id
    db.flush()

    # The form re-sends the whole table, in the other order this time.
    PriceTagRequestService.replace_lines(
        db,
        request,
        [
            seed.line_dict(host, combo, quantity=3),
            seed.line_dict(host, None, quantity=2),
        ],
    )
    db.flush()

    lines = _lines_of(db, request.id)
    assert len(lines) == 2
    ala = next(line for line in lines if line.combo_id is None)
    pkg = next(line for line in lines if line.combo_id is not None)
    assert [t.id for t in r9.tags_of(ala)] == [ala_tag_id]
    assert [t.id for t in r9.tags_of(pkg)] == [pkg_tag_id]
    assert Decimal(str(_tag(ala).marketing_price_override)) == Decimal("11.00")
    assert _tag(ala).marketing_override_reason == "ZZT ala carte override"
    assert Decimal(str(_tag(pkg).marketing_price_override)) == Decimal("22.00")
    assert _tag(pkg).marketing_override_reason == "ZZT package override"


# =========================================================================== AC-12/13 portal revise


def _revise_setup(db, lines):
    from app.services.portal_revision_service import PortalRevisionService  # noqa: F401
    from tests.test_portal_price_tag_revise import (
        _seed_contact,
        _seed_ptag_config,
        _seed_system_settings,
        _seed_token,
    )

    _seed_system_settings(db, cap=3)
    _seed_ptag_config(db, max_revisions=None)
    contact = _seed_contact(db)
    request = PriceTagRequestService.create_request(
        db,
        contact_id=contact.id,
        company_id=SORENTO,
        data={"debtor_name": "ZZT Original Dealer", "lines": lines},
    )
    request.status = "proof_ready"
    request.portal_draft_at = None
    request.print_by = "office"
    request.revision_no = 0
    db.commit()
    return contact, request, _seed_token(contact)


def _revise(db, token, request, products):
    from app.services.portal_revision_service import PortalRevisionService

    return PortalRevisionService(db).revise(
        token, "price_tag_request", str(request.id), {"products": products}, "Reason", 0
    )


def test_ac13_portal_revise_with_ala_carte_and_package_lines_keeps_each_lines_own(db):
    host, combo = _host_with_one_combo(db)
    fixed = seed.product(db, "P-ALA-PART", list_price="20.00")
    combo_with_part = seed.combo(db, host, unique_code("ZZT Pkg F"), parts=[{"product": fixed}])
    contact, request, token = _revise_setup(
        db,
        [
            seed.line_dict(host, None, quantity=1),
            seed.line_dict(host, combo_with_part, [{"product_id": fixed.id}], quantity=1),
        ],
    )
    lines = _lines_of(db, request.id)
    ala = next(line for line in lines if line.combo_id is None)
    pkg = next(line for line in lines if line.combo_id is not None)
    _tag(ala).marketing_price_override = Decimal("11.00")
    _tag(pkg).marketing_price_override = Decimal("22.00")
    ala_tag_id, pkg_tag_id = _tag(ala).id, _tag(pkg).id
    db.commit()

    # The composer sends each line's package; parts are carried from the old line.
    _revise(
        db,
        token,
        request,
        [
            {"product_id": host.id, "combo_id": None, "quantity": 4},
            {"product_id": host.id, "combo_id": combo_with_part.id, "quantity": 5},
        ],
    )

    lines = _lines_of(db, request.id)
    assert len(lines) == 2
    ala = next(line for line in lines if line.combo_id is None)
    pkg = next(line for line in lines if line.combo_id is not None)
    assert str(pkg.combo_id) == str(combo_with_part.id)
    assert ala.quantity == 4 and pkg.quantity == 5
    assert [p.product_id for p in (ala.parts or [])] == []
    assert [p.product_id for p in (pkg.parts or [])] == [fixed.id]
    assert [t.id for t in r9.tags_of(ala)] == [ala_tag_id]
    assert [t.id for t in r9.tags_of(pkg)] == [pkg_tag_id]
    assert Decimal(str(_tag(ala).marketing_price_override)) == Decimal("11.00")
    assert Decimal(str(_tag(pkg).marketing_price_override)) == Decimal("22.00")


def test_ac12_portal_revise_same_pair_twice_is_422_before_any_mutation(db):
    host, combo = _host_with_one_combo(db)
    contact, request, token = _revise_setup(
        db, [seed.line_dict(host, None), seed.line_dict(host, combo)]
    )

    with pytest.raises(HTTPException) as exc_info:
        _revise(
            db,
            token,
            request,
            [
                {"product_id": host.id, "combo_id": combo.id, "quantity": 1},
                {"product_id": host.id, "combo_id": combo.id, "quantity": 2},
            ],
        )

    assert exc_info.value.status_code == 422
    assert _code_of(exc_info.value) == "DUPLICATE_LINE"
    lines = _lines_of(db, request.id)
    assert len(lines) == 2, "a refused revision leaves both original lines in place"
    assert sorted(str(line.combo_id) for line in lines) == sorted([str(combo.id), "None"])


# =========================================================================== AC-14 regression


def test_ac14_ala_carte_line_beside_its_combo_line_prints_the_products_own_price_and_list(db):
    from tests.test_accessories import _accessory, _link_combo, _link_product, _name

    host, combo = _host_with_one_combo(db, list_price="1000.00", combo_list_price=Decimal("1500.00"))
    own = _accessory(db, _name("OWNACC"))
    packaged = _accessory(db, _name("PKGACC"))
    _link_product(db, host, [own])
    _link_combo(db, combo, [packaged])

    request = seed.submit(db, [seed.line_dict(host, None), seed.line_dict(host, combo)])
    db.flush()

    rows = seed.rows(db, request)
    assert len(rows) == 2
    line_combo = {line.id: line.combo_id for line in _lines_of(db, request.id)}
    ala_row = next(row for row in rows if line_combo[row["line_id"]] is None)
    pkg_row = next(row for row in rows if line_combo[row["line_id"]] is not None)

    assert Decimal(str(ala_row["list_price"])) == Decimal("1000.00")
    assert ala_row["combo"] is None
    assert [item["name"] for item in ala_row["accessories"]] == [own.name]

    assert Decimal(str(pkg_row["list_price"])) == Decimal("1500.00")
    assert [item["name"] for item in pkg_row["accessories"]] == [packaged.name]


# =========================================================================== AC-16 combo delete


def test_ac16_deleting_a_combo_merges_its_line_into_the_ala_carte_line(db):
    from app.services.product_combo_service import ProductComboService

    host, combo = _host_with_one_combo(db)
    request = seed.submit(
        db,
        [
            seed.line_dict(host, None, quantity=2),
            seed.line_dict(host, combo, quantity=3),
        ],
    )
    lines = _lines_of(db, request.id)
    ala = next(line for line in lines if line.combo_id is None)
    ala_id = ala.id
    ala_tag_ids = [t.id for t in r9.tags_of(ala)]
    db.commit()

    ProductComboService(db).delete(combo.id)

    lines = _lines_of(db, request.id)
    assert len(lines) == 1, "one ala carte line of the product is left"
    (survivor,) = lines
    assert survivor.id == ala_id
    assert survivor.product_id == host.id
    assert survivor.combo_id is None
    assert survivor.quantity == 5
    assert [t.id for t in r9.tags_of(survivor)] == ala_tag_ids


def test_ac16_a_request_with_only_the_package_line_turns_ala_carte(db):
    from app.services.product_combo_service import ProductComboService

    host, combo = _host_with_one_combo(db)
    merged = seed.submit(
        db, [seed.line_dict(host, None, quantity=1), seed.line_dict(host, combo, quantity=1)]
    )
    only_pkg = seed.submit(db, [seed.line_dict(host, combo, quantity=5)])
    db.commit()

    ProductComboService(db).delete(combo.id)

    (line,) = _lines_of(db, only_pkg.id)
    assert line.combo_id is None
    assert line.quantity == 5
    assert len(_lines_of(db, merged.id)) == 1


# =========================================================================== AC-17 snapshot + diff


def test_ac17_the_revision_snapshot_carries_item_code_and_package(db):
    from app.services.portal_revision_service import _serialize_price_tag_lines

    host, combo = _host_with_one_combo(db, name=unique_code("ZZT Pkg Snap"))
    product_set = r9.seed_product_set(db)
    request = seed.submit(
        db,
        [
            seed.line_dict(host, None),
            seed.line_dict(host, combo),
            {"line_type": "product_set", "product_set_id": product_set.id, "quantity": 1},
        ],
    )
    db.flush()

    lines = _serialize_price_tag_lines(db, request)
    assert [line["item_code"] for line in lines] == [
        host.product_code,
        host.product_code,
        product_set.set_code,
    ]
    assert lines[0]["package"] == ALA_CARTE
    assert lines[1]["package"] == combo.name


def test_ac17_a_package_change_is_a_named_line_change():
    from app.services.portal_revision_service import _diff_lines

    before = [{"item_code": "P-ALA-1", "quantity": 1, "package": "ZZT Pkg A"}]
    after = [{"item_code": "P-ALA-1", "quantity": 1, "package": ALA_CARTE}]

    changes = _diff_lines(before, after)

    assert len(changes) == 1
    (change,) = changes
    assert "package" in change["label"].lower()
    assert change["label"] == "Product line 1 package"
    assert change["from"] == "ZZT Pkg A"
    assert change["to"] == ALA_CARTE
