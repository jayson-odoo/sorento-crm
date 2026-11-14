"""PRICETAG-ALA-CARTE backend: the same product any number of times, told apart by line id.

Contract: `documentation/plans/dealer-kit/pricetag-ala-carte-acceptance-criteria.md`
(rewritten after the owner's final answers, 13 Nov): AC-11, AC-12, AC-13, AC-15, AC-16.
"Package" of a product line = its `combo_id`; None = ala carte. Set lines unchanged.

Written test-FIRST (PRINCIPLES.md Phase 2). Today `_raise_on_duplicate_line` refuses a
product that repeats with 422 DUPLICATE_LINE, `uq_ptag_line_request_product` refuses it at
the table, and `replace_lines` / portal revise carry tags keyed by product, not by line id.
Every request below that holds one product twice is therefore refused before the
assertion that matters runs: that is the red reason.

Postgres only (`tests/_pg_fixture.blank_session`), every row seeded here with its own FK
chain (`tests/_ptag_combo_seed.py`). Codes and prices are synthetic.
"""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

import pytest
from fastapi import HTTPException

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402,F401

from app.models.price_tag import PriceTagRequestLine, PriceTagRequestTag
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


def _by_remark(db, request_id) -> dict:
    return {line.remarks: line for line in _lines_of(db, request_id)}


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
    combo = seed.combo(db, host, name or unique_code("ZZT Pkg A"), list_price=combo_list_price)
    return host, combo


def _tag_state(line) -> list[tuple]:
    """A line's tags as (id, quantity, override, reason, print_excluded), print order."""
    return [
        (
            tag.id,
            tag.quantity,
            None if tag.marketing_price_override is None else Decimal(str(tag.marketing_price_override)),
            tag.marketing_override_reason,
            bool(tag.print_excluded),
        )
        for tag in r9.tags_of(line)
    ]


# =========================================================================== AC-11 no product duplicate refusal


def test_ac11_one_product_ala_carte_and_on_its_combo_is_two_lines(db):
    host, combo = _host_with_one_combo(db)

    request = seed.submit(db, [seed.line_dict(host, combo), seed.line_dict(host, None)])

    lines = _lines_of(db, request.id)
    assert len(lines) == 2
    assert sorted(str(line.combo_id) for line in lines) == sorted([str(combo.id), "None"])


def test_ac11_same_product_ala_carte_twice_is_accepted(db):
    host, _combo = _host_with_one_combo(db)

    request = seed.submit(
        db, [seed.line_dict(host, None, quantity=1), seed.line_dict(host, None, quantity=2)]
    )

    lines = _lines_of(db, request.id)
    assert [(line.product_id, line.combo_id, line.quantity) for line in lines] == [
        (host.id, None, 1),
        (host.id, None, 2),
    ]


def test_ac11_same_product_same_combo_three_times_is_accepted(db):
    host, combo = _host_with_one_combo(db)

    request = seed.submit(db, [seed.line_dict(host, combo) for _ in range(3)])

    lines = _lines_of(db, request.id)
    assert len(lines) == 3
    assert {str(line.combo_id) for line in lines} == {str(combo.id)}


def test_ac11_create_request_draft_accepts_a_repeated_product(db):
    """The draft path (`create_request`, no submit) takes the same rule."""
    host, _combo = _host_with_one_combo(db)

    request = PriceTagRequestService.create_request(
        db,
        contact_id=seed.contact(db).id,
        company_id=SORENTO,
        data={"debtor_name": "ZZT Dealer", "lines": [seed.line_dict(host), seed.line_dict(host)]},
    )

    assert len(_lines_of(db, request.id)) == 2


def test_ac11_update_replace_lines_accepts_a_repeated_product(db):
    host, combo = _host_with_one_combo(db)
    request = seed.submit(db, [seed.line_dict(host, None)])

    PriceTagRequestService.replace_lines(
        db,
        request,
        [seed.line_dict(host, None), seed.line_dict(host, None), seed.line_dict(host, combo)],
    )

    assert len(_lines_of(db, request.id)) == 3


def test_ac11_the_same_set_twice_is_still_422_naming_the_set(db):
    """Regression guard: sets are unchanged (passes today, must stay green)."""
    product_set = r9.seed_product_set(db)
    set_line = {"line_type": "product_set", "product_set_id": product_set.id, "quantity": 1}

    with pytest.raises(HTTPException) as exc_info:
        seed.submit(db, [dict(set_line), dict(set_line)])

    assert exc_info.value.status_code == 422
    assert _code_of(exc_info.value) == "DUPLICATE_LINE"
    assert product_set.set_code in _message_of(exc_info.value)


# =========================================================================== AC-12 replace_lines carries by line id


