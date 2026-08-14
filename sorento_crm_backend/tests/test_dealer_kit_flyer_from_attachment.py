"""Reading a flyer the file library already holds (S7.3 hardening, Phase 2B).

Covers `documentation/plans/dealer-kit/flyer-read-hardening-acceptance-criteria.md`:

* AC-J2 - the read runs off the event loop (pinned by shape, not a wall clock).
* AC-J3 - the dealer-kit routers carry exactly one `async def` route + its helper.
* AC-A1 - a reading can be created from an existing attachment.
* AC-A2 - the same permission (`dealer_kit.page.edit`) guards both sources.
* AC-A3 - another company's attachment is a 404, never a 403, and creates nothing.
  A TRASHED attachment is the same 404, for the same reason: the loader behind
  the route reads active-or-archived rows, so the route has to refuse it itself.
* AC-A4 - the same validation (not-a-PDF, password-protected, oversized) applies,
  refusing from the RECORDED size before any bytes are fetched, and the actual
  bytes are still re-checked when the recorded size understates them.
* AC-A5 - the upload route's behaviour is unchanged (spot-checked here;
  exhaustively covered by test_dealer_kit_flyer_readings.py, untouched by this
  branch).
* Edge cases the coder flagged: a malformed attachmentId is a 422 at the edge,
  and a storage download failure is a 502 FLYER_SOURCE_UNREADABLE, not a 500.

Postgres only, on a blank scratch schema (tests/_pg_fixture.py). Every row is
ZZT-scoped except the product code, which has to be one the fixture flyer
actually prints - see tests/test_dealer_kit_flyer_readings.py for why.
"""
from __future__ import annotations

import ast
import asyncio
import pathlib
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from tests._fake_storage import patch_storage
from tests._pg_fixture import blank_session, unique_code

FIXTURE_PDF = Path(__file__).parent / "fixtures" / "dealer_kit" / "flyer_sample.pdf"

# A code printed on page 2 of the fixture, verified in flyer_golden.json (see
# test_dealer_kit_flyer_readings.py).
PRINTED_CODE = "SRTJC8041"

_SORENTO = "00000000-0000-0000-0000-000000000001"

_ADMIN_ID = "8f1c2d34-5e67-4a89-9b01-2c3d4e5f6a71"
_ADMIN_ROLE = "1a2b3c4d-5e6f-4708-9192-a3b4c5d6e7f8"
_EDITOR_ID = "3d4e5f60-7182-4930-a415-2c3b4a5968f7"
_EDITOR_ROLE = "9c8b7a65-4d3e-4f20-8112-3f4e5d6c7b8a"
_NOPERM_ID = "5a6b7c8d-9e0f-4a12-8b34-c5d6e7f80912"


def _seed_roles(db) -> None:
    """A superadmin, an editor holding view+edit, and a stranger holding nothing."""
    from app.models.user import (
        User,
        UserPermission,
        UserRole,
        UserRoleAssignment,
        UserRolePermission,
    )

    db.add(
        UserRole(
            id=_ADMIN_ROLE,
            slug="superadmin",
            name="Superadmin",
            description="",
            is_protected=True,
            is_default=False,
        )
    )
    db.add(
        UserRole(
            id=_EDITOR_ROLE,
            slug="zzt_flyer_fa_editor",
            name="ZZT Flyer From-Attachment Editor",
            description="Reads flyers into the Kit",
            is_protected=False,
            is_default=False,
        )
    )
    db.add(User(id=_ADMIN_ID, email="zzt-fa-admin@test.com", name="FA Admin", status="ACTIVE"))
    db.add(User(id=_EDITOR_ID, email="zzt-fa-editor@test.com", name="FA Editor", status="ACTIVE"))
    db.add(User(id=_NOPERM_ID, email="zzt-fa-out@test.com", name="FA Outsider", status="ACTIVE"))
    db.flush()

    db.add(UserRoleAssignment(user_id=_ADMIN_ID, role_id=_ADMIN_ROLE))
    db.add(UserRoleAssignment(user_id=_EDITOR_ID, role_id=_EDITOR_ROLE))

    granted = ("dealer_kit.page.view", "dealer_kit.page.edit")
    for slug in granted:
        perm_id = str(uuid.uuid4())
        db.add(UserPermission(id=perm_id, slug=slug, name=slug, description=""))
        db.flush()
        db.add(
            UserRolePermission(id=str(uuid.uuid4()), role_id=_EDITOR_ROLE, permission_id=perm_id)
        )
    db.commit()


