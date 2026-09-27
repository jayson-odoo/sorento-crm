"""Order inquiry line attachments - storage and link (#1312,
PLAN-oi-line-attachments-27sep.md). UAC group A (AC-A1..A7).

Postgres only, `tests/_pg_fixture.py::blank_session`, own seeded chain (`ZZOIA` marker).
Storage is stubbed the way `tests/test_shipment_line_photos.py` stubs it - upload/download
are never a real network call in this suite.

TEST-FIRST: written before `app.services.so_line_attachments` / the
`/api/v1/project-sales/sales-order-lines/...` routes exist, so a red here is
ModuleNotFoundError (the whole file fails to collect) - never an import typo or a fixture
bug. Once the module and routes exist, a specific-test red is a wrong status code, a wrong
response shape, or a wrong audit row - never a route 404 that should be 200.
"""
from __future__ import annotations

import asyncio
import io
import uuid
from decimal import Decimal

import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

from app.models.audit import AuditLog
from app.models.base import set_company_scope
from app.models.entity_attachment import EntityAttachmentLink
from app.models.order import SalesOrder, SalesOrderLine
from app.models.product import Product, ProductCategory, UnitOfMeasure
from app.models.resources import Attachment, AttachmentType
from app.services import so_line_attachments
from app.services.company_scope import DEFAULT_COMPANY_ID
from app.services.error_handler import AppException
from tests._pg_fixture import blank_session, unique_code

MARKER = "ZZOIA"

# A hardcoded, valid 1x1 PNG (same fixture `test_shipment_line_photos.py` uses) -
# decodable by Pillow, so `store_thumbnail` works.
_TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0"
    b"\x00\x00\x03\x01\x01\x00\xc9\xfe\x92\xef\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.fixture
def db():
    with blank_session() as session:
        set_company_scope(session, frozenset({DEFAULT_COMPANY_ID}))
        yield session


def _uom(db) -> str:
    uid = str(uuid.uuid4())
    db.add(UnitOfMeasure(id=uid, uom_code=unique_code("U")[:20], uom_name="pcs"))
    db.flush()
    return uid


def _category(db) -> str:
    cid = str(uuid.uuid4())
    db.add(
        ProductCategory(id=cid, category_code=unique_code("CAT"), category_name=f"{MARKER} category")
    )
    db.flush()
    return cid


def _product(db, code: str, *, category_id: str, uom_id: str) -> Product:
    p = Product(
        id=str(uuid.uuid4()),
        product_code=unique_code(code),
        product_name=code,
        category_id=category_id,
        base_uom_id=uom_id,
        list_price=0,
        is_active=True,
    )
    db.add(p)
    db.flush()
    return p


def _seed_line(db, *, code: str = "TAP", qty: str = "10", line_no: int = 3):
    category = _category(db)
    uom = _uom(db)
    product = _product(db, code, category_id=category, uom_id=uom)
    so = SalesOrder(
        id=str(uuid.uuid4()),
        company_id=DEFAULT_COMPANY_ID,
        so_number=unique_code("SO"),
        status="open",
        demand_class="project",
    )
    db.add(so)
    db.flush()
    line = SalesOrderLine(
        id=str(uuid.uuid4()),
        company_id=DEFAULT_COMPANY_ID,
        sales_order_id=so.id,
        product_id=product.id,
        qty_ordered=Decimal(qty),
        qty_delivered=Decimal("0"),
        line_status="open",
        line_no=line_no,
    )
    db.add(line)
    db.flush()
    return so, line


def _attachment_type(
    db,
    *,
    code: str = "so_line_attachment",
    allowed_extensions: str = "jpg,jpeg,png,webp,gif,pdf,xlsx,xls",
    max_file_size_mb: int = 10,
) -> AttachmentType:
    t = AttachmentType(
        id=str(uuid.uuid4()),
        type_name="Sales Order Line Attachment",
        code=code,
        allowed_extensions=allowed_extensions,
        max_file_size_mb=max_file_size_mb,
    )
    db.add(t)
    db.flush()
    return t


def _upload(name: str, *, data: bytes = _TINY_PNG, content_type: str = "image/png") -> UploadFile:
    return UploadFile(file=io.BytesIO(data), filename=name, headers=Headers({"content-type": content_type}))


