"""Stock list word list storage (S2, `PLAN-stock-list-bare-model-codes.md` D6/D7).

TEST-FIRST (Phase 2): `import_field_alias.supplier_id` does not exist yet and
`canonical_fields("supplier_inventory_word")` returns `[]`, so every test below is expected
to be RED - either a `TypeError` seeding `ImportFieldAlias(supplier_id=...)` (the column is
not an ORM attribute yet), a 422 from `_assert_known_field` (the doc type has no readers),
or a missing `supplier_id`/`supplier_name` key on the list response - until S2 lands.

Route/permission wiring modelled on `tests/system/test_import_field_aliases_api.py` (same
`scm_app`/company-user pattern). AC-W2's downgrade half (rows + column removed) is not
covered here: exercising an actual `alembic downgrade` against a shared test database is
outside what a rolled-back session can safely prove, and CI's `check-migration-heads` gate
already covers the single-head half.
"""
from __future__ import annotations

import importlib.util
import uuid
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.models.import_alias import ImportFieldAlias
from app.services.import_alias_service import canonical_fields
from tests._pg_fixture import pg_session, unique_code
from tests.scm.conftest import requires_pg, scm_app  # noqa: F401 - re-exported fixture
from tests.scm.test_outstanding_import_routes import as_company_user

pytestmark = requires_pg

URL = "/api/v1/system/import-field-aliases"
VIEW_PERMISSION = "system.import_field_aliases.view"
EDIT_PERMISSION = "system.import_field_aliases.edit"
DOC_TYPE = "supplier_inventory_word"
MARKER = "ZZIFAW"

#: `sorento_crm_backend/alembic/versions/` - CI's database is built by `create_all` + stamp
#: (`scripts/bootstrap_env.py`), which never runs a migration BODY, so the D7 seed rows this
#: migration inserts in `upgrade()` do not exist there. Loading the migration module the way
#: `tests/scm/test_packing_list_kailu.py`'s own `_load` helper does and calling its seed
#: function directly runs the SAME insert path production/`bootstrap_env` uses, rather than
#: retyping the 15 pairs a second time somewhere they can drift from the migration.
_VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, _VERSIONS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _u() -> str:
    return str(uuid.uuid4())


def _grant(db, uid: str, slug: str) -> None:
    from app.models.user import UserPermission, UserRole, UserRolePermission, UserRoleAssignment

    tag = uuid.uuid4().hex[:8]
    role = UserRole(id=_u(), slug=f"{MARKER}-role-{tag}", name=f"{MARKER} role {tag}")
    db.add(role)
    db.flush()
    perm = db.query(UserPermission).filter(UserPermission.slug == slug).one_or_none()
    if perm is None:
        perm = UserPermission(id=_u(), slug=slug, name=slug)
        db.add(perm)
        db.flush()
    db.add(UserRolePermission(id=_u(), role_id=role.id, permission_id=perm.id))
    db.add(UserRoleAssignment(id=_u(), user_id=uid, role_id=role.id))
    db.flush()


def _client(scm_app, *, view: bool = False, edit: bool = False):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk, role=None)
    uid = app.dependency_overrides[gcu]()["id"]
    if view:
        _grant(db, uid, VIEW_PERMISSION)
    if edit:
        _grant(db, uid, EDIT_PERMISSION)
    return TestClient(app), db


def _seed_supplier(db) -> str:
    from app.models.procurement import Supplier

    supplier = Supplier(
        id=str(uuid.uuid4()),
        supplier_code=unique_code("SUP"),
        supplier_name=f"{MARKER} supplier",
        is_active=True,
    )
    db.add(supplier)
    db.flush()
    return str(supplier.id)


def test_ac_w1_canonical_fields_is_empty_the_word_vocabulary_is_open_not_a_reader_list():
    # Review round 1, item 4: the word doc type's field is an OPEN, shape-validated
    # vocabulary (`WORD_TOKEN_RE`), never a reader's declared field set - `canonical_fields`
    # deliberately answers `[]` and `_assert_known_field` validates by shape instead.
    assert canonical_fields(DOC_TYPE) == []


