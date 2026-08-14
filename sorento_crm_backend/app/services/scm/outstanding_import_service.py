"""Preview an outstanding-orders upload, and apply it once someone confirms.

Two entry points sharing one code path, which is the point: `preview()` and `apply()` build
the SAME diff from the SAME resolution, and apply simply writes what preview showed. A
preview computed differently from the commit is a preview that lies.

Resolution failures are surfaced, never guessed. An unknown item code is reported with its
row number and the line is skipped; it is not invented as a new product, because a typo
would otherwise silently become a SKU that gets planned and purchased.
"""
from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.order import Customer, SalesOrder, SalesOrderLine
from app.models.procurement import PurchaseOrder, PurchaseOrderLine, Supplier
from app.models.inventory import Warehouse
from app.models.product import Product
from app.services.import_alias_service import AliasResolver
from app.services.scm.outstanding_diff import (
    ADDED,
    CLOSED,
    DATE_AND_QTY_CHANGED,
    QTY_CHANGED,
    UNCHANGED,
    Diff,
    Line,
    diff_lines,
)
from app.services.scm import plan_exception_service
from app.services.scm import reorder_run_service
from app.services.scm import sales_agent_service
# Imported rather than defined here, and re-exported under the names this module has always
# used. The vocabulary moved to `demand_class.py` when the salesperson master gained a
# `demand_class` column of its own: two modules now WRITE this value and one of them is a
# check constraint, so a second copy of the word list would be a database that accepts what
# the importer rejects.
from app.services.scm.demand_class import DEFAULT_DEMAND_CLASS
from app.services.scm.demand_class import class_of as _class_of
from app.services.scm.outstanding_reader import PO, SO, ReadResult, RowProblem, read_workbook

logger = logging.getLogger(__name__)

# Demand class drives fulfilment priority: `scm.priority_policy.demand_class_weights` is
# keyed on it. A stated split that is not recognisably a project is retail, because that is
# the only other class the seeded weights carry and a new word would score as nothing.
# A split nobody states is NOT retail - see `_class_of`, imported above.

# A quantity difference below this is noise between two exports, not a decision. Same figure
# the diff uses, for the same reason.
_QTY_EPSILON = 0.0005


@dataclass(frozen=True)
class _Binding:
    """How one document type maps onto its tables.

    The write path is parameterised by this rather than branching on `doc_type` in a dozen
    places, and `outstanding_diff` stays entirely document-agnostic. Two copy-pasted halves
    is how the two sides drift: the original bug was precisely a write path that ignored
    doc_type and put purchase orders into `sales_orders`.
    """

    header: type            # SalesOrder / PurchaseOrder
    line: type              # SalesOrderLine / PurchaseOrderLine
    number: str             # the header's human document number attribute
    header_fk: str          # the line's FK back to its header
    date: str               # the line's dated axis
    fulfilled: str          # quantity already delivered / received
    party_fk: str           # the header's counterparty FK
    party_code: str         # the file field naming that counterparty
    party: Optional[type]   # the counterparty model, or None when this path does not link one
    party_code_col: str     # that model's code column
    # Two DIFFERENT jobs, deliberately separate fields. `write_status` is what a header this
    # import creates (or lifts) is stamped with; `live_statuses` is the predicate for reading
    # existing ones. They were one field, and the narrower write value then hid every document
    # that had moved on: a purchase order that has taken a goods receipt sits in `received`,
    # so the diff saw a document with no lines and inserted them all again, doubling on-order.
    write_status: str
    live_statuses: tuple[str, ...]
    # Line columns fed from the file's money columns, when it has any. Empty for the sales
    # book, whose extract carries no price at all.
    money_cols: tuple[tuple[str, str], ...] = ()
    # Header columns fed from the file, per document. Same (column, extras key) shape.
    header_cols: tuple[tuple[str, str], ...] = ()
    # Header columns the file FILLS rather than restates: written only where the header
    # holds nothing. Separate from `header_cols` because the two answer different questions.
    # `header_cols` is for figures the file is the system of record for (the PO date), so a
    # later extract corrects them; these are for a value a person may have set by hand, where
    # a weekly re-upload silently overwriting it is the failure.
    header_fill_cols: tuple[tuple[str, str], ...] = ()
    # The header column fulfilment priority is weighed on, and the header column the
    # project-versus-dealer split is stated in. Both None for purchase orders, which carry
    # no demand at all. `demand_split_col` is the source of truth (plan amendment of
    # 4 Aug 2026); `demand_class_col` is what the policy reads, stamped from it at import.
    demand_class_col: Optional[str] = None
    demand_split_col: Optional[str] = None
    # The header column the salesperson master is linked through, and None for purchase
    # orders, which have no agent at all. Its presence is also what turns the agent half of
    # the classification and the unmapped-agent report on, so the PO path cannot acquire
    # either by accident.
    agent_fk: Optional[str] = None