def _stub_backend(monkeypatch, *, provider: str = "r2") -> None:
    """Same shape `test_shipment_line_photos.py::_stub_backend` uses - both the
    `storage_router` module-level names AND the names `so_line_attachments` imports
    directly (a separate binding a patch on `storage_router` alone never reaches)."""
    from app.services.storage_router import clear_signed_url_cache

    clear_signed_url_cache()
    stub_backend = type(
        "StubBackend",
        (),
        {
            "upload_file": staticmethod(lambda **kw: (f"stub/{provider}/key", "")),
            "download_file": staticmethod(lambda key: _TINY_PNG),
            "get_signed_url": staticmethod(
                lambda key, expires_in=3600: f"https://signed.test/{provider}/{key}"
            ),
            "get_cloudfront_base_url": staticmethod(lambda key: f"https://cdn.test/{key}"),
            "get_cdn_base_url": staticmethod(lambda key: f"https://cdn.test/{key}"),
        },
    )()

    def _get_backend(p):
        return stub_backend

    monkeypatch.setattr("app.services.storage_router.default_provider", lambda: provider)
    monkeypatch.setattr("app.services.storage_router.get_backend", _get_backend)
    monkeypatch.setattr(so_line_attachments, "default_provider", lambda: provider)
    monkeypatch.setattr(so_line_attachments, "get_backend", _get_backend)


def _msg(exc: AppException) -> str:
    return exc.detail.get("message") if isinstance(exc.detail, dict) else str(exc.detail)


# --------------------------------------------------------------------------- #
# AC-A1                                                                       #
# --------------------------------------------------------------------------- #


def test_upload_links_files_to_core_line(db, monkeypatch):
    _stub_backend(monkeypatch)
    _attachment_type(db)
    _so, line = _seed_line(db)
    db.commit()

    out = asyncio.run(
        so_line_attachments.upload(
            db,
            line_id=str(line.id),
            files=[
                _upload("a.png"),
                _upload("b.pdf", content_type="application/pdf"),
            ],
            actor_id=None,
        )
    )

    assert [f["filename"] for f in out] == ["a.png", "b.pdf"]

    links = (
        db.query(EntityAttachmentLink)
        .filter(
            EntityAttachmentLink.entity_type == so_line_attachments.ENTITY_TYPE,
            EntityAttachmentLink.entity_id == str(line.id),
        )
        .order_by(EntityAttachmentLink.sort_order.asc())
        .all()
    )
    assert len(links) == 2

    type_row = (
        db.query(AttachmentType)
        .filter(AttachmentType.code == so_line_attachments.TYPE_CODE)
        .one()
    )
    attachments = (
        db.query(Attachment)
        .filter(Attachment.id.in_([link.attachment_id for link in links]))
        .all()
    )
    assert {str(a.attachment_type_id) for a in attachments} == {str(type_row.id)}


# --------------------------------------------------------------------------- #
# AC-A3                                                                       #
# --------------------------------------------------------------------------- #


def test_upload_rejects_bad_type_and_size(db, monkeypatch):
    _stub_backend(monkeypatch)
    _attachment_type(db)
    _so, line = _seed_line(db)
    db.commit()

    with pytest.raises(AppException) as bad_type:
        asyncio.run(
            so_line_attachments.upload(
                db,
                line_id=str(line.id),
                files=[_upload("virus.exe", content_type="application/octet-stream")],
                actor_id=None,
            )
        )
    assert bad_type.value.status_code == 400
    assert "virus.exe" in _msg(bad_type.value)

    too_big = b"0" * (11 * 1024 * 1024)
    with pytest.raises(AppException) as too_large:
        asyncio.run(
            so_line_attachments.upload(
                db,
                line_id=str(line.id),
                files=[_upload("big.png", data=too_big)],
                actor_id=None,
            )
        )
    assert too_large.value.status_code == 400
    assert "big.png" in _msg(too_large.value)


# --------------------------------------------------------------------------- #
# AC-A4                                                                       #
# --------------------------------------------------------------------------- #


