"""Project import runs: upload, columns, value links, preview, import and revert.

`documentation/plans/project-sales/PLAN-project-import-12nov.md` ("Backend contract") and the
UAC `project-import-12nov-acceptance-criteria.md` (AC-PI-01..50).

A run is one `import_jobs` row (`job_type = project_po_register`); its stage lives in
`job_metadata["phase"]`. Preview and import are ONE function, `_run`: preview runs every
write inside a savepoint and rolls it back, so the two can never disagree about a row.

Rules that hold everywhere below:

* links are explicit: a value reaches a record only through a line a person set (or, for a
  customer, through the synced sales orders its rows name). Nothing is matched by name;
* create-only: an existing project or PO is never edited. The one additive write on an
  existing PO is linking a sales order synced since (`so_linked`);
* one savepoint per row, so one bad row never fails the batch;
* no notification, task or outbound message is written, so `JobService.complete_job` (which
  notifies the uploader) is not used: the run's own fields are set here instead.
"""
from __future__ import annotations

import logging
import re
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

import sqlalchemy as sa
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.audit_context import AuditActor, actor_scope
from app.models.import_alias import ImportFieldAlias
from app.models.job import ImportJob, ImportJobRow, JobStatus
from app.models.order import Customer, SalesOrder
from app.models.project_import import (
    ACTION_CREATE,
    ACTION_LINK,
    ACTION_NONE,
    ACTION_SKIP,
    KIND_CUSTOMER,
    KIND_DEVELOPER,
    KIND_PERSON,
    KIND_PROJECT,
    KINDS,
    ProjectImportValueMap,
)
from app.models.project_so import ProjectSalesOrder
from app.models.projects import (
    PO_SOURCE_CONTRACTOR_DIRECT,
    Project,
    ProjectParty,
    ProjectPurchaseOrder,
    ProjectPurchaseOrderLine,
    ProjectQuotation,
    ProjectSalesProfile,
)
from app.models.user import User
from app.services import import_outcome_codes as oc
from app.services.error_handler import AppException
from app.services.import_alias_service import IGNORE_FIELD, normalize_header
from app.services.import_outcome import ImportOutcome
from app.services.project_import import reader
from app.services.project_import.reader import fold
from app.services.queue_service import enqueue_job

logger = logging.getLogger(__name__)

JOB_TYPE = reader.DOC_TYPE
XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
#: Owner decision d4: 2026 only. A PS number of another year is skipped.
IMPORT_YEAR = "26"

PHASE_DRAFT = "draft"
PHASE_PREVIEWED = "previewed"
PHASE_IMPORTING = "importing"
PHASE_IMPORTED = "imported"
PHASE_REVERTED = "reverted"

OUTCOMES = ("created", "updated", "unchanged", "skipped", oc.OUTCOME_NEEDS_REVIEW, oc.OUTCOME_ERROR)

#: AC-PI-16: what a line of each kind may be set to.
ALLOWED_ACTIONS = {
    KIND_CUSTOMER: (ACTION_LINK, ACTION_SKIP),
    KIND_PROJECT: (ACTION_LINK, ACTION_CREATE, ACTION_SKIP),
    KIND_DEVELOPER: (ACTION_LINK, ACTION_CREATE, ACTION_NONE),
    KIND_PERSON: (ACTION_LINK, ACTION_NONE),
}

ENTITY_PROJECT = "project"
ENTITY_PROFILE = "project_sales_profile"
ENTITY_PO = "project_purchase_order"
ENTITY_PARTY = "project_party"
ENTITY_PSO = "project_sales_order"

_WAIVE_RE = re.compile(r"^WAIVE\s+TRA[NS]", re.IGNORECASE)

# Parsed workbooks, keyed by run + file + choices, so the Values step does not re-read the
# file for every line a person sets. Small and bounded: a run is worked on one at a time.
_READ_CACHE: dict[tuple, reader.ReadResult] = {}
_READ_CACHE_MAX = 8


# --------------------------------------------------------------------------- runs


def _scope_allows(db: Session, company_id: Any) -> bool:
    from app.models.base import get_company_scope

    scope = get_company_scope(db)
    if scope is None:
        return True
    if isinstance(scope, frozenset):
        return str(company_id) in {str(c) for c in scope}
    return False


def get_run(db: Session, run_id: Any) -> ImportJob:
    """The run, inside the caller's company scope. Anything else reads as 404."""
    try:
        uuid.UUID(str(run_id))
    except (ValueError, AttributeError, TypeError):
        raise AppException(404, "Import run not found.", code="project_import_run_not_found")
    run = (
        db.query(ImportJob)
        .filter(ImportJob.id == str(run_id), ImportJob.job_type == JOB_TYPE)
        .first()
    )
    if run is None or not _scope_allows(db, run.company_id):
        raise AppException(404, "Import run not found.", code="project_import_run_not_found")
    return run


def _meta(run: ImportJob) -> dict:
    return dict(run.job_metadata or {})


def _save_meta(db: Session, run: ImportJob, meta: dict) -> None:
    run.job_metadata = meta
    flag_modified(run, "job_metadata")
    run.updated_at = datetime.utcnow()
    db.flush()


def _phase(run: ImportJob) -> str:
    return _meta(run).get("phase") or PHASE_DRAFT


def _assert_phase(run: ImportJob, allowed: tuple[str, ...], doing: str) -> None:
    if _phase(run) not in allowed:
        raise AppException(
            409,
            f"This run is {_phase(run)}, so it cannot {doing}.",
            code="project_import_wrong_phase",
        )


def _check_upload(filename: Optional[str], content: Optional[bytes]) -> None:
    if not content:
        raise AppException(422, "The file is empty.", code="project_import_empty")
    if len(content) > MAX_UPLOAD_BYTES:
        raise AppException(422, "The file is larger than 10 MB.", code="project_import_too_big")
    if not (filename or "").lower().endswith(".xlsx") or content[:4] != b"PK\x03\x04":
        raise AppException(422, "Upload an Excel workbook (.xlsx).", code="project_import_not_xlsx")


def _next_run_no(db: Session, company_id: str) -> str:
    count = (
        db.query(sa.func.count(ImportJob.id))
        .filter(ImportJob.job_type == JOB_TYPE, ImportJob.company_id == str(company_id))
        .scalar()
        or 0
    )
    return f"PIM-{count + 1:04d}"


def create_run(db: Session, *, company_id: str, user_id: str, filename: str, content: bytes) -> ImportJob:
    """Read the upload's sheets, store the file on a new run. 422 on a bad upload (AC-PI-08)."""
    from app.services.import_source_store import store_import_source_file
    from app.services.job_service import JobService

    _check_upload(filename, content)
    try:
        probes = reader.probe(content, field_for=reader.field_resolver(db))
    except Exception as exc:  # noqa: BLE001 - the person who uploaded it reads the answer
        logger.info("project import upload unreadable: %s", type(exc).__name__)
        raise AppException(
            422, "The file could not be read as a workbook.", code="project_import_unreadable"
        )
    if not any(p.has_ps_heading for p in probes):
        raise AppException(
            422,
            "No sheet in this file has a PS number column.",
            code="project_import_no_ps_sheet",
        )
    ticked = [p.name for p in probes if p.has_ps_heading]
    columns: dict[str, str] = {}
    first = next(p for p in probes if p.has_ps_heading)
    for col in first.columns:
        f = col.get("field")
        if f in reader.FIELDS and f not in columns:
            columns[f] = col["header"]

    run_no = _next_run_no(db, company_id)
    job = JobService(db).create_job(
        job_type=JOB_TYPE, user_id=str(user_id), filename=filename, company_id=str(company_id),
    )
    job.total_rows = sum(p.row_count for p in probes if p.has_ps_heading)
    if not store_import_source_file(job, content, filename, XLSX_CONTENT_TYPE):
        raise AppException(503, "The file could not be stored. Try again.", code="project_import_store_failed")
    _save_meta(db, job, {
        "run_no": run_no,
        "phase": PHASE_DRAFT,
        "sheets": ticked,
        "columns": columns,
        "probe": [_probe_dict(p) for p in probes],
    })
    return job


