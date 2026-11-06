"""SPEC-ICON-PICKER-UX add-on (owner, PROD 6 Nov): Icon order = 1 on Spout was refused with
"Products are still being updated from another change" while another spec's re-read held the
one catalogue-read slot.

Icon order and value icons only decide how a price tag draws a spec, never what a product reads,
so a save that changes only them must neither take the slot nor wait on it - even when the client
also sends the rules, scope, cap and taken-away choices unchanged (the record page sends every
field). A save that really changes how products read still takes it, and a refusal names what is
running instead of a vague retry. The registry list is revalidated on every read, so a refetch
right after a save cannot bring back the old icon order from the browser's cache.
"""

from __future__ import annotations

import uuid

from sqlalchemy import text

from app.models.product_spec import ProductSpecRegistry
from tests.test_product_spec_fix_round2 import BASE, BUSY, api  # noqa: F401 - the fixture

RULE = {"builder": {"kind": "words", "words": ["MIXER"], "value": "mixer"}}


def _key(db, **fields) -> ProductSpecRegistry:
    row = ProductSpecRegistry(
        id=str(uuid.uuid4()),
        spec_key=f"zzd_{uuid.uuid4().hex[:8]}",
        label="Spout",
        data_type="enum",
        allowed_values=["mixer", "cold_only"],
        source="user",
        **fields,
    )
    db.add(row)
    db.commit()
    return row


class _OtherProcessRead:
    """Another API worker in the middle of a catalogue read: the advisory half of the slot."""

    def __init__(self, db):
        from app.database import engine
        from app.services.product_spec_preview import catalogue_read_lock_key

        self.key = catalogue_read_lock_key(db)
        self.connection = engine.connect()

    def __enter__(self):
        assert self.connection.execute(
            text("SELECT pg_try_advisory_lock(:k)"), {"k": self.key}
        ).scalar()
        return self

    def __exit__(self, *exc):
        self.connection.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": self.key})
        self.connection.close()


def _record_page_body(row, **changes) -> dict:
    """What `buildPatchBody` sends: every field, the reading ones unchanged."""
    body = {
        "label": row.label,
        "is_active": True,
        "max_value": None,
        "suppressed_values": [],
        "derivation_rules": [RULE],
        "value_labels": {},
        "icon_order": None,
    }
    body.update(changes)
    return body


def test_icon_order_alone_saves_while_another_read_holds_the_slot(api):
    client, db = api
    row = _key(db)
    with _OtherProcessRead(db):
        response = client.patch(f"{BASE}/{row.spec_key}", json={"icon_order": 1})
    assert response.status_code == 200, response.text
    assert response.json()["icon_order"] == 1
    assert response.json()["products_updated"] == 0


def test_icon_order_saves_with_the_unchanged_reading_fields_the_record_page_sends(api):
    client, db = api
    row = _key(db, derivation_rules=[RULE])
    with _OtherProcessRead(db):
        response = client.patch(
            f"{BASE}/{row.spec_key}", json=_record_page_body(row, icon_order=1, value_icons={})
        )
    assert response.status_code == 200, response.text
    assert response.json()["icon_order"] == 1


def test_a_save_that_changes_the_rules_still_waits_its_turn_and_stores_nothing(api):
    client, db = api
    row = _key(db, derivation_rules=[RULE])
    with _OtherProcessRead(db):
        response = client.patch(
            f"{BASE}/{row.spec_key}",
            json=_record_page_body(
                row,
                icon_order=4,
                derivation_rules=[{"builder": {"kind": "words", "words": ["COLD"], "value": "cold_only"}}],
            ),
        )
    assert response.status_code == 409, response.text
    assert response.json()["code"] == "spec_catalogue_read_running"
    db.rollback()
    db.expire_all()
    stored = db.query(ProductSpecRegistry).filter_by(spec_key=row.spec_key).one()
    assert stored.icon_order is None
    assert stored.derivation_rules == [RULE]


def test_the_refusal_names_the_change_that_is_running(api):
    from app.services import product_spec_preview
    from tests._pg_fixture import blank_session

    client, db = api
    row = _key(db, derivation_rules=[RULE])
    with blank_session() as other:
        token = product_spec_preview.begin_catalogue_read(other, label="Water supply")
        try:
            response = client.patch(
                f"{BASE}/{row.spec_key}",
                json={"derivation_rules": [{"builder": {"kind": "words", "words": ["COLD"], "value": "cold_only"}}]},
            )
        finally:
            product_spec_preview.end_catalogue_read(token)
    assert response.status_code == 409, response.text
    message = response.json()["message"]
    assert message != BUSY
    assert "Water supply" in message
    assert "started" in message


def test_the_label_does_not_outlive_the_read_on_a_pooled_connection():
    """The holder's connection goes back to the pool: it must not keep naming a finished read."""
    from app.services import product_spec_preview
    from tests._pg_fixture import blank_session

    with blank_session() as db:
        token = product_spec_preview.begin_catalogue_read(db, label="Water supply")
        product_spec_preview.end_catalogue_read(token)
        assert product_spec_preview.running_catalogue_read(db) is None


def test_the_registry_list_is_revalidated_on_every_read(api):
    client, db = api
    _key(db)
    response = client.get(BASE)
    assert response.status_code == 200, response.text
    cache = response.headers.get("cache-control", "")
    assert "max-age=60" not in cache
    assert "no-cache" in cache
    assert response.headers.get("etag")
