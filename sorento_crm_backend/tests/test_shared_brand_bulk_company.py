"""Group B - `bulk-company` on files: the twin linker.

`documentation/plans/multi-company/shared-brand-attachments-acceptance-criteria.md`
AC-B1..B13. Postgres only via `tests/_pg_fixture.py::blank_session`, own seeded
`ZZT-` chain per test - CI's database is empty, nothing borrowed from an
existing row. Mocha is the real id from the plan
(`tests._shared_brand_seed.MOCHA_ID`).

Most of these exercise `AttachmentCompanyService.apply()` directly - that IS
the unit under test (R4/S2: the route and the deferred actions are both thin
wrappers over it). AC-B5/B6/B10/B12 need the HTTP layer (scope-visibility 404,
grant 403, the auth dependency, the pending-actions engine) and go through
`TestClient`.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

# MUST be the first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from app.api.v1.external.product_attachments import _link_attachment_to_products_bulk
from app.models.attachment_field_link import AttachmentFieldLink
from app.models.base import set_company_scope
from app.models.product import ProductAttachment
from app.models.resources import Attachment
from app.services.attachment_company_service import AttachmentCompanyService
from app.services.error_handler import AppException

from tests import _shared_brand_seed as seed
from tests._pg_fixture import blank_session

SORENTO = seed.SORENTO_ID
MOCHA = seed.MOCHA_ID


@pytest.fixture
def db():
    with blank_session() as session:
        seed.seed_mocha(session)
        yield session


def _twin(db, code: str = "ZZT-A"):
    cat_s = seed.category(db, company_id=SORENTO)
    uom_s = seed.uom(db, company_id=SORENTO)
    cat_m = seed.category(db, company_id=MOCHA)
    uom_m = seed.uom(db, company_id=MOCHA)
    return seed.twin_products(
        db, code=code, sorento_cat=cat_s.id, sorento_uom=uom_s.id, mocha_cat=cat_m.id, mocha_uom=uom_m.id
    )


def _sorento_only_product(db, code: str = "ZZT-SOLO"):
    cat = seed.category(db, company_id=SORENTO)
    u = seed.uom(db, company_id=SORENTO)
    return seed.product(db, company_id=SORENTO, code=code, category_id=cat.id, uom_id=u.id)


# --------------------------------------------------------------------------- #
# AC-B1 - share expands the link to the Mocha twin
# --------------------------------------------------------------------------- #


def test_ac_b1_share_expands_link_to_the_twin_and_nulls_company(db):
    s, m = _twin(db)
    t = seed.att_type(db)
    a = seed.attachment(db, company_id=SORENTO, type_id=t.id)
    seed.product_attachment(
        db, company_id=SORENTO, product_id=s.id, attachment_id=a.id,
        is_primary=True, sort_order=7, access_levels=["dealer", "end_user"],
    )
    db.commit()

    set_company_scope(db, frozenset({SORENTO, MOCHA}))
    result = AttachmentCompanyService(db).apply(attachment_ids=[a.id], company_id=None)

    assert result["links_added"] == 1
    assert result["links_removed"] == 0
    assert result["updated_attachments"] == 1
    assert result["company_id"] is None

    db.expire_all()
    updated = db.query(Attachment).filter(Attachment.id == a.id).first()
    assert updated.company_id is None, "the file must go NULL (shared)"

    twin_link = (
        db.query(ProductAttachment)
        .filter(ProductAttachment.product_id == m.id, ProductAttachment.attachment_id == a.id)
        .first()
    )
    assert twin_link is not None, "no product_attachments row was created for the Mocha twin"
    assert twin_link.company_id == MOCHA, "the twin link must be stamped to the TWIN's own company"
    assert twin_link.is_primary is True
    assert twin_link.sort_order == 7
    assert twin_link.access_levels == ["dealer", "end_user"]


# --------------------------------------------------------------------------- #
# AC-B2 - un-sharing to S removes the M link, keeps the S link
# --------------------------------------------------------------------------- #


def test_ac_b2_setting_shared_file_to_sorento_removes_the_mocha_link(db):
    s, m = _twin(db)
    t = seed.att_type(db)
    a = seed.attachment(db, company_id=None, type_id=t.id)
    seed.product_attachment(db, company_id=SORENTO, product_id=s.id, attachment_id=a.id)
    seed.product_attachment(db, company_id=MOCHA, product_id=m.id, attachment_id=a.id)
    db.commit()

    set_company_scope(db, frozenset({SORENTO, MOCHA}))
    result = AttachmentCompanyService(db).apply(attachment_ids=[a.id], company_id=SORENTO)

    assert result["links_removed"] == 1
    assert result["links_added"] == 0

    db.expire_all()
    links = db.query(ProductAttachment).filter(ProductAttachment.attachment_id == a.id).all()
    product_ids = {str(l.product_id) for l in links}
    assert product_ids == {str(s.id)}, "the Mocha link must be gone, the Sorento one must stay"
    updated = db.query(Attachment).filter(Attachment.id == a.id).first()
    assert updated.company_id == SORENTO


# --------------------------------------------------------------------------- #
# AC-B3 - S file moved to M points at the M twin only (both directions at once)
# --------------------------------------------------------------------------- #


def test_ac_b3_moving_an_sorento_file_to_mocha_points_at_the_mocha_twin(db):
    s, m = _twin(db)
    t = seed.att_type(db)
    a = seed.attachment(db, company_id=SORENTO, type_id=t.id)
    seed.product_attachment(db, company_id=SORENTO, product_id=s.id, attachment_id=a.id)
    actor = seed.user(db)
    seed.grant(db, user_id=actor.id, company_id=SORENTO)
    seed.grant(db, user_id=actor.id, company_id=MOCHA)
    db.commit()

    set_company_scope(db, frozenset({SORENTO, MOCHA}))
    result = AttachmentCompanyService(db).apply(
        attachment_ids=[a.id], company_id=MOCHA, actor_id=actor.id
    )

    assert result["links_added"] == 1
    assert result["links_removed"] == 1

    db.expire_all()
    links = db.query(ProductAttachment).filter(ProductAttachment.attachment_id == a.id).all()
    product_ids = {str(l.product_id) for l in links}
    assert product_ids == {str(m.id)}, "only the Mocha twin should be linked after the move"
    updated = db.query(Attachment).filter(Attachment.id == a.id).first()
    assert updated.company_id == MOCHA


# --------------------------------------------------------------------------- #
# AC-B4 - a code that exists in Sorento only: nothing to add, no error;
# moving it away removes the link and the call still succeeds.
# --------------------------------------------------------------------------- #


def test_ac_b4_single_company_code_shares_with_nothing_added(db):
    p = _sorento_only_product(db)
    t = seed.att_type(db)
    a = seed.attachment(db, company_id=SORENTO, type_id=t.id)
    seed.product_attachment(db, company_id=SORENTO, product_id=p.id, attachment_id=a.id)
    db.commit()

    set_company_scope(db, frozenset({SORENTO, MOCHA}))
    result = AttachmentCompanyService(db).apply(attachment_ids=[a.id], company_id=None)

    assert result["links_added"] == 0
    assert result["links_removed"] == 0
    db.expire_all()
    links = db.query(ProductAttachment).filter(ProductAttachment.attachment_id == a.id).all()
    assert len(links) == 1
    assert str(links[0].product_id) == str(p.id)


def test_ac_b4_single_company_code_moved_away_removes_the_link_without_error(db):
    p = _sorento_only_product(db)
    t = seed.att_type(db)
    a = seed.attachment(db, company_id=SORENTO, type_id=t.id)
    seed.product_attachment(db, company_id=SORENTO, product_id=p.id, attachment_id=a.id)
    db.commit()

    set_company_scope(db, frozenset({SORENTO, MOCHA}))
    result = AttachmentCompanyService(db).apply(attachment_ids=[a.id], company_id=MOCHA)

    assert result["links_removed"] == 1
    assert result["links_added"] == 0
    db.expire_all()
    links = db.query(ProductAttachment).filter(ProductAttachment.attachment_id == a.id).all()
    assert links == []


# --------------------------------------------------------------------------- #
# AC-B5 - an id outside the caller's scope is 404, and nothing changes
# --------------------------------------------------------------------------- #


def _scope_client(db, *, actor_id: str | None, scope):
    """Overrides `get_current_user` + `apply_company_scope` for one client.

    `get_current_user_or_api_key` also has to be overridden: the resources
    router carries `require_module_enabled_with_api_key("resources")`, which
    depends on it independently of the route's own `get_current_user` - the
    module guard runs FIRST, so without this the real dependency runs, sees no
    Authorization header on this bare TestClient request, and 401s before the
    route (or its own override) is ever reached.
    """
    from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
    from app.services.company_scope_resolver import apply_company_scope

    def _override_get_db():
        yield db

    def _override_current_user():
        return {"id": actor_id}

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = _override_current_user
    app.dependency_overrides[get_current_user_or_api_key] = _override_current_user
    app.dependency_overrides[apply_company_scope] = lambda: set_company_scope(db, scope)
    return TestClient(app)


_URL = "/api/v1/resource-management/attachments/bulk-company"


def test_ac_b5_id_outside_caller_scope_is_404_and_nothing_changes(db):
    a = seed.attachment(db, company_id=MOCHA, type_id=seed.att_type(db).id)
    actor = seed.user(db)
    seed.grant(db, user_id=actor.id, company_id=SORENTO)
    db.commit()

    c = _scope_client(db, actor_id=actor.id, scope=frozenset({SORENTO}))
    try:
        r = c.post(_URL, json={"attachment_ids": [a.id], "company_id": None})
    finally:
        app.dependency_overrides.clear()

    assert r.status_code == 404, r.text
    # Widen back to read the row: the request itself left `db`'s scope pinned
    # to Sorento-only (the override ran on this same session), which would
    # hide the Mocha row from this assertion too.
    set_company_scope(db, frozenset({SORENTO, MOCHA}))
    db.expire_all()
    unchanged = db.query(Attachment).filter(Attachment.id == a.id).first()
    assert unchanged.company_id == MOCHA, "a 404'd call must not have written anything"


# --------------------------------------------------------------------------- #
# AC-B6 - target company not granted to the caller -> 403
# --------------------------------------------------------------------------- #


def test_ac_b6_target_company_not_granted_is_403(db):
    a = seed.attachment(db, company_id=SORENTO, type_id=seed.att_type(db).id)
    actor = seed.user(db)
    seed.grant(db, user_id=actor.id, company_id=SORENTO)  # NOT granted Mocha
    db.commit()

    c = _scope_client(db, actor_id=actor.id, scope=frozenset({SORENTO}))
    try:
        r = c.post(_URL, json={"attachment_ids": [a.id], "company_id": MOCHA})
    finally:
        app.dependency_overrides.clear()

    assert r.status_code == 403, r.text
    db.expire_all()
    unchanged = db.query(Attachment).filter(Attachment.id == a.id).first()
    assert unchanged.company_id == SORENTO


# --------------------------------------------------------------------------- #
# AC-B7 - one transaction: a failure on the second id leaves the first alone
# --------------------------------------------------------------------------- #


def test_ac_b7_a_bad_second_id_leaves_the_first_unchanged(db):
    a = seed.attachment(db, company_id=SORENTO, type_id=seed.att_type(db).id)
    db.commit()

    set_company_scope(db, frozenset({SORENTO, MOCHA}))
    missing_id = str(uuid.uuid4())

    with pytest.raises(AppException) as exc_info:
        AttachmentCompanyService(db).apply(
            attachment_ids=[a.id, missing_id], company_id=None
        )
    assert exc_info.value.status_code == 404

    db.rollback()
    db.expire_all()
    unchanged = db.query(Attachment).filter(Attachment.id == a.id).first()
    assert unchanged.company_id == SORENTO, "the valid id must not have been touched"


# --------------------------------------------------------------------------- #
# AC-B8 - the n8n link-products path stamps each row from ITS OWN product's
# company, not the incumbent (DEFAULT_COMPANY_ID)
# --------------------------------------------------------------------------- #


def test_ac_b8_link_products_stamps_each_row_from_its_own_product(db):
    s, m = _twin(db)
    t = seed.att_type(db)
    a = seed.attachment(db, company_id=None, type_id=t.id)  # shared file
    actor = seed.user(db)
    db.commit()

    set_company_scope(db, None)  # all-companies, matches a contact-less X-API-Key call
    result = _link_attachment_to_products_bulk(
        db, a.id, ["ZZT-A"], {"id": actor.id}
    )

    assert result.skipped_product_codes == []
    assert len(result.linked) == 2, "both twins must be linked"

    db.expire_all()
    links = db.query(ProductAttachment).filter(ProductAttachment.attachment_id == a.id).all()
    by_product = {str(l.product_id): l for l in links}
    assert by_product[str(s.id)].company_id == SORENTO
    assert by_product[str(m.id)].company_id == MOCHA, (
        "the Mocha twin's link must be stamped MOCHA, not the incumbent "
        "(DEFAULT_COMPANY_ID) - the child-row-split gotcha this fixes"
    )


# --------------------------------------------------------------------------- #
# AC-B9 - the field-link template runs for the twin row too
# --------------------------------------------------------------------------- #


def test_ac_b9_field_link_template_applies_to_the_twin(db):
    s, m = _twin(db)
    t = seed.att_type(db)
    a = seed.attachment(
        db, company_id=SORENTO, type_id=t.id,
        target_entity_type="product", target_field_keys=["weight"],
    )
    seed.product_attachment(db, company_id=SORENTO, product_id=s.id, attachment_id=a.id)
    db.commit()

    set_company_scope(db, frozenset({SORENTO, MOCHA}))
    AttachmentCompanyService(db).apply(attachment_ids=[a.id], company_id=None)

    db.expire_all()
    link = (
        db.query(AttachmentFieldLink)
        .filter(
            AttachmentFieldLink.entity_type == "product",
            AttachmentFieldLink.entity_id == str(m.id),
            AttachmentFieldLink.attachment_id == a.id,
        )
        .all()
    )
    assert any(l.field_key == "weight" for l in link), (
        "apply_template_to_row did not run for the newly-linked Mocha twin"
    )


# --------------------------------------------------------------------------- #
# AC-B10 - same guard as PUT /attachments/{id}: unauthenticated -> 401/403
# --------------------------------------------------------------------------- #


def test_ac_b10_route_requires_auth_same_as_attachment_put():
    app.dependency_overrides.clear()
    with TestClient(app) as c:
        put_response = c.put("/api/v1/resource-management/attachments/" + str(uuid.uuid4()), json={})
        post_response = c.post(_URL, json={"attachment_ids": [str(uuid.uuid4())], "company_id": None})

    assert put_response.status_code in (401, 403), put_response.text
    assert post_response.status_code in (401, 403), post_response.text
    assert post_response.status_code == put_response.status_code, (
        "bulk-company must be guarded by the SAME dependency as PUT /attachments/{id}"
    )


# --------------------------------------------------------------------------- #
# AC-B11 - a Packing List file is accepted like any other (no type rejection)
# --------------------------------------------------------------------------- #


def test_ac_b11_packing_list_type_is_not_rejected(db):
    s, m = _twin(db)
    t = seed.att_type(db, name="ZZT Packing List")
    a = seed.attachment(db, company_id=SORENTO, type_id=t.id)
    seed.product_attachment(db, company_id=SORENTO, product_id=s.id, attachment_id=a.id)
    db.commit()

    set_company_scope(db, frozenset({SORENTO, MOCHA}))
    result = AttachmentCompanyService(db).apply(attachment_ids=[a.id], company_id=None)

    assert result["links_added"] == 1
    db.expire_all()
    updated = db.query(Attachment).filter(Attachment.id == a.id).first()
    assert updated.company_id is None


# --------------------------------------------------------------------------- #
# AC-B12 - the deferred action: park / lapse / cancel / RBAC through the
# generic engine (`/api/v1/pending-actions`)
# --------------------------------------------------------------------------- #


class TestDeferredSetCompany:
    BASE = "/api/v1/pending-actions"

    @pytest.fixture
    def action_client(self, db):
        from datetime import datetime, timedelta

        from app.dependencies import get_current_user, get_db
        from app.services.company_scope_resolver import apply_company_scope
        from app.models.sla import SlaFormAction

        actor = seed.user(db)
        seed.grant(db, user_id=actor.id, company_id=SORENTO)
        seed.grant(db, user_id=actor.id, company_id=MOCHA)
        db.commit()

        def _override_get_db():
            yield db

        def _override_current_user():
            return {"id": actor.id}

        def _override_scope():
            set_company_scope(db, frozenset({SORENTO, MOCHA}))

        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[get_current_user] = _override_current_user
        app.dependency_overrides[apply_company_scope] = _override_scope
        # Registers attachment.set_company / attachment_directory.set_company.
        from app.services import record_actions  # noqa: F401  (registers the actions)

        try:
            with TestClient(app) as c:
                yield c, db, actor
        finally:
            app.dependency_overrides.clear()

    @staticmethod
    def _lapse(db, action_id: str) -> None:
        from datetime import datetime, timedelta

        from app.models.sla import SlaFormAction

        db.query(SlaFormAction).filter(SlaFormAction.id == action_id).update(
            {"commit_at": datetime.utcnow() - timedelta(seconds=1)},
            synchronize_session=False,
        )
        db.commit()

    def test_lapsing_the_window_applies_the_same_result_as_ac_b1(self, action_client):
        c, db, actor = action_client
        s, m = _twin(db)
        t = seed.att_type(db)
        a = seed.attachment(db, company_id=SORENTO, type_id=t.id)
        seed.product_attachment(db, company_id=SORENTO, product_id=s.id, attachment_id=a.id)
        db.commit()

        parked = c.post(
            self.BASE,
            json={
                "action_key": "attachment.set_company",
                "entity_type": "attachment",
                "entity_id": a.id,
                "payload": {"company_id": None},
            },
        )
        assert parked.status_code == 202, parked.text

        # Nothing applied yet.
        db.expire_all()
        still = db.query(Attachment).filter(Attachment.id == a.id).first()
        assert still.company_id == SORENTO

        self._lapse(db, parked.json()["id"])
        current = c.get(
            f"{self.BASE}/current",
            params={"entity_type": "attachment", "entity_id": a.id},
        )
        body = current.json()
        assert body["last_outcome"]["status"] == "committed", body["last_outcome"]

        db.expire_all()
        committed = db.query(Attachment).filter(Attachment.id == a.id).first()
        assert committed.company_id is None
        twin_link = (
            db.query(ProductAttachment)
            .filter(ProductAttachment.product_id == m.id, ProductAttachment.attachment_id == a.id)
            .first()
        )
        assert twin_link is not None and twin_link.company_id == MOCHA

    def test_folder_set_company_lapses_through_the_directory_action(self, action_client):
        c, db, actor = action_client
        f = seed.folder(db, company_id=SORENTO)
        db.commit()

        parked = c.post(
            self.BASE,
            json={
                "action_key": "attachment_directory.set_company",
                "entity_type": "attachment_directory",
                "entity_id": f.id,
                "payload": {"company_id": None},
            },
        )
        assert parked.status_code == 202, parked.text
        self._lapse(db, parked.json()["id"])
        current = c.get(
            f"{self.BASE}/current",
            params={"entity_type": "attachment_directory", "entity_id": f.id},
        )
        assert current.json()["last_outcome"]["status"] == "committed"

        from app.models.resources import AttachmentDirectory

        db.expire_all()
        row = db.query(AttachmentDirectory).filter(AttachmentDirectory.id == f.id).first()
        assert row.company_id is None

    def test_cancel_inside_the_window_changes_nothing(self, action_client):
        c, db, actor = action_client
        a = seed.attachment(db, company_id=SORENTO, type_id=seed.att_type(db).id)
        db.commit()

        parked = c.post(
            self.BASE,
            json={
                "action_key": "attachment.set_company",
                "entity_type": "attachment",
                "entity_id": a.id,
                "payload": {"company_id": None},
            },
        )
        assert parked.status_code == 202, parked.text

        cancelled = c.post(f"{self.BASE}/{parked.json()['id']}/cancel")
        assert cancelled.status_code == 200, cancelled.text

        db.expire_all()
        untouched = db.query(Attachment).filter(Attachment.id == a.id).first()
        assert untouched.company_id == SORENTO

    def test_a_signed_out_caller_is_denied_by_the_engines_own_check(self, db):
        """OWN_RECORD's grant IS being signed in - `requested_by_id` empty is
        the one way this permission slug refuses a click."""
        from app.dependencies import get_current_user, get_db
        from app.services.company_scope_resolver import apply_company_scope

        a = seed.attachment(db, company_id=SORENTO, type_id=seed.att_type(db).id)
        db.commit()

        def _override_get_db():
            yield db

        app.dependency_overrides[get_db] = _override_get_db
        app.dependency_overrides[get_current_user] = lambda: {"id": None}
        app.dependency_overrides[apply_company_scope] = lambda: set_company_scope(
            db, frozenset({SORENTO})
        )
        from app.services import record_actions  # noqa: F401  (registers the actions)

        try:
            with TestClient(app) as c:
                r = c.post(
                    self.BASE,
                    json={
                        "action_key": "attachment.set_company",
                        "entity_type": "attachment",
                        "entity_id": a.id,
                        "payload": {"company_id": None},
                    },
                )
        finally:
            app.dependency_overrides.clear()

        assert r.status_code == 403, r.text
        db.expire_all()
        untouched = db.query(Attachment).filter(Attachment.id == a.id).first()
        assert untouched.company_id == SORENTO


# --------------------------------------------------------------------------- #
# AC-B13 - the linker is SET-BASED: one INSERT ... SELECT, one DELETE, for a
# call covering 500 seeded files - never one statement per file.
# --------------------------------------------------------------------------- #


def test_ac_b13_five_hundred_files_share_in_one_insert_and_one_delete(db):
    cat_s = seed.category(db, company_id=SORENTO)
    uom_s = seed.uom(db, company_id=SORENTO)
    cat_m = seed.category(db, company_id=MOCHA)
    uom_m = seed.uom(db, company_id=MOCHA)
    t = seed.att_type(db)

    attachment_ids: list[str] = []
    for i in range(500):
        code = f"ZZT-B13-{i:04d}"
        s, m = seed.twin_products(
            db, code=code, sorento_cat=cat_s.id, sorento_uom=uom_s.id,
            mocha_cat=cat_m.id, mocha_uom=uom_m.id,
        )
        a = seed.attachment(db, company_id=SORENTO, type_id=t.id)
        seed.product_attachment(db, company_id=SORENTO, product_id=s.id, attachment_id=a.id)
        attachment_ids.append(a.id)
    db.commit()

    statements: list[str] = []

    def _capture(conn, cursor, statement, *_a, **_kw):
        low = statement.lower()
        if "product_attachments" in low and ("insert into" in low or "delete from" in low):
            statements.append(low)

    connection = db.get_bind()
    event.listen(connection, "before_cursor_execute", _capture)
    try:
        set_company_scope(db, frozenset({SORENTO, MOCHA}))
        result = AttachmentCompanyService(db).apply(
            attachment_ids=attachment_ids, company_id=None
        )
    finally:
        event.remove(connection, "before_cursor_execute", _capture)

    assert result["links_added"] == 500
    inserts = [s for s in statements if "insert into" in s]
    deletes = [s for s in statements if "delete from" in s]
    assert len(inserts) == 1, f"expected ONE insert for 500 files, saw {len(inserts)}"
    assert len(deletes) == 1, f"expected ONE delete for 500 files, saw {len(deletes)}"
