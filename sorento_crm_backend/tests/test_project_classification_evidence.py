"""The Proof button's evidence: `GET .../fulfilment-planning/classification` (PLAN 3.3a
follow-up, 19 August 2026 - the captain: "don't give me jargon like abc classification,
just tell me hot selling or cold selling, at project or retail, with some button for me to
view detail as a proof").

Rank / of / cumulative share are computed live over the SAME rows the board's own
hot-selling predicate reads (`ProjectSupplyService._classification`): a non-null quantity
for the class, at an active, `counts_as_available` warehouse. The letter is read straight
off `scm.item_classification`, never recomputed, so a "hot" verdict here can never disagree
with the one the board already acted on.

Postgres, blank scratch schema, every FK target seeded here (PRINCIPLES).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.inventory import Warehouse
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.scm import ItemClassification
from app.services.error_handler import AppException
from app.services.project_classification_evidence import classification_evidence

from ._pg_fixture import blank_session

MARKER = "zzt-classev"


def _uid() -> str:
    return str(uuid.uuid4())


def _product(db, code: str) -> Product:
    uom = UnitOfMeasure(id=_uid(), uom_code=f"ZZT{_uid()[:6]}", uom_name="Unit")
    category = ProductCategory(
        id=_uid(), category_code=f"ZZT-{_uid()[:8]}", category_name=f"{MARKER} cat"
    )
    db.add_all([uom, category])
    db.flush()
    row = Product(
        id=_uid(),
        product_code=code,
        product_name=f"{MARKER} {code}",
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=Decimal("100.00"),
    )
    db.add(row)
    db.flush()
    return row


def _warehouse(db, code: str, *, active: bool = True, available: bool = True) -> Warehouse:
    row = Warehouse(
        id=_uid(),
        warehouse_code=code,
        warehouse_name=code,
        is_active=active,
        counts_as_available=available,
    )
    db.add(row)
    db.flush()
    return row


def _row(db, product, warehouse, *, retail_qty=None, retail_letter=None,
         project_qty=None, project_letter=None, computed_at=None):
    db.add(
        ItemClassification(
            id=_uid(),
            product_id=product.id,
            warehouse_id=warehouse.id,
            annual_qty_retail=retail_qty,
            abc_class_retail=retail_letter,
            annual_qty_project=project_qty,
            abc_class_project=project_letter,
            computed_at=computed_at or datetime(2026, 8, 1, 3, 0, 0),
        )
    )
    db.flush()


def _by_class(evidence, demand_class):
    return next(c for c in evidence["classes"] if c["demand_class"] == demand_class)


def test_the_hot_product_is_ranked_first_with_the_share_and_the_letter_it_earned():
    with blank_session() as db:
        warehouse = _warehouse(db, f"ZZT{_uid()[:6]}"[:20])
        hot = _product(db, f"ZZT-{_uid()[:6]}")
        cold = _product(db, f"ZZT-{_uid()[:6]}")
        _row(db, hot, warehouse, retail_qty=100, retail_letter="A",
             computed_at=datetime(2026, 8, 15, 3, 0, 0))
        _row(db, cold, warehouse, retail_qty=50, retail_letter="B")

        evidence = classification_evidence(db, str(hot.id))

        assert evidence["product_id"] == str(hot.id)
        assert evidence["item_code"] == hot.product_code
        assert evidence["window_days"] == 365
        assert evidence["hot_cut_pct"] == 80
        assert evidence["computed_at"] == datetime(2026, 8, 15, 3, 0, 0)

        retail = _by_class(evidence, "retail")
        assert retail["label"] == "Dealer"
        assert retail["verdict"] == "hot"
        assert retail["locations"] == [
            {
                "warehouse_code": warehouse.warehouse_code,
                "qty_delivered": "100",
                "rank": 1,
                "of": 2,
                # This row's OWN weight (100 of the 150 total), not the running "everyone at
                # or above me" figure - the two read the same on a rank-1 row of a THIN
                # ranking, which is exactly the case the captain misread as impressive.
                "share_pct": pytest.approx(66.67, abs=0.01),
                "cumulative_share_pct": pytest.approx(66.7, abs=0.1),
                "letter": "A",
                "hot": True,
            }
        ]

        project = _by_class(evidence, "project")
        assert project["label"] == "Project"
        assert project["verdict"] == "unclassified"
        assert project["locations"] == []


def test_a_real_non_a_letter_is_cold_not_hot():
    with blank_session() as db:
        warehouse = _warehouse(db, f"ZZT{_uid()[:6]}"[:20])
        hot = _product(db, f"ZZT-{_uid()[:6]}")
        cold = _product(db, f"ZZT-{_uid()[:6]}")
        _row(db, hot, warehouse, retail_qty=100, retail_letter="A")
        _row(db, cold, warehouse, retail_qty=50, retail_letter="B")

        evidence = classification_evidence(db, str(cold.id))

        retail = _by_class(evidence, "retail")
        assert retail["verdict"] == "cold"
        assert retail["locations"] == [
            {
                "warehouse_code": warehouse.warehouse_code,
                "qty_delivered": "50",
                "rank": 2,
                "of": 2,
                "share_pct": pytest.approx(33.33, abs=0.01),
                "cumulative_share_pct": 100.0,
                "letter": "B",
                "hot": False,
            }
        ]
        # "Ranked above it" (the popover's own subtraction): 100.0 - 33.33 -> the row ranked
        # first held the rest.
        assert retail["locations"][0]["cumulative_share_pct"] - retail["locations"][0][
            "share_pct"
        ] == pytest.approx(66.67, abs=0.01)


def test_a_product_with_no_row_at_all_is_unclassified_on_both_classes():
    with blank_session() as db:
        product = _product(db, f"ZZT-{_uid()[:6]}")

        evidence = classification_evidence(db, str(product.id))

        for demand_class in ("retail", "project"):
            cls = _by_class(evidence, demand_class)
            assert cls["verdict"] == "unclassified"
            assert cls["locations"] == []
        assert evidence["computed_at"] is None


def test_an_inactive_or_unavailable_warehouse_never_counts_toward_rank_or_verdict():
    """The same filter the board's own hot-selling predicate reads
    (`ProjectSupplyService._classification`): a letter at a location nobody can plan
    against is not evidence of anything."""
    with blank_session() as db:
        live = _warehouse(db, f"ZZT{_uid()[:6]}"[:20])
        inactive = _warehouse(db, f"ZZT{_uid()[:6]}"[:20], active=False)
        unavailable = _warehouse(db, f"ZZT{_uid()[:6]}"[:20], available=False)
        product = _product(db, f"ZZT-{_uid()[:6]}")
        _row(db, product, live, retail_qty=10, retail_letter="B")
        _row(db, product, inactive, retail_qty=999, retail_letter="A")
        _row(db, product, unavailable, retail_qty=999, retail_letter="A")

        evidence = classification_evidence(db, str(product.id))

        retail = _by_class(evidence, "retail")
        assert retail["verdict"] == "cold", "the two A rows sit at locations that don't count"
        assert [loc["warehouse_code"] for loc in retail["locations"]] == [live.warehouse_code]
        assert retail["locations"][0]["of"] == 1
        assert retail["locations"][0]["share_pct"] == 100.0, "the only counted row is the whole"


def test_an_unknown_product_is_a_404_not_an_empty_answer():
    with blank_session() as db:
        with pytest.raises(AppException) as exc_info:
            classification_evidence(db, _uid())
        assert exc_info.value.status_code == 404
