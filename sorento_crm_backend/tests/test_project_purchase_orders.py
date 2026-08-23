"""S4 Project purchase orders (UAC Group F, AC-F8 to AC-F10).

Three rules carry the design:

- **Mismatches are FLAGGED, never blocked** (AC-F9). A PO is a fact that arrived; a
  system that refuses to record it because a model code differs just means the PO gets
  tracked in somebody's spreadsheet instead.
- **The comparison is against the BOUND version**, which is the price the contractor was
  actually last shown. Comparing against v1 after three revisions would flag every
  legitimate PO, and an alert that always fires is an alert nobody reads.
- **Drift from v1 is a separate, visible number** (AC-F9a), because total erosion across
  a negotiation is what management actually wants to see.

Plus AC-F10: the FIRST PO moves the project's status to PO Received, through the engine's
legality check rather than around it.
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.projects import ProjectParty
from app.models.user import User
from app.services import project_seed_service
from app.services.error_handler import AppException

from ._pg_fixture import blank_session

MARKER = "zzt-po"


def _uid() -> str:
    return str(uuid.uuid4())


def _sorento(db) -> str:
    return db.execute(text("select id from companies where code = 'SRT'")).scalar()


def _user(db, name: str) -> str:
    user_id = _uid()
    db.add(User(id=user_id, email=f"{user_id}@zzt.test", name=name))
    db.flush()
    return user_id


def _uom(db) -> str:
    row = UnitOfMeasure(id=_uid(), uom_code=f"ZZT{_uid()[:4]}", uom_name="Piece")
    db.add(row)
    db.flush()
    return row.id


def _product(db, uom_id: str, list_price: str, code=None) -> Product:
    category = ProductCategory(
        id=_uid(), category_code=f"ZZT-{_uid()[:8]}", category_name=f"{MARKER} cat"
    )
    db.add(category)
    db.flush()
    row = Product(
        id=_uid(),
        product_code=code or f"ZZT-{_uid()[:8]}",
        product_name=f"{MARKER} Basin",
        category_id=category.id,
        base_uom_id=uom_id,
        list_price=Decimal(list_price),
    )
    db.add(row)
    db.flush()
    return row


def _party(db, company_id: str, party_type: str) -> ProjectParty:
    row = ProjectParty(
        id=_uid(),
        company_id=company_id,
        party_type=party_type,
        name=f"{MARKER} {party_type} {_uid()[:6]}",
    )
    db.add(row)
    db.flush()
    return row


def _project(db, company_id: str, owner: str):
    from app.services.project_service import register_project

    return register_project(
        db,
        company_id=company_id,
        actor_user_id=owner,
        developer_party_id=None,
        title=f"{MARKER} Tower {_uid()[:12]}",
    )


def _status_id(db, key: str) -> str:
    # str(), not the raw scalar: psycopg2 hands back a uuid.UUID and the column stores a
    # string, so a bare comparison fails on two spellings of the same id.
    return str(
        db.execute(
            text(
                "select id from statuses where entity_type = 'project' and key = :k "
                "and scope_id is null"
            ),
            {"k": key},
        ).scalar()
    )


def _quoted_project(db, company_id: str, owner: str, *, unit_price="1000.00", quantity=10):
    """A project with one quotation version holding one priced line."""
    from app.services import project_quotation_service as quotes

    project = _project(db, company_id, owner)
    uom = _uom(db)
    product = _product(db, uom, "1200.00")
    quotation = quotes.create_quotation(
        db, project=project, actor_user_id=owner, payload={"scope_label": "House Units"}
    )
    version = quotes.current_version(db, quotation.id)
    quotes.upsert_line(
        db,
        version=version,
        actor_user_id=owner,
        payload={
            "product_id": product.id,
            "unit_price": Decimal(unit_price),
            "quantity": quantity,
        },
    )
    return project, quotation, version, product


@pytest.fixture()
def seeded():
    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        owner = _user(db, f"{MARKER} Ali")
        yield db, company_id, owner


# ------------------------------------------------------------------- recording


def test_a_po_records_its_source_issuer_and_bound_version(seeded):
    from app.services import project_po_service as pos

    db, company_id, owner = seeded
    project, _quotation, version, _product = _quoted_project(db, company_id, owner)
    contractor = _party(db, company_id, "main_contractor")

    po = pos.create_po(
        db,
        project=project,
        actor_user_id=owner,
        payload={
            "quotation_version_id": version.id,
            "po_source": "contractor_direct",
            "issuing_party_id": contractor.id,
            "po_number": "PO-9001",
            "po_date": date(2026, 7, 22),
            "po_amount": Decimal("9500.00"),
        },
    )

    assert po.po_number == "PO-9001"
    assert po.po_source == "contractor_direct"
    assert po.issuing_party_id == contractor.id
    assert po.quotation_version_id == version.id


def test_an_unknown_source_is_refused(seeded):
    from app.services import project_po_service as pos

    db, company_id, owner = seeded
    project, _q, version, _p = _quoted_project(db, company_id, owner)

    with pytest.raises(AppException) as excinfo:
        pos.create_po(
            db,
            project=project,
            actor_user_id=owner,
            payload={
                "quotation_version_id": version.id,
                "po_source": "walked_in",
                "po_number": "PO-9002",
            },
        )
    assert excinfo.value.status_code == 422


def test_a_po_may_be_recorded_against_a_superseded_version(seeded):
    """Unlike a sample (AC-F2). The contractor buys off the document they were given,
    and that is frequently not the newest one -- refusing it would make the PO
    unrecordable through no fault of the person recording it."""
    from app.services import project_po_service as pos
    from app.services import project_quotation_service as quotes

    db, company_id, owner = seeded
    project, quotation, version, _p = _quoted_project(db, company_id, owner)
    quotes.revise(db, quotation=quotation, actor_user_id=owner)

    po = pos.create_po(
        db,
        project=project,
        actor_user_id=owner,
        payload={
            "quotation_version_id": version.id,
            "po_source": "contractor_direct",
            "po_number": "PO-9003",
        },
    )
    assert po.quotation_version_id == version.id


# --------------------------------------------------------------- line matching


def test_a_line_matching_the_bound_version_is_flagged_clean(seeded):
    from app.services import project_po_service as pos

    db, company_id, owner = seeded
    project, _q, version, product = _quoted_project(db, company_id, owner, unit_price="900.00")
    po = pos.create_po(
        db,
        project=project,
        actor_user_id=owner,
        payload={
            "quotation_version_id": version.id,
            "po_source": "contractor_direct",
            "po_number": "PO-9004",
        },
    )

    line = pos.upsert_line(
        db,
        po=po,
        payload={"product_id": product.id, "unit_price": Decimal("900.00"), "quantity": 10},
    )

    assert line.model_mismatch is False
    assert line.price_mismatch is False


def test_a_different_unit_price_is_flagged_not_blocked(seeded):
    """AC-F9. The PO exists; our job is to make the difference visible."""
    from app.services import project_po_service as pos

    db, company_id, owner = seeded
    project, _q, version, product = _quoted_project(db, company_id, owner, unit_price="900.00")
    po = pos.create_po(
        db,
        project=project,
        actor_user_id=owner,
        payload={
            "quotation_version_id": version.id,
            "po_source": "contractor_direct",
            "po_number": "PO-9005",
        },
    )

    line = pos.upsert_line(
        db,
        po=po,
        payload={"product_id": product.id, "unit_price": Decimal("820.00"), "quantity": 10},
    )

    assert line.price_mismatch is True
    assert line.model_mismatch is False
    assert line.quoted_unit_price == Decimal("900.00")


def test_a_product_not_on_the_bound_version_is_a_model_mismatch(seeded):
    from app.services import project_po_service as pos

    db, company_id, owner = seeded
    project, _q, version, _quoted_product = _quoted_project(db, company_id, owner)
    other = _product(db, _uom(db), "500.00", code="ZZT-SUBSTITUTE")
    po = pos.create_po(
        db,
        project=project,
        actor_user_id=owner,
        payload={
            "quotation_version_id": version.id,
            "po_source": "contractor_direct",
            "po_number": "PO-9006",
        },
    )

    line = pos.upsert_line(
        db,
        po=po,
        payload={"product_id": other.id, "unit_price": Decimal("500.00"), "quantity": 4},
    )

    assert line.model_mismatch is True
    # Nothing to compare a price against, so the price is not ALSO flagged: two alerts
    # for one problem is how people learn to ignore both.
    assert line.price_mismatch is False
    assert line.quoted_unit_price is None


def test_a_different_quantity_is_never_flagged(seeded):
    """AC-F9: quantity may differ freely. Contractors order in stages."""
    from app.services import project_po_service as pos

    db, company_id, owner = seeded
    project, _q, version, product = _quoted_project(
        db, company_id, owner, unit_price="900.00", quantity=10
    )
    po = pos.create_po(
        db,
        project=project,
        actor_user_id=owner,
        payload={
            "quotation_version_id": version.id,
            "po_source": "contractor_direct",
            "po_number": "PO-9007",
        },
    )

    line = pos.upsert_line(
        db,
        po=po,
        payload={"product_id": product.id, "unit_price": Decimal("900.00"), "quantity": 3},
    )

    assert line.model_mismatch is False
    assert line.price_mismatch is False


def test_an_off_catalog_po_line_is_a_model_mismatch(seeded):
    from app.services import project_po_service as pos

    db, company_id, owner = seeded
    project, _q, version, _p = _quoted_project(db, company_id, owner)
    po = pos.create_po(
        db,
        project=project,
        actor_user_id=owner,
        payload={
            "quotation_version_id": version.id,
            "po_source": "trading_house",
            "po_number": "PO-9008",
        },
    )

    line = pos.upsert_line(
        db,
        po=po,
        payload={"product_code": "THEIR-OWN-CODE", "unit_price": Decimal("100.00"), "quantity": 1},
    )

    assert line.model_mismatch is True


def test_line_flags_are_stored_and_survive_a_later_version_edit(seeded):
    """Same reasoning as the price floor (AC-E7): the flag records what was true when the
    PO was checked. Re-deriving it on read would make an old PO change its mind."""
    from app.services import project_po_service as pos
    from app.services import project_quotation_service as quotes

    db, company_id, owner = seeded
    project, _q, version, product = _quoted_project(db, company_id, owner, unit_price="900.00")
    po = pos.create_po(
        db,
        project=project,
        actor_user_id=owner,
        payload={
            "quotation_version_id": version.id,
            "po_source": "contractor_direct",
            "po_number": "PO-9009",
        },
    )
    line = pos.upsert_line(
        db,
        po=po,
        payload={"product_id": product.id, "unit_price": Decimal("900.00"), "quantity": 10},
    )
    assert line.price_mismatch is False

    quoted_line = quotes.list_lines(db, version_id=version.id)[0]
    quotes.upsert_line(
        db,
        version=version,
        actor_user_id=owner,
        line=quoted_line,
        payload={"unit_price": Decimal("750.00")},
    )

    db.refresh(line)
    assert line.price_mismatch is False
    assert line.quoted_unit_price == Decimal("900.00")


# ------------------------------------------------------------- drift from v1


def test_drift_from_v1_is_reported_as_an_amount_and_a_percentage(seeded):
    """AC-F9a. "v1 RM 1,000.00 -> PO RM 800.00, -20%" is the erosion figure management
    asked for, and it is deliberately NOT a flag."""
    from app.services import project_po_service as pos
    from app.services import project_quotation_service as quotes

    db, company_id, owner = seeded
    project, quotation, v1, product = _quoted_project(
        db, company_id, owner, unit_price="1000.00", quantity=10
    )
    v2 = quotes.revise(db, quotation=quotation, actor_user_id=owner)
    v2_line = quotes.list_lines(db, version_id=v2.id)[0]
    quotes.upsert_line(
        db, version=v2, actor_user_id=owner, line=v2_line, payload={"unit_price": Decimal("900.00")}
    )

    po = pos.create_po(
        db,
        project=project,
        actor_user_id=owner,
        payload={
            "quotation_version_id": v2.id,
            "po_source": "contractor_direct",
            "po_number": "PO-9010",
        },
    )
    pos.upsert_line(
        db, po=po, payload={"product_id": product.id, "unit_price": Decimal("800.00"), "quantity": 10}
    )

    drift = pos.drift_from_first_version(db, po=po)
    assert drift["v1_total"] == Decimal("10000.00")
    assert drift["po_total"] == Decimal("8000.00")
    assert drift["delta"] == Decimal("-2000.00")
    assert drift["percent"] == Decimal("-20.00")


def test_drift_is_none_when_v1_priced_nothing_comparable(seeded):
    """A percentage against zero is not a number, and reporting 0% would read as "no
    erosion" when the truth is "no baseline"."""
    from app.services import project_po_service as pos

    db, company_id, owner = seeded
    from app.services import project_quotation_service as quotes

    project = _project(db, company_id, owner)
    quotation = quotes.create_quotation(
        db, project=project, actor_user_id=owner, payload={"scope_label": "Common Area"}
    )
    version = quotes.current_version(db, quotation.id)
    po = pos.create_po(
        db,
        project=project,
        actor_user_id=owner,
        payload={
            "quotation_version_id": version.id,
            "po_source": "contractor_direct",
            "po_number": "PO-9011",
        },
    )

    drift = pos.drift_from_first_version(db, po=po)
    assert drift["percent"] is None


