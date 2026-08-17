"""S3 quotations, versions and the two alerts (UAC Group E).

The version model is the part worth specifying carefully, because it is defined by what
it does NOT have (AC-E3a): no ``current_version_id``, no ``is_frozen`` flag. Current is
``MAX(version_no)`` and everything below it is frozen. Every test here is really asking
"can the two facts disagree", and the answer must stay no.

The other subtlety is the below-floor alert firing on the TRANSITION into breach only
(AC-E6a). Editing in place is the normal way to work, and an alert on every save is an
alert people filter to a folder they never open.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.projects import ProjectSeries
from app.models.user import User
from app.services import project_seed_service
from app.services.error_handler import AppException

from ._pg_fixture import blank_session

MARKER = "zzt-quote"


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


def _category(db, name: str, parent_id=None) -> ProductCategory:
    row = ProductCategory(
        id=_uid(),
        category_code=f"ZZT-{_uid()[:8]}",
        category_name=f"{MARKER} {name}",
        parent_category_id=parent_id,
    )
    db.add(row)
    db.flush()
    return row


def _product(db, category_id: str, uom_id: str, list_price: str, code=None) -> Product:
    row = Product(
        id=_uid(),
        product_code=code or f"ZZT-{_uid()[:8]}",
        product_name=f"{MARKER} Basin",
        description="Wall-hung basin, white",
        category_id=category_id,
        base_uom_id=uom_id,
        list_price=Decimal(list_price),
    )
    db.add(row)
    db.flush()
    return row


def _project(db, company_id: str, owner: str, title=None):
    from app.services.project_service import register_project

    return register_project(
        db,
        company_id=company_id,
        actor_user_id=owner,
        developer_party_id=None,
        title=title or f"{MARKER} Tower {_uid()[:6]}",
    )


def _floor(db, company_id: str, *, mode: str, value: str, category_id=None):
    from app.services import project_pricing_service as pricing

    return pricing.upsert_floor_rule(
        db,
        company_id=company_id,
        payload={"mode": mode, "value": value, "category_id": category_id},
    )


# ------------------------------------------------------------------- versions


def test_creating_a_quotation_opens_version_one():
    from app.services import project_quotation_service as quotes

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        owner = _user(db, f"{MARKER} Ali")
        project = _project(db, company_id, owner)

        quotation = quotes.create_quotation(
            db,
            project=project,
            actor_user_id=owner,
            payload={"scope_label": "House Units"},
        )

        version = quotes.current_version(db, quotation.id)
        assert version.version_no == 1
        assert version.frozen_at is None
        assert quotation.outcome == quotes.OUTCOME_OPEN


def test_editing_the_current_version_saves_in_place_and_does_not_create_a_version():
    """AC-E2. A new version per keystroke would make "which one did we send" unanswerable."""
    from app.services import project_quotation_service as quotes

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        owner = _user(db, f"{MARKER} Ali")
        uom = _uom(db)
        category = _category(db, "Basins")
        product = _product(db, category.id, uom, "1000.00")
        project = _project(db, company_id, owner)

        quotation = quotes.create_quotation(
            db, project=project, actor_user_id=owner, payload={"scope_label": "House Units"}
        )
        version = quotes.current_version(db, quotation.id)

        quotes.upsert_line(
            db,
            version=version,
            actor_user_id=owner,
            payload={"product_id": product.id, "unit_price": "900.00", "quantity": 10},
        )
        quotes.upsert_line(
            db,
            version=version,
            actor_user_id=owner,
            payload={"product_id": product.id, "unit_price": "880.00", "quantity": 4},
        )

        assert len(quotes.list_versions(db, quotation.id)) == 1
        assert quotes.current_version(db, quotation.id).version_no == 1


def test_revise_freezes_the_current_version_and_opens_the_next():
    """AC-E3. The frozen one is exactly what the customer holds."""
    from app.services import project_quotation_service as quotes

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        owner = _user(db, f"{MARKER} Ali")
        uom = _uom(db)
        category = _category(db, "Basins")
        product = _product(db, category.id, uom, "1000.00")
        project = _project(db, company_id, owner)

        quotation = quotes.create_quotation(
            db, project=project, actor_user_id=owner, payload={"scope_label": "House Units"}
        )
        first = quotes.current_version(db, quotation.id)
        quotes.upsert_line(
            db,
            version=first,
            actor_user_id=owner,
            payload={"product_id": product.id, "unit_price": "900.00", "quantity": 10},
        )

        second = quotes.revise(db, quotation=quotation, actor_user_id=owner)

        assert second.version_no == 2
        assert second.frozen_at is None
        db.refresh(first)
        assert first.frozen_at is not None
        # The lines come across, so revising is a starting point rather than a blank page.
        assert len(quotes.list_lines(db, second.id)) == 1
        assert quotes.list_lines(db, second.id)[0].unit_price == Decimal("900.00")


def test_a_frozen_version_can_never_be_edited_again():
    from app.services import project_quotation_service as quotes

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        owner = _user(db, f"{MARKER} Ali")
        uom = _uom(db)
        category = _category(db, "Basins")
        product = _product(db, category.id, uom, "1000.00")
        project = _project(db, company_id, owner)

        quotation = quotes.create_quotation(
            db, project=project, actor_user_id=owner, payload={"scope_label": "House Units"}
        )
        first = quotes.current_version(db, quotation.id)
        line = quotes.upsert_line(
            db,
            version=first,
            actor_user_id=owner,
            payload={"product_id": product.id, "unit_price": "900.00", "quantity": 10},
        )
        quotes.revise(db, quotation=quotation, actor_user_id=owner)

        with pytest.raises(AppException) as adding:
            quotes.upsert_line(
                db,
                version=first,
                actor_user_id=owner,
                payload={"product_id": product.id, "unit_price": "800.00", "quantity": 1},
            )
        assert adding.value.status_code == 422

        with pytest.raises(AppException) as deleting:
            quotes.delete_line(db, version=first, line=line)
        assert deleting.value.status_code == 422


def test_frozen_is_derived_from_version_number_not_stored_as_a_flag():
    """AC-E3a. The guard against the two facts drifting: there is only one fact."""
    from app.models.projects import ProjectQuotationVersion
    from app.services import project_quotation_service as quotes

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        owner = _user(db, f"{MARKER} Ali")
        project = _project(db, company_id, owner)
        quotation = quotes.create_quotation(
            db, project=project, actor_user_id=owner, payload={"scope_label": "House Units"}
        )
        quotes.revise(db, quotation=quotation, actor_user_id=owner)
        quotes.revise(db, quotation=quotation, actor_user_id=owner)

        columns = {c.name for c in ProjectQuotationVersion.__table__.columns}
        assert "is_frozen" not in columns
        assert "current_version_id" not in {
            c.name for c in quotation.__table__.columns
        }

        versions = quotes.list_versions(db, quotation.id)
        assert [v.version_no for v in versions] == [3, 2, 1]
        assert quotes.current_version(db, quotation.id).version_no == 3
        assert [quotes.is_frozen(db, v) for v in versions] == [False, True, True]


def test_two_versions_cannot_share_a_number():
    from app.models.projects import ProjectQuotationVersion
    from app.services import project_quotation_service as quotes

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        owner = _user(db, f"{MARKER} Ali")
        project = _project(db, company_id, owner)
        quotation = quotes.create_quotation(
            db, project=project, actor_user_id=owner, payload={"scope_label": "House Units"}
        )

        db.add(
            ProjectQuotationVersion(
                id=_uid(),
                company_id=company_id,
                quotation_id=quotation.id,
                version_no=1,
            )
        )
        with pytest.raises(Exception):
            db.flush()
        db.rollback()


# --------------------------------------------------------------------- lines


def test_a_line_snapshots_the_product_so_a_later_price_change_cannot_rewrite_history():
    """AC-E4."""
    from app.services import project_quotation_service as quotes

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        owner = _user(db, f"{MARKER} Ali")
        uom = _uom(db)
        category = _category(db, "Basins")
        product = _product(db, category.id, uom, "1000.00", code="ZZT-BASIN-1")
        project = _project(db, company_id, owner)

        quotation = quotes.create_quotation(
            db, project=project, actor_user_id=owner, payload={"scope_label": "House Units"}
        )
        version = quotes.current_version(db, quotation.id)
        line = quotes.upsert_line(
            db,
            version=version,
            actor_user_id=owner,
            payload={
                "product_id": product.id,
                "unit_price": "900.00",
                "quantity": 10,
                "unit_type": "house_unit",
            },
        )

        assert line.product_code_snapshot == "ZZT-BASIN-1"
        assert line.description_snapshot == "Wall-hung basin, white"
        assert line.list_price_snapshot == Decimal("1000.00")
        assert line.line_total == Decimal("9000.00")

        product.product_code = "ZZT-BASIN-RENAMED"
        product.list_price = Decimal("1500.00")
        db.flush()
        db.refresh(line)

        assert line.product_code_snapshot == "ZZT-BASIN-1"
        assert line.list_price_snapshot == Decimal("1000.00")


def test_the_version_total_is_the_sum_of_its_lines():
    from app.services import project_quotation_service as quotes

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        owner = _user(db, f"{MARKER} Ali")
        uom = _uom(db)
        category = _category(db, "Basins")
        product = _product(db, category.id, uom, "1000.00")
        project = _project(db, company_id, owner)

        quotation = quotes.create_quotation(
            db, project=project, actor_user_id=owner, payload={"scope_label": "House Units"}
        )
        version = quotes.current_version(db, quotation.id)
        quotes.upsert_line(
            db,
            version=version,
            actor_user_id=owner,
            payload={"product_id": product.id, "unit_price": "900.00", "quantity": 10},
        )
        second = quotes.upsert_line(
            db,
            version=version,
            actor_user_id=owner,
            payload={"product_id": product.id, "unit_price": "100.00", "quantity": 5},
        )

        db.refresh(version)
        assert version.total_amount == Decimal("9500.00")

        quotes.delete_line(db, version=version, line=second)
        db.refresh(version)
        assert version.total_amount == Decimal("9000.00")


# -------------------------------------------------------------------- alerts


def test_an_off_catalog_line_always_raises_the_non_standard_alert():
    """AC-E5. There is no category to check, and "we quoted something not in our
    catalogue" is exactly what the alert exists to surface."""
    from app.services import project_quotation_service as quotes

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        owner = _user(db, f"{MARKER} Ali")
        project = _project(db, company_id, owner)

        quotation = quotes.create_quotation(
            db, project=project, actor_user_id=owner, payload={"scope_label": "House Units"}
        )
        version = quotes.current_version(db, quotation.id)
        line = quotes.upsert_line(
            db,
            version=version,
            actor_user_id=owner,
            payload={
                "description_snapshot": "Bespoke stone counter",
                "unit_price": "4000.00",
                "quantity": 1,
            },
        )

        assert line.product_id is None
        assert line.is_non_standard is True