def test_ac_w1_create_a_shared_word_row(scm_app):
    client, _db = _client(scm_app, view=True, edit=True)

    r = client.post(URL, json={"doc_type": DOC_TYPE, "field": "SRT", "alias": f"{MARKER}_SORENTO"})

    assert r.status_code in (200, 201), r.text


def test_ac_w1_create_a_supplier_scoped_word_row(scm_app):
    client, db = _client(scm_app, view=True, edit=True)
    supplier_id = _seed_supplier(db)

    r = client.post(
        URL,
        json={
            "doc_type": DOC_TYPE,
            "field": "SH",
            "alias": f"{MARKER}_dui_chong",
            "supplier_id": supplier_id,
        },
    )

    assert r.status_code in (200, 201), r.text


def test_ac_w1_a_field_violating_the_token_shape_is_422(scm_app):
    # The vocabulary is OPEN (any 1-10 char uppercase alphanumeric token is a valid word
    # token - "XYZ" included), so what is refused is the SHAPE, not membership in a list.
    client, _db = _client(scm_app, view=True, edit=True)

    r = client.post(URL, json={"doc_type": DOC_TYPE, "field": "SH!", "alias": f"{MARKER}_x"})

    assert r.status_code == 422, r.text


def test_ac_w1_an_eleven_character_field_is_422(scm_app):
    client, _db = _client(scm_app, view=True, edit=True)

    r = client.post(
        URL, json={"doc_type": DOC_TYPE, "field": "A" * 11, "alias": f"{MARKER}_x11"}
    )

    assert r.status_code == 422, r.text


def test_ac_w1_a_lowercase_field_is_accepted_and_stored_uppercased(scm_app):
    client, db = _client(scm_app, view=True, edit=True)

    r = client.post(URL, json={"doc_type": DOC_TYPE, "field": "hp", "alias": f"{MARKER}_hp"})

    assert r.status_code in (200, 201), r.text
    stored_field = db.execute(
        text("SELECT field FROM import_field_alias WHERE doc_type = :d AND alias = :a"),
        {"d": DOC_TYPE, "a": f"{MARKER}_hp"},
    ).scalar()
    assert stored_field == "HP"


def test_ac_w1_an_unknown_supplier_id_is_422(scm_app):
    client, _db = _client(scm_app, view=True, edit=True)

    r = client.post(
        URL,
        json={
            "doc_type": DOC_TYPE,
            "field": "SRT",
            "alias": f"{MARKER}_y",
            "supplier_id": str(uuid.uuid4()),
        },
    )

    assert r.status_code == 422, r.text
    assert r.json().get("detail") in ("supplier_id", None) or "supplier_id" in str(r.json())


def test_a_supplier_scoped_row_duplicating_a_shared_pair_is_409(scm_app):
    """Round 3 ruling: the ORIGINAL `uq_import_field_alias_triple` on (doc_type, field,
    alias) stays - `supplier_id` is not part of the key at all, so a (field, alias) PAIR
    exists at most once on file, shared or scoped. A supplier's own row is an OVERRIDE: the
    same WORD (alias) mapped to a DIFFERENT token (field) - a different triple, so it is
    free to exist beside the shared one, and `WordList.for_supplier` reads that supplier's
    row over the shared one for that word while every other supplier still reads the shared
    token."""
    client, db = _client(scm_app, view=True, edit=True)
    supplier_id = _seed_supplier(db)
    field, alias = "SH", f"{MARKER}_scoping_word"

    shared = client.post(URL, json={"doc_type": DOC_TYPE, "field": field, "alias": alias})
    assert shared.status_code in (200, 201), shared.text

    # Same (field, alias) pair, scoped to a supplier - the identical triple, so 409 even
    # though the supplier differs; the constraint has no supplier_id column to distinguish.
    dup_scoped = client.post(
        URL,
        json={"doc_type": DOC_TYPE, "field": field, "alias": alias, "supplier_id": supplier_id},
    )
    assert dup_scoped.status_code == 409, dup_scoped.text
    assert "shared" in dup_scoped.text.lower(), dup_scoped.text

    # The OVERRIDE case: the same word, a DIFFERENT token, scoped to the supplier - a new
    # triple, so it is free to exist.
    override_field = "SHX"
    override = client.post(
        URL,
        json={
            "doc_type": DOC_TYPE, "field": override_field, "alias": alias,
            "supplier_id": supplier_id,
        },
    )
    assert override.status_code in (200, 201), override.text

    from app.services.scm.supplier_code_composer import WordList

    other_supplier_id = _seed_supplier(db)
    overridden_words = WordList.for_supplier(db, supplier_id)
    shared_words = WordList.for_supplier(db, other_supplier_id)
    assert overridden_words.lookup(alias) == override_field
    assert shared_words.lookup(alias) == field