# --------------------------------------------------------- the auto status edge


def test_the_first_po_moves_the_project_to_po_received(seeded):
    """AC-F10, the single auto edge in v1."""
    from app.services import project_po_service as pos

    db, company_id, owner = seeded
    project, _q, version, _p = _quoted_project(db, company_id, owner)
    # Arranged, not exercised: getting from Identified to Quoted legally means walking
    # three rungs, and the transition engine has its own tests.
    project.status_id = _status_id(db, "quoted")
    db.flush()

    pos.create_po(
        db,
        project=project,
        actor_user_id=owner,
        payload={
            "quotation_version_id": version.id,
            "po_source": "contractor_direct",
            "po_number": "PO-9012",
        },
    )

    db.refresh(project)
    assert project.status_id == _status_id(db, "po_received")


def test_the_auto_edge_does_not_touch_the_derived_outcome(seeded):
    """AC-F10 explicitly: outcome comes from quotations (AC-E10), not from a PO. A PO
    against a lost scope is a data problem somebody should see, not something to paper
    over by flipping the outcome."""
    from app.services import project_po_service as pos

    db, company_id, owner = seeded
    project, _q, version, _p = _quoted_project(db, company_id, owner)
    outcome_before = project.outcome

    pos.create_po(
        db,
        project=project,
        actor_user_id=owner,
        payload={
            "quotation_version_id": version.id,
            "po_source": "contractor_direct",
            "po_number": "PO-9013",
        },
    )

    db.refresh(project)
    assert project.outcome == outcome_before


