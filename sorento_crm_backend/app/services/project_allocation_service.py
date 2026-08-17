"""Allocation: where each sales order line's stock comes from (P9, AC-H1 to AC-H5).

This service reads live rows and writes decisions. The ranking itself is not here: it lives
in ``project_allocation_engine`` as a pure function, so the rule can be tested without a
database and so nobody is ever tempted to cache its output. Candidates are recomputed on
every request. A stored snapshot of another project's on-hand goes stale the moment they
ship, and acting on a stale figure is the failure this slice exists to prevent.

Three rules are enforced HERE rather than in the UI, because a rule that only exists on a
screen is not a rule:

* **A source cannot exceed what the location actually holds free.** Checked against the
  same live figures the screen was showing, at the moment of the write.
* **A cross project pull is a REQUEST, not a decision (AC-H4).** Choosing another project's
  stock writes an UNCONFIRMED allocation plus a claim in ``requested``. Until that
  project's CS accepts, the line has no stock location, reads as ``pending_claim``, and
  grants no hold that would make the pile look spoken for on a third project's screen.
  Nothing moves on silence.
* **A refusal carries a reason.** "No" without one sends the asker back to a phone call,
  which is what the claim exists to replace.

BRW-BB is identified by warehouse CODE, resolved at runtime from
``settings.project_allocation_brw_warehouse_code``. It is a real ``warehouses`` row (the
AutoCount location code) and NOT a hardcoded string in the ranking: all four sites run a
``-BB`` bin (BRW-BB, DC1-BB, MWH-BB, WH3-BB) and only the Bukit Raja one is the master, so
the site prefix is load bearing. A database with no such row simply has no ``brw``
candidate rather than a blank screen.
"""
from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.config import settings
from app.models.inventory import Stock, Warehouse
from app.models.product import Product
from app.models.project_so import (
    ALLOC_SOURCE_ORDER,
    CLAIM_REFUSED,
    CLAIM_REQUESTED,
    DECISION_ACTIVE,
    AllocationClaim,
    ProjectSalesOrder,
    ProjectSalesOrderLine,
    SOLineAllocation,
    SOSupplyDecision,
)
from app.models.projects import Project, ProjectCollaborator
from app.models.user import User
from app.services.error_handler import AppException
from app.services.project_allocation_engine import (
    LineNeed,
    ProjectHold,
    RankedSources,
    StockRow,
    rank_sources,
)

logger = logging.getLogger(__name__)

_ZERO = Decimal("0")

# Line states, in the order the checks run.
STATE_UNALLOCATED = "unallocated"
STATE_PENDING_CLAIM = "pending_claim"
STATE_REFUSED = "refused"
STATE_PARTIAL = "partial"
STATE_CONFIRMED = "confirmed"

MANAGE_PERMISSION = "projects.projects.manage"


def _dec(value: Any, default: Decimal = _ZERO) -> Decimal:
    if value is None:
        return default
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return default


def _qty(value: Any) -> Decimal:
    """A quantity as a person writes it: no trailing zeros, no scientific notation.

    ``Numeric(15, 4)`` gives back ``Decimal("135.0000")``, which serialises as
    ``"135.0000"`` and reads on screen like a precision claim nobody made.
    """
    return Decimal(format(_dec(value).normalize(), "f"))