def test_upload_unknown_line_404(db, monkeypatch):
    _stub_backend(monkeypatch)
    _attachment_type(db)
    db.commit()

    with pytest.raises(AppException) as excinfo:
        asyncio.run(
            so_line_attachments.upload(
                db,
                line_id=str(uuid.uuid4()),
                files=[_upload("a.png")],
                actor_id=None,
            )
        )
    assert excinfo.value.status_code == 404


# --------------------------------------------------------------------------- #
# AC-A6 (service half) / AC-A7                                                #
# --------------------------------------------------------------------------- #


def test_delete_scoped_to_line(db, monkeypatch):
    _stub_backend(monkeypatch)
    _attachment_type(db)
    _so_a, line_a = _seed_line(db, code="TAPA", line_no=1)
    _so_b, line_b = _seed_line(db, code="TAPB", line_no=2)
    db.commit()

    out = asyncio.run(
        so_line_attachments.upload(
            db, line_id=str(line_a.id), files=[_upload("a.png")], actor_id=None,
        )
    )
    link_id = out[0]["id"]

    with pytest.raises(AppException) as excinfo:
        so_line_attachments.delete(db, str(line_b.id), link_id, None)
    assert excinfo.value.status_code == 404
    assert (
        db.query(EntityAttachmentLink).filter(EntityAttachmentLink.id == link_id).first()
        is not None
    ), "a 404 on the wrong line must delete nothing"


def test_deferred_delete_registered():
    import app.services.record_actions  # noqa: F401 - registers side effects on import
    from app.services.form_action_grace import WINDOW_DESTRUCTIVE
    from app.services.form_action_registry import get_action

    action = get_action("sales_order_line_attachment.delete")
    assert action is not None
    assert action.window == WINDOW_DESTRUCTIVE
    assert action.permission == "projects.projects.edit"


def test_upload_and_delete_audit_on_line(db, monkeypatch):
    _stub_backend(monkeypatch)
    _attachment_type(db)
    _so, line = _seed_line(db)
    db.commit()

    out = asyncio.run(
        so_line_attachments.upload(
            db, line_id=str(line.id), files=[_upload("a.png")], actor_id=None,
        )
    )
    link_id = out[0]["id"]

    added = (
        db.query(AuditLog)
        .filter(
            AuditLog.entity_type == "sales_order_line",
            AuditLog.entity_id == str(line.id),
            AuditLog.action == "UPDATE",
        )
        .all()
    )
    assert any(a.new_values == {"attachment_added": "a.png"} for a in added)

    so_line_attachments.delete(db, str(line.id), link_id, None)

    removed = (
        db.query(AuditLog)
        .filter(
            AuditLog.entity_type == "sales_order_line",
            AuditLog.entity_id == str(line.id),
            AuditLog.action == "UPDATE",
        )
        .all()
    )
    assert any(a.old_values == {"attachment_removed": "a.png"} for a in removed)


# --------------------------------------------------------------------------- #
# Routes - AC-A2, AC-A5 (over the wire)                                       #
# --------------------------------------------------------------------------- #

from fastapi.testclient import TestClient  # noqa: E402

from app.dependencies import get_current_user, get_current_user_or_api_key, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.services.company_scope_resolver import apply_company_scope  # noqa: E402
from app.services.user_service import UserPermissionService  # noqa: E402

_ROUTE_COMPANY_ID = DEFAULT_COMPANY_ID
BASE = "/api/v1/project-sales/sales-order-lines"


def _route_caller(db, monkeypatch, *, permitted_slugs: set[str]) -> TestClient:
    principal = {"id": str(uuid.uuid4()), "email": "zzt-oia@example.com"}
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: principal
    app.dependency_overrides[get_current_user_or_api_key] = lambda: principal
    monkeypatch.setattr(
        UserPermissionService,
        "check_user_has_permission",
        lambda self, uid, slug: slug in permitted_slugs,
    )

    scope = frozenset({_ROUTE_COMPANY_ID})
    set_company_scope(db, scope)

    async def _scope():
        set_company_scope(db, scope)
        return scope

    app.dependency_overrides[apply_company_scope] = _scope
    return TestClient(app)