def _probe_dict(p: reader.SheetProbe) -> dict:
    return {
        "name": p.name,
        "name_trimmed": p.name_trimmed,
        "has_ps_heading": p.has_ps_heading,
        "row_count": p.row_count,
        "columns": [dict(c) for c in p.columns],
    }


def _save_alias(db: Session, field_key: str, header: str) -> None:
    """A column choice is a SHARED alias row for this doc type: a later file with the same
    heading needs no choice (AC-PI-10). A re-pick replaces the earlier row for the heading."""
    key = normalize_header(header)
    stale = [
        row.id
        for row in db.query(ImportFieldAlias.id, ImportFieldAlias.alias).filter(
            ImportFieldAlias.doc_type == JOB_TYPE, ImportFieldAlias.supplier_id.is_(None)
        )
        if normalize_header(row.alias) == key
    ]
    if stale:
        db.query(ImportFieldAlias).filter(ImportFieldAlias.id.in_(stale)).delete(
            synchronize_session=False
        )
    db.add(ImportFieldAlias(doc_type=JOB_TYPE, field=field_key, alias=str(header)[:255]))
    db.flush()


def save_columns(db: Session, run: ImportJob, *, sheets: list[str], columns: dict[str, str], user_id: str) -> None:
    """Tick the sheets and choose a heading per field; each choice is saved as an alias."""
    _assert_phase(run, (PHASE_DRAFT, PHASE_PREVIEWED), "change its columns")
    meta = _meta(run)
    probe = meta.get("probe") or []
    by_trim = {p["name"].strip(): p["name"] for p in probe}
    picked = []
    for name in sheets or []:
        real = by_trim.get(str(name).strip())
        if real is None:
            raise AppException(422, "A ticked sheet is not in this file.", code="project_import_sheet_unknown")
        if real not in picked:
            picked.append(real)
    clean: dict[str, str] = {}
    for key, header in (columns or {}).items():
        if key not in reader.FIELDS and key != IGNORE_FIELD:
            raise AppException(422, f"Unknown field: {key}.", code="project_import_field_unknown")
        if header is None or not str(header).strip():
            continue
        clean[key] = str(header)
        _save_alias(db, key, str(header))
    chosen = {normalize_header(h): f for f, h in clean.items()}
    for sheet in probe:
        for col in sheet.get("columns") or []:
            col["field"] = chosen.get(normalize_header(col["header"]), col.get("field"))
    meta.update({"sheets": picked, "columns": clean, "probe": probe, "phase": PHASE_DRAFT})
    _save_meta(db, run, meta)


def _missing_required(run: ImportJob) -> list[str]:
    columns = _meta(run).get("columns") or {}
    return [f for f in reader.REQUIRED_FIELDS if not columns.get(f)]


def _assert_columns(run: ImportJob) -> None:
    missing = _missing_required(run)
    if missing:
        names = ", ".join(reader.FIELD_LABELS[f] for f in missing)
        raise AppException(
            422, f"Choose a column for: {names}.", code="project_import_column_missing",
        )


def _content(run: ImportJob) -> bytes:
    from app.services.storage_router import get_backend

    if not run.source_file_key:
        raise AppException(409, "The uploaded file is not available.", code="project_import_no_file")
    try:
        return get_backend(run.source_file_provider).download_file(run.source_file_key)
    except Exception as exc:  # noqa: BLE001
        logger.warning("project import %s: file not readable (%s)", run.id, type(exc).__name__)
        raise AppException(409, "The uploaded file is not available.", code="project_import_no_file")


def _read(run: ImportJob) -> reader.ReadResult:
    meta = _meta(run)
    sheets = tuple(meta.get("sheets") or ())
    columns = tuple(sorted((meta.get("columns") or {}).items()))
    key = (str(run.id), run.source_file_key, sheets, columns)
    hit = _READ_CACHE.get(key)
    if hit is not None:
        return hit
    result = reader.read_rows(_content(run), sheets=list(sheets), columns=dict(columns))
    if len(_READ_CACHE) >= _READ_CACHE_MAX:
        _READ_CACHE.pop(next(iter(_READ_CACHE)))
    _READ_CACHE[key] = result
    return result


# --------------------------------------------------------------------------- lines


def _collect_lines(rows: list[reader.SourceRow]) -> dict[str, dict[tuple[str, str], dict]]:
    """kind -> {(customer_value_key, value_key): {value_text, customer_text, rows}}."""
    out: dict[str, dict[tuple[str, str], dict]] = {k: {} for k in KINDS}

    def add(kind, ck, vk, text, ctext=None):
        line = out[kind].setdefault((ck, vk), {"value_text": text, "customer_text": ctext, "rows": 0})
        line["rows"] += 1

    for r in rows:
        ck = fold(r.customer)
        if not ck:
            continue
        add(KIND_CUSTOMER, "", ck, r.customer)
        if fold(r.project_name):
            add(KIND_PROJECT, ck, fold(r.project_name), r.project_name, r.customer)
        if fold(r.developer):
            add(KIND_DEVELOPER, "", fold(r.developer), r.developer)
        for person in {fold(r.salesperson): r.salesperson, fold(r.customer_service): r.customer_service}.items():
            if person[0]:
                add(KIND_PERSON, "", person[0], person[1])
    return out


def _maps(db: Session, company_id: Any, kind: Optional[str] = None) -> dict[tuple[str, str, str], ProjectImportValueMap]:
    q = db.query(ProjectImportValueMap).filter(ProjectImportValueMap.company_id == str(company_id))
    if kind:
        q = q.filter(ProjectImportValueMap.kind == kind)
    return {(m.kind, m.customer_value_key or "", m.value_key): m for m in q.all()}


def _sales_orders(db: Session, company_id: Any, rows: list[reader.SourceRow]) -> dict[str, SalesOrder]:
    """Synced core sales orders of this company named by the rows, by upper-cased number."""
    numbers = sorted({so for r in rows for so in r.so_numbers})
    out: dict[str, SalesOrder] = {}
    for start in range(0, len(numbers), 500):
        chunk = numbers[start:start + 500]
        for so in (
            db.query(SalesOrder)
            .filter(SalesOrder.company_id == str(company_id), sa.func.upper(SalesOrder.so_number).in_(chunk))
            .all()
        ):
            out.setdefault((so.so_number or "").upper(), so)
    return out


def _so_customers(rows: list[reader.SourceRow], so_map: dict[str, SalesOrder]) -> dict[str, str]:
    """Customer line -> the one customer every SO on its rows resolves to (AC-PI-19)."""
    numbers: dict[str, set[str]] = defaultdict(set)
    for r in rows:
        ck = fold(r.customer)
        if ck:
            numbers[ck].update(r.so_numbers)
    out: dict[str, str] = {}
    for ck, sos in numbers.items():
        if not sos or any(so not in so_map for so in sos):
            continue
        customers = {so_map[so].customer_id for so in sos}
        if len(customers) == 1 and None not in customers:
            out[ck] = str(next(iter(customers)))
    return out


