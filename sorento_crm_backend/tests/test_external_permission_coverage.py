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
        assert mounted <= mapped, f"mounted but unmapped: {sorted(mounted - mapped)}"


class TestSlugsAreReal:
    def test_every_mapped_slug_exists_in_the_registry(self):
        # A guard referencing a slug that no role can ever hold is a permanent
        # 403 -- the feature would look broken rather than protected.
        known = {p["slug"] for p in PERMISSION_REGISTRY}
        unknown = {v for v in EXTERNAL_ENDPOINT_PERMISSIONS.values() if v not in known}
        assert not unknown, f"mapped to non-existent permission slugs: {sorted(unknown)}"

    def test_no_route_is_mapped_to_an_empty_slug(self):
        assert all(v and v.strip() for v in EXTERNAL_ENDPOINT_PERMISSIONS.values())
