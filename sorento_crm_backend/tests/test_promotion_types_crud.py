"""Promotion-type CRUD and the migration's seed (UAC T1, T5, T6).

The seed is exercised by importing the migration and running its helpers inside a
blank schema, rather than asserting against whatever the shared database holds --
that tests the code instead of the environment.
"""
from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

import pytest

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


def _run_seed(db, module):
    module._seed_types(db.connection())
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


def test_an_explicit_null_on_a_required_field_leaves_the_row_alone():
    """A null for a NOT NULL column is a malformed payload, not a write of NULL."""
    with blank_session() as db:
        created = _create(db, show_expired=True, match_priority=15, type_name="Clearance")

        updated = _service(db).update_promotion_type(
            created.id,
            PromotionTypeUpdate.model_validate(
                {
                    "type_name": None,
                    "show_expired": None,
                    "expired_valid_until_year_end": None,
                    "match_markers": None,
                    "match_priority": None,
                    "sort_order": None,
                    "description": "still editable",
                }
            ),
        )

        assert updated.type_name == "Clearance"
        assert updated.show_expired is True
        assert updated.match_markers == ["clearance"]
        assert updated.match_priority == 15
        assert updated.description == "still editable"


def test_a_malformed_promotion_type_id_is_a_4xx_not_a_db_error():
    """The id reaches a UUID column; an unparseable one must never hit the cast."""
    from app.schemas.marketing import PromotionCreate, PromotionUpdate
    from app.services.marketing_service import PromotionService

    with blank_session() as db:
        with pytest.raises(AppException) as create_exc:
            PromotionService(db).create_promotion(
                PromotionCreate.model_validate(
                    {
                        "description": "ZZT bad type id",
                        "access_levels": ["dealer"],
                        "promotion_type_id": "abc",
                    }
                ),
                created_by=None,
            )
        assert 400 <= create_exc.value.status_code < 500

        promo = Promotion(
            id=str(uuid.uuid4()), description="ZZT retype target", access_levels=["dealer"]
        )
        db.add(promo)
        db.commit()

        with pytest.raises(AppException) as update_exc:
            PromotionService(db).update_promotion(
                str(promo.id), PromotionUpdate.model_validate({"promotion_type_id": "abc"})
            )
        assert 400 <= update_exc.value.status_code < 500

        assert db.query(PromotionType).count() == 0


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


def test_resending_the_same_type_with_another_edit_keeps_the_auto_classification():
    """The edit form posts the current type on every save.

    Treating that echo as a retype would flip every auto row to manual on an
    unrelated edit, and the re-send path never reclassifies a manual row again.
    """
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
            str(promo.id),
            PromotionUpdate.model_validate(
                {
                    "description": "ZZT SPECIAL renamed",
                    "promotion_type_id": str(special.id),
                }
            ),
        )

        assert updated.promotion_type_id == str(special.id)
        assert updated.promotion_type_source == "auto"


def test_create_returns_the_type_code_and_name_it_was_given():
    """The create response feeds the UI directly, and it may not show a UUID."""
    from app.schemas.marketing import PromotionCreate
    from app.services.marketing_service import PromotionService

    module = _load_migration()
    with blank_session() as db:
        _run_seed(db, module)
        special = db.query(PromotionType).filter(PromotionType.type_code == "special").one()

        created = PromotionService(db).create_promotion(
            PromotionCreate.model_validate(
                {
                    "description": "ZZT created with a type",
                    "access_levels": ["dealer"],
                    "promotion_type_id": str(special.id),
                }
            ),
            created_by=None,
        )

        assert created.promotion_type_id == str(special.id)
        assert created.promotion_type_source == "manual"
        assert created.promotion_type_code == "special"
        assert created.promotion_type_name == special.type_name


def test_deleting_a_type_clears_the_source_with_the_classification():
    """An unclassified promotion with `manual` left behind is invisible to both
    the re-send classifier and the UI's "from the file name" cue."""
    with blank_session() as db:
        created = _create(db)
        promo = Promotion(
            id=str(uuid.uuid4()),
            description="ZZT clearance promo",
            access_levels=["dealer"],
            promotion_type_id=created.id,
            promotion_type_source="manual",
        )
        db.add(promo)
        db.commit()

        result = _service(db).delete_promotion_type(created.id)

        assert result["promotions_unclassified"] == 1
        db.expire_all()
        row = db.query(Promotion).one()
        assert row.promotion_type_id is None
        assert row.promotion_type_source is None
