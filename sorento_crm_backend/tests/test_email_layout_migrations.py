"""eml_0002_seed_layouts (#1349 AC-EM095/096/097, AC-EM050..055): the seeded automation
templates move onto block documents only while their body is still the seeded one, the
system mail codes are inserted when absent, downgrade undoes exactly that.

Replays the real seed chain (212 -> soatt_0001) on a blank scratch schema first, so the
sha256 guard is checked against the body a real database carries, not a fixture copy.
"""
from __future__ import annotations

import hashlib
import re

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory

from app.services.email_layout import has_layout
from tests._pg_fixture import blank_session

SEED_CHAIN = (
    "212_seed_pr_sponsorship_approved_automation",
    "oihe_0001_seed_handover",
    "undo_0002_seed_undone",
    "oihr_0001_handover_r2_layout",
    "oihr_0002_undone_headline",
    "oirs_0001_reserve_requests",
    "oirs_0003_reserve_commit_tmpl",
    "oihr_0003_location_column",
    "soatt_0001_so_line_attachments",
)
SEEDED_CODES = (
    "purchase_request_approved" + "_default",
    "sponsorship_form_approved" + "_default",
    "order_inquiry_handover" + "_default",
    "order_inquiry_undone" + "_default",
    "order_inquiry_reserve_requested" + "_default",
    "order_inquiry_reserved" + "_default",
)


def _scripts():
    sd = ScriptDirectory.from_config(Config("alembic.ini"))
    return {r.revision: r.module for r in sd.walk_revisions()}


def _run(module, db, direction="upgrade"):
    ctx = MigrationContext.configure(db.connection())
    with Operations.context(ctx):
        getattr(module, direction)()


def _seed(db):
    # The blank schema is built from the models, whose NOT NULL columns added after 212
    # carry Python defaults, not server defaults; 212's raw INSERT predates them. Relax
    # them in this scratch transaction only (it is rolled back) so the real chain runs.
    for (col,) in db.execute(
        sa.text(
            "SELECT column_name FROM information_schema.columns WHERE table_schema = current_schema() "
            "AND table_name = 'automations' AND is_nullable = 'NO' AND column_default IS NULL AND column_name <> 'id'"
        )
    ).all():
        db.execute(sa.text(f'ALTER TABLE automations ALTER COLUMN "{col}" DROP NOT NULL'))
    mods = _scripts()
    for rev in SEED_CHAIN:
        _run(mods[rev], db)
    return mods


def _row(db, code):
    return db.execute(
        sa.text("SELECT body_html, body_text, layout_json, preheader FROM email_templates WHERE code = :c"),
        {"c": code},
    ).first()


def test_head_chain():  # AC-EM097
    mods = _scripts()
    assert mods["eml_0002_seed_layouts"].down_revision == "eml_0001_layout_columns"
    sd = ScriptDirectory.from_config(Config("alembic.ini"))
    # The root's parent is whatever main's head was at the last re-parent
    # (scripts/alembic-reparent.sh), so it is checked as "a real revision that
    # is not ours", never by name: a pinned name goes red on every main merge.
    parent = mods["eml_0001_layout_columns"].down_revision
    assert isinstance(parent, str) and not parent.startswith("eml_")
    assert sd.get_revision(parent) is not None
    # One head, with this chain in its history: a later lane's migration may sit on top
    # (#1356 chains ac_grn_do_0001_ingest onto eml_0002), so the head is not pinned by name.
    heads = sd.get_heads()
    assert len(heads) == 1
    assert "eml_0002_seed_layouts" in {r.revision for r in sd.iterate_revisions(heads[0], "base")}
    for rev in ("eml_0001_layout_columns", "eml_0002_seed_layouts"):
        assert len(rev) <= 32


def test_seeded_templates_converted_bodies_untouched():  # AC-EM095
    with blank_session() as db:
        mods = _seed(db)
        before = {c: _row(db, c) for c in SEEDED_CODES}
        _run(mods["eml_0002_seed_layouts"], db)
        for code in SEEDED_CODES:
            after = _row(db, code)
            assert after[0] == before[code][0], f"{code}: body_html must not change"
            assert after[1] == before[code][1], f"{code}: body_text must not change"
            types = [b["type"] for b in after[2]["blocks"]]
            assert types[0] == "brand_header" and types[-1] == "footer"
            assert "button" in types and "heading" in types, (code, types)


