"""NEW-PRODUCT-APP staff surface, red-first. Every test cites its AC id
(documentation/plans/procurement/new-product-application-acceptance-criteria.md).

Route level on purpose: the UAC promises HTTP behaviour (codes, keys, 403 vs 404).
Postgres only (tests/_pg_fixture.py). Every test seeds its own chain; recipients for
notifications come from REAL role grants (the recipient query reads the tables), while the
route permission checks are swapped per caller like the Sample Request suite does.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from ._pg_fixture import blank_session
from ._sample_request_seed import (
    MARKER,
    make_customer,
    make_product,
    make_user,
    second_company,
    sorento,
    uid,
)

NPA = "/api/v1/procurement/new-product-applications"

VIEW = "procurement.new_product_applications.view"
CREATE = "procurement.new_product_applications.create"
APPROVE = "procurement.new_product_applications.approve"
OPEN_CODE = "procurement.new_product_applications.open_code"
ALL = "ALL"


# ------------------------------------------------------------------ harness


def _install_client(db, perms: dict, state: dict):
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.main import app
    from app.services.company_scope_resolver import apply_company_scope
    from app.services.user_service import UserPermissionService

    def actor():
        uid_ = state["user"]
        return {"id": uid_, "email": f"{uid_}@zzt.test", "role": "staff"}

    def has(self, user_id, slug):
        granted = perms.get(user_id, set())
        return granted == ALL or slug in granted

    def slugs(self, user_id):
        granted = perms.get(user_id, set())
        return {VIEW, CREATE, APPROVE, OPEN_CODE} if granted == ALL else set(granted)

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = actor
    app.dependency_overrides[get_current_user_or_api_key] = actor
    app.dependency_overrides[apply_company_scope] = lambda: None

    originals = (
        UserPermissionService.check_user_has_permission,
        UserPermissionService.get_user_permission_slugs,
        UserPermissionService.check_user_has_any_permission,
        UserPermissionService.get_user_role_slugs,
    )
    UserPermissionService.check_user_has_permission = has
    UserPermissionService.get_user_permission_slugs = slugs
    UserPermissionService.check_user_has_any_permission = lambda self, uid_, ss: any(
        has(self, uid_, s) for s in ss
    )
    UserPermissionService.get_user_role_slugs = lambda self, uid_: set()
    return TestClient(app), originals


def _restore(originals):
    from app.main import app
    from app.services.user_service import UserPermissionService

    (
        UserPermissionService.check_user_has_permission,
        UserPermissionService.get_user_permission_slugs,
        UserPermissionService.check_user_has_any_permission,
        UserPermissionService.get_user_role_slugs,
    ) = originals
    app.dependency_overrides.clear()


class Api:
    def __init__(self, client, state):
        self.client = client
        self._state = state

    def as_(self, user_id: str) -> "Api":
        self._state["user"] = user_id
        return self

    def __getattr__(self, name):
        return getattr(self.client, name)


def _grant(db, user_id: str, slugs: set, company_id: str, *, integration: bool = False) -> None:
    """A real role carrying `slugs`, assigned to an ACTIVE user with a grant for the company."""
    from app.models.company import UserCompany
    from app.models.user import (
        User,
        UserPermission,
        UserRole,
        UserRoleAssignment,
        UserRolePermission,
    )

    user = db.get(User, user_id)
    user.status = "ACTIVE"
    user.is_integration = integration
    role = UserRole(id=uid(), slug=f"zzt-npa-{uid()[:8]}", name=f"{MARKER} npa role {uid()[:8]}")
    db.add(role)
    db.flush()
    for slug in slugs:
        perm = db.query(UserPermission).filter(UserPermission.slug == slug).first()
        if perm is None:
            perm = UserPermission(id=uid(), slug=slug, name=slug)
            db.add(perm)
            db.flush()
        db.add(UserRolePermission(id=uid(), role_id=role.id, permission_id=perm.id))
    db.add(UserRoleAssignment(id=uid(), user_id=user_id, role_id=role.id))
    db.add(UserCompany(id=uid(), user_id=user_id, company_id=company_id))
    db.flush()


def _refs(db):
    from app.models.procurement import Supplier
    from app.models.product import ItemType

    product = make_product(db)
    item_type = ItemType(id=uid(), item_type_code=f"ZZT{uid()[:6]}", item_type_name="KITCHEN SINK")
    supplier = Supplier(id=uid(), supplier_code=f"ZZT-S{uid()[:6]}", supplier_name=f"{MARKER} supplier")
    db.add_all([item_type, supplier])
    db.flush()
    return SimpleNamespace(
        category=product.category_id,
        uom=product.base_uom_id,
        brand=product.brand_id,
        item_type=item_type.id,
        supplier=supplier.id,
    )


def _inquiry(db, **over):
    from app.models.procurement import StockInquiry

    row = StockInquiry(
        id=uid(),
        inquiry_number=f"SI26-Z{uid()[:4]}",
        product_code="XY-1234-MB & XY-1234-BG",
        item_description="Kitchen sink, nanograin finish & kitchen sink, stainless steel",
        project_customer=f"{MARKER} EXAMPLE DEVELOPER SDN BHD",
        project_name=f"{MARKER} EXAMPLE RESIDENCE, TOWER B",
        quantity="55",
        delivery_date="2028-01-17",
        purchasing_response="Supplier can make it, please apply for a new code.",
        status="responded",
    )
    for k, v in over.items():
        setattr(row, k, v)
    db.add(row)
    db.flush()
    return row


@pytest.fixture()
def sent(monkeypatch):
    """Every notification the feature creates: (user_id, type, entity id)."""
    from app.services.notification_service import NotificationService

    calls = []

    def capture(self, **kw):
        calls.append((kw.get("user_id"), kw.get("type"), kw.get("source_entity_id")))

    monkeypatch.setattr(NotificationService, "create_with_channel_preferences", capture)
    return calls


@pytest.fixture()
def world(sent):
    from app.models.base import company_scope

    with blank_session() as db:
        company_id = sorento(db)
        admin = make_user(db, f"{MARKER} admin")
        sales = make_user(db, f"{MARKER} sales A")
        sales_b = make_user(db, f"{MARKER} sales B")
        manager = make_user(db, f"{MARKER} manager")
        manager_bot = make_user(db, f"{MARKER} manager bot")
        buyer = make_user(db, f"{MARKER} purchasing")
        viewer = make_user(db, f"{MARKER} viewer")
        stranger = make_user(db, f"{MARKER} stranger")
        perms = {
            admin: ALL,
            sales: {CREATE},
            sales_b: {CREATE},
            manager: {VIEW, APPROVE},
            manager_bot: {VIEW, APPROVE},
            buyer: {VIEW, OPEN_CODE},
            viewer: {VIEW},
            stranger: set(),
        }
        _grant(db, manager, {APPROVE}, company_id)
        _grant(db, manager_bot, {APPROVE}, company_id, integration=True)
        _grant(db, buyer, {OPEN_CODE}, company_id)
        _grant(db, sales, {CREATE, APPROVE}, company_id)  # an applicant who can also approve
        with company_scope(db, frozenset({company_id})):
            refs = _refs(db)
            product = make_product(db, code="ZZT-KS2433", name=f"{MARKER} nanograin sink")
            product2 = make_product(db, code="ZZT-KS2406", name=f"{MARKER} steel sink")
            inactive = make_product(db, active=False)
            customer = make_customer(db, company_id)
        inquiry = _inquiry(db)
        db.commit()

        state = {"user": sales}
        client, originals = _install_client(db, perms, state)
        api = Api(client, state)
        try:
            with company_scope(db, frozenset({company_id})):
                yield SimpleNamespace(
                    api=api, db=db, company_id=company_id, admin=admin, sales=sales,
                    sales_b=sales_b, manager=manager, manager_bot=manager_bot, buyer=buyer,
                    viewer=viewer, stranger=stranger, refs=refs, product=product,
                    product2=product2, inactive=inactive, customer=customer, inquiry=inquiry,
                    sent=sent,
                )
        finally:
            _restore(originals)


# ------------------------------------------------------------------ helpers


def _line(w, **over):
    body = {
        "proposed_code": "XY-1234-MB",
        "description": "Kitchen sink, nanograin finish",
        "brand_id": w.refs.brand,
        "expected_qty": "55",
    }
    body.update(over)
    return body


def _body(w, **over):
    body = {
        "stock_inquiry_id": w.inquiry.id,
        "customer_name": f"{MARKER} EXAMPLE DEVELOPER SDN BHD",
        "project_name": f"{MARKER} EXAMPLE RESIDENCE, TOWER B",
        "needed_by": "2028-01-17",
        "lines": [_line(w), _line(w, proposed_code="XY-1234-BG", description="Kitchen sink, stainless steel")],
    }
    body.update(over)
    return body


def _draft(w, user=None, **over):
    res = w.api.as_(user or w.sales).post(NPA, json=_body(w, **over))
    assert res.status_code == 201, res.text
    return res.json()


def _act(w, aid, action, user, **json):
    return w.api.as_(user).post(f"{NPA}/{aid}/{action}", json=json or None)


def _submitted(w, **over):
    d = _draft(w, **over)
    res = _act(w, d["id"], "submit", w.sales)
    assert res.status_code == 200, res.text
    return res.json()


def _approved(w, **over):
    d = _submitted(w, **over)
    res = _act(w, d["id"], "approve", w.manager)
    assert res.status_code == 200, res.text
    return res.json()


def _get(w, aid, user=None):
    res = w.api.as_(user or w.admin).get(f"{NPA}/{aid}")
    assert res.status_code == 200, res.text
    return res.json()


def _types(w, aid):
    return [t for (_u, t, e) in w.sent if e == aid]


def _to(w, aid, notif_type):
    return {u for (u, t, e) in w.sent if e == aid and t == notif_type}


# ------------------------------------------------------------------ AC-NPA-01..05 draft


def test_ac01_draft_is_numbered_per_company_and_owned_by_the_caller(world):
    first = _draft(world)
    second = _draft(world)
    assert first["application_no"] == "NPA-000001"
    assert second["application_no"] == "NPA-000002"
    assert first["status"] == "draft"
    assert first["source"] == "staff"
    assert first["applicant_id"] == world.sales
    assert [l["line_no"] for l in first["lines"]] == [1, 2]


def test_ac01_create_needs_the_create_permission(world):
    res = world.api.as_(world.stranger).post(NPA, json=_body(world))
    assert res.status_code == 403


def test_ac02_a_draft_saves_empty_fields_and_cleared_numbers_stay_null(world):
    d = _draft(world, lines=[{"description": None, "expected_qty": None, "dimension": None}])
    line = d["lines"][0]
    assert line["expected_qty"] is None
    assert line["cost_price"] is None
    assert line["dimension"] is None


def test_ac03_only_the_applicant_edits_a_draft(world):
    d = _draft(world)
    res = world.api.as_(world.sales_b).put(f"{NPA}/{d['id']}", json=_body(world, remark="x"))
    assert res.status_code == 403
    ok = world.api.as_(world.sales).put(f"{NPA}/{d['id']}", json=_body(world, remark="mine"))
    assert ok.status_code == 200, ok.text
    assert ok.json()["remark"] == "mine"


def test_ac03_put_replaces_the_lines(world):
    d = _draft(world)
    res = world.api.as_(world.sales).put(
        f"{NPA}/{d['id']}", json=_body(world, lines=[_line(world, proposed_code="ONLY")])
    )
    assert res.status_code == 200, res.text
    assert [l["proposed_code"] for l in res.json()["lines"]] == ["ONLY"]


def test_ac03_delete_draft_is_a_registered_countdown_action_for_the_owner_only(world):
    from app.services import new_product_application_service as svc
    from app.services.error_handler import AppException
    import app.services.record_actions  # noqa: F401  (registers the actions)
    from app.services.form_action_registry import get_action

    assert get_action("new_product_application.delete") is not None
    d = _draft(world)
    with pytest.raises(AppException) as not_yours:
        svc.assert_deletable(world.db, d["id"], world.sales_b)
    assert not_yours.value.status_code == 403
    svc.delete_draft(world.db, d["id"], world.sales)
    assert world.api.as_(world.admin).get(f"{NPA}/{d['id']}").status_code == 404


def test_ac03_a_submitted_application_is_not_deletable(world):
    from app.services import new_product_application_service as svc
    from app.services.error_handler import AppException

    d = _submitted(world)
    with pytest.raises(AppException) as exc:
        svc.assert_deletable(world.db, d["id"], world.sales)
    assert exc.value.status_code == 409


@pytest.mark.parametrize("field", ["brand_id"])
def test_ac04_an_unknown_reference_is_422_naming_the_field(world, field):
    res = world.api.as_(world.sales).post(NPA, json=_body(world, lines=[_line(world, **{field: uid()})]))
    assert res.status_code == 422, res.text
    assert field in res.text


def test_ac04_unknown_stock_inquiry_and_customer_are_refused(world):
    assert world.api.as_(world.sales).post(NPA, json=_body(world, stock_inquiry_id=uid())).status_code == 422
    assert world.api.as_(world.sales).post(NPA, json=_body(world, customer_id=uid())).status_code == 422


def test_ac05_prefill_copies_the_inquiry_as_text_and_matches_nothing(world):
    from app.models.order import Customer

    # A debtor whose name equals the inquiry's customer text must NOT be picked.
    same = world.db.query(Customer).filter(Customer.id == world.customer.id).one()
    same.customer_name = world.inquiry.project_customer
    world.db.flush()
    res = world.api.as_(world.sales).get(f"{NPA}/prefill", params={"stock_inquiry_id": world.inquiry.id})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["stock_inquiry_id"] == world.inquiry.id
    assert body["customer_id"] is None
    assert body["customer_name"] == world.inquiry.project_customer
    assert body["project_name"] == world.inquiry.project_name
    assert body["needed_by"] == "2028-01-17"
    assert len(body["lines"]) == 1
    line = body["lines"][0]
    assert line["proposed_code"] == "XY-1234-MB & XY-1234-BG"  # never split
    assert line["description"] == world.inquiry.item_description
    assert line["expected_qty"] == "55"
    assert line.get("category_id") is None


def test_ac05_prefill_leaves_a_non_numeric_quantity_and_bad_date_empty(world):
    inq = _inquiry(world.db, quantity="1141 pcs", delivery_date="end of month")
    res = world.api.as_(world.sales).get(f"{NPA}/prefill", params={"stock_inquiry_id": inq.id})
    assert res.status_code == 200, res.text
    assert res.json()["needed_by"] is None
    assert res.json()["lines"][0]["expected_qty"] is None


# ------------------------------------------------------------------ AC-NPA-10..14 submit / decide / lock


def test_ac10_submit_needs_at_least_one_line(world):
    d = _draft(world, lines=[])
    res = _act(world, d["id"], "submit", world.sales)
    assert res.status_code == 422
    assert _get(world, d["id"])["status"] == "draft"


def test_ac10_submit_names_the_product_and_the_missing_product_type(world):
    d = _draft(world, lines=[_line(world), _line(world, description=None)])
    res = _act(world, d["id"], "submit", world.sales)
    assert res.status_code == 422
    assert "Product 2: enter the product type." in res.text
    after = _get(world, d["id"])
    assert after["status"] == "draft"
    assert len(after["lines"]) == 2


def test_ac11_submit_moves_to_submitted_and_tells_the_approvers(world):
    d = _submitted(world)
    assert d["status"] == "submitted"
    assert d["submitted_at"]
    told = _to(world, d["id"], "new_product_application_submitted")
    # Active, non-integration approvers of the company; the applicant (who holds approve too)
    # is not told about their own application.
    assert told == {world.manager}


def test_ac11_only_the_applicant_submits(world):
    d = _draft(world)
    assert _act(world, d["id"], "submit", world.sales_b).status_code == 403


def test_ac12_a_rejected_application_is_edited_and_resubmitted_in_one_press(world):
    d = _submitted(world)
    rej = _act(world, d["id"], "reject", world.manager, reason="Supplier price too high")
    assert rej.status_code == 200, rej.text
    assert rej.json()["status"] == "rejected"
    assert rej.json()["reject_reason"] == "Supplier price too high"
    assert _to(world, d["id"], "new_product_application_rejected") == {world.sales}

    edit = world.api.as_(world.sales).put(f"{NPA}/{d['id']}", json=_body(world, remark="cheaper"))
    assert edit.status_code == 200, edit.text
    world.sent.clear()
    again = _act(world, d["id"], "submit", world.sales)
    assert again.status_code == 200, again.text
    assert again.json()["status"] == "submitted"
    assert _to(world, d["id"], "new_product_application_submitted") == {world.manager}


def test_ac13_approve_needs_the_approve_permission(world):
    d = _submitted(world)
    assert _act(world, d["id"], "approve", world.viewer).status_code == 403
    assert _act(world, d["id"], "reject", world.viewer, reason="no").status_code == 403


def test_ac13_approve_only_from_submitted(world):
    d = _draft(world)
    assert _act(world, d["id"], "approve", world.manager).status_code == 409


def test_ac13_reject_needs_a_reason(world):
    d = _submitted(world)
    assert _act(world, d["id"], "reject", world.manager, reason="  ").status_code == 422


def test_ac13_approve_tells_purchasing_and_stamps_the_decision(world):
    d = _approved(world)
    assert d["status"] == "approved"
    assert d["decided_by"] == world.manager
    assert _to(world, d["id"], "new_product_application_approved") == {world.buyer}


@pytest.mark.parametrize("state", ["submitted", "approved"])
def test_ac14_submitted_and_approved_lock_every_write(world, state):
    d = _submitted(world) if state == "submitted" else _approved(world)
    res = world.api.as_(world.sales).put(f"{NPA}/{d['id']}", json=_body(world, remark="sneaky"))
    assert res.status_code == 422
    assert "new_product_application_locked" in res.text


# ------------------------------------------------------------------ AC-NPA-20..23 revise / cancel


def test_ac20_revise_needs_a_reason(world):
    d = _approved(world)
    assert _act(world, d["id"], "revise", world.sales, reason="").status_code == 422


def test_ac20_revise_from_approved_returns_to_draft_and_keeps_the_reason(world):
    d = _approved(world)
    world.sent.clear()
    res = _act(world, d["id"], "revise", world.sales, reason="UOM is SET, not UNIT")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "draft"
    assert body["revise_reason"] == "UOM is SET, not UNIT"
    assert body["decided_by"] is None
    # AC-NPA-21: from Approved nobody is told.
    assert _types(world, d["id"]) == []


def test_ac20_an_approver_may_revise(world):
    d = _approved(world)
    assert _act(world, d["id"], "revise", world.manager, reason="wrong group").status_code == 200


def test_ac20_a_stranger_may_not_revise(world):
    d = _approved(world)
    assert _act(world, d["id"], "revise", world.sales_b, reason="x").status_code == 403


def test_ac20_revise_only_from_submitted_or_approved(world):
    d = _draft(world)
    assert _act(world, d["id"], "revise", world.sales, reason="x").status_code == 409


def test_ac21_revise_from_submitted_tells_the_approvers_it_was_withdrawn(world):
    d = _submitted(world)
    world.sent.clear()
    assert _act(world, d["id"], "revise", world.sales, reason="typo").status_code == 200
    assert _to(world, d["id"], "new_product_application_withdrawn") == {world.manager}


def test_ac22_revise_and_cancel_are_refused_once_a_line_is_resolved(world):
    d = _approved(world)
    line = d["lines"][0]["id"]
    assert world.api.as_(world.buyer).post(
        f"{NPA}/{d['id']}/lines/{line}/link", json={"product_id": world.product.id}
    ).status_code == 200
    assert _act(world, d["id"], "revise", world.sales, reason="x").status_code == 409
    assert _act(world, d["id"], "cancel", world.sales).status_code == 409


def test_ac23_the_applicant_cancels_and_it_is_terminal(world):
    d = _submitted(world)
    res = _act(world, d["id"], "cancel", world.sales, reason="customer dropped it")
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "cancelled"
    assert _act(world, d["id"], "submit", world.sales).status_code == 409
    put = world.api.as_(world.sales).put(f"{NPA}/{d['id']}", json=_body(world))
    assert put.status_code in (409, 422)


def test_ac23_someone_else_cannot_cancel(world):
    d = _draft(world)
    assert _act(world, d["id"], "cancel", world.sales_b).status_code == 403


# ------------------------------------------------------------------ AC-NPA-30..35 open the code


def _link(w, aid, line_id, product_id, user=None):
    return w.api.as_(user or w.buyer).post(
        f"{NPA}/{aid}/lines/{line_id}/link", json={"product_id": product_id}
    )


def test_ac30_purchasing_links_a_line_to_an_active_product(world):
    d = _approved(world)
    res = _link(world, d["id"], d["lines"][0]["id"], world.product.id)
    assert res.status_code == 200, res.text
    line = res.json()["lines"][0]
    assert line["opened_product_id"] == world.product.id
    assert line["opened_product_code"] == "ZZT-KS2433"
    assert line["resolved_by"] == world.buyer
    assert res.json()["status"] == "approved"  # line 2 still open


def test_ac30_linking_needs_open_code(world):
    d = _approved(world)
    assert _link(world, d["id"], d["lines"][0]["id"], world.product.id, user=world.sales).status_code == 403


def test_ac30_linking_only_on_an_approved_application(world):
    d = _submitted(world)
    assert _link(world, d["id"], d["lines"][0]["id"], world.product.id).status_code == 409


def test_ac30_inactive_unknown_and_other_company_products_are_refused(world):
    from app.models.base import company_scope

    d = _approved(world)
    line = d["lines"][0]["id"]
    assert _link(world, d["id"], line, world.inactive.id).status_code == 422
    assert _link(world, d["id"], line, uid()).status_code == 422
    other = second_company(world.db)
    with company_scope(world.db, frozenset({other})):
        foreign = make_product(world.db)
    assert _link(world, d["id"], line, foreign.id).status_code == 422


def test_ac30_a_line_of_another_application_is_404(world):
    a = _approved(world)
    b = _approved(world)
    assert _link(world, a["id"], b["lines"][0]["id"], world.product.id).status_code == 404


def test_ac31_product_search_ignores_dashes_and_case_and_only_lists(world):
    res = world.api.as_(world.buyer).get(f"{NPA}/products", params={"q": "zztks2433"})
    assert res.status_code == 200, res.text
    codes = [p["product_code"] for p in res.json()]
    assert "ZZT-KS2433" in codes
    assert world.api.as_(world.buyer).get(f"{NPA}/products", params={"q": ""}).json() == []
    inactive = world.api.as_(world.buyer).get(f"{NPA}/products", params={"q": world.inactive.product_code})
    assert world.inactive.product_code not in [p["product_code"] for p in inactive.json()]


def test_ac32_not_opening_needs_a_reason(world):
    d = _approved(world)
    line = d["lines"][1]["id"]
    url = f"{NPA}/{d['id']}/lines/{line}/close"
    assert world.api.as_(world.buyer).post(url, json={"reason": " "}).status_code == 422
    ok = world.api.as_(world.buyer).post(url, json={"reason": "supplier dropped BG"})
    assert ok.status_code == 200, ok.text
    assert ok.json()["lines"][1]["closed_reason"] == "supplier dropped BG"


def test_ac34_resolving_every_line_completes_and_tells_the_applicant(world):
    d = _approved(world)
    world.sent.clear()
    assert _link(world, d["id"], d["lines"][0]["id"], world.product.id).status_code == 200
    res = world.api.as_(world.buyer).post(
        f"{NPA}/{d['id']}/lines/{d['lines'][1]['id']}/close", json={"reason": "not needed"}
    )
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "completed"
    assert res.json()["completed_at"]
    assert _to(world, d["id"], "new_product_application_completed") == {world.sales}


def test_ac33_undo_reopens_a_completed_application(world):
    d = _approved(world)
    _link(world, d["id"], d["lines"][0]["id"], world.product.id)
    _link(world, d["id"], d["lines"][1]["id"], world.product2.id)
    assert _get(world, d["id"])["status"] == "completed"
    res = world.api.as_(world.buyer).post(f"{NPA}/{d['id']}/lines/{d['lines'][1]['id']}/undo")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "approved"
    assert body["completed_at"] is None
    assert body["lines"][1]["opened_product_id"] is None
    assert body["lines"][1]["resolved_by"] is None


def test_ac33_undo_needs_open_code(world):
    d = _approved(world)
    _link(world, d["id"], d["lines"][0]["id"], world.product.id)
    res = world.api.as_(world.sales).post(f"{NPA}/{d['id']}/lines/{d['lines'][0]['id']}/undo")
    assert res.status_code == 403


def test_ac35_a_resolved_line_cannot_be_linked_again(world):
    d = _approved(world)
    line = d["lines"][0]["id"]
    assert _link(world, d["id"], line, world.product.id).status_code == 200
    assert _link(world, d["id"], line, world.product2.id).status_code == 409


# ------------------------------------------------------------------ AC-NPA-40 notifications


def test_ac40_a_failing_notification_never_undoes_the_move(world, monkeypatch):
    from app.services.notification_service import NotificationService

    def boom(self, **kw):
        raise RuntimeError("smtp down")

    monkeypatch.setattr(NotificationService, "create_with_channel_preferences", boom)
    d = _submitted(world)
    assert _get(world, d["id"])["status"] == "submitted"


def test_ac40_draft_saves_and_cancels_notify_nobody(world):
    d = _draft(world)
    world.api.as_(world.sales).put(f"{NPA}/{d['id']}", json=_body(world, remark="x"))
    _act(world, d["id"], "cancel", world.sales)
    assert _types(world, d["id"]) == []


# ------------------------------------------------------------------ AC-NPA-50..53 reads


def test_ac50_view_sees_everyone_and_create_sees_own(world):
    mine = _draft(world)
    theirs = _draft(world, user=world.sales_b)
    own = world.api.as_(world.sales).get(NPA).json()
    ids = {r["id"] for r in own["items"]}
    assert mine["id"] in ids and theirs["id"] not in ids
    every = world.api.as_(world.viewer).get(NPA).json()
    ids = {r["id"] for r in every["items"]}
    assert {mine["id"], theirs["id"]} <= ids
    assert world.api.as_(world.stranger).get(NPA).status_code == 403


def test_ac50_list_searches_number_code_and_description_and_filters_status(world):
    a = _draft(world, lines=[_line(world, proposed_code="ZZTFINDME")])
    _submitted(world)
    by_code = world.api.as_(world.viewer).get(NPA, params={"q": "zztfindme"}).json()
    assert [r["id"] for r in by_code["items"]] == [a["id"]]
    drafts = world.api.as_(world.viewer).get(NPA, params={"status": "draft"}).json()
    assert {r["status"] for r in drafts["items"]} == {"draft"}
    assert by_code["total"] == 1


def test_ac50_list_by_stock_inquiry_feeds_the_inquiry_row(world):
    d = _draft(world)
    other = _inquiry(world.db)
    rows = world.api.as_(world.viewer).get(NPA, params={"stock_inquiry_id": world.inquiry.id}).json()
    assert [r["id"] for r in rows["items"]] == [d["id"]]
    none = world.api.as_(world.viewer).get(NPA, params={"stock_inquiry_id": other.id}).json()
    assert none["items"] == []


def test_ac51_detail_is_readable_by_owner_and_view_not_by_others(world):
    d = _draft(world)
    assert world.api.as_(world.sales).get(f"{NPA}/{d['id']}").status_code == 200
    assert world.api.as_(world.viewer).get(f"{NPA}/{d['id']}").status_code == 200
    assert world.api.as_(world.sales_b).get(f"{NPA}/{d['id']}").status_code == 403


def test_ac51_detail_resolves_labels_not_ids(world):
    d = _draft(world, customer_id=world.customer.id)
    got = _get(world, d["id"])
    assert got["stock_inquiry_number"] == world.inquiry.inquiry_number
    assert got["customer_code"] == world.customer.customer_code
    line = got["lines"][0]
    assert line["brand_name"]


def test_ac53_another_companys_application_is_invisible(world):
    from app.models.base import company_scope

    d = _draft(world)
    other = second_company(world.db)
    with company_scope(world.db, frozenset({other})):
        assert world.api.as_(world.admin).get(f"{NPA}/{d['id']}").status_code == 404
        listed = world.api.as_(world.admin).get(NPA).json()
        assert d["id"] not in {r["id"] for r in listed["items"]}


def test_item_type_select_is_gone(world):
    """v4 D3: the applicant no longer picks an item type, so the unused select is removed."""
    res = world.api.as_(world.sales).get(f"{NPA}/item-types", params={"q": "kitchen"})
    assert res.status_code in (404, 405, 422), res.text


# ------------------------------------------------------------------ review round 1


def test_review_list_rows_carry_the_opened_codes(world):
    """AC-NPA-52: the inquiry row shows the codes opened (it reads the LIST endpoint)."""
    d = _approved(world)
    assert _link(world, d["id"], d["lines"][0]["id"], world.product.id).status_code == 200
    rows = world.api.as_(world.viewer).get(NPA, params={"stock_inquiry_id": world.inquiry.id}).json()
    assert rows["items"][0]["opened_codes"] == ["ZZT-KS2433"]


def test_review_line_history_rolls_up_to_the_application():
    """Card example D: the application's audit trail shows a line's old values."""
    from app.models.new_product_application import NewProductApplicationLine
    from app.services import audit_service

    assert audit_service._parent_of(NewProductApplicationLine) == (
        "new_product_application",
        "application_id",
    )


def test_review_deleting_a_linked_product_is_a_named_409_not_a_500(world):
    from app.services.error_handler import AppException
    from app.services.product_service import ProductService

    d = _approved(world)
    assert _link(world, d["id"], d["lines"][0]["id"], world.product.id).status_code == 200
    with pytest.raises(AppException) as exc:
        ProductService(world.db).delete_product(world.product.id)
    assert exc.value.status_code == 409
    assert d["application_no"] in str(exc.value.message)


def test_review_moves_lock_the_application_row(world, monkeypatch):
    """Two purchasers finishing the last two lines at once must not leave it stuck in
    Approved: every move loads the row FOR UPDATE."""
    from app.services import new_product_application_service as svc

    seen = []
    original = svc.get_for

    def spy(db, application_id, *, contact_id=None, for_update=False):
        seen.append(for_update)
        return original(db, application_id, contact_id=contact_id, for_update=for_update)

    monkeypatch.setattr(svc, "get_for", spy)
    d = _approved(world)
    seen.clear()
    _link(world, d["id"], d["lines"][0]["id"], world.product.id)
    _act(world, d["id"], "revise", world.sales, reason="x")
    assert seen and all(seen)


def test_review_a_move_really_emits_select_for_update(world):
    """The spy above only proves the flag is passed; this proves the lock is taken."""
    from sqlalchemy import event

    d = _approved(world)
    statements = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    bind = world.db.get_bind()
    event.listen(bind, "before_cursor_execute", capture)
    try:
        assert _link(world, d["id"], d["lines"][0]["id"], world.product.id).status_code == 200
    finally:
        event.remove(bind, "before_cursor_execute", capture)
    assert any(
        "FROM" in st and "new_product_applications" in st and "FOR UPDATE" in st for st in statements
    ), statements[:5]


def test_review_withdrawn_is_not_sent_to_the_approver_who_revised(world):
    d = _submitted(world)
    world.sent.clear()
    assert _act(world, d["id"], "revise", world.manager, reason="wrong group").status_code == 200
    assert world.manager not in _to(world, d["id"], "new_product_application_withdrawn")


def test_review_staff_cannot_edit_a_portal_application(world):
    from app.models.new_product_application import NewProductApplication

    d = _draft(world)
    row = world.db.get(NewProductApplication, d["id"])
    row.source = "portal"
    world.db.commit()
    res = world.api.as_(world.sales).put(f"{NPA}/{d['id']}", json=_body(world, remark="x"))
    assert res.status_code == 409, res.text


@pytest.mark.parametrize("field", ["description"])
def test_review_line_text_is_capped(world, field):
    res = world.api.as_(world.sales).post(NPA, json=_body(world, lines=[_line(world, **{field: "x" * 5001})]))
    assert res.status_code == 422


def test_review_reason_is_capped(world):
    d = _submitted(world)
    assert _act(world, d["id"], "reject", world.manager, reason="x" * 5001).status_code == 422


def test_review_refusals_name_the_field_in_words(world):
    res = world.api.as_(world.sales).post(NPA, json=_body(world, lines=[_line(world, brand_id=uid())]))
    assert res.status_code == 422
    assert "brand" in res.text
    assert "brand_id does not exist" not in res.text


# ====================================================================================
# v4: the paper layout (AC-NPA-70..78). Written red-first from the UAC and the plan.
# ====================================================================================

from datetime import datetime  # noqa: E402
from decimal import Decimal  # noqa: E402

from ._npa_v4_support import (  # noqa: E402
    BAD_UPLOAD_CASES,
    IMAGE_FORMATS,
    bad_upload,
    REFUSED_LINE_KEYS,
    refused_value,
    SHEET_LABELS,
    downloaded_name,
    image_bytes,
    label_rows,
    noon,
    open_workbook,
    seed_attachment,
    sheet_values,
    text_of,
)

LOCKED_CODE = "new_product_application_locked"


@pytest.fixture()
def store(monkeypatch, world):
    from ._npa_v4_support import install_storage, seed_attachment_type

    seed_attachment_type(world.db)
    return install_storage(monkeypatch)


def _put(w, aid, lines, user=None, **over):
    return w.api.as_(user or w.sales).put(f"{NPA}/{aid}", json=_body(w, lines=lines, **over))


def _upload(w, aid, line_id, user=None, name="photo.png", data=None, mime="image/png"):
    return w.api.as_(user or w.sales).post(
        f"{NPA}/{aid}/lines/{line_id}/images",
        files={"file": (name, data if data is not None else image_bytes(), mime)},
    )


def _ok(res):
    assert res.status_code in (200, 201), res.text
    return res


def _images(w, aid, index=0):
    return _get(w, aid)["lines"][index]["images"]


def _feedback(w, aid, user=None, **body):
    return w.api.as_(user or w.buyer).put(f"{NPA}/{aid}/feedback", json=body)


def _rows_for(w, entity_type, entity_id):
    from app.models.entity_attachment import EntityAttachmentLink

    return (
        w.db.query(EntityAttachmentLink)
        .filter(EntityAttachmentLink.entity_type == entity_type, EntityAttachmentLink.entity_id == entity_id)
        .all()
    )


# ------------------------------------------------------------------ AC-NPA-70 the write body


def test_ac70_the_paper_fields_round_trip(world):
    d = _draft(
        world,
        lines=[
            _line(
                world,
                dimension="600 x 450 mm",
                material="Stainless steel",
                thickness="1.2 mm",
                packing="1 pc per carton",
            )
        ],
    )
    for got in (d["lines"][0], _get(world, d["id"])["lines"][0]):
        assert got["dimension"] == "600 x 450 mm"
        assert got["material"] == "Stainless steel"
        assert got["thickness"] == "1.2 mm"
        assert got["packing"] == "1 pc per carton"
        assert got["brand_id"] == world.refs.brand
        assert got["images"] == []


@pytest.mark.parametrize("key", REFUSED_LINE_KEYS)
def test_ac70_a_removed_line_key_is_422_naming_the_field_on_create(world, key):
    res = world.api.as_(world.sales).post(
        NPA, json=_body(world, lines=[_line(world, **{key: refused_value(key, world.refs)})])
    )
    assert res.status_code == 422, res.text
    assert key in res.text


@pytest.mark.parametrize("key", REFUSED_LINE_KEYS)
def test_ac70_a_removed_line_key_is_422_naming_the_field_on_update(world, key):
    d = _draft(world)
    res = _put(world, d["id"], [_line(world, **{key: refused_value(key, world.refs)})])
    assert res.status_code == 422, res.text
    assert key in res.text
    assert len(_get(world, d["id"])["lines"]) == 2  # the refused save changed nothing


@pytest.mark.parametrize("key", ["status", "application_no", "applicant_id"])
def test_ac70_an_unknown_header_key_is_422_naming_the_field(world, key):
    res = world.api.as_(world.sales).post(NPA, json=_body(world, **{key: "x"}))
    assert res.status_code == 422, res.text
    assert key in res.text


# ------------------------------------------------------------------ AC-NPA-71 products kept by id


def test_ac71_an_edit_keeps_the_product_id_and_its_image(world, store):
    d = _draft(world)
    first, second = [l["id"] for l in d["lines"]]
    _ok(_upload(world, d["id"], first))
    link_before = _images(world, d["id"])[0]["link_id"]

    res = _put(
        world,
        d["id"],
        [_line(world, id=first, description="Sink, now polished"), _line(world, id=second)],
    )
    assert res.status_code == 200, res.text
    lines = res.json()["lines"]
    assert [l["id"] for l in lines] == [first, second]
    assert lines[0]["description"] == "Sink, now polished"
    assert [i["link_id"] for i in lines[0]["images"]] == [link_before]


def test_ac71_a_product_without_an_id_is_added_in_body_order(world):
    d = _draft(world)
    first, second = [l["id"] for l in d["lines"]]
    res = _put(
        world,
        d["id"],
        [_line(world, proposed_code="NEW-1"), _line(world, id=second), _line(world, id=first)],
    )
    assert res.status_code == 200, res.text
    lines = res.json()["lines"]
    assert [l["line_no"] for l in lines] == [1, 2, 3]
    assert lines[0]["proposed_code"] == "NEW-1"
    assert lines[0]["id"] not in (first, second)
    assert [l["id"] for l in lines[1:]] == [second, first]


def test_ac71_a_product_left_out_is_deleted_with_its_image_links(world, store):
    d = _draft(world)
    first, second = [l["id"] for l in d["lines"]]
    _ok(_upload(world, d["id"], second))
    assert len(_rows_for(world, "new_product_application_line", second)) == 1

    res = _put(world, d["id"], [_line(world, id=first)])
    assert res.status_code == 200, res.text
    assert [l["id"] for l in res.json()["lines"]] == [first]
    assert _rows_for(world, "new_product_application_line", second) == []


@pytest.mark.parametrize("which", ["other_application", "unknown"])
def test_ac71_a_line_id_of_another_application_is_422(world, which):
    mine = _draft(world)
    other = _draft(world)
    foreign = other["lines"][0]["id"] if which == "other_application" else uid()
    res = _put(world, mine["id"], [_line(world, id=foreign)])
    assert res.status_code == 422, res.text
    assert [l["id"] for l in _get(world, other["id"])["lines"]] == [l["id"] for l in other["lines"]]
    assert len(_get(world, mine["id"])["lines"]) == 2


# ------------------------------------------------------------------ AC-NPA-72 submit


def test_ac72_submit_names_every_product_without_a_type(world):
    d = _draft(world, lines=[_line(world, description=None), _line(world), _line(world, description="  ")])
    res = _act(world, d["id"], "submit", world.sales)
    assert res.status_code == 422
    assert "Product 1: enter the product type." in res.text
    assert "Product 3: enter the product type." in res.text
    assert "Product 2: enter the product type." not in res.text
    assert _get(world, d["id"])["status"] == "draft"


def test_ac72_a_product_with_only_a_type_submits(world):
    d = _draft(world, lines=[{"description": "Kitchen sink"}])
    res = _act(world, d["id"], "submit", world.sales)
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "submitted"


def test_ac72_submit_needs_at_least_one_product(world):
    d = _draft(world, lines=[])
    assert _act(world, d["id"], "submit", world.sales).status_code == 422


# ------------------------------------------------------------------ AC-NPA-73 images


@pytest.mark.parametrize("fmt, mime, name", IMAGE_FORMATS)
def test_ac73_the_applicant_uploads_a_jpeg_png_or_webp(world, store, fmt, mime, name):
    d = _draft(world)
    res = _ok(_upload(world, d["id"], d["lines"][0]["id"], name=name, data=image_bytes(fmt), mime=mime))
    assert res.status_code in (200, 201)
    images = _images(world, d["id"])
    assert len(images) == 1
    image = images[0]
    assert image["filename"] == name
    assert image["content_type"] == mime
    assert image["url"] and image["link_id"] and image["attachment_id"]
    assert _images(world, d["id"], 1) == []


@pytest.mark.parametrize(
    "name, mime, data",
    [("notes.txt", "text/plain", b"hello"), ("sheet.pdf", "application/pdf", b"%PDF-1.4 fake")],
)
def test_ac73_anything_but_an_image_is_422(world, store, name, mime, data):
    d = _draft(world)
    res = _upload(world, d["id"], d["lines"][0]["id"], name=name, data=data, mime=mime)
    assert res.status_code == 422, res.text
    assert _images(world, d["id"]) == []


def test_ac73_upload_is_open_again_after_a_rejection(world, store):
    d = _submitted(world)
    assert _act(world, d["id"], "reject", world.manager, reason="Add a photo").status_code == 200
    _ok(_upload(world, d["id"], d["lines"][0]["id"]))
    assert len(_images(world, d["id"])) == 1


@pytest.mark.parametrize("state", ["submitted", "approved"])
def test_ac73_images_are_locked_while_submitted_or_approved(world, store, state):
    d = _draft(world)
    line = d["lines"][0]["id"]
    _ok(_upload(world, d["id"], line))
    link_id = _images(world, d["id"])[0]["link_id"]
    att_id, _ = seed_attachment(world.db, store, "stock_inquiry", world.inquiry.id, "site.png", image_bytes(), "image/png")
    assert _act(world, d["id"], "submit", world.sales).status_code == 200
    if state == "approved":
        assert _act(world, d["id"], "approve", world.manager).status_code == 200

    up = _upload(world, d["id"], line)
    cp = world.api.as_(world.sales).post(f"{NPA}/{d['id']}/lines/{line}/images/copy", json={"attachment_id": att_id})
    rm = world.api.as_(world.sales).delete(f"{NPA}/{d['id']}/lines/{line}/images/{link_id}")
    for res in (up, cp, rm):
        assert res.status_code == 422, res.text
        assert LOCKED_CODE in res.text
    assert len(_images(world, d["id"])) == 1


def test_ac73_only_the_owner_changes_images(world, store):
    d = _draft(world)
    line = d["lines"][0]["id"]
    _ok(_upload(world, d["id"], line))
    link_id = _images(world, d["id"])[0]["link_id"]
    att_id, _ = seed_attachment(world.db, store, "stock_inquiry", world.inquiry.id, "site.png", image_bytes(), "image/png")

    assert _upload(world, d["id"], line, user=world.sales_b).status_code == 403
    cp = world.api.as_(world.sales_b).post(f"{NPA}/{d['id']}/lines/{line}/images/copy", json={"attachment_id": att_id})
    assert cp.status_code == 403
    rm = world.api.as_(world.sales_b).delete(f"{NPA}/{d['id']}/lines/{line}/images/{link_id}")
    assert rm.status_code == 403
    assert len(_images(world, d["id"])) == 1


def test_ac73_copy_links_a_file_already_on_the_stock_inquiry(world, store):
    from app.models.resources import Attachment

    d = _draft(world)
    line = d["lines"][0]["id"]
    att_id, _ = seed_attachment(world.db, store, "stock_inquiry", world.inquiry.id, "site.png", image_bytes(), "image/png")
    before = world.db.query(Attachment).count()
    res = world.api.as_(world.sales).post(
        f"{NPA}/{d['id']}/lines/{line}/images/copy", json={"attachment_id": att_id}
    )
    _ok(res)
    images = _images(world, d["id"])
    assert [i["attachment_id"] for i in images] == [att_id]
    assert images[0]["filename"] == "site.png"
    assert world.db.query(Attachment).count() == before  # linked, never uploaded twice


@pytest.mark.parametrize("which", ["other_inquiry", "unknown"])
def test_ac73_copy_refuses_a_file_not_on_this_inquiry(world, store, which):
    d = _draft(world)
    line = d["lines"][0]["id"]
    if which == "other_inquiry":
        other = _inquiry(world.db)
        att_id, _ = seed_attachment(world.db, store, "stock_inquiry", other.id, "x.png", image_bytes(), "image/png")
    else:
        att_id = uid()
    res = world.api.as_(world.sales).post(
        f"{NPA}/{d['id']}/lines/{line}/images/copy", json={"attachment_id": att_id}
    )
    assert res.status_code == 422, res.text
    assert _images(world, d["id"]) == []


def test_ac73_unlink_removes_the_link_and_keeps_the_file_row(world, store):
    from app.models.resources import Attachment

    d = _draft(world)
    line = d["lines"][0]["id"]
    _ok(_upload(world, d["id"], line))
    image = _images(world, d["id"])[0]
    res = world.api.as_(world.sales).delete(f"{NPA}/{d['id']}/lines/{line}/images/{image['link_id']}")
    assert res.status_code in (200, 204), res.text
    assert _images(world, d["id"]) == []
    assert world.db.query(Attachment).filter(Attachment.id == image["attachment_id"]).count() == 1


# ------------------------------------------------------------------ AC-NPA-74 purchasing feedback


def _line_costs(w, aid):
    return [l["cost_price"] for l in _get(w, aid)["lines"]]


def test_ac74_open_code_saves_leadtime_and_cost_and_stamps_who_and_when(world):
    d = _approved(world)
    first, second = [l["id"] for l in d["lines"]]
    res = _feedback(
        world, d["id"], lead_time="3 weeks after PO",
        lines=[{"id": first, "cost_price": "12.50"}, {"id": second, "cost_price": 0}],
    )
    assert res.status_code == 200, res.text
    got = _get(world, d["id"])
    assert got["lead_time"] == "3 weeks after PO"
    assert [Decimal(l["cost_price"]) for l in got["lines"]] == [Decimal("12.50"), Decimal("0")]
    assert got["feedback_by_name"] == f"{MARKER} purchasing"
    assert got["feedback_at"]
    # No approval or status change: still Approved, still decided by the approver.
    assert got["status"] == "approved"
    assert got["decided_by"] == world.manager
    assert got["completed_at"] is None


@pytest.mark.parametrize("who", ["viewer", "sales", "stranger", "manager"])
def test_ac74_only_open_code_may_save_feedback(world, who):
    d = _approved(world)
    res = _feedback(world, d["id"], user=getattr(world, who), lead_time="1 week")
    assert res.status_code == 403, res.text
    assert _get(world, d["id"])["lead_time"] is None


@pytest.mark.parametrize("state", ["draft", "submitted", "rejected", "cancelled"])
def test_ac74_feedback_is_409_before_approval_or_after_a_stop(world, state):
    d = _draft(world)
    if state in ("submitted", "rejected"):
        assert _act(world, d["id"], "submit", world.sales).status_code == 200
    if state == "rejected":
        assert _act(world, d["id"], "reject", world.manager, reason="no").status_code == 200
    if state == "cancelled":
        assert _act(world, d["id"], "cancel", world.sales).status_code == 200
    res = _feedback(world, d["id"], lead_time="1 week")
    assert res.status_code == 409, res.text
    assert _get(world, d["id"])["lead_time"] is None


def test_ac74_feedback_is_open_on_a_completed_application(world):
    d = _approved(world)
    assert _link(world, d["id"], d["lines"][0]["id"], world.product.id).status_code == 200
    assert _link(world, d["id"], d["lines"][1]["id"], world.product2.id).status_code == 200
    assert _get(world, d["id"])["status"] == "completed"
    res = _feedback(world, d["id"], lead_time="2 weeks")
    assert res.status_code == 200, res.text
    got = _get(world, d["id"])
    assert got["lead_time"] == "2 weeks"
    assert got["status"] == "completed"


def test_ac74_a_cost_below_zero_is_422_and_saves_nothing(world):
    d = _approved(world)
    first = d["lines"][0]["id"]
    res = _feedback(world, d["id"], lead_time="9 days", lines=[{"id": first, "cost_price": "-0.01"}])
    assert res.status_code == 422, res.text
    got = _get(world, d["id"])
    assert got["lead_time"] is None
    assert _line_costs(world, d["id"]) == [None, None]


def test_ac74_an_empty_cost_clears_it_to_null(world):
    d = _approved(world)
    first = d["lines"][0]["id"]
    _ok(_feedback(world, d["id"], lines=[{"id": first, "cost_price": "7.25"}]))
    assert Decimal(_line_costs(world, d["id"])[0]) == Decimal("7.25")
    _ok(_feedback(world, d["id"], lines=[{"id": first, "cost_price": None}]))
    assert _line_costs(world, d["id"])[0] is None


def test_ac74_feedback_notifies_nobody(world):
    d = _approved(world)
    world.sent.clear()
    _ok(_feedback(world, d["id"], lead_time="5 days"))
    assert _types(world, d["id"]) == []
    assert world.sent == []


def test_ac74_feedback_writes_an_audit_row(world):
    import json

    from app.models.audit import AuditLog

    d = _approved(world)
    world.db.commit()

    def rows():
        return (
            world.db.query(AuditLog)
            .filter(AuditLog.entity_type == "new_product_application", AuditLog.entity_id == d["id"])
            .all()
        )

    before = len(rows())
    _ok(_feedback(world, d["id"], lead_time="a distinctive lead time"))
    world.db.commit()
    after = rows()
    assert len(after) > before
    assert any("a distinctive lead time" in json.dumps(r.new_values or {}) for r in after)


# ------------------------------------------------------------------ AC-NPA-75 revise


def test_ac75_revise_clears_leadtime_every_cost_and_the_stamp(world):
    d = _approved(world)
    first, second = [l["id"] for l in d["lines"]]
    _ok(_feedback(world, d["id"], lead_time="3 weeks",
                  lines=[{"id": first, "cost_price": "12.50"}, {"id": second, "cost_price": "8.00"}]))
    assert _get(world, d["id"])["feedback_at"]
    res = _act(world, d["id"], "revise", world.sales, reason="wrong packing")
    assert res.status_code == 200, res.text
    got = _get(world, d["id"])
    assert got["status"] == "draft"
    assert got["lead_time"] is None
    assert got["feedback_by_name"] is None
    assert got["feedback_at"] is None
    assert _line_costs(world, d["id"]) == [None, None]


# ------------------------------------------------------------------ AC-NPA-76 read-only values from the linked product


def _linked_product(w, *, suppliers):
    """A product with a category, a base UOM, list price 100 and `suppliers`:
    [(name, is_primary, created_at)]."""
    from app.models.procurement import ProductSupplier, Supplier

    product = make_product(w.db, name=f"{MARKER} D3 item {uid()[:6]}")
    for name, primary, created in suppliers:
        supplier = Supplier(id=uid(), supplier_code=f"ZZT-S{uid()[:6]}", supplier_name=name)
        w.db.add(supplier)
        w.db.flush()
        w.db.add(
            ProductSupplier(
                id=uid(), product_id=product.id, supplier_id=supplier.id,
                is_primary_supplier=primary, created_at=created,
            )
        )
    w.db.flush()
    return product


def _opened(w, product):
    d = _approved(w)
    res = _link(w, d["id"], d["lines"][0]["id"], product.id)
    assert res.status_code == 200, res.text
    return _get(w, d["id"])["lines"][0]


def test_ac76_before_a_link_the_read_only_values_are_empty(world):
    d = _approved(world)
    line = _get(world, d["id"])["lines"][0]
    for key in ("opened_category_name", "opened_base_uom_name", "opened_list_price", "opened_supplier_name"):
        assert key in line, key
        assert line[key] is None, key


def test_ac76_a_linked_product_shows_group_uom_price_and_the_primary_supplier(world):
    from app.models.product import ProductCategory, UnitOfMeasure

    product = _linked_product(
        world,
        suppliers=[
            ("Older Example Supplier", False, datetime(2026, 1, 1)),
            ("Primary Example Supplier", True, datetime(2026, 6, 1)),
        ],
    )
    line = _opened(world, product)
    assert line["opened_category_name"] == world.db.get(ProductCategory, product.category_id).category_name
    assert line["opened_base_uom_name"] == world.db.get(UnitOfMeasure, product.base_uom_id).uom_name
    assert Decimal(str(line["opened_list_price"])) == Decimal("100")
    assert line["opened_supplier_name"] == "Primary Example Supplier"
    assert line.get("category_id") is None  # shown, never copied into the application


def test_ac76_with_no_primary_the_oldest_supplier_row_wins(world):
    product = _linked_product(
        world,
        suppliers=[
            ("Newer Example Supplier", False, datetime(2026, 6, 1)),
            ("Oldest Example Supplier", False, datetime(2026, 1, 1)),
        ],
    )
    assert _opened(world, product)["opened_supplier_name"] == "Oldest Example Supplier"


def test_ac76_a_product_with_no_supplier_shows_none(world):
    product = _linked_product(world, suppliers=[])
    assert _opened(world, product)["opened_supplier_name"] is None


# ------------------------------------------------------------------ AC-NPA-77 Download Excel


def _xlsx_app(w, **over):
    """An Approved application with made-up values and purchasing feedback saved."""
    from app.models.new_product_application import NewProductApplication
    from app.models.user import User

    w.db.get(User, w.sales).name = "Alex Tan"
    lines = over.pop(
        "lines",
        [
            _line(
                w, proposed_code="XY-1234-MB", description="Sink A", dimension="600 x 450 mm",
                material="Stainless steel", thickness="1.2 mm", packing="1 pc per carton",
                expected_qty="55",
            ),
            _line(w, proposed_code="XY-1234-BG", description="Sink B"),
        ],
    )
    d = _approved(
        w, customer_name=over.pop("customer_name", "Example Developer Sdn Bhd"),
        project_name="Example Residence, Tower B", remark="Deliver in two drops", lines=lines, **over,
    )
    row = w.db.get(NewProductApplication, d["id"])
    row.created_at = noon()
    w.db.commit()
    _ok(_feedback(w, d["id"], lead_time="3 weeks after PO",
                  lines=[{"id": d["lines"][0]["id"], "cost_price": "12.50"}]))
    return _get(w, d["id"])


def _download(w, aid, user=None):
    return w.api.as_(user or w.viewer).get(f"{NPA}/{aid}/download")


def _workbook(w, aid, user=None):
    res = _download(w, aid, user)
    assert res.status_code == 200, res.text
    return res, open_workbook(res.content)


def test_ac77_one_sheet_per_product_with_the_paper_rows_in_order(world):
    d = _xlsx_app(world)
    res, wb = _workbook(world, d["id"])
    assert res.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert wb.sheetnames == ["Product 1", "Product 2"]
    for ws in wb.worksheets:
        assert [label for label, _row in label_rows(ws)] == SHEET_LABELS, ws.title


def test_ac77_the_cells_carry_the_application_values(world):
    d = _xlsx_app(world)
    _res, wb = _workbook(world, d["id"])
    one = sheet_values(wb["Product 1"])
    assert text_of(one["PRODUCT CODE:"]) == "XY-1234-MB"
    assert text_of(one["PRODUCT TYPE:"]) == "Sink A"
    assert text_of(one["DIMENSION:"]) == "600 x 450 mm"
    assert text_of(one["MATERIAL:"]) == "Stainless steel"
    assert text_of(one["THICKNESS:"]) == "1.2 mm"
    assert text_of(one["PACKING"]) == "1 pc per carton"
    assert float(text_of(one["QTY:"])) == 55
    assert text_of(one["DATE:"]) == "17/01/2028"
    assert text_of(one["SALES PERSON:"]) == "Alex Tan"
    assert text_of(one["CUSTOMER:"]) == "Example Developer Sdn Bhd"
    assert text_of(one["PROJECT:"]) == "Example Residence, Tower B"
    assert text_of(one["REMARK:"]) == "Deliver in two drops"
    assert "2028" in text_of(one["TARGET DELIVERY:"])
    assert float(text_of(one["COST:"])) == 12.5
    assert text_of(one["LEADTIME:"]) == "3 weeks after PO"
    two = sheet_values(wb["Product 2"])
    assert text_of(two["PRODUCT CODE:"]) == "XY-1234-BG"
    assert text_of(two["COST:"]) == ""  # no cost saved for product 2
    assert text_of(two["LEADTIME:"]) == "3 weeks after PO"  # one per application


def test_ac77_the_file_name_and_the_reff_cell_agree(world):
    d = _xlsx_app(world)
    res, wb = _workbook(world, d["id"])
    name = downloaded_name(res)
    assert name == (
        "NPA_20280117_AT_Example Developer Sdn Bhd (XY-1234-MB Sink A) (XY-1234-BG Sink B).xlsx"
    )
    stem = name[: -len(".xlsx")]
    for ws in wb.worksheets:
        assert text_of(sheet_values(ws)["REFF:"]) == stem


def test_ac77_a_file_name_drops_forbidden_characters_and_is_capped(world):
    d = _xlsx_app(world, customer_name='Example/Dev: "Sdn" <Bhd>? ' + "Z" * 200)
    res, wb = _workbook(world, d["id"])
    name = downloaded_name(res)
    assert name.endswith(".xlsx") and name.startswith("NPA_20280117_AT_")
    assert not any(ch in name for ch in '/\\:*?"<>|')
    assert len(name) <= 255
    assert text_of(sheet_values(wb["Product 1"])["REFF:"]) == name[: -len(".xlsx")]


def test_ac77_labels_are_bold_right_values_wrapped_and_bordered(world):
    d = _xlsx_app(world)
    _res, wb = _workbook(world, d["id"])
    ws = wb["Product 1"]
    row = dict(label_rows(ws))["PRODUCT TYPE:"]
    label, value = ws.cell(row=row, column=1), ws.cell(row=row, column=2)
    assert label.font.b is True
    assert label.alignment.horizontal == "right"
    assert value.alignment.wrap_text is True
    for cell in (label, value):
        for side in ("left", "right", "top", "bottom"):
            assert getattr(cell.border, side).style == "thin", (cell.coordinate, side)


def test_ac77_a4_portrait_fit_to_one_page(world):
    d = _xlsx_app(world)
    _res, wb = _workbook(world, d["id"])
    for ws in wb.worksheets:
        assert ws.page_setup.orientation == "portrait"
        assert str(ws.page_setup.paperSize) == "9"
        assert ws.sheet_properties.pageSetUpPr.fitToPage is True
        assert ws.page_setup.fitToWidth == 1
        assert ws.page_setup.fitToHeight == 1


def test_ac77_a_value_starting_with_equals_is_text_not_a_formula(world):
    d = _xlsx_app(
        world,
        lines=[_line(world, description="=SUM(A1)", material="@cmd", packing="-2+3")],
    )
    _res, wb = _workbook(world, d["id"])
    values = sheet_values(wb["Product 1"])
    for label, needle in (("PRODUCT TYPE:", "SUM(A1)"), ("MATERIAL:", "cmd"), ("PACKING", "2+3")):
        cell = values[label]
        assert cell.data_type != "f", label
        assert needle in text_of(cell), label


def test_ac77_the_first_image_sits_in_the_image_row(world, store):
    d = _xlsx_app(world)
    first = d["lines"][0]["id"]
    # The application is Approved (locked), so attach through the service the way an earlier
    # draft would have left it.
    seed_attachment(world.db, store, "new_product_application_line", first, "front.png", image_bytes(), "image/png")
    world.db.commit()
    _res, wb = _workbook(world, d["id"])
    assert len(wb["Product 1"]._images) == 1
    assert len(wb["Product 2"]._images) == 0


def test_ac77_an_attachment_that_is_not_an_image_shows_its_file_name(world, store):
    d = _xlsx_app(world)
    first = d["lines"][0]["id"]
    seed_attachment(world.db, store, "new_product_application_line", first, "broken.png", b"not an image at all", "image/png")
    world.db.commit()
    _res, wb = _workbook(world, d["id"])
    ws = wb["Product 1"]
    assert len(ws._images) == 0
    assert "broken.png" in text_of(sheet_values(ws)["IMAGE:"])


def test_ac77_an_image_over_40_megapixels_shows_its_file_name(world, store):
    import io

    from PIL import Image

    d = _xlsx_app(world)
    first = d["lines"][0]["id"]
    buf = io.BytesIO()
    Image.new("L", (7000, 6000), 128).save(buf, format="PNG")  # 42 MP
    seed_attachment(world.db, store, "new_product_application_line", first, "huge.png", buf.getvalue(), "image/png")
    world.db.commit()
    _res, wb = _workbook(world, d["id"])
    ws = wb["Product 1"]
    assert len(ws._images) == 0
    assert "huge.png" in text_of(sheet_values(ws)["IMAGE:"])


def test_ac77_whoever_can_view_downloads_and_nobody_else(world):
    d = _draft(world)
    assert _download(world, d["id"], world.viewer).status_code == 200
    assert _download(world, d["id"], world.sales).status_code == 200  # the owner, a draft
    assert _download(world, d["id"], world.stranger).status_code == 403
    assert _download(world, d["id"], world.sales_b).status_code == 403
    assert _download(world, uid(), world.viewer).status_code == 404


def test_ac77_another_companys_application_does_not_download(world):
    from app.models.base import company_scope

    d = _draft(world)
    assert _download(world, d["id"], world.admin).status_code == 200
    other = second_company(world.db)
    with company_scope(world.db, frozenset({other})):
        assert _download(world, d["id"], world.admin).status_code == 404


# ------------------------------------------------------------------ AC-NPA-78 staff keeps the staff-only values


def test_ac78_staff_detail_carries_cost_leadtime_and_the_opened_as_values(world):
    d = _approved(world)
    got = _get(world, d["id"])
    for key in ("lead_time", "feedback_by_name", "feedback_at"):
        assert key in got, key
    for key in ("cost_price", "opened_category_name", "opened_base_uom_name", "opened_list_price",
                "opened_supplier_name", "images", "dimension", "material", "thickness", "packing"):
        assert key in got["lines"][0], key


# ------------------------------------------------------------------ inquiry attachments picker (staff)


def _inq_atts(w, inquiry_id, user=None):
    return w.api.as_(user or w.sales).get(f"{NPA}/inquiry-attachments", params={"stock_inquiry_id": inquiry_id})


def test_inquiry_attachments_lists_only_images_of_that_inquiry(world, store):
    img, _ = seed_attachment(world.db, store, "stock_inquiry", world.inquiry.id, "site.png", image_bytes(), "image/png")
    seed_attachment(world.db, store, "stock_inquiry", world.inquiry.id, "quote.pdf", b"%PDF-1.4 fake", "application/pdf")
    other = _inquiry(world.db)
    seed_attachment(world.db, store, "stock_inquiry", other.id, "other.png", image_bytes(), "image/png")
    res = _inq_atts(world, world.inquiry.id)
    assert res.status_code == 200, res.text
    rows = res.json()
    assert [r["attachment_id"] for r in rows] == [img]
    assert rows[0]["filename"] == "site.png"
    assert rows[0]["content_type"] == "image/png"
    assert rows[0]["url"]


def test_inquiry_attachments_needs_create_and_a_known_inquiry(world, store):
    assert _inq_atts(world, world.inquiry.id, user=world.stranger).status_code == 403
    assert _inq_atts(world, world.inquiry.id, user=world.viewer).status_code == 403
    assert _inq_atts(world, uid()).status_code == 404


# ====================================================================================
# fix round (review + security findings on 8a6793b9fb)
# ====================================================================================


def test_s2_deleting_a_draft_leaves_no_image_links_behind(world, store):
    from app.services import new_product_application_service as svc

    d = _draft(world)
    lines = [l["id"] for l in d["lines"]]
    for line in lines:
        _ok(_upload(world, d["id"], line))
        assert len(_rows_for(world, "new_product_application_line", line)) == 1
    svc.delete_draft(world.db, d["id"], world.sales)
    world.db.flush()
    for line in lines:
        assert _rows_for(world, "new_product_application_line", line) == []


def test_staff_image_routes_are_refused_on_a_portal_raised_application(world, store):
    from app.models.new_product_application import NewProductApplication

    d = _draft(world)
    line = d["lines"][0]["id"]
    att, link = seed_attachment(world.db, store, "new_product_application_line", line, "a.png", image_bytes(), "image/png")
    inq_att, _ = seed_attachment(world.db, store, "stock_inquiry", world.inquiry.id, "b.png", image_bytes(), "image/png")
    row = world.db.get(NewProductApplication, d["id"])
    row.source = "portal"
    world.db.commit()
    put = world.api.as_(world.sales).put(f"{NPA}/{d['id']}", json=_body(world, remark="x"))
    assert put.status_code == 409, put.text
    base = f"{NPA}/{d['id']}/lines/{line}/images"
    api = world.api.as_(world.sales)
    for res in (
        _upload(world, d["id"], line),
        api.post(f"{base}/copy", json={"attachment_id": inq_att}),
        api.delete(f"{base}/{link}"),
    ):
        assert res.status_code == put.status_code, res.text
        assert res.json().get("code") == put.json().get("code")
    assert len(_rows_for(world, "new_product_application_line", line)) == 1


@pytest.mark.parametrize("case", BAD_UPLOAD_CASES)
def test_upload_validation_refuses_oversize_fake_and_huge_images(world, store, case):
    name, mime, data = bad_upload(case)
    d = _draft(world)
    res = _upload(world, d["id"], d["lines"][0]["id"], name=name, data=data, mime=mime)
    assert res.status_code == 422, res.text
    assert _images(world, d["id"]) == []


def test_xlsx_control_characters_are_removed_from_the_cells(world):
    d = _approved(
        world, remark="line\x0bbreak\x01", customer_name="Example Developer Sdn Bhd",
        lines=[_line(world, material="steel\x0b\x01plate", description="Sink\x08 A")],
    )
    _res, wb = _workbook(world, d["id"])
    values = sheet_values(wb["Product 1"])
    assert text_of(values["REMARK:"]) == "linebreak"
    assert text_of(values["MATERIAL:"]) == "steelplate"
    assert text_of(values["PRODUCT TYPE:"]) == "Sink A"


def _thumb_fixture(world, store, *, with_thumbnail):
    import io

    from PIL import Image

    from app.services.image_thumbnailer import thumbnail_key_for

    d = _xlsx_app(world)
    first = d["lines"][0]["id"]
    seed_attachment(world.db, store, "new_product_application_line", first, "front.png", image_bytes(size=(16, 12)), "image/png")
    key = next(k for k in store.files if k.endswith("front.png"))
    if with_thumbnail:
        buf = io.BytesIO()
        Image.new("RGB", (5, 7), (10, 10, 200)).save(buf, format="JPEG")
        store.files[thumbnail_key_for(key)] = buf.getvalue()
    world.db.commit()
    store.fetched.clear()
    return d, key


def _embedded_size(ws):
    import io

    from PIL import Image

    return Image.open(io.BytesIO(ws._images[0]._data())).size


def test_xlsx_embeds_the_stored_thumbnail_and_never_fetches_the_original(world, store):
    d, key = _thumb_fixture(world, store, with_thumbnail=True)
    _res, wb = _workbook(world, d["id"])
    assert len(wb["Product 1"]._images) == 1
    assert _embedded_size(wb["Product 1"]) == (5, 7)
    assert key not in store.fetched


def test_xlsx_falls_back_to_the_original_when_there_is_no_thumbnail(world, store):
    d, key = _thumb_fixture(world, store, with_thumbnail=False)
    _res, wb = _workbook(world, d["id"])
    assert _embedded_size(wb["Product 1"]) == (16, 12)
    assert key in store.fetched