def _labels(db: Session, kind: str, ids: set[str]) -> dict[str, str]:
    ids = {i for i in ids if i and _is_uuid(i)}
    if not ids:
        return {}
    if kind == KIND_CUSTOMER:
        return {str(c.id): c.customer_name or c.customer_code for c in db.query(Customer).filter(Customer.id.in_(ids))}
    if kind == KIND_PROJECT:
        return {
            str(p.id): " ".join(x for x in (p.project_code, p.title) if x)
            for p in db.query(Project).filter(Project.id.in_(ids))
        }
    if kind == KIND_DEVELOPER:
        return {str(p.id): p.name for p in db.query(ProjectParty).filter(ProjectParty.id.in_(ids))}
    return {str(u.id): u.name or u.email for u in db.query(User).filter(User.id.in_(ids))}


def _is_uuid(value: Any) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, AttributeError, TypeError):
        return False


def list_lines(db: Session, run: ImportJob, *, kind: str, status: Optional[str] = None) -> list[dict]:
    """One line per distinct folded value of `kind` in the run, with its saved choice."""
    if kind not in KINDS:
        raise AppException(422, "Unknown line kind.", code="project_import_kind_unknown")
    read = _read(run)
    lines = _collect_lines(read.rows)[kind]
    maps = _maps(db, run.company_id, kind)
    so_customers = (
        _so_customers(read.rows, _sales_orders(db, run.company_id, read.rows))
        if kind == KIND_CUSTOMER else {}
    )
    out = []
    for (ck, vk), info in lines.items():
        out.append(_line_dict(kind, ck, vk, info, maps.get((kind, ck, vk)), so_customers.get(vk)))
    labels = _labels(db, kind, {l["target_id"] for l in out if l["target_id"]})
    setter_ids = {l["_set_by"] for l in out if l.get("_set_by")}
    setters = (
        {str(u.id): u.name or u.email for u in db.query(User).filter(User.id.in_(setter_ids))}
        if setter_ids else {}
    )
    for line in out:
        set_by = line.pop("_set_by", None)
        line.pop("_set_by_id", None)
        line["target_label"] = labels.get(line["target_id"]) if line["target_id"] else None
        line["set_by_name"] = setters.get(set_by) if set_by else None
    if status:
        out = [l for l in out if l["status"] == status]
    out.sort(key=lambda l: (l["customer_value_key"], l["value_key"]))
    return out


def _line_dict(kind, ck, vk, info, m: Optional[ProjectImportValueMap], so_customer: Optional[str]) -> dict:
    line = {
        "kind": kind,
        "customer_value_key": ck,
        "value_key": vk,
        "value_text": info["value_text"],
        "customer_text": info.get("customer_text"),
        "rows": info["rows"],
        "action": None,
        "target_id": None,
        "target_label": None,
        "new_title": None,
        "source": None,
        "set_by_name": None,
        "set_at": None,
        "status": "todo",
    }
    if m is not None:
        line.update({
            "action": m.action, "target_id": m.target_id, "new_title": m.new_title,
            "source": "saved", "status": "set",
            "set_at": m.set_at.isoformat() if m.set_at else None,
            "_set_by": m.set_by_user_id, "_set_by_id": m.set_by_user_id,
        })
    elif so_customer:
        line.update({"action": ACTION_LINK, "target_id": so_customer, "source": "so", "status": "set"})
    return line


def _assert_target(db: Session, run: ImportJob, kind: str, target_id: Optional[str]) -> None:
    refused = AppException(
        422, "The linked record was not found in this company.", code="project_import_target_invalid"
    )
    if not target_id or not _is_uuid(target_id):
        raise refused
    company = str(run.company_id)
    if kind == KIND_CUSTOMER:
        found = db.query(Customer.id).filter(Customer.id == target_id, Customer.company_id == company).first()
    elif kind == KIND_PROJECT:
        found = db.query(Project.id).filter(Project.id == target_id, Project.company_id == company).first()
    elif kind == KIND_DEVELOPER:
        found = db.query(ProjectParty.id).filter(
            ProjectParty.id == target_id, ProjectParty.company_id == company
        ).first()
    else:
        found = db.query(User.id).filter(User.id == target_id).first()
    if found is None:
        raise refused


def set_line(
    db: Session,
    run: ImportJob,
    *,
    kind: str,
    value_key: str,
    customer_value_key: str = "",
    action: str,
    target_id: Optional[str] = None,
    new_title: Optional[str] = None,
    user_id: str,
) -> dict:
    """Store (or replace) the one saved choice for a line (AC-PI-16)."""
    _assert_phase(run, (PHASE_DRAFT, PHASE_PREVIEWED), "change its values")
    if kind not in KINDS:
        raise AppException(422, "Unknown line kind.", code="project_import_kind_unknown")
    if action not in ALLOWED_ACTIONS[kind]:
        raise AppException(422, f"A {kind} line cannot be set to {action}.", code="project_import_action_invalid")
    ck = fold(customer_value_key) if kind == KIND_PROJECT else ""
    vk = fold(value_key)
    read = _read(run)
    info = _collect_lines(read.rows)[kind].get((ck, vk))
    if info is None:
        shown = f"{ck} / {vk}" if ck else vk
        raise AppException(422, f"{shown} is not a {kind} value in this file.", code="project_import_line_unknown")
    clean_title = None
    if action == ACTION_LINK:
        _assert_target(db, run, kind, target_id)
    else:
        target_id = None
    if action == ACTION_CREATE and kind == KIND_PROJECT:
        clean_title = " ".join((new_title or "").split())
        if not clean_title:
            raise AppException(422, "A new project needs a title.", code="project_import_title_required")
    m = (
        db.query(ProjectImportValueMap)
        .filter(
            ProjectImportValueMap.company_id == str(run.company_id),
            ProjectImportValueMap.kind == kind,
            ProjectImportValueMap.customer_value_key == ck,
            ProjectImportValueMap.value_key == vk,
        )
        .first()
    )
    if m is None:
        m = ProjectImportValueMap(
            company_id=str(run.company_id), kind=kind, customer_value_key=ck, value_key=vk,
            value_text=info["value_text"],
        )
        db.add(m)
    m.action = action
    m.target_id = str(target_id) if target_id else None
    m.new_title = clean_title
    m.set_by_user_id = str(user_id) if user_id else None
    m.set_at = datetime.utcnow()
    db.flush()
    line = _line_dict(kind, ck, vk, info, m, None)
    line.pop("_set_by", None)
    line.pop("_set_by_id", None)
    setter = db.query(User).filter(User.id == str(user_id)).first() if user_id else None
    line["set_by_name"] = (setter.name or setter.email) if setter else None
    line["target_label"] = _labels(db, kind, {line["target_id"]}).get(line["target_id"]) if line["target_id"] else None
    return line


def bulk_set(
    db: Session,
    run: ImportJob,
    *,
    kind: str,
    keys: list[tuple[str, str]],
    action: str,
    target_id: Optional[str] = None,
    new_title: Optional[str] = None,
    user_id: str,
) -> list[dict]:
    """One action on every listed line, through `set_line` once per line. All or nothing."""
    savepoint = db.begin_nested()
    out = []
    try:
        for customer_value_key, value_key in keys:
            out.append(set_line(
                db, run, kind=kind, value_key=value_key, customer_value_key=customer_value_key or "",
                action=action, target_id=target_id, new_title=new_title, user_id=user_id,
            ))
    except Exception:
        savepoint.rollback()
        raise
    savepoint.commit()
    return out


# --------------------------------------------------------------------------- preview / import


class _Review(Exception):
    def __init__(self, code: str, message: Optional[str] = None):
        super().__init__(code)
        self.code = code
        self.message = message


