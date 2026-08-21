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
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Callable, Optional

import sqlalchemy as sa
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.order import Customer, SalesOrder, SalesOrderLine
from app.models.procurement import PurchaseOrder, PurchaseOrderLine, Supplier
from app.models.inventory import Warehouse
from app.models.product import Product
from app.services import import_outcome_codes as oc
from app.services.import_outcome import ImportOutcome
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
from app.services.scm.history_sources import HISTORY_SOURCE_SYSTEMS
from app.services.scm.demand_class import DEFAULT_DEMAND_CLASS
from app.services.scm.demand_class import class_of as _class_of
from app.services.scm.customer_label import normalize_debtor_code
from app.services.scm.outstanding_reader import PO, SO, ReadResult, RowProblem, read_workbook

logger = logging.getLogger(__name__)

# Demand class drives fulfilment priority: `scm.priority_policy.demand_class_weights` is
# keyed on it. A stated split that is not recognisably a project is retail, because that is
# the only other class the seeded weights carry and a new word would score as nothing.
# A split nobody states is NOT retail - see `_class_of`, imported above.

# A quantity difference below this is noise between two exports, not a decision. Same figure
# the diff uses, for the same reason.
_QTY_EPSILON = 0.0005

# How many back-created supplier codes the job report names outright before it switches to
# "... and N more". `suppliers_created` (the count) is never capped - only the list an
# operator would actually read is, the same trade `_samples` makes for diff evidence.
_CREATED_SUPPLIERS_LISTED = 20

# A trailing "(RMB)" / "（RMB)" style currency note AutoCount appends to a creditor NAME,
# never part of the legal name. Anchored to the END of the string so a genuine parenthesised
# token earlier in the name ("XYZ TRADING (M) SDN BHD") is never touched, and written to
# accept EITHER paren style on EITHER side ("（RMB)" - the captain's real file mismatches
# them) because NFKC header folding does not touch cell VALUES, only header text.
_CURRENCY_SUFFIX_RE = re.compile(r"[\(（]\s*[A-Za-z]{2,4}\s*[\)）]\s*$")

# `suppliers.supplier_code` is String(50) (see the model); a slug longer than this is
# truncated to leave room for the `-2`/`-3` disambiguator below.
_SUPPLIER_SLUG_MAX = 50


def _clean_supplier_name(raw: Optional[str]) -> str:
    """The legal supplier name, with AutoCount's trailing currency note stripped.

    The supplier master holds `XIAMEN TAIYANG TECHNOLOGY CO.,LTD`, never `... (RMB)` - the
    suffix is the export's own currency notation, not part of the name - so matching or
    back-creating on the raw cell would either miss an existing supplier or create a
    duplicate per currency the client happens to buy that item in.
    """
    if not raw:
        return ""
    return _CURRENCY_SUFFIX_RE.sub("", str(raw).strip()).strip()