def test_a_product_outside_the_nominated_series_raises_the_non_standard_alert():
    from app.services import project_pricing_service as pricing
    from app.services import project_quotation_service as quotes

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        owner = _user(db, f"{MARKER} Ali")
        uom = _uom(db)
        inside_parent = _category(db, "Sanitary Ware")
        inside_leaf = _category(db, "Basins", parent_id=inside_parent.id)
        outside = _category(db, "Kitchen Sinks")
        in_series = _product(db, inside_leaf.id, uom, "1000.00")
        out_of_series = _product(db, outside.id, uom, "1000.00")

        series = ProjectSeries(id=_uid(), company_id=company_id, name=f"{MARKER} Premium")
        db.add(series)
        db.flush()
        pricing.set_series_categories(
            db, series=series, category_ids=[inside_parent.id]
        )

        project = _project(db, company_id, owner)
        quotation = quotes.create_quotation(
            db,
            project=project,
            actor_user_id=owner,
            payload={"scope_label": "House Units", "series_id": series.id},
        )
        version = quotes.current_version(db, quotation.id)

        standard = quotes.upsert_line(
            db,
            version=version,
            actor_user_id=owner,
            payload={"product_id": in_series.id, "unit_price": "900.00", "quantity": 1},
        )
        non_standard = quotes.upsert_line(
            db,
            version=version,
            actor_user_id=owner,
            payload={"product_id": out_of_series.id, "unit_price": "900.00", "quantity": 1},
        )

        assert standard.is_non_standard is False
        assert non_standard.is_non_standard is True