_BINDINGS: dict[str, _Binding] = {
    SO: _Binding(
        header=SalesOrder, line=SalesOrderLine,
        number="so_number", header_fk="sales_order_id",
        date="required_date", fulfilled="qty_delivered",
        party_fk="customer_id", party_code="debtor_code",
        # The SO path deliberately does NOT link the customer yet. The debtor code is read but
        # nothing consumes `sales_orders.customer_id` from this channel, and reporting an
        # unresolvable debtor code as an issue before anything reads it is noise on a screen
        # whose whole job is to show the operator what needs fixing. Linking it is the same
        # three lines as the PO side the day a consumer exists.
        party=None, party_code_col="customer_code",
        # `scm.committed_v` counts exactly one sales-order status, so writing and reading are
        # the same value here.
        write_status="open", live_statuses=("open",),
        # OPTIONAL in the file and FILL-only on the header: no export carries an order type
        # today, so this is the column that lets a differently-worded export classify its own
        # documents the day it does, without a release. A value already on the header wins,
        # because that is what a person set and the extract is not the record of it.
        header_fill_cols=(("order_type", "order_type"),),
        demand_class_col="demand_class", demand_split_col="order_type",
        agent_fk="sales_agent_id",
    ),
    PO: _Binding(
        header=PurchaseOrder, line=PurchaseOrderLine,
        number="po_number", header_fk="purchase_order_id",
        date="expected_date", fulfilled="qty_received",
        party_fk="supplier_id", party_code="creditor_code",
        party=Supplier, party_code_col="supplier_code",
        # NOT "draft". `scm.on_order_v` counts only placed orders, deliberately excluding
        # drafts (M4-D5), and an outstanding-PO extract is a book of orders already placed
        # with suppliers. Writing them as drafts would import the supply and then hide it.
        write_status="active",
        # Every status in which a purchase order is still a live document, matching
        # `scm.on_order_v`, `dashboard_service.PLACED_PO_STATUSES` and
        # `purchase_order_service._ON_ORDER_STATUSES`. A part-received order is the same
        # order, so Monday's extract re-uploaded must diff against it rather than re-order it.
        live_statuses=("active", "received", "partial", "closed"),
        # (line column, extras key). Cost is what the cash co-pilot ranks on, so an absent
        # cost stays absent rather than becoming a zero that reads as free goods.
        money_cols=(("unit_cost", "unit_cost"), ("currency", "currency")),
        # `scm.receipt_lead_v` measures lead days from `po.issue_date`, so an order imported
        # without it contributes nothing to the measured supplier lead time.
        header_cols=(("issue_date", "order_date"), ("currency", "currency")),
    ),
}


def _binding(doc_type: str) -> _Binding:
    try:
        return _BINDINGS[doc_type]
    except KeyError:  # pragma: no cover - guarded at the route
        raise ValueError(f"no write binding for document type {doc_type!r}")


@dataclass
class ResolutionIssue:
    row_number: int
    field: str
    value: str
    reason: str


@dataclass
class AgentNotice:
    """An agent code in this file that can classify nothing, and why.

    Its own list rather than a row problem or a resolution issue, because it is neither: the
    file is fine, the code resolved (or was created), and nothing is being skipped. What it
    reports is a gap in MASTER data that only the client can close - which of his 38 codes
    still need a demand class - and that is a different question from "which rows of this file
    could not be read". Kept off the row lists so it cannot bury them.
    """

    code: str
    #: True when this upload is the first thing that has ever named the agent.
    is_new: bool
    reason: str


@dataclass
class PreviewResult:
    doc_type: str
    scope_documents: tuple[str, ...]
    counts: dict
    total_rows: int
    unmapped_headers: list[str]
    missing_columns: list[str]
    row_problems: list[RowProblem] = field(default_factory=list)
    resolution_issues: list[ResolutionIssue] = field(default_factory=list)
    samples: dict = field(default_factory=dict)
    # Documents this upload would lift to the live status. Same key as `apply`'s response, so
    # the confirm screen shows the side effect BEFORE it happens and the commit reports the
    # same fact afterwards.
    activated_documents: list[str] = field(default_factory=list)
    # Agent codes in this file that carry no demand class, so the client can see which of his
    # master rows still need one. Same key on both responses, same reason as above.
    unmapped_agents: list[AgentNotice] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.missing_columns

    def to_dict(self) -> dict:
        return {
            "doc_type": self.doc_type,
            "ok": self.ok,
            "scope_documents": list(self.scope_documents),
            "counts": self.counts,
            "total_rows": self.total_rows,
            "unmapped_headers": self.unmapped_headers,
            "missing_columns": self.missing_columns,
            "row_problems": [asdict(p) for p in self.row_problems],
            "resolution_issues": [asdict(i) for i in self.resolution_issues],
            "samples": self.samples,
            "activated_documents": list(self.activated_documents),
            "unmapped_agents": [asdict(a) for a in self.unmapped_agents],
        }


@dataclass
class _Resolved:
    lines: list[Line]
    issues: list[ResolutionIssue]
    product_by_code: dict
    warehouse_by_code: dict
    # Which counterparty each document in the file belongs to. Per DOCUMENT, not per line:
    # the counterparty lives on the header, and a file naming two different creditors on one
    # PO number is a file problem, not a shape this write path should invent support for.
    party_by_doc: dict
    # The counterparty CODE behind each of those, so a report can name it instead of an id.
    party_code_by_doc: dict = field(default_factory=dict)
    # Header-level values the file states per document (`_Binding.header_cols`), first
    # non-empty wins: the extract repeats them on every row of the document.
    header_by_doc: dict = field(default_factory=dict)
    # Which agent CODE (normalised) sold each document. Per document and first non-empty
    # wins, and a document naming two different agents is REPORTED - the same rule as the
    # counterparty, in both halves, for the same reason: the extract states one value per
    # document on every row of it, so a second value is a file to fix rather than a shape to
    # support. Normalised by `sales_agent_service.normalize_code`, the same authority the
    # master is keyed by, so the class lookup, the row creation and the report all compare
    # one string.
    agent_by_doc: dict = field(default_factory=dict)


def _norm(code: str) -> str:
    return (code or "").strip().upper()


def _resolve_parties(db: Session, read: ReadResult, bind: _Binding) -> dict[str, str]:
    """Counterparty code -> id, within the active company.

    ORM, not raw SQL, for the same reason as every other lookup here: the isolation filter
    runs on ORM execution only, and reading another company's supplier would attribute this
    order to the wrong one. Who is late is the entire point of an expediting list.
    """
    if bind.party is None:
        return {}
    codes = {_norm(x.get("party_code")) for x in read.extras.values() if x.get("party_code")}
    if not codes:
        return {}
    code_col = getattr(bind.party, bind.party_code_col)
    return {
        _norm(code): str(pid)
        for pid, code in (
            db.query(bind.party.id, code_col)
            .filter(func.upper(code_col).in_(list(codes)))
            .all()
        )
    }


