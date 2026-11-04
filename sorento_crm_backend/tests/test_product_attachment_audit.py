"""PRODUCT-ATTACH-AUDIT: who linked or unlinked a product's file, and who may.

Owner, 28 Oct 2026: a product's drawing link vanished and nobody could say who. The link
tables (``product_attachments``, ``certificate_products``) are opted out of the automatic
audit for volume (review B3), so a STAFF link / unlink writes one explicit row rooted on the
product instead, and the n8n intake stays silent. Plan:
``documentation/plans/products/PLAN-product-attach-audit-28oct.md``.

Reuses the certificate route fixture (a superadmin acting, a grantless user for denials).
"""
import uuid

import pytest

from app.models.audit import AuditLog
from app.models.certificate import CertificateProduct
from app.models.product import ProductAttachment
from tests.test_certificate_api import (  # noqa: F401  (env is a fixture)
    BASE as CERT_BASE,
    EXTERNAL,
    TODAY,
    _create,
    env,
)

from datetime import timedelta

LINKS = "/api/v1/master-data/product-attachments"
_EDIT = "master_data.product_attachments.edit"


# HOTFIX-ATTACH-AUDIT (3 Nov): the verb is LINK / UNLINK, but prod's audit_logs_action_check
# admits only CREATE / READ / UPDATE / DELETE / IMPORT / EVENT, so the row STORES CREATE / DELETE
# and names the verb in `event`.
_STORED = {"LINK": ("CREATE", "file_linked"), "UNLINK": ("DELETE", "file_unlinked")}


@pytest.fixture(autouse=True)
def _prod_audit_action_check(env):
    """Prod's `audit_logs_action_check`, read from the migration: the scratch schema is built
    from the models and has no such constraint, which is how 'LINK' shipped (a 500 on every
    staff link and unlink in prod, 3 Nov)."""
    from tests.support.cost_price_env import install_audit_action_check

    install_audit_action_check(env.db)


def _trail_rows(env, product_id, verb=None):
    verbs = [verb] if verb else list(_STORED)
    q = env.db.query(AuditLog).filter(
        AuditLog.root_entity_type == "product",
        AuditLog.root_entity_id == str(product_id),
        AuditLog.event.in_([_STORED[v][1] for v in verbs]),
    )
    rows = q.all()
    for row in rows:
        assert (row.action, row.event) in _STORED.values(), (row.action, row.event)
    return rows


def _drawing_link(env, name="drawing"):
    """A non-certificate file linked to a fresh product, the shape that vanished in prod."""
    drawing_type = env.attachment_type(is_certificate=False, name="Drawing")
    attachment = env.attachment(drawing_type, name)
    product = env.product("DRAW")
    link = ProductAttachment(
        id=str(uuid.uuid4()), product_id=product.id, attachment_id=attachment.id
    )
    env.db.add(link)
    env.db.commit()
    return product, attachment, drawing_type, link


def _grant_edit_only(env):
    """A non-admin user whose role holds the link edit slug and nothing else."""
    from app.models.user import (
        User,
        UserPermission,
        UserRole,
        UserRoleAssignment,
        UserRolePermission,
    )

    role_id, user_id, perm_id = (str(uuid.uuid4()) for _ in range(3))
    env.db.add(UserRole(id=role_id, slug=f"zzt_link_editor_{role_id[:8]}", name="ZZT link editor",
                        description="", is_protected=False, is_default=False))
    env.db.add(User(id=user_id, email=f"zzt-link-{role_id[:8]}@test.com", name="Link Editor",
                    status="ACTIVE"))
    env.db.add(UserPermission(id=perm_id, slug=_EDIT, name=_EDIT, description=""))
    env.db.flush()
    env.db.add(UserRoleAssignment(user_id=user_id, role_id=role_id))
    env.db.add(UserRolePermission(id=str(uuid.uuid4()), role_id=role_id, permission_id=perm_id))
    env.db.commit()
    env._acting["user"] = {"id": user_id, "email": "editor@test.com"}
    return user_id


# ------------------------------------------------------------------ permission
def test_delete_without_the_edit_slug_is_403_and_the_link_survives(env):
    _product, _attachment, _type, link = _drawing_link(env)
    env.act_as_plain_user()

    response = env.client.delete(f"{LINKS}/{link.id}")

    assert response.status_code == 403, response.text
    assert env.db.query(ProductAttachment).filter(ProductAttachment.id == link.id).count() == 1