def test_a_line_below_its_floor_is_flagged_and_stores_the_floor_it_breached():
    """AC-E6 + AC-E7: the value in force at the time lives on the line."""
    from app.services import project_quotation_service as quotes

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        owner = _user(db, f"{MARKER} Ali")
        uom = _uom(db)
        category = _category(db, "Basins")
        product = _product(db, category.id, uom, "1000.00")
        _floor(db, company_id, mode="percent", value="90", category_id=category.id)
        project = _project(db, company_id, owner)

        quotation = quotes.create_quotation(
            db, project=project, actor_user_id=owner, payload={"scope_label": "House Units"}
        )
        version = quotes.current_version(db, quotation.id)

        compliant = quotes.upsert_line(
            db,
            version=version,
            actor_user_id=owner,
            payload={"product_id": product.id, "unit_price": "950.00", "quantity": 1},
        )
        breaching = quotes.upsert_line(
            db,
            version=version,
            actor_user_id=owner,
            payload={"product_id": product.id, "unit_price": "850.00", "quantity": 1},
        )

        assert compliant.is_below_floor is False
        assert compliant.floor_value_applied == Decimal("900.00")
        assert breaching.is_below_floor is True
        assert breaching.floor_value_applied == Decimal("900.00")
        assert breaching.floor_level_applied == "category"


