"""PS-QUOTE-MATRIX through the services and the routes.

Written BEFORE the implementation (Phase 2, test-first). Contract:
``documentation/plans/project-sales/PLAN-ps-quote-matrix-02nov.md`` ("Contract (Phase 2 ...)").
Postgres only, via ``blank_session``; every test seeds its own chain (marker ``zzt-ppq`` comes from
the proposal helpers this file borrows, which seed a company-less world on an empty database).

The columns route is mounted under the project-sales prefix like every other quotation-version
route: ``PUT /api/v1/project-sales/quotation-versions/{id}/columns``.

This module also exports ``grid_world`` / ``set_grid`` for ``test_quote_matrix_render.py`` and
``test_quote_feedback.py``.
"""
from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from ._pg_fixture import blank_session
from .test_project_po_document_save import _client, _restore
from .test_project_proposal_quotation import (
    MARKER,
    _issue,
    _price,
    _setup,
    _win,
)

BASE = "/api/v1/project-sales"

COLUMNS = [
    {
        "key": "ta",
        "label": "TYPE A",
        "cols": [
            {"key": "ta_bh", "label": "1 BH"},
            {"key": "ta_kit", "label": "KITCHEN"},
        ],
    },
    {
        "key": "tb",
        "label": "TYPE B",
        "cols": [
            {"key": "tb_bh", "label": "2 BH"},
            {"key": "tb_kit", "label": "KITCHEN"},
        ],
    },
    {"key": "tank", "label": "BREAK TANK", "cols": []},
]


# ------------------------------------------------------------------ shared helpers


def set_grid(db, version, columns, cells_by_line):
    """Write columns and cells straight onto the rows (no route), for render / feedback worlds.

    Fails loudly and early when the columns do not exist yet, so a red run says why.
    """
    from app.models.projects import ProjectQuotationLine, ProjectQuotationVersion

    assert "matrix_columns" in ProjectQuotationVersion.__table__.columns, "no matrix_columns column"
    assert "qty_cells" in ProjectQuotationLine.__table__.columns, "no qty_cells column"
    from app.services import project_quotation_service as quotes

    version.matrix_columns = columns
    for line, cells in cells_by_line:
        line.qty_cells = cells
        line.quantity = sum((Decimal(v) for v in cells.values()), Decimal("0"))
        line.line_total = (Decimal(line.unit_price) * Decimal(line.quantity)).quantize(
            Decimal("0.01")
        )
    version.total_amount = sum(
        (Decimal(line.line_total) for line, _ in cells_by_line if not line.is_rate_only),
        Decimal("0"),
    )
    db.flush()
    quotes.recalculate_total(db, version)
    db.flush()


def grid_world(db):
    """A proposal with TWO scopes: ``UNIT`` (a grid) and ``GUARD`` (plain), signed and issued.

    UNIT lines: floor trap at 45.00 (E1 shape, cells ta_bh 120 + ta_kit 120, tb_bh 500 + tb_kit 250)
    and a sink at 100.00 (ta_bh 2). GUARD: one plain line, 5 x 80.00.
    Returns a namespace; nothing is committed.
    """
    from app.services import project_quotation_document_service as qdocs
    from app.services import project_quotation_service as quotes

    company_id, owner, product, project, document, unit_scope = _setup(db)
    guard_scope = qdocs.add_scope(
        db, document=document, scope_label=f"{MARKER} GUARD HOUSE", actor_user_id=owner
    )
    trap = _price(db, unit_scope, product, owner, "45.00", 1)
    sink = _price(db, unit_scope, product, owner, "100.00", 1)
    plain = _price(db, guard_scope, product, owner, "80.00", 5)
    unit_version = quotes.current_version(db, unit_scope.id)
    set_grid(
        db,
        unit_version,
        COLUMNS,
        [
            (trap, {"ta_bh": "120.00", "ta_kit": "120.00", "tb_bh": "500.00", "tb_kit": "250.00"}),
            (sink, {"ta_bh": "2.00"}),
        ],
    )
    record = _issue(db, document, owner)
    db.flush()
    return SimpleNamespace(
        company_id=company_id,
        owner=owner,
        product=product,
        project=project,
        document=document,
        unit_scope=unit_scope,
        guard_scope=guard_scope,
        unit_version=unit_version,
        guard_version=quotes.current_version(db, guard_scope.id),
        trap=trap,
        sink=sink,
        plain=plain,
        record=record,
    )


