"""Recording what a supplier's code means, and putting the rows already on file right.

The ladder (`supplier_code_matcher`) answers what it can and writes its answers down. This
module is the other half: what a PERSON decides, and what happens to the rows uploaded
before they decided it.

The re-bind is the point. The loading plan is read off `scm.supplier_inventory` and the PI
convert off `scm.proforma_invoice_line`, so an answer that only takes effect on the next
upload is an answer nobody gets to use today - the operator would have to re-upload a file
they already uploaded to see their own decision.
"""
from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.product import Product
from app.models.product_set import ProductSet
from app.models.scm import (
    ProformaInvoice,
    ProformaInvoiceLine,
    ProformaInvoiceShipmentLink,
    SupplierInventory,
    SupplierProductCodeAlias,
)
from app.services.error_handler import AppException
from app.services.scm.supplier_code_matcher import resolve
from app.services.scm.supplier_scope import is_uuid as _is_uuid

_MANUAL = "manual"
_DISMISSED = "dismissed"


def _uuid() -> str:
    return str(uuid.uuid4())


def _product_or_404(db: Session, product_id: str) -> Product:
    """One of OUR products, through the ORM so the company filter applies: a code cannot be
    bound to another company's catalogue."""
    if not _is_uuid(product_id):
        raise AppException(404, "That product does not exist.", detail="product_id")
    product = db.query(Product).filter(Product.id == str(product_id)).first()
    if product is None:
        raise AppException(404, "That product does not exist.", detail="product_id")
    return product


def _set_or_404(db: Session, product_set_id: str) -> ProductSet:
    """One of OUR sets, through the ORM so the company filter applies: a code cannot be
    bound to another company's set any more than to another company's product."""
    if not _is_uuid(product_set_id):
        raise AppException(404, "That product set does not exist.", detail="product_set_id")
    row = db.query(ProductSet).filter(ProductSet.id == str(product_set_id)).first()
    if row is None:
        raise AppException(404, "That product set does not exist.", detail="product_set_id")
    return row


def create(
    db: Session,
    *,
    supplier_id: str,
    supplier_code: str,
    product_id: Optional[str] = None,
    product_set_id: Optional[str] = None,
    actor: Optional[str] = None,
) -> dict:
    """"This code is that product" - or that SET. Replaces what was recorded, and re-binds.

    Exactly one of the two (R19, R20). A supplier who sells the whole WC writes the set
    code, and no product carries it, so "none of ours" would be the wrong answer and a
    member would be the wrong half. Two targets at once is refused here rather than at the
    database's CHECK, so the operator is told what to do about it.

    Replaces rather than adds: one supplier code means one thing, and two rows saying
    different things is the state the identity index exists to forbid. A manual pick landing
    on top of an automatic one is the normal path - it is how a guess gets corrected.

    Does not commit.
    """
    code = (supplier_code or "").strip()
    if not code:
        raise AppException(422, "Name the code the supplier wrote.", detail="supplier_code")
    if not _is_uuid(supplier_id):
        raise AppException(422, "That supplier does not exist.", detail="supplier_id")
    if bool(product_id) == bool(product_set_id):
        raise AppException(
            422,
            "Name either a product or a product set for this code, not both and not neither.",
            detail="product_id",
        )

    if product_set_id:
        product_set = _set_or_404(db, product_set_id)
        written = _record(db, supplier_id, code, None, str(product_set.id), _MANUAL, actor)
        rebound = _rebind(db, supplier_id, code, None, str(product_set.id))
        return {
            "id": str(written.id),
            "supplier_code": written.supplier_code,
            "product_id": None,
            "product_code": None,
            "product_set_id": str(product_set.id),
            "set_code": product_set.set_code,
            "set_name": product_set.name,
            "source": written.source,
            "matched_by": written.matched_by,
            **rebound,
        }

    product = _product_or_404(db, str(product_id))
    written = _record(db, supplier_id, code, str(product.id), None, _MANUAL, actor)
    rebound = _rebind(db, supplier_id, code, str(product.id), None)
    return {
        "id": str(written.id),
        "supplier_code": written.supplier_code,
        "product_id": str(product.id),
        "product_code": product.product_code,
        "product_set_id": None,
        "set_code": None,
        "set_name": None,
        "source": written.source,
        "matched_by": written.matched_by,
        **rebound,
    }


