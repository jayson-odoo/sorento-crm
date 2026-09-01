"""Try it and preview (AC-B.1, B.2): S3's endpoints.

`try` reads a DRAFT rule list row by row against a real product or pasted text,
unsaved. `preview` compares a draft against the whole catalogue and reports counts -
its job runs on an in-process background thread (`product_spec_preview.py`), the same
shape `reread-catalogue` already uses, so:

  * the "job enqueued, wired correctly" tests monkeypatch `threading.Thread` to a
    no-op, because the real thread opens its OWN `SessionLocal()` on the shared
    engine's default schema - a connection this test's scratch-schema data (rolled
    back at teardown, on a different connection) is invisible to, AND one that would
    otherwise run a real derivation pass over the actual prod-copy `products` table.
  * the "job finishes with counts" tests call `product_spec_preview._run_job(...)`
    directly, against THIS test's own session, instead of polling a thread - the same
    function the real background thread runs (S4: `run_inline` was a second, test-only
    copy of that call; `_run_job` takes an optional `db` so both callers share one).

Fixture pattern copied from `test_spec_registry_pr2_routes.py` (the `api` fixture,
`_grant`/`_seed`/`_key`/`_product`/`_spec`).
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from tests._pg_fixture import blank_session

_VIEWER = "3a2f6d81-4c7e-5a13-b6e9-1d8c4f2a6b73"
_VIEWER_ROLE = "6b1e9c04-2f7a-5d38-a4c6-0e3b7f1a9d52"
_EDITOR = "9c4e2b17-6a8d-5f42-b1e3-4c9a2d6f8b05"
_EDITOR_ROLE = "4f8a1c93-7e2b-5a06-c9d4-1b6e3a8f0c27"
_OUTSIDER = "1e6a3c58-9d2f-5b74-e0a1-8c4f6b2d9e31"
_SORENTO = "00000000-0000-0000-0000-000000000001"

_BASE = "/api/v1/master-data/spec-registry"


def _grant(db: Session, role_id: str, slugs) -> None:
    from app.models.user import UserPermission, UserRolePermission

    for slug in slugs:
        existing = db.query(UserPermission).filter_by(slug=slug).first()
        if existing is None:
            existing = UserPermission(id=str(uuid.uuid4()), slug=slug, name=slug, description="")
            db.add(existing)
            db.flush()
        db.add(
            UserRolePermission(
                id=str(uuid.uuid4()), role_id=role_id, permission_id=existing.id
            )
        )


def _seed(db: Session) -> None:
    from app.models.user import User, UserRole, UserRoleAssignment

    for role_id, slug, name in (
        (_VIEWER_ROLE, "zzt_try_preview_viewer", "ZZT Try/Preview Viewer"),
        (_EDITOR_ROLE, "zzt_try_preview_editor", "ZZT Try/Preview Editor"),
    ):
        db.add(
            UserRole(
                id=role_id,
                slug=slug,
                name=name,
                description="",
                is_protected=False,
                is_default=False,
            )
        )
    db.add(User(id=_VIEWER, email="zzt-tp-viewer@test.com", name="Viewer", status="ACTIVE"))
    db.add(User(id=_EDITOR, email="zzt-tp-editor@test.com", name="Editor", status="ACTIVE"))
    db.add(User(id=_OUTSIDER, email="zzt-tp-outsider@test.com", name="Outsider", status="ACTIVE"))
    db.flush()

    db.add(UserRoleAssignment(user_id=_VIEWER, role_id=_VIEWER_ROLE))
    db.add(UserRoleAssignment(user_id=_EDITOR, role_id=_EDITOR_ROLE))
    _grant(db, _VIEWER_ROLE, ("master_data.spec_registry.view",))
    _grant(
        db,
        _EDITOR_ROLE,
        ("master_data.spec_registry.view", "master_data.spec_registry.edit"),
    )
    db.commit()


def _key(db: Session, spec_key: str, **kwargs):
    from app.models.product_spec import ProductSpecRegistry

    row = ProductSpecRegistry(
        spec_key=spec_key,
        label=kwargs.pop("label", spec_key.replace("_", " ").title()),
        data_type=kwargs.pop("data_type", "numeric"),
        unit=kwargs.pop("unit", "mm"),
        allowed_values=kwargs.pop("allowed_values", []),
        synonyms=kwargs.pop("synonyms", {}),
        user_synonyms=kwargs.pop("user_synonyms", {}),
        user_values=kwargs.pop("user_values", []),
        applies_when=kwargs.pop("applies_when", {}),
        is_active=kwargs.pop("is_active", True),
        source=kwargs.pop("source", "user"),
        **kwargs,
    )
    db.add(row)
    db.flush()
    return row


def _product(db: Session, description: str, code: str | None = None):
    from app.models.product import Product, ProductCategory, UnitOfMeasure

    stem = f"ZZTSR{uuid.uuid4().hex[:6]}"
    category = ProductCategory(category_code=stem, category_name=f"ZZT cat {stem}")
    uom = UnitOfMeasure(uom_code=stem[:20], uom_name=f"ZZT uom {stem}")
    db.add_all([category, uom])
    db.flush()
    product = Product(
        product_code=code or stem,
        product_name=f"ZZT product {stem}",
        description=description,
        category_id=category.id,
        base_uom_id=uom.id,
        list_price=Decimal("10.00"),
        company_id=_SORENTO,
    )
    db.add(product)
    db.flush()
    return product


def _spec(db: Session, product, values, provenance=None):
    from app.models.product_spec import ProductSpecifications

    row = ProductSpecifications(
        product_id=product.id,
        values=values,
        provenance=provenance or {},
        status="derived",
    )
    db.add(row)
    db.flush()
    return row


@pytest.fixture
def api():
    from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
    from app.models.base import set_company_scope
    from app.services.company_scope_resolver import apply_company_scope

    with blank_session() as db:
        _seed(db)

        def _override_get_db():
            yield db

        app.dependency_overrides[get_db] = _override_get_db

        async def _override_scope():
            scope = frozenset({_SORENTO})
            set_company_scope(db, scope)
            return scope

        app.dependency_overrides[apply_company_scope] = _override_scope

        def _as(user_id: str):
            principal = {"id": user_id, "email": f"{user_id}@test.com"}
            app.dependency_overrides[get_current_user] = lambda: principal
            app.dependency_overrides[get_current_user_or_api_key] = lambda: principal

        yield db, _as

        app.dependency_overrides.clear()


_ONE_ROW = [{"match": "regex", "pattern": r"\((\d+)MM\)", "capture": 1}]


# --------------------------------------------------------------------------- #
# AC-B.1 - try
# --------------------------------------------------------------------------- #
def test_try_by_product_id_reads_every_row(api):
    db, _as = api
    _as(_VIEWER)
    client = TestClient(app)
    _key(db, "zzt_length")
    product = _product(db, "MARBLE TOP BASIN (800MM)")

    response = client.post(
        f"{_BASE}/zzt_length/try", json={"productId": product.id, "rules": _ONE_ROW}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["description"] == "MARBLE TOP BASIN (800MM)"
    assert body["reads"] == [{"index": 0, "value": 800, "evidence": "(800MM)"}]
    assert body["winner_index"] == 0


def test_try_by_text_reads_the_pasted_text_not_a_product(api):
    db, _as = api
    _as(_VIEWER)
    client = TestClient(app)
    _key(db, "zzt_length")

    response = client.post(
        f"{_BASE}/zzt_length/try",
        json={"text": "MARBLE TOP BASIN (800MM)", "rules": _ONE_ROW},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["description"] == "MARBLE TOP BASIN (800MM)"
    assert body["reads"] == [{"index": 0, "value": 800, "evidence": "(800MM)"}]
    assert body["winner_index"] == 0


def test_try_every_row_reads_nothing_when_nothing_matches(api):
    db, _as = api
    _as(_VIEWER)
    client = TestClient(app)
    _key(db, "zzt_length")
    product = _product(
        db, "WASH DOWN CLOSE COUPLED WATER CLOSET S-TRAP:300MM"
    )
    two_rows = [
        {"match": "regex", "pattern": r"\((\d+)MM\)", "capture": 1},
        {"match": "contains", "pattern": "RIMLESS", "value": True},
    ]

    response = client.post(
        f"{_BASE}/zzt_length/try", json={"productId": product.id, "rules": two_rows}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["reads"] == [
        {"index": 0, "value": None, "evidence": None},
        {"index": 1, "value": None, "evidence": None},
    ]
    assert body["winner_index"] is None


def test_try_a_from_field_row_reads_nothing_from_pasted_text(api):
    """AC-B.1: pasted text has no product to read a `from_field` row from."""
    db, _as = api
    _as(_VIEWER)
    client = TestClient(app)
    _key(db, "zzt_length")

    response = client.post(
        f"{_BASE}/zzt_length/try",
        json={
            "text": "MARBLE TOP BASIN (800MM)",
            "rules": [{"match": "from_field", "pattern": "column:dimensions_length"}],
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["reads"] == [{"index": 0, "value": None, "evidence": None}]
    assert body["winner_index"] is None


def test_try_404s_an_unknown_product(api):
    db, _as = api
    _as(_VIEWER)
    client = TestClient(app)
    _key(db, "zzt_length")

    response = client.post(
        f"{_BASE}/zzt_length/try",
        json={"productId": str(uuid.uuid4()), "rules": _ONE_ROW},
    )
    assert response.status_code == 404, response.text


def test_try_404s_a_malformed_product_id(api):
    """S5: a non-UUID `productId` used to reach the database driver unparsed and
    raise `InvalidTextRepresentation` - a 500 for a typo in a URL nobody sees, not a
    genuinely unknown product."""
    db, _as = api
    _as(_VIEWER)
    client = TestClient(app)
    _key(db, "zzt_length")

    response = client.post(
        f"{_BASE}/zzt_length/try",
        json={"productId": "not-a-uuid", "rules": _ONE_ROW},
    )
    assert response.status_code == 404, response.text


def test_try_404s_an_unknown_spec_key(api):
    db, _as = api
    _as(_VIEWER)
    client = TestClient(app)

    response = client.post(
        f"{_BASE}/zzt_no_such_key/try", json={"text": "anything", "rules": []}
    )
    assert response.status_code == 404, response.text


def test_try_refuses_a_malformed_rule_naming_the_row(api):
    """`_validate_rules` (`_reject`) is reused as-is, unchanged: it answers 400 for a
    bad kind, same as the PATCH route it was built for. The plan text says 422; the
    shipped `_reject` says 400 for this shape and 422 only for a builder/pattern
    mismatch (AC-A.7). Reusing the function literally, as instructed, means this
    status code - the row is still named in the message either way."""
    db, _as = api
    _as(_VIEWER)
    client = TestClient(app)
    _key(db, "zzt_length")

    response = client.post(
        f"{_BASE}/zzt_length/try",
        json={"text": "anything", "rules": [{"match": "not_a_kind", "pattern": "x"}]},
    )
    assert response.status_code == 400, response.text
    assert "Rule 1" in response.json()["message"]


def test_try_422s_a_builder_pattern_mismatch_naming_the_row(api):
    """The one shape `_validate_rules` DOES 422 on: a `builder` that does not compile
    to the `pattern` sent alongside it (AC-A.7)."""
    db, _as = api
    _as(_VIEWER)
    client = TestClient(app)
    _key(db, "zzt_length")

    response = client.post(
        f"{_BASE}/zzt_length/try",
        json={
            "text": "anything",
            "rules": [
                {
                    "match": "regex",
                    "pattern": "this does not match the builder",
                    "capture": 1,
                    "builder": {"kind": "number_after", "word": "L"},
                }
            ],
        },
    )
    assert response.status_code == 422, response.text
    assert "Rule 1" in response.json()["message"]


def test_try_refuses_both_product_and_text(api):
    db, _as = api
    _as(_VIEWER)
    client = TestClient(app)
    _key(db, "zzt_length")
    product = _product(db, "MARBLE TOP BASIN (800MM)")

    response = client.post(
        f"{_BASE}/zzt_length/try",
        json={"productId": product.id, "text": "also this", "rules": []},
    )
    assert response.status_code == 400, response.text


def test_try_refuses_neither_product_nor_text(api):
    db, _as = api
    _as(_VIEWER)
    client = TestClient(app)
    _key(db, "zzt_length")

    response = client.post(f"{_BASE}/zzt_length/try", json={"rules": []})
    assert response.status_code == 400, response.text


def test_try_denies_a_caller_with_no_permission(api):
    db, _as = api
    _as(_OUTSIDER)
    client = TestClient(app)
    _key(db, "zzt_length")

    response = client.post(
        f"{_BASE}/zzt_length/try", json={"text": "anything", "rules": []}
    )
    assert response.status_code == 403, response.text


# --------------------------------------------------------------------------- #
# AC-B.2 - preview
# --------------------------------------------------------------------------- #
def test_preview_denies_a_view_only_caller(api):
    db, _as = api
    _as(_VIEWER)
    client = TestClient(app)
    _key(db, "zzt_length")

    response = client.post(f"{_BASE}/zzt_length/preview", json={"rules": []})
    assert response.status_code == 403, response.text


def test_preview_404s_an_unknown_spec_key(api):
    db, _as = api
    _as(_EDITOR)
    client = TestClient(app)

    response = client.post(f"{_BASE}/zzt_no_such_key/preview", json={"rules": []})
    assert response.status_code == 404, response.text


def test_preview_refuses_a_malformed_rule_naming_the_row(api):
    """See the `try` version of this test for why 400, not 422."""
    db, _as = api
    _as(_EDITOR)
    client = TestClient(app)
    _key(db, "zzt_length")

    response = client.post(
        f"{_BASE}/zzt_length/preview",
        json={"rules": [{"match": "not_a_kind", "pattern": "x"}]},
    )
    assert response.status_code == 400, response.text
    assert "Rule 1" in response.json()["message"]


def test_preview_enqueues_a_job_without_running_it_inline(api, monkeypatch):
    """The route hands back a jobId immediately - it does not wait on the thread."""
    db, _as = api
    _as(_EDITOR)
    client = TestClient(app)
    _key(db, "zzt_length")

    from app.services import product_spec_preview

    started: dict = {}

    def _fake_start(spec_key, rules):
        started["spec_key"] = spec_key
        started["rules"] = rules
        return "zzt-fake-job"

    monkeypatch.setattr(product_spec_preview, "start", _fake_start)

    response = client.post(f"{_BASE}/zzt_length/preview", json={"rules": _ONE_ROW})
    assert response.status_code == 200, response.text
    assert response.json() == {"jobId": "zzt-fake-job"}
    assert started["spec_key"] == "zzt_length"
    assert started["rules"][0]["pattern"] == r"\((\d+)MM\)"


def test_preview_job_reports_pending_before_it_finishes(api, monkeypatch):
    """The background thread itself is stubbed out - only the `pending` state, which
    `start()` writes before spawning it, is under test here."""
    db, _as = api
    _as(_EDITOR)
    client = TestClient(app)
    _key(db, "zzt_length")

    from app.services import product_spec_preview

    class _NoopThread:
        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            pass

    monkeypatch.setattr(product_spec_preview.threading, "Thread", _NoopThread)

    response = client.post(f"{_BASE}/zzt_length/preview", json={"rules": _ONE_ROW})
    assert response.status_code == 200, response.text
    job_id = response.json()["jobId"]

    status_response = client.get(f"{_BASE}/zzt_length/preview/{job_id}")
    assert status_response.status_code == 200, status_response.text
    # `spec_key` is bookkeeping for the mismatch guard below, stripped before the
    # body reaches a client - an exact-equality check is what proves it never leaks.
    assert status_response.json() == {"status": "pending"}

    # The no-op thread double above never reaches `_run_job`'s `finally`, so
    # `start()`'s single-run guard (S4) would otherwise stay "running" for the rest
    # of this process and 409 every real `start()` call after this test.
    product_spec_preview._RUNNING_JOB_ID = None


def test_preview_get_requires_edit_not_view(api):
    """UAC AC-B.2: the poll needs the same grant the POST that started the job does -
    a viewer holding only `.view` is refused, not merely 404'd for guessing wrong."""
    db, _as = api
    _as(_VIEWER)
    client = TestClient(app)
    _key(db, "zzt_length")

    response = client.get(f"{_BASE}/zzt_length/preview/no-such-job")
    assert response.status_code == 403, response.text