@pytest.fixture
def api(monkeypatch):
    """The route stack with a switchable principal AND a switchable company, plus
    the fake storage backend so a seeded attachment's bytes come from the test
    rather than a live bucket.
    """
    from app.dependencies import (
        get_current_user,
        get_current_user_or_api_key,
        get_db,
    )
    from app.models.base import set_company_scope
    from app.services.company_scope_resolver import apply_company_scope

    with blank_session() as db:
        _seed_roles(db)
        storage = patch_storage(monkeypatch)
        here = {"company": _SORENTO}

        def _override_get_db():
            yield db

        app.dependency_overrides[get_db] = _override_get_db

        async def _override_scope():
            scope = frozenset({here["company"]})
            set_company_scope(db, scope)
            return scope

        app.dependency_overrides[apply_company_scope] = _override_scope

        def _as(user_id: str):
            principal = {"id": user_id, "email": f"{user_id}@test.com"}
            app.dependency_overrides[get_current_user] = lambda: principal
            app.dependency_overrides[get_current_user_or_api_key] = lambda: principal

        def _in_company(company_id: str):
            here["company"] = company_id
            set_company_scope(db, frozenset({company_id}))

        _as(_ADMIN_ID)
        yield db, _as, _in_company, storage

        app.dependency_overrides.clear()


# --------------------------------------------------------------------------- #
# Rows
# --------------------------------------------------------------------------- #
def _pdf_bytes() -> bytes:
    return FIXTURE_PDF.read_bytes()


def _upload(client: TestClient, *, filename: str = "zzt-flyer.pdf", data: bytes | None = None, **params):
    return client.post(
        "/api/v1/dealer-kit/flyer-readings",
        files={"file": (filename, data if data is not None else _pdf_bytes(), "application/pdf")},
        params=params,
    )


def _from_attachment(client: TestClient, attachment_id, **extra):
    body = {"attachmentId": str(attachment_id), **extra}
    return client.post("/api/v1/dealer-kit/flyer-readings/from-attachment", json=body)


def _company(db) -> str:
    from app.models.company import Company

    company = Company(
        id=str(uuid.uuid4()),
        name=unique_code("ZZT Other Co"),
        code=unique_code("ZZTFAC")[:20],
        is_active=True,
    )
    db.add(company)
    db.commit()
    return company.id


def _attachment(
    db,
    storage,
    *,
    company_id,
    filename: str = "zzt-library-flyer.pdf",
    mime_type: str | None = "application/pdf",
    data: bytes | None = None,
    recorded_size: int | None = None,
):
    """A row the from-attachment route can read, with real bytes behind it.

    ``company_id`` is ALWAYS explicit: attachments are company-shared, so a row
    inserted without one is stamped NULL and visible from every scope by
    design - a test that omitted it would pass the AC-A3 "out of scope" case
    for the wrong reason (the row would just be visible everywhere).
    """
    from app.models.resources import Attachment

    data = _pdf_bytes() if data is None else data
    key = f"zzt-dealer-kit-attachments/{uuid.uuid4()}/{filename}"
    storage.objects[key] = (data, mime_type)

    attachment = Attachment(
        id=str(uuid.uuid4()),
        company_id=company_id,
        original_filename=filename,
        stored_filename=filename,
        file_path=key,
        file_size_bytes=recorded_size if recorded_size is not None else len(data),
        mime_type=mime_type,
        storage_provider="s3",
    )
    db.add(attachment)
    db.commit()
    db.refresh(attachment)
    return attachment


def _codes(entries) -> list[str]:
    return [entry["code"] for entry in entries]


def _locked_pdf_bytes() -> bytes:
    import pymupdf

    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "SRTJC8041 599")
    return doc.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="o", user_pw="u")