def _three_line_request(db):
    """P ala carte (L1), P ala carte (L2, split into two tags by marketing), P + C (L3).

    Every tag gets its own override so a swap between lines is visible. Returns
    (host, combo, request, {remark: line id}, {remark: tag state}).
    """
    host, combo = _host_with_one_combo(db)
    request = seed.submit(
        db,
        [
            seed.line_dict(host, None, quantity=1, remarks="L1"),
            seed.line_dict(host, None, quantity=4, remarks="L2"),
            seed.line_dict(host, combo, quantity=3, remarks="L3"),
        ],
    )
    lines = _by_remark(db, request.id)
    for remark, figure in (("L1", "11.00"), ("L2", "22.00"), ("L3", "33.00")):
        tag = r9.tags_of(lines[remark])[0]
        tag.marketing_price_override = Decimal(figure)
        tag.marketing_override_reason = f"ZZT override {remark}"
    # Marketing split L2 by hand: two tags of 2, the second not printed.
    first = r9.tags_of(lines["L2"])[0]
    first.quantity = 2
    db.add(
        PriceTagRequestTag(
            line_id=lines["L2"].id,
            sort_order=1,
            quantity=2,
            choices={},
            marketing_price_override=Decimal("23.00"),
            marketing_override_reason="ZZT override L2b",
            print_excluded=True,
        )
    )
    db.flush()
    lines = _by_remark(db, request.id)
    ids = {remark: line.id for remark, line in lines.items()}
    state = {remark: _tag_state(line) for remark, line in lines.items()}
    assert len(state["L2"]) == 2
    return host, combo, request, ids, state


def _payload(host, combo, remark, quantity, line_id=None):
    line = seed.line_dict(host, combo, quantity=quantity, remarks=remark)
    if line_id is not None:
        line["id"] = line_id
    return line


def test_ac12_re_save_with_ids_in_swapped_order_keeps_each_lines_own_tags(db):
    host, combo, request, ids, state = _three_line_request(db)

    # L2 first, then L3, then L1: a product-keyed fallback would hand L1's tags to L2.
    PriceTagRequestService.replace_lines(
        db,
        request,
        [
            _payload(host, None, "L2", 4, ids["L2"]),
            _payload(host, combo, "L3", 3, ids["L3"]),
            _payload(host, None, "L1", 1, ids["L1"]),
        ],
    )
    db.flush()

    after = {remark: _tag_state(line) for remark, line in _by_remark(db, request.id).items()}
    assert after == state


def test_ac12_re_save_without_ids_claims_old_lines_in_order_per_package(db):
    """Compatibility fallback: the first unclaimed old line with the same
    (product_id, product_set_id, combo_id), each old line claimed once."""
    host, combo, request, _ids, state = _three_line_request(db)

    PriceTagRequestService.replace_lines(
        db,
        request,
        [
            _payload(host, None, "L1", 1),
            _payload(host, None, "L2", 4),
            _payload(host, combo, "L3", 3),
        ],
    )
    db.flush()

    after = {remark: _tag_state(line) for remark, line in _by_remark(db, request.id).items()}
    assert after == state


def test_ac12_a_new_extra_line_of_the_same_product_gets_fresh_tags(db):
    host, combo, request, ids, state = _three_line_request(db)
    carried_tag_ids = {tag[0] for tags in state.values() for tag in tags}

    PriceTagRequestService.replace_lines(
        db,
        request,
        [
            _payload(host, None, "L1", 1, ids["L1"]),
            _payload(host, None, "L2", 4, ids["L2"]),
            _payload(host, combo, "L3", 3, ids["L3"]),
            _payload(host, None, "L4", 7),
        ],
    )
    db.flush()

    lines = _by_remark(db, request.id)
    after = {remark: _tag_state(line) for remark, line in lines.items() if remark != "L4"}
    assert after == state
    (fresh,) = _tag_state(lines["L4"])
    assert fresh[0] not in carried_tag_ids
    assert fresh[1:] == (7, None, None, False)


# =========================================================================== AC-11/12 portal revise


def _revise_setup(db, lines):
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
    return request, _seed_token(contact)


def _revise(db, token, request, products):
    from app.services.portal_revision_service import PortalRevisionService

    return PortalRevisionService(db).revise(
        token, "price_tag_request", str(request.id), {"products": products}, "Reason", 0
    )


def test_ac11_portal_revise_accepts_the_same_product_twice(db):
    host, _combo = _host_with_one_combo(db)
    request, token = _revise_setup(db, [seed.line_dict(host, None)])

    _revise(
        db,
        token,
        request,
        [
            {"product_id": host.id, "quantity": 1},
            {"product_id": host.id, "quantity": 2},
        ],
    )

    lines = _lines_of(db, request.id)
    assert [(line.product_id, line.quantity) for line in lines] == [(host.id, 1), (host.id, 2)]