def test_preview_404s_an_unknown_job(api):
    db, _as = api
    _as(_EDITOR)
    client = TestClient(app)

    response = client.get(f"{_BASE}/zzt_length/preview/no-such-job")
    assert response.status_code == 404, response.text


def test_preview_404s_a_job_started_under_a_different_spec_key(api):
    db, _as = api
    _as(_EDITOR)
    client = TestClient(app)
    _key(db, "zzt_length")
    _key(db, "zzt_width")

    from app.services import product_spec_preview

    job_id = "zzt-other-key-job"
    product_spec_preview._run_job(job_id, "zzt_width", _ONE_ROW, db)

    response = client.get(f"{_BASE}/zzt_length/preview/{job_id}")
    assert response.status_code == 404, response.text
    # The job is real - reading it under its OWN key still works.
    own = client.get(f"{_BASE}/zzt_width/preview/{job_id}")
    assert own.status_code == 200, own.text


def test_preview_refuses_a_second_run_while_one_is_running(api, monkeypatch):
    """S4: only one preview at a time, the way `product_spec_rederive.start()` guards
    its own single run. `_RUNNING_JOB_ID` is set through `monkeypatch` rather than a
    real `start()` call, so this test cannot leak a stuck "running" state into any
    test that runs after it - `monkeypatch` undoes the attribute on teardown."""
    db, _as = api
    _as(_EDITOR)
    client = TestClient(app)
    _key(db, "zzt_length")

    from app.services import product_spec_preview

    monkeypatch.setattr(product_spec_preview, "_RUNNING_JOB_ID", "zzt-already-running")

    response = client.post(f"{_BASE}/zzt_length/preview", json={"rules": _ONE_ROW})
    assert response.status_code == 409, response.text
    body = response.json()
    assert body["code"] == "spec_preview_running"
    assert body["detail"] == "zzt-already-running"


