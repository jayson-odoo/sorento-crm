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

import uuid

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


def test_ac_w2_the_original_triple_constraint_stands_and_supplier_id_was_added():
    """Round 3 ruling: the partial unique indexes are gone - `uq_import_field_alias_triple`
    on (doc_type, field, alias) is the ORIGINAL constraint, restored, and `supplier_id` is
    an added nullable column, not part of any uniqueness key. Two rows for the exact same
    (field, alias) pair - whatever their `supplier_id` - collide on this constraint; that
    behaviour is covered by the 409 test above, which exercises it through the route rather
    than a raw insert."""
    with pg_session() as db:
        constraint_exists = db.execute(
            text(
                "SELECT 1 FROM pg_constraint WHERE conname = 'uq_import_field_alias_triple'"
            )
        ).scalar()
        assert constraint_exists == 1

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