@pytest.fixture
def view_and_edit_client(db, monkeypatch):
    try:
        yield _route_caller(
            db, monkeypatch,
            permitted_slugs={"projects.projects.view", "projects.projects.edit"},
        )
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def view_only_client(db, monkeypatch):
    try:
        yield _route_caller(db, monkeypatch, permitted_slugs={"projects.projects.view"})
    finally:
        app.dependency_overrides.clear()


def test_upload_needs_edit_permission(view_only_client, db, monkeypatch):
    """AC-A2: view-only refuses both the upload and the delete route with 403."""
    _stub_backend(monkeypatch)
    _attachment_type(db)
    _so, line = _seed_line(db)
    db.commit()

    upload_resp = view_only_client.post(
        f"{BASE}/{line.id}/attachments",
        files={"files": ("a.png", _TINY_PNG, "image/png")},
    )
    assert upload_resp.status_code == 403, upload_resp.text

    delete_resp = view_only_client.delete(f"{BASE}/{line.id}/attachments/{uuid.uuid4()}")
    assert delete_resp.status_code == 403, delete_resp.text


def test_lookup_needs_view(db, monkeypatch):
    """AC-A2: no permission at all refuses the lookup with 403; view-only gets 200."""
    _stub_backend(monkeypatch)
    _so, line = _seed_line(db)
    db.commit()

    no_perms_client = _route_caller(db, monkeypatch, permitted_slugs=set())
    try:
        r = no_perms_client.post(f"{BASE}/attachments/lookup", json={"line_ids": [str(line.id)]})
        assert r.status_code == 403, r.text
    finally:
        app.dependency_overrides.clear()

    view_client = _route_caller(db, monkeypatch, permitted_slugs={"projects.projects.view"})
    try:
        r = view_client.post(f"{BASE}/attachments/lookup", json={"line_ids": [str(line.id)]})
        assert r.status_code == 200, r.text
    finally:
        app.dependency_overrides.clear()


