"""Promotion-type CRUD and the migration's seed (UAC T1, T5, T6).

The seed is exercised by importing the migration and running its helpers inside a
blank schema, rather than asserting against whatever the shared database holds --
that tests the code instead of the environment.
"""
from __future__ import annotations

import importlib.util
import json
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa

from app.models.marketing import Promotion, PromotionType
from app.schemas.marketing import PromotionTypeCreate, PromotionTypeUpdate
from app.services.error_handler import AppException
from app.services.marketing_service import PromotionTypeService
from tests._pg_fixture import blank_session


MIGRATION = (
    Path(__file__).resolve().parents[1] / "alembic" / "versions" / "361_promotion_types.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("m361_promotion_types", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SEED_SQL = """
INSERT INTO promotion_types (
    id, type_code, type_name, description, show_expired,
    expired_valid_until_year_end, expired_max_age_days,
    match_markers, match_priority, is_default, sort_order
)
SELECT gen_random_uuid(), :code, :name, :description, :show_expired,
       :year_end, :max_age, CAST(:markers AS jsonb), :priority,
       :is_default, :sort_order
WHERE NOT EXISTS (SELECT 1 FROM promotion_types WHERE type_code = :code)
"""


def _run_seed(db, module):
    for (
        code, name, show_expired, year_end, max_age, markers, priority, is_default, sort_order, description,
    ) in module.SEED_TYPES:
        db.execute(
            sa.text(SEED_SQL),
            {
                "code": code,
                "name": name,
                "description": description,
                "show_expired": show_expired,
                "year_end": year_end,
                "max_age": max_age,
                "markers": json.dumps(markers),
                "priority": priority,
                "is_default": is_default,
                "sort_order": sort_order,
            },
        )
    db.flush()


def test_seed_creates_the_five_types_and_is_idempotent():  # T1
    module = _load_migration()
    with blank_session() as db:
        _run_seed(db, module)
        _run_seed(db, module)  # a second upgrade must not duplicate

        rows = db.query(PromotionType).all()
        by_code = {row.type_code: row for row in rows}
        assert set(by_code) == {"special", "pp", "focus_item", "a3_flyer", "standard"}
        assert by_code["special"].show_expired is False
        assert by_code["pp"].show_expired is True
        assert by_code["pp"].expired_valid_until_year_end is True
        assert by_code["a3_flyer"].expired_max_age_days == 180
        assert [row.type_code for row in rows if row.is_default] == ["standard"]
        # Conservative first, so a two-marker name resolves to special.
        assert by_code["special"].match_priority < by_code["pp"].match_priority


def test_migration_backfills_existing_promotions_from_their_names():  # T2
    module = _load_migration()
    with blank_session() as db:
        _run_seed(db, module)
        db.add_all(
            [
                Promotion(id=str(uuid.uuid4()), description="SORENTO SPECIAL PROMO_01072026.pdf", access_levels=["dealer"]),
                Promotion(id=str(uuid.uuid4()), description="_SORENTO A3 FLYER 2025-2026", access_levels=["dealer"]),
                Promotion(id=str(uuid.uuid4()), description="CABANA SHELF PROMO 31032026", access_levels=["dealer"]),
            ]
        )
        db.flush()

        module._backfill_promotion_types(db.connection())
        db.expire_all()

        got = {
            promo.description: (promo.promotion_type.type_code, promo.promotion_type_source)
            for promo in db.query(Promotion).all()
        }
        assert got["SORENTO SPECIAL PROMO_01072026.pdf"] == ("special", "auto")
        assert got["_SORENTO A3 FLYER 2025-2026"] == ("a3_flyer", "auto")
        assert got["CABANA SHELF PROMO 31032026"] == ("standard", "auto")


def test_backfill_leaves_a_manual_classification_alone():  # C5 (migration half)
    module = _load_migration()
    with blank_session() as db:
        _run_seed(db, module)
        standard = db.query(PromotionType).filter(PromotionType.type_code == "standard").one()
        promo = Promotion(
            id=str(uuid.uuid4()),
            description="SORENTO SPECIAL PROMO_01072026.pdf",
            access_levels=["dealer"],
            promotion_type_id=standard.id,
            promotion_type_source="manual",
        )
        db.add(promo)
        db.flush()

        module._backfill_promotion_types(db.connection())
        db.expire_all()

        assert db.query(Promotion).one().promotion_type.type_code == "standard"


def _service(db):
    return PromotionTypeService(db)


def _create(db, **kwargs):
    payload = dict(
        type_code="clearance",
        type_name="Clearance",
        show_expired=False,
        match_markers=["Clearance"],
        match_priority=15,
    )
    payload.update(kwargs)
    return _service(db).create_promotion_type(PromotionTypeCreate(**payload))


def test_create_normalizes_code_and_markers():
    with blank_session() as db:
        created = _create(db, type_code="  ClearAnce ", match_markers=["Clearance", "clearance", " END OF LINE "])
        assert created.type_code == "clearance"
        assert created.match_markers == ["clearance", "end of line"]


def test_blank_type_code_is_rejected_on_create_and_update():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        PromotionTypeCreate(type_code="   ", type_name="Blank")
    with pytest.raises(ValidationError):
        PromotionTypeUpdate(type_code="")


def test_duplicate_code_is_a_conflict_not_a_500():  # T6
    with blank_session() as db:
        _create(db)
        with pytest.raises(AppException) as exc:
            _create(db)
        assert exc.value.status_code == 409


def test_delete_is_hard_and_unclassifies_its_promotions():  # T5
    with blank_session() as db:
        created = _create(db)
        promo = Promotion(
            id=str(uuid.uuid4()),
            description="ZZT clearance promo",
            access_levels=["dealer"],
            promotion_type_id=created.id,
            promotion_type_source="auto",
        )
        db.add(promo)
        db.commit()

        result = _service(db).delete_promotion_type(created.id)

        assert result["promotions_unclassified"] == 1
        assert db.query(PromotionType).filter(PromotionType.id == created.id).first() is None
        db.expire_all()
        assert db.query(Promotion).one().promotion_type_id is None


def test_the_default_type_cannot_be_deleted():  # T5
    with blank_session() as db:
        default = _create(db, type_code="standard", type_name="Standard", is_default=True)
        with pytest.raises(AppException) as exc:
            _service(db).delete_promotion_type(default.id)
        assert exc.value.status_code == 409


def test_making_a_type_default_moves_the_flag():
    with blank_session() as db:
        first = _create(db, type_code="standard", type_name="Standard", is_default=True)
        second = _create(db, type_code="house", type_name="House")

        _service(db).update_promotion_type(second.id, PromotionTypeUpdate(is_default=True))
        db.expire_all()

        assert db.query(PromotionType).filter(PromotionType.id == first.id).one().is_default is False
        assert db.query(PromotionType).filter(PromotionType.id == second.id).one().is_default is True


def test_unticking_the_only_default_is_refused():
    with blank_session() as db:
        default = _create(db, type_code="standard", type_name="Standard", is_default=True)
        with pytest.raises(AppException) as exc:
            _service(db).update_promotion_type(default.id, PromotionTypeUpdate(is_default=False))
        assert exc.value.status_code == 409


def test_list_reports_how_many_promotions_use_each_type():
    with blank_session() as db:
        created = _create(db)
        db.add(
            Promotion(
                id=str(uuid.uuid4()),
                description="ZZT clearance promo",
                access_levels=["dealer"],
                promotion_type_id=created.id,
            )
        )
        db.commit()

        listed = _service(db).list_promotion_types()
        assert [(row.type_code, row.promotions_count) for row in listed] == [("clearance", 1)]


# --- retyping a promotion (UAC V3, V4, C5) ---------------------------------


def test_update_stamps_manual_and_survives_the_schema():
    """The edit form's field has to reach the service, not be dropped in the schema.

    `PromotionUpdate` does not inherit `PromotionBase`, so this is the failure that
    would otherwise look like "the select saves but the value never changes".
    """
    from app.schemas.marketing import PromotionUpdate
    from app.services.marketing_service import PromotionService

    module = _load_migration()
    with blank_session() as db:
        _run_seed(db, module)
        standard = db.query(PromotionType).filter(PromotionType.type_code == "standard").one()
        special = db.query(PromotionType).filter(PromotionType.type_code == "special").one()

        promo = Promotion(
            id=str(uuid.uuid4()),
            description="ZZT SORENTO SPECIAL PROMO",
            access_levels=["dealer"],
            promotion_type_id=special.id,
            promotion_type_source="auto",
        )
        db.add(promo)
        db.commit()

        payload = PromotionUpdate.model_validate({"promotion_type_id": str(standard.id)})
        assert payload.promotion_type_id == str(standard.id)

        updated = PromotionService(db).update_promotion(str(promo.id), payload)

        assert updated.promotion_type_id == str(standard.id)
        assert updated.promotion_type_source == "manual"
        assert updated.promotion_type_code == "standard"


def test_update_can_clear_the_type_back_to_unclassified():
    from app.schemas.marketing import PromotionUpdate
    from app.services.marketing_service import PromotionService

    module = _load_migration()
    with blank_session() as db:
        _run_seed(db, module)
        special = db.query(PromotionType).filter(PromotionType.type_code == "special").one()
        promo = Promotion(
            id=str(uuid.uuid4()),
            description="ZZT SPECIAL",
            access_levels=["dealer"],
            promotion_type_id=special.id,
            promotion_type_source="auto",
        )
        db.add(promo)
        db.commit()

        updated = PromotionService(db).update_promotion(
            str(promo.id), PromotionUpdate.model_validate({"promotion_type_id": None})
        )

        assert updated.promotion_type_id is None
        assert updated.promotion_type_source == "manual"


def test_update_leaves_the_type_alone_when_the_field_is_omitted():
    from app.schemas.marketing import PromotionUpdate
    from app.services.marketing_service import PromotionService

    module = _load_migration()
    with blank_session() as db:
        _run_seed(db, module)
        special = db.query(PromotionType).filter(PromotionType.type_code == "special").one()
        promo = Promotion(
            id=str(uuid.uuid4()),
            description="ZZT SPECIAL",
            access_levels=["dealer"],
            promotion_type_id=special.id,
            promotion_type_source="auto",
        )
        db.add(promo)
        db.commit()

        updated = PromotionService(db).update_promotion(
            str(promo.id), PromotionUpdate.model_validate({"description": "ZZT SPECIAL renamed"})
        )

        assert updated.promotion_type_id == str(special.id)
        assert updated.promotion_type_source == "auto"
