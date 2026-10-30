"""PORTAL-P4-REQUESTS S2 red tests (owner Q6 a, P4-14): the complaint gets revision code.

Both surfaces run the same flows: the portal (`/api/v1/public/portal`) and the CRM
(`/api/v1/my-requests`). Flows and assumptions live in tests/_portal_p4_complaint_revision.py.
Today the complaint has no RevisionAdapter, so every revise answers 422 even when the setting
allows it: the "ok" flows fail there, the "refused" flows fail on the missing `revision` policy.
"""
from __future__ import annotations

import pytest

from tests import _portal_p4_complaint_revision as f
from tests._portal_p4_support import scene  # noqa: F401  (pytest fixture)

SURFACES = ["portal", "me"]


@pytest.mark.parametrize("surface", SURFACES)
def test_p4_14_complaint_revise_allowed_by_setting(scene, surface):
    f.flow_revise_ok(scene, getattr(scene, surface))


@pytest.mark.parametrize("surface", SURFACES)
def test_p4_14_complaint_revise_refused_when_type_disabled(scene, surface):
    f.flow_revise_refused_disabled(scene, getattr(scene, surface))


@pytest.mark.parametrize("surface", SURFACES)
def test_p4_14_complaint_revise_refused_when_status_not_allowed(scene, surface):
    f.flow_revise_refused_status(scene, getattr(scene, surface))


@pytest.mark.parametrize("surface", SURFACES)
def test_p4_14_complaint_revise_refused_at_cap(scene, surface):
    f.flow_revise_refused_cap(scene, getattr(scene, surface))