def test_lookup_groups_by_line(view_and_edit_client, db, monkeypatch):
    """AC-A5: 3 ids, 2 with files -> 2 keys, counts right; 1001 ids -> 422."""
    _stub_backend(monkeypatch)
    _attachment_type(db)
    _so_a, line_a = _seed_line(db, code="TAPA", line_no=1)
    _so_b, line_b = _seed_line(db, code="TAPB", line_no=2)
    _so_c, line_c = _seed_line(db, code="TAPC", line_no=3)
    db.commit()

    asyncio.run(
        so_line_attachments.upload(
            db, line_id=str(line_a.id),
            files=[_upload("a1.png"), _upload("a2.png")], actor_id=None,
        )
    )
    asyncio.run(
        so_line_attachments.upload(
            db, line_id=str(line_b.id), files=[_upload("b1.png")], actor_id=None,
        )
    )
    db.commit()

    r = view_and_edit_client.post(
        f"{BASE}/attachments/lookup",
        json={"line_ids": [str(line_a.id), str(line_b.id), str(line_c.id)]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body.keys()) == {str(line_a.id), str(line_b.id)}
    assert len(body[str(line_a.id)]) == 2
    assert len(body[str(line_b.id)]) == 1
    for item in body[str(line_a.id)]:
        assert {"id", "attachment_id", "filename", "size_bytes", "content_type", "url", "thumbnail_url"} <= set(item)

    too_many = [str(uuid.uuid4()) for _ in range(1001)]
    over_limit = view_and_edit_client.post(f"{BASE}/attachments/lookup", json={"line_ids": too_many})
    assert over_limit.status_code == 422, over_limit.text


# --------------------------------------------------------------------------- #
# Fix round 1 (reviewer + security-reviewer + captain)                       #
# --------------------------------------------------------------------------- #


def test_handover_attachments_visible_with_no_company_scope(db, monkeypatch):
    """Blocker 1: `_fire_pending_handover` reads on `fresh = SessionLocal()`, which
    never sets a company scope (UNSET, fail-closed) - `Attachment` is company-scoped
    (`__company_shared__`, so UNSET reads only its NULL-company rows), and a real
    upload is stamped with the uploader's own company. Without the fix,
    `handover_attachments` returned `{}` for every real upload - the handover never
    actually attached anything in production."""
    from app.models.base import UNSET, set_company_scope as _set_scope

    _stub_backend(monkeypatch)
    _attachment_type(db)
    _so, line = _seed_line(db)
    db.commit()

    asyncio.run(
        so_line_attachments.upload(
            db, line_id=str(line.id), files=[_upload("a.png")], actor_id=None,
        )
    )
    db.commit()

    # Simulate the drain's own fresh session: no scope ever set on it.
    _set_scope(db, UNSET)

    out = so_line_attachments.handover_attachments(db, [str(line.id)])
    assert out.get(str(line.id)), (
        "a real upload's files must be visible to a session with no company scope set"
    )
    assert out[str(line.id)][0]["filename"] == "a.png"


def test_upload_ignores_client_content_type(db, monkeypatch):
    """security M1: the client's own `Content-Type` header is never trusted - the
    stored `mime_type` is always derived from the (validated) extension."""
    _stub_backend(monkeypatch)
    _attachment_type(db)
    _so, line = _seed_line(db)
    db.commit()

    out = asyncio.run(
        so_line_attachments.upload(
            db,
            line_id=str(line.id),
            files=[_upload("a.png", content_type="text/html")],
            actor_id=None,
        )
    )
    assert out[0]["content_type"] == "image/png"
    attachment = (
        db.query(Attachment).filter(Attachment.id == out[0]["attachment_id"]).one()
    )
    assert attachment.mime_type == "image/png"


def test_upload_rejects_over_hardcoded_max_bytes_regardless_of_type_row(db, monkeypatch):
    """security L1: 10 MiB is HARDCODED in the service - an admin widening the
    attachment type row's own `max_file_size_mb` past it must not raise the ceiling."""
    _stub_backend(monkeypatch)
    _attachment_type(db, max_file_size_mb=50)
    _so, line = _seed_line(db)
    db.commit()

    too_big = b"0" * (so_line_attachments._MAX_BYTES + 1024)
    with pytest.raises(AppException) as excinfo:
        asyncio.run(
            so_line_attachments.upload(
                db, line_id=str(line.id), files=[_upload("huge.png", data=too_big)], actor_id=None,
            )
        )
    assert excinfo.value.status_code == 400
    assert "huge.png" in _msg(excinfo.value)


def test_upload_rejects_more_than_max_files_per_request(db, monkeypatch):
    """security L1: at most 10 files per request, named in the message."""
    _stub_backend(monkeypatch)
    _attachment_type(db)
    _so, line = _seed_line(db)
    db.commit()

    files = [_upload(f"a{i}.png") for i in range(so_line_attachments._MAX_FILES_PER_REQUEST + 1)]
    with pytest.raises(AppException) as excinfo:
        asyncio.run(so_line_attachments.upload(db, line_id=str(line.id), files=files, actor_id=None))
    assert excinfo.value.status_code == 400
    assert str(so_line_attachments._MAX_FILES_PER_REQUEST) in _msg(excinfo.value)


def test_upload_malformed_line_id_404(view_and_edit_client):
    """security L3: a malformed path id answers 404, never a 500 off an invalid
    UUID literal reaching the DB layer."""
    resp = view_and_edit_client.post(
        f"{BASE}/not-a-real-uuid/attachments",
        files={"files": ("a.png", _TINY_PNG, "image/png")},
    )
    assert resp.status_code == 404, resp.text


def test_delete_malformed_link_id_404(view_and_edit_client, db, monkeypatch):
    """security L3: same rule on the delete route's own `link_id`."""
    _stub_backend(monkeypatch)
    _attachment_type(db)
    _so, line = _seed_line(db)
    db.commit()

    resp = view_and_edit_client.delete(f"{BASE}/{line.id}/attachments/not-a-real-uuid")
    assert resp.status_code == 404, resp.text


def test_lookup_malformed_id_entry_422(view_and_edit_client):
    """security L3: `line_ids` is `List[UUID]` on the request schema - a malformed
    entry answers 422 through FastAPI's own validation, not a 500."""
    resp = view_and_edit_client.post(
        f"{BASE}/attachments/lookup", json={"line_ids": ["not-a-real-uuid"]}
    )
    assert resp.status_code == 422, resp.text