@dataclass
class _Plan:
    row: reader.SourceRow
    flags: list[str]
    outcome: Optional[str] = None
    codes: list[str] = field(default_factory=list)
    message: Optional[str] = None
    existing: Optional[ProjectPurchaseOrder] = None
    customer_id: Optional[str] = None
    project: Optional[tuple] = None  # ("link", id) | ("create", title_key)
    developer: Optional[tuple] = None  # ("link", id) | ("create", value_key) | None


@dataclass
class _Group:
    key: str
    title: str
    rows: list[_Plan] = field(default_factory=list)
    admin_ref: Optional[str] = None
    owner_user_id: Optional[str] = None
    developer: Optional[tuple] = None
    developer_name: Optional[str] = None
    blocked: Optional[_Review] = None
    project: Optional[Project] = None


def _is_cancelled(r: reader.SourceRow) -> bool:
    if r.value_dash:
        return True
    return any(
        (cell or "").strip().upper().startswith("CANCEL") for cell in (r.outstanding, r.so_cell, r.remarks)
    )


def _fmt(value: Any) -> str:
    return value.strftime("%d/%m/%Y") if isinstance(value, date) else str(value)


def _notes(r: reader.SourceRow) -> str:
    """AC-PI-26: one line each, in this order, only when present."""
    lines = []
    if r.customer_service:
        lines.append(f"CS: {r.customer_service}")
    if r.amended is not None:
        lines.append(f"Amended: {_fmt(r.amended)}")
    if r.schedule:
        lines.append(f"Schedule: {r.schedule}")
    if r.delivery is not None:
        lines.append(f"Delivery: {_fmt(r.delivery)}")
    if r.outstanding:
        lines.append(f"Outstanding: {r.outstanding}")
    waive = bool(r.remarks and _WAIVE_RE.match(r.remarks.strip()))
    if waive:
        lines.append("Waive transport charge")
    if r.so_cell and not r.so_numbers:
        lines.append(f"SO note: {r.so_cell}")
    if r.remarks and not waive:
        lines.append(f"Remarks: {r.remarks}")
    return "\n".join(lines)


def _flags(r: reader.SourceRow, so_map: dict[str, SalesOrder]) -> list[str]:
    out = []
    if r.po_number_numeric:
        out.append(oc.PO_NUMBER_NUMERIC)
    if r.po_date is not None:
        year = 2000 + int(reader.PS_RE.match(r.ps_number).group(1))
        if r.po_date.year != year:
            out.append(oc.DATE_OTHER_YEAR)
        month = reader.sheet_month(r.sheet)
        if month and r.po_date.month != month:
            out.append(oc.DATE_OTHER_MONTH)
    if any(so not in so_map for so in r.so_numbers):
        out.append(oc.SO_NOT_SYNCED)
    return out


def _same_shop(db: Session, a_id: str, b_id: str) -> bool:
    """Two keyed customers are one shop: same group, or the same ledger family (AC-PI-19)."""
    from app.services.ledger_family import ledger_family_key

    a, b = db.get(Customer, a_id), db.get(Customer, b_id)
    if a is None or b is None:
        return False
    if a.customer_group_id and str(a.customer_group_id) == str(b.customer_group_id or ""):
        return True
    ka, kb = ledger_family_key(a.customer_name or ""), ledger_family_key(b.customer_name or "")
    return bool(ka) and ka == kb


def preview(db: Session, run: ImportJob, *, user_id: str) -> dict:
    """The import, run and rolled back. Only the run's report rows are kept (AC-PI-20)."""
    return _run(db, run, user_id=user_id, persist=False)


def apply(db: Session, run: ImportJob, *, user_id: str) -> dict:
    """The import. Does not commit; the caller owns the transaction."""
    return _run(db, run, user_id=user_id, persist=True)


def _run(db: Session, run: ImportJob, *, user_id: str, persist: bool) -> dict:
    _assert_columns(run)
    if persist:
        _assert_phase(run, (PHASE_DRAFT, PHASE_PREVIEWED, PHASE_IMPORTING), "be imported")
    else:
        _assert_phase(run, (PHASE_DRAFT, PHASE_PREVIEWED), "be previewed")
    read = _read(run)
    actor = AuditActor(actor_type="user", user_id=str(user_id), real_user_id=str(user_id), job_id=str(run.id))
    with actor_scope(actor, db=db):
        savepoint = None if persist else db.begin_nested()
        try:
            report_rows, ledger = _process(db, run, read, user_id=str(user_id), persist=persist)
        finally:
            if savepoint is not None and savepoint.is_active:
                savepoint.rollback()

    counts = Counter(r["outcome"] for r in report_rows)
    codes = Counter(c for r in report_rows for c in r["codes"])
    report = {
        "counts": {o: counts.get(o, 0) for o in OUTCOMES},
        "codes": dict(codes),
        "rows": report_rows,
        "sheet_errors": list(read.sheet_errors),
    }
    _write_rows(db, run, report_rows, ledger)

    meta = _meta(run)
    meta["sheet_errors"] = list(read.sheet_errors)
    if persist:
        marker = db.execute(sa.select(sa.cast(sa.func.now(), sa.DateTime(timezone=False)))).scalar()
        meta.update({"phase": PHASE_IMPORTED, "result_counts": report["counts"],
                     "result_codes": report["codes"], "imported_at": marker.isoformat()})
        now = datetime.utcnow()
        run.status = JobStatus.FINISHED.value
        run.completed_at = now
        run.processed_rows = len(report_rows)
        run.successful_rows = sum(counts.get(o, 0) for o in ("created", "updated", "unchanged"))
        run.skipped_rows = counts.get("skipped", 0)
        run.failed_rows = counts.get(oc.OUTCOME_ERROR, 0) + counts.get(oc.OUTCOME_NEEDS_REVIEW, 0)
        run.result = {"counts": report["counts"], "codes": report["codes"]}
    else:
        meta.update({"phase": PHASE_PREVIEWED, "preview_counts": report["counts"],
                     "preview_codes": report["codes"]})
    _save_meta(db, run, meta)
    return report


def _write_rows(db: Session, run: ImportJob, report_rows: list[dict], ledger: list[dict]) -> None:
    """Replace the run's report rows; add the ledger of what was created (AC-PI-35)."""
    from sqlalchemy.orm import Session as _Session

    db.query(ImportJobRow).filter(ImportJobRow.import_job_id == run.id).delete(synchronize_session=False)
    db.flush()

    def factory():
        return _Session(bind=db.connection(), join_transaction_mode="create_savepoint")

    rows_out = ImportOutcome(run.id, session_factory=factory, buffer_size=5000)
    for r in report_rows:
        code = r["codes"][0] if r["codes"] else r["outcome"]
        kwargs = dict(
            row=r["row_number"], code=code, message=r["message"], value=r["ps_number"],
            identity={
                "sheet": r["sheet"], "ps_number": r["ps_number"], "customer": r["customer"],
                "project": r["project"], "po_number": r["po_number"], "po_date": r["po_date"],
                "codes": ",".join(r["codes"]),
            },
        )
        if r["outcome"] == "skipped":
            rows_out.skip(**kwargs)
        elif r["outcome"] == oc.OUTCOME_ERROR:
            rows_out.fail(**kwargs)
        else:
            rows_out.success(outcome=r["outcome"], **kwargs)
    rows_out.flush()
    entities = ImportOutcome(run.id, session_factory=factory, buffer_size=5000)
    for e in ledger:
        entities.success(
            row=e["row_number"], code=oc.CREATED, message=e["label"], value=e["ps_number"],
            identity={"ps_number": e["ps_number"]}, entity_type=e["entity_type"],
            entity_id=e["entity_id"],
        )
    entities.flush()