def _resolve(db: Session, read: ReadResult, bind: _Binding) -> _Resolved:
    """Map codes in the file onto real rows, reporting whatever cannot be resolved.

    Deliberately ORM queries, not raw SQL. `products`, `warehouses` and `sales_orders` are
    all company-scoped, and the isolation filter runs on ORM execution only - a raw
    `SELECT ... FROM products` sees EVERY company. That matters here rather than in theory:
    each company carries its own copy of the catalogue, so 11,390 product codes exist twice
    in this database. A raw lookup keyed by code would resolve to whichever row came back
    last and could attach an imported order line to another company's product.
    """
    issues: list[ResolutionIssue] = []

    item_codes = {_norm(l.item_code) for l in read.lines if l.item_code}
    loc_codes = {_norm(l.location) for l in read.lines if l.location}

    products: dict[str, str] = {}
    if item_codes:
        for pid, code in (
            db.query(Product.id, Product.product_code)
            .filter(func.upper(Product.product_code).in_(list(item_codes)))
            .all()
        ):
            products[_norm(code)] = str(pid)

    warehouses: dict[str, str] = {}
    if loc_codes:
        for wid, code in (
            db.query(Warehouse.id, Warehouse.warehouse_code)
            .filter(func.upper(Warehouse.warehouse_code).in_(list(loc_codes)))
            .all()
        ):
            warehouses[_norm(code)] = str(wid)

    parties = _resolve_parties(db, read, bind)
    party_by_doc: dict[str, str] = {}
    party_code_by_doc: dict[str, str] = {}
    header_by_doc: dict[str, dict] = {}
    agent_by_doc: dict[str, str] = {}

    kept: list[Line] = []
    for l in read.lines:
        row = int(l.row_ref) if (l.row_ref or "").isdigit() else 0
        extra = read.extras.get(str(l.row_ref), {})
        pid = products.get(_norm(l.item_code))
        if not pid:
            # Never auto-create: a typo would become a SKU that gets planned and bought.
            issues.append(ResolutionIssue(row, "item_code", l.item_code,
                                          "no product with this code"))
            continue
        if l.location and _norm(l.location) not in warehouses:
            issues.append(ResolutionIssue(row, "stock_location", l.location,
                                          "no warehouse with this code"))
            continue
        kept.append(l)

        # Who sold it. Read only where the document type HAS an agent, so the purchase book
        # cannot pick one up from a stray column, and normalised through
        # `sales_agent_service.normalize_code` - the ONE authority - so the key this builds is
        # byte-for-byte the key the master is looked up and created under. A second
        # normaliser that merely happened to agree would, the day the two drifted, report
        # every agent as new and create a duplicate master row on every upload.
        if bind.agent_fk:
            agent_code = sales_agent_service.normalize_code(extra.get("agent"))
            if agent_code:
                seen_agent = agent_by_doc.get(l.doc_number)
                if seen_agent is not None and seen_agent != agent_code:
                    # One document is sold by one agent, so a file naming two is a file to
                    # fix. The first row still wins the write, but SAID OUT LOUD - exactly the
                    # counterparty rule below. Silent first-wins would attribute half the
                    # document's demand to a salesperson who never sold it, and where the two
                    # agents carry different demand classes it would also decide the order's
                    # fulfilment priority from whichever row the export happened to list first.
                    issues.append(ResolutionIssue(
                        row, "agent", agent_code,
                        f"{l.doc_number} names two different agent values, "
                        f"{seen_agent} and {agent_code}; the first is being used"))
                agent_by_doc.setdefault(l.doc_number, agent_code)

        # Header-level values the file repeats on every row of the document. First non-empty
        # wins rather than last, so a trailing blank cell cannot erase a stated date.
        if bind.header_cols or bind.header_fill_cols:
            slot = header_by_doc.setdefault(l.doc_number, {})
            for _col, key in bind.header_cols + bind.header_fill_cols:
                if slot.get(key) is None and extra.get(key) is not None:
                    slot[key] = extra.get(key)

        # The counterparty is resolved but NEVER gates the line, unlike the item and the
        # location. A quantity with no product cannot be planned, and a quantity in the wrong
        # warehouse makes every coverage figure for that location wrong - so those rows are
        # dropped. An unknown creditor leaves the quantity and the arrival date perfectly
        # true, and dropping the line would make on-order UNDERSTATE supply, which is what
        # causes a second, unnecessary purchase. So it is reported and the header is left
        # unlinked.
        code = _norm(extra.get("party_code"))
        if bind.party is None:
            # Nothing is LINKED on this path, but the code is not discarded either: the
            # demand class falls back to this customer's market segment, and a code kept
            # only per row is a fallback that can never fire. First non-empty wins, the same
            # rule as the header columns, because the extract repeats it on every row.
            if code:
                party_code_by_doc.setdefault(l.doc_number, code)
            continue
        if not code:
            continue
        pid_party = parties.get(code)
        if pid_party is None:
            issues.append(ResolutionIssue(
                row, bind.party_code, code,
                f"no {bind.party.__name__.lower()} with this code"))
            continue
        seen_code = party_code_by_doc.get(l.doc_number)
        if seen_code is not None and seen_code != code:
            # One document has one counterparty, so a file naming two is a file to fix. The
            # first row still wins the write, but silently: half the document's lines would
            # otherwise be attributed to a company that never sold them, and the supplier
            # scorecard would blame them for a delivery they were never asked to make.
            issues.append(ResolutionIssue(
                row, bind.party_code, code,
                f"{l.doc_number} names two different {bind.party_code} values, "
                f"{seen_code} and {code}; the first is being used"))
            continue
        party_by_doc.setdefault(l.doc_number, pid_party)
        party_code_by_doc.setdefault(l.doc_number, code)

    return _Resolved(lines=kept, issues=issues, product_by_code=products,
                     warehouse_by_code=warehouses, party_by_doc=party_by_doc,
                     party_code_by_doc=party_code_by_doc, header_by_doc=header_by_doc,
                     agent_by_doc=agent_by_doc)