def test_admin_edited_template_left_alone():  # AC-EM095
    code = "order_inquiry_handover" + "_default"
    with blank_session() as db:
        mods = _seed(db)
        db.execute(sa.text("UPDATE email_templates SET body_html = body_html || '<p>admin</p>' WHERE code = :c"), {"c": code})
        _run(mods["eml_0002_seed_layouts"], db)
        assert _row(db, code)[2] is None
        # the others still convert
        assert _row(db, "order_inquiry_undone" + "_default")[2] is not None


MAY_CODES = {
    "purchase_request_approved" + "_default": "44f044773f5b20a779df2ce167088faa3998dc4d9c1aa1cd44b69365360e48b7",
    "sponsorship_form_approved" + "_default": "1c64e75361503768cf62a4fc498b1983b5cc6a2a47b4c2b8b481e815e37d8242",
}


def _to_may_body(db):
    """Rewrite the two purchase request bodies to what 212 wrote in May 2026 (long dashes)."""
    for code, want in MAY_CODES.items():
        body = _row(db, code)[0].replace("or '-'", "or '\u2014'")
        assert hashlib.sha256(body.encode("utf-8")).hexdigest() == want, f"{code}: fixture is not the production body"
        db.execute(sa.text("UPDATE email_templates SET body_html = :b WHERE code = :c"), {"b": body, "c": code})


def test_may_seeded_long_dash_bodies_are_converted():  # AC-EM095
    with blank_session() as db:
        mods = _seed(db)
        _to_may_body(db)
        before = {c: _row(db, c) for c in MAY_CODES}
        _run(mods["eml_0002_seed_layouts"], db)
        for code in MAY_CODES:
            after = _row(db, code)
            assert after[2] is not None and after[3], code
            assert after[0] == before[code][0] and after[1] == before[code][1], f"{code}: body must not change"


def test_long_dash_body_with_an_admin_edit_is_left_alone():  # AC-EM095
    with blank_session() as db:
        mods = _seed(db)
        _to_may_body(db)
        db.execute(sa.text("UPDATE email_templates SET body_html = body_html || 'x' WHERE code = ANY(:c)"), {"c": list(MAY_CODES)})
        _run(mods["eml_0002_seed_layouts"], db)
        for code in MAY_CODES:
            assert _row(db, code)[2] is None, code


def test_downgrade_after_may_body_conversion_leaves_body():  # AC-EM095
    with blank_session() as db:
        mods = _seed(db)
        _to_may_body(db)
        before = {c: _row(db, c) for c in MAY_CODES}
        mig = mods["eml_0002_seed_layouts"]
        _run(mig, db)
        assert all(_row(db, c)[2] is not None for c in MAY_CODES), "upgrade must convert both rows first"
        _run(mig, db, "downgrade")
        for code in MAY_CODES:
            after = _row(db, code)
            assert after[2] is None and after[3] is None, code
            assert after[0] == before[code][0], code


def test_system_codes_inserted_once_and_never_overwrite():  # AC-EM096
    mig = _scripts()["eml_0002_seed_layouts"]
    with blank_session() as db:
        mods = _seed(db)
        db.execute(
            sa.text(
                "INSERT INTO email_templates (id, code, name, subject, body_html, is_active, created_at, updated_at) "
                "VALUES (gen_random_uuid(), 'account_email_changed', 'Mine', 'Admin subject', '<p>x</p>', true, now(), now())"
            )
        )
        _run(mods["eml_0002_seed_layouts"], db)
        _run(mods["eml_0002_seed_layouts"], db)  # idempotent
        for code in mig.SYSTEM:
            n = db.execute(sa.text("SELECT count(*) FROM email_templates WHERE code = :c"), {"c": code}).scalar()
            assert n == 1, code
        assert db.execute(sa.text("SELECT subject FROM email_templates WHERE code = 'account_email_changed'")).scalar() == "Admin subject"
        assert _row(db, "auth_password_reset") is None  # credential mail: no editable row
        inv = _row(db, "complaint_created")
        assert inv[2]["blocks"][0]["type"] == "brand_header"


def test_frozen_documents_match_registry():
    """The migration carries a frozen copy; at this revision it equals the registry."""
    from app.services.email_system_templates import CREDENTIAL_CODES, SYSTEM_TEMPLATES

    mig = _scripts()["eml_0002_seed_layouts"]
    # credential mails are never seeded as editable rows (PLAN D11)
    assert set(mig.SYSTEM) == set(SYSTEM_TEMPLATES) - CREDENTIAL_CODES
    for code, t in SYSTEM_TEMPLATES.items():
        if code in CREDENTIAL_CODES:
            continue
        assert mig.SYSTEM[code]["layout"] == t.document(), code
        assert mig.SYSTEM[code]["subject"] == t.subject, code


