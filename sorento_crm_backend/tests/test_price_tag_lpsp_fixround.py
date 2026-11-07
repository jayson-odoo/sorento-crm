"""PRICETAG-LPSP fix round 1: revise keeps the line type, the prompt publish of ptag_0014,
the new slot bindings and the one-query combo match.

Reuses the revise harness of `test_portal_price_tag_revise.py` and the migration loader of
`test_migration_ptag_0014_lpsp.py`.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402,F401

from app.services.portal_revision_service import PortalRevisionService
from app.services.price_tag_request_service import PriceTagRequestService
from tests._pg_fixture import blank_session
from tests.test_migration_ptag_0014_lpsp import _load, _run
from tests.test_portal_price_tag_revise import (  # noqa: F401  (no_queue is an autouse fixture)
    _SORENTO_COMPANY_ID,
    _seed_contact,
    _seed_product,
    _seed_ptag_config,
    _seed_system_settings,
    _seed_token,
    no_queue,
)


@pytest.fixture
def db():
    with blank_session() as session:
        yield session


# --------------------------------------------------------------------------- S1: revise
def _sp_request(db):
    """A List-mode request holding one SP line with a typed price."""
    _seed_system_settings(db, cap=3)
    _seed_ptag_config(db, max_revisions=None)
    contact = _seed_contact(db)
    product_id = _seed_product(db)
    req = PriceTagRequestService.create_request(
        db,
        contact_id=contact.id,
        company_id=_SORENTO_COMPANY_ID,
        data={
            "debtor_name": "ZZT Dealer",
            "price_mode": "list",
            "lines": [
                {"line_type": "product", "product_id": product_id,
                 "price_type": "selling", "manual_sell_price": Decimal("599")}
            ],
        },
    )
    req.status = "proof_ready"
    req.portal_draft_at = None
    req.print_by = "office"
    req.revision_no = 0
    db.commit()
    return contact, product_id, req


def _revise(db, contact, req, products, expected=0):
    PortalRevisionService(db).revise(
        _seed_token(contact), "price_tag_request", str(req.id),
        {"debtor_name": "ZZT Dealer", "products": products}, "Changed", expected,
    )
    db.expire_all()
    return PriceTagRequestService.get_request(db, str(req.id))


def test_a_revise_without_price_type_carries_the_stored_sp_line(db):
    contact, product_id, req = _sp_request(db)
    fresh = _revise(db, contact, req, [{"product_id": product_id, "quantity": 3}])
    (line,) = fresh.lines
    assert fresh.price_mode == "list"
    assert line.price_type == "selling"
    assert line.show_promo_price is True
    assert line.manual_sell_price == Decimal("599")


def test_a_revise_can_set_the_type_and_a_typed_price_on_a_line(db):
    contact, product_id, req = _sp_request(db)
    fresh = _revise(
        db, contact, req,
        [{"product_id": product_id, "quantity": 1, "price_type": "list", "manual_sell_price": None}],
    )
    assert fresh.lines[0].price_type == "list"
    assert fresh.lines[0].show_promo_price is False

    again = _revise(
        db, contact, fresh,
        [{"product_id": product_id, "quantity": 1, "price_type": "selling",
          "manual_sell_price": "480.00"}],
        expected=1,
    )
    assert again.lines[0].price_type == "selling"
    assert again.lines[0].manual_sell_price == Decimal("480.00")
    assert again.lines[0].show_promo_price is True


def test_the_revision_history_snapshot_names_each_lines_type(db):
    from app.models.portal import PortalFormRevision

    contact, product_id, req = _sp_request(db)
    _revise(db, contact, req, [{"product_id": product_id, "quantity": 3}])
    rows = (
        db.query(PortalFormRevision)
        .filter(PortalFormRevision.source_entity_id == str(req.id))
        .order_by(PortalFormRevision.version_no.asc())
        .all()
    )
    assert [r.snapshot_json["products"][0]["price_type"] for r in rows] == ["selling", "selling"]


# --------------------------------------------------------------------------- S4: prompt publish
PROMPT_NAME = "ai_extract_portal_price_tag_request"


def _seed_version(db, version: int, template: str) -> str:
    version_id = str(uuid.uuid4())
    db.execute(
        text(
            "INSERT INTO ai_prompt_versions (id, name, version, type, template, variables) "
            "VALUES (:i, :n, :v, 'text', :t, '[]'::jsonb)"
        ),
        {"i": version_id, "n": PROMPT_NAME, "v": version, "t": template},
    )
    return version_id


def _seed_label(db, version_id: str) -> None:
    db.execute(
        text(
            "INSERT INTO ai_prompt_labels (id, name, label, version_id) "
            "VALUES (:i, :n, 'production', :v)"
        ),
        {"i": str(uuid.uuid4()), "n": PROMPT_NAME, "v": version_id},
    )


def _production(db):
    return db.execute(
        text(
            "SELECT v.template, v.version FROM ai_prompt_labels l "
            "JOIN ai_prompt_versions v ON v.id = l.version_id "
            "WHERE l.name = :n AND l.label = 'production'"
        ),
        {"n": PROMPT_NAME},
    ).one_or_none()


def _count(db) -> int:
    return db.execute(
        text("SELECT count(*) FROM ai_prompt_versions WHERE name = :n"), {"n": PROMPT_NAME}
    ).scalar()


def test_untouched_production_text_moves_to_the_new_version(db):
    module = _load()
    _seed_label(db, _seed_version(db, 1, module._PRE_LPSP_TEXT))
    _run(db, "upgrade")
    template, version = _production(db)
    assert version == 2
    assert template == module._LPSP_TEXT
    assert "(10)" in template and "set_codes" in template


def test_an_owner_edited_production_text_is_left_alone(db):
    _seed_label(db, _seed_version(db, 1, "The owner's own prompt."))
    _run(db, "upgrade")
    assert _production(db) == ("The owner's own prompt.", 1)
    assert _count(db) == 1


def test_no_production_label_is_a_no_op(db):
    _seed_version(db, 1, _load()._PRE_LPSP_TEXT)
    _run(db, "upgrade")
    assert _production(db) is None
    assert _count(db) == 1


def test_running_the_upgrade_twice_inserts_no_second_version(db):
    module = _load()
    _seed_label(db, _seed_version(db, 1, module._PRE_LPSP_TEXT))
    _run(db, "upgrade")
    _run(db, "upgrade")
    assert _count(db) == 2
    assert _production(db)[1] == 2


# --------------------------------------------------------------------------- S5: slot bindings
@pytest.mark.parametrize("binding", ["price", "price_label"])
def test_the_template_doc_accepts_the_price_slots(binding):
    from app.schemas.price_tag import TagTemplateDocModel

    doc = {
        "width_mm": 80,
        "height_mm": 50,
        "layers": [
            {
                "id": "l1", "type": "text", "x_mm": 0, "y_mm": 0, "width_mm": 20, "height_mm": 10,
                "rotation_deg": 0, "z_index": 0, "locked": False, "visible": True,
                "slot_binding": binding, "text_override": None,
                "props": {
                    "kind": "text", "text": "x", "fontFamily": "Jost", "fontSize": 10,
                    "fontWeight": 400, "color": "#000", "align": "left", "lineHeight": 1.2,
                    "letterSpacing": 0,
                },
            }
        ],
    }
    assert TagTemplateDocModel.model_validate(doc).layers[0].slot_binding == binding
