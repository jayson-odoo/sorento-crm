"""Shared fixtures for the AC-QTSO-CRM red tests (AutoCount quotation + sales order writes).

Plan: `documentation/plans/autocount/PLAN-ac-qtso-crm-04nov.md` ("Phase 2 contract").

Three things live here so the five test files read as behaviour, not plumbing:

* `FakeSS`: the Shared Service as an `httpx.MockTransport` on
  `foundryx_autocount_client.TRANSPORT`. Every request is kept in `calls`, so a test asserts the
  exact gateway body, header and path the CRM sent, and "the client was never called" is
  `fake.calls == []`.
* `world` builders: a real published project SO (built and published through the draft service,
  the way `tests/test_project_so_worksheet.py` does), an amendment on it, and an accepted
  quotation document. Everything is seeded here; nothing is borrowed from existing rows.
* `route_client`: TestClient + dependency overrides, with the granted permission slugs explicit.

Postgres only, via `blank_session`.
"""
from __future__ import annotations

import json
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Callable, Optional

import httpx
import pytest

from app.models.inventory import Warehouse
from app.models.order import SalesOrder, SalesOrderLine
from app.models.project_so import (
    AMENDMENT_PUBLISHED,
    SO_STATUS_AMENDED,
    ProjectSalesOrderLine,
    SOAmendment,
)
from app.models.projects import (
    ProjectQuotation,
    ProjectQuotationDocument,
    ProjectQuotationIssue,
    ProjectQuotationIssueScope,
    ProjectQuotationLine,
    ProjectQuotationVersion,
)
from app.models.sales_agent import SalesAgent
from app.services import project_seed_service
from app.services.project_so_draft_service import ProjectSODraftService
from tests.support.fake_foundryx import seed_foundryx_connection

from ._pg_fixture import blank_session
from .test_project_so_draft import (
    _customer,
    _minimal,
    _party,
    _product,
    _project,
    _sorento,
    _uid,
    _user,
)

MARKER = "zzt-acwrite"
BASE = "/api/v1/project-sales"
VIEW = "projects.projects.view"
EDIT = "projects.projects.edit"
WRITE = "projects.autocount.write"
SS_BASE_URL = "http://fake-ss.test"
SS_API_KEY = "fxa_acwrite_test"

CAPS_PATH = "/api/v1/autocount/write-capabilities"
SO_CREATE_PATH = "/api/v1/autocount/documents/sales-orders"
QT_CREATE_PATH = "/api/v1/autocount/documents/quotations"

OFF_MESSAGE = (
    "AutoCount quotations and sales orders from Project sales are switched off in Settings."
)
WAITING = "Waiting for AutoCount"
SWITCHED_OFF_HERE = "Changes to AutoCount are switched off here"
UNREACHABLE_TEXT = "Could not reach AutoCount"
PENDING_TEXT = "Sent; AutoCount has not confirmed yet. It will show after the next sync."

#: The AutoCount book the fake Shared Service names and the stored records belong to (R8).
BOOK = "db3"
DOC_KEY = 12008
DTL_1 = 12009
DTL_2 = 12010
LAST_MODIFIED = "2026-10-01T09:30:00"


# --------------------------------------------------------------------------- fake SS


def cap_entry(op: str, kind: str, enabled: bool, reason: Optional[str] = None) -> dict:
    return {"op": op, "kind": kind, "enabled": enabled, "reasonCode": reason}


def default_capabilities() -> list[dict]:
    """The pinned SS contract: create/edit/add on, delete_line and cancel_doc OFF."""
    out: list[dict] = []
    for kind in ("quotations", "sales-orders"):
        out += [
            cap_entry("create_doc", kind, True),
            cap_entry("edit_doc", kind, True),
            cap_entry("add_line", kind, True),
            cap_entry("delete_line", kind, False, "VENDOR_UNSUPPORTED"),
            cap_entry("cancel_doc", kind, False, "VENDOR_UNSUPPORTED"),
        ]
    return out


def caps_with(**overrides: tuple[bool, Optional[str]]) -> list[dict]:
    """`caps_with(cancel_doc=(True, None))` flips that op for both kinds."""
    out = default_capabilities()
    for entry in out:
        if entry["op"] in overrides:
            entry["enabled"], entry["reasonCode"] = overrides[entry["op"]]
    return out