@pytest.fixture()
def env():
    """A draft proposal scope with ONE priced line (qty 7 x 100.00), and a staff client."""
    from app.models.base import company_scope
    from app.services import project_quotation_service as quotes

    with blank_session() as db:
        company_id, owner, product, project, document, scope = _setup(db)
        line = _price(db, scope, product, owner, "100.00", 7)
        version = quotes.current_version(db, scope.id)
        db.commit()
        client, originals = _client(db, owner)
        try:
            with company_scope(db, frozenset({company_id})):
                yield SimpleNamespace(
                    client=client,
                    db=db,
                    owner=owner,
                    product=product,
                    project=project,
                    document=document,
                    scope=scope,
                    line=line,
                    version=version,
                )
        finally:
            _restore(originals)


def _cols_url(version_id):
    return f"{BASE}/quotation-versions/{version_id}/columns"


def _lines_url(version_id):
    return f"{BASE}/quotation-versions/{version_id}/lines"


def _put_columns(env, columns, version=None):
    return env.client.put(_cols_url((version or env.version).id), json={"columns": columns})


def _line_body(env, **over):
    body = {"product_id": env.product.id, "unit_price": "10.00"}
    body.update(over)
    return body


def _db_line(env, line_id):
    from app.models.projects import ProjectQuotationLine

    env.db.expire_all()
    return env.db.query(ProjectQuotationLine).filter(ProjectQuotationLine.id == line_id).one()


# ------------------------------------------------------------------ PUT columns: transitions


def test_columns_from_none_to_some_moves_the_quantity_into_the_first_leaf(env):
    response = _put_columns(env, COLUMNS)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["version"]["matrix_columns"] == COLUMNS
    (line,) = body["lines"]
    assert line["id"] == env.line.id
    assert line["qty_cells"] == {"ta_bh": "7.00"}
    assert Decimal(str(line["quantity"])) == Decimal("7")
    assert Decimal(str(line["line_total"])) == Decimal("700.00")
    assert Decimal(str(body["version"]["total_amount"])) == Decimal("700.00")

    stored = _db_line(env, env.line.id)
    assert stored.qty_cells == {"ta_bh": "7.00"}


def test_columns_from_some_to_none_keeps_the_sum_and_nulls_the_cells(env):
    assert _put_columns(env, COLUMNS).status_code == 200
    env.client.put(
        f"{_lines_url(env.version.id)}/{env.line.id}",
        json={"qty_cells": {"ta_bh": 3, "tb_kit": "4.5"}},
    )
    response = _put_columns(env, [])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["version"]["matrix_columns"] == []
    (line,) = body["lines"]
    assert line["qty_cells"] == {}
    assert Decimal(str(line["quantity"])) == Decimal("7.50")
    assert Decimal(str(body["version"]["total_amount"])) == Decimal("750.00")
    assert _db_line(env, env.line.id).qty_cells is None


def test_removing_a_col_drops_its_cells_and_resums_quantity_and_totals(env):
    assert _put_columns(env, COLUMNS).status_code == 200
    updated = env.client.put(
        f"{_lines_url(env.version.id)}/{env.line.id}",
        json={"qty_cells": {"ta_bh": 10, "ta_kit": 5, "tb_kit": 2}},
    )
    assert updated.status_code == 200, updated.text

    without_ta_kit = [
        {**COLUMNS[0], "cols": [COLUMNS[0]["cols"][0]]},
        COLUMNS[1],
        COLUMNS[2],
    ]
    response = _put_columns(env, without_ta_kit)
    assert response.status_code == 200, response.text
    (line,) = response.json()["lines"]
    assert line["qty_cells"] == {"ta_bh": "10.00", "tb_kit": "2.00"}
    assert Decimal(str(line["quantity"])) == Decimal("12")
    assert Decimal(str(line["line_total"])) == Decimal("1200.00")
    assert Decimal(str(response.json()["version"]["total_amount"])) == Decimal("1200.00")


def test_columns_edit_that_keeps_every_leaf_changes_no_quantity(env):
    assert _put_columns(env, COLUMNS).status_code == 200
    renamed = [{**COLUMNS[0], "label": "TYPE A - 1 BH"}, COLUMNS[1], COLUMNS[2]]
    response = _put_columns(env, renamed)
    assert response.status_code == 200, response.text
    assert response.json()["version"]["matrix_columns"][0]["label"] == "TYPE A - 1 BH"
    (line,) = response.json()["lines"]
    assert line["qty_cells"] == {"ta_bh": "7.00"}