def test_preview_job_counts_and_sample_excluding_hand_set(api):
    """Run the comparison inline (AC-B.2): changed, added, removed, unchanged, and a
    hand-set value counted in none of them."""
    db, _as = api
    _as(_EDITOR)
    _key(db, "zzt_length")

    changed_product = _product(db, "TAP A (800MM)")
    _spec(db, changed_product, {"zzt_length": {"value": 700}}, {"zzt_length": {"source": "derived"}})

    added_product = _product(db, "TAP B (500MM)")
    _spec(db, added_product, {}, {})

    removed_product = _product(db, "TAP C - no size here")
    _spec(db, removed_product, {"zzt_length": {"value": 300}}, {"zzt_length": {"source": "derived"}})

    unchanged_product = _product(db, "TAP D (200MM)")
    _spec(db, unchanged_product, {"zzt_length": {"value": 200}}, {"zzt_length": {"source": "derived"}})

    hand_set_product = _product(db, "TAP E (999MM)")
    _spec(
        db,
        hand_set_product,
        {"zzt_length": {"value": 111}},
        {"zzt_length": {"source": "human", "confidence": 1.0, "evidence": "set by hand"}},
    )

    from app.services import product_spec_preview

    job_id = "zzt-inline-job"
    product_spec_preview._run_job(job_id, "zzt_length", _ONE_ROW, db)

    state = product_spec_preview.get(job_id)
    assert state["status"] == "done"
    assert state["changed"] == 1
    assert state["added"] == 1
    assert state["removed"] == 1
    assert state["unchanged"] == 1

    by_code = {row["code"]: row for row in state["sample"]}
    assert by_code[changed_product.product_code] == {
        "code": changed_product.product_code,
        "before": 700,
        "after": 800,
    }
    assert by_code[added_product.product_code]["before"] is None
    assert by_code[added_product.product_code]["after"] == 500
    assert by_code[removed_product.product_code]["before"] == 300
    assert by_code[removed_product.product_code]["after"] is None
    assert hand_set_product.product_code not in by_code

    client = TestClient(app)
    _as(_EDITOR)
    status_response = client.get(f"{_BASE}/zzt_length/preview/{job_id}")
    assert status_response.status_code == 200, status_response.text
    assert status_response.json()["changed"] == 1