def _existing_lines(db: Session, docs: set[str], bind: _Binding, *,
                    fulfilled_into: Optional[dict[str, float]] = None) -> list[Line]:
    """Current outstanding lines for the documents named in the file, as diff Lines.

    `row_ref` carries the DB line id so apply() can update in place rather than matching
    twice by content.

    `fulfilled_into`, when given, is filled with each returned line's already
    delivered/received quantity. The diff has no place for it (it is deliberately
    document-agnostic and compares OUTSTANDING figures) but the honesty checks need it, and a
    caller that only wants the diff should not have to unpack a pair to get it.
    """
    if not docs:
        return []
    # ORM, so the company-isolation filter applies. See `_resolve`: another company's order
    # carrying the same SO number must never be diffed against this upload, let alone closed
    # by it.
    line, header = bind.line, bind.header
    fulfilled = getattr(line, bind.fulfilled)
    rows = (
        db.query(
            line.id,
            getattr(header, bind.number),
            Product.product_code,
            Warehouse.warehouse_code,
            (line.qty_ordered - fulfilled).label("outstanding"),
            getattr(line, bind.date),
            fulfilled,
        )
        .join(header, header.id == getattr(line, bind.header_fk))
        .join(Product, Product.id == line.product_id)
        .outerjoin(Warehouse, Warehouse.id == line.warehouse_id)
        .filter(
            getattr(header, bind.number).in_(list(docs)),
            # Every status the readers call live, not only the one this import writes.
            header.status.in_(list(bind.live_statuses)),
            # Open lines ONLY. A closed line that comes back arrives as an ADD, which is where
            # apply() reopens it in place. Returning closed lines here instead would make the
            # pair read as `unchanged` AND break idempotency, because a closed line absent
            # from the next upload would be re-closed on every single re-run.
            line.line_status == "open",
            line.qty_ordered > fulfilled,
        )
        .all()
    )
    if fulfilled_into is not None:
        fulfilled_into.update({str(r[0]): float(r[6] or 0) for r in rows})
    return [
        Line(doc_number=r[1], item_code=r[2], location=r[3] or "",
             qty=float(r[4] or 0), required_date=r[5], row_ref=str(r[0]))
        for r in rows
    ]


def _header_state(db: Session, docs: tuple[str, ...],
                  bind: _Binding) -> dict[str, tuple[str, Optional[str]]]:
    """Each in-scope document's current (status, counterparty id), for the headers that exist.

    ORM for the same isolation reason as every other lookup here.
    """
    if not docs:
        return {}
    rows = (
        db.query(getattr(bind.header, bind.number), bind.header.status,
                 getattr(bind.header, bind.party_fk))
        .filter(getattr(bind.header, bind.number).in_(list(docs)))
        .all()
    )
    return {r[0]: (r[1], str(r[2]) if r[2] else None) for r in rows}


def _segment_of(db: Session, debtor_code: str) -> Optional[str]:
    """This customer's market segment code, or None when there is no customer to read.

    Split from `_demand_class_for` so the caller can tell "no such customer" and "customer
    with no segment" (both None, both nothing to go on) from "a segment that says retail".
    Since the amendment of 4 Aug 2026 the segment is the FALLBACK, not the source of truth:
    it is NULL on 3,276 of 3,284 customers, so an answer from it is a bonus rather than the
    rule, and treating its silence as "retail" is exactly the invisible mis-prioritisation
    the report path exists to prevent.
    """
    if not debtor_code:
        return None
    # ORM again: customers are company-scoped too, and reading another company's customer
    # would decide this order's fulfilment priority from the wrong row.
    return (
        db.query(func.lower(func.coalesce(Customer.market_segment_code, "")))
        .filter(func.upper(Customer.customer_code) == _norm(debtor_code))
        .limit(1)
        .scalar()
    )


def _demand_class_for(db: Session, debtor_code: str) -> str:
    """The class this customer's market segment implies, defaulting when it implies none.

    The never-None facade: a caller holding this answer alone has to write something, and
    for a customer nothing is known about the safe write is the default. The import path
    does NOT use it - it needs to tell "no answer" apart from "retail" so it can report the
    document instead of guessing - but the vocabulary is the same one, `_class_of`.
    """
    return _class_of(_segment_of(db, debtor_code)) or DEFAULT_DEMAND_CLASS


def _demand_state(db: Session, docs: tuple[str, ...],
                  bind: _Binding) -> dict[str, tuple[Optional[str], Optional[str]]]:
    """Each existing in-scope document's (stated split, current classification).

    ORM for the same isolation reason as every other lookup here: another company's order
    carrying this SO number must not decide this one's fulfilment priority.
    """
    if bind.demand_class_col is None or bind.demand_split_col is None or not docs:
        return {}
    rows = (
        db.query(getattr(bind.header, bind.number),
                 getattr(bind.header, bind.demand_split_col),
                 getattr(bind.header, bind.demand_class_col))
        .filter(getattr(bind.header, bind.number).in_(list(docs)))
        .all()
    )
    return {r[0]: (r[1], r[2]) for r in rows}


def _agent_state(db: Session, resolved: _Resolved,
                 bind: _Binding) -> tuple[dict[str, Optional[str]], list[AgentNotice]]:
    """Every agent code this file names: the class it carries, and what needs saying about it.

    A read, never a write: `preview` runs this too and must create nothing, so an unknown code
    is REPORTED here and created by `apply` (which is also the only place that should be
    inventing master data).

    Two kinds of notice, told apart because the answers differ. A code nobody holds is new
    master data the client has just acquired without asking for it, and it wants a class. A
    code held with a NULL class is one of the 38 he already has and has not got to yet - which
    is the state every one of them ships in, since the I/III/IV suffix maps to neither company
    nor market segment anywhere in this database and guessing it would silently mis-prioritise
    real orders (UAC AC-3.3). An agent that HAS a class produces no notice at all: a list that
    names all 38 every week is a list nobody reads.
    """
    if not bind.agent_fk:
        return {}, []
    codes = sorted(set(resolved.agent_by_doc.values()))
    if not codes:
        return {}, []
    held = sales_agent_service.resolve_many(db, codes)
    classes: dict[str, Optional[str]] = {}
    notices: list[AgentNotice] = []
    for code in codes:
        agent = held.get(code)
        if agent is None:
            notices.append(AgentNotice(
                code, True,
                "new agent, unclassified: this upload is the first thing to name this agent "
                "code, so the master row is being created with no demand class"))
            continue
        classes[code] = agent.demand_class
        if not agent.demand_class:
            notices.append(AgentNotice(
                code, False,
                "this agent carries no demand class, so it cannot classify an order that "
                "states nothing else"))
    return classes, notices