def dismiss(
    db: Session,
    *,
    supplier_id: str,
    supplier_code: str,
    actor: Optional[str] = None,
) -> dict:
    """"That is not one of ours." A ruling with no product, kept like every other ruling.

    Some codes a supplier sends name nothing our catalogue is ever going to hold - their own
    accessory, a spare, something they store for somebody else - and the queue of unanswered
    codes is a to-do list nobody reads once it holds lines that can never be crossed off.

    It UNBINDS rather than binds. A row still pointing at a product would go on offering the
    item to the loading plan, which is the opposite of what the ruling says, so the stock rows
    and the invoice lines under this code go back to unmatched in the same transaction.

    Replaces whatever was recorded before, exactly as `create` does: one supplier code carries
    one ruling, and a dismissal beside a match is two rows saying different things.

    Does not commit.
    """
    code = (supplier_code or "").strip()
    if not code:
        raise AppException(422, "Name the code the supplier wrote.", detail="supplier_code")
    if not _is_uuid(supplier_id):
        raise AppException(422, "That supplier does not exist.", detail="supplier_id")

    written = _record(db, supplier_id, code, None, None, _DISMISSED, actor)
    rebound = _rebind(db, supplier_id, code, None, None)
    return {
        "id": str(written.id),
        "supplier_code": written.supplier_code,
        "product_id": None,
        "product_code": None,
        "product_set_id": None,
        "set_code": None,
        "set_name": None,
        "source": written.source,
        "matched_by": written.matched_by,
        **rebound,
    }


def _record(
    db: Session,
    supplier_id: str,
    code: str,
    product_id: Optional[str],
    product_set_id: Optional[str],
    source: str,
    actor: Optional[str],
) -> SupplierProductCodeAlias:
    """The one ruling on file for this supplier's spelling, written or overwritten.

    Overwrites rather than adds, whichever way the ruling goes: the identity index allows one
    row per (company, supplier, code), and a person changing their mind is the normal path -
    it is how a guess gets corrected and how a dismissal gets replaced by a real match.
    """
    existing = (
        db.query(SupplierProductCodeAlias)
        .filter(
            SupplierProductCodeAlias.supplier_id == str(supplier_id),
            SupplierProductCodeAlias.supplier_code.ilike(code),
        )
        .first()
    )
    if existing is None:
        existing = SupplierProductCodeAlias(
            id=_uuid(),
            supplier_id=str(supplier_id),
            supplier_code=code,
            product_id=product_id,
            product_set_id=product_set_id,
            source=source,
            matched_by=source,
            created_by=actor,
        )
        db.add(existing)
    else:
        # Both columns, every time. A ruling that named a set and now names a product must
        # not leave the set id behind it: the CHECK refuses a row naming two things, and a
        # reader that saw both could not say which one the code means.
        existing.product_id = product_id
        existing.product_set_id = product_set_id
        existing.source = source
        existing.matched_by = source
        existing.created_by = actor
    db.flush()
    return existing