def test_ac12_portal_revise_by_line_id_keeps_each_lines_package_parts_and_tags(db):
    host, _combo = _host_with_one_combo(db)
    fixed = seed.product(db, "P-ALA-PART", list_price="20.00")
    combo = seed.combo(db, host, unique_code("ZZT Pkg F"), parts=[{"product": fixed}])
    request, token = _revise_setup(
        db,
        [
            seed.line_dict(host, None, quantity=1, remarks="L1"),
            seed.line_dict(host, None, quantity=1, remarks="L2"),
            seed.line_dict(host, combo, [{"product_id": fixed.id}], quantity=1, remarks="L3"),
        ],
    )
    lines = _by_remark(db, request.id)
    for remark, figure in (("L1", "11.00"), ("L2", "22.00"), ("L3", "33.00")):
        r9.tags_of(lines[remark])[0].marketing_price_override = Decimal(figure)
    ids = {remark: line.id for remark, line in lines.items()}
    tag_ids = {remark: [t.id for t in r9.tags_of(line)] for remark, line in lines.items()}
    db.commit()

    # Swapped order, new quantities; the composer sends each saved line's id and package.
    _revise(
        db,
        token,
        request,
        [
            {"id": ids["L3"], "product_id": host.id, "combo_id": combo.id, "quantity": 5, "remarks": "L3"},
            {"id": ids["L2"], "product_id": host.id, "combo_id": None, "quantity": 6, "remarks": "L2"},
            {"id": ids["L1"], "product_id": host.id, "combo_id": None, "quantity": 7, "remarks": "L1"},
        ],
    )

    lines = _by_remark(db, request.id)
    assert set(lines) == {"L1", "L2", "L3"}
    assert str(lines["L3"].combo_id) == str(combo.id)
    assert lines["L1"].combo_id is None and lines["L2"].combo_id is None
    assert [p.product_id for p in (lines["L3"].parts or [])] == [fixed.id]
    assert list(lines["L1"].parts or []) == [] and list(lines["L2"].parts or []) == []
    assert (lines["L1"].quantity, lines["L2"].quantity, lines["L3"].quantity) == (7, 6, 5)
    for remark, figure in (("L1", "11.00"), ("L2", "22.00"), ("L3", "33.00")):
        assert [t.id for t in r9.tags_of(lines[remark])] == tag_ids[remark]
        assert Decimal(str(r9.tags_of(lines[remark])[0].marketing_price_override)) == Decimal(figure)


def test_ac11_portal_revise_still_refuses_a_set_twice_before_any_mutation(db):
    """Regression guard: sets unchanged (passes today, must stay green)."""
    host, _combo = _host_with_one_combo(db)
    product_set = r9.seed_product_set(db)
    request, token = _revise_setup(db, [seed.line_dict(host, None)])

    with pytest.raises(HTTPException) as exc_info:
        _revise(
            db,
            token,
            request,
            [
                {"product_set_id": product_set.id, "quantity": 1},
                {"product_set_id": product_set.id, "quantity": 2},
            ],
        )

    assert exc_info.value.status_code == 422
    assert _code_of(exc_info.value) == "DUPLICATE_LINE"
    lines = _lines_of(db, request.id)
    assert [(line.product_id, line.product_set_id) for line in lines] == [(host.id, None)]


# =========================================================================== AC-13 regression


def test_ac13_ala_carte_line_beside_its_combo_line_prints_the_products_own_price_and_list(db):
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


# =========================================================================== AC-15 combo delete


def test_ac15_deleting_a_combo_beside_an_ala_carte_line_leaves_both_ala_carte(db):
    from app.services.product_combo_service import ProductComboService

    host, combo = _host_with_one_combo(db)
    request = seed.submit(
        db,
        [
            seed.line_dict(host, None, quantity=2, remarks="L1"),
            seed.line_dict(host, combo, quantity=3, remarks="L2"),
        ],
    )
    ids = {remark: line.id for remark, line in _by_remark(db, request.id).items()}
    db.commit()

    ProductComboService(db).delete(combo.id)

    lines = _by_remark(db, request.id)
    assert {remark: line.id for remark, line in lines.items()} == ids, "no line merged or dropped"
    assert [(lines[r].combo_id, lines[r].quantity) for r in ("L1", "L2")] == [(None, 2), (None, 3)]


# =========================================================================== AC-16 snapshot + diff


def test_ac16_the_revision_snapshot_carries_item_code_and_package(db):
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


def test_ac16_the_snapshot_of_a_one_line_request_names_its_package(db):
    """Same as above without a repeated product, so it is red only for the missing keys."""
    from app.services.portal_revision_service import _serialize_price_tag_lines

    host, combo = _host_with_one_combo(db, name=unique_code("ZZT Pkg One"))
    other = seed.product(db, "P-ALA-2")
    request = seed.submit(db, [seed.line_dict(host, combo), seed.line_dict(other, None)])
    db.flush()

    lines = _serialize_price_tag_lines(db, request)
    assert [(line["item_code"], line["package"]) for line in lines] == [
        (host.product_code, combo.name),
        (other.product_code, ALA_CARTE),
    ]


def test_ac16_a_package_change_is_a_named_line_change():
    from app.services.portal_revision_service import _diff_lines

    before = [{"item_code": "P-ALA-1", "quantity": 1, "package": "ZZT Pkg A"}]
    after = [{"item_code": "P-ALA-1", "quantity": 1, "package": ALA_CARTE}]

    changes = _diff_lines(before, after)

    assert changes == [
        {
            "field": "products[0].package",
            "label": "Product line 1 package",
            "from": "ZZT Pkg A",
            "to": ALA_CARTE,
        }
    ]
