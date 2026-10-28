"""Showroom walkthroughs: the panorama builder, the routes, and the build job.

`documentation/plans/dealer-kit/PLAN-showroom-walkthrough-28oct.md` and
`showroom-walkthrough-28oct-acceptance-criteria.md` are the contract.

Postgres only, on a blank scratch schema. Storage is the in-process fake; the
queue seam (`walkthrough_service._enqueue`) is replaced by a recorder and the
job runs inline on the test's own session.
"""
from __future__ import annotations

import tempfile
import uuid

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

# MUST be first app import - resolves a circular import in app.modules.runtime.guards
from app.main import app  # noqa: E402

from app.services.dealer_kit import panorama  # noqa: E402
from app.services.dealer_kit import walkthrough_service as svc  # noqa: E402
from app.tasks.walkthrough_tasks import build_stop  # noqa: E402

from tests._fake_storage import patch_storage
from tests._pg_fixture import blank_session, unique_code

BASE = "/api/v1/dealer-kit/walkthroughs"

_SORENTO = "00000000-0000-0000-0000-000000000001"
_ADMIN_ID = "5d2e8a17-3c94-4b60-9f21-7a8e1c4d6b03"
_ADMIN_ROLE = "8b1f4c62-9e37-4a05-b6d8-2c7a5e9f1d40"
_EDITOR_ID = "3e7c9b25-1d48-4f63-a0b7-6e2d8c5a9f14"
_EDITOR_ROLE = "6a4e1d83-7b29-4c50-8f36-9d1c3b7e5a28"
_VIEWER_ID = "9c3a7e51-4b86-4d02-b5f9-1e8d6a2c7b39"
_VIEWER_ROLE = "2f8d5b94-6c13-4e70-a8b2-5d9e1a3c6f47"
_NOPERM_ID = "7b5d2f68-8a41-4c93-9e06-3f1b7d4a8c52"


# --------------------------------------------------------------------------- #
# Synthetic showroom: a textured wall the "camera" pans across.
# --------------------------------------------------------------------------- #
def _scene() -> np.ndarray:
    rng = np.random.default_rng(7)
    scene = cv2.GaussianBlur((rng.random((600, 3600, 3)) * 255).astype(np.uint8), (5, 5), 0)
    for _ in range(60):
        x, y = int(rng.integers(0, 3500)), int(rng.integers(0, 550))
        colour = tuple(int(c) for c in rng.integers(0, 255, 3))
        cv2.rectangle(scene, (x, y), (x + 80, y + 40), colour, -1)
    return scene


def _jpeg(image: np.ndarray) -> bytes:
    return cv2.imencode(".jpg", image)[1].tobytes()


def _photos() -> list[tuple[str, bytes]]:
    scene = _scene()
    return [(f"shot-{i}.jpg", _jpeg(scene[:, x : x + 900])) for i, x in enumerate(range(0, 2701, 300))]


def _video() -> bytes:
    scene = _scene()
    with tempfile.NamedTemporaryFile(suffix=".mp4") as tmp:
        writer = cv2.VideoWriter(tmp.name, cv2.VideoWriter_fourcc(*"mp4v"), 10, (900, 600))
        for x in range(0, 2701, 50):
            writer.write(np.ascontiguousarray(scene[:, x : x + 900]))
        writer.release()
        with open(tmp.name, "rb") as handle:
            return handle.read()