def test_a_second_po_does_not_move_the_status_again(seeded):
    """Already terminal; a second attempt would be an illegal transition and would raise
    on a perfectly ordinary second PO."""
    from app.services import project_po_service as pos

    db, company_id, owner = seeded
    project, _q, version, _p = _quoted_project(db, company_id, owner)
    for number in ("PO-9014", "PO-9015"):
        pos.create_po(
            db,
            project=project,
            actor_user_id=owner,
            payload={
                "quotation_version_id": version.id,
                "po_source": "contractor_direct",
                "po_number": number,
            },
        )

    db.refresh(project)
    assert project.status_id == _status_id(db, "po_received")
    assert len(pos.list_pos(db, project_id=project.id)) == 2


def test_an_illegal_auto_edge_records_the_po_anyway_and_says_the_status_did_not_move(seeded):
    """A PO is a fact. If the configured graph has no edge to PO Received from where the
    project sits, the recourse is to fix the graph or move the project by hand -- not to
    refuse the PO, and not to bypass the engine that exists to reject illegal moves."""
    from app.services import project_po_service as pos

    db, company_id, owner = seeded
    project, _q, version, _p = _quoted_project(db, company_id, owner)
    db.execute(
        text(
            "delete from status_transitions where entity_type = 'project' "
            "and to_status_id = :t"
        ),
        {"t": _status_id(db, "po_received")},
    )
    status_before = project.status_id

    po = pos.create_po(
        db,
        project=project,
        actor_user_id=owner,
        payload={
            "quotation_version_id": version.id,
            "po_source": "contractor_direct",
            "po_number": "PO-9016",
        },
    )

    db.refresh(project)
    assert project.status_id == status_before
    assert getattr(po, "_status_moved", None) is False