# --------------------------------------------------------------------------- #
# AC-J2: the extraction runs off the event loop, pinned by shape
# --------------------------------------------------------------------------- #
class TestOffTheLoop:
    def test_ac_j2_create_reading_is_called_off_the_event_loop(self, api, monkeypatch) -> None:
        """The regression this whole slice exists to prevent (AC-J1/J2).

        Patches the ROUTE module's ``svc.create_reading`` (not a fresh import)
        so the spy intercepts the exact call the upload route makes, and asserts
        ``asyncio.get_running_loop()`` RAISES inside it - i.e. it is executing in
        a worker thread, not on the loop the TestClient's request is served
        from. A wall-clock threshold would be flaky on CI hardware; the SHAPE of
        "off the loop or not" never is.
        """
        from app.api.v1.dealer_kit import flyer_readings as route_module

        db, _as, _scope, _storage = api
        real_create_reading = route_module.svc.create_reading
        observed: dict[str, bool] = {}

        def _spy(db_arg, **kwargs):
            try:
                asyncio.get_running_loop()
                observed["on_loop"] = True
            except RuntimeError:
                observed["on_loop"] = False
            return real_create_reading(db_arg, **kwargs)

        monkeypatch.setattr(route_module.svc, "create_reading", _spy)

        with TestClient(app) as c:
            res = _upload(c, filename="zzt-j2-upload.pdf")

        assert res.status_code == 201, res.text
        assert "on_loop" in observed, "the spy was never called"
        assert observed["on_loop"] is False, (
            "create_reading ran ON the event loop - this is the exact defect "
            "that froze a whole gunicorn worker for 57.5s (AC-J1)."
        )


