"""PS-QUOTE-RULES (CARD-ps-quote-rules-02nov.md), written BEFORE the implementation.

B1. A line outside the project's series needs a manager's approval (the existing
    ``projects.quotations.approve`` grant, nobody hard-coded) before the quotation can be sent.
B2. Asking for approval of a discount (a line below its minimum price) puts the project in Final
    Negotiation: the critical flag is raised and the stage moves forward to the
    ``final_negotiation`` rung when the graph has one. Withdrawn or rejected, it stays there.

Postgres only, via ``blank_session``; every row carries the ``zzt-qrules`` marker.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

import pytest

from app.models.product import Product, ProductCategory
from app.models.projects import ProjectSeries
from app.models.status import Status
from app.services.error_handler import AppException

from ._pg_fixture import blank_session
from .test_project_quotation_approval import (
    ABOVE_FLOOR,
    BELOW_FLOOR,
    EVERYTHING,
    LIST_PRICE,
    _setup,
    _sign,
    _status,
    _user,
)

MARKER = "zzt-qrules"


def _uid() -> str:
    return str(uuid.uuid4())


def _series_around(db, company_id: str, scope, product: Product) -> None:
    """Nominate a series on the scope whose category holds ``product``."""
    from app.services import project_pricing_service as pricing

    series = ProjectSeries(id=_uid(), company_id=company_id, name=f"{MARKER} Premium")
    db.add(series)
    db.flush()
    pricing.set_series_categories(db, series=series, category_ids=[product.category_id])
    scope.series_id = series.id
    db.flush()


def _outsider(db, product: Product) -> Product:
    """A product in a category the series does not nominate."""
    category = ProductCategory(
        id=_uid(),
        category_code=f"ZZT-{_uid()[:8]}",
        category_name=f"{MARKER} Kitchen Sinks",
    )
    db.add(category)
    db.flush()
    row = Product(
        id=_uid(),
        product_code=f"ZZT-{_uid()[:8]}",
        product_name=f"{MARKER} Sink",
        category_id=category.id,
        base_uom_id=product.base_uom_id,
        list_price=Decimal(LIST_PRICE),
    )
    db.add(row)
    db.flush()
    return row


def _line(db, scope, product, owner, unit_price: str):
    from app.services import project_quotation_service as quotes

    return quotes.upsert_line(
        db,
        version=quotes.current_version(db, scope.id),
        actor_user_id=owner,
        payload={"product_id": product.id, "unit_price": unit_price, "quantity": 2},
    )


def _ladder(db) -> dict:
    """Prod's ladder on top of the seeded one: final_negotiation and sponsorship_form after
    tendering, terminal rungs after them (prod made these in the admin editor)."""
    rows = {
        s.key: s
        for s in db.query(Status)
        .filter(Status.entity_type == "project", Status.scope_id.is_(None))
        .all()
    }
    for key, order in (("po_received", 7), ("lost", 8), ("dormant", 9)):
        rows[key].sort_order = order
    for key, label, order in (
        ("final_negotiation", "Final Negotiation", 5),
        ("sponsorship_form", "Sponsorship Form", 6),
    ):
        if key not in rows:
            rows[key] = Status(
                id=_uid(),
                entity_type="project",
                scope_id=None,
                key=key,
                label=label,
                sort_order=order,
            )
            db.add(rows[key])
    db.flush()
    return rows


def _ensure_default(db) -> None:
    """A configured default approver, so a test about something else can press Send."""
    from app.models.user import SystemSetting

    row = db.query(SystemSetting).first()
    if row is None:
        row = SystemSetting(id=_uid())
        db.add(row)
        db.flush()
    if not row.default_quotation_approver_user_id:
        row.default_quotation_approver_user_id = _approver(db, "Default Approver")
        db.flush()


def _ask(db, document, owner, *, ensure_default: bool = True) -> None:
    from app.services import project_quotation_approval_service as approval

    if ensure_default:
        _ensure_default(db)

    approval.move(
        db,
        document=document,
        to_status_id=_status(db, "pending_approval").id,
        actor_user_id=owner,
    )


# ------------------------------------------------------------------------- B1


def test_an_off_series_line_at_default_price_blocks_issue_until_approved():
    from app.services import project_quotation_approval_service as approval
    from app.services import project_quotation_document_service as qdocs

    with blank_session() as db:
        company_id, owner, product, _, document, scope = _setup(db)
        _series_around(db, company_id, scope, product)
        _line(db, scope, product, owner, LIST_PRICE)
        line = _line(db, scope, _outsider(db, product), owner, LIST_PRICE)
        assert line.is_non_standard is True
        assert line.is_below_floor is False

        assert approval.off_series_line_count(db, document) == 1
        assert approval.below_floor_line_count(db, document) == 0
        assert approval.requires_approval(db, document) is True

        _sign(db, document, owner)
        with pytest.raises(AppException) as refused:
            qdocs.issue(db, document=document, actor_user_id=owner)
        assert refused.value.status_code == 422
        assert refused.value.detail["code"] == "quotation_off_series_pending_approval"
        assert "outside the project's series" in refused.value.message
        assert qdocs.current_issue(db, document) is None

        _ask(db, document, owner)
        manager = document.approver_user_id
        approval.approve(db, document=document, actor_user_id=manager, permissions=EVERYTHING)
        assert qdocs.issue(db, document=document, actor_user_id=owner).issue_no == 1
        # Issuing spends the approval, exactly as for the minimum price.
        assert approval.current_key(db, document) == "issued"


def test_in_series_lines_and_a_project_without_series_are_not_gated():
    from app.services import project_quotation_approval_service as approval
    from app.services import project_quotation_document_service as qdocs

    with blank_session() as db:
        company_id, owner, product, _, document, scope = _setup(db)
        # No series nominated: nothing is off-series, even a product from anywhere.
        _line(db, scope, _outsider(db, product), owner, LIST_PRICE)
        assert approval.off_series_line_count(db, document) == 0
        assert approval.requires_approval(db, document) is False
        _sign(db, document, owner)
        assert qdocs.issue(db, document=document, actor_user_id=owner).issue_no == 1
        db.refresh(document)
        assert document.approval_status_id is None


def test_mixed_reasons_one_approval_and_the_message_names_both():
    from app.services import project_quotation_approval_service as approval
    from app.services import project_quotation_document_service as qdocs

    with blank_session() as db:
        company_id, owner, product, _, document, scope = _setup(db)
        _series_around(db, company_id, scope, product)
        _line(db, scope, product, owner, BELOW_FLOOR)
        _line(db, scope, _outsider(db, product), owner, LIST_PRICE)
        _sign(db, document, owner)
        with pytest.raises(AppException) as refused:
            qdocs.issue(db, document=document, actor_user_id=owner)
        # The minimum-price code stays the code whenever a line is below it (the screen and
        # older clients already handle it); the message names both reasons.
        assert refused.value.detail["code"] == "quotation_below_floor_pending_approval"
        assert "outside the project's series" in refused.value.message
        assert "below the minimum price" in refused.value.message

        block = approval.serialize_approval(db, document)
        assert block["requires_approval"] is True
        assert block["below_floor_line_count"] == 1
        assert block["off_series_line_count"] == 1


def test_an_off_series_approval_request_is_recorded_with_its_counts():
    from app.models.activities import ActivityEvent
    from app.services import project_quotation_approval_service as approval

    with blank_session() as db:
        company_id, owner, product, project, document, scope = _setup(db)
        _series_around(db, company_id, scope, product)
        _line(db, scope, _outsider(db, product), owner, LIST_PRICE)
        _ask(db, document, owner)
        row = (
            db.query(ActivityEvent)
            .filter(
                ActivityEvent.entity_id == str(project.id),
                ActivityEvent.system_template == "quotation_approval_requested",
            )
            .one()
        )
        assert row.system_payload["off_series_line_count"] == 1
        assert row.system_payload["below_floor_line_count"] == 0
        assert "outside the project's series" in (row.body_text or "")
        assert approval.current_key(db, document) == "pending_approval"


# ------------------------------------------------------------------------- B2


def _project_key(db, project) -> str:
    db.refresh(project)
    return db.query(Status).filter(Status.id == project.status_id).one().key


def _put_on(db, project, rows, key) -> None:
    project.status_id = rows[key].id
    db.flush()


def test_a_discount_request_moves_the_project_to_final_negotiation_and_raises_the_flag():
    from app.models.activities import ActivityEvent

    with blank_session() as db:
        _, owner, product, project, document, scope = _setup(db)
        rows = _ladder(db)
        _put_on(db, project, rows, "specified")
        _line(db, scope, product, owner, BELOW_FLOOR)
        assert project.is_critical is False

        _ask(db, document, owner)

        assert _project_key(db, project) == "final_negotiation"
        assert project.is_critical is True
        assert project.critical_at is not None
        moved = (
            db.query(ActivityEvent)
            .filter(
                ActivityEvent.entity_id == str(project.id),
                ActivityEvent.system_template == "stage_changed",
            )
            .one()
        )
        assert str(moved.actor_id) == owner
        assert moved.system_payload["to_status_id"] == str(rows["final_negotiation"].id)


def test_an_off_series_only_request_is_not_a_discount():
    with blank_session() as db:
        company_id, owner, product, project, document, scope = _setup(db)
        rows = _ladder(db)
        _put_on(db, project, rows, "specified")
        _series_around(db, company_id, scope, product)
        _line(db, scope, _outsider(db, product), owner, LIST_PRICE)

        _ask(db, document, owner)

        assert _project_key(db, project) == "specified"
        assert project.is_critical is False


@pytest.mark.parametrize("key", ["sponsorship_form", "po_received", "final_negotiation"])
def test_a_project_at_or_past_final_negotiation_keeps_its_stage(key):
    with blank_session() as db:
        _, owner, product, project, document, scope = _setup(db)
        rows = _ladder(db)
        _put_on(db, project, rows, key)
        _line(db, scope, product, owner, BELOW_FLOOR)

        _ask(db, document, owner)

        assert _project_key(db, project) == key
        assert project.is_critical is True


def test_without_a_final_negotiation_rung_only_the_flag_is_raised():
    with blank_session() as db:
        _, owner, product, project, document, scope = _setup(db)
        before = _project_key(db, project)
        _line(db, scope, product, owner, BELOW_FLOOR)

        _ask(db, document, owner)

        assert _project_key(db, project) == before
        assert project.is_critical is True


def test_the_flag_clock_is_not_reset_by_a_second_request():
    with blank_session() as db:
        _, owner, product, project, document, scope = _setup(db)
        _line(db, scope, product, owner, BELOW_FLOOR)
        project.is_critical = True
        project.critical_at = datetime(2026, 10, 1, 9, 0)
        db.flush()

        _ask(db, document, owner)

        assert project.critical_at == datetime(2026, 10, 1, 9, 0)


@pytest.mark.parametrize("ending", ["reject", "withdraw"])
def test_a_rejected_or_withdrawn_discount_leaves_the_project_in_final_negotiation(ending):
    from app.services import project_quotation_approval_service as approval

    with blank_session() as db:
        _, owner, product, project, document, scope = _setup(db)
        rows = _ladder(db)
        _put_on(db, project, rows, "quoted")
        _line(db, scope, product, owner, BELOW_FLOOR)
        _ask(db, document, owner)
        assert _project_key(db, project) == "final_negotiation"

        manager = document.approver_user_id
        if ending == "reject":
            approval.reject(
                db,
                document=document,
                actor_user_id=manager,
                reason="Too deep, try 5% less",
                permissions=EVERYTHING,
            )
        else:
            approval.revise_approval(db, document, owner, "Customer agreed list price")

        assert _project_key(db, project) == "final_negotiation"
        assert project.is_critical is True


def test_a_resubmitted_discount_after_rejection_also_moves_a_project_that_was_moved_back():
    from app.services import project_quotation_approval_service as approval

    with blank_session() as db:
        _, owner, product, project, document, scope = _setup(db)
        rows = _ladder(db)
        _put_on(db, project, rows, "quoted")
        _line(db, scope, product, owner, BELOW_FLOOR)
        _ask(db, document, owner)
        manager = document.approver_user_id
        approval.reject(
            db, document=document, actor_user_id=manager, reason="No", permissions=EVERYTHING
        )
        # Somebody moved it back by hand meanwhile.
        _put_on(db, project, rows, "quoted")

        _ask(db, document, owner)  # resubmit

        assert approval.current_key(db, document) in {"resubmitted", "pending_approval"}
        assert _project_key(db, project) == "final_negotiation"


# --------------------------------------------------------------- R1: any discount


def test_a_discount_above_the_minimum_price_still_needs_approval():
    """Owner ruling 21:20: ANY discount. 200 is above the floor (150) but below list (300)."""
    from app.services import project_quotation_approval_service as approval
    from app.services import project_quotation_document_service as qdocs

    with blank_session() as db:
        _, owner, product, _, document, scope = _setup(db)
        line = _line(db, scope, product, owner, ABOVE_FLOOR)
        assert line.is_below_floor is False
        assert line.is_discounted is True
        assert approval.discounted_line_count(db, document) == 1
        _sign(db, document, owner)
        with pytest.raises(AppException) as refused:
            qdocs.issue(db, document=document, actor_user_id=owner)
        assert refused.value.detail["code"] == "quotation_discount_pending_approval"
        assert "below the default price" in refused.value.message
        assert "floor" not in refused.value.message.lower()


def test_the_default_price_is_the_series_selling_price_when_the_series_names_one():
    from app.models.projects import ProjectSeriesProduct

    with blank_session() as db:
        company_id, owner, product, _, document, scope = _setup(db)
        _series_around(db, company_id, scope, product)
        db.add(
            ProjectSeriesProduct(
                series_id=scope.series_id,
                product_id=product.id,
                selling_price=Decimal("250.00"),
                max_discount_pct=Decimal("10"),
            )
        )
        db.flush()
        at_series = _line(db, scope, product, owner, "250.00")
        assert at_series.is_discounted is False  # below list, but at the agreed series price
        under = _line(db, scope, product, owner, "249.99")
        assert under.is_discounted is True


def test_a_line_at_or_above_its_default_price_is_not_a_discount_and_never_gated():
    from app.services import project_quotation_approval_service as approval
    from app.services import project_quotation_document_service as qdocs

    with blank_session() as db:
        _, owner, product, _, document, scope = _setup(db)
        _line(db, scope, product, owner, LIST_PRICE)
        _line(db, scope, product, owner, "320.00")
        assert approval.requires_approval(db, document) is False
        _sign(db, document, owner)
        assert qdocs.issue(db, document=document, actor_user_id=owner).issue_no == 1
        db.refresh(document)
        assert document.approval_status_id is None


# --------------------------------------------------------------- R4-R7: routing


def _approver(db, name: str, *, superior: str | None = None, grant: bool = True) -> str:
    """An active user, optionally holding the approve grant through a role, with a superior."""
    from app.models.user import (
        User,
        UserPermission,
        UserRole,
        UserRoleAssignment,
        UserRolePermission,
    )

    user_id = _uid()
    db.add(
        User(
            id=user_id,
            email=f"{user_id}@zzt.test",
            name=f"{MARKER} {name}",
            status="ACTIVE",
            superior_id=superior,
        )
    )
    db.flush()
    if grant:
        perm = db.query(UserPermission).filter(UserPermission.slug == APPROVE).first()
        if perm is None:
            perm = UserPermission(id=_uid(), slug=APPROVE, name="Approve")
            db.add(perm)
            db.flush()
        role = UserRole(id=_uid(), slug=f"zzt-{_uid()[:8]}", name=f"{MARKER} {_uid()[:8]}")
        db.add(role)
        db.flush()
        db.add(UserRolePermission(id=_uid(), role_id=role.id, permission_id=perm.id))
        db.add(UserRoleAssignment(id=_uid(), user_id=user_id, role_id=role.id))
        db.flush()
    return user_id


def _admin(db) -> str:
    from app.models.user import User, UserRole, UserRoleAssignment

    user_id = _uid()
    db.add(User(id=user_id, email=f"{user_id}@zzt.test", name=f"{MARKER} Admin", status="ACTIVE"))
    role = db.query(UserRole).filter(UserRole.slug == "admin").first()
    if role is None:
        role = UserRole(id=_uid(), slug="admin", name=f"{MARKER} admin")
        db.add(role)
    db.flush()
    db.add(UserRoleAssignment(id=_uid(), user_id=user_id, role_id=role.id))
    db.flush()
    return user_id


def _org(db, owner: str) -> dict:
    """CK on top; a southern manager reporting to CK; the owner reporting to the manager."""
    from app.models.user import User

    ck = _approver(db, "CK")
    south = _approver(db, "South Manager", superior=ck)
    db.query(User).filter(User.id == owner).update({"superior_id": south})
    db.flush()
    return {"ck": ck, "south": south}


APPROVE = "projects.quotations.approve"


def test_a_discount_routes_to_the_owners_superior_and_only_they_or_above_decide():
    from app.services import project_quotation_approval_service as approval

    with blank_session() as db:
        _, owner, product, _, document, scope = _setup(db)
        org = _org(db, owner)
        north = _approver(db, "North Manager", superior=org["ck"])
        _line(db, scope, product, owner, ABOVE_FLOOR)
        _ask(db, document, owner)

        assert document.approver_user_id == org["south"]
        block = approval.serialize_approval(db, document)
        assert block["approver_user_id"] == org["south"]
        assert block["approver_name"].endswith("South Manager")

        # Another region's manager holds the grant but is not on this line: refused.
        with pytest.raises(AppException) as refused:
            approval.approve(db, document=document, actor_user_id=north, permissions=EVERYTHING)
        assert refused.value.status_code == 403
        assert refused.value.detail["code"] == "quotation_approval_not_routed_to_you"

        # CK is above the southern manager: may act for them when they are away (R6).
        approval.approve(db, document=document, actor_user_id=org["ck"], permissions=EVERYTHING)
        assert approval.current_key(db, document) == "approved"


def test_the_routed_approver_decides_and_an_admin_may_too():
    from app.services import project_quotation_approval_service as approval

    with blank_session() as db:
        _, owner, product, _, document, scope = _setup(db)
        org = _org(db, owner)
        _line(db, scope, product, owner, ABOVE_FLOOR)
        _ask(db, document, owner)
        approval.reject(
            db, document=document, actor_user_id=org["south"], reason="No", permissions=EVERYTHING
        )
        _ask(db, document, owner)
        approval.approve(db, document=document, actor_user_id=_admin(db), permissions=EVERYTHING)
        assert approval.current_key(db, document) == "approved"


def test_the_project_override_beats_the_superior():
    with blank_session() as db:
        _, owner, product, project, document, scope = _setup(db)
        org = _org(db, owner)
        project.discount_approver_user_id = org["ck"]
        db.flush()
        _line(db, scope, product, owner, ABOVE_FLOOR)
        _ask(db, document, owner)
        assert document.approver_user_id == org["ck"]


def test_an_off_series_line_routes_to_the_off_series_approver_alone():
    from app.models.user import SystemSetting

    with blank_session() as db:
        company_id, owner, product, _, document, scope = _setup(db)
        org = _org(db, owner)
        settings_row = db.query(SystemSetting).first()
        if settings_row is None:
            settings_row = SystemSetting(id=_uid())
            db.add(settings_row)
        settings_row.off_series_approver_user_id = org["ck"]
        db.flush()
        _series_around(db, company_id, scope, product)
        _line(db, scope, product, owner, ABOVE_FLOOR)  # a discount too
        _line(db, scope, _outsider(db, product), owner, LIST_PRICE)
        _ask(db, document, owner)
        assert document.approver_user_id == org["ck"]


def test_a_superior_without_the_grant_hands_on_to_their_superior():
    from app.models.user import User

    with blank_session() as db:
        _, owner, product, _, document, scope = _setup(db)
        ck = _approver(db, "CK")
        team_lead = _approver(db, "Team Lead", superior=ck, grant=False)
        db.query(User).filter(User.id == owner).update({"superior_id": team_lead})
        db.flush()
        _line(db, scope, product, owner, ABOVE_FLOOR)
        _ask(db, document, owner)
        assert document.approver_user_id == ck


def test_a_manager_asking_on_a_project_they_own_goes_to_their_own_superior():
    with blank_session() as db:
        _, owner, product, project, document, scope = _setup(db)
        org = _org(db, owner)
        project.owner_user_id = org["south"]
        db.flush()
        _line(db, scope, product, owner, ABOVE_FLOOR)
        _ask(db, document, org["south"])
        assert document.approver_user_id == org["ck"]


def _settings(db):
    from app.models.user import SystemSetting

    row = db.query(SystemSetting).first()
    if row is None:
        row = SystemSetting(id=_uid())
        db.add(row)
        db.flush()
    return row


def test_nobody_else_routes_so_the_configured_default_approver_gets_it():
    from app.services import project_quotation_approval_service as approval

    with blank_session() as db:
        _, owner, product, _, document, scope = _setup(db)
        default = _approver(db, "Default Approver")
        _settings(db).default_quotation_approver_user_id = default
        db.flush()
        _line(db, scope, product, owner, ABOVE_FLOOR)
        _ask(db, document, owner)
        assert document.approver_user_id == default
        # Holding the grant is not enough (crew answer Q7): never "any approve holder".
        anyone = _approver(db, "Any Manager")
        with pytest.raises(AppException) as refused:
            approval.approve(db, document=document, actor_user_id=anyone, permissions=EVERYTHING)
        assert refused.value.detail["code"] == "quotation_approval_not_routed_to_you"


def test_with_nobody_configured_the_request_is_refused_and_nothing_moves():
    from app.services import project_quotation_approval_service as approval

    with blank_session() as db:
        _, owner, product, project, document, scope = _setup(db)
        _settings(db).default_quotation_approver_user_id = None
        db.flush()
        _line(db, scope, product, owner, ABOVE_FLOOR)
        with pytest.raises(AppException) as refused:
            _ask(db, document, owner, ensure_default=False)
        assert refused.value.detail["code"] == "quotation_approver_not_configured"
        assert approval.current_key(db, document) is None
        assert project.is_critical is False


def test_the_request_notification_goes_to_the_routed_approver_only(monkeypatch):
    from app.services import project_notify_service as notify
    from app.services import project_quotation_approval_service as approval

    sent = []
    monkeypatch.setattr(notify, "_send", lambda db, **kw: sent.append(kw) or 1)
    with blank_session() as db:
        _, owner, product, _, document, scope = _setup(db)
        org = _org(db, owner)
        _line(db, scope, product, owner, ABOVE_FLOOR)
        _ask(db, document, owner)
        notify.notify_quotation_approval_requested(
            db,
            project=approval._project_of(db, document),
            document=document,
            press="1",
            below=0,
            reasons=approval.reasons_text(approval.counts(db, document)),
            requester_id=owner,
            requester_name="Rep",
        )
        assert sent[-1]["user_ids"] == [org["south"]]
        assert "below the default price" in sent[-1]["body"]


def test_only_a_manager_may_set_the_project_override():
    from app.services import project_service

    with blank_session() as db:
        _, owner, _, project, _, _ = _setup(db)
        ck = _approver(db, "CK")
        with pytest.raises(AppException) as refused:
            project_service.update_project(
                db,
                project,
                payload={"discount_approver_user_id": ck},
                actor_user_id=owner,
                permissions={"projects.projects.view", "projects.projects.edit"},
            )
        assert refused.value.detail["code"] == "project_discount_approver_forbidden"
        project_service.update_project(
            db,
            project,
            payload={"discount_approver_user_id": ck},
            actor_user_id=owner,
            permissions=EVERYTHING,
        )
        assert project.discount_approver_user_id == ck