def test_create_and_update_without_the_edit_slug_are_403(env):
    product, attachment, _type, link = _drawing_link(env)
    other = env.attachment(_type, "other")
    env.act_as_plain_user()

    created = env.client.post(
        f"{LINKS}/", json={"product_id": str(product.id), "attachment_id": str(other.id)}
    )
    updated = env.client.put(f"{LINKS}/{link.id}", json={"sort_order": 7})

    assert created.status_code == 403, created.text
    assert updated.status_code == 403, updated.text


def test_a_non_admin_holding_the_edit_slug_can_still_delete(env):
    _product, _attachment, _type, link = _drawing_link(env)
    _grant_edit_only(env)

    response = env.client.delete(f"{LINKS}/{link.id}")

    assert response.status_code == 200, response.text
    assert env.db.query(ProductAttachment).filter(ProductAttachment.id == link.id).count() == 0


# ----------------------------------------------------------------------- audit
def test_unlink_writes_one_row_on_the_products_trail_naming_file_and_type(env):
    product, attachment, drawing_type, link = _drawing_link(env)
    user_id = _grant_edit_only(env)

    assert env.client.delete(f"{LINKS}/{link.id}").status_code == 200

    rows = _trail_rows(env, product.id)
    assert len(rows) == 1
    row = rows[0]
    assert (row.action, row.event) == ("DELETE", "file_unlinked")
    assert row.entity_type == "product_attachments"
    assert str(row.entity_id) == str(link.id)
    assert str(row.user_id) == user_id
    assert row.old_values["attachment_id"] == str(attachment.id)
    assert row.old_values["original_filename"] == attachment.original_filename
    assert row.old_values["attachment_type"] == drawing_type.type_name
    assert row.description == (
        f"File unlinked: {attachment.original_filename} ({drawing_type.type_name})"
    )


def test_link_writes_one_link_row(env):
    product, _attachment, drawing_type, _link = _drawing_link(env)
    second = env.attachment(drawing_type, "second")

    response = env.client.post(
        f"{LINKS}/", json={"product_id": str(product.id), "attachment_id": str(second.id)}
    )

    assert response.status_code == 201, response.text
    rows = _trail_rows(env, product.id, "LINK")
    assert len(rows) == 1
    assert (rows[0].action, rows[0].event) == ("CREATE", "file_linked")
    assert rows[0].new_values["attachment_id"] == str(second.id)
    assert rows[0].description == (
        f"File linked: {second.original_filename} ({drawing_type.type_name})"
    )


def test_relinking_a_file_already_linked_writes_no_link_row(env):
    """The POST is idempotent (TCK-2026-000020): a refresh is not a new link."""
    product, attachment, _type, _link = _drawing_link(env)

    response = env.client.post(
        f"{LINKS}/", json={"product_id": str(product.id), "attachment_id": str(attachment.id)}
    )

    assert response.status_code == 201, response.text
    assert _trail_rows(env, product.id) == []


def test_the_product_audit_trail_endpoint_shows_the_unlink_in_words(env):
    product, attachment, drawing_type, link = _drawing_link(env)
    assert env.client.delete(f"{LINKS}/{link.id}").status_code == 200

    response = env.client.get(
        "/api/v1/audit/logs/",
        params={"entity_type": "product", "entity_id": str(product.id), "include_children": "true"},
    )

    assert response.status_code == 200, response.text
    rows = [r for r in response.json()["data"] if r.get("event") == "file_unlinked"]
    assert [r["action"] for r in rows] == ["DELETE"]
    assert [r["description"] for r in rows] == [
        f"File unlinked: {attachment.original_filename} ({drawing_type.type_name})"
    ]
    assert rows[0]["actor_label"]


def test_removing_certificate_coverage_writes_an_unlink_row(env):
    cert_type = env.attachment_type(is_certificate=True, name="Certification")
    attachment = env.attachment(cert_type, "cov")
    product = env.product("COVAUD")
    created = _create(
        env,
        certificate_number="AUDIT COV 1",
        attachment_id=str(attachment.id),
        valid_until=(TODAY + timedelta(days=400)).isoformat(),
    )
    added = env.client.post(
        f"{CERT_BASE}/{created['id']}/products", json={"product_id": str(product.id)}
    )
    assert added.status_code == 201, added.text
    coverage = added.json()["products"][0]
    assert len(_trail_rows(env, product.id, "LINK")) == 1

    removed = env.client.delete(f"{CERT_BASE}/{created['id']}/products/{coverage['id']}")

    assert removed.status_code == 200, removed.text
    assert env.db.query(CertificateProduct).filter(CertificateProduct.id == coverage["id"]).count() == 0
    rows = _trail_rows(env, product.id, "UNLINK")
    assert len(rows) == 1
    assert rows[0].entity_type == "certificate_products"
    assert rows[0].old_values["certificate_number"] == "AUDIT COV 1"
    assert rows[0].old_values["attachment_id"] == str(attachment.id)
    assert rows[0].description == (
        f"File unlinked: {attachment.original_filename} ({cert_type.type_name})"
    )


