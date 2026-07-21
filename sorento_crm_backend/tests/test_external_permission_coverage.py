"""Every /external route enforces a permission — checked structurally.

A per-endpoint test can only cover the endpoints someone remembered to write a
test for. The failure mode that matters here is *omission*: a new router mounted
without a guard, reachable by any key holder, with nothing failing to say so.

These tests inspect the mounted application itself, so a route added tomorrow is
covered by construction.
"""
import pytest

import app.main  # noqa: F401  isort:skip

from app.api.v1.external import router as external_router
from app.api.v1.external.permissions import EXTERNAL_ENDPOINT_PERMISSIONS
from app.main import app as fastapi_app
from app.rbac.permission_registry import PERMISSION_REGISTRY

# Prefixes whose permission is resolved from the path at request time,
# because one route serves several entities with different slugs. Kept as an
# explicit allowlist so adding one is a deliberate act, not an oversight.
PATH_RESOLVED_PREFIXES = {"ingest", "read"}


def _external_routes():
    return [
        r
        for r in fastapi_app.routes
        if getattr(r, "path", "").startswith("/api/v1/external/")
    ]


class TestCoverage:
    def test_there_are_external_routes_to_check(self):
        # Guards the tests below against silently passing on an empty set.
        assert len(_external_routes()) > 20

    def test_every_external_route_carries_a_permission_dependency(self):
        unguarded = []
        for route in _external_routes():
            deps = getattr(route, "dependencies", []) or []
            names = [getattr(d.dependency, "__qualname__", "") for d in deps]
            if not any("require_external_permission" in n for n in names):
                unguarded.append(route.path)
        assert not unguarded, f"external routes without a permission guard: {unguarded}"

    def test_every_mounted_prefix_has_a_mapping_entry(self):
        # The guard is applied by looking the prefix up in the map, so a missing
        # entry would be a KeyError at import -- but assert it explicitly so the
        # failure names the gap instead of a traceback.
        mounted = set()
        for route in _external_routes():
            tail = route.path[len("/api/v1/external/") :]
            if tail:
                mounted.add(tail.split("/")[0])

        mapped = {k.split("/")[0] for k in EXTERNAL_ENDPOINT_PERMISSIONS}
        # These serve several entities from one route, so their slug is resolved
        # from the path at request time rather than fixed at mount. Listed
        # explicitly, and their maps are asserted below -- an unguarded router
        # cannot hide here just by being named 'ingest'.
        assert mounted <= mapped | PATH_RESOLVED_PREFIXES, (
            f"mounted but unmapped: {sorted(mounted - mapped - PATH_RESOLVED_PREFIXES)}"
        )

    def test_path_resolved_routes_cover_every_entity_they_serve(self):
        # The escape hatch above is only safe if these maps are complete: an
        # entity present in ingest but missing from the permission map would be
        # refused at runtime, which is safe, but silently unreachable.
        from app.api.v1.external.ingest import INGEST_PERMISSIONS, READ_PERMISSIONS
        from app.services.master_ingest_service import ENTITY_SPECS

        assert set(INGEST_PERMISSIONS) == set(ENTITY_SPECS)
        assert set(READ_PERMISSIONS) == set(ENTITY_SPECS)

    def test_ingest_and_read_use_different_slugs_per_entity(self):
        # Writing a warehouse must not be authorised by the products slug.
        from app.api.v1.external.ingest import INGEST_PERMISSIONS, READ_PERMISSIONS

        assert len(set(INGEST_PERMISSIONS.values())) == len(INGEST_PERMISSIONS)
        assert len(set(READ_PERMISSIONS.values())) == len(READ_PERMISSIONS)
        # ...and reading must not require the write permission.
        for entity, write_slug in INGEST_PERMISSIONS.items():
            assert READ_PERMISSIONS[entity] != write_slug


class TestSlugsAreReal:
    def test_every_mapped_slug_exists_in_the_registry(self):
        # A guard referencing a slug that no role can ever hold is a permanent
        # 403 -- the feature would look broken rather than protected.
        known = {p["slug"] for p in PERMISSION_REGISTRY}
        unknown = {v for v in EXTERNAL_ENDPOINT_PERMISSIONS.values() if v not in known}
        assert not unknown, f"mapped to non-existent permission slugs: {sorted(unknown)}"

    def test_no_route_is_mapped_to_an_empty_slug(self):
        assert all(v and v.strip() for v in EXTERNAL_ENDPOINT_PERMISSIONS.values())
