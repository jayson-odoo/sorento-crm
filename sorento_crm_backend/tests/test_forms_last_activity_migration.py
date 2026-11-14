"""FORMS-LAST-ACTIVITY Phase 2 red tests: migration ``fla_0001_last_activity_at`` (U1, U1b).

Column + index checks read the migrated real database; the backfill test calls
``backfill_last_activity(bind)`` from the migration module inside a rolled-back ``pg_session``
transaction. The shared local Postgres converges through create_all, so after the model change
the column may need the equivalent idempotent ADD COLUMN there (backend CLAUDE.md); CI migrates.

Run: SORENTO_ENV_FILE=.env.ci-tests venv/bin/pytest tests/test_forms_last_activity_migration.py -q
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
from datetime import datetime

import pytest
from sqlalchemy import inspect, text

from tests._last_activity_support import BY_KEY, FORMS, IDS, SORENTO, at, seed_contact, seed_user, uid
from tests._pg_fixture import pg_session

REVISION = "fla_0001_last_activity_at"
VERSIONS = pathlib.Path(__file__).resolve().parents[1] / "alembic" / "versions"


def _migration():
    path = VERSIONS / f"{REVISION}.py"
    assert path.exists(), f"missing migration file {path.name}"
    spec = importlib.util.spec_from_file_location(REVISION, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_revision_is_in_the_chain_and_short_enough():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    assert len(REVISION) <= 32
    cfg = Config(str(VERSIONS.parents[1] / "alembic.ini"))
    cfg.set_main_option("script_location", str(VERSIONS.parent))
    script = ScriptDirectory.from_config(cfg)
    assert REVISION in {r.revision for r in script.walk_revisions()}
    assert len(script.get_heads()) == 1


@pytest.mark.parametrize("form", FORMS, ids=IDS)
def test_u1_column_is_nullable_naive_timestamp_and_indexed(form):
    from app.database import engine

    table = form.model.__table__
    insp = inspect(engine)
    cols = {c["name"]: c for c in insp.get_columns(table.name, schema=table.schema)}
    assert "last_activity_at" in cols, f"{table.name}.last_activity_at missing"
    col = cols["last_activity_at"]
    assert col["nullable"] is True
    assert getattr(col["type"], "timezone", None) is False
    indexed = [i for i in insp.get_indexes(table.name, schema=table.schema) if i["column_names"][:1] == ["last_activity_at"]]
    assert indexed, f"{table.name}.last_activity_at has no index"


def _audit(db, entity_type, entity_id, when, actor_type, *, root=None, user_id=None):
    root_type, root_id = root if root else (None, None)
    db.execute(
        text(
            "INSERT INTO audit_logs (id, entity_type, entity_id, action, changed_at, actor_type, "
            "root_entity_type, root_entity_id, user_id) VALUES (:id, :et, :eid, 'UPDATE', :at, :actor, :rt, :rid, :uid)"
        ),
        {"id": uid(), "et": entity_type, "eid": entity_id, "at": when, "actor": actor_type,
         "rt": root_type, "rid": root_id, "uid": user_id},
    )


def _link(db, entity_type, entity_id, when):
    att = uid()
    db.execute(
        text("INSERT INTO attachments (id, original_filename, stored_filename, file_path, is_deleted) VALUES (:i, 'z.pdf', :s, 'z/z.pdf', false)"),
        {"i": att, "s": f"zzt-fla-{att}.pdf"},
    )
    db.execute(
        text(
            "INSERT INTO entity_attachment_links (id, entity_type, entity_id, attachment_id, is_primary, created_at) "
            "VALUES (:i, :et, :eid, :att, false, :at)"
        ),
        {"i": uid(), "et": entity_type, "eid": entity_id, "att": att, "at": when},
    )


def _comment(db, kind, entity_id, when, *, is_system=False):
    db.execute(
        text(
            "INSERT INTO entity_conversation_messages (id, entity_type, entity_id, scope, is_system, body_html, created_at) "
            "VALUES (:i, :et, :eid, 'form_comment', :sys, 'zzt', :at)"
        ),
        {"i": uid(), "et": kind, "eid": entity_id, "sys": is_system, "at": when},
    )


def _blank_stamps(db, form, row):
    table = form.model.__table__
    name = f'"{table.schema}"."{table.name}"' if table.schema else f'"{table.name}"'
    db.execute(text(f"UPDATE {name} SET last_activity_at = NULL WHERE id = :i"), {"i": row.id})


def _stamp(db, form, row):
    table = form.model.__table__
    name = f'"{table.schema}"."{table.name}"' if table.schema else f'"{table.name}"'
    return db.execute(text(f"SELECT last_activity_at FROM {name} WHERE id = :i"), {"i": row.id}).scalar_one()


@pytest.fixture
def db():
    from app.models.base import set_company_scope

    with pg_session() as session:
        set_company_scope(session, frozenset({SORENTO}))
        yield session


def _backfill(db):
    _migration().backfill_last_activity(db.connection())


def test_u1b_backfill_counts_legacy_person_rows_links_and_comments_only(db):
    form = BY_KEY["complaint"]
    legacy = form.seed(db, created_at=at(days=1))
    mixed = form.seed(db, created_at=at(days=1))
    linked = form.seed(db, created_at=at(days=1))
    commented = form.seed(db, created_at=at(days=1))
    bare = form.seed(db, created_at=at(days=1))
    rooted = form.seed(db, created_at=at(days=1))
    user = seed_user(db)

    _audit(db, "complaint", legacy.id, at(days=5), "legacy")  # root NULL still counts
    _audit(db, "complaint", mixed.id, at(days=6), "user", user_id=user.id)
    for n, actor in enumerate(["worker", "scheduler", "system", "integration"]):
        _audit(db, "complaint", mixed.id, at(days=20 + n), actor)  # newer, but not a person
    _audit(db, "complaint", linked.id, at(days=7), "user", user_id=user.id)
    _link(db, "complaint", linked.id, at(days=9))
    _audit(db, "complaint", commented.id, at(days=7), "user", user_id=user.id)
    _comment(db, "complaint", commented.id, at(days=10))
    _comment(db, "complaint", commented.id, at(days=30), is_system=True)
    _audit(db, "complaint_lines", uid(), at(days=11), "user", root=("complaint", rooted.id), user_id=user.id)

    for r in (legacy, mixed, linked, commented, bare, rooted):
        _blank_stamps(db, form, r)
    _backfill(db)

    assert _stamp(db, form, legacy) == at(days=5)
    assert _stamp(db, form, mixed) == at(days=6)
    assert _stamp(db, form, linked) == at(days=9), "entity_attachment_links.created_at counts"
    assert _stamp(db, form, commented) == at(days=10), "a system comment does not count"
    assert _stamp(db, form, bare) == at(days=1), "no events falls back to created_at"
    assert _stamp(db, form, rooted) == at(days=11), "child rows count through root_entity_*"


def test_u1b_backfill_maps_legacy_sponsorship_form_audit_type_and_singular_price_tag_links(db):
    pr = BY_KEY["purchase_request"]
    sponsorship = pr.seed(db, created_at=at(days=1), request_type="sponsorship_form")
    _audit(db, "sponsorship_form", sponsorship.id, at(days=8), "legacy")
    ptr = BY_KEY["price_tag_request"].seed(db, created_at=at(days=1))
    _link(db, "price_tag_request", ptr.id, at(days=12))
    _blank_stamps(db, pr, sponsorship)
    _blank_stamps(db, BY_KEY["price_tag_request"], ptr)
    _backfill(db)
    assert _stamp(db, pr, sponsorship) == at(days=8)
    assert _stamp(db, BY_KEY["price_tag_request"], ptr) == at(days=12)


@pytest.mark.parametrize("form", FORMS, ids=IDS)
def test_u1_backfill_without_events_uses_created_at_on_every_table(db, form):
    row = form.seed(db, created_at=at(days=2))
    _blank_stamps(db, form, row)
    _backfill(db)
    assert _stamp(db, form, row) == at(days=2)


def test_u1_backfill_picks_the_newest_person_audit_row_on_each_table(db):
    for form in FORMS:
        row = form.seed(db, created_at=at(days=1))
        _audit(db, form.audit_entity_type, row.id, at(days=3), "user", user_id=seed_user(db).id)
        _audit(db, form.audit_entity_type, row.id, at(days=4), "user", user_id=seed_user(db).id)
        _audit(db, form.audit_entity_type, row.id, at(days=40), "worker")
        _blank_stamps(db, form, row)
        _backfill(db)
        assert _stamp(db, form, row) == at(days=4), form.key