def _process(db: Session, run: ImportJob, read: reader.ReadResult, *, user_id: str, persist: bool):
    company_id = str(run.company_id)
    sheet_order = {}
    for r in read.rows:
        sheet_order.setdefault(r.sheet, len(sheet_order))
    rows = sorted(read.rows, key=lambda r: (r.ps_number, sheet_order[r.sheet], r.row_number))
    maps = _maps(db, company_id)
    so_map = _sales_orders(db, company_id, rows)
    so_customers = _so_customers(rows, so_map)

    plans = [_Plan(row=r, flags=_flags(r, so_map)) for r in rows]
    eligible = []
    for p in plans:
        r = p.row
        if reader.PS_RE.match(r.ps_number).group(1) != IMPORT_YEAR:
            p.outcome, p.codes = "skipped", [oc.OTHER_YEAR]
        elif not fold(r.customer):
            p.outcome, p.codes = "skipped", [oc.PLACEHOLDER]
        elif _is_cancelled(r):
            p.outcome, p.codes = "skipped", [oc.CANCELLED]
        elif not fold(r.project_name):
            p.outcome, p.codes = "skipped", [oc.NO_PROJECT_NAME]
        else:
            eligible.append(p)
    in_file = Counter(p.row.ps_number for p in eligible)
    existing: dict[str, list[ProjectPurchaseOrder]] = defaultdict(list)
    ps_numbers = sorted({p.row.ps_number for p in eligible})
    for start in range(0, len(ps_numbers), 500):
        for po in db.query(ProjectPurchaseOrder).filter(
            ProjectPurchaseOrder.company_id == company_id,
            ProjectPurchaseOrder.admin_ref.in_(ps_numbers[start:start + 500]),
        ):
            existing[po.admin_ref].append(po)

    ready: list[_Plan] = []
    for p in eligible:
        r = p.row
        if in_file[r.ps_number] > 1:
            p.outcome, p.codes = oc.OUTCOME_ERROR, [oc.PS_DUPLICATE_IN_FILE]
            continue
        held = existing.get(r.ps_number) or []
        if len(held) > 1:
            p.outcome, p.codes = oc.OUTCOME_ERROR, [oc.PS_DUPLICATE_IN_CRM]
            continue
        if held:
            p.existing = held[0]
            continue
        _resolve(db, p, maps, so_customers)
        if p.outcome is None:
            ready.append(p)

    groups = _groups(db, company_id, ready, maps)

    report: list[dict] = []
    ledger: list[dict] = []
    ctx = _Ctx(db=db, company_id=company_id, user_id=user_id, so_map=so_map, maps=maps,
               groups=groups, ledger=ledger)
    for p in plans:
        if p.outcome is None:
            if p.existing is not None:
                _existing_row(ctx, p)
            else:
                _new_row(ctx, p)
        report.append(_report_row(p))

    if persist:
        _rewrite_created_lines(db, ctx, user_id)
    order = {(r.sheet, r.row_number): i for i, r in enumerate(read.rows)}
    report.sort(key=lambda x: order.get((x["sheet"], x["row_number"]), 0))
    return report, ledger


def _resolve(db: Session, p: _Plan, maps: dict, so_customers: dict) -> None:
    """Pass one for a new row: its customer, project and developer, or what blocks it."""
    r = p.row
    ck, pk, dk = fold(r.customer), fold(r.project_name), fold(r.developer)
    cmap = maps.get((KIND_CUSTOMER, "", ck))
    pmap = maps.get((KIND_PROJECT, ck, pk))
    dmap = maps.get((KIND_DEVELOPER, "", dk)) if dk else None
    if (cmap is not None and cmap.action == ACTION_SKIP) or (pmap is not None and pmap.action == ACTION_SKIP):
        p.outcome, p.codes = "skipped", [oc.MAPPED_SKIP]
        return
    blocking: list[str] = []
    extra: list[str] = []
    so_customer = so_customers.get(ck)
    human = cmap.target_id if cmap is not None and cmap.action == ACTION_LINK else None
    if so_customer and human and so_customer != human:
        if _same_shop(db, so_customer, human):
            p.customer_id = so_customer
            extra.append(oc.CUSTOMER_SAME_SHOP_SO_USED)
        else:
            blocking.append(oc.CUSTOMER_CONFLICT)
    else:
        p.customer_id = so_customer or human
        if not p.customer_id:
            blocking.append(oc.CUSTOMER_UNMAPPED)
    if pmap is None or pmap.action not in (ACTION_LINK, ACTION_CREATE):
        blocking.append(oc.PROJECT_UNMAPPED)
    elif pmap.action == ACTION_LINK:
        p.project = (ACTION_LINK, pmap.target_id)
    else:
        p.project = (ACTION_CREATE, fold(pmap.new_title), pmap.new_title)
    linking = pmap is not None and pmap.action == ACTION_LINK
    if dk and not linking:
        if dmap is None or dmap.action not in (ACTION_LINK, ACTION_CREATE, ACTION_NONE):
            blocking.append(oc.DEVELOPER_UNMAPPED)
        elif dmap.action == ACTION_LINK:
            p.developer = (ACTION_LINK, dmap.target_id)
        elif dmap.action == ACTION_CREATE:
            p.developer = (ACTION_CREATE, dk)
    p.flags = extra + p.flags
    if blocking:
        p.outcome, p.codes = oc.OUTCOME_NEEDS_REVIEW, blocking + p.flags


def _groups(db: Session, company_id: str, ready: list[_Plan], maps: dict) -> dict[str, _Group]:
    """Pass two: the rows of each new project, its owner, developer and the lock check."""
    from app.services.project_clash_service import normalise_project_title

    groups: dict[str, _Group] = {}
    for p in sorted(ready, key=lambda x: x.row.ps_number):
        if p.project and p.project[0] == ACTION_CREATE:
            g = groups.setdefault(p.project[1], _Group(key=p.project[1], title=" ".join(p.project[2].split())))
            g.rows.append(p)
    for g in groups.values():
        lowest = g.rows[0]
        g.admin_ref = lowest.row.ps_number
        person = maps.get((KIND_PERSON, "", fold(lowest.row.salesperson)))
        if person is not None and person.action == ACTION_LINK:
            g.owner_user_id = person.target_id
        g.developer_name = next((x.row.developer for x in g.rows if x.row.developer), None)
        developers = {x.developer for x in g.rows if x.developer is not None}
        if len(developers) > 1:
            g.blocked = _Review(oc.DEVELOPER_CONFLICT)
            continue
        g.developer = next(iter(developers)) if developers else None
        if g.developer is not None and g.developer[0] == ACTION_CREATE:
            continue  # a party made by this run cannot already hold this title
        developer_id = g.developer[1] if g.developer else None
        q = db.query(Project).filter(
            Project.company_id == company_id,
            Project.normalised_title == normalise_project_title(g.title),
            sa.or_(Project.approval_state.is_(None), Project.approval_state == "approved"),
        )
        q = q.filter(Project.developer_party_id == developer_id) if developer_id else q.filter(
            Project.developer_party_id.is_(None)
        )
        clash = q.first()
        if clash is not None:
            g.blocked = _Review(
                oc.REGISTRATION_LOCK,
                f"Project {clash.project_code} already has this developer and title. "
                "Link the line to it instead.",
            )
    return groups


@dataclass
class _Ctx:
    db: Session
    company_id: str
    user_id: str
    so_map: dict
    maps: dict
    groups: dict
    ledger: list
    parties: dict = field(default_factory=dict)
    issuers: dict = field(default_factory=dict)
    created_parties: dict = field(default_factory=dict)