def detail(dtl_key: int, item: str, qty: str, price: str, loc: str, due: Optional[str], seq: int):
    return {
        "DtlKey": dtl_key,
        "Seq": seq,
        "ItemCode": item,
        "Description": f"{item} description",
        "Qty": float(qty),
        "UnitPrice": float(price),
        "Location": loc,
        "DeliveryDate": due,
    }


def done_body(
    *,
    doc_no: str = "SO412345",
    doc_key: int = DOC_KEY,
    details: Optional[list[dict]] = None,
    last_modified: str = "2026-11-05T10:15:00",
    warnings: Optional[list] = None,
) -> dict:
    return {
        "operationId": None,
        "actionId": "act-1",
        "outcome": "done",
        "errorCode": None,
        "message": "",
        "warnings": warnings or [],
        "docKey": doc_key,
        "docNo": doc_no,
        "replacedLines": [],
        "document": {
            "DocKey": doc_key,
            "DocNo": doc_no,
            "LastModified": last_modified,
            "Details": details if details is not None else [],
        },
    }


def refused_body(code: str, message: str, outcome: str = "refused") -> dict:
    return {
        "operationId": None,
        "actionId": "act-2",
        "outcome": outcome,
        "errorCode": code,
        "message": message,
        "warnings": [],
        "docKey": None,
        "docNo": None,
        "replacedLines": [],
        "document": None,
    }


class FakeSS:
    """Answers by `(METHOD, path)`; `answers[...]` is `(status, body)` or `callable(request)`."""

    def __init__(self) -> None:
        self.calls: list[httpx.Request] = []
        self.answers: dict[tuple[str, str], Any] = {
            ("GET", CAPS_PATH): (200, {"book": BOOK, "capabilities": default_capabilities()}),
        }
        self.transport_error: Optional[Exception] = None

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        if self.transport_error is not None:
            raise self.transport_error
        answer = self.answers.get((request.method, request.url.path))
        if answer is None:
            return httpx.Response(404, json={"code": "NOT_FOUND", "message": "no route"})
        if callable(answer):
            answer = answer(request)
        status, body = answer
        return httpx.Response(status, json=body)

    # ---- reading what was sent
    def writes(self) -> list[httpx.Request]:
        """Everything except the capability read."""
        return [r for r in self.calls if r.url.path != CAPS_PATH]

    def to(self, method: str, path: str) -> list[httpx.Request]:
        return [r for r in self.calls if r.method == method and r.url.path == path]

    @staticmethod
    def body(request: httpx.Request) -> dict:
        return json.loads(request.content)


def find_dicts(node: Any, **match: Any) -> list[dict]:
    """Every dict anywhere inside `node` whose keys equal `match` (numbers compared as Decimal).

    Used for the add-line POST, whose exact envelope (`line` or `lines[]`) the plan leaves open:
    the test pins the content, not the wrapper.
    """
    found: list[dict] = []

    def same(a: Any, b: Any) -> bool:
        try:
            return Decimal(str(a)) == Decimal(str(b))
        except Exception:
            return a == b

    def walk(n: Any) -> None:
        if isinstance(n, dict):
            if all(k in n and same(n[k], v) for k, v in match.items()):
                found.append(n)
            for v in n.values():
                walk(v)
        elif isinstance(n, list):
            for v in n:
                walk(v)

    walk(node)
    return found


@pytest.fixture
def fake_ss(monkeypatch) -> FakeSS:
    from app.services import foundryx_autocount_client as client_mod

    fake = FakeSS()
    monkeypatch.setattr(client_mod, "TRANSPORT", httpx.MockTransport(fake.handler), raising=False)
    # Owner ruling 11 Nov: the write service no longer keeps an attempt counter (no Redis): every
    # write but a create takes a fresh key each press, and a create holds its key on the record.
    return fake


# --------------------------------------------------------------------------- the settings switch


def set_switch(db, on: bool) -> None:
    """`system_settings.project_autocount_write_enabled` (R1)."""
    from app.models.user import SystemSetting

    row = db.query(SystemSetting).first()
    if row is None:
        row = SystemSetting(id=str(uuid.uuid4()), name=f"{MARKER} Co")
        db.add(row)
        db.flush()
    row.project_autocount_write_enabled = on
    db.flush()


# --------------------------------------------------------------------------- sales order world


class SoWorld:
    """What `build_so_world` hands back."""

    def __init__(self, **kw: Any) -> None:
        self.__dict__.update(kw)