def _classify_demand(db: Session, diff: Diff, resolved: _Resolved,
                     state: dict[str, tuple[Optional[str], Optional[str]]],
                     bind: _Binding,
                     agent_classes: dict[str, Optional[str]]) -> tuple[dict[str, str],
                                                                       list[RowProblem]]:
    """What each in-scope document's demand class should be, and what could not be decided.

    Per DOCUMENT, in order: the order type the header already carries, then the one the file
    states (which is also the value that fills an absent header), then the customer's market
    segment via the debtor code the file names, and last the demand class held against the
    agent who sold it. When none of the four answers, the document is REPORTED and left
    exactly as it was.

    The agent is LAST on purpose. An agent who mostly sells project work will still sell the
    occasional trade order, so their class is a tendency about the seller while the three
    ahead of it are statements about this order and this buyer. Reading it earlier would
    overwrite a fact with a tendency.

    Defaulting to retail is the failure this column exists to avoid: it under-prioritises a
    project order invisibly, and the wrong answer is stable, so no later upload surfaces it
    either. The symptom is a project that simply stops winning stock.

    Computed here rather than inside `apply` so preview and the commit report the same thing,
    which is the rule the rest of this module already follows.

    Reported as a `RowProblem` rather than a `ResolutionIssue`: the issue list means "a code
    in this file names nothing we hold", and this is the opposite complaint - the file states
    nothing to resolve. Both lists are put in front of the same person on the same screen.
    """
    if bind.demand_class_col is None:
        return {}, []

    # The row a document is reported against. The report is per DOCUMENT and both lists are
    # per row, so it is pinned to the first row that named it: a row number the operator can
    # actually find in the file beats a 0 that points at nothing.
    first_row: dict[str, int] = {}
    for l in resolved.lines:
        if l.doc_number not in first_row:
            first_row[l.doc_number] = int(l.row_ref) if (l.row_ref or "").isdigit() else 0

    out: dict[str, str] = {}
    problems: list[RowProblem] = []
    for number in diff.scope_documents:
        stored_split, current = state.get(number, (None, None))
        stated_split = resolved.header_by_doc.get(number, {}).get("order_type")
        agent_code = resolved.agent_by_doc.get(number, "")
        cls = (_class_of(stored_split) or _class_of(stated_split)
               or _class_of(_segment_of(db, resolved.party_code_by_doc.get(number, "")))
               # Taken as stored, NOT through `_class_of`: the column holds a class already,
               # constrained to the vocabulary, so passing it through the segment matcher
               # would turn a value that somehow escaped the constraint into `retail` - a
               # guess, in the one place this module refuses to guess.
               or agent_classes.get(agent_code))
        if cls is not None:
            out[number] = cls
            continue
        if current:
            # Already classified, and this upload knows nothing better. Never downgraded:
            # a project quietly demoted to retail mid-fulfilment shows up only as an order
            # that stopped winning stock, weeks later, with nothing to point at.
            continue
        # Named specifically, because the four sources have four different fixes: an order
        # type on the header, an order type in the export, a market segment on the customer,
        # or a demand class on the agent. "Unclassified" alone tells the operator nothing
        # about which one to go and set.
        agent_says = (f"agent {agent_code} carries no demand class" if agent_code
                      else "it names no agent")
        problems.append(RowProblem(
            first_row.get(number, 0),
            f"{number} states no order type, its debtor code resolves to no customer "
            f"market segment, and {agent_says}, so its fulfilment priority is left "
            f"unclassified rather than defaulted to {DEFAULT_DEMAND_CLASS}",
            value=number))
    return out, problems


def _honesty_issues(diff: Diff, fulfilled_by_line: dict[str, float],
                    header_state: dict[str, tuple[str, Optional[str]]],
                    resolved: _Resolved, bind: _Binding) -> list[ResolutionIssue]:
    """What the file says that a person has to see before it is believed.

    Computed from the diff alone so preview and apply report the SAME thing: a preview that
    does not mention a side effect the commit performs is a preview that lies.
    """
    out: list[ResolutionIssue] = []

    for c in diff.of_kind(QTY_CHANGED, DATE_AND_QTY_CHANGED):
        if c.before is None or c.after is None:
            continue
        fulfilled = fulfilled_by_line.get(str(c.before.row_ref))
        if fulfilled is None:
            continue
        ordered = c.before.qty + fulfilled
        # The extract states what is OUTSTANDING, so ordered becomes received plus outstanding.
        # Right for a fresh file; a file taken BEFORE the goods receipt inflates the order by
        # exactly what has already arrived. The two are indistinguishable from the file alone,
        # so the write still happens and the question is asked rather than guessed at.
        if fulfilled <= 0 or (fulfilled + c.after.qty) <= ordered + _QTY_EPSILON:
            continue
        row = int(c.after.row_ref) if (c.after.row_ref or "").isdigit() else 0
        out.append(ResolutionIssue(
            row, "qty_ordered", str(c.after.qty),
            f"{c.doc_number} / {c.item_code} already has {fulfilled:g} received, so this "
            f"raises the order from {ordered:g} to {fulfilled + c.after.qty:g}; either the "
            f"order grew or this extract predates the receipt"))

    for number in diff.scope_documents:
        _status, current_party = header_state.get(number, (None, None))
        party_id = resolved.party_by_doc.get(number)
        code = resolved.party_code_by_doc.get(number)
        if party_id and current_party and current_party != str(party_id):
            # The file is the system of record for who we bought from: chasing the wrong
            # supplier is the failure mode. Overwritten, and said out loud.
            out.append(ResolutionIssue(
                0, bind.party_code, code or "",
                f"the {bind.party_code} on {number} disagrees with the file and is being "
                f"changed to {code}"))

    return out