def test_unlinking_a_certificate_file_from_the_product_writes_one_row_not_two(env):
    """The product's own unlink of a cert file uncovers it (product_service): one row."""
    cert_type = env.attachment_type(is_certificate=True, name="Certification")
    attachment = env.attachment(cert_type, "covtwo")
    product = env.product("COVTWO")
    created = _create(
        env,
        certificate_number="AUDIT COV 2",
        attachment_id=str(attachment.id),
        valid_until=(TODAY + timedelta(days=400)).isoformat(),
    )
    env.client.post(f"{CERT_BASE}/{created['id']}/products", json={"product_id": str(product.id)})
    link = env.projection(attachment.id)[0]

    assert env.client.delete(f"{LINKS}/{link.id}").status_code == 200

    assert len(_trail_rows(env, product.id, "UNLINK")) == 1


def test_the_n8n_intake_link_stays_unaudited(env):
    """Review B3: the integration paths are the volume; they keep writing nothing."""
    drawing_type = env.attachment_type(is_certificate=False, name="Drawing")
    attachment = env.attachment(drawing_type, "intake")
    product = env.product("INTAKE")

    response = env.client.post(
        EXTERNAL, json={"attachment_id": str(attachment.id), "products": [product.product_code]}
    )

    assert response.status_code == 200, response.text
    assert env.projection(attachment.id)
    assert _trail_rows(env, product.id) == []


def test_covering_a_second_product_leaves_the_first_products_trail_alone(env):
    """Only the NEW coverage row is a link: covering B must not re-log A."""
    cert_type = env.attachment_type(is_certificate=True, name="Certification")
    attachment = env.attachment(cert_type, "covab")
    first, second = env.product("COVA"), env.product("COVB")
    created = _create(
        env,
        certificate_number="AUDIT COV 3",
        attachment_id=str(attachment.id),
        valid_until=(TODAY + timedelta(days=400)).isoformat(),
    )
    for product in (first, second):
        added = env.client.post(
            f"{CERT_BASE}/{created['id']}/products", json={"product_id": str(product.id)}
        )
        assert added.status_code == 201, added.text

    assert len(_trail_rows(env, first.id, "LINK")) == 1
    assert len(_trail_rows(env, second.id, "LINK")) == 1


def test_the_activity_timeline_reads_an_unlink_as_removed_without_id_chips(env):
    """LINK / UNLINK carry only ids and names; diffed as an update they would print UUIDs."""
    _product, attachment, drawing_type, link = _drawing_link(env)
    assert env.client.delete(f"{LINKS}/{link.id}").status_code == 200

    response = env.client.get(
        "/api/v1/audit/activity",
        params={"entity_type": "product_attachments", "action": "deleted"},
    )

    assert response.status_code == 200, response.text
    items = [i for i in response.json()["items"] if i["entity_id"] == str(link.id)]
    assert len(items) == 1
    assert items[0]["action"] == "deleted"
    assert items[0]["changes"] == []
    assert items[0]["summary"] == (
        f"File unlinked: {attachment.original_filename} ({drawing_type.type_name})"
    )


# ------------------------------------------------- HOTFIX-ATTACH-AUDIT (3 Nov, prod 500)
def test_link_and_its_audit_row_commit_together(env, monkeypatch):
    """A failed audit write must not leave a committed link behind a 500 (the prod half state:
    the service committed the link, then the audit insert hit the CHECK)."""
    from app.services import product_link_audit

    product, _attachment, drawing_type, _link = _drawing_link(env)
    second = env.attachment(drawing_type, "halfstate")

    def _boom(*args, **kwargs):
        raise RuntimeError("audit write failed")

    monkeypatch.setattr(product_link_audit, "log_product_file_link", _boom)
    response = env.client.post(
        f"{LINKS}/", json={"product_id": str(product.id), "attachment_id": str(second.id)}
    )

    assert response.status_code == 500
    env.db.rollback()
    assert (
        env.db.query(ProductAttachment)
        .filter(
            ProductAttachment.product_id == product.id,
            ProductAttachment.attachment_id == second.id,
        )
        .count()
        == 0
    )


def test_every_stored_link_action_is_one_prod_admits():
    """Guard: the actions this helper stores, against the migration's constraint list."""
    import re

    from app.services import product_link_audit
    from tests.support.cost_price_env import admitted_audit_actions

    allowed = set(re.findall(r"'([A-Z_]+)'", admitted_audit_actions()))
    assert set(product_link_audit.STORED_ACTION.values()) <= allowed