def _issuer(ctx: _Ctx, customer_id: Optional[str]) -> Optional[str]:
    """AC-PI-25: an existing party keyed to the customer, only when exactly one exists."""
    if not customer_id:
        return None
    if customer_id not in ctx.issuers:
        ids = [
            pid for (pid,) in ctx.db.query(ProjectParty.id).filter(
                ProjectParty.company_id == ctx.company_id, ProjectParty.customer_id == customer_id
            ).limit(2)
        ]
        ctx.issuers[customer_id] = str(ids[0]) if len(ids) == 1 else None
    return ctx.issuers[customer_id]


def _entity(ctx_rows: list, p: _Plan, entity_type: str, entity_id: Any, label: str) -> None:
    ctx_rows.append({
        "row_number": p.row.row_number, "ps_number": p.row.ps_number,
        "entity_type": entity_type, "entity_id": str(entity_id), "label": label,
    })


def _so_items(ctx: _Ctx, p: _Plan, project_id: Optional[str]) -> list[tuple]:
    items = []
    for so in p.row.so_numbers:
        core = ctx.so_map.get(so)
        if core is None:
            continue
        pso = ctx.db.query(ProjectSalesOrder).filter(ProjectSalesOrder.so_id == str(core.id)).first()
        if pso is not None and pso.project_id is not None and (
            project_id is None or str(pso.project_id) != str(project_id)
        ):
            raise _Review(oc.SO_ON_OTHER_PROJECT, f"Sales order {core.so_number} is already on another project.")
        items.append((core, pso))
    return items


def _adopt(ctx: _Ctx, core: SalesOrder, entities: list, p: _Plan) -> ProjectSalesOrder:
    from app.services.project_so_adoption_service import ProjectSOAdoptionService

    result = ProjectSOAdoptionService(ctx.db).adopt_for_migration(str(core.id), actor_user_id=ctx.user_id)
    pso = ctx.db.get(ProjectSalesOrder, result["project_sales_order_id"])
    if not result.get("already_adopted"):
        _entity(entities, p, ENTITY_PSO, pso.id, f"Sales order {core.so_number}")
    return pso


def _new_row(ctx: _Ctx, p: _Plan) -> None:
    from app.services.project_po_service import create_po
    from app.services.project_reference_service import create_party
    from app.services.project_service import register_project
    from app.services.project_so_link import link_sales_order_to_project

    db, r = ctx.db, p.row
    group = ctx.groups.get(p.project[1]) if p.project[0] == ACTION_CREATE else None
    if group is not None and group.blocked is not None:
        p.outcome, p.codes, p.message = oc.OUTCOME_NEEDS_REVIEW, [group.blocked.code] + p.flags, group.blocked.message
        return
    entities: list[dict] = []
    made_party: Optional[tuple] = None
    savepoint = db.begin_nested()
    try:
        codes: list[str] = []
        if group is None:
            project = None
            if _is_uuid(p.project[1]):
                project = db.query(Project).filter(
                    Project.id == p.project[1], Project.company_id == ctx.company_id
                ).first()
            if project is None:
                raise _Review(oc.PROJECT_UNMAPPED, "The linked project no longer exists.")
        else:
            project = group.project
        items = _so_items(ctx, p, project.id if project is not None else None)
        if project is not None:
            taken = db.query(ProjectPurchaseOrder).filter(
                ProjectPurchaseOrder.project_id == project.id,
                ProjectPurchaseOrder.po_number == r.po_number,
            ).first()
            if taken is not None:
                raise _Review(
                    oc.PO_NUMBER_TAKEN,
                    f"PO number {r.po_number} is already on this project under "
                    f"{taken.admin_ref or 'another PO'}.",
                )
        if project is None:
            developer_id = None
            if group.developer is not None and group.developer[0] == ACTION_LINK:
                developer_id = group.developer[1]
            elif group.developer is not None:
                developer_id = ctx.parties.get(group.developer[1])
                if developer_id is None:
                    dmap = ctx.maps.get((KIND_DEVELOPER, "", group.developer[1]))
                    name = " ".join(((dmap.value_text if dmap else None) or group.developer[1]).split())
                    party, created = create_party(
                        db, company_id=ctx.company_id,
                        payload={"party_type": "developer", "name": name}, actor_user_id=ctx.user_id,
                    )
                    developer_id = str(party.id)
                    made_party = (group.developer[1], developer_id)
                    if created:
                        _entity(entities, p, ENTITY_PARTY, party.id, party.name)
            project = register_project(
                db, company_id=ctx.company_id, actor_user_id=ctx.user_id,
                developer_party_id=developer_id, title=group.title,
                owner_user_id=group.owner_user_id or ctx.user_id,
                details={"customer_id": p.customer_id, "admin_ref": group.admin_ref},
                skip_clash_check=True,
            )
            profile = db.get(ProjectSalesProfile, project.id)
            if profile is None:
                profile = ProjectSalesProfile(project_id=project.id)
                db.add(profile)
            profile.developer_name = (group.developer_name or None) and group.developer_name[:255]
            db.flush()
            _entity(entities, p, ENTITY_PROJECT, project.id, f"{project.project_code} {project.title}")
            _entity(entities, p, ENTITY_PROFILE, project.id, f"Sales details of {project.project_code}")
            codes = [oc.PROJECT_AND_PO_CREATED, oc.CLASH_CHECK_SKIPPED]
            if not group.owner_user_id:
                codes.append(oc.OWNER_DEFAULTED)
        else:
            codes = [oc.PO_ADDED]
        notes = _notes(r)
        po = create_po(
            db, project=project, actor_user_id=ctx.user_id,
            payload={
                "po_source": PO_SOURCE_CONTRACTOR_DIRECT,
                "issuing_party_id": _issuer(ctx, p.customer_id),
                "po_number": r.po_number or "",
                "po_date": r.po_date,
                "po_amount": r.po_value,
                "notes": notes or None,
            },
        )
        po.sales_person = (r.salesperson or "").strip() or None
        po.admin_ref = r.ps_number
        db.flush()
        _entity(entities, p, ENTITY_PO, po.id, f"PO {po.po_number} ({r.ps_number})")
        for core, pso in items:
            if pso is None:
                pso = _adopt(ctx, core, entities, p)
            link_sales_order_to_project(db, project_sales_order=pso, project=project, purchase_order=po)
        savepoint.commit()
    except _Review as review:
        savepoint.rollback()
        p.outcome, p.codes, p.message = oc.OUTCOME_NEEDS_REVIEW, [review.code] + p.flags, review.message
        return
    except AppException as exc:
        savepoint.rollback()
        logger.warning("project import row %s refused: %s", r.row_number, exc.code)
        p.outcome, p.codes, p.message = oc.OUTCOME_ERROR, [oc.ROW_ERROR], exc.message
        return
    except Exception as exc:  # noqa: BLE001 - one bad row never fails the batch (AC-PI-33)
        savepoint.rollback()
        logger.warning("project import row %s failed: %s", r.row_number, type(exc).__name__)
        p.outcome, p.codes, p.message = oc.OUTCOME_ERROR, [oc.ROW_ERROR], "This row could not be saved."
        return
    if group is not None and group.project is None:
        group.project = project
    if made_party is not None:
        ctx.parties[made_party[0]] = made_party[1]
        ctx.created_parties[made_party[0]] = made_party[1]
    ctx.ledger.extend(entities)
    p.outcome, p.codes = "created", codes + p.flags


