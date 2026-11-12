"""TOWN-PROJECT-CITY Phase 2 (red): `projects` section of the snapshot.

Contract: PLAN-town-project-city-11nov.md "Phase 2 contract" (`projects`). Postgres only.
"""
from __future__ import annotations

from datetime import date

import pytest

from app.main import app  # noqa: F401
from app.models.base import set_company_scope
from app.models.status import Status
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests._mc_lookup_seed import MOCHA_ID, seed_mocha
from tests._pg_fixture import blank_session
from tests.town._town_project_seed import funnel, project
from tests.town._town_seed import DAY, NOW


@pytest.fixture
def db():
    with blank_session() as s:
        set_company_scope(s, None)
        seed_mocha(s)
        yield s


@pytest.fixture
def ids(db):
    return funnel(db)


def _projects(db, company_id=DEFAULT_COMPANY_ID):
    from app.services.town.snapshot import build_snapshot

    return build_snapshot(db, company_id, DAY, now=NOW)["projects"]


def test_no_projects_is_an_empty_section_not_missing(db, ids):
    assert _projects(db) == {"open_count": 0, "more": 0, "dormant": 0, "sites": []}


def test_only_open_projects_are_sites_lost_and_won_never_appear(db, ids):
    keep = project(db, ids, code="ZZT-OPEN")
    project(db, ids, code="ZZT-LOST", outcome="lost", stage="lost")
    project(db, ids, code="ZZT-WON", outcome="won", stage="po_received")
    out = _projects(db)
    assert [s["code"] for s in out["sites"]] == ["ZZT-OPEN"]
    assert out["sites"][0]["key"] == keep.id
    assert out["open_count"] == 1
    assert out["dormant"] == 0


def test_dormant_is_counted_never_drawn(db, ids):
    project(db, ids, code="ZZT-OPEN")
    project(db, ids, code="ZZT-DORM1", outcome="dormant", stage="dormant")
    project(db, ids, code="ZZT-DORM2", outcome="dormant", stage="dormant")
    out = _projects(db)
    assert out["dormant"] == 2
    assert out["open_count"] == 1
    assert [s["code"] for s in out["sites"]] == ["ZZT-OPEN"]


@pytest.mark.parametrize("approval", ["draft", "pending", "resubmitted", "rejected"])
def test_unapproved_portal_registrations_are_excluded_everywhere(db, ids, approval):
    project(db, ids, code="ZZT-STAFF")
    project(db, ids, code="ZZT-PORTAL", approval=approval)
    project(db, ids, code="ZZT-PORTALD", approval=approval, outcome="dormant", stage="dormant")
    out = _projects(db)
    assert [s["code"] for s in out["sites"]] == ["ZZT-STAFF"]
    assert out["open_count"] == 1
    assert out["dormant"] == 0


def test_approved_portal_registration_is_included(db, ids):
    project(db, ids, code="ZZT-APPR", approval="approved")
    assert [s["code"] for s in _projects(db)["sites"]] == ["ZZT-APPR"]


def test_cap_is_thirty_with_the_rest_counted_in_more(db, ids):
    for i in range(33):
        project(db, ids, code=f"ZZT-P{i:03d}", value=f"{(i + 1) * 100}.00")
    out = _projects(db)
    assert len(out["sites"]) == 30
    assert out["open_count"] == 33
    assert out["more"] == 3
    # the three smallest values are the ones left out
    assert {s["code"] for s in out["sites"]} == {f"ZZT-P{i:03d}" for i in range(3, 33)}


def test_more_is_zero_under_the_cap(db, ids):
    for i in range(5):
        project(db, ids, code=f"ZZT-P{i}")
    assert _projects(db)["more"] == 0


def test_order_is_value_desc_nulls_last_then_code(db, ids):
    project(db, ids, code="ZZT-B", value="500.00")
    project(db, ids, code="ZZT-A", value="500.00")
    project(db, ids, code="ZZT-Z", value="9000.00")
    project(db, ids, code="ZZT-N2", value=None)
    project(db, ids, code="ZZT-N1", value=None)
    project(db, ids, code="ZZT-S", value="1.00")
    assert [s["code"] for s in _projects(db)["sites"]] == [
        "ZZT-Z", "ZZT-A", "ZZT-B", "ZZT-S", "ZZT-N1", "ZZT-N2",
    ]


def test_site_fields(db, ids):
    proj = project(
        db, ids, code="ZZT-F1", name="Residensi ZZT", stage="tendering", critical=True, state="Johor",
        value="1234.5", launch=date(2025, 3, 1), delivery_from=date(2028, 3, 1),
    )
    (site,) = _projects(db)["sites"]
    status = db.get(Status, ids["tendering"])
    assert site == {
        "key": proj.id, "name": "Residensi ZZT", "code": "ZZT-F1", "stage": "tendering",
        # crew pass (11 Nov): the label and colour the CRM shows, from the statuses row itself
        "stage_label": status.label, "stage_color": status.color_hex,
        "final_negotiation": True, "state": "Johor", "launch_date": "2025-03-01",
        "delivery_date": "2028-03-01", "estimated_value": "1234.50",
    }


