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
    ALLOC_SOURCE_BRW,
    ALLOC_SOURCE_ORDER,
    ALLOC_SOURCE_OTHER_PROJECT,
    ALLOC_SOURCE_OWN,
    CLAIM_ACCEPTED,
    CLAIM_REFUSED,
    CLAIM_REQUESTED,
    AllocationClaim,
    ProjectSalesOrder,
    ProjectSalesOrderLine,
    SOLineAllocation,
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
            .filter(
                ProjectSalesOrderLine.product_id == product_id,
                SOLineAllocation.confirmed_at.isnot(None),
                SOLineAllocation.warehouse_id.isnot(None),
                SOLineAllocation.source_type != ALLOC_SOURCE_ORDER,
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

    # ------------------------------------------------------------------ decision

    def confirm(
        self,
        line: ProjectSalesOrderLine,
        project: Project,
        sources: Sequence[Dict[str, Any]],
        *,
        actor_user_id: str,
    ) -> Dict[str, Any]:
        """Stamp the sources for one line, replacing whatever stood before (AC-H3)."""
        needed = _dec(line.qty)
        total = sum((_dec(source.get("qty")) for source in sources), _ZERO)
        if total > needed:
            raise AppException(
                status_code=422,
                message=(
                    f"The sources add up to {format(_qty(total), 'f')} but the line needs "
                    f"{format(_qty(needed), 'f')}. Reduce one of them."
                ),
                code="allocation_over_line",
            )

        ranked = self.rank(line, project)
        by_warehouse = {
            candidate.warehouse_id: candidate
            for candidate in ranked.candidates
            if candidate.warehouse_id
        }
        seen: Set[str] = set()
        accepted_claims = self._accepted_claims(line.id)

        prepared: List[Dict[str, Any]] = []
        for source in sources:
            source_type = source.get("source_type")
            warehouse_id = source.get("warehouse_id")
            qty = _dec(source.get("qty"))

            if source_type == ALLOC_SOURCE_ORDER:
                if warehouse_id:
                    raise AppException(
                        status_code=422,
                        message="Ordering carries no location. Leave the location empty.",
                        code="allocation_order_has_warehouse",
                    )
                prepared.append(
                    {
                        "source_type": ALLOC_SOURCE_ORDER,
                        "warehouse_id": None,
                        "source_project_id": None,
                        "qty": qty,
                        "claim_id": None,
                        "confirmed": True,
                    }
                )
                continue

            if not warehouse_id:
                raise AppException(
                    status_code=422,
                    message="Name the location this stock comes from.",
                    code="allocation_warehouse_required",
                )
            if warehouse_id in seen:
                raise AppException(
                    status_code=422,
                    message="The same location is named twice. Combine them into one source.",
                    code="allocation_duplicate_warehouse",
                )
            seen.add(warehouse_id)

            candidate = by_warehouse.get(warehouse_id)
            if candidate is None:
                warehouse = self._warehouse(warehouse_id)
                raise AppException(
                    status_code=409,
                    message=(
                        f"{warehouse.warehouse_code if warehouse else 'That location'} holds "
                        "none of this product. Pick another source."
                    ),
                    code="allocation_source_empty",
                )

            if source_type == ALLOC_SOURCE_OTHER_PROJECT:
                claim = self._matching_accepted_claim(
                    accepted_claims, warehouse_id, source.get("source_project_id"), qty
                )
                if claim is None:
                    raise AppException(
                        status_code=409,
                        message=(
                            "That stock is held for another project. Raise a claim and wait "
                            "for their CS to accept it before sourcing the line from there."
                        ),
                        code="allocation_claim_required",
                    )
                prepared.append(
                    {
                        "source_type": ALLOC_SOURCE_OTHER_PROJECT,
                        "warehouse_id": warehouse_id,
                        "source_project_id": claim.to_project_id,
                        "qty": qty,
                        "claim_id": claim.id,
                        "confirmed": True,
                    }
                )
                continue

            if qty > candidate.available:
                raise AppException(
                    status_code=409,
                    message=(
                        f"{candidate.warehouse_code} has {format(_qty(candidate.available), 'f')} "
                        f"free, and {format(_qty(qty), 'f')} was asked for. Split the line or "
                        "pick another source."
                    ),
                    code="allocation_over_available",
                )
            expected = (
                ALLOC_SOURCE_BRW
                if candidate.source_type == ALLOC_SOURCE_BRW
                else ALLOC_SOURCE_OWN
            )
            if source_type != expected:
                raise AppException(
                    status_code=422,
                    message=(
                        f"{candidate.warehouse_code} is a '{expected}' source, not "
                        f"'{source_type}'. Reload the ranked sources and try again."
                    ),
                    code="allocation_source_type_mismatch",
                )
            prepared.append(
                {
                    "source_type": expected,
                    "warehouse_id": warehouse_id,
                    "source_project_id": None,
                    "qty": qty,
                    "claim_id": None,
                    "confirmed": True,
                }
            )

        self._replace_allocations(line, prepared, actor_user_id=actor_user_id)
        self._restamp_stock_location(line)
        self.db.flush()
        return self.serialize_line(line)

    def _accepted_claims(self, line_id: str) -> List[AllocationClaim]:
        return (
            self.db.query(AllocationClaim)
            .filter(
                AllocationClaim.so_line_id == line_id,
                AllocationClaim.state == CLAIM_ACCEPTED,
            )
            .all()
        )

    def _matching_accepted_claim(
        self,
        claims: Sequence[AllocationClaim],
        warehouse_id: str,
        source_project_id: Optional[str],
        qty: Decimal,
    ) -> Optional[AllocationClaim]:
        for claim in claims:
            if claim.warehouse_id != warehouse_id:
                continue
            if source_project_id and claim.to_project_id != source_project_id:
                continue
            if _dec(claim.qty) < qty:
                continue
            return claim
        return None

    def _replace_allocations(
        self,
        line: ProjectSalesOrderLine,
        prepared: Sequence[Dict[str, Any]],
        *,
        actor_user_id: str,
        keep_claims: bool = False,
    ) -> None:
        """The decision is a whole answer, so it is written whole.

        Open claims are withdrawn along with the allocation they backed: leaving a request
        alive after the asker has sourced the line elsewhere would put a decision in front
        of somebody that no longer matters.
        """
        existing = self.allocations_of(line.id)
        for row in existing:
            self.db.delete(row)
        if not keep_claims:
            self._withdraw_open_claims(line.id)
        self.db.flush()

        now = datetime.utcnow()
        for source in prepared:
            self.db.add(
                SOLineAllocation(
                    company_id=line.company_id,
                    so_line_id=line.id,
                    source_type=source["source_type"],
                    warehouse_id=source.get("warehouse_id"),
                    source_project_id=source.get("source_project_id"),
                    qty=source["qty"],
                    claim_id=source.get("claim_id"),
                    confirmed_by=actor_user_id if source.get("confirmed") else None,
                    confirmed_at=now if source.get("confirmed") else None,
                )
            )
        self.db.flush()

    def _withdraw_open_claims(self, line_id: str) -> None:
        for claim in (
            self.db.query(AllocationClaim)
            .filter(
                AllocationClaim.so_line_id == line_id,
                AllocationClaim.state == CLAIM_REQUESTED,
            )
            .all()
        ):
            self.db.delete(claim)

    def _restamp_stock_location(self, line: ProjectSalesOrderLine) -> None:
        """AC-H5: the CONFIRMED source becomes the stock location the inquiry carries.

        Unconfirmed sources are excluded on purpose. While a claim is open the line has no
        stock location, so an order inquiry derived from it cannot quote a warehouse nobody
        has agreed to release.
        """
        rows = [
            row
            for row in self.allocations_of(line.id)
            if row.confirmed_at is not None and row.warehouse_id
        ]
        codes = self._warehouse_codes({row.warehouse_id for row in rows})
        ordered = [codes.get(row.warehouse_id) for row in rows if codes.get(row.warehouse_id)]
        # Stable and readable: "BRW-BB + MWH" is what a split reads as on the inquiry.
        unique: List[str] = []
        for code in ordered:
            if code not in unique:
                unique.append(code)
        line.stock_location = " + ".join(unique) if unique else None

    def clear(self, line: ProjectSalesOrderLine) -> None:
        self._replace_allocations(line, [], actor_user_id="")
        self._restamp_stock_location(line)
        self.db.flush()

    # -------------------------------------------------------------------- claims

    def raise_claim(
        self,
        line: ProjectSalesOrderLine,
        project: Project,
        *,
        warehouse_id: str,
        to_project_id: str,
        qty: Decimal,
        actor_user_id: str,
    ) -> AllocationClaim:
        """Ask another project's CS for stock they are holding (AC-H4).

        Writes the claim AND an unconfirmed allocation, so the line shows what it is
        waiting on. Neither grants anything: the allocation carries no ``confirmed_at``,
        the line gets no stock location, and the pile stays held by its current owner.
        """
        if to_project_id == project.id:
            raise AppException(
                status_code=422,
                message="A project cannot claim stock from itself.",
                code="allocation_claim_self",
            )
        holder = self._project(to_project_id)
        if holder is None:
            raise AppException(
                status_code=404,
                message="The project holding that stock no longer exists.",
                code="project_not_found",
            )
        if _dec(line.qty) < qty:
            raise AppException(
                status_code=422,
                message=(
                    f"The line needs {format(_qty(line.qty), 'f')}. Asking for "
                    f"{format(_qty(qty), 'f')} would over-source it."
                ),
                code="allocation_claim_over_line",
            )

        ranked = self.rank(line, project)
        candidate = next(
            (c for c in ranked.candidates if c.warehouse_id == warehouse_id), None
        )
        held = _ZERO
        if candidate:
            held = sum(
                (holder_row.qty for holder_row in candidate.holders
                 if holder_row.project_id == to_project_id),
                _ZERO,
            )
        if held < qty:
            warehouse = self._warehouse(warehouse_id)
            raise AppException(
                status_code=409,
                message=(
                    f"{holder.project_code} holds {format(_qty(held), 'f')} at "
                    f"{warehouse.warehouse_code if warehouse else 'that location'}, and "
                    f"{format(_qty(qty), 'f')} was asked for."
                ),
                code="allocation_claim_over_hold",
            )

        already = (
            self.db.query(AllocationClaim)
            .filter(
                AllocationClaim.so_line_id == line.id,
                AllocationClaim.warehouse_id == warehouse_id,
                AllocationClaim.to_project_id == to_project_id,
                AllocationClaim.state == CLAIM_REQUESTED,
            )
            .first()
        )
        if already is not None:
            raise AppException(
                status_code=409,
                message=(
                    f"{holder.project_code} has already been asked for this stock and has "
                    "not answered yet."
                ),
                code="allocation_claim_open",
            )

        claim = AllocationClaim(
            company_id=line.company_id,
            from_project_id=project.id,
            to_project_id=to_project_id,
            so_line_id=line.id,
            product_id=line.product_id,
            warehouse_id=warehouse_id,
            qty=qty,
            state=CLAIM_REQUESTED,
            requested_by=actor_user_id,
        )
        self.db.add(claim)
        self.db.flush()

        self.db.add(
            SOLineAllocation(
                company_id=line.company_id,
                so_line_id=line.id,
                source_type=ALLOC_SOURCE_OTHER_PROJECT,
                warehouse_id=warehouse_id,
                source_project_id=to_project_id,
                qty=qty,
                claim_id=claim.id,
                confirmed_by=None,
                confirmed_at=None,
            )
        )
        self.db.flush()
        return claim

    def accept_claim(self, claim: AllocationClaim, *, actor_user_id: str) -> AllocationClaim:
        self._assert_open(claim)
        claim.state = CLAIM_ACCEPTED
        claim.decided_by = actor_user_id
        claim.decided_at = datetime.utcnow()
        self.db.flush()

        # The allocation the claim backed becomes real, stamped to the person who chose
        # the source rather than to the person who released it.
        for row in (
            self.db.query(SOLineAllocation)
            .filter(SOLineAllocation.claim_id == claim.id)
            .all()
        ):
            row.confirmed_by = claim.requested_by
            row.confirmed_at = claim.decided_at
        self.db.flush()
        if claim.so_line_id:
            line = (
                self.db.query(ProjectSalesOrderLine)
                .filter(ProjectSalesOrderLine.id == claim.so_line_id)
                .first()
            )
            if line is not None:
                self._restamp_stock_location(line)
        self.db.flush()
        return claim

    def refuse_claim(
        self, claim: AllocationClaim, *, reason: str, actor_user_id: str
    ) -> AllocationClaim:
        self._assert_open(claim)
        cleaned = (reason or "").strip()
        if len(cleaned) < 3:
            raise AppException(
                status_code=422,
                message=(
                    "Say why the stock cannot be released. A refusal without a reason "
                    "sends the asker back to a phone call."
                ),
                code="allocation_refusal_needs_reason",
            )
        claim.state = CLAIM_REFUSED
        claim.reason = cleaned
        claim.decided_by = actor_user_id
        claim.decided_at = datetime.utcnow()
        self.db.flush()
        # The allocation stays, unconfirmed, so the refusal and its reason are on the line
        # the next person opens instead of the row silently vanishing.
        if claim.so_line_id:
            line = (
                self.db.query(ProjectSalesOrderLine)
                .filter(ProjectSalesOrderLine.id == claim.so_line_id)
                .first()
            )
            if line is not None:
                self._restamp_stock_location(line)
        self.db.flush()
        return claim

    def _assert_open(self, claim: AllocationClaim) -> None:
        if claim.state != CLAIM_REQUESTED:
            raise AppException(
                status_code=409,
                message=(
                    f"This claim was already {claim.state}. Raise a new one if the answer "
                    "has changed."
                ),
                code="allocation_claim_decided",
            )

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

    def assert_can_answer(
        self, claim: AllocationClaim, user_id: str, permissions: Set[str]
    ) -> Project:
        holder = self._project(claim.to_project_id)
        if holder is None:
            raise AppException(
                status_code=404,
                message="The project holding that stock no longer exists.",
                code="project_not_found",
            )
        if not self.can_act_for_project(holder, user_id, permissions):
            raise AppException(
                status_code=403,
                message=(
                    f"{holder.project_code} belongs to another salesperson. Only their CS "
                    "can release this stock."
                ),
                code="allocation_claim_not_yours",
            )
        return holder

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

        ``can_answer`` is computed with the SAME authority that gates accept and refuse,
        rather than being inferred from which tab the user is looking at. Without it the
        outgoing view offered Release and Refuse on the viewer's own request: buttons the
        server would reject, on a list that mixes both directions when the filter is
        "all". Whether you may answer a claim is a property of the claim and the viewer,
        not of the filter.
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
        can_answer = False
        if viewer_id and holder is not None and claim.state == CLAIM_REQUESTED:
            can_answer = self.can_act_for_project(
                holder, viewer_id, viewer_permissions or set()
            )

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