def build_so_world(
    db,
    company_id: str,
    owner: str,
    *,
    debtor_code: str = "ZZT-DEBT-01",
    with_agent: bool = True,
    publish: bool = True,
) -> SoWorld:
    """A published project SO with two lines.

    Line 1 has no stock location of its own, so the derived one (agent group BB -> BRW-BB)
    applies. Line 2 names MWH-BB itself, so "location from the line else the derived location"
    is observable in one body.
    """
    if with_agent:
        db.add(Warehouse(id=_uid(), warehouse_code="BRW-BB", warehouse_name="BRW-BB", is_active=True))
        db.add(Warehouse(id=_uid(), warehouse_code="MWH-BB", warehouse_name="MWH-BB", is_active=True))
        agent = SalesAgent(id=_uid(), sales_agent=f"ZZT AGENT {_uid()[:4]}".upper(), location_group="BB")
        db.add(agent)
        db.flush()
    else:
        agent = None
    customer = _customer(db, "Buimaco")
    customer.customer_code = debtor_code
    customer.sales_agent_id = agent.id if agent else None
    db.flush()

    project, product, po, schedule = _minimal(db, company_id, owner, customer=customer)
    service = ProjectSODraftService(db)
    built = service.build(po.id, schedule.id)
    order = service.get_order(built["data"][0]["id"])
    if publish:
        service.publish(order, actor_user_id=owner)

    line1 = (
        db.query(ProjectSalesOrderLine)
        .filter(ProjectSalesOrderLine.project_sales_order_id == order.id)
        .order_by(ProjectSalesOrderLine.line_no.asc())
        .first()
    )
    line1.stock_location = None
    product2 = _product(db, f"ZZT-P2-{_uid()[:6]}")
    line2 = ProjectSalesOrderLine(
        id=_uid(),
        company_id=company_id,
        project_sales_order_id=order.id,
        line_no=line1.line_no + 1,
        product_id=product2.id,
        description="Second line",
        qty=Decimal("20"),
        uom="UNIT",
        unit_price=Decimal("50.00"),
        amount=Decimal("1000.00"),
        delivery_date=date(2026, 8, 1),
        stock_location="MWH-BB",
    )
    db.add(line2)
    db.flush()
    return SoWorld(
        service=service, order=order, project=project, product=product, product2=product2,
        po=po, customer=customer, agent=agent, line1=line1, line2=line2,
        company_id=company_id, owner=owner, db=db,
    )


def put_in_autocount(db, world: SoWorld) -> None:
    """The order already lives in AutoCount, with core lines carrying the SS dtlKeys."""
    order = world.order
    core = SalesOrder(id=_uid(), so_number="SO412345", status="open")
    db.add(core)
    db.flush()
    for line, product, dtl in ((world.line1, world.product, DTL_1), (world.line2, world.product2, DTL_2)):
        core_line = SalesOrderLine(
            id=_uid(),
            sales_order_id=core.id,
            product_id=product.id,
            qty_ordered=line.qty,
            qty_delivered=Decimal("0"),
            required_date=date(2026, 7, 1),
            source_system="autocount",
            source_ref=f"AED_SRT:{DOC_KEY}:{dtl}",
        )
        core_line.company_id = world.company_id
        db.add(core_line)
        db.flush()
        line.core_sales_order_line_id = core_line.id
    order.so_id = core.id
    order.autocount_doc_no = "SO412345"
    order.autocount_doc_key = str(DOC_KEY)
    order.autocount_book = BOOK
    order.autocount_last_modified = LAST_MODIFIED
    order.status = SO_STATUS_AMENDED
    db.flush()


def add_amendment(db, world: SoWorld, rows: list[dict], *, status: str = AMENDMENT_PUBLISHED) -> SOAmendment:
    amendment = SOAmendment(
        id=_uid(),
        company_id=world.company_id,
        project_sales_order_id=world.order.id,
        status=status,
        published_at=datetime.utcnow() if status == AMENDMENT_PUBLISHED else None,
        delta_json={"rows": rows},
        verb_summary={},
    )
    db.add(amendment)
    db.flush()
    return amendment