def _existing_row(ctx: _Ctx, p: _Plan) -> None:
    """A PS number already on a PO: report differences, write nothing but a new SO link."""
    from app.services.project_so_link import link_sales_order_to_project

    db, r, po = ctx.db, p.row, p.existing
    changes = []
    if r.po_number and r.po_number != po.po_number:
        changes.append("PO number")
    if r.po_value is not None and (
        po.po_amount is None
        or Decimal(po.po_amount).quantize(Decimal("0.01")) != r.po_value.quantize(Decimal("0.01"))
    ):
        changes.append("amount")
    if r.po_date is not None and r.po_date != po.po_date:
        changes.append("date")
    notes = _notes(r)
    if notes and notes != (po.notes or ""):
        changes.append("notes")
    entities: list[dict] = []
    linked = 0
    other = None
    savepoint = db.begin_nested()
    try:
        project = db.get(Project, po.project_id)
        for so in r.so_numbers:
            core = ctx.so_map.get(so)
            if core is None:
                continue
            pso = db.query(ProjectSalesOrder).filter(ProjectSalesOrder.so_id == str(core.id)).first()
            if pso is not None and pso.project_id is not None and str(pso.project_id) != str(project.id):
                other = core.so_number
                continue
            if pso is not None and pso.project_id is not None and pso.purchase_order_id is not None:
                continue
            if pso is None:
                pso = _adopt(ctx, core, entities, p)
            link_sales_order_to_project(db, project_sales_order=pso, project=project, purchase_order=po)
            linked += 1
        savepoint.commit()
    except Exception as exc:  # noqa: BLE001
        savepoint.rollback()
        logger.warning("project import row %s failed: %s", r.row_number, type(exc).__name__)
        p.outcome, p.codes, p.message = oc.OUTCOME_ERROR, [oc.ROW_ERROR], "This row could not be saved."
        return
    ctx.ledger.extend(entities)
    changed = [oc.CHANGED_IN_FILE] if changes else []
    p.message = (
        f"Differs from the CRM in: {', '.join(changes)}. Nothing was changed." if changes else None
    )
    if linked:
        p.outcome, p.codes = "updated", [oc.SO_LINKED] + changed + p.flags
    elif other:
        p.outcome, p.codes = oc.OUTCOME_NEEDS_REVIEW, [oc.SO_ON_OTHER_PROJECT] + changed + p.flags
        p.message = f"Sales order {other} is already on another project."
    else:
        p.outcome, p.codes = "unchanged", changed + p.flags


def _report_row(p: _Plan) -> dict:
    r = p.row
    message = p.message or "; ".join(oc.label_for(c) for c in p.codes) or oc.label_for(p.outcome)
    return {
        "sheet": r.sheet,
        "row_number": r.row_number,
        "ps_number": r.ps_number,
        "customer": r.customer,
        "project": r.project_name,
        "po_number": r.po_number,
        "po_date": r.po_date.isoformat() if r.po_date else None,
        "outcome": p.outcome,
        "codes": list(p.codes),
        "message": message,
    }


def _rewrite_created_lines(db: Session, ctx: _Ctx, user_id: str) -> None:
    """AC-PI-22/23: a "create" line now links to what the run made, so a later file adds to it."""
    made = {key: g.project for key, g in ctx.groups.items() if g.project is not None}
    for m in ctx.maps.values():
        if m.action != ACTION_CREATE:
            continue
        if m.kind == KIND_PROJECT and fold(m.new_title) in made:
            m.action, m.target_id = ACTION_LINK, str(made[fold(m.new_title)].id)
        elif m.kind == KIND_DEVELOPER and m.value_key in ctx.created_parties:
            m.action, m.target_id = ACTION_LINK, ctx.created_parties[m.value_key]
    db.flush()


def start_import(db: Session, run: ImportJob, *, user_id: str) -> str:
    """Queue the import on the `imports` queue (AC-PI-36). Returns the job id."""
    from app.tasks.import_tasks import process_project_import

    _assert_columns(run)
    _assert_phase(run, (PHASE_DRAFT, PHASE_PREVIEWED), "be imported")
    meta = _meta(run)
    meta.update({"phase": PHASE_IMPORTING, "started_by": str(user_id)})
    _save_meta(db, run, meta)
    try:
        job = enqueue_job(process_project_import, str(run.id), queue_name="imports", job_id=str(run.job_id))
    except Exception as exc:  # noqa: BLE001
        logger.warning("project import %s could not be queued: %s", run.id, type(exc).__name__)
        meta["phase"] = PHASE_PREVIEWED if meta.get("preview_counts") else PHASE_DRAFT
        _save_meta(db, run, meta)
        raise AppException(503, "The import could not be queued. Try again.", code="project_import_queue_failed")
    run.job_id = str(job.id)
    run.status = JobStatus.QUEUED.value
    db.flush()
    return str(job.id)


# --------------------------------------------------------------------------- revert


def revert(db: Session, run: ImportJob, *, user_id: str) -> dict:
    """Remove what the run created, children first; keep what changed since (AC-PI-37/38)."""
    from app.services.project_po_service import delete_po

    phase = _phase(run)
    if phase == PHASE_REVERTED:
        raise AppException(409, "This run is already reverted.", code="project_import_reverted")
    if phase != PHASE_IMPORTED:
        raise AppException(409, "Only an imported run can be reverted.", code="project_import_not_imported")
    meta = _meta(run)
    marker = datetime.fromisoformat(meta["imported_at"]) if meta.get("imported_at") else None
    ledger = (
        db.query(ImportJobRow)
        .filter(ImportJobRow.import_job_id == run.id, ImportJobRow.entity_id.isnot(None))
        .all()
    )
    ids: dict[str, list[str]] = defaultdict(list)
    for row in ledger:
        if row.entity_id not in ids[row.entity_type]:
            ids[row.entity_type].append(row.entity_id)

    removed: Counter = Counter()
    kept: list[dict] = []

    def edited(record) -> bool:
        stamp = getattr(record, "updated_at", None)
        return bool(marker and stamp and stamp > marker)

    def keep(entity_type: str, label: str) -> None:
        kept.append({"entity_type": entity_type, "label": label, "reason": oc.REVERT_KEPT_EDITED})

    actor = AuditActor(actor_type="user", user_id=str(user_id), real_user_id=str(user_id), job_id=str(run.id))
    with actor_scope(actor, db=db):
        for pso_id in ids.get(ENTITY_PSO, []):
            pso = db.get(ProjectSalesOrder, pso_id)
            if pso is None:
                continue
            if edited(pso):
                keep(ENTITY_PSO, f"Sales order {pso.provisional_ref}")
                continue
            db.delete(pso)
            removed[ENTITY_PSO] += 1
        db.flush()
        for po_id in ids.get(ENTITY_PO, []):
            po = db.get(ProjectPurchaseOrder, po_id)
            if po is None:
                continue
            label = f"PO {po.po_number} ({po.admin_ref})"
            has_child = (
                db.query(ProjectPurchaseOrderLine.id).filter(ProjectPurchaseOrderLine.po_id == po.id).first()
                or db.query(ProjectSalesOrder.id).filter(ProjectSalesOrder.purchase_order_id == po.id).first()
            )
            if edited(po) or has_child:
                keep(ENTITY_PO, label)
                continue
            delete_po(db, po=po)
            removed[ENTITY_PO] += 1
        gone_projects: list[str] = []
        for project_id in ids.get(ENTITY_PROJECT, []):
            project = db.get(Project, project_id)
            if project is None:
                continue
            label = " ".join(x for x in (project.project_code, project.title) if x)
            has_child = (
                db.query(ProjectPurchaseOrder.id).filter(ProjectPurchaseOrder.project_id == project.id).first()
                or db.query(ProjectSalesOrder.id).filter(ProjectSalesOrder.project_id == project.id).first()
                or db.query(ProjectQuotation.id).filter(ProjectQuotation.project_id == project.id).first()
            )
            profile = db.get(ProjectSalesProfile, project.id)
            if edited(project) or has_child or (profile is not None and edited(profile)):
                keep(ENTITY_PROJECT, label)
                if profile is not None and str(project.id) in ids.get(ENTITY_PROFILE, []):
                    keep(ENTITY_PROFILE, f"Sales details of {project.project_code}")
                continue
            if profile is not None:
                db.delete(profile)
                removed[ENTITY_PROFILE] += 1
            db.delete(project)
            db.flush()
            removed[ENTITY_PROJECT] += 1
            gone_projects.append(str(project_id))
        gone_parties: list[str] = []
        for party_id in ids.get(ENTITY_PARTY, []):
            party = db.get(ProjectParty, party_id)
            if party is None:
                continue
            used = db.query(Project.id).filter(Project.developer_party_id == party.id).first()
            if edited(party) or used:
                keep(ENTITY_PARTY, party.name)
                continue
            db.delete(party)
            db.flush()
            removed[ENTITY_PARTY] += 1
            gone_parties.append(str(party_id))
        # A line that linked to a record now gone goes back to "create", as a person set it.
        for m in db.query(ProjectImportValueMap).filter(
            ProjectImportValueMap.company_id == str(run.company_id),
            ProjectImportValueMap.target_id.in_(gone_projects + gone_parties or [""]),
        ):
            m.action, m.target_id = ACTION_CREATE, None
        db.flush()

    result = {"removed": dict(removed), "kept": kept}
    meta.update({"phase": PHASE_REVERTED, "reverted_at": datetime.utcnow().isoformat(),
                 "revert_result": result, "reverted_by": str(user_id)})
    _save_meta(db, run, meta)
    return result


