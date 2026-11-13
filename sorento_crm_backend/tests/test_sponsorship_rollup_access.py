"""PROJECT-RELATED-RECORDS fix round 3 (browser pass 1 D4, AC-B2): the project's sponsorship spend
line follows the same rule as the sponsorship rows on the Related tab (`own_scope.request_access`
for `sponsorship_form`): no sponsorship read -> 403; view_own -> the totals of their own forms only;
view -> every form. Postgres only; fake values (marker `zzt-prr`).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from tests._own_scope_support import acting, contact, user

from .test_project_related_records import (
    CX_VIEW,
    P_VIEW,
    SF_OWN,
    SF_VIEW,
    _request,
    scene,  # noqa: F401  (fixture)
)


def _url(project_id) -> str:
    return f"/api/v1/project-sales/projects/{project_id}/sponsorships/rollup"


def test_d4_no_sponsorship_read_is_refused(scene):  # noqa: F811
    db, p = scene["db"], scene["p"]
    with acting(db, user(db, "No SF"), {P_VIEW, CX_VIEW}) as client:
        response = client.get(_url(p.id))
    assert response.status_code == 403, response.text


def test_d4_view_sees_every_form(scene):  # noqa: F811
    db, p = scene["db"], scene["p"]
    mine = contact(db, "SF mine")
    _request(db, p.id, "sponsorship_form", request_number="ZZT-SF-MINE", contact_id=mine.id,
             request_date=date(2026, 6, 1), total_project_value=Decimal("500.00"))
    with acting(db, user(db, "SF all"), {P_VIEW, SF_VIEW}) as client:
        body = client.get(_url(p.id)).json()
    assert Decimal(str(body["total"])) == Decimal("1700.00"), body
    assert body["form_count"] == 2


def test_d4_view_own_sees_only_their_own_forms(scene):  # noqa: F811
    db, p = scene["db"], scene["p"]
    mine = contact(db, "SF own")
    me = user(db, "SF limited", mine.id)
    _request(db, p.id, "sponsorship_form", request_number="ZZT-SF-OWN", contact_id=mine.id,
             request_date=date(2026, 6, 1), total_project_value=Decimal("500.00"))
    with acting(db, me, {P_VIEW, SF_OWN}) as client:
        response = client.get(_url(p.id))
    assert response.status_code == 200, response.text
    body = response.json()
    assert Decimal(str(body["total"])) == Decimal("500.00"), body
    assert body["form_count"] == 1
    assert [y["year"] for y in body["by_year"]] == [2026]