def _delta_row(world, line, verb: str, field: str, from_value, to_value) -> dict:
    """A row exactly as `ProjectSODeltaService` produces it, verb constants and all."""
    from app.services.project_so_delta_service import ProjectSODeltaService

    return ProjectSODeltaService(world.db)._row(
        order=world.order,
        line=line,
        product_id=line.product_id,
        verb=verb,
        field_name=field,
        from_value=from_value,
        to_value=to_value,
        qty=Decimal("1"),
    )


def order_row(world: SoWorld, line, to: str, *, verb: str = "ORDER") -> dict:
    """Quantity up on an existing line: ORDER, or RESERVE & ORDER inside the reserve window."""
    return _delta_row(world, line, verb, "qty", str(line.qty), to)


qty_row = order_row


def reserve_row(world: SoWorld, line, to: str) -> dict:
    return order_row(world, line, to, verb="RESERVE & ORDER")


def delay_row(world: SoWorld, line, to: str, *, verb: str = "DELAY") -> dict:
    return _delta_row(world, line, verb, "delivery_date", str(line.delivery_date), to)


def advance_row(world: SoWorld, line, to: str) -> dict:
    return delay_row(world, line, to, verb="ADVANCE")


def cancel_balance_row(world: SoWorld, line, to: str) -> dict:
    return _delta_row(world, line, "CANCEL BALANCE", "qty", str(line.qty), to)


def change_so_no_row(world: SoWorld, line, to: str = "TOWER B") -> dict:
    return _delta_row(world, line, "CHANGE SO NO", "area_group", world.order.area_group, to)


# --------------------------------------------------------------------------- quotation world


def build_qt_world(
    db,
    company_id: str,
    owner: str,
    *,
    accepted: bool = True,
    kind: str = "quotation",
    debtor_code: str = "ZZT-DEBT-QT",
) -> SoWorld:
    """A project quotation document with one issued revision R1 (accepted or not).

    Lines, in order: an ordinary line, a rate-only alternate, and a product set of 3 parts, so
    the R6 result note is observable end to end.
    """
    from app.models.product_set import ProductSet

    db.add(Warehouse(id=_uid(), warehouse_code="BRW-BB", warehouse_name="BRW-BB", is_active=True))
    agent = SalesAgent(id=_uid(), sales_agent=f"ZZT QAGENT {_uid()[:4]}".upper(), location_group="BB")
    db.add(agent)
    db.flush()
    customer = _customer(db, "QT Buimaco")
    customer.customer_code = debtor_code
    customer.sales_agent_id = agent.id
    party = _party(db, company_id, customer=customer)
    project = _project(db, company_id, owner)

    document = ProjectQuotationDocument(
        id=_uid(), company_id=company_id, project_id=project.id,
        document_no=f"{MARKER}-QT-{_uid()[:8]}", your_ref="YR-QT-77",
        recipient_party_id=party.id, kind=kind, payment_terms="30 days from invoice",
    )
    db.add(document)
    db.flush()
    scope = ProjectQuotation(
        id=_uid(), company_id=company_id, project_id=project.id, document_id=document.id,
        scope_label=f"{MARKER} scope",
    )
    db.add(scope)
    db.flush()
    version = ProjectQuotationVersion(
        id=_uid(), company_id=company_id, quotation_id=scope.id, version_no=1,
        total_amount=Decimal("0"),
    )
    db.add(version)
    db.flush()

    p1 = _product(db, f"ZZT-Q1-{_uid()[:6]}")
    p_alt = _product(db, f"ZZT-QA-{_uid()[:6]}")
    p_wc = _product(db, f"ZZT-WC-{_uid()[:6]}")
    p_av = _product(db, f"ZZT-AV-{_uid()[:6]}")
    pset = ProductSet(id=_uid(), set_code=f"ZZT-SET-{_uid()[:5]}", name="ZZT set")
    pset.company_id = company_id
    db.add(pset)
    db.flush()

    def line(**kw: Any) -> ProjectQuotationLine:
        row = ProjectQuotationLine(id=_uid(), company_id=company_id, version_id=version.id, **kw)
        db.add(row)
        return row

    line(product_id=p1.id, product_code_snapshot=p1.product_code, description_snapshot="Wash basin",
         unit_price=Decimal("180.00"), quantity=Decimal("10"), uom="UNIT",
         line_total=Decimal("1800.00"), sort_order=0)
    line(product_id=p_alt.id, product_code_snapshot=p_alt.product_code, description_snapshot="Alt basin",
         unit_price=Decimal("170.00"), quantity=Decimal("10"), uom="UNIT",
         line_total=Decimal("0"), is_rate_only=True, sort_order=1)
    line(product_set_id=pset.id, product_code_snapshot=pset.set_code, description_snapshot="WC set",
         unit_price=Decimal("950.00"), quantity=Decimal("2"), uom="SET",
         line_total=Decimal("1900.00"), sort_order=2,
         set_parts_snapshot=[
             {"product_id": p_wc.id, "product_code": p_wc.product_code, "description": "WC",
              "quantity": "1", "is_driver": True, "uom": "UNIT"},
             {"product_id": p_av.id, "product_code": p_av.product_code, "description": "AV",
              "quantity": "2", "is_driver": False, "uom": "UNIT"},
         ])
    db.flush()

    issue = add_issue(db, company_id, document, scope, version, issue_no=1, accepted=accepted)
    return SoWorld(
        document=document, project=project, customer=customer, agent=agent, issue=issue,
        scope=scope, version=version, p1=p1, p_alt=p_alt, p_wc=p_wc, p_av=p_av, pset=pset,
        company_id=company_id, owner=owner,
    )