def test_ac_w2_the_migration_seeds_exactly_the_d7_rows_shared():
    with pg_session() as db:
        # CI's database never runs a migration BODY (create_all + stamp), so the seed rows
        # are not already on file there the way they are on a hand-migrated dev copy - seed
        # them here, through the migration's own function, idempotent against a database
        # where they already exist.
        migration = _load("ifa_supplier_word_col")
        migration.seed_supplier_word_rows(db.connection())
        db.flush()

        rows = db.execute(
            text(
                "SELECT field, alias FROM import_field_alias "
                "WHERE doc_type = :d AND supplier_id IS NULL"
            ),
            {"d": DOC_TYPE},
        ).fetchall()
        pairs = {(r[0], r[1]) for r in rows}
        expected = {
            ("SRT", "SORENTO"),
            ("SRT", "S"),
            ("C", "CABANA"),
            ("C", "C"),
            ("M", "MOCHA"),
            ("M", "M"),
            ("WC", "连体马桶"),
            ("WC", "分体马桶"),
            ("WCX", "座头"),
            ("WCX", "分体座头"),
            ("WCY", "水箱"),
            ("WB", "盆"),
            ("WB", "盆小孔"),
            ("SC", "盖板"),
            ("P", "横排"),
        }
        assert expected <= pairs, pairs


def test_ac_w2_the_alias_uniqueness_is_per_supplier():
    """Owner ruling A (24 Sep 2026, PLAN-import-column-mapper-24sep.md review round 2)
    SUPERSEDES the round 3 ruling this test used to assert: the single
    `uq_import_field_alias_triple` on (doc_type, field, alias) - which had no
    `supplier_id` in it at all - is gone. A second supplier saving a header an earlier
    supplier had already saved was losing the `ON CONFLICT` race entirely and never got a
    row of its own, so uniqueness split in two (migration `ifa_supplier_uniq`, commit
    `fdeec235b`): `uq_import_field_alias_shared`, a PARTIAL unique index on
    (doc_type, field, alias) WHERE supplier_id IS NULL, so shared rows still collide with
    each other exactly as the old triple did; and `uq_import_field_alias_supplier`, a
    plain unique index on (doc_type, field, alias, supplier_id), so two DIFFERENT
    suppliers saving the identical (field, alias) pair now land two separate rows, one
    each. `supplier_id` remains a nullable column (NULL = shared), unchanged by the
    split. AC-W2's downgrade half is still not covered here, for the same reason the
    module docstring gives for the constraint this replaces."""
    with pg_session() as db:
        old_constraint_gone = db.execute(
            text(
                "SELECT 1 FROM pg_constraint WHERE conname = 'uq_import_field_alias_triple'"
            )
        ).scalar()
        assert old_constraint_gone is None

        shared_index = db.execute(
            text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE tablename = 'import_field_alias' "
                "AND indexname = 'uq_import_field_alias_shared'"
            )
        ).scalar()
        assert shared_index is not None
        assert "(doc_type, field, alias)" in shared_index
        assert "supplier_id IS NULL" in shared_index

        supplier_index = db.execute(
            text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE tablename = 'import_field_alias' "
                "AND indexname = 'uq_import_field_alias_supplier'"
            )
        ).scalar()
        assert supplier_index is not None
        assert "(doc_type, field, alias, supplier_id)" in supplier_index

        column_exists = db.execute(
            text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'import_field_alias' AND column_name = 'supplier_id'"
            )
        ).scalar()
        assert column_exists == 1


