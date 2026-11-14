"""PROJECT-RELATED-RECORDS red tests: the related-records endpoint and its registry.

UAC: documentation/plans/project-sales/project-related-records-12nov-acceptance-criteria.md
Contract: documentation/plans/project-sales/CONTRACT-project-related-records.md (sections 5, 6).

`GET /api/v1/project-sales/projects/{project_id}/related-records` lists every purchase request,
sponsorship form, complaint, stock inquiry and new product application whose `project_id` is the
project, one line per row, sorted, searched, filtered and paged on the server. Each type follows
the viewer's own request rule (`own_scope.request_access`).

Postgres only (`blank_session`); every row is seeded here with fake values (marker `zzt-prr`).
Every test cites its AC id.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

import pytest

from app.models.base import company_scope
from app.models.procurement import PurchaseRequestLine
from app.models.projects import Project

from ._own_scope_support import acting, contact, sorento, uid, user
from ._pg_fixture import blank_session

MARKER = "zzt-prr"
BASE = "/api/v1/project-sales"

P_VIEW = "projects.projects.view"
P_VIEW_OWN = "projects.projects.view_own"

SI_VIEW, SI_OWN = "procurement.stock_inquiries.view", "procurement.stock_inquiries.view_own"
CX_VIEW, CX_OWN = (
    "complaint_management.complaints.view",
    "complaint_management.complaints.view_own",
)
PR_VIEW, PR_OWN = "procurement.purchase_requests.view", "procurement.purchase_requests.view_own"
SF_VIEW, SF_OWN = "procurement.sponsorship_forms.view", "procurement.sponsorship_forms.view_own"
NPA_VIEW, NPA_OWN = (
    "procurement.new_product_applications.view",
    "procurement.new_product_applications.view_own",
)

ALL_TYPES_VIEW = {SI_VIEW, CX_VIEW, PR_VIEW, SF_VIEW, NPA_VIEW}
ALL_TYPES_OWN = {SI_OWN, CX_OWN, PR_OWN, SF_OWN, NPA_OWN}

KINDS = (
    "stock_inquiry",
    "complaint",
    "purchase_request",
    "sponsorship_form",
    "new_product_application",
)
LABELS = {
    "stock_inquiry": "Stock Inquiry",
    "complaint": "Complaint",
    "purchase_request": "Purchase request",
    "sponsorship_form": "Sponsorship form",
    "new_product_application": "New product application",
}

SORT_KEYS = ("type", "number", "status", "approval", "date", "raised_by", "subject", "value")


# ------------------------------------------------------------------ seeding


def _second_company(db) -> str:
    from sqlalchemy import text

    company_id = uid()
    db.execute(
        text("insert into companies (id, code, name, is_active) values (:i, :c, :n, true)"),
        {"i": company_id, "c": f"Z{uuid.uuid4().hex}".upper(), "n": f"{MARKER} other co"},
    )
    db.flush()
    return company_id


def _project(db, company_id: str, owner: str | None, *, approval_state=None) -> Project:
    tag = uuid.uuid4().hex[:6]
    row = Project(
        id=uid(),
        company_id=company_id,
        project_code=f"ZZT-PRR-{tag}",
        title=f"{MARKER} Project {tag}",
        normalised_title=f"{MARKER} project {tag}",
        owner_user_id=owner,
        approval_state=approval_state,
    )
    db.add(row)
    db.flush()
    return row


def _si(db, project_id, **kw):
    from app.models.procurement import StockInquiry

    values = dict(
        id=uid(),
        inquiry_number=f"ZZT-SIX-{uuid.uuid4().hex[:6]}",
        status="new",
        salesperson=f"{MARKER} someone",
        item_description=f"{MARKER} other item",
        project_id=project_id,
    )
    values.update(kw)
    row = StockInquiry(**values)
    db.add(row)
    db.flush()
    return row


def _complaint(db, project_id, **kw):
    from app.models.complaints import Complaint

    values = dict(
        id=uid(),
        complaint_number=f"ZZT-CXX-{uuid.uuid4().hex[:6]}",
        complaint_date=date(2026, 1, 1),
        status="submitted",
        salesperson=f"{MARKER} someone",
        defect_description=f"{MARKER} other defect",
        project_id=project_id,
    )
    values.update(kw)
    row = Complaint(**values)
    db.add(row)
    db.flush()
    return row


def _request(db, project_id, kind: str, **kw):
    from app.models.procurement import PurchaseRequestHeader

    values = dict(
        id=uid(),
        request_type=kind,
        request_number=f"ZZT-RQX-{uuid.uuid4().hex[:6]}",
        request_date=date(2026, 1, 1),
        status="submitted",
        requested_by=f"{MARKER} someone",
        project_id=project_id,
    )
    values.update(kw)
    row = PurchaseRequestHeader(**values)
    db.add(row)
    db.flush()
    return row


def _npa(db, company_id: str, project_id, **kw):
    from app.models.new_product_application import NewProductApplication

    values = dict(
        id=uid(),
        company_id=company_id,
        application_no=f"NPA-{uuid.uuid4().int % 10**6:06d}",
        status="submitted",
        project_id=project_id,
    )
    values.update(kw)
    row = NewProductApplication(**values)
    db.add(row)
    db.flush()
    return row


#: The five linked rows, one per kind, with every sortable value distinct so each sort key has
#: one right answer. `raised_by` of the NPA is its applicant user's name.
EXPECTED = {
    "stock_inquiry": dict(
        number="ZZT-SI-0001", status="responded", approval_status=None,
        date="2026-01-10", raised_by="Zack Salesperson", subject="zzt-prr basin mixer", value=None,
    ),
    "complaint": dict(
        number="ZZT-CX-0001", status="submitted", approval_status=None,
        date="2026-02-10", raised_by="Amy Salesperson", subject="zzt-prr cracked tile", value=None,
    ),
    "purchase_request": dict(
        number="ZZT-PR-0001", status="processed_by_cs", approval_status="approved",
        date="2026-03-10", raised_by="Ben Requester", subject="zzt-prr tower lobby", value=Decimal("5000.00"),
    ),
    "sponsorship_form": dict(
        number="ZZT-SF-0001", status="approved", approval_status="pending",
        # What the form SPONSORS (its lines' Grand total: 150.00 + 2 x 25.00), never the project's
        # value it also carries (1200.00), as the retired Sponsorship Form tab showed it
        # (PROJECT-STAGE-ACTIONS, crew pass round 2).
        date="2026-04-10", raised_by="Cara Requester", subject="zzt-prr launch event", value=Decimal("200.00"),
    ),
    "new_product_application": dict(
        number="NPA-990001", status="completed", approval_status=None,
        date="2026-05-10", raised_by="Dina Applicant", subject="zzt-prr new sink", value=Decimal("300.00"),
    ),
}


@pytest.fixture()
def scene():
    """Project P (company SRT, owner `owner`) with one row of each kind linked; noise rows that
    must never show: unlinked rows, rows linked to P2 (same company), rows linked to Q (another
    company)."""
    with blank_session() as db:
        company_id = sorento(db)
        other_company = _second_company(db)
        owner = user(db, "Owner")
        applicant = user(db, "x")
        from app.models.user import User

        db.get(User, applicant).name = "Dina Applicant"
        db.flush()

        q = _project(db, other_company, owner)
        q_si = _si(db, q.id, inquiry_number="ZZT-SI-Q", item_description=f"{MARKER} foreign item")
        _npa(db, other_company, q.id, application_no="NPA-990099")

        with company_scope(db, frozenset({company_id})):
            p = _project(db, company_id, owner)
            p2 = _project(db, company_id, owner)
            e = EXPECTED
            rows = {
                "stock_inquiry": _si(
                    db, p.id, inquiry_number=e["stock_inquiry"]["number"], status="responded",
                    salesperson="Zack Salesperson", item_description="zzt-prr basin mixer",
                    created_at=datetime(2026, 1, 10, 9, 30),
                ),
                "complaint": _complaint(
                    db, p.id, complaint_number=e["complaint"]["number"], status="submitted",
                    complaint_date=date(2026, 2, 10), salesperson="Amy Salesperson",
                    defect_description="zzt-prr cracked tile",
                ),
                "purchase_request": _request(
                    db, p.id, "purchase_request", request_number=e["purchase_request"]["number"],
                    status="processed_by_cs", approval_status="approved",
                    request_date=date(2026, 3, 10), requested_by="Ben Requester",
                    project_title="zzt-prr tower lobby", total_project_value=Decimal("5000.00"),
                ),
                "sponsorship_form": _request(
                    db, p.id, "sponsorship_form", request_number=e["sponsorship_form"]["number"],
                    status="approved", approval_status="pending", request_date=date(2026, 4, 10),
                    requested_by="Cara Requester", purpose="zzt-prr launch event",
                    total_project_value=Decimal("1200.00"),
                    lines=[
                        PurchaseRequestLine(item_code="ZZT-1", quantity=Decimal("1"), total=Decimal("150.00"), sort_order=0),
                        # No total: quantity x unit price counts.
                        PurchaseRequestLine(item_code="ZZT-2", quantity=Decimal("2"), unit_price=Decimal("25.00"), sort_order=1),
                    ],
                ),
                "new_product_application": _npa(
                    db, company_id, p.id, application_no=e["new_product_application"]["number"],
                    status="completed", applicant_id=applicant, remark="zzt-prr new sink",
                    cost_price=Decimal("300.00"), submitted_at=datetime(2026, 5, 10, 14, 0),
                    created_at=datetime(2026, 5, 1, 8, 0),
                ),
            }
            noise = [
                _si(db, None, inquiry_number="ZZT-SI-NONE"),
                _complaint(db, None, complaint_number="ZZT-CX-NONE"),
                _request(db, None, "purchase_request", request_number="ZZT-PR-NONE"),
                _request(db, p2.id, "sponsorship_form", request_number="ZZT-SF-P2"),
                _npa(db, company_id, p2.id, application_no="NPA-990002"),
                _npa(db, company_id, None, application_no="NPA-990003"),
            ]
            db.flush()
            yield {
                "db": db, "company_id": company_id, "owner": owner, "p": p, "p2": p2, "q": q,
                "q_si": q_si, "rows": rows, "noise": noise,
            }


def _url(project_id: str) -> str:
    return f"{BASE}/projects/{project_id}/related-records"


def _get(client, project_id: str, **params):
    response = client.get(_url(project_id), params={"limit": 100, **params})
    assert response.status_code == 200, response.text
    return response.json()


def _mounted(response) -> None:
    """A 404 must come from the app (project not visible), not from the route being absent."""
    assert response.json() != {"detail": "Not Found"}, "route not mounted"


def _viewer(db) -> str:
    return user(db, "Viewer")


#: Fix round 2 (security B2): the NPA Value is its cost price, so the readers these tests pin the
#: Value of hold `products.cost.view`; tests/test_project_related_cost.py covers the reader without it.
FULL = {P_VIEW, "products.cost.view"} | ALL_TYPES_VIEW


# ------------------------------------------------------------------ AC-A3, AC-A4: the rows


def test_ac_a3_every_kind_linked_to_the_project_is_listed_with_its_columns(scene):
    db, p = scene["db"], scene["p"]
    with acting(db, _viewer(db), FULL) as client:
        body = _get(client, p.id)
    by_kind = {row["kind"]: row for row in body["data"]}
    assert sorted(by_kind) == sorted(KINDS), body["data"]
    assert body["pagination"]["total"] == 5
    for kind, expected in EXPECTED.items():
        row = by_kind[kind]
        assert row["id"] == str(scene["rows"][kind].id), kind
        assert row["number"] == expected["number"], kind
        assert row["status"] == expected["status"], kind
        assert row["approval_status"] == expected["approval_status"], kind
        assert row["date"] == expected["date"], kind
        assert row["raised_by"] == expected["raised_by"], kind
        assert row["subject"] == expected["subject"], kind
        got_value = None if row["value"] is None else Decimal(str(row["value"]))
        assert got_value == expected["value"], kind


def test_ac_a3_unlinked_rows_and_rows_of_other_projects_are_absent(scene):
    db, p = scene["db"], scene["p"]
    with acting(db, _viewer(db), FULL) as client:
        body = _get(client, p.id)
    ids = {row["id"] for row in body["data"]}
    numbers = {row["number"] for row in body["data"]}
    for noise in scene["noise"]:
        assert str(noise.id) not in ids
    assert str(scene["q_si"].id) not in ids
    assert not numbers & {"ZZT-SI-NONE", "ZZT-CX-NONE", "ZZT-PR-NONE", "ZZT-SF-P2", "NPA-990002", "NPA-990003", "ZZT-SI-Q", "NPA-990099"}


def test_ac_a3_a_draft_npa_with_no_submitted_at_dates_by_created_at(scene):
    db, p = scene["db"], scene["p"]
    with company_scope(db, frozenset({scene["company_id"]})):
        draft = _npa(db, scene["company_id"], p.id, application_no="NPA-990004", status="draft",
                     created_at=datetime(2026, 6, 20, 8, 0))
    with acting(db, _viewer(db), FULL) as client:
        body = _get(client, p.id)
    row = next(r for r in body["data"] if r["id"] == str(draft.id))
    assert row["date"] == "2026-06-20"


def test_ac_a4_default_sort_is_date_newest_first(scene):
    db, p = scene["db"], scene["p"]
    with acting(db, _viewer(db), FULL) as client:
        body = _get(client, p.id)
    assert [row["kind"] for row in body["data"]] == [
        "new_product_application", "sponsorship_form", "purchase_request", "complaint", "stock_inquiry",
    ]


def _sort_value(kind: str, key: str):
    e = EXPECTED[kind]
    return {
        "type": LABELS[kind],
        "number": e["number"],
        "status": e["status"],
        "approval": e["approval_status"],
        "date": e["date"],
        "raised_by": e["raised_by"],
        "subject": e["subject"],
        "value": e["value"],
    }[key]


@pytest.mark.parametrize("direction", ["asc", "desc"])
@pytest.mark.parametrize("key", SORT_KEYS)
def test_ac_a4_every_column_sorts_on_the_server_and_holds_on_page_2(scene, key, direction):
    """Pages of 2 concatenated equal the one-page order, and the rows with a value for the key
    come in that key's order. Where a key is empty (approval, value) only the non-empty rows'
    relative order is pinned: the contract does not place nulls."""
    db, p = scene["db"], scene["p"]
    with acting(db, _viewer(db), FULL) as client:
        whole = _get(client, p.id, sort=key, dir=direction)["data"]
        paged = []
        for page in (1, 2, 3):
            response = client.get(_url(p.id), params={"sort": key, "dir": direction, "page": page, "limit": 2})
            assert response.status_code == 200, response.text
            assert response.json()["pagination"]["total"] == 5
            paged += response.json()["data"]
    assert [r["id"] for r in paged] == [r["id"] for r in whole]
    kinds = [r["kind"] for r in whole if _sort_value(r["kind"], key) is not None]
    expected = sorted(
        (k for k in KINDS if _sort_value(k, key) is not None),
        key=lambda k: _sort_value(k, key),
        reverse=direction == "desc",
    )
    assert kinds == expected


def test_ac_a4_an_unknown_sort_key_is_refused(scene):
    db, p = scene["db"], scene["p"]
    with acting(db, _viewer(db), FULL) as client:
        response = client.get(_url(p.id), params={"sort": "id; drop table x"})
    assert response.status_code == 422, response.text


# ------------------------------------------------------------------ AC-A5: search


@pytest.mark.parametrize(
    "query,kind",
    [
        ("cracked", "complaint"),  # subject
        ("zzt-pr-0001", "purchase_request"),  # number, case-insensitive
        ("dina", "new_product_application"),  # raised by (the applicant's name)
        ("ZACK", "stock_inquiry"),  # raised by (the SI salesperson text)
    ],
)
def test_ac_a5_search_matches_number_subject_and_raised_by(scene, query, kind):
    db, p = scene["db"], scene["p"]
    with acting(db, _viewer(db), FULL) as client:
        body = _get(client, p.id, query=query)
    assert [row["kind"] for row in body["data"]] == [kind]
    assert body["pagination"]["total"] == 1


# ------------------------------------------------------------------ AC-A6: filters


def test_ac_a6_two_types_mean_either(scene):
    db, p = scene["db"], scene["p"]
    with acting(db, _viewer(db), FULL) as client:
        body = _get(client, p.id, type=["complaint", "sponsorship_form"])
    assert sorted(row["kind"] for row in body["data"]) == ["complaint", "sponsorship_form"]


def test_ac_a6_two_statuses_mean_either(scene):
    db, p = scene["db"], scene["p"]
    with acting(db, _viewer(db), FULL) as client:
        body = _get(client, p.id, status=["submitted", "completed"])
    assert sorted(row["kind"] for row in body["data"]) == ["complaint", "new_product_application"]


def test_ac_a6_type_and_status_filters_combine(scene):
    db, p = scene["db"], scene["p"]
    with acting(db, _viewer(db), FULL) as client:
        body = _get(client, p.id, type=["complaint", "stock_inquiry"], status=["submitted", "approved"])
    assert [row["kind"] for row in body["data"]] == ["complaint"]


def test_ac_a1_type_counts_ignore_filters_and_types_follow_registry_order(scene):
    db, p = scene["db"], scene["p"]
    with acting(db, _viewer(db), FULL) as client:
        body = _get(client, p.id, type=["complaint"], status=["submitted"], query="cracked")
    assert len(body["data"]) == 1
    counts = {k: v for k, v in body["type_counts"].items() if v}
    assert counts == {kind: 1 for kind in KINDS}
    assert body["types"] == [{"kind": kind, "label": LABELS[kind]} for kind in KINDS]


# ------------------------------------------------------------------ AC-B2: per-type visibility


def test_ac_b2_no_complaint_permission_means_no_complaint_rows_type_or_count(scene):
    db, p = scene["db"], scene["p"]
    with acting(db, _viewer(db), FULL - {CX_VIEW}) as client:
        body = _get(client, p.id)
        filtered = _get(client, p.id, type=["complaint"])
    assert "complaint" not in {row["kind"] for row in body["data"]}
    assert body["pagination"]["total"] == 4
    assert "complaint" not in body["type_counts"]
    assert "complaint" not in [t["kind"] for t in body["types"]]
    assert filtered["data"] == []


def test_ac_b2_view_own_only_sees_rows_raised_by_their_contact(scene):
    db, p = scene["db"], scene["p"]
    mine_contact = contact(db, "Mine")
    other_contact = contact(db, "Theirs")
    me = user(db, "Limited", mine_contact.id)
    company_id = scene["company_id"]
    own = {
        "stock_inquiry": _si(db, p.id, inquiry_number="ZZT-SI-MINE", contact_id=mine_contact.id),
        "complaint": _complaint(db, p.id, complaint_number="ZZT-CX-MINE", contact_id=mine_contact.id),
        "purchase_request": _request(db, p.id, "purchase_request", request_number="ZZT-PR-MINE", contact_id=mine_contact.id),
        "sponsorship_form": _request(db, p.id, "sponsorship_form", request_number="ZZT-SF-MINE", contact_id=mine_contact.id),
    }
    with company_scope(db, frozenset({company_id})):
        npa_applicant = _npa(db, company_id, p.id, application_no="NPA-990005", applicant_id=me)
        npa_contact = _npa(db, company_id, p.id, application_no="NPA-990006", contact_id=mine_contact.id)
        npa_theirs = _npa(db, company_id, p.id, application_no="NPA-990007", contact_id=other_contact.id)
    theirs = [
        _si(db, p.id, inquiry_number="ZZT-SI-THEIRS", contact_id=other_contact.id),
        _complaint(db, p.id, complaint_number="ZZT-CX-THEIRS", contact_id=other_contact.id),
        npa_theirs,
    ]
    with acting(db, me, {P_VIEW} | ALL_TYPES_OWN) as client:
        body = _get(client, p.id)
    ids = {row["id"] for row in body["data"]}
    expected = {str(r.id) for r in own.values()} | {str(npa_applicant.id), str(npa_contact.id)}
    assert ids == expected
    for row in theirs:
        assert str(row.id) not in ids
    assert sum(body["type_counts"].values()) == len(expected)


def test_ac_b2_view_on_one_type_and_view_own_on_another(scene):
    db, p = scene["db"], scene["p"]
    mine_contact = contact(db, "Mine2")
    me = user(db, "Mixed", mine_contact.id)
    mine_si = _si(db, p.id, inquiry_number="ZZT-SI-MINE2", contact_id=mine_contact.id)
    with acting(db, me, {P_VIEW, SI_OWN, CX_VIEW}) as client:
        body = _get(client, p.id)
    got = {(row["kind"], row["id"]) for row in body["data"]}
    assert got == {("stock_inquiry", str(mine_si.id)), ("complaint", str(scene["rows"]["complaint"].id))}
    assert [t["kind"] for t in body["types"]] == ["stock_inquiry", "complaint"]


# ------------------------------------------------------------------ AC-B1, AC-B3: the project gate


def test_ac_b1_no_project_read_is_refused(scene):
    db, p = scene["db"], scene["p"]
    with acting(db, _viewer(db), ALL_TYPES_VIEW) as client:
        response = client.get(_url(p.id))
    assert response.status_code == 403, response.text


def test_ac_b1_b3_a_project_of_another_company_is_404(scene):
    db, q = scene["db"], scene["q"]
    with acting(db, _viewer(db), FULL) as client:
        response = client.get(_url(q.id))
    assert response.status_code == 404, response.text
    _mounted(response)
    assert "ZZT-SI-Q" not in response.text


def test_ac_b1_a_view_own_user_on_someone_elses_project_is_404(scene):
    db, p = scene["db"], scene["p"]
    stranger = user(db, "Stranger")
    with acting(db, stranger, {P_VIEW_OWN} | ALL_TYPES_VIEW) as client:
        response = client.get(_url(p.id))
    assert response.status_code == 404, response.text
    _mounted(response)


def test_ac_b1_a_view_own_user_on_their_own_project_reads_it(scene):
    db, p, owner = scene["db"], scene["p"], scene["owner"]
    with acting(db, owner, {P_VIEW_OWN} | ALL_TYPES_VIEW) as client:
        body = _get(client, p.id)
    assert body["pagination"]["total"] == 5


def test_ac_b1_a_malformed_project_id_is_not_a_500(scene):
    db = scene["db"]
    with acting(db, _viewer(db), FULL) as client:
        response = client.get(_url("not-a-uuid"))
    assert response.status_code in (404, 422), response.text
    _mounted(response)


# ------------------------------------------------------------------ limit cap


def test_limit_is_capped_like_every_other_list(scene):
    from app.schemas.common import MAX_PAGE_LIMIT

    db, p = scene["db"], scene["p"]
    with acting(db, _viewer(db), FULL) as client:
        ok = client.get(_url(p.id), params={"limit": MAX_PAGE_LIMIT})
        over = client.get(_url(p.id), params={"limit": MAX_PAGE_LIMIT + 1})
    assert ok.status_code == 200, ok.text
    assert over.status_code == 422, over.text


def test_default_limit_is_25(scene):
    db, p = scene["db"], scene["p"]
    with acting(db, _viewer(db), FULL) as client:
        response = client.get(_url(p.id))
    assert response.status_code == 200, response.text
    assert response.json()["pagination"]["limit"] == 25


# ------------------------------------------------------------------ AC-D1: a sixth type plugs in


def _fake_select(me, access):
    """A sixth kind reusing the complaints table under its own label: complaints whose
    description carries the fake marker. Columns labelled per the contract."""
    from sqlalchemy import Date, Numeric, String, cast, literal, null, select

    from app.models.complaints import Complaint

    return select(
        literal("zzt_fake_kind", String).label("kind"),
        Complaint.id.label("id"),
        Complaint.complaint_number.label("number"),
        Complaint.status.label("status"),
        cast(null(), String).label("approval_status"),
        cast(Complaint.complaint_date, Date).label("date"),
        Complaint.salesperson.label("raised_by"),
        Complaint.defect_description.label("subject"),
        cast(null(), Numeric).label("value"),
    ).where(Complaint.defect_description.like("zzt-prr-fake%"))


@pytest.fixture()
def fake_type():
    from app.models.complaints import Complaint
    from app.services import project_related_records as registry

    rt = registry.RelatedType(
        kind="zzt_fake_kind",
        label="ZZT fake kind",
        access_kind="complaint",
        model=Complaint,
        select=_fake_select,
    )
    registry.register_related_type(rt)
    try:
        yield rt
    finally:
        registry.RELATED_TYPES.pop("zzt_fake_kind", None)


def test_ac_d1_a_registered_sixth_type_appears_with_no_other_change(scene, fake_type):
    db, p, p2 = scene["db"], scene["p"], scene["p2"]
    fake = _complaint(db, p.id, complaint_number="ZZT-FAKE-1", complaint_date=date(2026, 7, 1),
                      salesperson="Eve Fake", defect_description="zzt-prr-fake thing")
    elsewhere = _complaint(db, p2.id, complaint_number="ZZT-FAKE-2",
                           defect_description="zzt-prr-fake elsewhere")
    with acting(db, _viewer(db), FULL) as client:
        body = _get(client, p.id)
        only = _get(client, p.id, type=["zzt_fake_kind"])
    fake_rows = [row for row in body["data"] if row["kind"] == "zzt_fake_kind"]
    assert [row["id"] for row in fake_rows] == [str(fake.id)]
    assert fake_rows[0]["number"] == "ZZT-FAKE-1"
    assert fake_rows[0]["raised_by"] == "Eve Fake"
    assert str(elsewhere.id) not in {row["id"] for row in body["data"]}
    assert {"kind": "zzt_fake_kind", "label": "ZZT fake kind"} in body["types"]
    assert body["types"][-1]["kind"] == "zzt_fake_kind"  # registry order: appended last
    assert body["type_counts"]["zzt_fake_kind"] == 1
    assert [row["id"] for row in only["data"]] == [str(fake.id)]


def test_ac_d1_a_sixth_type_follows_its_access_kind(scene, fake_type):
    db, p = scene["db"], scene["p"]
    _complaint(db, p.id, complaint_number="ZZT-FAKE-3", defect_description="zzt-prr-fake hidden")
    with acting(db, _viewer(db), FULL - {CX_VIEW}) as client:
        body = _get(client, p.id)
    assert "zzt_fake_kind" not in {row["kind"] for row in body["data"]}
    assert "zzt_fake_kind" not in [t["kind"] for t in body["types"]]


def test_ac_d1_the_registry_holds_the_five_kinds_in_order():
    from app.services import project_related_records as registry

    assert list(registry.RELATED_TYPES)[:5] == list(KINDS)
    assert {k: registry.RELATED_TYPES[k].label for k in KINDS} == LABELS


# ------------------------------------------------------------------ guards


def test_the_route_is_on_the_project_own_scope_pin_list():
    """The new route is reachable by a view_own user only through the project guard, so it
    is pinned in tests/portal_p2_allowed_routes.txt (contract section 5)."""
    from pathlib import Path

    pinned = (Path(__file__).parent / "portal_p2_allowed_routes.txt").read_text().split("\n")
    assert "GET /projects/{project_id}/related-records" in pinned


# ------------------------------------------------------------------ fix round 7: the Malaysia day


def test_the_date_is_the_malaysia_day_not_the_utc_day(scene):
    """created_at / submitted_at are naive UTC; the grid's Date is the calendar day in
    Asia/Kuala_Lumpur (UTC+8), as every other screen reads it. 23:30 UTC on the 12th is 07:30 on
    the 13th in Malaysia; 15:00 UTC on the 12th is 23:00 on the 12th."""
    db, p = scene["db"], scene["p"]
    company_id = scene["company_id"]
    early_si = _si(db, p.id, inquiry_number="ZZT-SI-MYT1", created_at=datetime(2026, 11, 12, 23, 30))
    late_si = _si(db, p.id, inquiry_number="ZZT-SI-MYT2", created_at=datetime(2026, 11, 12, 15, 0))
    with company_scope(db, frozenset({company_id})):
        npa = _npa(db, company_id, p.id, application_no="NPA-990011",
                   submitted_at=datetime(2026, 11, 12, 22, 0), created_at=datetime(2026, 11, 10, 1, 0))
    with acting(db, _viewer(db), FULL) as client:
        body = _get(client, p.id)
    dates = {row["id"]: row["date"] for row in body["data"]}
    assert dates[str(early_si.id)] == "2026-11-13"
    assert dates[str(npa.id)] == "2026-11-13"
    assert dates[str(late_si.id)] == "2026-11-12"


# ------------------------------------------------------------------ fix round 8: request date fallback


@pytest.mark.parametrize("kind", ["purchase_request", "sponsorship_form"])
def test_a_request_with_no_request_date_dates_by_the_malaysia_submitted_or_created_day(scene, kind):
    """request_date is a Date and wins; without it the Malaysia day of submitted_at, then of
    created_at (both naive UTC)."""
    db, p = scene["db"], scene["p"]
    submitted = _request(db, p.id, kind, request_number=f"ZZT-RQ-{kind[:2]}-S", request_date=None,
                         submitted_at=datetime(2026, 11, 12, 23, 30), created_at=datetime(2026, 11, 10, 1, 0))
    created = _request(db, p.id, kind, request_number=f"ZZT-RQ-{kind[:2]}-C", request_date=None,
                       submitted_at=None, created_at=datetime(2026, 11, 12, 15, 0))
    dated = _request(db, p.id, kind, request_number=f"ZZT-RQ-{kind[:2]}-D", request_date=date(2026, 11, 1),
                     submitted_at=datetime(2026, 11, 12, 23, 30))
    with acting(db, _viewer(db), FULL) as client:
        body = _get(client, p.id)
    dates = {row["id"]: row["date"] for row in body["data"]}
    assert dates[str(submitted.id)] == "2026-11-13"
    assert dates[str(created.id)] == "2026-11-12"
    assert dates[str(dated.id)] == "2026-11-01"