def test_changing_floor_policy_later_never_retro_flags_a_sent_quotation():
    """AC-E7. The customer holds a document; a policy change tomorrow must not turn it
    retrospectively non-compliant."""
    from app.services import project_quotation_service as quotes

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        owner = _user(db, f"{MARKER} Ali")
        uom = _uom(db)
        category = _category(db, "Basins")
        product = _product(db, category.id, uom, "1000.00")
        _floor(db, company_id, mode="percent", value="80", category_id=category.id)
        project = _project(db, company_id, owner)

        quotation = quotes.create_quotation(
            db, project=project, actor_user_id=owner, payload={"scope_label": "House Units"}
        )
        version = quotes.current_version(db, quotation.id)
        line = quotes.upsert_line(
            db,
            version=version,
            actor_user_id=owner,
            payload={"product_id": product.id, "unit_price": "850.00", "quantity": 1},
        )
        assert line.is_below_floor is False
        assert line.floor_value_applied == Decimal("800.00")

        # Policy tightens well above what was quoted.
        _floor(db, company_id, mode="percent", value="95", category_id=category.id)
        db.refresh(line)

        assert line.is_below_floor is False
        assert line.floor_value_applied == Decimal("800.00")


def test_management_is_notified_on_entering_breach_and_not_on_every_save():
    """AC-E6a. In-place editing is how the work is done, so an alert per save is an
    alert people learn to ignore -- and then the real one is ignored too."""
    from app.services import project_quotation_service as quotes

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        owner = _user(db, f"{MARKER} Ali")
        uom = _uom(db)
        category = _category(db, "Basins")
        product = _product(db, category.id, uom, "1000.00")
        _floor(db, company_id, mode="percent", value="90", category_id=category.id)
        project = _project(db, company_id, owner)

        quotation = quotes.create_quotation(
            db, project=project, actor_user_id=owner, payload={"scope_label": "House Units"}
        )
        version = quotes.current_version(db, quotation.id)

        line = quotes.upsert_line(
            db,
            version=version,
            actor_user_id=owner,
            payload={"product_id": product.id, "unit_price": "950.00", "quantity": 1},
        )
        assert quotes.pop_breach_events(line) == []

        line = quotes.upsert_line(
            db,
            version=version,
            actor_user_id=owner,
            line=line,
            payload={"unit_price": "850.00"},
        )
        entered = quotes.pop_breach_events(line)
        assert len(entered) == 1
        assert entered[0]["floor_value"] == Decimal("900.00")

        # Still in breach, edited again: silent.
        line = quotes.upsert_line(
            db, version=version, actor_user_id=owner, line=line, payload={"unit_price": "840.00"}
        )
        assert quotes.pop_breach_events(line) == []

        # Back above the floor, then below again: that is a NEW breach and notifies.
        line = quotes.upsert_line(
            db, version=version, actor_user_id=owner, line=line, payload={"unit_price": "960.00"}
        )
        assert quotes.pop_breach_events(line) == []
        line = quotes.upsert_line(
            db, version=version, actor_user_id=owner, line=line, payload={"unit_price": "800.00"}
        )
        assert len(quotes.pop_breach_events(line)) == 1