def delete(db: Session, alias_id: str, *, actor: Optional[str] = None) -> dict:
    """Forget this decision, and put the rows back to whatever the ladder says now.

    Not "leave them where they are": the binding existed BECAUSE of this alias, and a row
    still pointing at a product whose reason has been deleted is a binding nobody can
    account for. The ladder is re-run WITHOUT remembering, so deleting a correction does not
    immediately resurrect the guess it corrected as a fresh automatic alias.
    """
    if not _is_uuid(alias_id):
        raise AppException(404, "That code match does not exist.", detail="alias_id")
    alias = (
        db.query(SupplierProductCodeAlias)
        .filter(SupplierProductCodeAlias.id == str(alias_id))
        .first()
    )
    if alias is None:
        raise AppException(404, "That code match does not exist.", detail="alias_id")

    supplier_id = str(alias.supplier_id)
    code = alias.supplier_code
    db.delete(alias)
    db.flush()

    found = resolve(db, supplier_id, [code], remember=False, actor=actor)
    match = found.get(code)
    rebound = _rebind(
        db,
        supplier_id,
        code,
        match.product_id if match else None,
        match.product_set_id if match else None,
    )
    return {"deleted": 1, **rebound}


def rematch_for_plan(db: Session, plan_id: str, *, actor: Optional[str] = None) -> dict:
    """Run the ladder again over THIS plan's still-unbound rows (S6, AC-C7).

    The same pass, one scope narrower: the queue beside the button is the plan's own, so a
    run that moved another plan's rows would report counts nobody on this screen can see. The
    ALIAS it writes is still the supplier's and is consulted on every later upload - the
    memory is the supplier's, only the rebind is the plan's.
    """
    plan = _plan_or_422(db, plan_id)
    if plan.document_kind == "none":
        return {"inventory_bound": 0, "invoice_lines_bound": 0, "still_unmatched": 0}
    return rematch(
        db,
        supplier_id=str(plan.supplier_id),
        actor=actor,
        loading_plan_id=str(plan.id),
    )


def rematch(
    db: Session,
    *,
    supplier_id: str,
    actor: Optional[str] = None,
    loading_plan_id: Optional[str] = None,
) -> dict:
    """Run the ladder again over everything of this supplier's that is still unbound (R18).

    The catalogue moves after the file lands. A product added the day after the stock list
    was uploaded, or an alias recorded from the invoice screen, leaves rows sitting unbound
    under a code the ladder can now answer - and the only way to make them catch up was to
    upload the same file again, which is a ceremony rather than a decision.

    Unbound rows ONLY, both readers, the SAME ladder the upload walks: a row that already
    carries a product is left where it is (re-deriving a settled binding is a chance to
    disagree with it), and rung 0 means a dismissal stays dismissed and a person's own pick
    still outranks every derivation. What the ladder works out is written down as an `auto`
    alias exactly as an upload writes it, so the next file reads a decision.

    Does not commit.
    """
    if not _is_uuid(supplier_id):
        raise AppException(422, "That supplier does not exist.", detail="supplier_id")

    stock_q = db.query(SupplierInventory).filter(
        SupplierInventory.supplier_id == str(supplier_id),
        SupplierInventory.product_id.is_(None),
        SupplierInventory.product_set_id.is_(None),
    )
    if loading_plan_id:
        stock_q = stock_q.filter(SupplierInventory.loading_plan_id == loading_plan_id)
    stock = stock_q.all()
    lines_q = (
        db.query(ProformaInvoiceLine)
        .join(ProformaInvoice, ProformaInvoice.id == ProformaInvoiceLine.invoice_id)
        .filter(
            ProformaInvoice.supplier_id == str(supplier_id),
            # A superseded revision is what the supplier sent on the day and is read-only, and
            # a converted invoice has already told each line's story on a shipment - binding
            # one afterwards would leave the PI detail saying "matched" beside a link row that
            # says the line was skipped as unmatched.
            ProformaInvoice.status == "current",
            ~db.query(ProformaInvoiceShipmentLink)
            .filter(
                ProformaInvoiceShipmentLink.proforma_invoice_id == ProformaInvoice.id
            )
            .exists(),
            ProformaInvoiceLine.product_id.is_(None),
            ProformaInvoiceLine.product_set_id.is_(None),
        )
    )
    if loading_plan_id:
        lines_q = lines_q.filter(ProformaInvoice.loading_plan_id == loading_plan_id)
    lines = lines_q.all()

    codes = [
        code
        for code in dict.fromkeys(
            [(r.item_code or "").strip() for r in stock]
            + [(l.item_code or "").strip() for l in lines]
        )
        if code
    ]
    if not codes:
        return {
            "inventory_bound": 0,
            "invoice_lines_bound": 0,
            "still_unmatched": _still_unmatched(db, supplier_id, loading_plan_id),
        }

    found = resolve(db, supplier_id, codes, remember=True, actor=actor)
    # Keyed the way the rows are read back: two rows can spell one code in two cases, and the
    # ladder answers under the spelling it was handed. Both halves of the answer travel,
    # because since R19 a code can name a set as readily as a product.
    by_code = {
        code.strip().upper(): (match.product_id, match.product_set_id)
        for code, match in found.items()
    }

    bound_stock = 0
    for row in stock:
        product_id, set_id = by_code.get((row.item_code or "").strip().upper(), (None, None))
        if product_id or set_id:
            row.product_id = product_id
            row.product_set_id = set_id
            bound_stock += 1
    bound_lines = 0
    for line in lines:
        product_id, set_id = by_code.get((line.item_code or "").strip().upper(), (None, None))
        if product_id or set_id:
            line.product_id = product_id
            line.product_set_id = set_id
            bound_lines += 1
    db.flush()

    return {
        "inventory_bound": bound_stock,
        "invoice_lines_bound": bound_lines,
        # The queue as the operator will see it after this - the rows still unbound and not
        # dismissed - rather than a count of codes, because the queue is what they read.
        "still_unmatched": _still_unmatched(db, supplier_id, loading_plan_id),
    }


