"""Test-only helper: bypass the /external permission guard.

Several /external suites are *route-behaviour* tests -- they override
``get_external_api_user`` with a stub principal and ``get_db`` with a MagicMock,
because the point is the handler's logic, not authentication. Since AC-AC-05
added a real RBAC check to every external route, that mocked database cannot
answer the permission lookup, so every such route denies.

Granting the permission explicitly keeps those tests honest: they state that
authorization is deliberately out of scope, rather than silently depending on
there having been no check. Enforcement itself is covered by
``test_external_permission_guard`` (behaviour) and
``test_external_permission_coverage`` (every route is guarded at all).

Do NOT use this in a test that is about authorization.
"""
from contextlib import contextmanager
from unittest.mock import patch


@contextmanager
def external_permissions_granted():
    """Treat the caller as holding whatever permission the route requires."""
    with patch("app.api.v1.external.permissions.UserPermissionService") as service:
        service.return_value.check_user_has_permission.return_value = True
        yield