def _to_activate(diff: Diff, header_state: dict[str, tuple[str, Optional[str]]],
                 bind: _Binding) -> list[str]:
    """In-scope documents whose header is not live and therefore has to be lifted.

    An outstanding-orders extract is a book of documents already placed, and AutoCount is the
    system of record for that, so a document it names is by definition no longer a draft.
    Leaving it as one imports the lines and then hides them: `scm.on_order_v` ignores drafts
    (M4-D5), so on-order stays 0 while the response still reports `added: N` - a silent no-op
    reporting success. Reported rather than merely done, because changing a document's status
    crosses a decision boundary a person should see.
    """
    return [
        number for number in diff.scope_documents
        if (state := header_state.get(number)) is not None
        and state[0] not in bind.live_statuses
    ]


def _samples(diff: Diff, limit: int = 8) -> dict:
    """A few real rows per change kind, so the confirm screen shows evidence not just counts."""
    out: dict = {}
    for c in diff.changes:
        if c.kind == "unchanged":
            continue
        bucket = out.setdefault(c.kind, [])
        if len(bucket) >= limit:
            continue
        bucket.append({
            "doc_number": c.doc_number,
            "item_code": c.item_code,
            "location": c.location,
            "qty_before": c.before.qty if c.before else None,
            "qty_after": c.after.qty if c.after else None,
            "date_before": c.before.required_date.isoformat()
                           if c.before and c.before.required_date else None,
            "date_after": c.after.required_date.isoformat()
                          if c.after and c.after.required_date else None,
            "days_moved": c.days_moved,
            "label": (c.after or c.before).label,
        })
    return out


@dataclass
class _Plan:
    """Everything both entry points need, built once so they cannot disagree."""

    read: ReadResult
    resolved: Optional[_Resolved] = None
    diff: Optional[Diff] = None
    issues: list[ResolutionIssue] = field(default_factory=list)
    # Documents that would be (preview) or were (apply) lifted to the live write status.
    activate: list[str] = field(default_factory=list)
    # Document number -> the demand class this upload could decide. A document absent from
    # this map is one nothing could classify, and it is reported rather than defaulted.
    demand: dict[str, str] = field(default_factory=dict)
    # Row-scoped complaints this module raises on top of the reader's own, so both entry
    # points hand the operator ONE list of rows to look at.
    problems: list[RowProblem] = field(default_factory=list)
    # Agent codes in the file that can classify nothing yet. Master-data gaps, not row
    # failures, so they travel separately.
    agent_notices: list[AgentNotice] = field(default_factory=list)


def _build(db: Session, file_data: bytes, doc_type: str) -> _Plan:
    bind = _binding(doc_type)
    resolver = AliasResolver.for_doc_type(db, doc_type)
    read = read_workbook(file_data, doc_type, resolver)
    if not read.ok:
        return _Plan(read=read)
    resolved = _resolve(db, read, bind)
    fulfilled: dict[str, float] = {}
    existing = _existing_lines(db, {l.doc_number for l in resolved.lines}, bind,
                               fulfilled_into=fulfilled)
    diff = diff_lines(existing, resolved.lines)
    header_state = _header_state(db, diff.scope_documents, bind)
    agent_classes, agent_notices = _agent_state(db, resolved, bind)
    demand, demand_problems = _classify_demand(
        db, diff, resolved, _demand_state(db, diff.scope_documents, bind), bind,
        agent_classes)
    return _Plan(
        read=read,
        resolved=resolved,
        diff=diff,
        issues=resolved.issues + _honesty_issues(diff, fulfilled, header_state,
                                                 resolved, bind),
        activate=_to_activate(diff, header_state, bind),
        demand=demand,
        problems=demand_problems,
        agent_notices=agent_notices,
    )


def _affected_product_ids(plan: _Plan) -> list[str]:
    """Products whose position this restatement could move.

    Only the ones that actually CHANGED: an unchanged line cannot make the plan disagree
    with anything, and snapshotting the whole book on every upload would cost the dated
    engine a run over thousands of products to find the handful that moved.
    """
    if plan.diff is None or plan.resolved is None:
        return []
    changed_codes = {
        c.item_code for c in plan.diff.changes if c.kind != UNCHANGED
    }
    # `product_by_code` is keyed by the NORMALISED code, so normalise on lookup: the diff
    # carries the code as the file spelled it, and a case difference would silently drop the
    # product from the batch rather than fail.
    by_code = plan.resolved.product_by_code
    return sorted(
        {str(by_code[_norm(code)]) for code in changed_codes if by_code.get(_norm(code))}
    )


def preview(db: Session, file_data: bytes, doc_type: str = SO) -> PreviewResult:
    """What this upload would change. Writes nothing."""
    plan = _build(db, file_data, doc_type)
    read, diff = plan.read, plan.diff
    if diff is None:
        return PreviewResult(
            doc_type=doc_type, scope_documents=(), counts={}, total_rows=read.total_rows,
            unmapped_headers=read.unmapped_headers, missing_columns=read.missing_columns,
            row_problems=read.problems,
        )
    return PreviewResult(
        doc_type=doc_type,
        scope_documents=diff.scope_documents,
        counts=diff.counts,
        total_rows=read.total_rows,
        unmapped_headers=read.unmapped_headers,
        missing_columns=read.missing_columns,
        row_problems=read.problems + plan.problems,
        resolution_issues=plan.issues,
        samples=_samples(diff),
        activated_documents=plan.activate,
        unmapped_agents=plan.agent_notices,
    )


