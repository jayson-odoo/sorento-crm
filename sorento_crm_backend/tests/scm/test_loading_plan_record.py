"""S1 of part 4 - the loading plan as a RECORD, over the wire.

`PLAN-scm-fulfilment-feedback-p4.md` R1-R6 and AC-A10/A11 are this file's contract. What is
proved here is the LIFECYCLE, not the ranking: the plan row is created, listed, filtered,
edited, cancelled and deleted, the build reads its supplier and its cut-off off the row, and a
send links its notice to it.

Nothing about the suggestion is re-derived - `test_container_request.py` owns that, and this
suite deliberately seeds the thinnest chain a plan needs (one supplier, one product with open
demand) so a change in the engine cannot turn a lifecycle test red.

Every chain is seeded here under a marker-prefixed tag: CI's database is empty.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.models.scm import LoadingPlan
from app.models.supplier_notice import SupplierNotice
from app.services.scm import supplier_notice_service
from tests.scm.conftest import as_user, requires_pg, seed_user
from tests.scm.test_container_request import _so
from tests.scm.test_loading_plan import World
from tests.scm.test_outstanding_import_routes import as_company_user

pytestmark = requires_pg

MARKER = "ZZLPR"

PLANS_URL = "/api/v1/scm/loading-plans"
BUILD_URL = "/api/v1/scm/container-requests/build"
SEND_URL = "/api/v1/scm/container-requests"


@pytest.fixture(autouse=True)
def _no_pdf_no_storage(monkeypatch):
    """A send here is about the plan row, not WeasyPrint - same stub as S8's own suite."""
    monkeypatch.setattr(supplier_notice_service, "render_document", lambda html: b"%PDF-1.4 stub")
    monkeypatch.setattr(
        supplier_notice_service, "_store", lambda data, filename: ("s3", f"exports/test/{filename}")
    )


def _world(db) -> World:
    """One supplier holding one product the order book owes a customer.

    The supplier carries an address because a send with nothing to address is refused since
    S3 (422 `no_recipients`, AC-C2) - these tests are about the plan's lifecycle, not about
    who the request is addressed to.
    """
    w = World(db)
    w.supplier.email = f"{MARKER}-supplier@example.test"
    db.flush()
    w.stock("A", packed=50, cbm=0.5)
    _so(db, w, "A", 20)
    return w


def _live_links(db, *, supplier_id: str | None = None, plan_id: str | None = None) -> int:
    """How many container-request links are still answering, for one supplier or one plan.

    `clock_timestamp() AT TIME ZONE 'UTC'`, never `now()`, and neither half is cosmetic.
    `now()` is the TRANSACTION's start time, and this suite runs every test inside one
    rolled-back transaction (`scm_app`), so a link retired mid-test carries a stamp LATER
    than `now()` and reads as live however dead it is. And the column is `timestamp without
    time zone` holding UTC while `now()` is a `timestamptz` Postgres converts with the
    session's zone, so the answer moved with the machine: a developer database set to
    Asia/Seoul shifted the stamp nine hours back and hid the first problem, and CI (UTC)
    did not. The service's own liveness test is `expires_at > datetime.utcnow()`
    (`supplier_notice_service._link_live`); this is that same comparison in SQL.
    """
    column = "supplier_id" if supplier_id else "loading_plan_id"
    return db.execute(
        text(
            f"SELECT count(*) FROM supplier_notices WHERE {column} = CAST(:v AS uuid) "
            "AND public_token IS NOT NULL "
            "AND public_token_expires_at > (clock_timestamp() AT TIME ZONE 'UTC')"
        ),
        {"v": supplier_id or plan_id},
    ).scalar()


def _create(client, supplier_id: str, **overrides):
    body = {
        "supplier_id": supplier_id,
        "plan_horizon_date": None,
        "document_kind": "none",
        "source_attachment_id": None,
    }
    body.update(overrides)
    return client.post(PLANS_URL, json=body)


# --------------------------------------------------------------------------- #
# create
# --------------------------------------------------------------------------- #