class TestWordListForSupplier:
    """AC-W3: a supplier's own row wins over the shared row; a word with only a shared row
    resolves; a word with neither is unknown; lookup is case/whitespace-insensitive."""

    def _seed(self, db):
        from app.models.procurement import Supplier

        sup = Supplier(
            id=str(uuid.uuid4()), supplier_code=unique_code("SUP"),
            supplier_name=f"{MARKER} wordlist supplier", is_active=True,
        )
        other = Supplier(
            id=str(uuid.uuid4()), supplier_code=unique_code("SUP"),
            supplier_name=f"{MARKER} other supplier", is_active=True,
        )
        db.add_all([sup, other])
        db.flush()
        db.add_all(
            [
                # Shared row.
                ImportFieldAlias(
                    id=str(uuid.uuid4()), doc_type=DOC_TYPE, field="C",
                    alias=f"{MARKER}_CABANA", supplier_id=None,
                ),
                # This supplier's own override of the same word.
                ImportFieldAlias(
                    id=str(uuid.uuid4()), doc_type=DOC_TYPE, field="M",
                    alias=f"{MARKER}_CABANA", supplier_id=str(sup.id),
                ),
            ]
        )
        db.flush()
        return str(sup.id), str(other.id)

    def test_a_suppliers_own_row_wins_over_the_shared_row(self):
        from app.services.scm.supplier_code_composer import WordList

        with pg_session() as db:
            sup_id, _other_id = self._seed(db)
            words = WordList.for_supplier(db, sup_id)
            assert words.lookup(f"{MARKER}_CABANA") == "M"

    def test_a_word_with_only_a_shared_row_resolves_for_any_supplier(self):
        from app.services.scm.supplier_code_composer import WordList

        with pg_session() as db:
            _sup_id, other_id = self._seed(db)
            words = WordList.for_supplier(db, other_id)
            assert words.lookup(f"{MARKER}_CABANA") == "C"

    def test_a_word_with_neither_row_is_unknown(self):
        from app.services.scm.supplier_code_composer import WordList

        with pg_session() as db:
            sup_id, _other_id = self._seed(db)
            words = WordList.for_supplier(db, sup_id)
            assert words.lookup(f"{MARKER}_NOWHERE") is None

    def test_lookup_is_case_and_whitespace_insensitive(self):
        from app.services.scm.supplier_code_composer import WordList

        with pg_session() as db:
            _sup_id, other_id = self._seed(db)
            words = WordList.for_supplier(db, other_id)
            assert words.lookup(f" {MARKER}_cabana ".lower()) == "C"


def test_ac_w4_the_list_endpoint_returns_supplier_id_and_supplier_name_per_row(scm_app):
    client, db = _client(scm_app, view=True)
    supplier_id = _seed_supplier(db)
    db.add(
        ImportFieldAlias(
            id=str(uuid.uuid4()), doc_type=DOC_TYPE, field="SH",
            alias=f"{MARKER}_shared_word", supplier_id=None,
        )
    )
    db.add(
        ImportFieldAlias(
            id=str(uuid.uuid4()), doc_type=DOC_TYPE, field="SH",
            alias=f"{MARKER}_scoped_word", supplier_id=supplier_id,
        )
    )
    db.commit()

    r = client.get(f"{URL}?doc_type={DOC_TYPE}")
    assert r.status_code == 200, r.text
    body = r.json()
    group = next((g for g in body if g["field"] == "SH"), None)
    assert group is not None, body
    by_alias = {a["alias"]: a for a in group["aliases"]}
    shared = by_alias[f"{MARKER}_shared_word"]
    scoped = by_alias[f"{MARKER}_scoped_word"]
    assert shared["supplier_id"] is None
    assert shared["supplier_name"] is None
    assert scoped["supplier_id"] == supplier_id
    assert scoped["supplier_name"] and f"{MARKER}" in scoped["supplier_name"]