def _still_unmatched(
    db: Session, supplier_id: str, loading_plan_id: Optional[str]
) -> int:
    """What is left to answer, on the same scope the pass just ran on."""
    if not loading_plan_id:
        return len(unmatched_for_supplier(db, supplier_id))
    rows = _unmatched_rows(db, supplier_id, loading_plan_id=loading_plan_id)
    return len(rows) if rows is not None else len(unmatched_for_supplier(db, supplier_id))


def list_for_supplier(db: Session, supplier_id: str) -> list[dict]:
    """What is on record for this supplier, in names a person reads - never an id."""
    if not _is_uuid(supplier_id):
        raise AppException(422, "That supplier does not exist.", detail="supplier_id")
    rows = (
        # OUTER on BOTH, because a ruling names a product, a set, or - when it is a
        # dismissal - neither, and all three are rulings somebody has to be able to see and
        # undo. An inner join would hide exactly the rows whose only route back into the
        # queue is the Forget button beside them.
        db.query(SupplierProductCodeAlias, Product, ProductSet)
        .outerjoin(Product, Product.id == SupplierProductCodeAlias.product_id)
        .outerjoin(ProductSet, ProductSet.id == SupplierProductCodeAlias.product_set_id)
        .filter(SupplierProductCodeAlias.supplier_id == str(supplier_id))
        # Newest ruling first (AC-C5): this is the supplier's memory, and what somebody just
        # decided is what they came back to check, not whatever sorts first alphabetically.
        .order_by(
            SupplierProductCodeAlias.created_at.desc(), SupplierProductCodeAlias.id.desc()
        )
        .all()
    )
    return [
        {
            "id": str(alias.id),
            "supplier_code": alias.supplier_code,
            "product_code": product.product_code if product else None,
            "product_name": product.product_name if product else None,
            "set_code": product_set.set_code if product_set else None,
            "set_name": product_set.name if product_set else None,
            "source": alias.source,
            "matched_by": alias.matched_by,
            "created_by": alias.created_by,
            "created_at": alias.created_at.isoformat() if alias.created_at else None,
        }
        for alias, product, product_set in rows
    ]