def test_a_plan_is_created_in_planning_named_by_its_supplier_and_start_time(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = _world(db)

    r = _create(
        TestClient(app),
        str(w.supplier.id),
        plan_horizon_date="2026-09-30",
        document_kind="stock_list",
    )

    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "planning"
    assert body["supplier_id"] == str(w.supplier.id)
    assert body["supplier_name"] == w.supplier.supplier_name
    assert body["plan_horizon_date"] == "2026-09-30"
    assert body["document_kind"] == "stock_list"
    assert body["started_at"]
    assert body["sent_at"] is None
    assert body["cancelled_at"] is None
    assert body["line_edits"] == {}
    # No plan number: a plan is named by supplier + start time, as a reorder run is.
    assert "plan_number" not in body


def test_the_document_label_names_the_file_the_plan_was_started_from(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = _world(db)
    client = TestClient(app)

    with_file = _create(client, str(w.supplier.id), document_kind="stock_list").json()
    without = _create(client, str(w.supplier.id), document_kind="none").json()

    assert with_file["document_label"].startswith("Stock list")
    assert without["document_label"] == "No file"


def test_creating_a_plan_for_a_supplier_that_does_not_exist_is_a_404(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)

    r = _create(TestClient(app), str(uuid.uuid4()))

    assert r.status_code == 404, r.text


def test_creating_a_plan_for_another_companys_supplier_is_a_404(scm_app):
    # B1 again, on this route. `_supplier_name` was a bare
    # `SELECT supplier_name FROM suppliers WHERE id = :i`, so a caller in company A could
    # start a plan against company B's supplier - and every screen from there on would name
    # and address that supplier.
    from app.models.company import Company

    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = _world(db)
    other = str(uuid.uuid4())
    db.add(
        Company(
            id=other,
            name=f"{MARKER} other company {other[:8]}",
            code=f"{MARKER}-{uuid.uuid4().hex[:6]}".upper()[:50],
            is_active=True,
        )
    )
    db.flush()
    db.execute(
        text("UPDATE suppliers SET company_id = CAST(:c AS uuid) WHERE id = CAST(:s AS uuid)"),
        {"c": other, "s": str(w.supplier.id)},
    )
    db.flush()

    r = _create(TestClient(app), str(w.supplier.id))

    assert r.status_code == 404, r.text


def test_creating_a_plan_for_a_supplier_id_that_is_not_an_id_is_a_404(scm_app):
    # The raw lookup handed a non-uuid straight to the UUID column and 500'd on it. A typo in
    # a body is a 404, the same answer every other id-shaped filter in this module gives.
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)

    r = _create(TestClient(app), "not-a-supplier-id")

    assert r.status_code == 404, r.text


def test_creating_a_plan_requires_the_operator_permission(scm_app):
    app, db, gcu, gcuk = scm_app
    as_user(app, gcu, gcuk, seed_user(db, None))

    r = _create(TestClient(app), str(uuid.uuid4()))

    assert r.status_code == 403, r.text


# --------------------------------------------------------------------------- #
# the list
# --------------------------------------------------------------------------- #


def test_the_list_pages_and_carries_the_grid_fields(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = _world(db)
    client = TestClient(app)
    _create(client, str(w.supplier.id), document_kind="none")

    r = client.get(PLANS_URL, params={"page": 1, "limit": 25, "sort": "started_at", "dir": "desc"})

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] >= 1
    mine = [p for p in body["data"] if p["supplier_id"] == str(w.supplier.id)]
    assert len(mine) == 1
    for field in (
        "started_at",
        "supplier_name",
        "plan_horizon_date",
        "document_label",
        "to_request_qty",
        "to_request_cbm",
        "sent_channel",
        "sent_at",
        "opened_at",
        "status",
    ):
        assert field in mine[0], field
    # S3 lands open tracking; until then the column is honestly empty rather than invented.
    assert mine[0]["opened_at"] is None


def test_the_search_narrows_to_the_supplier_name(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = _world(db)
    client = TestClient(app)
    _create(client, str(w.supplier.id))

    hit = client.get(PLANS_URL, params={"query": w.supplier.supplier_name[:12]}).json()
    miss = client.get(PLANS_URL, params={"query": f"{MARKER}-nothing-{uuid.uuid4().hex}"}).json()

    assert any(p["supplier_id"] == str(w.supplier.id) for p in hit["data"])
    assert miss["total"] == 0


def test_active_is_planning_plus_sent_and_cancelled_is_asked_for_by_name(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = _world(db)
    client = TestClient(app)
    plan = _create(client, str(w.supplier.id)).json()

    client.post(f"{PLANS_URL}/{plan['id']}/cancel")

    active = client.get(PLANS_URL, params={"status": "active"}).json()
    cancelled = client.get(PLANS_URL, params={"status": "cancelled"}).json()
    assert plan["id"] not in [p["id"] for p in active["data"]]
    assert plan["id"] in [p["id"] for p in cancelled["data"]]


def test_reading_the_list_requires_the_dashboard_permission(scm_app):
    app, db, gcu, gcuk = scm_app
    as_user(app, gcu, gcuk, seed_user(db, None))

    r = TestClient(app).get(PLANS_URL)

    assert r.status_code == 403, r.text


# --------------------------------------------------------------------------- #
# cancel and delete (Q4, Q5)
# --------------------------------------------------------------------------- #


def test_cancel_stamps_who_and_when_and_retires_the_suppliers_live_link(scm_app):
    # Q4: the plan stops being worked on AND the link the supplier holds stops answering.
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = _world(db)
    client = TestClient(app)
    plan = _create(client, str(w.supplier.id)).json()
    client.post(SEND_URL, json={"plan_id": plan["id"], "lines": [
        {"product_id": str(w.product("A").id), "qty": 5}
    ]})
    assert _live_links(db, supplier_id=str(w.supplier.id)) >= 1

    r = client.post(f"{PLANS_URL}/{plan['id']}/cancel")

    assert r.status_code == 200, r.text
    assert r.json()["status"] == "cancelled"
    assert r.json()["cancelled_at"]
    assert r.json()["cancelled_by"]
    assert _live_links(db, supplier_id=str(w.supplier.id)) == 0


def test_an_unsent_plan_is_hard_deleted(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = _world(db)
    client = TestClient(app)
    plan = _create(client, str(w.supplier.id)).json()

    r = client.delete(f"{PLANS_URL}/{plan['id']}")

    assert r.status_code == 204, r.text
    assert db.query(LoadingPlan).filter(LoadingPlan.id == plan["id"]).first() is None


def test_a_sent_plan_is_cancelled_not_deleted(scm_app):
    # Q5: the notice is the record of what left the building; deleting the plan under it
    # would leave a notice pointing at nothing.
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = _world(db)
    client = TestClient(app)
    plan = _create(client, str(w.supplier.id)).json()
    client.post(SEND_URL, json={"plan_id": plan["id"], "lines": [
        {"product_id": str(w.product("A").id), "qty": 5}
    ]})

    r = client.delete(f"{PLANS_URL}/{plan['id']}")

    assert r.status_code == 409, r.text
    assert r.json()["detail"]["code"] == "plan_sent"
    assert db.query(LoadingPlan).filter(LoadingPlan.id == plan["id"]).first() is not None


def test_cancelling_requires_the_operator_permission(scm_app):
    app, db, gcu, gcuk = scm_app
    as_user(app, gcu, gcuk, seed_user(db, None))

    r = TestClient(app).post(f"{PLANS_URL}/{uuid.uuid4()}/cancel")

    assert r.status_code == 403, r.text


# --------------------------------------------------------------------------- #
# the typed quantities (R6)
# --------------------------------------------------------------------------- #


def test_edits_replace_the_whole_map_rather_than_patching_it(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = _world(db)
    client = TestClient(app)
    plan = _create(client, str(w.supplier.id)).json()
    product_a = str(w.product("A").id)

    client.put(f"{PLANS_URL}/{plan['id']}/edits", json={"line_edits": {product_a: 7, "other": 3}})
    r = client.put(f"{PLANS_URL}/{plan['id']}/edits", json={"line_edits": {product_a: 9}})

    assert r.status_code == 200, r.text
    # "other" is gone: a cleared cell must not survive as a stale override.
    assert r.json()["line_edits"] == {product_a: 9}


def test_a_cancelled_plan_takes_no_more_edits(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = _world(db)
    client = TestClient(app)
    plan = _create(client, str(w.supplier.id)).json()
    client.post(f"{PLANS_URL}/{plan['id']}/cancel")

    r = client.put(f"{PLANS_URL}/{plan['id']}/edits", json={"line_edits": {"x": 1}})

    assert r.status_code == 409, r.text
    assert r.json()["detail"]["code"] == "plan_cancelled"


def test_saving_edits_requires_the_operator_permission(scm_app):
    app, db, gcu, gcuk = scm_app
    as_user(app, gcu, gcuk, seed_user(db, None))

    r = TestClient(app).put(f"{PLANS_URL}/{uuid.uuid4()}/edits", json={"line_edits": {}})

    assert r.status_code == 403, r.text


# --------------------------------------------------------------------------- #
# the build is scoped to a plan (R2, AC-A11)
# --------------------------------------------------------------------------- #


def test_the_build_reads_the_supplier_off_the_plan_and_echoes_the_row_back(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = _world(db)
    client = TestClient(app)
    plan = _create(client, str(w.supplier.id), document_kind="stock_list").json()

    r = client.post(BUILD_URL, json={"plan_id": plan["id"]})

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["supplier_id"] == str(w.supplier.id)
    assert body["plan"]["id"] == plan["id"]
    assert body["plan"]["status"] == "planning"
    assert body["plan"]["document_kind"] == "stock_list"
    assert body["plan"]["started_at"]


def test_every_row_carries_the_engines_own_answer_beside_the_edited_one(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = _world(db)
    client = TestClient(app)
    plan = _create(client, str(w.supplier.id)).json()
    before = client.post(BUILD_URL, json={"plan_id": plan["id"]}).json()["rows"]
    row_key = before[0]["row_key"]
    engine = before[0]["suggested_qty"]
    assert before[0]["engine_qty"] == engine

    client.put(f"{PLANS_URL}/{plan['id']}/edits", json={"line_edits": {row_key: engine + 11}})
    after = client.post(BUILD_URL, json={"plan_id": plan["id"]}).json()["rows"]

    edited = next(r for r in after if r["row_key"] == row_key)
    assert edited["suggested_qty"] == engine + 11
    assert edited["engine_qty"] == engine


def test_the_cut_off_on_the_plan_narrows_the_build(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = _world(db)
    _so(db, w, "A", 40, required_date=date(2027, 6, 1))
    client = TestClient(app)
    wide = _create(client, str(w.supplier.id)).json()
    narrow = _create(client, str(w.supplier.id), plan_horizon_date="2026-01-31").json()

    wide_need = client.post(BUILD_URL, json={"plan_id": wide["id"]}).json()["rows"][0]
    narrow_body = client.post(BUILD_URL, json={"plan_id": narrow["id"]}).json()

    assert narrow_body["plan_horizon_date"] == "2026-01-31"
    narrow_need = narrow_body["rows"][0]
    assert narrow_need["open_so_need"] < wide_need["open_so_need"]


def test_the_supplier_scoped_build_body_is_no_longer_accepted(scm_app):
    # The page was its only caller, and a body naming a supplier cannot say WHICH plan the
    # typed quantities belong to.
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = _world(db)

    r = TestClient(app).post(BUILD_URL, json={"supplier_id": str(w.supplier.id)})

    assert r.status_code == 422, r.text


def test_a_build_for_a_plan_that_does_not_exist_is_a_404(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)

    r = TestClient(app).post(BUILD_URL, json={"plan_id": str(uuid.uuid4())})

    assert r.status_code == 404, r.text


def test_the_list_carries_what_the_last_build_asked_for(scm_app):
    # The grid's "To request" column: stamped by the build rather than re-derived per row,
    # because one build per listed row is a page of full suggestion runs.
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = _world(db)
    client = TestClient(app)
    plan = _create(client, str(w.supplier.id)).json()
    assert plan["to_request_qty"] is None

    built = client.post(BUILD_URL, json={"plan_id": plan["id"]}).json()
    listed = client.get(PLANS_URL, params={"status": "active"}).json()["data"]

    row = next(p for p in listed if p["id"] == plan["id"])
    assert row["to_request_qty"] == sum(r["suggested_qty"] for r in built["rows"])
    assert row["to_request_cbm"] is not None


def test_a_newer_stock_list_moves_an_older_plans_numbers_but_not_its_document(scm_app):
    # AC-A17 / R2, stated in the open: the supplier snapshot is per supplier and replaced
    # whole, so an older open plan reads what the supplier holds NOW - which is the correct
    # reading of "what should we ask them for". What must NOT move is which file that plan
    # says it started from, which is why the snapshot date is pinned at create time.
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = _world(db)
    client = TestClient(app)
    plan = _create(client, str(w.supplier.id), document_kind="stock_list").json()
    label_before = plan["document_label"]
    packed_before = client.post(BUILD_URL, json={"plan_id": plan["id"]}).json()["rows"][0][
        "qty_packed"
    ]

    # A newer list for the same supplier, exactly as a second plan's upload would leave it.
    db.execute(
        text(
            "UPDATE scm.supplier_inventory SET qty_packed = qty_packed + 100, "
            "as_of = as_of + INTERVAL '30 days' WHERE supplier_id = CAST(:s AS uuid)"
        ),
        {"s": str(w.supplier.id)},
    )
    db.flush()

    after = client.post(BUILD_URL, json={"plan_id": plan["id"]}).json()

    assert after["rows"][0]["qty_packed"] == packed_before + 100
    assert after["plan"]["document_label"] == label_before


# --------------------------------------------------------------------------- #
# the send belongs to the plan
# --------------------------------------------------------------------------- #


def test_the_send_links_its_notices_to_the_plan_and_flips_it_to_sent(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = _world(db)
    client = TestClient(app)
    plan = _create(client, str(w.supplier.id)).json()

    r = client.post(
        SEND_URL,
        json={"plan_id": plan["id"], "lines": [{"product_id": str(w.product("A").id), "qty": 5}]},
    )

    assert r.status_code == 201, r.text
    assert all(n["loading_plan_id"] == plan["id"] for n in r.json()["notices"])
    after = client.get(f"{PLANS_URL}/{plan['id']}").json()
    assert after["status"] == "sent"
    assert after["sent_at"]
    assert after["sent_channel"] in {"email", "chat"}
    assert (
        db.query(SupplierNotice)
        .filter(SupplierNotice.loading_plan_id == plan["id"])
        .count()
        >= 1
    )


def test_sending_for_a_plan_that_does_not_exist_is_a_404(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = _world(db)

    r = TestClient(app).post(
        SEND_URL,
        json={"plan_id": str(uuid.uuid4()), "lines": [{"product_id": str(w.product("A").id), "qty": 5}]},
    )

    assert r.status_code == 404, r.text


# --------------------------------------------------------------------------- #
# the cut-off is changed on the plan, not by starting a second one
# --------------------------------------------------------------------------- #


def test_the_cut_off_can_be_changed_on_an_open_plan(scm_app):
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = _world(db)
    client = TestClient(app)
    plan = _create(client, str(w.supplier.id), plan_horizon_date="2026-09-30").json()

    r = client.patch(f"{PLANS_URL}/{plan['id']}", json={"plan_horizon_date": None})

    assert r.status_code == 200, r.text
    assert r.json()["plan_horizon_date"] is None
    assert client.post(BUILD_URL, json={"plan_id": plan["id"]}).json()["plan_horizon_date"] is None


# --------------------------------------------------------------------------- #
# one live link per PLAN, not per supplier (R3/R11)
# --------------------------------------------------------------------------- #


def test_cancelling_one_plan_leaves_the_other_plans_link_answering(scm_app, monkeypatch):
    # R3/R11. Two plans against one supplier is the ordinary case (a September container and
    # an October one), and retirement per SUPPLIER meant cancelling either one killed the
    # link the supplier was working off for the other.
    app, db, gcu, gcuk = scm_app
    # A link is only built when a public base URL is configured, and CI configures none
    # (no FRONTEND_BASE_URL in the job): without this the send honestly returns
    # `public_url: null` and the assertion below reads as "no link was issued". Same stub
    # `test_supplier_request_public.py` uses wherever a URL is the subject.
    monkeypatch.setattr(
        supplier_notice_service, "_public_base_url", lambda: "https://crm.example.test"
    )
    as_company_user(app, db, gcu, gcuk)
    w = _world(db)
    client = TestClient(app)
    line = [{"product_id": str(w.product("A").id), "qty": 5}]
    plan_a = _create(client, str(w.supplier.id)).json()
    token_a = client.post(SEND_URL, json={"plan_id": plan_a["id"], "lines": line}).json()[
        "notices"
    ][0]["public_url"]
    plan_b = _create(client, str(w.supplier.id)).json()
    client.post(SEND_URL, json={"plan_id": plan_b["id"], "lines": line})

    r = client.post(f"{PLANS_URL}/{plan_b['id']}/cancel")

    assert r.status_code == 200, r.text
    assert token_a, "plan A's send issued no link"
    assert _live_links(db, plan_id=plan_a["id"]) == 1
    assert _live_links(db, plan_id=plan_b["id"]) == 0


def test_a_resend_for_the_same_plan_still_retires_that_plans_link(scm_app):
    # AC-C7 stands within the plan: the second request IS the current ask for it.
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = _world(db)
    client = TestClient(app)
    line = [{"product_id": str(w.product("A").id), "qty": 5}]
    plan = _create(client, str(w.supplier.id)).json()
    client.post(SEND_URL, json={"plan_id": plan["id"], "lines": line})
    client.post(SEND_URL, json={"plan_id": plan["id"], "lines": line})

    live = _live_links(db, plan_id=plan["id"])

    assert live == 1


def test_the_records_notice_history_is_only_its_own_plans(scm_app):
    # R3/R11. The record page prints "sent, by whom, when" for the plan it is showing; the
    # supplier's OTHER plan's sends belong on that plan's page, not on this one.
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = _world(db)
    client = TestClient(app)
    line = [{"product_id": str(w.product("A").id), "qty": 5}]
    plan_a = _create(client, str(w.supplier.id)).json()
    client.post(SEND_URL, json={"plan_id": plan_a["id"], "lines": line})
    plan_b = _create(client, str(w.supplier.id)).json()
    client.post(SEND_URL, json={"plan_id": plan_b["id"], "lines": line})

    scoped = client.get(
        "/api/v1/scm/supplier-notices",
        params={"supplier_id": str(w.supplier.id), "loading_plan_id": plan_a["id"]},
    ).json()
    every = client.get(
        "/api/v1/scm/supplier-notices", params={"supplier_id": str(w.supplier.id)}
    ).json()

    assert [n["loading_plan_id"] for n in scoped["data"]] == [plan_a["id"]]
    assert len(every["data"]) == 2


# --------------------------------------------------------------------------- #
# a send that could not go out (fix pass)
# --------------------------------------------------------------------------- #


def test_a_send_that_failed_leaves_the_plan_in_planning_and_deletable(scm_app, monkeypatch):
    # The plan flipped to `sent` on every send, so a refused email left a plan claiming it
    # went out - and Q5 then refused to delete it, so the row could be neither sent nor
    # removed. `sent` means the ask left the building; a failed notice means it did not.
    from app.services import email_outbox_service

    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = _world(db)
    client = TestClient(app)
    plan = _create(client, str(w.supplier.id)).json()

    def refuse(*_a, **_k):
        raise RuntimeError("the outbox is not accepting mail")

    monkeypatch.setattr(email_outbox_service, "enqueue", refuse)

    r = client.post(
        SEND_URL,
        json={"plan_id": plan["id"], "lines": [{"product_id": str(w.product("A").id), "qty": 5}]},
    )

    assert r.status_code == 201, r.text
    notice = r.json()["notices"][0]
    assert notice["status"] == "failed"
    assert "not accepting mail" in (notice["last_error"] or "")
    assert r.json()["plan"]["status"] == "planning"
    after = client.get(f"{PLANS_URL}/{plan['id']}").json()
    assert after["status"] == "planning"
    assert after["sent_at"] is None
    assert client.delete(f"{PLANS_URL}/{plan['id']}").status_code == 204


def test_a_cancelled_plan_can_no_longer_be_sent_or_downloaded(scm_app):
    # AC-A8. The record page is read-only once cancelled, but both POSTs took a plan id and
    # neither looked at its status - so a stale tab could still send the supplier an ask for
    # a plan that had been called off.
    app, db, gcu, gcuk = scm_app
    as_company_user(app, db, gcu, gcuk)
    w = _world(db)
    client = TestClient(app)
    plan = _create(client, str(w.supplier.id)).json()
    client.post(f"{PLANS_URL}/{plan['id']}/cancel")
    lines = [{"product_id": str(w.product("A").id), "qty": 5}]

    send = client.post(SEND_URL, json={"plan_id": plan["id"], "lines": lines})
    document = client.post(
        f"{SEND_URL}/document?format=xlsx", json={"plan_id": plan["id"], "lines": lines}
    )

    assert send.status_code == 409, send.text
    assert send.json()["detail"]["code"] == "plan_cancelled"
    assert document.status_code == 409, document.text
    assert document.json()["detail"]["code"] == "plan_cancelled"
    assert (
        db.query(SupplierNotice).filter(SupplierNotice.loading_plan_id == plan["id"]).count()
        == 0
    )
