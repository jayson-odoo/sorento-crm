"""PORTAL-P4-REQUESTS S0-B red tests: complaint written from the CRM through /api/v1/my-requests.

UAC P4-10 .. P4-17. Flows live in tests/_portal_p4_support.py. P4_CONTROL=1 re-points the same
flows at the portal route (a self-check of the staff steps; not part of the red run).
"""
from __future__ import annotations

from tests import _portal_p4_support as s
from tests._portal_p4_support import scene  # noqa: F401  (pytest fixture)

SPEC = s.SPECS["complaint"]


def test_p4_10_parity_with_the_portal(scene):
    s.flow_parity(scene, SPEC)


def test_p4_11_12_create_save_submit_then_staff_to_final(scene):
    s.flow_happy(scene, SPEC)


def test_p4_13_reject_then_resubmit_is_resubmitted(scene):
    s.flow_reject_resubmit(scene, SPEC)


def test_p4_14_revise_refused_for_a_complaint(scene):
    s.flow_revision_refused(scene, SPEC)


def test_p4_11_delete_and_edit_rules_match_the_portal(scene):
    s.flow_delete_and_edit_rules(scene, SPEC)


def test_p4_ownership_matches_the_portal_on_every_route(scene):
    s.flow_ownership(scene, SPEC)


def test_p4_comments_on_own_row(scene):
    s.flow_comments(scene, SPEC)


def test_p4_15_requestor_options_equal_the_portal(scene):
    s.flow_requestor_options(scene, SPEC)


def test_p4_17_impersonation_acts_as_the_salesperson(scene):
    s.flow_impersonation(scene, SPEC)