def test_recording_a_po_blocks_deleting_the_project(seeded):
    """AC-G10. The guard was written in S2 against information_schema; this is the first
    time the table it looks for actually exists."""
    from app.services import project_po_service as pos
    from app.services import project_service

    db, company_id, owner = seeded
    project, _q, version, _p = _quoted_project(db, company_id, owner)
    pos.create_po(
        db,
        project=project,
        actor_user_id=owner,
        payload={
            "quotation_version_id": version.id,
            "po_source": "contractor_direct",
            "po_number": "PO-9017",
        },
    )

    with pytest.raises(AppException) as excinfo:
        project_service.delete_project(
            db, project, actor_user_id=owner, permissions={"projects.projects.delete"}
        )
    assert excinfo.value.status_code == 409


# --------------------------------------------------------------- serialisation


def test_serialisation_names_the_issuer_the_scope_and_the_flag_counts(seeded):
    from app.services import project_po_service as pos

    db, company_id, owner = seeded
    project, _q, version, product = _quoted_project(db, company_id, owner, unit_price="900.00")
    contractor = _party(db, company_id, "main_contractor")
    po = pos.create_po(
        db,
        project=project,
        actor_user_id=owner,
        payload={
            "quotation_version_id": version.id,
            "po_source": "contractor_direct",
            "issuing_party_id": contractor.id,
            "po_number": "PO-9018",
        },
    )
    pos.upsert_line(
        db, po=po, payload={"product_id": product.id, "unit_price": Decimal("820.00"), "quantity": 10}
    )

    rows = pos.serialize_pos(db, pos.list_pos(db, project_id=project.id))
    assert rows[0]["issuing_party_name"] == contractor.name
    assert rows[0]["scope_label"] == "House Units"
    assert rows[0]["version_no"] == 1
    assert rows[0]["price_mismatch_count"] == 1
    assert rows[0]["model_mismatch_count"] == 0
    assert rows[0]["line_count"] == 1