# --------------------------------------------------------------------------- #
# AC-J3: sweep for async def handlers doing heavy sync work
# --------------------------------------------------------------------------- #
def test_ac_j3_only_the_upload_route_and_its_read_helper_are_async() -> None:
    """Every OTHER dealer-kit route stays a plain ``def`` so FastAPI threadpools
    it automatically - confirmed by walking the actual source, not assumed.
    """
    dealer_kit_dir = (
        pathlib.Path(__file__).resolve().parents[1] / "app" / "api" / "v1" / "dealer_kit"
    )
    assert dealer_kit_dir.is_dir(), dealer_kit_dir

    allowed = {
        ("flyer_readings.py", "upload_flyer_reading"),
        ("flyer_readings.py", "_read_within_limit"),
    }
    offenders: list[str] = []
    # rglob, not glob: there is no subpackage under dealer_kit today, and a
    # sweep that only ever looks at the top level would stop covering the first
    # one somebody adds without failing to say so.
    for path in sorted(dealer_kit_dir.rglob("*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef):
                if (path.name, node.name) not in allowed:
                    offenders.append(f"{path.name}:{node.name}")

    assert offenders == [], (
        "unexpected async def in the dealer-kit routers (must be plain def so "
        f"FastAPI threadpools them, or explicitly added to `allowed`): {offenders}"
    )


# --------------------------------------------------------------------------- #
# AC-A1 / AC-A5: equivalence between the two sources
# --------------------------------------------------------------------------- #
class TestEquivalence:
    def test_ac_a1_a_reading_can_be_created_from_an_attachment(self, api) -> None:
        db, _as, _scope, storage = api
        attachment = _attachment(db, storage, company_id=_SORENTO, filename="zzt-a1-flyer.pdf")

        with TestClient(app) as c:
            res = _from_attachment(c, attachment.id)

        assert res.status_code == 201, res.text
        body = res.json()
        assert body["id"]
        assert body["filename"] == "zzt-a1-flyer.pdf"
        assert body["pageCount"] == 3
        assert PRINTED_CODE in _codes(body["report"]["unmatched"])

        # Lands in the caller's company scope, exactly as an upload does.
        from app.models.dealer_kit import FlyerReadingRecord

        record = db.query(FlyerReadingRecord).filter(FlyerReadingRecord.id == body["id"]).one()
        assert record.company_id == _SORENTO

    def test_ac_a1_a5_upload_and_from_attachment_produce_equivalent_readings(self, api) -> None:
        """The same bytes through both routes: same pages, same codes, same
        report, same banners stored - and the upload route's own contract
        (status/body/messages) is untouched by this branch (AC-A5).
        """
        db, _as, _scope, storage = api
        attachment = _attachment(
            db, storage, company_id=_SORENTO, filename="zzt-a5-via-library.pdf"
        )

        with TestClient(app) as c:
            uploaded = _upload(c, filename="zzt-a5-via-upload.pdf")
            from_attachment = _from_attachment(c, attachment.id)

        assert uploaded.status_code == 201, uploaded.text
        assert from_attachment.status_code == 201, from_attachment.text

        up_body = uploaded.json()
        fa_body = from_attachment.json()

        # AC-A5: the upload route's own shape is unchanged.
        assert up_body["filename"] == "zzt-a5-via-upload.pdf"
        assert up_body["pageCount"] == 3
        assert up_body["report"]["matched"] == []
        assert PRINTED_CODE in _codes(up_body["report"]["unmatched"])

        # AC-A1: indistinguishable once created, aside from the id/filename/
        # timestamp that are properties of WHICH row this is.
        for field in ("pageCount", "codeCount"):
            assert up_body[field] == fa_body[field], field
        assert up_body["report"]["matched"] == fa_body["report"]["matched"]
        assert _codes(up_body["report"]["unmatched"]) == _codes(fa_body["report"]["unmatched"])
        assert up_body["report"]["dimensionCandidates"] == fa_body["report"]["dimensionCandidates"]
        assert up_body["headings"] == fa_body["headings"]

        # Both stored a banner for at least one page - the from-attachment path
        # does not skip the artwork step the upload path performs.
        from app.models.dealer_kit import FlyerReadingRecord

        up_record = db.query(FlyerReadingRecord).filter(
            FlyerReadingRecord.id == up_body["id"]
        ).one()
        fa_record = db.query(FlyerReadingRecord).filter(
            FlyerReadingRecord.id == fa_body["id"]
        ).one()
        assert any(
            page.get("banner_asset_id") for page in up_record.reading_json["pages"]
        )
        assert any(
            page.get("banner_asset_id") for page in fa_record.reading_json["pages"]
        )


# --------------------------------------------------------------------------- #
# AC-A2: the same permission guards both sources
# --------------------------------------------------------------------------- #
class TestAccess:
    def test_ac_a2_a_stranger_is_refused_naming_the_edit_permission(self, api) -> None:
        db, _as, _scope, storage = api
        attachment = _attachment(db, storage, company_id=_SORENTO, filename="zzt-a2-flyer.pdf")

        _as(_NOPERM_ID)
        with TestClient(app) as c:
            res = _from_attachment(c, attachment.id)

        assert res.status_code == 403, res.text
        # Exactly as the upload route does: same slug, same wording.
        assert "dealer_kit.page.edit" in res.text

    def test_ac_a2_an_editor_holding_page_edit_may_use_it(self, api) -> None:
        db, _as, _scope, storage = api
        attachment = _attachment(db, storage, company_id=_SORENTO, filename="zzt-a2-ok.pdf")

        _as(_EDITOR_ID)
        with TestClient(app) as c:
            res = _from_attachment(c, attachment.id)

        assert res.status_code == 201, res.text


# --------------------------------------------------------------------------- #
# AC-A3: out-of-scope attachment is a 404, never a 403, and creates nothing
# --------------------------------------------------------------------------- #
class TestCompanyScope:
    def test_ac_a3_another_companys_attachment_is_absent_not_forbidden(self, api) -> None:
        db, _as, _scope, storage = api
        elsewhere = _company(db)
        attachment = _attachment(
            db, storage, company_id=elsewhere, filename="zzt-a3-elsewhere.pdf"
        )
        # Still in the Sorento scope: the attachment was created explicitly
        # OUT of it.
        from app.models.dealer_kit import FlyerReadingRecord

        before = db.query(FlyerReadingRecord).count()

        with TestClient(app) as c:
            res = _from_attachment(c, attachment.id)

        assert res.status_code == 404, res.text
        assert res.status_code != 403  # would confirm the id exists

        after = db.query(FlyerReadingRecord).count()
        assert after == before, "a 404 must not have created a reading"

    def test_ac_a3_a_null_company_attachment_is_shared_and_stays_readable(self, api) -> None:
        """The counterpoint: NULL is deliberately shared (form attachments),
        not "forgot to set it" - see the module's company-shared docstring.
        """
        db, _as, _scope, storage = api
        attachment = _attachment(
            db, storage, company_id=None, filename="zzt-a3-shared.pdf"
        )

        with TestClient(app) as c:
            res = _from_attachment(c, attachment.id)

        assert res.status_code == 201, res.text

    def test_a_trashed_attachment_is_absent_too_and_creates_nothing(self, api) -> None:
        """A file in the trash is not a file you may read.

        The loader behind this route is ``_get_attachment_any``, "active or
        archived" by its own docstring, so a trashed id reads perfectly well
        unless the route says otherwise. The picker sends ``is_deleted: false``
        and so cannot reach it - which is the point: the guard has to live on
        the route, because the route accepts an id from anywhere.

        Same 404 as the out-of-scope case, deliberately: a trashed file and
        somebody else's file must be one answer, or which one it was is readable
        from outside.
        """
        from app.models.dealer_kit import FlyerReadingRecord

        db, _as, _scope, storage = api
        attachment = _attachment(
            db, storage, company_id=_SORENTO, filename="zzt-a3-trashed.pdf"
        )
        attachment.is_deleted = True
        db.commit()

        before = db.query(FlyerReadingRecord).count()

        with TestClient(app) as c:
            res = _from_attachment(c, attachment.id)

        assert res.status_code == 404, res.text
        assert res.status_code != 403  # would confirm the id exists
        assert db.query(FlyerReadingRecord).count() == before, (
            "a 404 must not have created a reading"
        )


# --------------------------------------------------------------------------- #
# AC-A4: the same validation as the upload route
# --------------------------------------------------------------------------- #
class TestValidation:
    def test_ac_a4_a_non_pdf_mime_is_refused_with_the_same_code(self, api) -> None:
        db, _as, _scope, storage = api
        attachment = _attachment(
            db,
            storage,
            company_id=_SORENTO,
            filename="zzt-a4-notes.docx",
            mime_type="application/msword",
            data=b"not a pdf at all",
        )

        with TestClient(app) as c:
            res = _from_attachment(c, attachment.id)

        assert res.status_code == 400, res.text
        assert res.json().get("code") == "FLYER_NOT_A_PDF"

    def test_ac_a4_a_password_protected_flyer_is_refused_with_the_same_code(self, api) -> None:
        db, _as, _scope, storage = api
        locked = _locked_pdf_bytes()
        attachment = _attachment(
            db,
            storage,
            company_id=_SORENTO,
            filename="zzt-a4-locked.pdf",
            mime_type="application/pdf",
            data=locked,
        )

        with TestClient(app) as c:
            res = _from_attachment(c, attachment.id)

        assert res.status_code == 400, res.text
        assert res.json().get("code") == "FLYER_PASSWORD_PROTECTED"

    def test_ac_a4_oversized_is_refused_from_the_recorded_size_before_fetching_bytes(
        self, api, monkeypatch
    ) -> None:
        """The recorded size alone is enough to refuse - the fetch must never
        happen. Downloading first and refusing after is the version of this that
        costs money.
        """
        import app.services.resources_service as resources_service
        from app.services.dealer_kit import flyer_reading_service as svc

        db, _as, _scope, storage = api
        monkeypatch.setattr(svc, "MAX_UPLOAD_BYTES", 100 * 1024)

        # ``get_file_content_for`` and not ``get_file_content``: the route holds
        # the row already and fetches through the preloaded variant, so spying on
        # the id-taking wrapper would record nothing and pass vacuously.
        calls: list[str] = []
        original = resources_service.AttachmentService.get_file_content_for

        def _spy(self, attachment):
            calls.append(str(attachment.id))
            return original(self, attachment)

        monkeypatch.setattr(
            resources_service.AttachmentService, "get_file_content_for", _spy
        )

        attachment = _attachment(
            db,
            storage,
            company_id=_SORENTO,
            filename="zzt-a4-oversized-recorded.pdf",
            recorded_size=200 * 1024,  # over the 100 KB test ceiling
        )

        with TestClient(app) as c:
            res = _from_attachment(c, attachment.id)

        assert res.status_code == 413, res.text
        assert res.json().get("code") == "FLYER_TOO_LARGE"
        assert calls == [], "the bytes must never be fetched once the recorded size refuses it"

    def test_ac_a4_a_lying_recorded_size_is_still_caught_on_the_real_bytes(
        self, api, monkeypatch
    ) -> None:
        """The recorded size UNDERSTATES the real size (metadata drift). The
        first check passes, the bytes ARE fetched, and the second
        `assert_within_limit` on the real length still refuses it - matching
        what the upload path does on the actual wire bytes.
        """
        import app.services.resources_service as resources_service
        from app.services.dealer_kit import flyer_reading_service as svc

        db, _as, _scope, storage = api
        monkeypatch.setattr(svc, "MAX_UPLOAD_BYTES", 100 * 1024)

        # ``get_file_content_for`` and not ``get_file_content``: the route holds
        # the row already and fetches through the preloaded variant, so spying on
        # the id-taking wrapper would record nothing and pass vacuously.
        calls: list[str] = []
        original = resources_service.AttachmentService.get_file_content_for

        def _spy(self, attachment):
            calls.append(str(attachment.id))
            return original(self, attachment)

        monkeypatch.setattr(
            resources_service.AttachmentService, "get_file_content_for", _spy
        )

        # Real fixture is ~420 KB; recorded size lies and says it is tiny.
        attachment = _attachment(
            db,
            storage,
            company_id=_SORENTO,
            filename="zzt-a4-lying-size.pdf",
            recorded_size=1024,
        )

        with TestClient(app) as c:
            res = _from_attachment(c, attachment.id)

        assert res.status_code == 413, res.text
        assert res.json().get("code") == "FLYER_TOO_LARGE"
        assert calls == [attachment.id], "the real bytes must still be fetched and re-checked"


# --------------------------------------------------------------------------- #
# Edge cases: malformed input and an unreadable store
# --------------------------------------------------------------------------- #
class TestEdgeCases:
    def test_a_malformed_attachment_id_is_422_at_the_edge(self, api) -> None:
        _db, _as, _scope, _storage = api

        with TestClient(app) as c:
            res = c.post(
                "/api/v1/dealer-kit/flyer-readings/from-attachment",
                json={"attachmentId": "not-a-uuid"},
            )

        assert res.status_code == 422, res.text

    def test_a_storage_download_failure_is_a_502_not_a_bare_500(self, api) -> None:
        db, _as, _scope, storage = api
        attachment = _attachment(
            db, storage, company_id=_SORENTO, filename="zzt-a4-unreadable.pdf"
        )
        storage.downloading_fails = True

        with TestClient(app) as c:
            res = _from_attachment(c, attachment.id)

        assert res.status_code == 502, res.text
        assert res.json().get("code") == "FLYER_SOURCE_UNREADABLE"

    def test_a_row_with_no_stored_copy_is_a_422_not_a_502(self, api) -> None:
        """A row with no ``file_path`` is the caller's data problem, not the
        bucket's: nothing was ever uploaded, so retrying a download can never
        succeed. That is a 422 ``FLYER_SOURCE_MISSING`` telling the designer to
        upload the flyer from their computer instead - distinct from the 502
        above, where the bytes exist but the fetch itself failed and a retry
        might work. Before this split both answered 502.
        """
        db, _as, _scope, storage = api
        attachment = _attachment(
            db, storage, company_id=_SORENTO, filename="zzt-a4-no-source.pdf"
        )
        attachment.file_path = ""
        db.add(attachment)
        db.commit()

        with TestClient(app) as c:
            res = _from_attachment(c, attachment.id)

        assert res.status_code == 422, res.text
        assert res.json().get("code") == "FLYER_SOURCE_MISSING"