def _closed_line(db: Session, bind: _Binding, header_id: str, product_id: Optional[str],
                 warehouse_id: Optional[str], when: Optional[date]):
    """A closed line on this document matching the incoming row exactly, if there is one.

    An explicit lookup rather than widening `_existing_lines`: the diff must stay open-only,
    or a closed line simply absent from the next upload would be re-closed on every re-run
    and `applied.closed` would never settle at 0.
    """
    if product_id is None:
        return None
    line = bind.line
    q = (
        db.query(line)
        .filter(getattr(line, bind.header_fk) == header_id,
                line.product_id == product_id,
                line.line_status == "closed")
    )
    q = q.filter(line.warehouse_id.is_(None) if warehouse_id is None
                 else line.warehouse_id == warehouse_id)
    dated = getattr(line, bind.date)
    q = q.filter(dated.is_(None) if when is None else dated == when)
    return q.order_by(line.created_at).first()


def _refresh_money(line, extra: dict, bind: _Binding) -> None:
    """Bring the line's money columns up to what this extract says.

    Applied on update, not on insert only: cost is what the cash co-pilot ranks and budgets
    on, so a line frozen at the first extract's price is ranked on last week's money, and a
    line that arrived with the column blank and was priced later would stay blank for ever -
    ranked as if it were free. A value the file does NOT state leaves the column alone rather
    than blanking a cost we already know.
    """
    for col, key in bind.money_cols:
        value = extra.get(key)
        if value is not None:
            setattr(line, col, value)