def test_invalid_columns_are_422_with_the_columns_code_and_change_nothing(env):
    duplicate = [{"key": "x", "label": "X", "cols": [{"key": "x", "label": "Y"}]}]
    response = _put_columns(env, duplicate)
    assert response.status_code == 422, response.text
    assert response.json()["code"] == "quotation_columns_invalid"
    assert _db_line(env, env.line.id).qty_cells is None

    blank = _put_columns(env, [{"key": "x", "label": "  ", "cols": []}])
    assert blank.status_code == 422
    assert blank.json()["code"] == "quotation_columns_invalid"


def test_columns_on_an_issued_version_are_refused_like_line_writes(env):
    from app.services import project_quotation_document_service as qdocs  # noqa: F401

    _issue(env.db, env.document, env.owner)
    env.db.commit()
    response = _put_columns(env, COLUMNS)
    assert response.status_code == 422, response.text
    assert response.json()["code"] == "quotation_version_issued"
    refused_line = env.client.post(_lines_url(env.version.id), json=_line_body(env))
    assert refused_line.json()["code"] == response.json()["code"]


def test_columns_on_a_superseded_version_are_refused(env):
    from app.services import project_quotation_service as quotes

    quotes.revise(env.db, quotation=env.scope, actor_user_id=env.owner)
    env.db.commit()
    response = _put_columns(env, COLUMNS)
    assert response.status_code == 422, response.text
    assert response.json()["code"] == "quotation_version_frozen"


def test_columns_on_an_unknown_version_are_404(env):
    import uuid

    response = env.client.put(_cols_url(str(uuid.uuid4())), json={"columns": COLUMNS})
    assert response.status_code == 404, response.text
    assert response.json()["code"] == "quotation_version_not_found"


# ------------------------------------------------------------------ cells on a line