# ------------------------------------------------- outcome, derived and not


def test_losing_a_quotation_requires_a_reason_from_the_lookup():
    """AC-E9."""
    from app.services import project_quotation_service as quotes

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        owner = _user(db, f"{MARKER} Ali")
        project = _project(db, company_id, owner)
        quotation = quotes.create_quotation(
            db, project=project, actor_user_id=owner, payload={"scope_label": "House Units"}
        )

        with pytest.raises(AppException) as missing:
            quotes.set_outcome(db, quotation=quotation, outcome="lost", loss_reason=None)
        assert missing.value.status_code == 422

        with pytest.raises(AppException) as invented:
            quotes.set_outcome(
                db, quotation=quotation, outcome="lost", loss_reason="they hated us"
            )
        assert invented.value.status_code == 422

        quotes.set_outcome(db, quotation=quotation, outcome="lost", loss_reason="price")
        assert quotation.outcome == "lost"
        assert quotation.loss_reason == "price"
        assert quotation.decided_at is not None


def test_winning_a_quotation_clears_any_loss_reason():
    from app.services import project_quotation_service as quotes

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        owner = _user(db, f"{MARKER} Ali")
        project = _project(db, company_id, owner)
        quotation = quotes.create_quotation(
            db, project=project, actor_user_id=owner, payload={"scope_label": "House Units"}
        )
        quotes.set_outcome(db, quotation=quotation, outcome="lost", loss_reason="price")

        quotes.set_outcome(db, quotation=quotation, outcome="won", loss_reason=None)

        assert quotation.outcome == "won"
        assert quotation.loss_reason is None


def test_project_outcome_is_derived_won_if_any_lost_only_if_all():
    """AC-E10. A project with one won scope and one open scope is still live."""
    from app.services import project_quotation_service as quotes

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        owner = _user(db, f"{MARKER} Ali")
        project = _project(db, company_id, owner)

        # No quotations at all: open, not lost. Nothing has been decided.
        assert quotes.derive_project_outcome(db, project) == "open"

        house = quotes.create_quotation(
            db, project=project, actor_user_id=owner, payload={"scope_label": "House Units"}
        )
        common = quotes.create_quotation(
            db, project=project, actor_user_id=owner, payload={"scope_label": "Common Area"}
        )
        assert quotes.derive_project_outcome(db, project) == "open"

        quotes.set_outcome(db, quotation=house, outcome="lost", loss_reason="price")
        assert quotes.derive_project_outcome(db, project) == "open"

        quotes.set_outcome(db, quotation=common, outcome="lost", loss_reason="lead_time")
        assert quotes.derive_project_outcome(db, project) == "lost"

        # One win flips the whole project back to won, even alongside a loss.
        quotes.set_outcome(db, quotation=house, outcome="won", loss_reason=None)
        assert quotes.derive_project_outcome(db, project) == "won"