def test_a_stage_the_map_does_not_know_still_carries_the_crm_label_and_colour(db, ids):
    """Dev runs funnel rungs no seed has (sponsorship_form, final_negotiation, sample_submission) and
    relabels seeded ones (specified reads "Quotation"): the site carries the statuses row's own label
    and colour, so the map shows exactly what the CRM shows."""
    import uuid

    seeded = db.get(Status, ids["quoted"])
    custom = Status(
        id=str(uuid.uuid4()), entity_type=seeded.entity_type, scope_id=seeded.scope_id, key="sponsorship_form",
        label="Sponsorship Form", color_hex="#7c3aed", sort_order=99,
    )
    db.add(custom)
    db.flush()
    seeded_spec = db.get(Status, ids["specified"])
    seeded_spec.label = "Quotation"
    db.flush()
    a = project(db, ids, code="ZZT-C1", value="2")
    a.status_id = custom.id
    project(db, ids, code="ZZT-C2", stage="specified", value="1")
    db.flush()
    sites = {s["code"]: s for s in _projects(db)["sites"]}
    assert (sites["ZZT-C1"]["stage"], sites["ZZT-C1"]["stage_label"], sites["ZZT-C1"]["stage_color"]) == (
        "sponsorship_form", "Sponsorship Form", "#7c3aed")
    assert sites["ZZT-C2"]["stage_label"] == "Quotation"


def test_a_site_with_no_stage_has_no_label(db, ids):
    project(db, ids, code="ZZT-NS", stage=None)
    site = _projects(db)["sites"][0]
    assert (site["stage"], site["stage_label"], site["stage_color"]) == (None, None, None)


def test_name_falls_back_to_title(db, ids):
    project(db, ids, code="ZZT-T", name=None, title="ZZT Long Legal Title Sdn Bhd Phase 2")
    assert _projects(db)["sites"][0]["name"] == "ZZT Long Legal Title Sdn Bhd Phase 2"


@pytest.mark.parametrize("stage", ["identified", "registered", "specified", "quoted", "tendering", "po_received"])
def test_stage_is_the_status_key(db, ids, stage):
    project(db, ids, code="ZZT-ST", stage=stage)
    site = _projects(db)["sites"][0]
    assert site["stage"] == stage
    assert site["final_negotiation"] is False


def test_open_project_on_po_received_is_still_a_site(db, ids):
    project(db, ids, code="ZZT-PO", stage="po_received", outcome="open")
    assert _projects(db)["sites"][0]["stage"] == "po_received"


def test_no_status_means_null_stage(db, ids):
    project(db, ids, code="ZZT-NS", stage=None)
    assert _projects(db)["sites"][0]["stage"] is None


@pytest.mark.parametrize("typed,expected", [
    ("Johor", "Johor"), ("johor", "Johor"), ("  PULAU PINANG ", "Pulau Pinang"),
    ("kuala lumpur", "Kuala Lumpur"), ("Atlantis", None), ("", None), (None, None),
    ("Johor Bahru", None),
])
def test_state_is_matched_to_my_state_case_insensitively_else_null(db, ids, typed, expected):
    project(db, ids, code="ZZT-S", state=typed)
    assert _projects(db)["sites"][0]["state"] == expected


def test_delivery_date_prefers_from_then_to_and_may_be_null(db, ids):
    project(db, ids, code="ZZT-D1", value="3.00", delivery_from=date(2027, 1, 2), delivery_to=date(2027, 6, 1))
    project(db, ids, code="ZZT-D2", value="2.00", delivery_to=date(2027, 6, 1))
    project(db, ids, code="ZZT-D3", value="1.00")
    sites = {s["code"]: s for s in _projects(db)["sites"]}
    assert sites["ZZT-D1"]["delivery_date"] == "2027-01-02"
    assert sites["ZZT-D2"]["delivery_date"] == "2027-06-01"
    assert sites["ZZT-D3"]["delivery_date"] is None
    assert sites["ZZT-D3"]["launch_date"] is None
    assert sites["ZZT-D3"]["estimated_value"] == "1.00"


def test_estimated_value_null_stays_null(db, ids):
    project(db, ids, code="ZZT-NV", value=None)
    assert _projects(db)["sites"][0]["estimated_value"] is None


def test_other_companys_projects_are_absent_and_counted_in_its_own_town(db, ids):
    project(db, ids, code="ZZT-SRT")
    project(db, ids, code="ZZT-MOCHA", company_id=MOCHA_ID)
    project(db, ids, code="ZZT-MDORM", company_id=MOCHA_ID, outcome="dormant", stage="dormant")
    srt, mocha = _projects(db), _projects(db, MOCHA_ID)
    assert [s["code"] for s in srt["sites"]] == ["ZZT-SRT"] and srt["dormant"] == 0
    assert [s["code"] for s in mocha["sites"]] == ["ZZT-MOCHA"] and mocha["dormant"] == 1
