"""Customer Branches list (#1356): the AutoCount branch table, read only.

The AutoCount `branchbypage` push is the only writer of `branches` (plan 1.11, ruling Q2), so
this service only reads. A branch belongs to the CRM customer whose `customer_code` equals the
branch's `AccNo`, trimmed and case-insensitive, in the branch's own company: the rule the DO
ingest uses for `DebtorCode` (`MasterRefResolver._resolve_by_code`).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import exists, func, or_, select
from sqlalchemy.orm import Session

from app.models.autocount_branch import Branch
from app.models.order import Customer
from app.services.error_handler import handle_not_found


def _key(column):
    return func.upper(func.btrim(column))


def _norm(value: Optional[str]) -> str:
    return (value or "").strip().upper()


class BranchService:
    SORT_MAP = {
        "acc_no": Branch.acc_no,
        "branch_code": Branch.branch_code,
        "branch_name": Branch.branch_name,
        "source_book": Branch.source_book,
        "last_synced_at": Branch.last_synced_at,
    }

    def __init__(self, db: Session):
        self.db = db

    def _in_crm(self):
        return exists(
            select(Customer.id).where(
                Customer.company_id == Branch.company_id,
                _key(Customer.customer_code) == _key(Branch.acc_no),
            )
        )

    def list_branches(
        self,
        page: int = 1,
        limit: int = 50,
        query: Optional[str] = None,
        sort_field: str = "last_synced_at",
        sort_dir: str = "desc",
        book: Optional[str] = None,
        in_crm: Optional[bool] = None,
        customer_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        q = self.db.query(Branch)
        if customer_id:
            customer = self.db.query(Customer).filter(Customer.id == customer_id).first()
            if customer is None:
                raise handle_not_found("Customer", customer_id)
            q = q.filter(
                Branch.company_id == customer.company_id,
                _key(Branch.acc_no) == _norm(customer.customer_code),
            )
        if query:
            like = f"%{query.strip()}%"
            q = q.filter(
                or_(
                    Branch.acc_no.ilike(like),
                    Branch.branch_code.ilike(like),
                    Branch.branch_name.ilike(like),
                )
            )
        if book:
            q = q.filter(Branch.source_book == book)
        if in_crm is not None:
            q = q.filter(self._in_crm() if in_crm else ~self._in_crm())

        column = self.SORT_MAP.get(sort_field, Branch.last_synced_at)
        ordered = column.asc() if sort_dir == "asc" else column.desc()
        q = q.order_by(ordered.nullslast(), Branch.id.asc())

        total = q.count()
        rows = q.offset((page - 1) * limit).limit(limit).all()
        return {
            "data": self._serialize(rows),
            "pagination": {"total": total, "page": page, "limit": limit},
            "empty": total == 0,
        }

    def books(self) -> List[str]:
        """The books the caller's branches come from, for the Book filter."""
        return [
            b for (b,) in self.db.query(Branch.source_book).distinct().order_by(Branch.source_book)
        ]

    def _serialize(self, rows: List[Branch]) -> List[Dict[str, Any]]:
        """One lookup for the page's customers; the oldest customer wins a code shared by two
        (customers are unique by code AND name)."""
        codes = {_norm(r.acc_no) for r in rows if _norm(r.acc_no)}
        matched: Dict[Tuple[str, str], Customer] = {}
        if codes:
            customers = (
                self.db.query(Customer)
                .filter(
                    Customer.company_id.in_(list({r.company_id for r in rows})),
                    _key(Customer.customer_code).in_(codes),
                )
                .order_by(Customer.created_at.asc(), Customer.id.asc())
                .all()
            )
            for c in customers:
                matched.setdefault((str(c.company_id), _norm(c.customer_code)), c)
        out = []
        for r in rows:
            customer = matched.get((str(r.company_id), _norm(r.acc_no)))
            out.append(
                {
                    "id": r.id,
                    "source_book": r.source_book,
                    "acc_no": r.acc_no,
                    "branch_code": r.branch_code,
                    "branch_name": r.branch_name,
                    "last_synced_at": r.last_synced_at,
                    "customer_id": customer.id if customer else None,
                    "customer_name": customer.customer_name if customer else None,
                }
            )
        return out