def test_downgrade_restores_prior_state():
    with blank_session() as db:
        mods = _seed(db)
        mig = mods["eml_0002_seed_layouts"]
        _run(mig, db)
        _run(mig, db, "downgrade")
        for code in SEEDED_CODES:
            assert _row(db, code)[2] is None and _row(db, code)[3] is None
        for code in mig.SYSTEM:
            assert _row(db, code) is None


def test_converted_handover_renders_heading_tables_and_button():  # AC-EM052
    from app.models.email_template import EmailTemplate
    from app.services.email_template_service import EmailTemplateService

    code = "order_inquiry_handover" + "_default"
    with blank_session() as db:
        mods = _seed(db)
        _run(mods["eml_0002_seed_layouts"], db)
        template = db.query(EmailTemplate).filter(EmailTemplate.code == code).one()
        ctx = {
            "handover": {
                "headline": "ORDER, AMEND",
                "subject_scope": "SO1",
                "link": "https://crm.example.com/scm/order-inquiries/1",
                "orders": [{"so_number": "SO1", "customer": "ACME", "project": "P1"}],
                "lines": [{"so_date": "01/09/2026", "so_number": "SO1", "location": "KL", "item_code": "IT-1", "qty": "5", "was": {"qty": "3"}, "delivery_date": "02/09/2026", "remark": "R"}],
            },
            "actor": {"name": "Aina", "email": "aina@example.com"},
            "today": "28/09/2026",
        }
        out = EmailTemplateService(db).render(template, ctx)
        html = out["body_html"]
        assert has_layout(html)
        assert ">ORDER, AMEND</h1>" in html
        assert "QTY CHANGE TO" in html and "IT-1" in html
        assert 'class="em-btn-link" href="https://crm.example.com/scm/order-inquiries/1"' in html
        assert "Open in Order Inquiries" in html
        # the hand-tuned text part is kept verbatim
        assert "SO DATE | S/O NO" in out["body_text"]
        assert out["subject"] == "OI: SO1"


RESERVE_CODES = (
    "order_inquiry_reserve_requested" + "_default",
    "order_inquiry_reserved" + "_default",
)


def _converted_preview(db, code):
    from app.models.email_template import EmailTemplate
    from app.services.email_template_service import EmailTemplateService

    template = db.query(EmailTemplate).filter(EmailTemplate.code == code).one()
    assert template.layout_json is not None, code
    return EmailTemplateService(db).preview(str(template.id), None)


@pytest.mark.parametrize("code", RESERVE_CODES)
def test_reserve_preview_has_no_unknown_or_error(code):  # AC-EM004
    with blank_session() as db:
        mods = _seed(db)
        _run(mods["eml_0002_seed_layouts"], db)
        out = _converted_preview(db, code)
        for part in ("subject", "body_html", "body_text"):
            assert "[unknown:" not in out[part], (code, part)
            assert "[template-error" not in out[part], (code, part)


@pytest.mark.parametrize("code", RESERVE_CODES)
def test_reserve_preview_button_points_at_the_sample_link(code):  # AC-EM004
    with blank_session() as db:
        mods = _seed(db)
        _run(mods["eml_0002_seed_layouts"], db)
        html = _converted_preview(db, code)["body_html"]
        match = re.search(r'<a [^>]*href="(https://crm\.example\.com/[^"]+)"[^>]*>\s*Open in Order Inquiries', html)
        assert match, "button missing or without a sample link"
        assert "reserve=sample" in match.group(1)


@pytest.mark.parametrize("code", RESERVE_CODES)
def test_reserve_preview_shows_sample_values(code):  # AC-EM004
    with blank_session() as db:
        mods = _seed(db)
        _run(mods["eml_0002_seed_layouts"], db)
        out = _converted_preview(db, code)
        assert "OI-0755" in out["subject"] and "SO-26-0412" in out["subject"]
        assert "SRT-6060-GL" in out["body_html"] and "SRT-3030-MT" in out["body_html"]


def test_every_seeded_template_previews_without_unknown_placeholders():  # AC-EM004
    with blank_session() as db:
        mods = _seed(db)
        _run(mods["eml_0002_seed_layouts"], db)
        for code in SEEDED_CODES:
            out = _converted_preview(db, code)
            for part in ("subject", "body_html", "body_text"):
                assert "[unknown:" not in out[part], (code, part)
