"""Shared seeds for the TOWN-PROJECT-CITY Phase 2 red tests (not a test module).

Contract: `documentation/plans/dashboard/PLAN-town-project-city-11nov.md`, "Phase 2 contract".
Every row is seeded by the caller (CI's database is empty); codes carry the `ZZT` prefix.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

from app.main import app  # noqa: F401  (import order: resolves the guards cycle)
from app.models.order import Order
from app.models.projects import Project, ProjectParty, ProjectPartyLink, ProjectSalesProfile
from app.models.status import Status
from app.services import project_seed_service
from app.services.company_scope import DEFAULT_COMPANY_ID
from tests._pg_fixture import unique_code
from tests._sales_unified_seed import so
from tests.town._town_seed import D

MY_STATES = (
    "Johor", "Kedah", "Kelantan", "Melaka", "Negeri Sembilan", "Pahang", "Perak", "Perlis",
    "Pulau Pinang", "Sabah", "Sarawak", "Selangor", "Terengganu", "Kuala Lumpur", "Labuan", "Putrajaya",
)


def funnel(db) -> dict:
    """status key -> status id for the default project funnel, seeded here (CI's db is empty)."""
    project_seed_service.seed_default_funnel(db)
    rows = db.query(Status).filter(Status.entity_type == "project", Status.scope_id.is_(None)).all()
    return {row.key: row.id for row in rows}


def project(
    db,
    funnel_ids: dict,
    *,
    code: Optional[str] = None,
    outcome: str = "open",
    stage: Optional[str] = "quoted",
    state: Optional[str] = None,
    value: Optional[str] = None,
    launch: Optional[date] = None,
    delivery_from: Optional[date] = None,
    delivery_to: Optional[date] = None,
    critical: bool = False,
    approval: Optional[str] = None,
    name: Optional[str] = None,
    title: Optional[str] = None,
    company_id: str = DEFAULT_COMPANY_ID,
) -> Project:
    unique_title = title or f"ZZT Project {uuid.uuid4().hex[:10]}"
    row = Project(
        id=str(uuid.uuid4()),
        company_id=company_id,
        project_code=code if code is not None else unique_code("ZZTP"),
        title=unique_title,
        normalised_title=unique_title.casefold(),
        name=name,
        status_id=funnel_ids[stage] if stage else None,
        outcome=outcome,
        is_critical=critical,
        approval_state=approval,
    )
    db.add(row)
    db.flush()
    db.add(ProjectSalesProfile(
        project_id=row.id,
        state=state,
        estimated_sales_value=D(value) if value is not None else None,
        launch_date=launch,
        expected_delivery_from=delivery_from,
        expected_delivery_to=delivery_to,
    ))
    db.flush()
    return row


def link_trading_house(db, proj: Project, customer, *, with_customer: bool = True,
                       role: str = "trading_house") -> ProjectParty:
    """A party (optionally tied to a customer) linked to `proj` in `role`."""
    party = ProjectParty(
        id=str(uuid.uuid4()), company_id=proj.company_id, party_type="trading_house",
        name=f"ZZT Party {uuid.uuid4().hex[:8]}", customer_id=customer.id if with_customer else None,
    )
    db.add(party)
    db.flush()
    db.add(ProjectPartyLink(project_id=proj.id, role=role, party_id=party.id))
    db.flush()
    return party


def delivery_order(
    db, customer, address: Optional[str], order_date: date, *, cancelled: bool = False,
    deleted: bool = False, company_id: str = DEFAULT_COMPANY_ID,
) -> Order:
    row = Order(
        id=str(uuid.uuid4()), order_number=unique_code("DO"), company_id=company_id,
        customer_id=customer.id, order_date=order_date, deliver_address=address,
        is_cancelled=cancelled, deleted_at=datetime(2026, 11, 1) if deleted else None,
    )
    db.add(row)
    db.flush()
    return row


def addr(postcode: str, town: str = "Shah Alam", state: str = "Selangor") -> str:
    return f"No. 7, Jalan ZZT Satu, {postcode} {town}, {state}"


def due_order(db, customer, required: date, demand_class: str = "retail"):
    """A sales order still owing goods, due on `required`."""
    header, (ln,) = so(db, customer=customer, demand_class=demand_class)
    ln.qty_ordered, ln.qty_delivered, ln.line_status, ln.required_date = D(5), D(0), "open", required
    db.flush()
    return header


def shop_for(snap: dict, customer) -> dict:
    return next(s for s in snap["shops"] if s["key"] == str(customer.id))


def site_dict(i: int, **over) -> dict:
    base = {
        "key": str(uuid.uuid4()), "name": f"ZZT Tower {i}", "code": f"ZZT-P{i:03d}",
        "stage": ["identified", "registered", "specified", "quoted", "tendering", "po_received"][i % 6],
        "final_negotiation": i % 2 == 0, "state": ["Johor", "Selangor", "Sabah", None][i % 4],
        "launch_date": f"2026-0{1 + i % 9}-01", "delivery_date": f"2028-0{1 + i % 9}-01",
        "estimated_value": f"{(100 - i) * 1000}.00",
    }
    base.update(over)
    return base


def full_with_projects(n_sites: int = 12, n_houses: int = 3) -> dict:
    from tests.town._town_seed import fake_full

    full = fake_full()
    full["today"]["split"] = {
        "dealer": {"amount": "400111.10", "invoice_count": 200},
        "project": {"amount": "100222.20", "invoice_count": 100},
        "other": {"amount": "12012.30", "invoice_count": 21},
    }
    full["projects"] = {
        "open_count": n_sites + 3, "more": 3, "dormant": 2,
        "sites": [site_dict(i) for i in range(n_sites)],
    }
    full["trading_houses"] = {
        "more": 1,
        "rows": [
            {"key": str(uuid.uuid4()), "name": f"ZZT Trading House {i}", "state": "Selangor",
             "open_projects": 5 - i, "today_docs": i}
            for i in range(n_houses)
        ],
    }
    return full


__all__ = [n for n in dir() if not n.startswith("_")] + ["timedelta", "Decimal"]