class TestPanoramaBuilder:
    def test_overlapping_photos_stitch_into_one_wide_view(self) -> None:
        result = panorama.build_panorama(_photos())
        assert result.width > result.height * 4
        assert 200 < result.h_fov_deg <= 360
        assert cv2.imdecode(np.frombuffer(result.jpeg, np.uint8), cv2.IMREAD_COLOR) is not None

    def test_a_turn_on_the_spot_video_stitches(self) -> None:
        result = panorama.build_panorama([("turn.mp4", _video())])
        assert result.width > result.height * 4
        assert result.h_fov_deg > 200

    def test_a_2_to_1_photo_is_already_the_full_sphere(self) -> None:
        result = panorama.build_panorama([("pano.jpg", _jpeg(np.zeros((500, 1000, 3), np.uint8)))])
        assert (result.h_fov_deg, result.v_fov_deg) == (360.0, 180.0)

    def test_a_single_flat_photo_covers_one_frame(self) -> None:
        result = panorama.build_panorama([("one.jpg", _jpeg(np.zeros((600, 900, 3), np.uint8)))])
        assert result.h_fov_deg == pytest.approx(68.0, abs=0.1)
        assert result.v_fov_deg < result.h_fov_deg

    def test_photos_that_do_not_overlap_are_refused_in_words(self) -> None:
        shots = _photos()
        with pytest.raises(panorama.PanoramaError, match="overlap"):
            panorama.build_panorama([shots[0], shots[-1]])

    def test_bytes_that_are_not_media_are_refused_by_name(self) -> None:
        with pytest.raises(panorama.PanoramaError, match="broken.jpg"):
            panorama.build_panorama([("broken.jpg", b"not an image")])


# --------------------------------------------------------------------------- #
# Routes and job
# --------------------------------------------------------------------------- #
def _seed_roles(db) -> None:
    from app.models.user import (
        User,
        UserPermission,
        UserRole,
        UserRoleAssignment,
        UserRolePermission,
    )

    roles = {
        _ADMIN_ROLE: "superadmin",
        _EDITOR_ROLE: "zzt_walkthrough_editor",
        _VIEWER_ROLE: "zzt_walkthrough_viewer",
    }
    for role_id, slug in roles.items():
        db.add(
            UserRole(
                id=role_id,
                slug=slug,
                name=slug,
                description="",
                is_protected=slug == "superadmin",
                is_default=False,
            )
        )
    users = {
        _ADMIN_ID: _ADMIN_ROLE,
        _EDITOR_ID: _EDITOR_ROLE,
        _VIEWER_ID: _VIEWER_ROLE,
        _NOPERM_ID: None,
    }
    for user_id in users:
        db.add(User(id=user_id, email=f"zzt-wt-{user_id[:8]}@test.com", name="WT", status="ACTIVE"))
    db.flush()
    for user_id, role_id in users.items():
        if role_id:
            db.add(UserRoleAssignment(user_id=user_id, role_id=role_id))

    grants = {
        "dealer_kit.page.view": (_EDITOR_ROLE, _VIEWER_ROLE),
        "dealer_kit.page.edit": (_EDITOR_ROLE,),
    }
    for slug, role_ids in grants.items():
        perm_id = str(uuid.uuid4())
        db.add(UserPermission(id=perm_id, slug=slug, name=slug, description=""))
        db.flush()
        for role_id in role_ids:
            db.add(UserRolePermission(id=str(uuid.uuid4()), role_id=role_id, permission_id=perm_id))
    db.commit()


class InlineBuild:
    def __init__(self, db) -> None:
        self.db = db
        self.queued: list[tuple[str, list[list[str]]]] = []
        self.fail_enqueue = False

    def __call__(self, stop, staged):
        if self.fail_enqueue:
            raise RuntimeError("redis is down")
        self.queued.append((str(stop.id), staged))
        return f"zzt-job-{len(self.queued)}"

    def run_pending(self) -> list[dict]:
        pending, self.queued = self.queued, []
        return [build_stop(stop_id, staged, _db=self.db) for stop_id, staged in pending]


@pytest.fixture
def api(monkeypatch):
    from app.dependencies import get_current_user, get_current_user_or_api_key, get_db
    from app.models.base import set_company_scope
    from app.services.company_scope_resolver import apply_company_scope

    with blank_session() as db:
        _seed_roles(db)
        storage = patch_storage(monkeypatch)
        builds = InlineBuild(db)
        monkeypatch.setattr(svc, "_enqueue", builds)
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
        set_company_scope(db, frozenset({_SORENTO}))
        yield {"db": db, "storage": storage, "builds": builds, "as": _as, "in_company": _in_company}

        app.dependency_overrides.clear()


