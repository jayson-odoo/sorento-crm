"""Deferred removes on a specification's page (#1286, D7 / D8 / D13; AC-S1.10, AC-S1.15).

Removing a rule, a choice or a word is a 5 s deferred action with Cancel, never a confirm
dialog. Three record actions carry them through `/api/v1/pending-actions`:
`spec_rule.remove`, `spec_value.remove` and `spec_word.remove`. One happy path each,
driven end to end (park, lapse, commit), and the permission slug each one is refused
without. The registration contract every record action honours (window, entity type,
lazy imports) is `tests/test_record_actions_s6b.py`, which runs over these too.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.product_spec import ProductSpecifications, ProductSpecRegistry
from app.models.sla import SlaFormAction
from app.models.user import User
from app.services import record_actions  # noqa: F401  (registers the record actions)
from app.services.form_action_registry import REGISTRY
from tests._pg_fixture import blank_session

BASE = "/api/v1/pending-actions"
EDIT = "master_data.spec_registry.edit"


def _uid() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def client(monkeypatch):
    from fastapi import Depends

    import app.services.product_spec_change_listener as listener
    from app.database import get_db
    from app.dependencies import get_current_user
    from app.models.base import set_company_scope
    from app.services.company_scope_resolver import apply_company_scope
    from app.services.user_service import UserPermissionService

    with blank_session() as db:

        def _override_get_db():
            yield db

        # A re-read opens its own session in production; here it runs on the test's.
        def _inline_in_this_session(codes):
            from app.services.product_spec_derivation import derive_for_code

            for code in codes:
                derive_for_code(db, code)

        monkeypatch.setattr(listener, "_rederive_inline", _inline_in_this_session)

        actor_row = User(id=_uid(), email=f"zzt-rules-{_uid()[:8]}@example.test", name="Ada")
        db.add(actor_row)
        db.commit()
        actor = {"id": actor_row.id, "email": actor_row.email, "name": actor_row.name}
        denied: set[str] = set()

        def _override_scope(_db=Depends(get_db)):
            set_company_scope(_db, None)
            return None

        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[apply_company_scope] = _override_scope
        app.dependency_overrides[get_current_user] = lambda: actor
        monkeypatch.setattr(
            UserPermissionService,
            "check_user_has_permission",
            lambda self, uid, slug: slug not in denied,
        )
        try:
            with TestClient(app) as c:
                yield c, db, denied
        finally:
            app.dependency_overrides.clear()


def _key(db, **fields) -> ProductSpecRegistry:
    row = ProductSpecRegistry(
        id=_uid(),
        spec_key=f"zzt_{_uid()[:8]}",
        label="ZZT colour",
        data_type="enum",
        source="user",
        **fields,
    )
    db.add(row)
    db.commit()
    return row


def _start(c, action_key: str, spec_key: str, payload: dict):
    return c.post(
        BASE,
        json={
            "action_key": action_key,
            "entity_type": "spec_key",
            "entity_id": spec_key,
            "payload": payload,
        },
    )


def _commit_now(c, db, spec_key: str, action_id: str) -> dict:
    db.query(SlaFormAction).filter(SlaFormAction.id == action_id).update(
        {"commit_at": datetime.utcnow() - timedelta(seconds=1)}, synchronize_session=False
    )
    db.commit()
    return c.get(
        f"{BASE}/current", params={"entity_type": "spec_key", "entity_id": spec_key}
    ).json()


def _row(db, spec_key: str) -> ProductSpecRegistry:
    db.expire_all()
    return db.query(ProductSpecRegistry).filter_by(spec_key=spec_key).one()


@pytest.mark.parametrize(
    "action_key,label",
    [
        ("spec_rule.remove", "Remove rule"),
        ("spec_value.remove", "Remove choice"),
        ("spec_word.remove", "Remove word"),
    ],
)
def test_ac_s1_10_the_removes_are_reversible_record_actions_on_the_registry_edit_grant(
    action_key, label
):
    from app.services.form_action_grace import WINDOW_REVERSIBLE

    action = REGISTRY[action_key]
    assert action.permission == EDIT
    assert action.window == WINDOW_REVERSIBLE
    assert action.label == label
    assert "spec_key" in action.entity_types


# --------------------------------------------------------------------------- #
# spec_rule.remove (AC-S1.10)
# --------------------------------------------------------------------------- #
def test_ac_s1_10_removing_a_rule_commits_and_rereads_the_products_it_changed(client):
    c, db, _denied = client
    cat = ProductCategory(id=_uid(), category_code=f"ZZT-{_uid()[:6]}", category_name="cat")
    uom = UnitOfMeasure(id=_uid(), uom_code=f"ZZT-{_uid()[:6]}", uom_name="uom")
    db.add_all([cat, uom])
    db.flush()
    keep = {"kind": "words", "words": ["ZZTKEEPWORD"], "value": "b"}
    gone = {"kind": "words", "words": ["ZZTGONEWORD"], "value": "a"}
    row = _key(
        db,
        allowed_values=["a", "b"],
        derivation_rules=[{"builder": gone}, {"builder": keep}],
    )
    code = f"ZZT-RM-{_uid()[:6]}"
    product = Product(
        id=_uid(),
        product_code=code,
        product_name=code,
        description="THIS SAYS ZZTGONEWORD",
        category_id=cat.id,
        base_uom_id=uom.id,
        list_price=Decimal("1.00"),
    )
    db.add(product)
    db.flush()
    from app.services.product_spec_derivation import derive_for_code

    derive_for_code(db, code)
    db.commit()
    spec = db.query(ProductSpecifications).filter_by(product_id=product.id).one()
    assert spec.values[row.spec_key]["value"] == "a"

    # Spelled the way the screen might, not the way it is stored: same rule.
    parked = _start(
        c,
        "spec_rule.remove",
        row.spec_key,
        {"builder": {"kind": "words", "words": ["zztgoneword"], "value": "a", "at_end": False}},
    )
    assert parked.status_code == 202, parked.text
    assert parked.json()["window_seconds"] == 5

    body = _commit_now(c, db, row.spec_key, parked.json()["id"])

    assert body["last_outcome"]["status"] == "committed", body["last_outcome"]
    assert _row(db, row.spec_key).derivation_rules == [{"builder": keep}]
    spec = db.query(ProductSpecifications).filter_by(product_id=product.id).one()
    assert row.spec_key not in (spec.values or {}), "the product it read is read again"


def test_ac_s1_10_removing_a_shipped_rule_writes_the_rest_of_the_shipped_list(client):
    from app.services.product_spec_registry import _rules_from_shipped_tables

    c, db, _denied = client
    row = ProductSpecRegistry(
        id=_uid(), spec_key="is_rimless", label="Rimless", data_type="boolean", source="seed"
    )
    db.add(row)
    db.commit()
    shipped = _rules_from_shipped_tables()["is_rimless"]

    parked = _start(c, "spec_rule.remove", "is_rimless", {"builder": shipped[0]["builder"]})
    body = _commit_now(c, db, "is_rimless", parked.json()["id"])

    assert body["last_outcome"]["status"] == "committed", body["last_outcome"]
    assert _row(db, "is_rimless").derivation_rules == []


def test_ac_s1_10_removing_a_rule_is_refused_without_the_registry_edit_grant(client):
    c, db, denied = client
    row = _key(
        db,
        allowed_values=["a"],
        derivation_rules=[{"builder": {"kind": "words", "words": ["X"], "value": "a"}}],
    )
    denied.add(EDIT)

    response = _start(
        c,
        "spec_rule.remove",
        row.spec_key,
        {"builder": {"kind": "words", "words": ["X"], "value": "a"}},
    )

    assert response.status_code == 403, response.text
    assert EDIT in response.json()["message"]
    assert db.query(SlaFormAction).count() == 0


# --------------------------------------------------------------------------- #
# spec_value.remove and spec_word.remove (AC-S1.15)
# --------------------------------------------------------------------------- #
def test_ac_s1_15_removing_an_added_choice_drops_it_with_its_words_and_label(client):
    c, db, _denied = client
    row = _key(
        db,
        allowed_values=["chrome"],
        synonyms={"chrome": ["chrome"]},
        user_values=["rose_gold"],
        user_synonyms={"rose_gold": ["rose gold"]},
        value_labels={"rose_gold": "Rose gold"},
    )

    parked = _start(c, "spec_value.remove", row.spec_key, {"value": "rose_gold"})
    body = _commit_now(c, db, row.spec_key, parked.json()["id"])

    assert body["last_outcome"]["status"] == "committed", body["last_outcome"]
    after = _row(db, row.spec_key)
    assert after.user_values == []
    assert "rose_gold" not in (after.user_synonyms or {})
    assert "rose_gold" not in (after.value_labels or {})


def test_ac_s1_15_removing_a_shipped_choice_suppresses_it(client):
    c, db, _denied = client
    row = _key(
        db, allowed_values=["chrome", "black"], synonyms={"chrome": ["chrome"], "black": ["black"]}
    )

    parked = _start(c, "spec_value.remove", row.spec_key, {"value": "black"})
    body = _commit_now(c, db, row.spec_key, parked.json()["id"])

    assert body["last_outcome"]["status"] == "committed", body["last_outcome"]
    after = _row(db, row.spec_key)
    assert after.allowed_values == ["chrome", "black"], "the shipped list is never edited"
    assert after.suppressed_values == ["black"]


def test_ac_s1_15_removing_a_choice_is_refused_without_the_registry_edit_grant(client):
    c, db, denied = client
    row = _key(db, allowed_values=["chrome"])
    denied.add(EDIT)

    response = _start(c, "spec_value.remove", row.spec_key, {"value": "chrome"})

    assert response.status_code == 403, response.text
    assert EDIT in response.json()["message"]


def test_ac_s1_15_removing_an_added_word_drops_it_and_a_shipped_word_is_suppressed(client):
    c, db, _denied = client
    row = _key(
        db,
        allowed_values=["chrome"],
        synonyms={"chrome": ["chrome", "polished chrome"], "_self": ["colour"]},
        user_synonyms={"chrome": ["shiny"], "_self": ["tone"]},
    )

    first = _start(c, "spec_word.remove", row.spec_key, {"value": "chrome", "word": "SHINY"})
    assert (
        _commit_now(c, db, row.spec_key, first.json()["id"])["last_outcome"]["status"]
        == "committed"
    )
    second = _start(c, "spec_word.remove", row.spec_key, {"value": "_self", "word": "colour"})
    assert (
        _commit_now(c, db, row.spec_key, second.json()["id"])["last_outcome"]["status"]
        == "committed"
    )

    after = _row(db, row.spec_key)
    assert after.user_synonyms == {"_self": ["tone"]}
    assert after.suppressed_synonyms == {"_self": ["colour"]}
    assert after.synonyms["_self"] == ["colour"], "the shipped words are never edited"


def test_ac_s1_15_removing_a_word_is_refused_without_the_registry_edit_grant(client):
    c, db, denied = client
    row = _key(db, allowed_values=["chrome"], user_synonyms={"chrome": ["shiny"]})
    denied.add(EDIT)

    response = _start(c, "spec_word.remove", row.spec_key, {"value": "chrome", "word": "shiny"})

    assert response.status_code == 403, response.text
    assert EDIT in response.json()["message"]