def _plan_or_422(db: Session, plan_id: str):
    """The loading plan a read is scoped to. A bad id is a form mistake, not a 500."""
    from app.models.scm import LoadingPlan

    if not _is_uuid(plan_id):
        raise AppException(422, "That loading plan does not exist.", detail="plan_id")
    plan = db.query(LoadingPlan).filter(LoadingPlan.id == str(plan_id)).first()
    if plan is None:
        raise AppException(422, "That loading plan does not exist.", detail="plan_id")
    return plan


def unmatched_for_plan(db: Session, plan_id: str) -> list[dict]:
    """The unknown codes on THIS plan's own statement (S6, AC-C7).

    The queue used to be the supplier's, and a ROYAL MIRROR plan started with NO file listed
    79 codes off a stock list somebody had uploaded from a different plan - beside a subtitle
    reading "No file". A plan reads what it was started from:

    * `stock_list` - the `supplier_inventory` rows stamped with it;
    * `proforma` - the `proforma_invoice_line` rows of the invoices stamped with it, which
      the supplier-wide read never looked at, so a proforma plan's queue was always empty;
    * `none` - nothing at all. That is the whole point of the fix.

    A plan that predates migration 454 has nothing stamped and falls back to the supplier-wide
    queue, exactly as the build does: blanking every plan that was open on the day would be a
    worse answer than the drift they already carry. A "No file" plan never falls back - it has
    no statement to be legacy about.
    """
    plan = _plan_or_422(db, plan_id)
    if plan.document_kind == "none":
        return []
    supplier_id = str(plan.supplier_id)
    rows = _unmatched_rows(db, supplier_id, loading_plan_id=str(plan.id))
    return rows if rows is not None else unmatched_for_supplier(db, supplier_id)


def unmatched_for_supplier(db: Session, supplier_id: str) -> list[dict]:
    """The codes this supplier sent that bind to nothing we hold.

    Read off the STOCK rows rather than off the last upload's summary: the upload dialog
    counts them and then goes away, and the loading plan is where somebody comes back to
    answer them. The supplier's own words for the item travel with the code, because that is
    what the person matching it has to recognise.

    A code somebody dismissed is NOT here. The queue is a to-do list, and a line that cannot
    be crossed off is what makes people stop reading one; the ruling stays on file, and
    Forget puts the code back.
    """
    if not _is_uuid(supplier_id):
        raise AppException(422, "That supplier does not exist.", detail="supplier_id")
    dismissed = (
        db.query(func.upper(SupplierProductCodeAlias.supplier_code))
        .filter(
            SupplierProductCodeAlias.supplier_id == str(supplier_id),
            SupplierProductCodeAlias.source == _DISMISSED,
        )
        .scalar_subquery()
    )
    rows = (
        db.query(SupplierInventory)
        .filter(
            SupplierInventory.supplier_id == str(supplier_id),
            # Unbound means bound to NEITHER: a row naming a set is answered, and the queue
            # is a to-do list (R19).
            SupplierInventory.product_id.is_(None),
            SupplierInventory.product_set_id.is_(None),
            func.upper(SupplierInventory.item_code).notin_(dismissed),
        )
        .order_by(SupplierInventory.item_code)
        .all()
    )
    return [_stock_queue_row(row) for row in rows]


def _stock_queue_row(row: SupplierInventory) -> dict:
    """One queue line off a stock row. The supplier's own words travel with the code, because
    that is what the person matching it recognises."""
    return {
        "item_code": row.item_code,
        "product_name": row.product_name,
        "brand": row.brand,
        "spec": row.spec,
        "qty_packed": float(row.qty_packed or 0),
        "qty_unfinished": float(row.qty_unfinished or 0),
        "as_of": row.as_of.isoformat() if row.as_of else None,
    }