def _create(client: TestClient, name: str = "ZZT Showroom") -> dict:
    response = client.post(BASE, json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()


def _add_stop(client: TestClient, walkthrough_id: str, files, title: str = "Entrance"):
    return client.post(
        f"{BASE}/{walkthrough_id}/stops",
        data={"title": title},
        files=[("files", (name, data, "application/octet-stream")) for name, data in files],
    )


def _other_company(db) -> str:
    from app.models.company import Company

    company = Company(
        id=str(uuid.uuid4()),
        name=unique_code("ZZT Other Co"),
        code=unique_code("ZZTWT")[:20],
        is_active=True,
    )
    db.add(company)
    db.commit()
    return company.id


class TestWalkthroughLifecycle:
    def test_photos_become_a_done_stop_with_a_panorama(self, api) -> None:
        with TestClient(app) as c:
            walkthrough = _create(c)
            accepted = _add_stop(c, walkthrough["id"], _photos())
            assert accepted.status_code == 202, accepted.text
            stop = accepted.json()
            assert stop["status"] == "processing"
            assert stop["position"] == 1
            assert stop["title"] == "Entrance"

            staged_keys = [key for _p, key, _f in api["builds"].queued[0][1]]
            assert all(key in api["storage"].objects for key in staged_keys)

            assert [r["status"] for r in api["builds"].run_pending()] == ["done"]
            # Staged uploads go once the job ends.
            assert not any(key in api["storage"].objects for key in staged_keys)

            detail = c.get(f"{BASE}/{walkthrough['id']}").json()
            assert detail["stopCount"] == 1
            assert detail["processingCount"] == 0
            done = detail["stops"][0]
            assert done["status"] == "done"
            assert done["hFovDeg"] > 200

            image = c.get(f"{BASE}/{walkthrough['id']}/stops/{done['id']}/panorama")
            assert image.status_code == 200
            assert image.headers["content-type"] == "image/jpeg"
            assert image.content[:2] == b"\xff\xd8"

    def test_stops_are_numbered_in_upload_order(self, api) -> None:
        one_photo = [("pano.jpg", _jpeg(np.zeros((500, 1000, 3), np.uint8)))]
        with TestClient(app) as c:
            walkthrough = _create(c)
            first = _add_stop(c, walkthrough["id"], one_photo, title="").json()
            second = _add_stop(c, walkthrough["id"], one_photo, title="Kitchen").json()
            assert (first["position"], first["title"]) == (1, "Stop 1")
            assert (second["position"], second["title"]) == (2, "Kitchen")

    def test_a_stop_that_cannot_be_stitched_fails_with_the_reason(self, api) -> None:
        shots = _photos()
        with TestClient(app) as c:
            walkthrough = _create(c)
            stop = _add_stop(c, walkthrough["id"], [shots[0], shots[-1]]).json()
            api["builds"].run_pending()
            detail = c.get(f"{BASE}/{walkthrough['id']}").json()
            failed = detail["stops"][0]
            assert failed["status"] == "failed"
            assert "overlap" in failed["errorMessage"]
            panorama_response = c.get(f"{BASE}/{walkthrough['id']}/stops/{stop['id']}/panorama")
            assert panorama_response.status_code == 409

    def test_a_queue_outage_reads_as_failed_not_processing(self, api) -> None:
        api["builds"].fail_enqueue = True
        with TestClient(app) as c:
            walkthrough = _create(c)
            stop = _add_stop(c, walkthrough["id"], _photos()[:2])
            assert stop.status_code == 202
            assert stop.json()["status"] == "failed"
            assert "queue" in stop.json()["errorMessage"]
        assert not any(k.startswith(svc.STAGING_PREFIX) for k in api["storage"].objects)

    def test_unsupported_files_are_refused_before_anything_is_stored(self, api) -> None:
        with TestClient(app) as c:
            walkthrough = _create(c)
            refused = _add_stop(c, walkthrough["id"], [("plan.pdf", b"%PDF-1.4")])
            assert refused.status_code == 400
            assert "plan.pdf" in refused.json()["message"]
        assert api["storage"].objects == {}

    def test_rename_and_list(self, api) -> None:
        with TestClient(app) as c:
            walkthrough = _create(c, "ZZT Old name")
            renamed = c.patch(f"{BASE}/{walkthrough['id']}", json={"name": "ZZT New name"})
            assert renamed.status_code == 200
            names = [row["name"] for row in c.get(BASE).json()]
            assert "ZZT New name" in names
            assert c.post(BASE, json={"name": "   "}).status_code == 422

    def test_deleting_a_walkthrough_takes_its_panoramas(self, api) -> None:
        with TestClient(app) as c:
            walkthrough = _create(c)
            _add_stop(c, walkthrough["id"], _photos())
            api["builds"].run_pending()
            assert any(k.startswith(svc.PANORAMA_PREFIX) for k in api["storage"].objects)
            assert c.delete(f"{BASE}/{walkthrough['id']}").status_code == 204
            assert c.get(f"{BASE}/{walkthrough['id']}").status_code == 404
        assert not any(k.startswith(svc.PANORAMA_PREFIX) for k in api["storage"].objects)

    def test_deleting_a_stop_keeps_the_others(self, api) -> None:
        one_photo = [("pano.jpg", _jpeg(np.zeros((500, 1000, 3), np.uint8)))]
        with TestClient(app) as c:
            walkthrough = _create(c)
            first = _add_stop(c, walkthrough["id"], one_photo).json()
            _add_stop(c, walkthrough["id"], one_photo)
            api["builds"].run_pending()
            assert c.delete(f"{BASE}/{walkthrough['id']}/stops/{first['id']}").status_code == 204
            assert [s["position"] for s in c.get(f"{BASE}/{walkthrough['id']}").json()["stops"]] == [2]

    def test_a_stop_deleted_mid_build_is_left_alone(self, api) -> None:
        with TestClient(app) as c:
            walkthrough = _create(c)
            stop = _add_stop(c, walkthrough["id"], _photos()[:3]).json()
            svc.delete_stop(api["db"], stop["id"])
            assert [r["status"] for r in api["builds"].run_pending()] == ["gone"]
        assert not any(k.startswith(svc.PANORAMA_PREFIX) for k in api["storage"].objects)


class TestAccess:
    def test_a_viewer_may_look_but_not_change(self, api) -> None:
        with TestClient(app) as c:
            walkthrough = _create(c)
        api["as"](_VIEWER_ID)
        with TestClient(app) as c:
            assert c.get(BASE).status_code == 200
            assert c.get(f"{BASE}/{walkthrough['id']}").status_code == 200
            assert c.post(BASE, json={"name": "ZZT"}).status_code == 403
            assert _add_stop(c, walkthrough["id"], _photos()[:2]).status_code == 403
            assert c.delete(f"{BASE}/{walkthrough['id']}").status_code == 403

    def test_an_editor_may_build(self, api) -> None:
        api["as"](_EDITOR_ID)
        with TestClient(app) as c:
            walkthrough = _create(c)
            assert _add_stop(c, walkthrough["id"], _photos()[:2]).status_code == 202

    def test_a_stranger_is_refused(self, api) -> None:
        api["as"](_NOPERM_ID)
        with TestClient(app) as c:
            assert c.get(BASE).status_code == 403


class TestCompanyScope:
    def test_another_companys_walkthrough_is_absent_not_forbidden(self, api) -> None:
        with TestClient(app) as c:
            walkthrough = _create(c)
            stop = _add_stop(c, walkthrough["id"], _photos()[:2]).json()
        api["in_company"](_other_company(api["db"]))
        with TestClient(app) as c:
            assert c.get(f"{BASE}/{walkthrough['id']}").status_code == 404
            assert walkthrough["id"] not in [row["id"] for row in c.get(BASE).json()]
            assert c.get(f"{BASE}/{walkthrough['id']}/stops/{stop['id']}/panorama").status_code == 404
            assert c.delete(f"{BASE}/{walkthrough['id']}/stops/{stop['id']}").status_code == 404