def test_drift_is_none_before_anything_is_entered_on_the_po(seeded):
    """A PO recorded as a header with no lines and no amount has NO figure yet, and
    reporting "-100%" says we gave the whole thing away. The browser showed exactly that
    on a freshly recorded PO, which is the moment a salesperson is most likely to be
    looking at the screen with a manager.
    """
    from app.services import project_po_service as pos

    db, company_id, owner = seeded
    project, _q, version, _p = _quoted_project(
        db, company_id, owner, unit_price="1000.00", quantity=10
    )
    po = pos.create_po(
        db,
        project=project,
        actor_user_id=owner,
        payload={
            "quotation_version_id": version.id,
            "po_source": "contractor_direct",
            "po_number": "PO-9020",
        },
    )

    drift = pos.drift_from_first_version(db, po=po)
    assert drift["po_total"] == Decimal("0.00")
    assert drift["percent"] is None
    assert drift["delta"] is None


def test_a_matched_line_takes_its_code_from_the_product(seeded):
    """The PO line has to be readable. Recording it with only a product_id left the row
    rendering as "Unnamed item" in the browser, which is useless next to a mismatch badge:
    the first thing anybody asks is WHICH item differs.

    Snapshotted rather than joined at read time, for the same reason the quotation line is
    (AC-E4): what the PO was checked against must not change when the catalogue does.
    """
    from app.services import project_po_service as pos

    db, company_id, owner = seeded
    project, _q, version, product = _quoted_project(db, company_id, owner, unit_price="900.00")
    po = pos.create_po(
        db,
        project=project,
        actor_user_id=owner,
        payload={
            "quotation_version_id": version.id,
            "po_source": "contractor_direct",
            "po_number": "PO-9021",
        },
    )

    line = pos.upsert_line(
        db, po=po, payload={"product_id": product.id, "unit_price": Decimal("900.00")}
    )

    assert line.product_code == product.product_code
    assert line.description


def test_a_code_the_po_actually_printed_is_never_overwritten(seeded):
    """Their code is evidence. If the PO says "WC-BLK-01" for our SRT-WC-01, that IS the
    mismatch somebody needs to see, and replacing it with our own code hides it."""
    from app.services import project_po_service as pos

    db, company_id, owner = seeded
    project, _q, version, product = _quoted_project(db, company_id, owner)
    po = pos.create_po(
        db,
        project=project,
        actor_user_id=owner,
        payload={
            "quotation_version_id": version.id,
            "po_source": "contractor_direct",
            "po_number": "PO-9022",
        },
    )

    line = pos.upsert_line(
        db,
        po=po,
        payload={
            "product_id": product.id,
            "product_code": "THEIR-WC-BLK-01",
            "unit_price": Decimal("900.00"),
        },
    )

    assert line.product_code == "THEIR-WC-BLK-01"