def test_setting_a_quotation_outcome_updates_the_projects_derived_outcome():
    from app.services import project_quotation_service as quotes

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        owner = _user(db, f"{MARKER} Ali")
        project = _project(db, company_id, owner)
        quotation = quotes.create_quotation(
            db, project=project, actor_user_id=owner, payload={"scope_label": "House Units"}
        )

        quotes.set_outcome(db, quotation=quotation, outcome="won", loss_reason=None)

        db.refresh(project)
        assert project.outcome == "won"


def test_the_project_status_is_never_touched_by_an_outcome_change():
    """AC-E10a: outcome and status are different axes. Moving one must not move the
    other, or the board starts lying about where work actually is."""
    from app.services import project_quotation_service as quotes

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        owner = _user(db, f"{MARKER} Ali")
        project = _project(db, company_id, owner)
        status_before = project.status_id

        quotation = quotes.create_quotation(
            db, project=project, actor_user_id=owner, payload={"scope_label": "House Units"}
        )
        quotes.set_outcome(db, quotation=quotation, outcome="won", loss_reason=None)

        db.refresh(project)
        assert project.status_id == status_before


# --------------------------------------------------------------------- audit


def test_editing_a_line_leaves_an_audit_trail():
    """AC-E2 says an in-place edit writes an audit entry, and the LINE is where the money
    changes. Tracking only the version would leave an edit that happens not to move the
    version total -- a quantity swap, a description fix -- with no trail at all, which is
    exactly the edit somebody would want to explain later.

    The before-flush handler is invoked directly, the same way the audit-attribution test
    does it: the global listener is registered at app startup, which a unit test does not
    run, and registering it here would put audit side effects on every other test's flush.
    """
    from app.models.audit import AuditLog
    from app.services import audit_service
    from app.services import project_quotation_service as quotes

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        owner = _user(db, f"{MARKER} Ali")
        uom = _uom(db)
        category = _category(db, "Basins")
        product = _product(db, category.id, uom, "1000.00")
        project = _project(db, company_id, owner)
        quotation = quotes.create_quotation(
            db, project=project, actor_user_id=owner, payload={"scope_label": "House Units"}
        )
        version = quotes.current_version(db, quotation.id)
        line = quotes.upsert_line(
            db,
            version=version,
            actor_user_id=owner,
            payload={"product_id": product.id, "unit_price": Decimal("900"), "quantity": 2},
        )

        # An edit that does NOT move the line total, so the version's own audit row would
        # not fire for it.
        line.notes = "Agreed with the QS on site"
        audit_service._session_before_flush(db, None, None)

        rows = [
            obj
            for obj in db.new
            if isinstance(obj, AuditLog)
            and obj.entity_type == "project_quotation_lines"
            and obj.entity_id == line.id
            and obj.action == "UPDATE"
        ]
        assert rows, "a line edit wrote no audit entry"


def test_changing_a_price_floor_leaves_an_audit_trail():
    """A floor is a policy somebody set, and a breach report is only arguable if who
    changed the policy and when is recoverable."""
    from app.models.audit import AuditLog
    from app.services import audit_service

    with blank_session() as db:
        company_id = _sorento(db)
        rule = _floor(db, company_id, mode="percent", value="70")
        db.flush()

        rule.value = Decimal("60")
        audit_service._session_before_flush(db, None, None)

        rows = [
            obj
            for obj in db.new
            if isinstance(obj, AuditLog)
            and obj.entity_type == "price_floor_rules"
            and obj.entity_id == rule.id
        ]
        assert rows, "a price floor change wrote no audit entry"