def add_issue(db, company_id, document, scope, version, *, issue_no: int, accepted: bool):
    issue = ProjectQuotationIssue(
        id=_uid(), company_id=company_id, document_id=document.id, issue_no=issue_no,
        our_ref_text=f"{document.document_no} (R{issue_no})", revision_label=f"R{issue_no}",
        grand_total=Decimal("3700.00"),
        accepted_at=datetime(2026, 10, 20, 9, 0) if accepted else None,
    )
    db.add(issue)
    db.flush()
    db.add(
        ProjectQuotationIssueScope(
            id=_uid(), company_id=company_id, issue_id=issue.id, quotation_id=scope.id,
            version_id=version.id, sort_order=0, scope_total=Decimal("3700.00"),
        )
    )
    db.flush()
    return issue


# --------------------------------------------------------------------------- route client


def make_client(db, user_id: str, permissions):
    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.dependencies import get_current_user, get_current_user_or_api_key
    from app.main import app
    from app.services.company_scope_resolver import apply_company_scope
    from app.services.user_service import UserPermissionService

    actor = {"id": user_id, "email": f"{user_id}@zzt.test", "role": "user"}
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: dict(actor)
    app.dependency_overrides[get_current_user_or_api_key] = lambda: dict(actor)
    app.dependency_overrides[apply_company_scope] = lambda: None

    originals = (
        UserPermissionService.check_user_has_permission,
        UserPermissionService.get_user_permission_slugs,
    )
    granted = list(permissions)
    UserPermissionService.check_user_has_permission = lambda self, uid, slug: slug in granted
    UserPermissionService.get_user_permission_slugs = lambda self, uid: list(granted)
    return TestClient(app), originals


def restore_client(originals) -> None:
    from app.main import app
    from app.services.user_service import UserPermissionService

    UserPermissionService.check_user_has_permission = originals[0]
    UserPermissionService.get_user_permission_slugs = originals[1]
    app.dependency_overrides.clear()


def api_fixture(which: str, permissions, *, switch: bool = True, **world_kw: Any):
    """Generator behind the per-file `api` fixtures.

    Yields `(client, db, world)`. `which` is "so" or "qt". The fake SS must be requested by the
    test (or fixture) alongside, so the transport is patched before any call.
    """
    from app.models.base import company_scope

    with blank_session() as db:
        company_id = _sorento(db)
        project_seed_service.run(db, company_id=company_id)
        owner = _user(db, f"{MARKER} CS")
        world = (
            build_so_world(db, company_id, owner, **world_kw)
            if which == "so"
            else build_qt_world(db, company_id, owner, **world_kw)
        )
        seed_foundryx_connection(db, base_url=SS_BASE_URL, api_key=SS_API_KEY)
        set_switch(db, switch)
        db.commit()
        client, originals = make_client(db, owner, permissions)
        try:
            with company_scope(db, frozenset({company_id})):
                yield client, db, world
        finally:
            restore_client(originals)


def myt_today_candidates() -> set[str]:
    """Today's date as ISO, in MYT and in UTC: the test must not flake across midnight."""
    from datetime import timedelta, timezone

    now = datetime.now(timezone.utc)
    return {now.date().isoformat(), (now + timedelta(hours=8)).date().isoformat()}
