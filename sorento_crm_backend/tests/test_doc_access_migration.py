"""DOC-ACCESS-SIMPLE S1: the `das_0001_ai_read_ticks` migration (DAS-BE-1, DAS-BE-2, DAS-BE-3).

The migration module is loaded from its file by path, and its `backfill(bind)` is called on the
test's own connection, so the carry-over test runs the SAME statement the migration runs. Every row
is seeded on the blank Postgres schema (CI's database is empty).
"""
from __future__ import annotations

import importlib.util
import json
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text

from tests._knowledge_seed import seed_access_codes, seed_attachment, seed_company, seed_type, SORENTO_COMPANY_ID
from tests._pg_fixture import blank_session
from tests.chatbot.agent._seed import seed_contact

BACKEND = Path(__file__).resolve().parents[1]
MIGRATION = BACKEND / "alembic" / "versions" / "das_0001_ai_read_ticks.py"


def _migration():
    assert MIGRATION.exists(), f"missing migration file {MIGRATION.name}"
    spec = importlib.util.spec_from_file_location("das_0001_ai_read_ticks", MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def db():
    with blank_session() as s:
        yield s


def _set_audience(db, att_type, audience):
    # Also reset to the fresh-column state, so only backfill() can produce the ticks.
    db.execute(
        text("UPDATE attachment_types SET ai_audience = :a, ai_read_staff = false, ai_read_codes = '[]'::jsonb WHERE id = :i"),
        {"a": audience, "i": str(att_type.id)},
    )


def _ticks(db, att_type):
    row = db.execute(
        text("SELECT ai_read_staff, ai_read_codes FROM attachment_types WHERE id = :i"), {"i": str(att_type.id)}
    ).one()
    return bool(row[0]), list(row[1])


# ---------------------------------------------------------------- DAS-BE-1


def test_migration_adds_ai_read_columns(db):
    from alembic.operations import Operations
    from alembic.runtime.migration import MigrationContext

    mod = _migration()
    assert mod.revision == "das_0001_ai_read_ticks"
    assert len(mod.revision) <= 32
    assert isinstance(mod.down_revision, str), "chains onto exactly one parent"

    # Drop the two columns the model already carries, then let the migration's own upgrade add them back.
    db.execute(text("ALTER TABLE attachment_types DROP COLUMN IF EXISTS ai_read_staff, DROP COLUMN IF EXISTS ai_read_codes"))
    conn = db.connection()
    with Operations.context(MigrationContext.configure(conn)):
        mod.upgrade()

    cols = {
        r[0]: r
        for r in db.execute(
            text(
                "SELECT column_name, data_type, is_nullable, column_default FROM information_schema.columns "
                "WHERE table_schema = current_schema() AND table_name = 'attachment_types' "
                "AND column_name IN ('ai_read_staff', 'ai_read_codes', 'ai_audience')"
            )
        ).all()
    }
    assert cols["ai_read_staff"][1:3] == ("boolean", "NO")
    assert "false" in cols["ai_read_staff"][3].lower()
    assert cols["ai_read_codes"][1:3] == ("jsonb", "NO")
    assert "'[]'" in cols["ai_read_codes"][3]
    assert "ai_audience" in cols, "ai_audience stays in the table, unread"


def test_migration_is_the_single_alembic_head():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    assert ScriptDirectory.from_config(cfg).get_heads() == ["das_0001_ai_read_ticks"]


# ---------------------------------------------------------------- DAS-BE-2


def test_backfill_maps_each_audience(db):
    # Sort order is deliberately not alphabetical; nl_dealer is inactive.
    seed_access_codes(db, ["sorento_dealer", "dealer", "end_user", "cabana_dealer"], inactive=["nl_dealer"])
    off, staff, dealer, public = (seed_type(db, audience="off") for _ in range(4))
    for t, a in ((off, "off"), (staff, "staff"), (dealer, "dealer"), (public, "public")):
        _set_audience(db, t, a)

    assert all(_ticks(db, t) == (False, []) for t in (off, staff, dealer, public))

    _migration().backfill(db.connection())

    assert _ticks(db, off) == (False, [])
    assert _ticks(db, staff) == (True, [])
    assert _ticks(db, dealer) == (True, ["sorento_dealer", "dealer", "cabana_dealer"])
    assert _ticks(db, public) == (True, ["sorento_dealer", "dealer", "end_user", "cabana_dealer"])


# ---------------------------------------------------------------- DAS-BE-3


def _link_contact(db, codes, companies):
    c = seed_contact(db)
    for code in codes:
        db.execute(text("INSERT INTO respond_contact_access_types (contact_id, access_type_code) VALUES (:c, :k)"), {"c": c["pk"], "k": code})
    for co in companies:
        db.execute(
            text("INSERT INTO respond_contact_companies (id, respond_contact_id, company_id) VALUES (:i, :c, :co)"),
            {"i": str(uuid.uuid4()), "c": c["pk"], "co": co},
        )
    db.flush()
    return c["pk"]


def test_carryover_reader_sets_unchanged(db):
    from app.models.base import company_scope
    from app.models.resources import Attachment, AttachmentType
    from app.services import knowledge_service as ks
    from app.services.chatbot.agent.access import _active_access_codes

    active = ["end_user", "dealer", "sorento_dealer", "mocha_dealer", "sorento_office"]
    seed_access_codes(db, active, inactive=["nl_dealer"])
    other = seed_company(db)

    levels_set = {
        "all": list(active),
        "brand_pair": ["sorento_dealer", "dealer"],
        "end_user_only": ["end_user"],
        "inactive_only": ["nl_dealer"],
    }
    companies = {"mine": SORENTO_COMPANY_ID, "other": other, "shared": None}
    types = {a: seed_type(db, audience=a) for a in ("off", "staff", "dealer", "public")}
    for a, t in types.items():
        _set_audience(db, t, a)
    for a, t in types.items():
        for lname, lv in levels_set.items():
            for cname, cid in companies.items():
                att = seed_attachment(db, t, f"{a}-{lname}-{cname}-{uuid.uuid4().hex[:6]}.pdf", company_id=cid)
                att.access_levels = list(lv)
                if cid is None:
                    att.company_id = None
    db.flush()

    contacts = {
        "several": _link_contact(db, ["dealer", "sorento_dealer", "end_user"], [SORENTO_COMPANY_ID]),
        "both_companies": _link_contact(db, ["mocha_dealer", "nl_dealer"], [SORENTO_COMPANY_ID, other]),
        "end_user_only": _link_contact(db, ["end_user"], [SORENTO_COMPANY_ID]),
        "office_only": _link_contact(db, ["sorento_office"], [other]),
        "no_code": _link_contact(db, [], [SORENTO_COMPANY_ID]),
        "no_company": _link_contact(db, ["dealer", "end_user"], []),
    }
    co_of = {
        pk: {str(r[0]) for r in db.execute(text("SELECT company_id FROM respond_contact_companies WHERE respond_contact_id = :c"), {"c": pk})}
        for pk in contacts.values()
    }
    codes_of = {pk: sorted(_active_access_codes(db, pk)) for pk in contacts.values()}
    assert "nl_dealer" not in codes_of[contacts["both_companies"]]

    def company_ok(pk, att_company):
        return bool(co_of[pk]) and (att_company is None or str(att_company) in co_of[pk])

    def old_pairs():
        out = set()
        for pk, codes in codes_of.items():
            if not codes:
                continue
            dealer_codes = [c for c in codes if c != "end_user"]
            rows = db.execute(
                text(
                    "SELECT a.id, a.company_id FROM attachments a JOIN attachment_types t ON t.id = a.attachment_type_id "
                    "WHERE a.is_deleted = false AND ("
                    "(t.ai_audience = 'public' AND jsonb_exists_any(a.access_levels, CAST(:codes AS text[]))) OR "
                    "(t.ai_audience = 'dealer' AND jsonb_exists_any(a.access_levels, CAST(:dealer AS text[]))))"
                ),
                {"codes": codes, "dealer": dealer_codes},
            ).all()
            out |= {(pk, str(r[0])) for r in rows if company_ok(pk, r[1])}
        return out

    def new_pairs():
        out = set()
        with company_scope(db, None):
            for pk, codes in codes_of.items():
                if not codes:
                    continue
                rows = (
                    db.query(Attachment.id, Attachment.company_id)
                    .join(AttachmentType, AttachmentType.id == Attachment.attachment_type_id)
                    .filter(Attachment.is_deleted.is_(False), ks.contact_readable_clause(codes))
                    .all()
                )
                out |= {(pk, str(r[0])) for r in rows if company_ok(pk, r[1])}
        return out

    def staff_by_type():
        return {a: bool(db.execute(text("SELECT ai_audience <> 'off' FROM attachment_types WHERE id = :i"), {"i": str(t.id)}).scalar()) for a, t in types.items()}

    before = old_pairs()
    assert before, "the seed must produce readable pairs, or equality proves nothing"
    assert len(before) < len(contacts) * len(levels_set) * len(companies) * len(types), "and some pairs must be refused"
    old_staff = staff_by_type()
    assert all(_ticks(db, t) == (False, []) for t in types.values())

    _migration().backfill(db.connection())

    assert new_pairs() == before
    new_staff = {a: _ticks(db, t)[0] for a, t in types.items()}
    assert new_staff == old_staff