class ProjectAllocationService:
    """Ranked sources, the confirmed decision, and the claims between projects."""

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------ lookups

    def get_line(self, line_id: str) -> ProjectSalesOrderLine:
        line = (
            self.db.query(ProjectSalesOrderLine)
            .filter(ProjectSalesOrderLine.id == line_id)
            .first()
        )
        if line is None:
            raise AppException(
                status_code=404,
                message="Sales order line not found.",
                code="so_line_not_found",
            )
        return line

    def get_order(self, pso_id: str) -> ProjectSalesOrder:
        order = (
            self.db.query(ProjectSalesOrder).filter(ProjectSalesOrder.id == pso_id).first()
        )
        if order is None:
            raise AppException(
                status_code=404, message="Sales order not found.", code="so_not_found"
            )
        return order

    def get_claim(self, claim_id: str) -> AllocationClaim:
        claim = (
            self.db.query(AllocationClaim).filter(AllocationClaim.id == claim_id).first()
        )
        if claim is None:
            raise AppException(
                status_code=404,
                message="That stock claim no longer exists.",
                code="allocation_claim_not_found",
            )
        return claim

    def project_of_line(self, line: ProjectSalesOrderLine) -> Project:
        order = self.get_order(line.project_sales_order_id)
        project = self.db.query(Project).filter(Project.id == order.project_id).first()
        if project is None:
            raise AppException(
                status_code=404, message="Project not found.", code="project_not_found"
            )
        return project

    def _project(self, project_id: Optional[str]) -> Optional[Project]:
        if not project_id:
            return None
        return self.db.query(Project).filter(Project.id == project_id).first()

    def _warehouse(self, warehouse_id: Optional[str]) -> Optional[Warehouse]:
        if not warehouse_id:
            return None
        return self.db.query(Warehouse).filter(Warehouse.id == warehouse_id).first()

    def _user_name(self, user_id: Optional[str]) -> Optional[str]:
        if not user_id:
            return None
        user = self.db.query(User).filter(User.id == user_id).first()
        return user.name if user else None

    def _brw_warehouse(self) -> Optional[Warehouse]:
        code = (getattr(settings, "project_allocation_brw_warehouse_code", "") or "").strip()
        if not code:
            return None
        return (
            self.db.query(Warehouse)
            .filter(Warehouse.warehouse_code == code)
            .first()
        )

    # -------------------------------------------------------------- live figures

    def _stock_rows(self, product_id: Optional[str]) -> List[StockRow]:
        """Every SELLABLE location holding this product.

        ``is_active`` is the filter the data already carries: the defect, dispatch, rework
        and showroom bins are inactive rows, and offering them as a source would propose
        shipping a customer stock that is in the reject pile.
        """
        if not product_id:
            return []
        rows = (
            self.db.query(Stock, Warehouse)
            .join(Warehouse, Warehouse.id == Stock.warehouse_id)
            .filter(Stock.product_id == product_id, Warehouse.is_active.is_(True))
            .all()
        )
        return [
            StockRow(
                warehouse_id=warehouse.id,
                warehouse_code=warehouse.warehouse_code,
                warehouse_name=warehouse.warehouse_name,
                on_hand=_dec(stock.quantity_on_hand),
                reserved=_dec(stock.quantity_reserved),
            )
            for stock, warehouse in rows
        ]

    def _holds(
        self, product_id: Optional[str], *, exclude_line_id: Optional[str]
    ) -> List[ProjectHold]:
        """Stock at a location already CONFIRMED to a project, with that project's CS.

        Confirmed only. An allocation waiting on a claim is a request, and a request holds
        nothing: counting it would let one project make a pile look spoken for simply by
        asking, which is the opposite of "nothing moves on silence".

        The line being sourced is excluded so its own previous decision does not compete
        with the override that is replacing it.

        After a claim is accepted BOTH projects hold at that location until the stock
        physically moves, so the holds can total more than the on-hand. That is deliberate:
        the engine floors availability at zero, so the effect is that nobody else is
        offered the pile, which is the safe direction. The movement itself is SCM's, not
        this slice's.

        A SUPERSEDED revision holds nothing (Stage 1C). Its rows stay for audit, so the
        filter is on the decision's state, and a row belonging to no decision at all -
        every allocation written before Stage 1C - still holds, because nothing has
        replaced it. `project_supply_service` reads free stock by the identical rule, and
        the two must agree or the candidate list and the supply sheet describe different
        piles.
        """
        if not product_id:
            return []
        query = (
            self.db.query(
                SOLineAllocation.warehouse_id,
                Project.id,
                Project.project_code,
                Project.title,
                Project.owner_user_id,
                SOLineAllocation.qty,
            )
            .join(
                ProjectSalesOrderLine,
                ProjectSalesOrderLine.id == SOLineAllocation.so_line_id,
            )
            .join(
                ProjectSalesOrder,
                ProjectSalesOrder.id == ProjectSalesOrderLine.project_sales_order_id,
            )
            .join(Project, Project.id == ProjectSalesOrder.project_id)
            .outerjoin(
                SOSupplyDecision, SOSupplyDecision.id == SOLineAllocation.decision_id
            )
            .filter(
                ProjectSalesOrderLine.product_id == product_id,
                SOLineAllocation.confirmed_at.isnot(None),
                SOLineAllocation.warehouse_id.isnot(None),
                SOLineAllocation.source_type != ALLOC_SOURCE_ORDER,
                or_(
                    SOLineAllocation.decision_id.is_(None),
                    SOSupplyDecision.state == DECISION_ACTIVE,
                ),
            )
        )
        if exclude_line_id:
            query = query.filter(SOLineAllocation.so_line_id != exclude_line_id)

        totals: Dict[Tuple[str, str], Dict[str, Any]] = {}
        for warehouse_id, project_id, code, title, owner_user_id, qty in query.all():
            key = (warehouse_id, project_id)
            entry = totals.setdefault(
                key,
                {
                    "code": code,
                    "title": title,
                    "owner": owner_user_id,
                    "qty": _ZERO,
                },
            )
            entry["qty"] += _dec(qty)

        names = self._names_for({entry["owner"] for entry in totals.values() if entry["owner"]})
        return [
            ProjectHold(
                warehouse_id=warehouse_id,
                project_id=project_id,
                project_code=entry["code"],
                project_title=entry["title"],
                cs_user_id=entry["owner"],
                cs_name=names.get(entry["owner"]),
                qty=entry["qty"],
            )
            for (warehouse_id, project_id), entry in totals.items()
        ]

    def _names_for(self, user_ids: Iterable[Optional[str]]) -> Dict[str, str]:
        ids = {uid for uid in user_ids if uid}
        if not ids:
            return {}
        rows = self.db.query(User.id, User.name).filter(User.id.in_(ids)).all()
        return {uid: name for uid, name in rows}

    def rank(self, line: ProjectSalesOrderLine, project: Project) -> RankedSources:
        """The live ranking for one line. Never cached, never stored."""
        brw = self._brw_warehouse()
        return rank_sources(
            LineNeed(
                line_id=line.id,
                product_id=line.product_id or "",
                project_id=project.id,
                qty=_dec(line.qty),
            ),
            stock_rows=self._stock_rows(line.product_id),
            holds=self._holds(line.product_id, exclude_line_id=line.id),
            brw_warehouse_id=brw.id if brw else None,
        )

    # ------------------------------------------------------------- serialisation

    def serialize_candidates(self, line: ProjectSalesOrderLine) -> Dict[str, Any]:
        project = self.project_of_line(line)
        ranked = self.rank(line, project)
        brw = self._brw_warehouse()
        codes = self._warehouse_codes(
            {candidate.warehouse_id for candidate in ranked.candidates if candidate.warehouse_id}
        )
        open_claims = self._open_claims_by_warehouse(line.id)

        return {
            "line_id": line.id,
            "line_no": line.line_no,
            "product_code": self._product_code(line.product_id),
            "description": line.description,
            "qty": _qty(line.qty),
            "uom": line.uom,
            "delivery_date": line.delivery_date,
            "project_code": project.project_code,
            "brw_warehouse_code": brw.warehouse_code if brw else None,
            "candidates": [
                {
                    "rank": candidate.rank,
                    "source_type": candidate.source_type,
                    "warehouse_id": candidate.warehouse_id,
                    "warehouse_code": candidate.warehouse_code,
                    "warehouse_name": candidate.warehouse_name,
                    "on_hand": _qty(candidate.on_hand),
                    "reserved": _qty(candidate.reserved),
                    "held_for_this_project": _qty(candidate.held_for_this_project),
                    "held_for_other_projects": _qty(candidate.held_for_other_projects),
                    "committed": _qty(candidate.committed),
                    "available": _qty(candidate.available),
                    "allocatable": _qty(candidate.allocatable),
                    "claimable": _qty(candidate.claimable),
                    "requires_claim": candidate.requires_claim,
                    "is_project_location": candidate.is_project_location,
                    "holders": [
                        {
                            "project_id": holder.project_id,
                            "project_code": holder.project_code,
                            "project_title": holder.project_title,
                            "cs_user_id": holder.cs_user_id,
                            "cs_name": holder.cs_name,
                            "qty": _qty(holder.qty),
                        }
                        for holder in candidate.holders
                    ],
                    "open_claim_id": open_claims.get(candidate.warehouse_id or "", {}).get("id"),
                    "open_claim_state": open_claims.get(candidate.warehouse_id or "", {}).get(
                        "state"
                    ),
                }
                for candidate in ranked.candidates
            ],
            "plan": [
                {
                    "warehouse_id": warehouse_id,
                    "warehouse_code": codes.get(warehouse_id),
                    "qty": _qty(qty),
                }
                for warehouse_id, qty in ranked.plan
            ],
            "shortfall": _qty(ranked.shortfall),
            "covered": ranked.covered,
        }

    def _warehouse_codes(self, warehouse_ids: Set[str]) -> Dict[str, str]:
        if not warehouse_ids:
            return {}
        rows = (
            self.db.query(Warehouse.id, Warehouse.warehouse_code)
            .filter(Warehouse.id.in_(warehouse_ids))
            .all()
        )
        return {row_id: code for row_id, code in rows}

    def _product_code(self, product_id: Optional[str]) -> Optional[str]:
        if not product_id:
            return None
        row = (
            self.db.query(Product.product_code).filter(Product.id == product_id).first()
        )
        return row[0] if row else None

    def _open_claims_by_warehouse(self, line_id: str) -> Dict[str, Dict[str, Any]]:
        rows = (
            self.db.query(AllocationClaim)
            .filter(
                AllocationClaim.so_line_id == line_id,
                AllocationClaim.state == CLAIM_REQUESTED,
            )
            .all()
        )
        return {
            claim.warehouse_id: {"id": claim.id, "state": claim.state}
            for claim in rows
            if claim.warehouse_id
        }

    def allocations_of(self, line_id: str) -> List[SOLineAllocation]:
        return (
            self.db.query(SOLineAllocation)
            .filter(SOLineAllocation.so_line_id == line_id)
            .order_by(SOLineAllocation.created_at.asc())
            .all()
        )

    def serialize_line(self, line: ProjectSalesOrderLine) -> Dict[str, Any]:
        rows = self.allocations_of(line.id)
        claims = {
            claim.id: claim
            for claim in self.db.query(AllocationClaim)
            .filter(AllocationClaim.so_line_id == line.id)
            .all()
        }
        projects = {
            project.id: project
            for project in self.db.query(Project)
            .filter(
                Project.id.in_({row.source_project_id for row in rows if row.source_project_id})
            )
            .all()
        } if any(row.source_project_id for row in rows) else {}
        warehouses = {
            warehouse.id: warehouse
            for warehouse in self.db.query(Warehouse)
            .filter(Warehouse.id.in_({row.warehouse_id for row in rows if row.warehouse_id}))
            .all()
        } if any(row.warehouse_id for row in rows) else {}
        names = self._names_for(
            [row.confirmed_by for row in rows]
            + [project.owner_user_id for project in projects.values()]
        )

        sources: List[Dict[str, Any]] = []
        for row in rows:
            claim = claims.get(row.claim_id) if row.claim_id else None
            warehouse = warehouses.get(row.warehouse_id) if row.warehouse_id else None
            project = projects.get(row.source_project_id) if row.source_project_id else None
            sources.append(
                {
                    "id": row.id,
                    "source_type": row.source_type,
                    "warehouse_id": row.warehouse_id,
                    "warehouse_code": warehouse.warehouse_code if warehouse else None,
                    "warehouse_name": warehouse.warehouse_name if warehouse else None,
                    "source_project_id": row.source_project_id,
                    "source_project_code": project.project_code if project else None,
                    "source_project_cs_name": (
                        names.get(project.owner_user_id) if project else None
                    ),
                    "qty": _qty(row.qty),
                    "confirmed": row.confirmed_at is not None,
                    "confirmed_by_name": names.get(row.confirmed_by) if row.confirmed_by else None,
                    "confirmed_at": row.confirmed_at,
                    "claim_id": row.claim_id,
                    "claim_state": claim.state if claim else None,
                    "claim_reason": claim.reason if claim else None,
                }
            )

        allocated = sum((_dec(row.qty) for row in rows if row.confirmed_at is not None), _ZERO)
        needed = _dec(line.qty)
        return {
            "line_id": line.id,
            "line_no": line.line_no,
            "product_id": line.product_id,
            "product_code": self._product_code(line.product_id),
            "description": line.description,
            "qty": _qty(needed),
            "uom": line.uom,
            "delivery_date": line.delivery_date,
            "state": self._state(rows, claims, allocated, needed),
            "stock_location": line.stock_location,
            "allocated_qty": _qty(allocated),
            "outstanding_qty": _qty(needed - allocated if needed > allocated else _ZERO),
            "sources": sources,
        }

    def _state(
        self,
        rows: Sequence[SOLineAllocation],
        claims: Dict[str, AllocationClaim],
        allocated: Decimal,
        needed: Decimal,
    ) -> str:
        if not rows:
            return STATE_UNALLOCATED
        open_claim = any(
            row.claim_id
            and row.confirmed_at is None
            and claims.get(row.claim_id)
            and claims[row.claim_id].state == CLAIM_REQUESTED
            for row in rows
        )
        if open_claim:
            return STATE_PENDING_CLAIM
        refused = any(
            row.claim_id
            and row.confirmed_at is None
            and claims.get(row.claim_id)
            and claims[row.claim_id].state == CLAIM_REFUSED
            for row in rows
        )
        if refused:
            return STATE_REFUSED
        if allocated >= needed and allocated > _ZERO:
            return STATE_CONFIRMED
        if allocated <= _ZERO:
            return STATE_UNALLOCATED
        return STATE_PARTIAL

    def list_for_order(self, pso_id: str) -> List[Dict[str, Any]]:
        lines = (
            self.db.query(ProjectSalesOrderLine)
            .filter(ProjectSalesOrderLine.project_sales_order_id == pso_id)
            .order_by(ProjectSalesOrderLine.line_no.asc())
            .all()
        )
        return [self.serialize_line(line) for line in lines]

    # ------------------------------------------------------------------ worklist

    def editable_project_ids(self, user_id: str, permissions: Set[str]) -> Optional[Set[str]]:
        """Projects this user may act for. ``None`` means every project (manager)."""
        if MANAGE_PERMISSION in (permissions or set()):
            return None
        owned = {
            row_id
            for (row_id,) in self.db.query(Project.id)
            .filter(Project.owner_user_id == user_id)
            .all()
        }
        joined = {
            row_id
            for (row_id,) in self.db.query(ProjectCollaborator.project_id)
            .filter(ProjectCollaborator.user_id == user_id)
            .all()
        }
        return owned | joined

    def can_act_for_project(
        self, project: Project, user_id: str, permissions: Set[str]
    ) -> bool:
        allowed = self.editable_project_ids(user_id, permissions)
        return allowed is None or project.id in allowed

    def list_claims(
        self,
        *,
        user_id: str,
        permissions: Set[str],
        direction: str = "incoming",
        state: Optional[Sequence[str]] = None,
        page: int = 1,
        limit: int = 50,
    ) -> Tuple[List[Dict[str, Any]], int]:
        allowed = self.editable_project_ids(user_id, permissions)
        query = self.db.query(AllocationClaim)

        if direction == "outgoing":
            if allowed is not None:
                if not allowed:
                    return [], 0
                query = query.filter(AllocationClaim.from_project_id.in_(allowed))
        elif direction == "all":
            if allowed is not None:
                if not allowed:
                    return [], 0
                query = query.filter(
                    or_(
                        AllocationClaim.from_project_id.in_(allowed),
                        AllocationClaim.to_project_id.in_(allowed),
                    )
                )
        else:
            if allowed is not None:
                if not allowed:
                    return [], 0
                query = query.filter(AllocationClaim.to_project_id.in_(allowed))

        states = [value for value in (state or []) if value]
        if states:
            query = query.filter(AllocationClaim.state.in_(states))

        total = query.count()
        rows = (
            query.order_by(AllocationClaim.created_at.desc())
            .offset(max(page - 1, 0) * limit)
            .limit(limit)
            .all()
        )
        return [
            self.serialize_claim(
                row, viewer_id=user_id, viewer_permissions=permissions
            )
            for row in rows
        ], total

    def serialize_claim(
        self,
        claim: AllocationClaim,
        *,
        viewer_id: Optional[str] = None,
        viewer_permissions: Optional[Set[str]] = None,
    ) -> Dict[str, Any]:
        """One claim as the caller may act on it.

        ``can_answer`` is always False now (see below): there is no accept or refuse to
        gate, because a Borrow is confirmed by the CS actor composing the sales order and
        the claim row is written in its terminal state.
        """
        source = self._project(claim.from_project_id)
        holder = self._project(claim.to_project_id)
        warehouse = self._warehouse(claim.warehouse_id)
        product = (
            self.db.query(Product).filter(Product.id == claim.product_id).first()
            if claim.product_id
            else None
        )
        line = (
            self.db.query(ProjectSalesOrderLine)
            .filter(ProjectSalesOrderLine.id == claim.so_line_id)
            .first()
            if claim.so_line_id
            else None
        )
        order = self.get_order(line.project_sales_order_id) if line else None
        names = self._names_for(
            [
                claim.requested_by,
                claim.decided_by,
                source.owner_user_id if source else None,
                holder.owner_user_id if holder else None,
            ]
        )
        # Nothing is answerable any more: Stage 1C writes a cross-project Borrow claim
        # straight to `accepted` inside the atomic confirmation, by the CS actor who
        # confirms the order (AC-B10), and the accept / refuse routes are gone. The field
        # stays while the frontend still reads it, and it stays FALSE rather than being
        # computed, because offering a button no route serves is the thing it was added
        # to stop.
        can_answer = False

        return {
            "id": claim.id,
            "state": claim.state,
            "can_answer": can_answer,
            "qty": _qty(claim.qty),
            "reason": claim.reason,
            "from_project_id": claim.from_project_id,
            "from_project_code": source.project_code if source else "",
            "from_project_title": source.title if source else None,
            "from_project_cs_name": names.get(source.owner_user_id) if source else None,
            "to_project_id": claim.to_project_id,
            "to_project_code": holder.project_code if holder else "",
            "to_project_title": holder.title if holder else None,
            "to_project_cs_name": names.get(holder.owner_user_id) if holder else None,
            "product_id": claim.product_id,
            "product_code": product.product_code if product else None,
            "product_name": product.product_name if product else None,
            "warehouse_id": claim.warehouse_id,
            "warehouse_code": warehouse.warehouse_code if warehouse else None,
            "so_line_id": claim.so_line_id,
            "sales_order_id": order.id if order else None,
            "sales_order_ref": (
                (order.autocount_doc_no or order.provisional_ref) if order else None
            ),
            "line_no": line.line_no if line else None,
            "delivery_date": line.delivery_date if line else None,
            "requested_by_name": names.get(claim.requested_by),
            "decided_by_name": names.get(claim.decided_by),
            "decided_at": claim.decided_at,
            "created_at": claim.created_at,
        }