def test_preview_scans_with_the_all_companies_scope(api):
    """The real job runs on a background thread with its OWN session, which starts
    with NO company scope set at all - and `CompanyScopedMixin` fails CLOSED on that
    (0 rows), not open. A preview that forgot to open `company_scope(db, None)` would
    silently compare against nothing and report every count as 0, which reads as "no
    drift" rather than as the missing scope it actually is (caught once already, in
    the browser evidence run for this slice - AC-B.5).

    This test reproduces that starting condition on purpose: it clears the scope key
    the test harness would otherwise default for us, the way a fresh `SessionLocal()`
    genuinely starts, and asserts the seeded product is still found.
    """
    db, _as = api
    _as(_EDITOR)
    _key(db, "zzt_length")
    product = _product(db, "TAP F (600MM)")
    _spec(db, product, {"zzt_length": {"value": 600}}, {"zzt_length": {"source": "derived"}})

    db.info.pop("company_scope", None)

    from app.services import product_spec_preview

    job_id = "zzt-scope-job"
    product_spec_preview._run_job(job_id, "zzt_length", _ONE_ROW, db)

    state = product_spec_preview.get(job_id)
    assert state["status"] == "done"
    # Unchanged, not "nothing scanned": the row was found and read the same as stored.
    assert state["unchanged"] == 1
    assert state["changed"] == 0
    assert state["added"] == 0
    assert state["removed"] == 0