def test_a_new_line_with_cells_gets_quantity_as_their_sum_and_ignores_the_payload_quantity(env):
    assert _put_columns(env, COLUMNS).status_code == 200
    response = env.client.post(
        _lines_url(env.version.id),
        json=_line_body(
            env, quantity="99", qty_cells={"ta_bh": 120, "tb_kit": "250.5", "tank": 0, "ta_kit": ""}
        ),
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["qty_cells"] == {"ta_bh": "120.00", "tb_kit": "250.50"}
    assert Decimal(str(body["quantity"])) == Decimal("370.50")
    assert Decimal(str(body["line_total"])) == Decimal("3705.00")


def test_a_grid_line_with_no_cells_has_quantity_zero_even_if_one_is_sent(env):
    assert _put_columns(env, COLUMNS).status_code == 200
    response = env.client.post(_lines_url(env.version.id), json=_line_body(env, quantity="5"))
    assert response.status_code == 201, response.text
    assert Decimal(str(response.json()["quantity"])) == Decimal("0")
    assert response.json()["qty_cells"] == {}


def test_an_update_re_sums_and_a_payload_quantity_alone_changes_nothing(env):
    assert _put_columns(env, COLUMNS).status_code == 200
    url = f"{_lines_url(env.version.id)}/{env.line.id}"
    first = env.client.put(url, json={"qty_cells": {"ta_bh": 4, "tb_bh": 6}})
    assert first.status_code == 200, first.text
    assert Decimal(str(first.json()["quantity"])) == Decimal("10")
    second = env.client.put(url, json={"quantity": "500"})
    assert second.status_code == 200, second.text
    assert Decimal(str(second.json()["quantity"])) == Decimal("10")
    assert second.json()["qty_cells"] == {"ta_bh": "4.00", "tb_bh": "6.00"}
    cleared = env.client.put(url, json={"qty_cells": {}})
    assert cleared.status_code == 200, cleared.text
    assert Decimal(str(cleared.json()["quantity"])) == Decimal("0")
    assert cleared.json()["qty_cells"] == {}
    assert _db_line(env, env.line.id).qty_cells is None


@pytest.mark.parametrize(
    "cells",
    [
        {"ghost": 1},
        {"ta": 1},
        {"ta_bh": -1},
        {"ta_bh": "10000000.00"},
        {"ta_bh": "many"},
    ],
)
def test_a_bad_cell_is_422_with_the_cells_code_and_nothing_is_stored(env, cells):
    assert _put_columns(env, COLUMNS).status_code == 200
    created = env.client.post(_lines_url(env.version.id), json=_line_body(env, qty_cells=cells))
    assert created.status_code == 422, created.text
    assert created.json()["code"] == "quotation_cells_invalid"
    updated = env.client.put(
        f"{_lines_url(env.version.id)}/{env.line.id}", json={"qty_cells": cells}
    )
    assert updated.status_code == 422, updated.text
    assert updated.json()["code"] == "quotation_cells_invalid"
    listed = env.client.get(_lines_url(env.version.id)).json()["data"]
    assert [row["id"] for row in listed] == [env.line.id]


def test_the_largest_allowed_cell_is_accepted(env):
    assert _put_columns(env, COLUMNS).status_code == 200
    response = env.client.put(
        f"{_lines_url(env.version.id)}/{env.line.id}", json={"qty_cells": {"ta_bh": "9999999.99"}}
    )
    assert response.status_code == 200, response.text
    assert response.json()["qty_cells"] == {"ta_bh": "9999999.99"}


def test_cells_on_a_version_without_columns_are_422_unless_empty_or_null(env):
    url = _lines_url(env.version.id)
    refused = env.client.post(url, json=_line_body(env, qty_cells={"ta_bh": 1}))
    assert refused.status_code == 422, refused.text
    assert refused.json()["code"] == "quotation_cells_invalid"
    refused_update = env.client.put(
        f"{url}/{env.line.id}", json={"qty_cells": {"ta_bh": 1}}
    )
    assert refused_update.status_code == 422
    assert refused_update.json()["code"] == "quotation_cells_invalid"

    for empty in ({}, None):
        ok = env.client.post(url, json=_line_body(env, quantity="3", qty_cells=empty))
        assert ok.status_code == 201, ok.text
        assert Decimal(str(ok.json()["quantity"])) == Decimal("3")
        assert ok.json()["qty_cells"] == {}


def test_bulk_save_writes_cells_and_sums_them_and_a_bad_cell_rolls_everything_back(env):
    assert _put_columns(env, COLUMNS).status_code == 200
    url = _lines_url(env.version.id)
    good = env.client.put(
        url,
        json={
            "lines": [
                {
                    "id": env.line.id,
                    "product_id": env.product.id,
                    "unit_price": "100.00",
                    "qty_cells": {"ta_bh": 1, "ta_kit": 2},
                },
                {
                    "product_id": env.product.id,
                    "unit_price": "50.00",
                    "quantity": "77",
                    "qty_cells": {"tb_bh": "4"},
                },
            ]
        },
    )
    assert good.status_code == 200, good.text
    rows = good.json()["data"]
    assert [r["qty_cells"] for r in rows] == [
        {"ta_bh": "1.00", "ta_kit": "2.00"},
        {"tb_bh": "4.00"},
    ]
    assert [Decimal(str(r["quantity"])) for r in rows] == [Decimal("3"), Decimal("4")]

    bad = env.client.put(
        url,
        json={
            "lines": [
                {
                    "id": env.line.id,
                    "product_id": env.product.id,
                    "unit_price": "100.00",
                    "qty_cells": {"ta_bh": 9},
                },
                {"product_id": env.product.id, "unit_price": "1.00", "qty_cells": {"ghost": 1}},
            ]
        },
    )
    assert bad.status_code == 422, bad.text
    assert bad.json()["code"] == "quotation_cells_invalid"
    again = env.client.get(url).json()["data"]
    assert [r["qty_cells"] for r in again] == [
        {"ta_bh": "1.00", "ta_kit": "2.00"},
        {"tb_bh": "4.00"},
    ]


def test_the_version_total_follows_the_cells(env):
    assert _put_columns(env, COLUMNS).status_code == 200
    env.client.put(
        f"{_lines_url(env.version.id)}/{env.line.id}", json={"qty_cells": {"ta_bh": 3}}
    )
    created = env.client.post(
        _lines_url(env.version.id), json=_line_body(env, qty_cells={"tb_bh": 2})
    )
    assert created.status_code == 201, created.text
    versions = env.client.get(f"{BASE}/quotations/{env.scope.id}/versions").json()["data"]
    (current,) = [v for v in versions if v["id"] == env.version.id]
    assert Decimal(str(current["total_amount"])) == Decimal("320.00")
    assert current["matrix_columns"] == COLUMNS


# ------------------------------------------------------------------ plain scope regression


def test_a_scope_without_columns_behaves_exactly_as_before(env):
    url = _lines_url(env.version.id)
    listed = env.client.get(url).json()["data"]
    assert listed[0]["qty_cells"] == {}
    assert Decimal(str(listed[0]["quantity"])) == Decimal("7")

    created = env.client.post(url, json=_line_body(env, quantity="3"))
    assert created.status_code == 201, created.text
    assert Decimal(str(created.json()["quantity"])) == Decimal("3")
    assert Decimal(str(created.json()["line_total"])) == Decimal("30.00")

    updated = env.client.put(f"{url}/{env.line.id}", json={"quantity": "8"})
    assert updated.status_code == 200, updated.text
    assert Decimal(str(updated.json()["quantity"])) == Decimal("8")
    assert Decimal(str(updated.json()["line_total"])) == Decimal("800.00")

    versions = env.client.get(f"{BASE}/quotations/{env.scope.id}/versions").json()["data"]
    assert versions[0]["matrix_columns"] == []
    assert Decimal(str(versions[0]["total_amount"])) == Decimal("830.00")


# ------------------------------------------------------------------ revise + make_quotation


def test_revise_copies_the_columns_and_the_cells_and_leaves_the_issued_version_alone():
    from app.models.projects import ProjectQuotationLine
    from app.services import project_quotation_service as quotes

    with blank_session() as db:
        w = grid_world(db)
        revised = quotes.revise(db, quotation=w.unit_scope, actor_user_id=w.owner)
        db.flush()
        assert revised.matrix_columns == COLUMNS
        copies = (
            db.query(ProjectQuotationLine)
            .filter(ProjectQuotationLine.version_id == revised.id)
            .order_by(ProjectQuotationLine.sort_order)
            .all()
        )
        assert [c.qty_cells for c in copies] == [
            {"ta_bh": "120.00", "ta_kit": "120.00", "tb_bh": "500.00", "tb_kit": "250.00"},
            {"ta_bh": "2.00"},
        ]
        assert [Decimal(c.quantity) for c in copies] == [Decimal("990"), Decimal("2")]
        assert Decimal(revised.total_amount) == Decimal("990") * Decimal("45.00") + Decimal("200.00")

        # Editing the draft's columns never touches the frozen version.
        copies[0].qty_cells = {"ta_bh": "1.00"}
        revised.matrix_columns = []
        db.flush()
        db.expire_all()
        original = (
            db.query(ProjectQuotationLine)
            .filter(ProjectQuotationLine.id == w.trap.id)
            .one()
        )
        assert original.qty_cells["tb_kit"] == "250.00"
        assert w.unit_version.matrix_columns == COLUMNS


def test_make_quotation_copies_the_columns_and_the_cells():
    from app.models.projects import ProjectQuotationLine, ProjectQuotationVersion
    from app.services import project_quotation_document_service as qdocs
    from app.services import project_quotation_service as quotes

    with blank_session() as db:
        w = grid_world(db)
        _win(db, w.unit_scope)
        _win(db, w.guard_scope)
        made = qdocs.make_quotation(
            db, proposal=w.document, issue_id=w.record.id, actor_user_id=w.owner
        )
        db.flush()
        scopes = qdocs.list_scopes(db, made)
        grids = []
        plains = []
        for scope in scopes:
            version = quotes.current_version(db, scope.id)
            (grids if version.matrix_columns else plains).append(version)
        assert len(grids) == 1 and len(plains) == 1
        assert grids[0].matrix_columns == COLUMNS
        assert plains[0].matrix_columns in (None, [])
        cells = [
            line.qty_cells
            for line in db.query(ProjectQuotationLine)
            .filter(ProjectQuotationLine.version_id == grids[0].id)
            .order_by(ProjectQuotationLine.sort_order)
            .all()
        ]
        assert cells == [
            {"ta_bh": "120.00", "ta_kit": "120.00", "tb_bh": "500.00", "tb_kit": "250.00"},
            {"ta_bh": "2.00"},
        ]
        assert db.query(ProjectQuotationVersion).filter(
            ProjectQuotationVersion.id == grids[0].id
        ).one().matrix_columns == COLUMNS