def _unmatched_rows(
    db: Session, supplier_id: str, *, loading_plan_id: str
) -> Optional[list[dict]]:
    """The queue for ONE plan's own rows, or `None` when it has none of its own (legacy).

    `None` rather than `[]` on purpose: "this plan has nothing stamped" and "this plan's
    codes are all answered" are different states, and only the first one falls back.
    """
    dismissed = (
        db.query(func.upper(SupplierProductCodeAlias.supplier_code))
        .filter(
            SupplierProductCodeAlias.supplier_id == str(supplier_id),
            SupplierProductCodeAlias.source == _DISMISSED,
        )
        .scalar_subquery()
    )

    stock_scope = db.query(SupplierInventory).filter(
        SupplierInventory.loading_plan_id == loading_plan_id
    )
    if stock_scope.count():
        rows = (
            stock_scope.filter(
                SupplierInventory.product_id.is_(None),
                SupplierInventory.product_set_id.is_(None),
                func.upper(SupplierInventory.item_code).notin_(dismissed),
            )
            .order_by(SupplierInventory.item_code)
            .all()
        )
        return [_stock_queue_row(row) for row in rows]

    invoice_scope = db.query(ProformaInvoice).filter(
        ProformaInvoice.loading_plan_id == loading_plan_id
    )
    if not invoice_scope.count():
        return None
    lines = (
        db.query(ProformaInvoiceLine, ProformaInvoice)
        .join(ProformaInvoice, ProformaInvoice.id == ProformaInvoiceLine.invoice_id)
        .filter(
            ProformaInvoice.loading_plan_id == loading_plan_id,
            ProformaInvoiceLine.product_id.is_(None),
            ProformaInvoiceLine.product_set_id.is_(None),
            func.upper(ProformaInvoiceLine.item_code).notin_(dismissed),
        )
        .order_by(ProformaInvoiceLine.item_code)
        .all()
    )
    # One line per CODE, not per block: the pre-loading sheet names one model in two of its
    # five blocks, and asking the same question twice is what makes a queue stop being read.
    merged: dict[str, dict] = {}
    for line, invoice in lines:
        code = (line.item_code or "").strip()
        if not code:
            continue
        cur = merged.setdefault(
            code,
            {
                "item_code": code,
                "product_name": line.description,
                "brand": None,
                "spec": None,
                "qty_packed": 0.0,
                # A proforma states ONE quantity per line: there is no unfinished half of it,
                # and inventing one would be a number the supplier never wrote.
                "qty_unfinished": 0.0,
                "as_of": invoice.invoice_date.isoformat() if invoice.invoice_date else None,
            },
        )
        cur["qty_packed"] += float(line.qty or 0)
        if cur["product_name"] is None:
            cur["product_name"] = line.description
    return [merged[code] for code in sorted(merged)]


def _rebind(
    db: Session,
    supplier_id: str,
    code: str,
    product_id: Optional[str],
    product_set_id: Optional[str] = None,
) -> dict:
    """Point every row already uploaded under this code at whatever it now means.

    Both readers, in the same transaction: the stock list feeds the loading plan and the
    invoice lines feed the convert, and a decision that reached one of them and not the
    other would have the two screens disagreeing about the same code.

    BOTH columns are written on every row, never just the one being set. A row that used to
    name a set and now names a product has to stop naming the set, or the plan goes on
    offering the whole WC under a code somebody has just said is the pedestal.
    """
    stock = (
        db.query(SupplierInventory)
        .filter(
            SupplierInventory.supplier_id == str(supplier_id),
            SupplierInventory.item_code.ilike(code),
        )
        .all()
    )
    for row in stock:
        row.product_id = product_id
        row.product_set_id = product_set_id

    lines = (
        db.query(ProformaInvoiceLine)
        .join(ProformaInvoice, ProformaInvoice.id == ProformaInvoiceLine.invoice_id)
        .filter(
            ProformaInvoice.supplier_id == str(supplier_id),
            ProformaInvoiceLine.item_code.ilike(code),
        )
        .all()
    )
    for line in lines:
        line.product_id = product_id
        line.product_set_id = product_set_id
    db.flush()
    return {
        "rebound_stock_rows": len(stock),
        "rebound_invoice_lines": len(lines),
    }