def _supplier_slug(db: Session, bind: _Binding, name: str) -> str:
    """A deterministic `supplier_code` for a creditor the file names but gives no code for.

    Upper-cased alphanumerics only - punctuation and spaces dropped rather than kept, so
    `XIAMEN TAIYANG TECHNOLOGY CO.,LTD` becomes `XIAMENTAIYANGTECHNOLOGYCOLTD` - truncated to
    fit the column. A code already held in this company (another supplier whose name
    happens to slug the same way; by construction this is never the SAME name, since a
    matching existing name would have resolved before creation was ever considered) gets a
    numeric `-2`, `-3`, ... suffix rather than colliding on the unique constraint.
    """
    base = re.sub(r"[^A-Z0-9]", "", name.upper()) or "SUPPLIER"
    code_col = getattr(bind.party, bind.party_code_col)
    candidate = base[:_SUPPLIER_SLUG_MAX]
    suffix = 1
    while db.query(bind.party.id).filter(func.upper(code_col) == candidate).first() is not None:
        suffix += 1
        tail = f"-{suffix}"
        candidate = base[: max(_SUPPLIER_SLUG_MAX - len(tail), 0)] + tail
    return candidate


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
    # Line columns fed from the file's money columns, when it has any.
    money_cols: tuple[tuple[str, str], ...] = ()
    # Header columns fed from the file, per document. Same (column, extras key) shape.
    header_cols: tuple[tuple[str, str], ...] = ()
    # Header columns the file FILLS rather than restates: written only where the header
    # holds nothing. Separate from `header_cols` because the two answer different questions.
    # `header_cols` is for figures the file is the system of record for (the PO date), so a
    # later extract corrects them; these are for a value a person may have set by hand, where
    # a weekly re-upload silently overwriting it is the failure.
    header_fill_cols: tuple[tuple[str, str], ...] = ()
    # The header column the counterparty CODE itself is kept in, when the header has one.
    # Its presence changes what an unresolvable code MEANS: the code is not lost, so the
    # order stays attributable ("Debtor 300-R009") and there is nothing to report. Absent
    # (the PO side), an unresolvable code leaves the document unlinked with no trace, which
    # is a resolution issue the operator has to see.
    party_code_header_col: Optional[str] = None
    # Whether an unresolved counterparty code gets a MINIMAL master row created for it
    # rather than only reported. Purchase-order creditor codes only (AC below): 2,177 of
    # 5,243 PO-book documents in the captain's own file carried a creditor code the
    # supplier master had never seen, so every one of them landed with no supplier at
    # all. The sales side keeps the code on the header instead (`party_code_header_col`)
    # and stays exactly as it was - a debtor code with no customer row still names a
    # market segment fallback there, which a back-created customer with no segment
    # would only make WORSE.
    party_back_create: bool = False
    # The counterparty model's own "name" column, read only when `party_back_create` is
    # set - the file's label column (`SUPPLIER` on the PO export) becomes this row's
    # name, so the created supplier is not just a bare code on the expediting list.
    party_name_col: Optional[str] = None
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
        # The customer IS linked now, exactly as the PO side links its supplier. It used to
        # be deliberately skipped because nothing read `sales_orders.customer_id` from this
        # channel; the plan's demand and trend popovers now name who ordered every line, and
        # 2,546 of the 2,548 orders this feed created had no customer at all - so every one
        # of them read "Unnamed customer" while the debtor code was sitting in the file.
        party=Customer, party_code_col="customer_code",
        # ... and the code itself is kept on the header whether or not it resolves, so an
        # order this feed cannot link is still attributable and still fixable later.
        party_code_header_col="debtor_code",
        # `scm.committed_v` counts exactly one sales-order status, so writing and reading are
        # the same value here.
        write_status="open", live_statuses=("open",),
        # What the customer pays. The extract has stated it since migration 338 seeded the
        # `UNIT PRICE` alias, and nothing on this channel wrote it - so the demand popover,
        # whose whole job is "who ordered it and at what price", quoted a blank on every real
        # row. Same shape and same rule as the PO side's cost: an absent price stays NULL
        # rather than becoming a 0 that reads as goods given away.
        money_cols=(("unit_price", "unit_price"),),
        # OPTIONAL in the file and FILL-only on the header: no export carries an order type
        # today, so this is the column that lets a differently-worded export classify its own
        # documents the day it does, without a release. A value already on the header wins,
        # because that is what a person set and the extract is not the record of it.
        #
        # `order_date` is FILL-only for a different reason: the extract states the SO date
        # and the header had none (the trend reads `order_date` over 24 months, so an order
        # imported without one carries open demand and no history at all - "No order
        # history" beside 51 open units). It fills the gap; an existing date, wherever it
        # came from, stands.
        header_fill_cols=(("order_type", "order_type"), ("order_date", "order_date")),
        demand_class_col="demand_class", demand_split_col="order_type",
        agent_fk="sales_agent_id",
    ),
    PO: _Binding(
        header=PurchaseOrder, line=PurchaseOrderLine,
        number="po_number", header_fk="purchase_order_id",
        date="expected_date", fulfilled="qty_received",
        party_fk="supplier_id", party_code="creditor_code",
        party=Supplier, party_code_col="supplier_code",
        party_back_create=True, party_name_col="supplier_name",
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
    # Additive safety notices that do not map to a single row or document - today, only
    # "N rows carry a date the reader could not read". The operator reads `row_problems`
    # for WHICH rows; this is the one-line summary that says the write will leave those
    # rows' dates exactly as they already are, rather than the operator having to infer
    # that from the per-row reasons.
    warnings: list[str] = field(default_factory=list)

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
            "warnings": self.warnings,
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
    # Every counterparty code (normalised) this file names that no master row matched,
    # mapped to the file's own label for it - read only where `_Binding.party_back_create`
    # is set. `apply()` creates one row per key here; `preview()` never does, matching
    # every other creation this module performs. A code the file never labels (the
    # column is missing, or blank on every row) falls back to the code itself.
    party_label_by_code: dict = field(default_factory=dict)
    # The SAME codes, first-seen exactly as the file printed them (case, punctuation) -
    # what the created row's code column is stamped with. Matching stays on the
    # normalised key; display stays on what the operator's own file said.
    party_raw_code_by_code: dict = field(default_factory=dict)
    # PO-book fallback, read only where `_Binding.party_back_create` is set: which
    # document belongs to which CLEANED counterparty name, for a file that names the
    # creditor but carries no code column at all (`party_code` blank on every row). A
    # separate map from the code ones above rather than a shared key space, because a
    # slug is generated, not read off the file, and the two must never collide with a
    # genuine code creating (or matching) the wrong row.
    party_name_key_by_doc: dict = field(default_factory=dict)
    # Normalised name key -> the CLEANED name itself (display form, currency suffix
    # already stripped). `apply()` creates one supplier per key here, exactly as the code
    # map does for `party_raw_code_by_code`.
    party_cleaned_name_by_key: dict = field(default_factory=dict)
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


def _resolve_parties_by_name(db: Session, read: ReadResult, bind: _Binding) -> dict[str, str]:
    """Cleaned counterparty NAME -> id, within the active company.

    PO-book fallback only (`bind.party_back_create`): read only for rows that state no
    `party_code` at all, since a row that DOES carry a code is resolved by
    `_resolve_parties` and this map is never consulted for it. Matched case-insensitively
    on the cleaned name - the master holds `XIAMEN TAIYANG TECHNOLOGY CO.,LTD`, the file
    says `XIAMEN TAIYANG TECHNOLOGY CO.,LTD (RMB)` - so the raw cell would never match.

    `supplier_name` carries no uniqueness constraint (unlike `supplier_code`), so more
    than one supplier can legitimately share a name - ordered by id so the dict
    comprehension's last-write-wins lands on the same row every time, rather than
    whatever order Postgres happened to return.
    """
    if bind.party is None or not bind.party_back_create or bind.party_name_col is None:
        return {}
    names = {
        _norm(cleaned)
        for x in read.extras.values()
        if not x.get("party_code") and (cleaned := _clean_supplier_name(x.get("party_name")))
    }
    if not names:
        return {}
    name_col = getattr(bind.party, bind.party_name_col)
    return {
        _norm(name): str(pid)
        for pid, name in (
            db.query(bind.party.id, name_col)
            .filter(func.upper(name_col).in_(list(names)))
            .order_by(bind.party.id.desc())
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
    names_by_key = _resolve_parties_by_name(db, read, bind)
    party_by_doc: dict[str, str] = {}
    party_code_by_doc: dict[str, str] = {}
    party_label_by_code: dict[str, str] = {}
    party_raw_code_by_code: dict[str, str] = {}
    party_name_key_by_doc: dict[str, str] = {}
    party_cleaned_name_by_key: dict[str, str] = {}
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
            # PO-book fallback: the file names a creditor but states no CODE at all - the
            # shape of the captain's real "PO & SPO outstanding.xlsx" export. Only where
            # `party_back_create` is set, matching the code-side rule that only the purchase
            # book back-creates a counterparty.
            if bind.party_back_create:
                cleaned = _clean_supplier_name(extra.get("party_name"))
                if cleaned:
                    name_key = _norm(cleaned)
                    seen_name_key = party_name_key_by_doc.get(l.doc_number)
                    if seen_name_key is not None and seen_name_key != name_key:
                        # One document has one creditor, exactly the rule the code path
                        # enforces below - the first row still wins, said out loud.
                        issues.append(ResolutionIssue(
                            row, "party_name", cleaned,
                            f"{l.doc_number} names two different creditors, "
                            f"{party_cleaned_name_by_key.get(seen_name_key, seen_name_key)} "
                            f"and {cleaned}; the first is being used"))
                    else:
                        party_name_key_by_doc.setdefault(l.doc_number, name_key)
                        party_cleaned_name_by_key.setdefault(name_key, cleaned)
                        pid_by_name = names_by_key.get(name_key)
                        if pid_by_name is not None:
                            party_by_doc.setdefault(l.doc_number, pid_by_name)
                        else:
                            issues.append(ResolutionIssue(
                                row, "party_name", cleaned,
                                f"no {bind.party.__name__.lower()} named {cleaned!r}; a new "
                                f"{bind.party.__name__.lower()} is being created for it"))
            continue
        pid_party = parties.get(code)
        if pid_party is None:
            # An unresolvable code is only a PROBLEM when it would otherwise be lost. The
            # sales book keeps it on the header, so the order stays attributable and there
            # is nothing for the operator to fix in this file - reporting 2,546 of them
            # would bury the rows that really did fail.
            if bind.party_back_create:
                # The purchase book has nowhere to put an unlinked code, and 2,177 of
                # 5,243 documents in the captain's own file arrived exactly this way -
                # not a typo, a supplier AutoCount already deals with that the master
                # simply hasn't caught up on. `apply()` creates a minimal supplier row
                # for it (mirrors `order_service`'s customer back-create) and links the
                # document; still reported here, so it is visible rather than a surprise
                # after the fact.
                party_code_by_doc.setdefault(l.doc_number, code)
                party_raw_code_by_code.setdefault(code, extra.get("party_code") or code)
                if code not in party_label_by_code and l.label:
                    party_label_by_code[code] = l.label
                issues.append(ResolutionIssue(
                    row, bind.party_code, code,
                    f"no {bind.party.__name__.lower()} with this code; a new "
                    f"{bind.party.__name__.lower()} is being created for it"))
            elif bind.party_code_header_col:
                party_code_by_doc.setdefault(l.doc_number, code)
            else:
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
                     party_code_by_doc=party_code_by_doc,
                     party_label_by_code=party_label_by_code,
                     party_raw_code_by_code=party_raw_code_by_code,
                     party_name_key_by_doc=party_name_key_by_doc,
                     party_cleaned_name_by_key=party_cleaned_name_by_key,
                     header_by_doc=header_by_doc, agent_by_doc=agent_by_doc)


def _existing_lines(db: Session, docs: set[str], bind: _Binding, *,
                    fulfilled_into: Optional[dict[str, float]] = None,
                    money_into: Optional[dict[str, dict]] = None) -> list[Line]:
    """Current outstanding lines for the documents named in the file, as diff Lines.

    `row_ref` carries the DB line id so apply() can update in place rather than matching
    twice by content.

    `fulfilled_into`, when given, is filled with each returned line's already
    delivered/received quantity. The diff has no place for it (it is deliberately
    document-agnostic and compares OUTSTANDING figures) but the honesty checks need it, and a
    caller that only wants the diff should not have to unpack a pair to get it.

    `money_into` is the same idea for the money columns, and it is read for every line the
    file restates unchanged - so it comes out of THIS query rather than a lookup per row. On
    the client's 4,349-row book that is one statement instead of four thousand.
    """
    if not docs:
        return []
    # ORM, so the company-isolation filter applies. See `_resolve`: another company's order
    # carrying the same SO number must never be diffed against this upload, let alone closed
    # by it.
    line, header = bind.line, bind.header
    fulfilled = getattr(line, bind.fulfilled)
    money = [getattr(line, col) for col, _key in bind.money_cols]
    rows = (
        db.query(
            line.id,
            getattr(header, bind.number),
            Product.product_code,
            Warehouse.warehouse_code,
            (line.qty_ordered - fulfilled).label("outstanding"),
            getattr(line, bind.date),
            fulfilled,
            *money,
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
    if money_into is not None:
        money_into.update({
            str(r[0]): {col: r[7 + i] for i, (col, _key) in enumerate(bind.money_cols)}
            for r in rows
        })
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
        # A code-less document resolved through the NAME fallback has nothing in
        # `party_code_by_doc` to name here - fall back to the cleaned name the file
        # actually said, so the message still names what changed instead of reading
        # "changed to ".
        code = (resolved.party_code_by_doc.get(number)
                or resolved.party_cleaned_name_by_key.get(
                    resolved.party_name_key_by_doc.get(number, "")))
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
    # DB line id -> the money columns that line currently holds, read alongside the lines
    # themselves. It is what lets the write path tell a line the file merely restates from
    # one whose PRICE moved, without a lookup per unchanged row.
    money_by_line: dict[str, dict] = field(default_factory=dict)


def _build(db: Session, file_data: bytes, doc_type: str,
           on_total_rows: Optional[Callable[[int], None]] = None) -> _Plan:
    bind = _binding(doc_type)
    resolver = AliasResolver.for_doc_type(db, doc_type)
    read = read_workbook(file_data, doc_type, resolver)
    if on_total_rows is not None:
        # Published the moment the sheet is read, before the diff. Without it `total_rows`
        # first appears when the job completes and the upload drawer shows 0/0 for the whole
        # run, which reads as stuck (the same lesson as the customer importer).
        on_total_rows(read.total_rows)
    if not read.ok:
        return _Plan(read=read)
    resolved = _resolve(db, read, bind)
    fulfilled: dict[str, float] = {}
    money: dict[str, dict] = {}
    existing = _existing_lines(db, {l.doc_number for l in resolved.lines}, bind,
                               fulfilled_into=fulfilled, money_into=money)
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
        money_by_line=money,
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


def _unreadable_date_warning(problems: list[RowProblem]) -> list[str]:
    """AC-safety: a file whose dates the reader could not parse must say so ONCE, up front,
    in plain language - not leave the operator to count "could not read the date" rows in
    the per-row list and infer the consequence themselves. Additive: `row_problems` keeps
    every one of those rows, this just states what happens to them."""
    n = sum(1 for p in problems if "could not read the date" in p.reason)
    if not n:
        return []
    row = "row" if n == 1 else "rows"
    return [
        f"{n} {row} carry a date the reader could not read; those dates will be left as "
        "they are"
    ]


def preview(db: Session, file_data: bytes, doc_type: str = SO) -> PreviewResult:
    """What this upload would change. Writes nothing."""
    plan = _build(db, file_data, doc_type)
    read, diff = plan.read, plan.diff
    if diff is None:
        return PreviewResult(
            doc_type=doc_type, scope_documents=(), counts={}, total_rows=read.total_rows,
            unmapped_headers=read.unmapped_headers, missing_columns=read.missing_columns,
            row_problems=read.problems,
            warnings=_unreadable_date_warning(read.problems),
        )
    row_problems = read.problems + plan.problems
    return PreviewResult(
        doc_type=doc_type,
        scope_documents=diff.scope_documents,
        counts=diff.counts,
        total_rows=read.total_rows,
        unmapped_headers=read.unmapped_headers,
        missing_columns=read.missing_columns,
        row_problems=row_problems,
        resolution_issues=plan.issues,
        samples=_samples(diff),
        activated_documents=plan.activate,
        unmapped_agents=plan.agent_notices,
        warnings=_unreadable_date_warning(row_problems),
    )


def _closed_line(db: Session, bind: _Binding, header_id: str, product_id: Optional[str],
                 warehouse_id: Optional[str], when: Optional[date]):
    """A closed line on this document matching the incoming row exactly, if there is one.

    An explicit lookup rather than widening `_existing_lines`: the diff must stay open-only,
    or a closed line simply absent from the next upload would be re-closed on every re-run
    and `applied.closed` would never settle at 0.

    **A HISTORY line is never revived.** `po_history_service` writes into these same tables,
    closed and fully received, precisely so `scm.on_order_v` and `scm.po_ordered_v` cannot
    count it. Reviving one sets `line_status='open'` and adds the incoming quantity on top of
    what was already received, which satisfies both views: a 2023 purchase that was delivered
    years ago would read as stock on its way in, permanently, and re-uploading would never
    correct it. The two feeds share the table and are told apart by the stamp
    (`history_sources.HISTORY_SOURCE_SYSTEMS`) - so the outstanding book adds its own line for
    that item instead, which is the truth: this document really is open again, and the closed
    history row really did happen.

    Only reachable since S5, which is what makes the guard necessary now: history lines used
    to carry NULL `warehouse_id` and NULL `expected_date`, so the equality below could not
    match a row that stated either. The structured PO + SPO export states both.
    """
    if product_id is None:
        return None
    line = bind.line
    q = (
        db.query(line)
        .filter(getattr(line, bind.header_fk) == header_id,
                line.product_id == product_id,
                line.line_status == "closed",
                sa.or_(line.source_system.is_(None),
                       line.source_system.notin_(list(HISTORY_SOURCE_SYSTEMS))))
    )
    q = q.filter(line.warehouse_id.is_(None) if warehouse_id is None
                 else line.warehouse_id == warehouse_id)
    dated = getattr(line, bind.date)
    q = q.filter(dated.is_(None) if when is None else dated == when)
    return q.order_by(line.created_at).first()


#: Both money columns on both books are stored at 2 decimal places, so that is the precision
#: a comparison between the file and the database can honestly be made at. A sheet stating
#: 0.945 comes back out of the column as 0.95, and comparing the raw figures would call that
#: a price change on every single re-upload, for ever.
_MONEY_PLACES = Decimal("0.01")


def _money_2dp(value) -> Optional[Decimal]:
    """`value` as the column would store it, or None when it is not a number at all."""
    if value is None or value == "":
        return None
    try:
        # ROUND_HALF_UP, which is how Postgres rounds into NUMERIC(_, 2). A different
        # rounding here would disagree with the value it just wrote.
        return Decimal(str(value)).quantize(_MONEY_PLACES, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        return None


def _money_differs(held: dict, extra: dict, bind: _Binding) -> bool:
    """Whether this extract states money that is not what the line already holds.

    Only what the file STATES counts: an absent value is not a disagreement, for the same
    reason `_refresh_money` never blanks a figure the file omits.
    """
    for col, key in bind.money_cols:
        stated = extra.get(key)
        if stated is None:
            continue
        stored = held.get(col)
        a, b = _money_2dp(stated), _money_2dp(stored)
        if a is not None and b is not None:
            if a != b:
                return True
            continue
        # A currency code, or a price arriving where the column was empty.
        if str(stated).strip() != str(stored if stored is not None else "").strip():
            return True
    return False


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


def _write_date(change_after: Optional[Line], fallback: Optional[date]) -> Optional[date]:
    """The date to WRITE for a changed line: the incoming date, unless the reader could not
    read it - in which case the stored date must not be overwritten with `None`.

    `change_after.required_date` is already `None` for both a genuinely blank cell and an
    unreadable one; `date_unreadable` is what tells them apart. `fallback` is whatever the
    line already holds (the diff's own `before.required_date` for an update, or `None` for
    a brand-new line, which has nothing to fall back to).
    """
    if change_after is not None and change_after.date_unreadable:
        return fallback
    return change_after.required_date if change_after is not None else fallback


def _identity(doc_number: str, item_code: str, location: str) -> dict:
    """What names a row in the job detail. No ids - the operator reads document numbers."""
    return {"doc_no": doc_number, "item_code": item_code, "location": location or ""}


def _record_rows_never_written(read: ReadResult, resolved: _Resolved,
                               outcome: ImportOutcome) -> None:
    """Record every source row that did NOT become a line, with the reason it did not.

    Worked out STRUCTURALLY - which row numbers came out of the reader, and which of those
    survived resolution - rather than by reading the wording of a problem. A row can carry a
    problem and still be written (an unreadable date leaves the line dated null; a document
    naming two agents keeps the first), so classifying by message would report rows as
    skipped that are sitting in the database.
    """
    read_rows = {str(l.row_ref) for l in read.lines}
    kept_rows = {str(l.row_ref) for l in resolved.lines}

    for row_number in read.layout_row_numbers:
        outcome.skip(row=row_number, code=oc.NOT_A_LINE)
    for row_number in read.settled_row_numbers:
        outcome.skip(row=row_number, code=oc.NOTHING_OUTSTANDING)

    for problem in read.problems:
        if str(problem.row_number) in read_rows:
            continue  # reported, but the row IS a line - it is counted where it was written
        outcome.skip(
            row=problem.row_number or None,
            code=oc.MISSING_REQUIRED_FIELD if problem.reason.startswith("missing")
            else oc.ROW_ERROR,
            message=problem.reason,
            value=problem.value or None,
        )

    # The only two fields that DROP a row in `_resolve`. Every other issue it raises (an
    # unknown creditor, two agents on one document) is reported while the line is written, so
    # recording those here would count the row twice and claim a skip that never happened.
    codes = {"item_code": oc.PRODUCT_NOT_FOUND, "stock_location": oc.WAREHOUSE_NOT_FOUND}
    for issue in resolved.issues:
        code = codes.get(issue.field)
        if code is None or str(issue.row_number) in kept_rows:
            continue
        outcome.skip(row=issue.row_number or None, code=code, message=issue.reason,
                     value=issue.value or None)


def _supersede_crm_raised_pos(db: Session, resolved: _Resolved,
                              outcome: ImportOutcome) -> tuple[int, list[dict]]:
    """Close the CRM's own recommendation once AutoCount confirms the same order.

    The captain's ruling of 21 Aug: the CRM can raise its own purchase order from a
    reorder-plan confirm (`source_system == "scm_recommendation"`, active after
    `bulk_confirm`). When Joey keys the SAME physical order into AutoCount and this
    outstanding-PO book is uploaded, the two must not both count as on-order for the
    same (product, supplier) - AutoCount is the book of record (the same doctrine the
    `adopted` handover above and `_closed_line`'s history guard already follow), so
    ITS import is what retires the CRM's own draft-turned-order, never the reverse.

    Matched on (product, supplier), never on document number: the CRM's own number
    and AutoCount's number for the same physical order are never the same string, so
    a document-number match would never fire. Only an ACTIVE, OPEN CRM line
    qualifies - a `draft_recommendation` PO is not on-order at all yet (M4-D5) and has
    nothing to supersede, and an already-closed line is left alone, which is what
    makes re-running the same upload a no-op rather than a second attempt at
    something already done.

    Any order-inquiry row PLACED on a line this closes is untagged FIRST, through
    `ProjectOrderInquiryService.unplace_rows` rather than reimplemented here, so it
    reads `raised` again before this SAME import's own auto-place cascade (one of
    its three triggers, PLAN-demo-followups-19aug-ladder-v2.md section G.4) runs
    against the freshly-written AutoCount lines - untagging AFTER that pass would
    miss the very cascade this upload is about to feed, and leave the row `placed`
    on a line that is about to disappear.

    Recorded through the SAME `LINE_CLOSED` code the diff's own closes use above -
    this module invents no new outcome vocabulary - with the `message` naming which
    AutoCount document is the reason, so the job detail is where an operator finds
    out a CRM-raised PO disappeared either way.

    Never called from `preview()`: like every other write in this module, a
    supersession only happens on `apply`.
    """
    pairs: dict[tuple[str, str], tuple[str, str]] = {}
    for l in resolved.lines:
        supplier_id = resolved.party_by_doc.get(l.doc_number)
        product_id = resolved.product_by_code.get(_norm(l.item_code))
        if supplier_id and product_id:
            pairs.setdefault((product_id, supplier_id), (l.doc_number, l.item_code))
    if not pairs:
        return 0, []

    product_ids = {product_id for product_id, _supplier_id in pairs}
    candidates = (
        db.query(PurchaseOrderLine, PurchaseOrder)
        .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id)
        .filter(
            PurchaseOrder.source_system == "scm_recommendation",
            PurchaseOrder.status == "active",
            PurchaseOrderLine.line_status == "open",
            PurchaseOrderLine.product_id.in_(list(product_ids)),
        )
        .all()
    )
    to_close: list[tuple] = []
    for line, header in candidates:
        supplier_id = str(header.supplier_id) if header.supplier_id else None
        if supplier_id is None:
            continue
        match = pairs.get((str(line.product_id), supplier_id))
        if match:
            to_close.append((line, header, match[0], match[1]))
    if not to_close:
        return 0, []

    # Untagged BEFORE the close, so the rows this frees are `raised` in time for
    # THIS SAME import's own auto-place pass to pick them up again.
    line_ids = [str(line.id) for line, _h, _n, _c in to_close]
    from app.models.project_so import INQUIRY_PLACED, OrderInquiryRow

    placed_row_ids = [
        row_id for (row_id,) in
        db.query(OrderInquiryRow.id)
        .filter(OrderInquiryRow.po_line_id.in_(line_ids),
                OrderInquiryRow.state == INQUIRY_PLACED)
        .all()
    ]
    if placed_row_ids:
        from app.services.project_order_inquiry_service import (
            ProjectOrderInquiryService,
        )

        ProjectOrderInquiryService(db).unplace_rows(placed_row_ids)

    touched_headers: dict[str, PurchaseOrder] = {}
    superseded_documents: list[dict] = []
    for line, header, ac_number, item_code in to_close:
        line.line_status = "closed"
        touched_headers[str(header.id)] = header
        outcome.updated(
            code=oc.LINE_CLOSED,
            identity=_identity(header.po_number, item_code, ""),
            value=header.po_number,
            message=f"{header.po_number} superseded by AutoCount PO {ac_number}",
            entity_type="order_line",
            entity_id=line.id,
        )
        superseded_documents.append({
            "po_number": header.po_number,
            "superseded_by": ac_number,
        })
        logger.info(
            "outstanding import: CRM-raised PO %s line %s (product %s) superseded "
            "by AutoCount PO %s", header.po_number, line.id, line.product_id, ac_number,
        )
    db.flush()

    # A PO whose every line just closed is itself closed - the header's status is a
    # summary of its lines, not a separate fact somebody has to notice went stale.
    for header in touched_headers.values():
        still_open = (
            db.query(PurchaseOrderLine.id)
            .filter(PurchaseOrderLine.purchase_order_id == header.id,
                    PurchaseOrderLine.line_status == "open")
            .first()
        )
        if still_open is None:
            header.status = "closed"
    db.flush()

    return len(to_close), superseded_documents


def apply(db: Session, file_data: bytes, doc_type: str = SO,
          actor: Optional[str] = None, outcome: Optional[ImportOutcome] = None,
          on_total_rows: Optional[Callable[[int], None]] = None,
          file_name: Optional[str] = None) -> dict:
    """Write the upload. Returns the same counts the preview showed.

    Closing is `line_status = 'closed'`, not a delete. The line existed and was planned
    against; erasing it would make last week's plan unexplainable, and `scm.committed_v`
    already excludes non-open lines (migration 311).

    `outcome` records what happened to each SOURCE ROW for the job detail. Optional so a
    direct caller (and every existing test) keeps the old signature; when absent a throwaway
    non-persisting recorder stands in, so there is exactly one code path either way.
    """
    outcome = outcome or ImportOutcome(None, persist=False)
    plan = _build(db, file_data, doc_type, on_total_rows=on_total_rows)
    read, resolved, diff = plan.read, plan.resolved, plan.diff
    if diff is None or resolved is None:
        return {"ok": False, "missing_columns": read.missing_columns, "counts": {}}

    _record_rows_never_written(read, resolved, outcome)

    # What this JOB accounts for, which is more than the file states. A closed line is reached
    # by its ABSENCE from the upload, so it carries an outcome and no source row: with the
    # file's own row count as the total, a five-row file that closes one line finishes
    # "6 / 5" with a progress bar past 100%. Published again here - the diff is known and
    # nothing has been written yet - so the denominator is right before the first write.
    closed_rows = sum(1 for c in diff.changes if c.kind == CLOSED)
    total_rows = read.total_rows + closed_rows
    if on_total_rows is not None:
        on_total_rows(total_rows)

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

    # The supplier master, back-created where a PO-book creditor code names nobody it
    # holds - the mirror of the agent creation just above, and the same pattern
    # `order_service._upsert_customer_from_debtor` uses for a sales debtor: find by code
    # first, create a minimal row, flush so the id is usable before the header links it,
    # commit stays with this transaction. One creation per distinct code (the dict key),
    # never inside `preview`.
    #
    # NOT a backfill: only documents THIS upload names get linked. A NULL `supplier_id`
    # left by an earlier upload of the same document stays NULL until that document is
    # re-uploaded - the next upload of the PO book links it then, same as any other
    # figure this importer restates.
    #
    # `supplier_code` is unique per COMPANY (migration 305), not globally, so a code
    # another company already holds is created here too - as its own row, under this
    # company, exactly as if nobody anywhere held it (`test_outstanding_import_company_
    # isolation.py`). The insert still runs inside a savepoint: a concurrent upload
    # creating the same code for this SAME company, or a schema still on the model's
    # bare column-level unique (a `create_all` scratch schema, unlike this suite's
    # migrated one), must not poison the whole transaction - the code is left exactly as
    # unresolved as it always was rather than crashing the upload.
    created_supplier_codes: list[str] = []
    if bind.party_back_create and resolved.party_raw_code_by_code:
        party_ids_by_code: dict[str, str] = {}
        code_col = getattr(bind.party, bind.party_code_col)
        # Driven by the RAW-code map, not the label map: the file's label column is
        # optional (`_MINIMAL` PO uploads carry no SUPPLIER name at all), and a code with
        # no label is still a code to create - it just falls back to naming itself.
        for code in sorted(resolved.party_raw_code_by_code):
            existing = db.query(bind.party).filter(func.upper(code_col) == code).one_or_none()
            if existing is not None:
                party_ids_by_code[code] = str(existing.id)
                continue
            raw_code = resolved.party_raw_code_by_code.get(code, code)
            name = resolved.party_label_by_code.get(code) or raw_code
            try:
                with db.begin_nested():
                    created = bind.party(**{
                        bind.party_code_col: raw_code,
                        bind.party_name_col: name,
                        "is_active": True,
                    })
                    db.add(created)
                    db.flush()
            except IntegrityError:
                logger.warning(
                    "outstanding import: could not back-create %s %r for the "
                    "purchase-order book (the code already exists)",
                    bind.party.__name__.lower(), raw_code)
                continue
            party_ids_by_code[code] = str(created.id)
            created_supplier_codes.append(raw_code)
        for number, code in resolved.party_code_by_doc.items():
            pid = party_ids_by_code.get(code)
            if pid and number not in resolved.party_by_doc:
                resolved.party_by_doc[number] = pid

    # The PO-book NAME fallback: a document whose only creditor evidence is a NAME
    # (`party_name_key_by_doc`, built when the file states no code at all - the captain's
    # real "PO & SPO outstanding.xlsx" export). `_resolve` already linked whatever an
    # existing supplier matched by name; what is left here is one back-creation per
    # distinct cleaned name, same savepoint guard and same reporting as the code path
    # above. Re-queried by name rather than trusting `_resolve`'s snapshot, for the same
    # reason the code loop re-queries by code: a name this run's own code-based creation
    # (or an earlier name in THIS loop) just created must be found, not re-created.
    if bind.party_back_create and resolved.party_cleaned_name_by_key:
        party_ids_by_name_key: dict[str, str] = {}
        name_col = getattr(bind.party, bind.party_name_col)
        for name_key in sorted(resolved.party_cleaned_name_by_key):
            cleaned = resolved.party_cleaned_name_by_key[name_key]
            # `.first()`, not `.one_or_none()`: unlike `supplier_code`, `supplier_name`
            # carries no uniqueness constraint - the real master already holds more than
            # one supplier under the identical name in places - so more than one match
            # is a fact of the data, not a defect this import should crash on. Ordered
            # so the choice is at least DETERMINISTIC across a re-upload rather than
            # whatever order Postgres happened to return rows in.
            existing = (
                db.query(bind.party)
                .filter(func.upper(name_col) == name_key)
                .order_by(bind.party.id)
                .first()
            )
            if existing is not None:
                party_ids_by_name_key[name_key] = str(existing.id)
                continue
            slug = _supplier_slug(db, bind, cleaned)
            try:
                with db.begin_nested():
                    created = bind.party(**{
                        bind.party_code_col: slug,
                        bind.party_name_col: cleaned,
                        "is_active": True,
                    })
                    db.add(created)
                    db.flush()
            except IntegrityError:
                logger.warning(
                    "outstanding import: could not back-create %s %r for the "
                    "purchase-order book (the generated code already exists)",
                    bind.party.__name__.lower(), slug)
                continue
            party_ids_by_name_key[name_key] = str(created.id)
            # The cleaned NAME, not the generated slug: it is what the operator's file
            # actually said and is what they will recognise, where the slug is an
            # internal code they never typed.
            created_supplier_codes.append(cleaned)
        for number, name_key in resolved.party_name_key_by_doc.items():
            pid = party_ids_by_name_key.get(name_key)
            if pid and number not in resolved.party_by_doc:
                resolved.party_by_doc[number] = pid

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
        # The code as printed, kept whether or not it linked. The file is the record of
        # what the document says, so a restated code overwrites; a file that simply omits
        # it never blanks one we already hold.
        #
        # `party_code_by_doc` holds it already `_norm`ed (trimmed, upper), which is what
        # `customer_label.normalize_debtor_code` writes from the history feed. The two feeds
        # write the SAME column, so a difference in spelling shows up as two Who-bought-it
        # rows for one debtor - passed through that helper here so there is one authority
        # for the value rather than two that merely agree today.
        if bind.party_code_header_col:
            code = normalize_debtor_code(resolved.party_code_by_doc.get(number))
            if code:
                setattr(header, bind.party_code_header_col, code)
        order_ids[number] = header.id

    applied = {"added": 0, "updated": 0, "closed": 0, "unchanged": 0}
    # The CORE line id each change actually wrote, keyed by the change object's identity
    # (stable for the life of this call: `diff.changes` is never rebuilt below). Best-effort
    # readers downstream - `planning_change_service.build_batch` - need this because an
    # ADDED change's own `row_ref` is the source ROW NUMBER, not a line id: there is no id
    # to have until the insert below runs.
    applied_line_ids: dict[int, str] = {}
    for c in diff.changes:
        source_row = (int(c.after.row_ref)
                      if c.after is not None and (c.after.row_ref or "").isdigit() else None)
        identity = _identity(c.doc_number, c.item_code, c.location)
        if c.kind == CLOSED:
            line = db.query(bind.line).filter(bind.line.id == c.before.row_ref).one_or_none()
            if line is not None:
                # A status change, never a delete, and never a fabricated receipt: the line
                # was planned against, and inventing a receipt no GRN supports would corrupt
                # lead-time measurement and the picking reconciliation.
                line.line_status = "closed"
                applied["closed"] += 1
                # No source row on purpose: a closed line is reached by its ABSENCE from the
                # file, so there is no row in the upload to point at. It is recorded all the
                # same - it is the destructive half, and the job detail is where somebody
                # goes to find out what an upload took away.
                outcome.updated(code=oc.LINE_CLOSED, identity=identity,
                                value=c.doc_number, entity_type="order_line",
                                entity_id=c.before.row_ref)
                applied_line_ids[id(c)] = str(c.before.row_ref)
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
                setattr(revived, bind.date, _write_date(c.after, getattr(revived, bind.date)))
                _refresh_money(revived, extra, bind)
                applied["added"] += 1
                applied_line_ids[id(c)] = str(revived.id)
                outcome.success(row=source_row, code=oc.CREATED, identity=identity,
                                value=c.doc_number, entity_type="order_line",
                                entity_id=revived.id)
                continue
            # An explicit id, not the column's own default: `planning_change_service`
            # (called after this function flushes) needs the CORE line id an ADDED change
            # wrote, and that default is a client-side callable SQLAlchemy would not
            # resolve onto this instance until the flush at the end of this loop.
            new_line_id = str(uuid.uuid4())
            fields = {
                "id": new_line_id,
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
            applied_line_ids[id(c)] = new_line_id
            outcome.success(row=source_row, code=oc.CREATED, identity=identity,
                            value=c.doc_number)
            continue

        if c.kind == "unchanged":
            # Unchanged is about the QUANTITY and the DATE, which is what the diff compares.
            # The same line can still be repriced, and nothing else on either channel ever
            # revisits that column, so a line left alone here quotes last week's money for
            # ever. Compared at the 2 decimals the column stores, so a sheet that states a
            # third one cannot report an update on every re-upload.
            extra = read.extras.get(str(c.after.row_ref), {})
            if _money_differs(plan.money_by_line.get(str(c.before.row_ref), {}), extra, bind):
                line = (db.query(bind.line)
                        .filter(bind.line.id == c.before.row_ref).one_or_none())
                if line is not None:
                    _refresh_money(line, extra, bind)
                    applied["updated"] += 1
                    outcome.updated(row=source_row, identity=identity, value=c.doc_number,
                                    entity_type="order_line", entity_id=line.id)
                    continue
            applied["unchanged"] += 1
            outcome.unchanged(row=source_row, identity=identity, value=c.doc_number)
            continue

        # qty and/or date changed: update the row the diff paired, in place.
        line = db.query(bind.line).filter(bind.line.id == c.before.row_ref).one_or_none()
        if line is None:
            # The line the diff paired against has gone since it was read. Nothing is
            # written, so the row is a skip rather than a silent nothing.
            outcome.skip(row=source_row, code=oc.ORDER_NOT_FOUND, identity=identity,
                         value=c.doc_number,
                         message="the line this row updates no longer exists")
            continue
        # The extract states what is OUTSTANDING, so ordered is outstanding plus whatever has
        # already been delivered or received. Writing the figure straight in would erase a
        # booked receipt and leave the goods counted as still at sea.
        already = float(getattr(line, bind.fulfilled) or 0)
        line.qty_ordered = already + c.after.qty
        # `c.kind` reaches here for QTY_CHANGED too, not only a real date move: an
        # unreadable incoming date leaves `_classify` reading the date as unchanged, but
        # the row still lands in this branch on the quantity alone, and a straight
        # `c.after.required_date` would still write the `None` `_classify` was built to
        # avoid. `_write_date` keeps the line's own stored date in that case.
        setattr(line, bind.date, _write_date(c.after, c.before.required_date))
        _refresh_money(line, read.extras.get(str(c.after.row_ref), {}), bind)
        applied["updated"] += 1
        applied_line_ids[id(c)] = str(line.id)
        outcome.updated(row=source_row, identity=identity, value=c.doc_number,
                        entity_type="order_line", entity_id=line.id)

    db.flush()

    # CRM<->AutoCount supersession (captain, 21 Aug): PO book only, and never wrapped in
    # a best-effort guard like the two batches below - a failure here must fail the whole
    # upload rather than let AutoCount lines land while the CRM's own duplicate stays open.
    superseded_lines, superseded_documents = (
        _supersede_crm_raised_pos(db, resolved, outcome) if doc_type == PO else (0, [])
    )
    # This job's own count, exactly like `closed_rows` above: a line closed here carries
    # an outcome and no source row either, so the total has to grow with it or `processed`
    # runs past `total_rows` on the progress bar.
    total_rows += superseded_lines

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

    # PLAN-so-book-diff-replanning.md section 2: the SO book's own reaction. Best-effort
    # for the same reason the exception batch above is - the upload has already succeeded,
    # and a defect in the reaction must cost the operator a batch the next upload produces
    # again, never the upload itself. Only the SO channel plans against a project; a PO
    # book has nothing to react to here.
    planning_change_batch = None
    if doc_type == SO and diff.has_material_change:
        try:
            from app.services import planning_change_service

            batch = planning_change_service.build_batch(
                db,
                diff,
                applied_line_ids=applied_line_ids,
                order_ids=order_ids,
                actor=actor,
                import_job_id=getattr(outcome, "import_job_id", None),
                file_name=file_name,
            )
            if batch is not None:
                planning_change_batch = {
                    "id": str(batch.id),
                    "order_count": batch.order_count,
                    "line_count": batch.line_count,
                }
        except Exception:  # pragma: no cover - defensive, see above
            logger.exception("planning change batch failed for a confirmed SO upload")

    return {
        "ok": True,
        "exception_batch_id": exception_batch_id,
        "planning_change_batch": planning_change_batch,
        # Everything this upload accounted for: every non-blank row of the file, plus the
        # lines it closed by absence. One outcome per unit, so processed reaches total exactly.
        "total_rows": total_rows,
        # The file's own row count, kept beside it: it is the number the operator sees at the
        # top of their spreadsheet, and the two differing is the closures.
        "file_rows": read.total_rows,
        "counts": diff.counts,
        "applied": applied,
        "scope_documents": list(diff.scope_documents),
        "activated_documents": activated,
        "adopted_documents": adopted,
        # CRM-raised purchase orders this same upload retired because AutoCount now
        # states the identical (product, supplier) - see `_supersede_crm_raised_pos`.
        "superseded_documents": superseded_documents,
        "resolution_issues": [asdict(i) for i in plan.issues],
        "row_problems": [asdict(p) for p in read.problems + plan.problems],
        # Reported by the commit as well as by the preview, and stated as it was BEFORE the
        # creation above: "new agent, unclassified" is exactly the fact the operator needs
        # after the fact, and re-reading the master here would report every one of them as
        # merely unclassified, losing which ones this upload invented.
        "unmapped_agents": [asdict(a) for a in plan.agent_notices],
        # AC: an operator must never discover an invented supplier by surprise. The count
        # is the whole truth; the list is capped the same way `_samples` caps diff
        # evidence, because a report naming every one of a few thousand codes is not one
        # a person can read either.
        "suppliers_created": len(created_supplier_codes),
        "suppliers_created_codes": created_supplier_codes[:_CREATED_SUPPLIERS_LISTED],
    }