def apply(db: Session, file_data: bytes, doc_type: str = SO,
          actor: Optional[str] = None) -> dict:
    """Write the upload. Returns the same counts the preview showed.

    Closing is `line_status = 'closed'`, not a delete. The line existed and was planned
    against; erasing it would make last week's plan unexplainable, and `scm.committed_v`
    already excludes non-open lines (migration 311).
    """
    plan = _build(db, file_data, doc_type)
    read, resolved, diff = plan.read, plan.resolved, plan.diff
    if diff is None or resolved is None:
        return {"ok": False, "missing_columns": read.missing_columns, "counts": {}}

    # The BEFORE half of every Plan Exception (AC-D4), taken while the old position is still
    # the one in the database. Reconstructing it afterwards by inverting the deltas would be
    # a second implementation of netting whose only job is to agree with the first, and the
    # day it stopped agreeing the before-column would be a number nobody could reproduce.
    #
    # Best-effort like the generation below, and for the same reason: the upload is the
    # operation the user asked for. A defect in the exception path must not send them back to
    # re-upload a book that would otherwise have gone in - it must cost them the batch, which
    # the next upload produces again.
    exception_pids = _affected_product_ids(plan) if doc_type == SO else []
    before_positions: dict = {}
    if exception_pids:
        try:
            before_positions = plan_exception_service.snapshot(db, exception_pids)
        except Exception:  # pragma: no cover - defensive, see above
            logger.exception("plan exception BEFORE snapshot failed; skipping the batch")
            exception_pids = []

    bind = _binding(doc_type)
    lift = set(plan.activate)

    # The salesperson master, created where this file names a code nobody holds (AC-6.4).
    # Resolved once per CODE rather than per document: one agent sells many orders, and
    # creating inside the header loop would issue the same lookup for each of them.
    # Deliberately before the loop and never inside `preview`, which writes nothing.
    agent_ids: dict[str, str] = {}
    if bind.agent_fk:
        for code in sorted(set(resolved.agent_by_doc.values())):
            agent = sales_agent_service.resolve_or_create(db, code)
            if agent is not None:
                agent_ids[code] = agent.id

    # Header per document in scope, created if absent. `write_status` differs per type: an
    # outstanding-PO extract is a book of orders already PLACED, and `scm.on_order_v`
    # deliberately ignores drafts, so writing them as drafts would import supply and hide it.
    order_ids: dict[str, str] = {}
    activated: list[str] = []
    #: Documents another feed created that this extract has taken ownership of. Reported so
    #: the handover is visible rather than a silent change of who may edit what.
    adopted: list[str] = []
    for number in diff.scope_documents:
        header = (
            db.query(bind.header)
            .filter(getattr(bind.header, bind.number) == number)
            .one_or_none()
        )
        if header is None:
            header = bind.header(**{
                bind.number: number,
                "status": bind.write_status,
                "source_system": "scm_upload",
                "source_ref": doc_type,
            })
            db.add(header)
            db.flush()
        else:
            if number in lift:
                # The extract is evidence the document has been placed, and AutoCount is the
                # system of record for that. Left as a draft the lines land and the supply is
                # invisible, while the response still reports them as added.
                header.status = bind.write_status
                activated.append(number)
            # ADOPTION. A document another feed created - the Order Inquiry sheet is the one
            # that does this - is taken over here, because this extract is a statement of the
            # WHOLE open book and that sheet is one person's working record. Without the
            # handover the sheet keeps ownership, and its next upload reverts a quantity CS
            # just corrected. Only a foreign source is claimed: re-uploading this extract
            # must not churn the rows it already owns.
            if (header.source_system or "") not in ("", "scm_upload"):
                header.source_system = "scm_upload"
                header.source_ref = doc_type
                adopted.append(number)
        # Header-level values the file states (PO DATE, currency). Written whenever the file
        # supplies one: `scm.receipt_lead_v` measures lead days from `issue_date`, so
        # discarding it costs the module every lead-time observation it could have had.
        for col, key in bind.header_cols:
            value = resolved.header_by_doc.get(number, {}).get(key)
            if value is not None:
                setattr(header, col, value)
        # Columns the file FILLS rather than restates. The sales book's order type is the
        # case: for a document this upload creates the file is the only evidence there is,
        # while a value already on the header was set by a person and a weekly re-upload
        # silently overwriting it is the failure.
        for col, key in bind.header_fill_cols:
            value = resolved.header_by_doc.get(number, {}).get(key)
            if value is not None and not getattr(header, col, None):
                setattr(header, col, value)
        # Who sold it. Written whenever the file names an agent we could resolve or create,
        # because the extract is the record of that and a re-upload restating the same code
        # is a no-op. An absent code never clears an existing link: a file that simply left
        # the column blank is not evidence that the order changed hands.
        if bind.agent_fk:
            agent_id = agent_ids.get(resolved.agent_by_doc.get(number, ""))
            if agent_id:
                setattr(header, bind.agent_fk, agent_id)
        # What the fulfilment policy actually weighs, stamped from the split above.
        # Written ONLY when this upload could decide it: a document nothing classified keeps
        # whatever it already had and is reported by name instead (`_classify_demand`).
        cls = plan.demand.get(number)
        if cls and bind.demand_class_col:
            setattr(header, bind.demand_class_col, cls)
        # Attach the counterparty when the file named one we could resolve. A missing code
        # never overwrites a present link; a code that CONTRADICTS it does, because the file
        # is the system of record for who we bought from and chasing the wrong supplier is
        # the failure mode. Both halves are reported by `_honesty_issues`.
        party_id = resolved.party_by_doc.get(number)
        if party_id and str(getattr(header, bind.party_fk, None) or "") != str(party_id):
            setattr(header, bind.party_fk, party_id)
        order_ids[number] = header.id

    applied = {"added": 0, "updated": 0, "closed": 0, "unchanged": 0}
    for c in diff.changes:
        if c.kind == CLOSED:
            line = db.query(bind.line).filter(bind.line.id == c.before.row_ref).one_or_none()
            if line is not None:
                # A status change, never a delete, and never a fabricated receipt: the line
                # was planned against, and inventing a receipt no GRN supports would corrupt
                # lead-time measurement and the picking reconciliation.
                line.line_status = "closed"
                applied["closed"] += 1
            continue

        if c.kind == ADDED:
            extra = read.extras.get(str(c.after.row_ref), {})
            product_id = resolved.product_by_code.get(_norm(c.item_code))
            warehouse_id = (resolved.warehouse_by_code.get(_norm(c.location))
                            if c.location else None)
            # A line that comes back is the SAME line, and the receipt already booked against
            # it belongs to it. Inserting a second row would leave that receipt stranded on
            # the old one while the new row starts at zero received, so the two together claim
            # the full ordered quantity is still at sea - overstated for good, and stable, so
            # re-uploading never corrects it.
            revived = _closed_line(db, bind, order_ids[c.doc_number], product_id,
                                   warehouse_id, c.after.required_date)
            if revived is not None:
                already = float(getattr(revived, bind.fulfilled) or 0)
                revived.line_status = "open"
                revived.qty_ordered = already + c.after.qty
                setattr(revived, bind.date, c.after.required_date)
                _refresh_money(revived, extra, bind)
                applied["added"] += 1
                continue
            fields = {
                bind.header_fk: order_ids[c.doc_number],
                "product_id": product_id,
                "warehouse_id": warehouse_id,
                "qty_ordered": c.after.qty,
                bind.fulfilled: 0,
                bind.date: c.after.required_date,
                "line_status": "open",
            }
            for col, key in bind.money_cols:
                fields[col] = extra.get(key)
            db.add(bind.line(**fields))
            applied["added"] += 1
            continue

        if c.kind == "unchanged":
            applied["unchanged"] += 1
            continue

        # qty and/or date changed: update the row the diff paired, in place.
        line = db.query(bind.line).filter(bind.line.id == c.before.row_ref).one_or_none()
        if line is None:
            continue
        # The extract states what is OUTSTANDING, so ordered is outstanding plus whatever has
        # already been delivered or received. Writing the figure straight in would erase a
        # booked receipt and leave the goods counted as still at sea.
        already = float(getattr(line, bind.fulfilled) or 0)
        line.qty_ordered = already + c.after.qty
        setattr(line, bind.date, c.after.required_date)
        _refresh_money(line, read.extras.get(str(c.after.row_ref), {}), bind)
        applied["updated"] += 1

    db.flush()

    # AC-D2a: exceptions are a BATCH produced on confirmation, not ad-hoc signals arriving
    # one at a time. Best-effort, because the upload itself has already succeeded: a failure
    # to diff the plan must not fail the write and send the operator back to re-upload a book
    # that is already in.
    exception_batch_id = None
    if exception_pids:
        try:
            after_positions = plan_exception_service.snapshot(db, exception_pids)
            # The batch belongs to the PLAN it contradicts. Without this the exception
            # screen - which is a view OF a run - filters by a run id no batch carries and
            # shows nothing for ever, while the rows sit in the table.
            current = reorder_run_service.today_or_latest_run(db)
            # A run still being built contradicts nothing yet, so the batch would hang off a
            # plan that has no rows to disagree with. Only a completed plan can be contradicted.
            if current and current["row"].get("status") != "completed":
                current = None
            batch = plan_exception_service.generate_batch(
                db,
                run_id=str(current["row"]["id"]) if current else None,
                before=before_positions,
                after=after_positions,
                # The upload's OWN count of changed lines, carried through unchanged so the
                # screen can reconcile deltas against exceptions (AC-D2b).
                delta_count=sum(
                    n for kind, n in diff.counts.items() if kind != "unchanged"
                ),
                source_documents=list(diff.scope_documents),
                actor=actor,
            )
            exception_batch_id = str(batch.id)
        except Exception:  # pragma: no cover - defensive, see above
            logger.exception("plan exception batch failed for a confirmed SO upload")

    return {
        "ok": True,
        "exception_batch_id": exception_batch_id,
        "counts": diff.counts,
        "applied": applied,
        "scope_documents": list(diff.scope_documents),
        "activated_documents": activated,
        "adopted_documents": adopted,
        "resolution_issues": [asdict(i) for i in plan.issues],
        "row_problems": [asdict(p) for p in read.problems + plan.problems],
        # Reported by the commit as well as by the preview, and stated as it was BEFORE the
        # creation above: "new agent, unclassified" is exactly the fact the operator needs
        # after the fact, and re-reading the master here would report every one of them as
        # merely unclassified, losing which ones this upload invented.
        "unmapped_agents": [asdict(a) for a in plan.agent_notices],
    }