def revert_by_id(db: Session, run_id: str, *, user_id: Optional[str]) -> dict:
    """The record action's handler: the run read in scope, then `revert`."""
    run = get_run(db, run_id)
    return revert(db, run, user_id=str(user_id or run.user_id))


def assert_revertable(db: Session, run_id: str) -> None:
    """Park-time check for the revert action: in scope and imported."""
    run = get_run(db, run_id)
    if _phase(run) != PHASE_IMPORTED:
        raise AppException(409, "Only an imported run can be reverted.", code="project_import_not_imported")


# --------------------------------------------------------------------------- listings


def serialize_run(db: Session, run: ImportJob, *, users: Optional[dict] = None, full: bool = False) -> dict:
    meta = _meta(run)
    counts = meta.get("result_counts") or meta.get("preview_counts") or {}
    if users is None:
        user = db.query(User).filter(User.id == run.user_id).first()
        users = {run.user_id: (user.name or user.email) if user else None}
    out = {
        "id": str(run.id),
        "run_no": meta.get("run_no"),
        "filename": run.filename,
        "status": meta.get("phase") or PHASE_DRAFT,
        "job_status": str(run.status.value if hasattr(run.status, "value") else run.status),
        "uploaded_by": users.get(run.user_id),
        "uploaded_by_id": run.user_id,
        "uploaded_at": run.created_at.isoformat() if run.created_at else None,
        "rows": run.total_rows or 0,
        "created": counts.get("created", 0),
        "skipped": counts.get("skipped", 0),
        "to_review": counts.get(oc.OUTCOME_NEEDS_REVIEW, 0),
        "imported_at": meta.get("imported_at"),
    }
    if full:
        ticked = {n.strip() for n in meta.get("sheets") or []}
        out.update({
            "sheets": [dict(p, ticked=p["name"].strip() in ticked) for p in meta.get("probe") or []],
            "columns": meta.get("columns") or {},
            "missing_columns": _missing_required(run),
            "preview_counts": meta.get("preview_counts"),
            "preview_codes": meta.get("preview_codes"),
            "result_counts": meta.get("result_counts"),
            "result_codes": meta.get("result_codes"),
            "sheet_errors": meta.get("sheet_errors") or [],
            "revert_result": meta.get("revert_result"),
            "reverted_at": meta.get("reverted_at"),
        })
    return out


_RUN_SORTS = ("run_no", "filename", "uploaded_by", "uploaded_at", "status", "rows", "created",
              "skipped", "to_review")


def list_runs(
    db: Session,
    *,
    page: int = 1,
    limit: int = 25,
    sort: Optional[str] = None,
    direction: Optional[str] = None,
    query: Optional[str] = None,
    status: Optional[list[str]] = None,
    uploaded_by: Optional[list[str]] = None,
) -> dict:
    from app.models.base import get_company_scope

    q = db.query(ImportJob).filter(ImportJob.job_type == JOB_TYPE)
    scope = get_company_scope(db)
    if isinstance(scope, frozenset):
        q = q.filter(ImportJob.company_id.in_([str(c) for c in scope] or [None]))
    elif scope is not None:
        q = q.filter(sa.false())
    runs = q.all()
    user_ids = {r.user_id for r in runs}
    users = {str(u.id): u.name or u.email for u in db.query(User).filter(User.id.in_(user_ids or {""}))}
    items = [serialize_run(db, r, users=users) for r in runs]
    if query:
        needle = query.strip().lower()
        items = [i for i in items if needle in (i["run_no"] or "").lower() or needle in (i["filename"] or "").lower()]
    if status:
        items = [i for i in items if i["status"] in status]
    if uploaded_by:
        items = [i for i in items if i["uploaded_by_id"] in uploaded_by]
    key = sort if sort in _RUN_SORTS else "uploaded_at"
    reverse = (direction or ("desc" if key == "uploaded_at" else "asc")).lower() == "desc"
    items.sort(key=lambda i: (i[key] is None, i[key] if i[key] is not None else ""), reverse=reverse)
    total = len(items)
    start = (page - 1) * limit
    return {"data": items[start:start + limit], "total": total, "page": page, "limit": limit}


def list_rows(
    db: Session,
    run: ImportJob,
    *,
    page: int = 1,
    limit: int = 50,
    outcome: Optional[list[str]] = None,
    code: Optional[list[str]] = None,
    sheet: Optional[list[str]] = None,
    query: Optional[str] = None,
) -> dict:
    """The run's report rows (preview or import), filtered and paged."""
    rows = (
        db.query(ImportJobRow)
        .filter(ImportJobRow.import_job_id == run.id, ImportJobRow.entity_id.is_(None))
        .order_by(ImportJobRow.created_at, ImportJobRow.row_number)
        .all()
    )
    sheet_rank: dict[str, int] = {}
    items = []
    for row in rows:
        ident = row.identity or {}
        name = ident.get("sheet") or ""
        sheet_rank.setdefault(name, len(sheet_rank))
        items.append({
            "sheet": name,
            "row_number": row.row_number,
            "ps_number": ident.get("ps_number"),
            "customer": ident.get("customer"),
            "project": ident.get("project"),
            "po_number": ident.get("po_number"),
            "po_date": ident.get("po_date"),
            "outcome": oc.OUTCOME_ERROR if row.outcome == oc.OUTCOME_FAILED else row.outcome,
            "codes": [c for c in (ident.get("codes") or "").split(",") if c],
            "message": row.message,
        })
    if outcome:
        items = [i for i in items if i["outcome"] in outcome]
    if code:
        items = [i for i in items if set(i["codes"]) & set(code)]
    if sheet:
        wanted = {s.strip() for s in sheet}
        items = [i for i in items if i["sheet"].strip() in wanted]
    if query:
        needle = query.strip().lower()
        items = [i for i in items if any(needle in str(i[k] or "").lower()
                                         for k in ("ps_number", "customer", "project", "po_number"))]
    items.sort(key=lambda i: (sheet_rank.get(i["sheet"], 0), i["row_number"] or 0))
    total = len(items)
    start = (page - 1) * limit
    return {"data": items[start:start + limit], "total": total, "page": page, "limit": limit}
