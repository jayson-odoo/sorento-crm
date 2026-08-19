"""Delivery-schedule intake: read the customer's matrix, then argue with it (P6).

A delivery schedule is a grid the customer drew: phase rows by product columns, the
quantity in the cell, grouped under an area heading such as TOWER or COMMON AREA, with
a TOTAL QTY row at the bottom. Every customer draws it differently and a main
contractor will not adopt our template (D13), so it is read rather than imported.

Four measured facts shape everything here, all from the 2026-08-02 spike over the
client's own R1 and R2 schedules (PLAN-project-lead-to-so.md 5c):

**Reconciliation is per COLUMN, never per document.** 29 of 37 columns reconciled on
the first vision pass of R1, 35 of 38 on R2. A document-level accept-or-reject would
reject nearly every real schedule; the confirm screen names the failing columns and a
person fixes those cells.

**The checksum has two independent sources.** The schedule's own TOTAL QTY row,
transcribed and not computed, and the PO quantity for the same product. A column is
reconciled when the column total equals the PO quantity and, where the document prints
one, the reported total too.

**It reconciles against the PO VERSION the schedule NAMES** (finding G1), not the
current amended state. The 4 March schedule still lists 16 of an item a 15 May pencil
note cancelled; measuring it against today's state would reject a document the customer
considers correct.

**Phase identity is `(area_group, sequence)` and never the label** (finding G6). The
COMMON AREA rows carry no label at all, and matching on the label collapsed three real
phases into one.

The intake is HYBRID, which is the shape the spike bought. These schedules are
spreadsheet prints and carry a text layer, so the quantities are lifted from it
geometrically -- exact, free and repeatable -- and the vision pass is left to do
STRUCTURE: which column is which product, which row is which phase and which area it
sits under. Measured on the real R1: 36 of 38 columns transcribed from the text layer
sum exactly to the printed TOTAL QTY row, against 29 of 37 for vision alone. Where a
page's grid cannot be corroborated the vision numbers stand and the checksum flags what
it flags -- a scanned schedule with no text layer takes that path for the whole
document, which is the fallback working rather than a degradation.
"""
from __future__ import annotations

import copy
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.models.order import Customer
from app.models.product import Product
from app.models.project_so import (
    AUTHORED_LIVE_STATUSES,
    CustomerItemCodeMap,
    DeliverySchedule,
    DeliveryScheduleCell,
    DeliveryScheduleVersion,
    ProjectDeliveryPhase,
    ProjectPOLine,
    ProjectPOVersion,
    ProjectSalesOrder,
)
from app.models.projects import (
    Project,
    ProjectParty,
    ProjectPurchaseOrder,
    ProjectPurchaseOrderLine,
)
from app.services.error_handler import AppException

logger = logging.getLogger(__name__)

STATE_QUEUED = "queued"
STATE_RUNNING = "running"
STATE_DONE = "done"
# Some pages answered and some did not. A separate state rather than a flag, because
# "done" beside an error message reads as a contradiction on screen.
STATE_PARTIAL = "partial"
STATE_FAILED = "failed"

# Where the uploaded document hangs. One attachment type for every phase-2 project
# document, so the Files admin has one row to configure rather than one per slice.
ATTACHMENT_ENTITY_TYPE = "delivery_schedule_version"
ATTACHMENT_TYPE_CODE = "project_document"

# A fuzzy product match is allowed to resolve a column only when it is both strong and
# unambiguous. A wrong product here becomes a wrong commitment, so the floor is high
# and a near-tie is left unresolved for a person rather than guessed.
TRIGRAM_FLOOR = 0.72
TRIGRAM_MARGIN = 0.08
# pg_trgm lives in ``public`` and is schema-qualified deliberately: tests pin
# search_path to a scratch schema so raw SQL cannot reach the real tables.
_TRGM_SCHEMA = "public"

# Section 9.7(b): a page note naming a date, DAY-first, the same convention pinned
# in `_parse_date`. `d/m/yyyy` or `dd/mm/yyyy`, one to two digits each side.
_NOTE_DATE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")

PROPOSAL_PROPOSED = "proposed"
PROPOSAL_ACCEPTED = "accepted"
PROPOSAL_REJECTED = "rejected"

_RESOLUTION_MAP = "map"
_RESOLUTION_CODE = "code"
_RESOLUTION_TRIGRAM = "trigram"
_RESOLUTION_MANUAL = "manual"


# --------------------------------------------------------------------- quantities


def qty_str(value: Optional[Decimal]) -> Optional[str]:
    """Quantities cross the wire as strings. A float round trip loses cents on a 1.8
    million ringgit PO, and the same discipline applies to the counts beside it."""
    if value is None:
        return None
    normalised = Decimal(value).normalize()
    if normalised == normalised.to_integral_value():
        normalised = normalised.quantize(Decimal(1))
    return format(normalised, "f")


def to_decimal(value: Any) -> Optional[Decimal]:
    """Anything the model or a person typed, as a Decimal, or None if it is not one."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value
    text_value = str(value).strip().replace(",", "")
    if not text_value:
        return None
    try:
        return Decimal(text_value)
    except InvalidOperation:
        return None


def _parse_date(value: Any) -> Optional[date]:
    """ISO first (what the prompt asks the model for), then a slash date DAY-first.

    Pinned 19 August 2026: the extractor read the same schedule's own "7/1/2027" as
    2027-07-01 on one page and 2027-01-07 on the others, because nothing told it
    which convention the customer writes in. The customer writes DAY/MONTH/YEAR, so
    a slash date reaching this function unconverted is read that way -- never
    month-first, and never guessed from calendar order.
    """
    if isinstance(value, date):
        return value
    if not value:
        return None
    text = str(value).strip()
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        pass
    try:
        return datetime.strptime(text, "%d/%m/%Y").date()
    except ValueError:
        return None


def _dated_note(data: dict) -> Optional[Tuple[str, date]]:
    """The first free-text note on a page that names a day-first date, and the date.

    Section 9.7(b): a note without a date proposes nothing (there is nothing to
    re-date TO), so this returns ``None`` and the caller records no proposal.
    """
    for note in data.get("notes") or []:
        if not isinstance(note, str):
            continue
        match = _NOTE_DATE.search(note)
        if not match:
            continue
        day, month, year = (int(part) for part in match.groups())
        try:
            return note.strip(), date(year, month, day)
        except ValueError:
            continue
    return None


def _clean(value: Any, limit: int = 180) -> Optional[str]:
    if value is None:
        return None
    text_value = str(value).strip()
    return text_value[:limit] or None


# ---------------------------------------------------------------- the text layer


_CODE_TOKEN = re.compile(r"^[A-Z0-9][A-Z0-9/\-]*\d[A-Z0-9/\-]*$")
_QTY_TOKEN = re.compile(r"^\d{1,3}(?:,\d{3})*(?:\.\d+)?$|^\d+(?:\.\d+)?$")
_ROW_TOLERANCE = 4.0  # points; rows on these prints sit ~11 apart
_COLUMN_TOLERANCE = 6.0
_COLUMN_SNAP = 12.0


@dataclass
class TextLayerPage:
    """One page of the matrix, read from the PDF's own text rather than from a model.

    ``rows`` are in printed order and map column index to quantity; a blank cell is
    ABSENT, never zero, because a blank means this phase does not take this product.

    ``grid_proven`` is the corroboration rule that makes the numbers usable: a page's
    grid is proven by the columns that carry a printed total, and where every one of
    them equals the sum of its own column the transcription of the remaining columns is
    trusted too. One column short means a row was misread, so the whole page is left to
    vision rather than half-believed.
    """

    page_no: int
    column_count: int
    header_codes: List[str] = field(default_factory=list)
    rows: List[Dict[int, Decimal]] = field(default_factory=list)
    totals: Dict[int, Decimal] = field(default_factory=dict)
    # Section 9.7(a): one entry per row, column index -> `#rrggbb`, for a cell that
    # sits inside a coloured fill on the page (grey/black/white excluded). Parallel
    # to `rows`, never merged into it: a highlight is not a quantity.
    highlights: List[Dict[int, str]] = field(default_factory=list)

    @property
    def grid_proven(self) -> bool:
        checked = 0
        for index in range(self.column_count):
            reported = self.totals.get(index)
            if reported is None:
                continue
            checked += 1
            if sum((row.get(index, Decimal(0)) for row in self.rows), Decimal(0)) != reported:
                return False
        return checked > 0


def _display_words(page) -> List[Tuple[Any, str]]:
    """Words in DISPLAY space. These sheets are printed rotated, so the raw coordinates
    have rows running vertically; the page's own rotation matrix undoes that and the
    rest of this parser can assume rows are horizontal on every document."""
    import fitz

    matrix = page.rotation_matrix
    return [(fitz.Rect(w[:4]) * matrix, w[4]) for w in page.get_text("words")]


# A fill within this tolerance on every channel reads as grey, black or white --
# a border, a gridline, a header band -- and is never a revision highlight
# (section 9.7a, measured on the real R2 page 7: rose fills at (0.86,0.59,0.58)
# and (0.9,0.72,0.72), nothing near-grey in between).
_GREY_TOLERANCE = 0.05

# A generic tint for a cell the VISION pass alone flagged `highlighted: true`: the
# model reports a boolean, never the printed colour, so this is what renders when
# no text-layer geometry is available to say the real one.
_VISION_HIGHLIGHT_HEX = "#e5b8b8"


def _is_colored_fill(rgb: Optional[Sequence[float]]) -> bool:
    if not rgb or len(rgb) < 3:
        return False
    r, g, b = rgb[0], rgb[1], rgb[2]
    return (max(r, g, b) - min(r, g, b)) > _GREY_TOLERANCE


def _fill_hex(rgb: Sequence[float]) -> str:
    r, g, b = rgb[0], rgb[1], rgb[2]
    return "#%02x%02x%02x" % (
        round(max(0.0, min(1.0, r)) * 255),
        round(max(0.0, min(1.0, g)) * 255),
        round(max(0.0, min(1.0, b)) * 255),
    )


def _colored_fills(page) -> List[Tuple[Any, str]]:
    """Coloured rectangular fills on the page, in DISPLAY space.

    ``page.get_drawings()`` reports every filled shape, borders and header bands
    included; ``_is_colored_fill`` is what tells a customer's rose highlight from
    the sheet's own grid lines.
    """
    import fitz

    matrix = page.rotation_matrix
    out: List[Tuple[Any, str]] = []
    for drawing in page.get_drawings():
        fill = drawing.get("fill")
        if not _is_colored_fill(fill):
            continue
        rect = drawing.get("rect")
        if rect is None:
            continue
        out.append((fitz.Rect(rect) * matrix, _fill_hex(fill)))
    return out


def _highlight_at(rect, fills: List[Tuple[Any, str]]) -> Optional[str]:
    """The colour of the fill this cell's own rect sits inside, first match wins."""
    for fill_rect, hex_color in fills:
        if rect.intersects(fill_rect):
            return hex_color
    return None


def _cluster(items, key, tolerance: float):
    groups: List[Tuple[List[float], List[Any]]] = []
    for item in sorted(items, key=key):
        centre = key(item)
        if groups and abs(centre - groups[-1][0][-1]) <= tolerance:
            groups[-1][0].append(centre)
            groups[-1][1].append(item)
        else:
            groups.append(([centre], [item]))
    return [(sum(cs) / len(cs), members) for cs, members in groups]


def _qty_token(word: str) -> Optional[Decimal]:
    cleaned = word.replace(",", "")
    return Decimal(cleaned) if _QTY_TOKEN.match(cleaned) else None


def _parse_text_page(page, page_no: int) -> Optional[TextLayerPage]:
    words = _display_words(page)
    if not words:
        return None

    # The header line is the printed line carrying the most code-like tokens. Its
    # LEFTMOST word marks where column one begins, which is also where the label and
    # date column ends -- one measurement that locates both axes.
    lines: Dict[float, List[Tuple[Any, str]]] = {}
    for rect, word in words:
        lines.setdefault(round(rect.y0, 1), []).append((rect, word))
    header = None
    for _key, group in sorted(lines.items()):
        codes = [(r, w) for r, w in group if len(w) >= 5 and _CODE_TOKEN.match(w)]
        if codes and (header is None or len(codes) > len(header[1])):
            header = (group, codes)
    if header is None:
        return None
    header_line, code_words = header
    label_x = min(rect.x0 for rect, _ in header_line)
    header_bottom = max(rect.y1 for rect, _ in header_line)

    body = [(r, w) for r, w in words if r.y0 > header_bottom]
    label_words = [(r, w) for r, w in body if (r.x0 + r.x1) / 2 < label_x]
    candidate_rows = _cluster(label_words, lambda it: (it[0].y0 + it[0].y1) / 2, _ROW_TOLERANCE)

    def numbers_at(centre: float):
        return [
            (r, w)
            for r, w in body
            if (r.x0 + r.x1) / 2 >= label_x
            and abs((r.y0 + r.y1) / 2 - centre) <= _ROW_TOLERANCE
            and _qty_token(w) is not None
        ]

    # The matrix body is bracketed by the first and last rows that carry a number in
    # the data region. Above it sit the product descriptions and the sheet's title
    # block, both of which contain numbers ("Size : 700 x 380mm") that would otherwise
    # be read as quantities.
    filled = [centre for centre, _ in candidate_rows if numbers_at(centre)]
    if not filled:
        return None
    first, last = min(filled), max(filled)

    totals_centre = None
    data_centres: List[float] = []
    for centre, group in candidate_rows:
        if not first <= centre <= last:
            continue
        if "TOTAL" in " ".join(word for _, word in group).upper():
            totals_centre = centre
        else:
            data_centres.append(centre)

    measured = []
    for centre in data_centres + ([totals_centre] if totals_centre is not None else []):
        measured.extend(numbers_at(centre))
    if not measured:
        return None

    # Columns are discovered from where the numbers actually fall, not from where the
    # header codes start: on the real R1 one page heads a column with a bare code and
    # another with a brand word first, so the code's offset inside its cell varies.
    centres = [c for c, _ in _cluster(measured, lambda it: (it[0].x0 + it[0].x1) / 2, _COLUMN_TOLERANCE)]

    def column_of(rect) -> Optional[int]:
        middle = (rect.x0 + rect.x1) / 2
        best_index, best_distance = None, None
        for index, centre in enumerate(centres):
            distance = abs(middle - centre)
            if best_distance is None or distance < best_distance:
                best_index, best_distance = index, distance
        return best_index if best_distance is not None and best_distance <= _COLUMN_SNAP else None

    def cells_at(centre: float) -> Dict[int, Decimal]:
        out: Dict[int, Decimal] = {}
        for rect, word in numbers_at(centre):
            index = column_of(rect)
            value = _qty_token(word)
            if index is not None and value is not None:
                out[index] = value
        return out

    # Section 9.7(a): the same cells, tagged with the colour of the fill they sit
    # inside. A cell with no coloured fill under it is simply absent from the map.
    fills = _colored_fills(page)

    def highlights_at(centre: float) -> Dict[int, str]:
        out: Dict[int, str] = {}
        for rect, word in numbers_at(centre):
            index = column_of(rect)
            if index is None or _qty_token(word) is None:
                continue
            color = _highlight_at(rect, fills)
            if color:
                out[index] = color
        return out

    return TextLayerPage(
        page_no=page_no,
        column_count=len(centres),
        header_codes=[word for _, word in sorted(code_words, key=lambda it: it[0].x0)],
        rows=[cells_at(centre) for centre in data_centres],
        totals=cells_at(totals_centre) if totals_centre is not None else {},
        highlights=[highlights_at(centre) for centre in data_centres],
    )


def parse_text_matrix(content: bytes, mime: str) -> Dict[int, TextLayerPage]:
    """Every page of the document that yields a matrix, keyed by 1-based page number.

    A scan has no text layer and returns nothing at all, which is the correct answer:
    the caller then keeps what the vision pass said.
    """
    if (mime or "").lower() not in ("application/pdf", "application/x-pdf"):
        return {}
    try:
        import fitz
    except Exception:  # noqa: BLE001 - the cross-check is an optimisation, never a gate
        logger.warning("PyMuPDF unavailable; schedule text-layer cross-check skipped")
        return {}

    pages: Dict[int, TextLayerPage] = {}
    try:
        document = fitz.open(stream=content, filetype="pdf")
    except Exception:  # noqa: BLE001
        logger.warning("schedule text-layer parse could not open the document", exc_info=True)
        return {}
    try:
        for index, page in enumerate(document, start=1):
            try:
                parsed = _parse_text_page(page, index)
            except Exception:  # noqa: BLE001 - one bad page must not lose the rest
                logger.warning("schedule text-layer parse failed on page %s", index, exc_info=True)
                parsed = None
            if parsed is not None:
                pages[index] = parsed
    finally:
        document.close()
    return pages


# ------------------------------------------------------------- in-flight structures


@dataclass
class _Phase:
    area_group: str
    sequence: int
    label: Optional[str] = None
    delivery_date: Optional[date] = None
    phase_id: Optional[str] = None

    @property
    def key(self) -> Tuple[str, int]:
        return (self.area_group, self.sequence)


@dataclass
class _Column:
    index: int
    page_no: int
    customer_code_raw: Optional[str]
    header_code: Optional[str]
    name: Optional[str]
    cells: Dict[Tuple[str, int], Decimal] = field(default_factory=dict)
    # Section 9.7(a): phase key -> `#rrggbb`, for a cell the document tints. Empty
    # for a column nothing highlights.
    cell_highlights: Dict[Tuple[str, int], str] = field(default_factory=dict)
    reported_total: Optional[Decimal] = None
    reported_total_source: Optional[str] = None
    qty_source: str = "vision"
    product_id: Optional[str] = None
    resolution_source: Optional[str] = None

    @property
    def key(self) -> str:
        if self.product_id:
            return f"product:{self.product_id}"
        return f"raw:{(self.customer_code_raw or '').upper()}"


# ------------------------------------------------------------------------ service


class ProjectScheduleService:
    """Everything a delivery schedule does between arriving and binding."""

    def __init__(self, db: Session):
        self.db = db
        # Set by read_document so run_extraction can report the model and the pages that
        # did not answer without threading them through persistence.
        self._last_extraction = None

    # ------------------------------------------------------------------ lookups

    def get_version(self, version_id: str) -> DeliveryScheduleVersion:
        version = self.db.get(DeliveryScheduleVersion, version_id)
        if version is None:
            raise AppException(
                status_code=404,
                message="Delivery schedule version not found.",
                code="schedule_version_not_found",
            )
        return version

    def schedule_for(self, version: DeliveryScheduleVersion) -> DeliverySchedule:
        schedule = self.db.get(DeliverySchedule, version.delivery_schedule_id)
        if schedule is None:
            raise AppException(
                status_code=404,
                message="Delivery schedule not found.",
                code="delivery_schedule_not_found",
            )
        return schedule

    # ------------------------------------------------------------------- upload

    def create_version(
        self,
        *,
        purchase_order: ProjectPurchaseOrder,
        content: bytes,
        filename: str,
        mime: str,
        actor_user_id: Optional[str],
        issuer_party_id: Optional[str] = None,
        revision_label: Optional[str] = None,
        delivery_schedule_id: Optional[str] = None,
        po_version_id: Optional[str] = None,
        page_count: Optional[int] = None,
    ) -> DeliveryScheduleVersion:
        """Store the document and open a version for it. Extraction happens later.

        ``po_version_id`` is what the checksum will reconcile AGAINST and defaults to
        the PO's latest CONFIRMED version, because that is the document the customer
        was working from when they drew the schedule (finding G1).
        """
        schedule = self._resolve_schedule(purchase_order, delivery_schedule_id, issuer_party_id)
        if issuer_party_id and schedule.issuer_party_id != issuer_party_id:
            self._assert_party(issuer_party_id)
            schedule.issuer_party_id = issuer_party_id

        resolved_po_version = self._resolve_po_version(purchase_order, po_version_id)
        next_no = (
            self.db.query(func.coalesce(func.max(DeliveryScheduleVersion.version_no), 0))
            .filter(DeliveryScheduleVersion.delivery_schedule_id == schedule.id)
            .scalar()
        ) + 1

        version = DeliveryScheduleVersion(
            company_id=schedule.company_id,
            delivery_schedule_id=schedule.id,
            version_no=next_no,
            revision_label=_clean(revision_label, 80),
            po_version_id=resolved_po_version.id if resolved_po_version else None,
            source_filename=_clean(filename, 255),
            extraction_state=STATE_QUEUED,
            # The page count is known here and nowhere else cheaply, and the confirm
            # screen needs it to say "4 of 7 pages read" rather than just "working".
            extracted_json={"page_count": page_count} if page_count else None,
        )
        self.db.add(version)
        self.db.flush()

        version.attachment_id = self._store_document(
            version, content=content, filename=filename, mime=mime, actor_user_id=actor_user_id
        )
        self.db.flush()
        return version

    def enqueue_extraction(self, version: DeliveryScheduleVersion) -> Optional[str]:
        """Hand the version to the project-documents queue. Call AFTER the commit.

        Same helper as the customer PO path, for the same two reasons: the queue name
        lives in one place, and the job id is recorded on the row so that a read whose
        work-horse is later killed can be told apart from one that is merely slow. A
        killed process does not run its own error handling, so nothing inside it can
        report the death (S20).
        """
        from app.services import project_extraction_recovery_service as recovery

        return recovery.start_job(self.db, version)

    def reconcile_stranded(self, versions) -> int:
        """Give a verdict to any of these reads whose worker died. See S20."""
        from app.services import project_extraction_recovery_service as recovery

        return recovery.reconcile(self.db, versions)

    def retry_extraction(self, version: DeliveryScheduleVersion) -> DeliveryScheduleVersion:
        """Read this schedule again, on the same version. 409 when there is nothing to
        retry: still in flight, already read, or confirmed."""
        from app.services import project_extraction_recovery_service as recovery

        return recovery.retry(self.db, version)

    def _resolve_schedule(
        self,
        purchase_order: ProjectPurchaseOrder,
        delivery_schedule_id: Optional[str],
        issuer_party_id: Optional[str],
    ) -> DeliverySchedule:
        if delivery_schedule_id:
            schedule = self.db.get(DeliverySchedule, delivery_schedule_id)
            if schedule is None or schedule.purchase_order_id != purchase_order.id:
                raise AppException(
                    status_code=404,
                    message="That delivery schedule does not belong to this purchase order.",
                    code="delivery_schedule_not_found",
                )
            return schedule

        existing = (
            self.db.query(DeliverySchedule)
            .filter(DeliverySchedule.purchase_order_id == purchase_order.id)
            .order_by(DeliverySchedule.created_at.asc())
            .first()
        )
        if existing is not None:
            return existing

        if issuer_party_id:
            self._assert_party(issuer_party_id)
        schedule = DeliverySchedule(
            company_id=purchase_order.company_id,
            project_id=purchase_order.project_id,
            purchase_order_id=purchase_order.id,
            issuer_party_id=issuer_party_id,
        )
        self.db.add(schedule)
        self.db.flush()
        return schedule

    def _assert_party(self, party_id: str) -> None:
        if self.db.get(ProjectParty, party_id) is None:
            raise AppException(
                status_code=404,
                message="The issuing company is not on file.",
                code="issuer_party_not_found",
            )

    def _resolve_po_version(
        self, purchase_order: ProjectPurchaseOrder, po_version_id: Optional[str]
    ) -> Optional[ProjectPOVersion]:
        query = self.db.query(ProjectPOVersion).filter(
            ProjectPOVersion.purchase_order_id == purchase_order.id
        )
        if po_version_id:
            version = query.filter(ProjectPOVersion.id == po_version_id).first()
            if version is None:
                raise AppException(
                    status_code=404,
                    message="That PO version does not belong to this purchase order.",
                    code="po_version_not_found",
                )
            return version
        confirmed = (
            query.filter(ProjectPOVersion.confirmed_at.isnot(None))
            .order_by(ProjectPOVersion.version_no.desc())
            .first()
        )
        return confirmed or query.order_by(ProjectPOVersion.version_no.desc()).first()

    def _store_document(
        self,
        version: DeliveryScheduleVersion,
        *,
        content: bytes,
        filename: str,
        mime: str,
        actor_user_id: Optional[str],
    ) -> Optional[str]:
        from app.services.entity_attachment_service import EntityAttachmentService
        from app.services.storage_router import (
            cdn_base_url,
            default_provider,
            get_backend,
            sanitize_storage_filename,
        )

        self._ensure_attachment_type()
        safe_name = sanitize_storage_filename(filename) or "delivery-schedule.pdf"
        provider = default_provider()
        key, _ = get_backend(provider).upload_file(
            file_content=content,
            file_path=f"{ATTACHMENT_ENTITY_TYPE}/{version.id}/{safe_name}",
            content_type=mime,
        )
        link = EntityAttachmentService(self.db).create_attachment_and_link(
            entity_type=ATTACHMENT_ENTITY_TYPE,
            entity_id=str(version.id),
            file_url=cdn_base_url(provider, key),
            file_name=filename,
            file_size_bytes=len(content),
            attachment_type_code=ATTACHMENT_TYPE_CODE,
            created_by=actor_user_id,
            storage_provider=provider,
        )
        if link.attachment is not None:
            # Set here rather than in the shared helper: re-reading the document on the
            # worker needs to know whether it is a PDF or a photograph.
            link.attachment.mime_type = _clean(mime, 100)
        return str(link.attachment_id)

    def _ensure_attachment_type(self) -> None:
        """One project-document type, created on first use.

        Seeded here rather than in a migration because the type is reference data the
        feature owns: an install that never uploads a project document never needs it.
        """
        from app.models.resources import AttachmentType

        existing = (
            self.db.query(AttachmentType)
            .filter(AttachmentType.code == ATTACHMENT_TYPE_CODE)
            .first()
        )
        if existing is not None:
            return
        self.db.add(
            AttachmentType(
                code=ATTACHMENT_TYPE_CODE,
                type_name="Project Document",
                description="Customer purchase orders and delivery schedules (project sales).",
                allowed_extensions="pdf,jpg,jpeg,png",
                max_file_size_mb=30,
            )
        )
        self.db.flush()

    def document_url(self, version: DeliveryScheduleVersion) -> Optional[str]:
        """A signed URL for the side-by-side viewer. Never a stored signed URL: they
        expire, and a detail page that 403s a week later reads as lost data."""
        if not version.attachment_id:
            return None
        from app.models.resources import Attachment
        from app.services.storage_router import resolve_signed_url

        attachment = self.db.get(Attachment, version.attachment_id)
        if attachment is None or not attachment.file_path:
            return None
        try:
            return resolve_signed_url(
                attachment.file_path, provider=attachment.storage_provider
            )
        except Exception:  # noqa: BLE001 - a missing preview must not 500 the page
            logger.warning(
                "could not sign the schedule document for version %s", version.id, exc_info=True
            )
            return None

    def _document_bytes(self, version: DeliveryScheduleVersion) -> Tuple[bytes, str]:
        from app.models.resources import Attachment
        from app.services.storage_router import extract_key, get_backend

        if not version.attachment_id:
            raise AppException(
                status_code=422,
                message="This schedule version has no document to read.",
                code="schedule_document_missing",
            )
        attachment = self.db.get(Attachment, version.attachment_id)
        key = extract_key(getattr(attachment, "file_path", None)) if attachment else None
        if attachment is None or not key:
            raise AppException(
                status_code=422,
                message="The stored document could not be located.",
                code="schedule_document_missing",
            )
        content = get_backend(attachment.storage_provider).download_file(key)
        mime = attachment.mime_type or self._guess_mime(version.source_filename)
        return content, mime

    @staticmethod
    def _guess_mime(filename: Optional[str]) -> str:
        lowered = (filename or "").lower()
        if lowered.endswith(".png"):
            return "image/png"
        if lowered.endswith((".jpg", ".jpeg")):
            return "image/jpeg"
        return "application/pdf"

    # --------------------------------------------------------------- extraction

    def read_document(self, content: bytes, mime: str) -> List[Tuple[int, dict]]:
        """The vision pass. Returns (page_no, answer) for every page that answered."""
        from app.services.document_extraction import extract_document

        result = extract_document(self.db, content, mime, prompt_key="schedule_extractor")
        self._last_extraction = result
        return [
            (page.page_no, page.data) for page in result.ok_pages if page.data is not None
        ]

    def run_extraction(self, schedule_version_id: str) -> dict:
        """Entry point for the RQ task. Always leaves a terminal state behind.

        A page that fails does not fail the document: nine good pages is a schedule a
        person can finish, an exception is one they cannot start.
        """
        from app.services.document_extraction import ExtractionUnavailable

        from app.services import project_extraction_recovery_service as recovery

        version = self.get_version(schedule_version_id)
        version.extraction_state = STATE_RUNNING
        version.extraction_error = None
        # Only the reader knows when it actually picked the document up. See S20.
        recovery.mark_started(self.db, version)
        self.db.commit()

        try:
            content, mime = self._document_bytes(version)
            pages = self.read_document(content, mime)
            result = getattr(self, "_last_extraction", None)
            if result is not None:
                version.extraction_model = result.model
                version.extraction_elapsed_ms = result.elapsed_ms or None
            if not pages:
                raise AppException(
                    status_code=422,
                    message="Nothing could be read from this document.",
                    code="schedule_extraction_empty",
                )
            summary = self.persist_pages(
                version, pages, text_pages=parse_text_matrix(content, mime)
            )
            failed = list(result.failed_pages) if result is not None else []
            # PARTIAL is a first-class outcome, not an error: the pages that answered
            # are usable, and naming the ones that did not is what lets a person finish
            # the job. `pages_extracted < page_count` says the same thing arithmetically.
            version.extraction_state = STATE_PARTIAL if failed else STATE_DONE
            if failed:
                version.extraction_error = (
                    f"Pages {', '.join(str(p) for p in failed)} could not be read; "
                    "the rest of the schedule was."
                )
            self.db.commit()
            return {"status": version.extraction_state, "version_id": str(version.id),
                    "failed_pages": failed, **summary}
        except ExtractionUnavailable as exc:
            self.db.rollback()
            return self._fail(version, str(exc))
        except AppException as exc:
            self.db.rollback()
            detail = exc.detail if isinstance(exc.detail, dict) else {}
            return self._fail(version, str(detail.get("message") or exc.detail))
        except Exception as exc:  # noqa: BLE001 - the row must never stay on "running"
            self.db.rollback()
            logger.exception("schedule extraction failed for version %s", schedule_version_id)
            return self._fail(version, str(exc))

    def _fail(self, version: DeliveryScheduleVersion, message: str) -> dict:
        version.extraction_state = STATE_FAILED
        version.extraction_error = message[:500]
        self.db.commit()
        return {"status": STATE_FAILED, "version_id": str(version.id), "error": message[:300]}

    # -------------------------------------------------------------- persistence

    def persist_pages(
        self,
        version: DeliveryScheduleVersion,
        pages: Sequence[Tuple[int, dict]],
        text_pages: Optional[Dict[int, TextLayerPage]] = None,
    ) -> dict:
        """Turn the extractor's per-page answers into phases, cells and a verdict.

        Re-running this on the same version replaces its cells and leaves the project's
        phases where they are: phases are upserted on their identity, so a second read
        after a prompt change cannot leave the project holding two of every row.
        """
        schedule = self.schedule_for(version)
        project = self.db.get(Project, schedule.project_id)
        header = self._merge_header(pages)
        version.extracted_json = {
            # Carried forward from the upload: it is how many pages the DOCUMENT has,
            # against how many answered.
            "page_count": (version.extracted_json or {}).get("page_count"),
            "pages": [{"page_no": no, "data": data} for no, data in pages],
        }
        if header.get("schedule_date"):
            version.schedule_date = header["schedule_date"]
        if header.get("revision") and not version.revision_label:
            version.revision_label = _clean(header["revision"], 80)

        phases, columns = self._read_pages(pages, text_pages or {})
        self._resolve_columns(version, schedule, columns)
        columns = self._merge_duplicate_columns(columns)
        self._upsert_phases(version, project, phases)
        self._write_cells(version, phases, columns)
        self._build_revision_proposals(version, phases, columns, pages)
        return self._reconcile(version, schedule, phases, columns, header)

    def _merge_header(self, pages: Sequence[Tuple[int, dict]]) -> dict:
        """First page that says something wins. Later pages repeat the same block."""
        merged: Dict[str, Any] = {}
        for _page_no, data in pages:
            block = (data or {}).get("header") or {}
            for field_name in ("project", "po_ref", "revision"):
                if not merged.get(field_name) and block.get(field_name):
                    merged[field_name] = _clean(block[field_name])
            if not merged.get("schedule_date"):
                parsed = _parse_date(block.get("schedule_date"))
                if parsed:
                    merged["schedule_date"] = parsed
        return merged

    def _read_pages(
        self, pages: Sequence[Tuple[int, dict]], text_pages: Dict[int, TextLayerPage]
    ) -> Tuple[List[_Phase], List[_Column]]:
        """Structure from the vision pass, quantities from the text layer where it
        corroborates itself. Column order and row order are the join between them:
        both read the sheet left to right and top to bottom."""
        phases: Dict[Tuple[str, int], _Phase] = {}
        columns: List[_Column] = []

        for page_no, data in pages:
            data = data or {}
            page_phases = self._page_phases(data)
            page_columns = self._page_columns(data, page_no, len(columns))

            for phase in page_phases:
                existing = phases.get(phase.key)
                if existing is None:
                    phases[phase.key] = phase
                    continue
                if existing.label is None and phase.label:
                    existing.label = phase.label
                if existing.delivery_date is None and phase.delivery_date:
                    existing.delivery_date = phase.delivery_date

            quantities = self._page_quantities(data, page_phases, page_columns)
            reported = self._page_reported_totals(data, page_columns)
            # Section 9.7(a): the vision pass's own `highlighted` flag, kept only as
            # the fallback -- overwritten below by the text layer's real colour
            # whenever the text layer is what this page's quantities trust too.
            highlights = self._page_vision_highlights(data, page_phases, page_columns)
            source = "vision"

            text_page = text_pages.get(page_no)
            if (
                text_page is not None
                and text_page.grid_proven
                and len(text_page.rows) == len(page_phases)
                and text_page.column_count == len(page_columns)
            ):
                quantities = {
                    (page_phases[row_index].key, page_columns[col_index].index): value
                    for row_index, row in enumerate(text_page.rows)
                    for col_index, value in row.items()
                    if col_index < len(page_columns)
                }
                reported = {
                    page_columns[col_index].index: value
                    for col_index, value in text_page.totals.items()
                    if col_index < len(page_columns)
                }
                highlights = {
                    (page_phases[row_index].key, page_columns[col_index].index): color
                    for row_index, row in enumerate(text_page.highlights)
                    for col_index, color in row.items()
                    if col_index < len(page_columns)
                }
                source = "text_layer"

            by_index = {column.index: column for column in page_columns}
            for column in page_columns:
                column.qty_source = source
                column.reported_total = reported.get(column.index)
                column.reported_total_source = (
                    source if column.reported_total is not None else None
                )
            for (phase_key, column_index), value in quantities.items():
                column = by_index.get(column_index)
                if column is not None:
                    column.cells[phase_key] = value
            for (phase_key, column_index), color in highlights.items():
                column = by_index.get(column_index)
                if column is not None:
                    column.cell_highlights[phase_key] = color
            columns.extend(page_columns)

        ordered = sorted(phases.values(), key=lambda p: (p.area_group, p.sequence))
        return ordered, columns

    def _page_phases(self, data: dict) -> List[_Phase]:
        """Rows in printed order, numbered within their area group.

        The sequence is the identity (finding G6). The COMMON AREA rows carry no label
        at all, so a label-keyed merge collapsed three real phases into one.
        """
        raw = data.get("phases") or []
        ordered = sorted(
            enumerate(raw), key=lambda pair: (_row_ordinal(pair[1], pair[0]), pair[0])
        )
        counters: Dict[str, int] = {}
        out: List[_Phase] = []
        for _index, row in ordered:
            area = _clean(row.get("area_group"), 80) or "UNGROUPED"
            counters[area] = counters.get(area, 0) + 1
            out.append(
                _Phase(
                    area_group=area,
                    sequence=counters[area],
                    label=_clean(row.get("label")),
                    delivery_date=_parse_date(row.get("delivery_date")),
                )
            )
        return out

    def _page_columns(self, data: dict, page_no: int, offset: int) -> List[_Column]:
        raw = data.get("products") or []
        ordered = sorted(
            enumerate(raw), key=lambda pair: (_col_ordinal(pair[1], pair[0]), pair[0])
        )
        return [
            _Column(
                index=offset + position,
                page_no=page_no,
                customer_code_raw=_clean(item.get("customer_code")) or _clean(item.get("code")),
                header_code=_clean(item.get("code"), 100),
                name=_clean(item.get("name"), 255),
            )
            for position, (_index, item) in enumerate(ordered)
        ]

    def _page_quantities(
        self, data: dict, page_phases: List[_Phase], page_columns: List[_Column]
    ) -> Dict[Tuple[Tuple[str, int], int], Decimal]:
        """The vision pass's cells, addressed by the row and column numbers it gave."""
        rows_by_number = {index + 1: phase for index, phase in enumerate(page_phases)}
        cols_by_number = {index + 1: column for index, column in enumerate(page_columns)}
        out: Dict[Tuple[Tuple[str, int], int], Decimal] = {}
        for cell in data.get("cells") or []:
            phase = rows_by_number.get(_as_int(cell.get("row")))
            column = cols_by_number.get(_as_int(cell.get("col")))
            value = to_decimal(cell.get("qty"))
            # A zero is dropped with the blanks: a printed zero and an empty cell both
            # mean this phase does not take this product.
            if phase is None or column is None or value is None or value == 0:
                continue
            out[(phase.key, column.index)] = value
        return out

    def _page_vision_highlights(
        self, data: dict, page_phases: List[_Phase], page_columns: List[_Column]
    ) -> Dict[Tuple[Tuple[str, int], int], str]:
        """The vision pass's own `highlighted` flag, rendered with a generic tint.

        The model reports a boolean, not the printed colour, so this is the
        fallback: the text layer's real `#rrggbb` (``TextLayerPage.highlights``)
        overwrites it in ``_read_pages`` whenever the text layer is what the page's
        quantities trust.
        """
        rows_by_number = {index + 1: phase for index, phase in enumerate(page_phases)}
        cols_by_number = {index + 1: column for index, column in enumerate(page_columns)}
        out: Dict[Tuple[Tuple[str, int], int], str] = {}
        for cell in data.get("cells") or []:
            if not cell.get("highlighted"):
                continue
            phase = rows_by_number.get(_as_int(cell.get("row")))
            column = cols_by_number.get(_as_int(cell.get("col")))
            if phase is None or column is None:
                continue
            out[(phase.key, column.index)] = _VISION_HIGHLIGHT_HEX
        return out

    def _page_reported_totals(
        self, data: dict, page_columns: List[_Column]
    ) -> Dict[int, Decimal]:
        cols_by_number = {index + 1: column for index, column in enumerate(page_columns)}
        out: Dict[int, Decimal] = {}
        for item in data.get("reported_totals") or []:
            column = cols_by_number.get(_as_int(item.get("col")))
            value = to_decimal(item.get("qty"))
            if column is not None and value is not None:
                out[column.index] = value
        return out

    # ------------------------------------------------------- product resolution

    def _resolve_columns(
        self,
        version: DeliveryScheduleVersion,
        schedule: DeliverySchedule,
        columns: List[_Column],
    ) -> None:
        customer_id = self.customer_id_for(schedule)
        remembered = self._remembered_codes(customer_id)
        for column in columns:
            product_id, source = self._resolve_one(version, column, remembered)
            column.product_id = product_id
            column.resolution_source = source

    def _remembered_codes(self, customer_id: Optional[str]) -> Dict[str, str]:
        if not customer_id:
            return {}
        rows = (
            self.db.query(CustomerItemCodeMap)
            .filter(CustomerItemCodeMap.customer_id == customer_id)
            .all()
        )
        return {(row.customer_code or "").upper(): row.product_id for row in rows}

    def _resolve_one(
        self,
        version: DeliveryScheduleVersion,
        column: _Column,
        remembered: Dict[str, str],
    ) -> Tuple[Optional[str], Optional[str]]:
        """In order: what this customer taught us, the code printed inside their own,
        then a strong and unambiguous fuzzy match. Anything less is left to a person."""
        raw = (column.customer_code_raw or "").upper()
        if raw and raw in remembered:
            return remembered[raw], _RESOLUTION_MAP

        for candidate in _code_candidates(column.header_code, column.customer_code_raw):
            product = self._product_by_code(version, candidate)
            if product is not None:
                return product.id, _RESOLUTION_CODE

        probe = column.header_code or column.customer_code_raw
        product_id = self._product_by_similarity(version, probe)
        if product_id:
            return product_id, _RESOLUTION_TRIGRAM
        return None, None

    def _product_by_code(
        self, version: DeliveryScheduleVersion, code: str
    ) -> Optional[Product]:
        query = self.db.query(Product).filter(
            func.upper(func.trim(Product.product_code)) == code.upper()
        )
        if version.company_id:
            query = query.filter(Product.company_id == version.company_id)
        return query.first()

    def _product_by_similarity(
        self, version: DeliveryScheduleVersion, probe: Optional[str]
    ) -> Optional[str]:
        if not probe or len(probe) < 4:
            return None
        similarity = getattr(func, _TRGM_SCHEMA).similarity(Product.product_code, probe)
        query = self.db.query(Product.id, similarity.label("sim"))
        if version.company_id:
            query = query.filter(Product.company_id == version.company_id)
        rows = query.order_by(similarity.desc()).limit(2).all()
        if not rows or float(rows[0].sim or 0) < TRIGRAM_FLOOR:
            return None
        if len(rows) > 1 and float(rows[0].sim) - float(rows[1].sim or 0) < TRIGRAM_MARGIN:
            # Two products this close apart is a question, not an answer.
            return None
        return rows[0].id

    def _merge_duplicate_columns(self, columns: List[_Column]) -> List[_Column]:
        """Two columns of the same product become one.

        A cell is keyed on (phase, product), so the data model cannot hold the same
        product twice for one phase. The real R1 heads two adjacent columns with the
        same code, so this is a document that exists rather than a hypothetical.
        """
        merged: Dict[str, _Column] = {}
        out: List[_Column] = []
        for column in columns:
            seen = merged.get(column.key)
            if seen is None:
                merged[column.key] = column
                out.append(column)
                continue
            for phase_key, value in column.cells.items():
                seen.cells[phase_key] = seen.cells.get(phase_key, Decimal(0)) + value
            if column.reported_total is not None:
                seen.reported_total = (seen.reported_total or Decimal(0)) + column.reported_total
        for position, column in enumerate(out):
            column.index = position
        return out

    # ------------------------------------------------------------------- phases

    def _upsert_phases(
        self,
        version: DeliveryScheduleVersion,
        project: Optional[Project],
        phases: List[_Phase],
    ) -> None:
        """Create the phase rows the cells need, and leave existing dates alone.

        A revision moves dates. Overwriting them here would erase the "from" side of
        the move before anyone has agreed the new document, so the promotion happens on
        confirm and this only fills what does not exist yet.
        """
        if project is None:
            raise AppException(
                status_code=404,
                message="The project this schedule belongs to is missing.",
                code="project_not_found",
            )
        existing = {
            (row.area_group, row.sequence): row
            for row in self.db.query(ProjectDeliveryPhase)
            .filter(ProjectDeliveryPhase.project_id == project.id)
            .all()
        }
        for phase in phases:
            row = existing.get(phase.key)
            if row is None:
                row = ProjectDeliveryPhase(
                    company_id=version.company_id,
                    project_id=project.id,
                    area_group=phase.area_group,
                    sequence=phase.sequence,
                    label=phase.label,
                    delivery_date=phase.delivery_date,
                    source_version_id=version.id,
                )
                self.db.add(row)
                self.db.flush()
                existing[phase.key] = row
            phase.phase_id = str(row.id)

    def _write_cells(
        self,
        version: DeliveryScheduleVersion,
        phases: List[_Phase],
        columns: List[_Column],
    ) -> None:
        by_key = {phase.key: phase for phase in phases}
        self.db.query(DeliveryScheduleCell).filter(
            DeliveryScheduleCell.version_id == version.id
        ).delete(synchronize_session=False)
        for column in columns:
            for phase_key, value in column.cells.items():
                phase = by_key.get(phase_key)
                if phase is None or phase.phase_id is None or value is None or value == 0:
                    continue
                self.db.add(
                    DeliveryScheduleCell(
                        company_id=version.company_id,
                        version_id=version.id,
                        phase_id=phase.phase_id,
                        product_id=column.product_id,
                        customer_code_raw=column.customer_code_raw,
                        qty=value,
                        highlight=column.cell_highlights.get(phase_key),
                    )
                )
        self.db.flush()

    def _build_revision_proposals(
        self,
        version: DeliveryScheduleVersion,
        phases: List[_Phase],
        columns: List[_Column],
        pages: Sequence[Tuple[int, dict]],
    ) -> None:
        """Section 9.7(b): a page's tinted cells plus its own margin note become a
        re-date SUGGESTION, never an applied change.

        First highlighted phase (by its CURRENT date) moves to the note's date;
        each later one moves by the ORIGINAL gap to its predecessor -- the
        document's own cadence, read off the dates already on the phases, never a
        constant. A note with no highlighted cells on the same page, or highlighted
        cells with no dated note, proposes nothing: the review shows the note or
        the tint as-is and leaves the reading to a person.

        Re-run on every extraction, same as the cells: a proposal already accepted
        or rejected does not survive a re-read, because the cells it was built from
        do not either (`_write_cells` replaces them). The override it already wrote
        on `delivery_schedule_cells` does survive, until that row is itself
        replaced by the same re-read.
        """
        by_key = {phase.key: phase for phase in phases}
        proposals: List[Dict[str, Any]] = []
        for page_no, data in pages:
            dated = _dated_note(data or {})
            if dated is None:
                continue
            note_text, note_date = dated
            for column in columns:
                if column.page_no != page_no or not column.product_id:
                    continue
                highlighted = [
                    by_key[key]
                    for key in column.cell_highlights
                    if key in column.cells and key in by_key and by_key[key].delivery_date
                ]
                if not highlighted:
                    continue
                highlighted.sort(key=lambda phase: phase.delivery_date)
                cells: List[Dict[str, Any]] = []
                previous_old: Optional[date] = None
                previous_new: Optional[date] = None
                for phase in highlighted:
                    if previous_old is None:
                        new_date = note_date
                    else:
                        gap_days = (phase.delivery_date - previous_old).days
                        new_date = previous_new + timedelta(days=gap_days)
                    cells.append(
                        {
                            "phase_id": phase.phase_id,
                            "phase_label": phase.label,
                            "qty": qty_str(column.cells.get(phase.key)),
                            "old_date": phase.delivery_date.isoformat(),
                            "new_date": new_date.isoformat(),
                        }
                    )
                    previous_old, previous_new = phase.delivery_date, new_date
                proposals.append(
                    {
                        "product_id": column.product_id,
                        "item_code": self._product_code(column.product_id) or column.header_code,
                        "note_text": note_text,
                        "page_no": page_no,
                        "state": PROPOSAL_PROPOSED,
                        "decided_by": None,
                        "decided_at": None,
                        "cells": cells,
                    }
                )
        version.revision_proposals = proposals

    def _product_code(self, product_id: Optional[str]) -> Optional[str]:
        if not product_id:
            return None
        row = self.db.query(Product.product_code).filter(Product.id == product_id).first()
        return row[0] if row else None

    # ----------------------------------------------------------- reconciliation

    def _reconcile(
        self,
        version: DeliveryScheduleVersion,
        schedule: DeliverySchedule,
        phases: List[_Phase],
        columns: List[_Column],
        header: dict,
    ) -> dict:
        po_quantities, po_source = self._po_quantities(schedule, version)
        entries = []
        for column in columns:
            total = sum(column.cells.values(), Decimal(0))
            po_row = po_quantities.get(column.product_id) if column.product_id else None
            entries.append(
                self._column_entry(
                    column, total=total, po_row=po_row, po_source=po_source
                )
            )

        payload = {
            "columns": entries,
            "phases": [
                {
                    "key": list(phase.key),
                    "area_group": phase.area_group,
                    "sequence": phase.sequence,
                    "phase_id": phase.phase_id,
                    "label": phase.label,
                    "delivery_date": phase.delivery_date.isoformat() if phase.delivery_date else None,
                }
                for phase in phases
            ],
            "date_warnings": _date_warnings(phases),
            "header": {
                "po_ref": header.get("po_ref"),
                "project": header.get("project"),
            },
            "qty_source": _count_by(columns, lambda c: c.qty_source),
            "reconciled_columns": sum(1 for entry in entries if entry["reconciled"]),
            "total_columns": len(entries),
        }
        existing = version.reconciliation_json or {}
        if existing.get("acknowledgement"):
            payload["acknowledgement"] = existing["acknowledgement"]
        self._store_reconciliation(version, payload)
        version.reconciled_columns = payload["reconciled_columns"]
        version.total_columns = payload["total_columns"]
        return {
            "reconciled_columns": payload["reconciled_columns"],
            "total_columns": payload["total_columns"],
        }

    def _store_reconciliation(
        self, version: DeliveryScheduleVersion, payload: dict
    ) -> None:
        """Write the verdict back, and TELL SQLAlchemy it changed.

        ``reconciliation_json`` is a plain ``Column(JSONB)``, not a ``MutableDict``, so
        the only change detection it has is comparing the value against the snapshot
        taken when the row was loaded. Every writer here mutates the loaded dict in
        place (a column entry gains a product id, say) and assigns it back, and that
        snapshot IS the object being mutated: the comparison finds them equal, no UPDATE
        is emitted, and the endpoint returns 200 over a row the database never took.
        Measured on the live stack: two 200s from ``PUT .../products/{index}`` left
        ``product_id`` null on the column. Assignment alone is NOT enough,
        ``flag_modified`` is what makes it flush.
        """
        version.reconciliation_json = payload
        flag_modified(version, "reconciliation_json")

    def _column_entry(
        self,
        column: _Column,
        *,
        total: Decimal,
        po_row: Optional[dict],
        po_source: Optional[str],
    ) -> dict:
        po_qty = po_row["qty"] if po_row else None
        cancelled = po_row["cancelled"] if po_row else Decimal(0)
        reconciled, reason, warning = _verdict(total, column.reported_total, po_qty)
        note = None
        if cancelled and cancelled > 0:
            # AC-E3a: the cancellation stays visible instead of quietly changing the
            # number this column is measured against.
            note = (
                f"{qty_str(cancelled)} of the PO quantity for this product is cancelled on "
                "the version this schedule names; it reconciles as printed and must not "
                "become sales order lines."
            )
        return {
            "index": column.index,
            "key": column.key,
            "page_no": column.page_no,
            "customer_code_raw": column.customer_code_raw,
            "header_code": column.header_code,
            "name": column.name,
            "product_id": column.product_id,
            "resolution_source": column.resolution_source,
            "column_total": qty_str(total),
            "reported_total": qty_str(column.reported_total),
            "reported_total_source": column.reported_total_source,
            "qty_source": column.qty_source,
            "po_qty": qty_str(po_qty),
            "po_qty_source": po_source if po_qty is not None else None,
            "cancelled_qty": qty_str(cancelled) if cancelled else None,
            "reconciled": reconciled,
            "reason": reason,
            # Reconciled, and still worth saying: the commonest one is a partial schedule.
            "warning": warning,
            "note": note,
        }

    def _po_quantities(
        self, schedule: DeliverySchedule, version: DeliveryScheduleVersion
    ) -> Tuple[Dict[str, dict], Optional[str]]:
        """What the PO committed, per product, on the version this schedule names.

        Cancelled lines are INCLUDED in the quantity and reported separately. The
        schedule was drawn from the document as printed, and netting a later pencil
        cancellation into the target would reject a correct schedule (finding G1).
        """
        quantities: Dict[str, dict] = {}
        if version.po_version_id:
            rows = (
                self.db.query(ProjectPOLine)
                .filter(ProjectPOLine.po_version_id == version.po_version_id)
                .all()
            )
            for row in rows:
                if not row.resolved_product_id:
                    continue
                entry = quantities.setdefault(
                    row.resolved_product_id, {"qty": Decimal(0), "cancelled": Decimal(0)}
                )
                entry["qty"] += Decimal(row.qty or 0)
                if row.is_cancelled:
                    entry["cancelled"] += Decimal(row.qty or 0)
            if quantities:
                return quantities, "po_version"

        # No extracted document on this PO: a PO keyed in by hand is still a PO, and
        # its lines are the same commitment.
        rows = (
            self.db.query(ProjectPurchaseOrderLine)
            .filter(ProjectPurchaseOrderLine.po_id == schedule.purchase_order_id)
            .all()
        )
        for row in rows:
            if not row.product_id:
                continue
            entry = quantities.setdefault(
                row.product_id, {"qty": Decimal(0), "cancelled": Decimal(0)}
            )
            entry["qty"] += Decimal(row.quantity or 0)
        return quantities, ("po_row" if quantities else None)

    def _recompute(self, version: DeliveryScheduleVersion) -> None:
        """Re-run the verdict from the CELL ROWS after a person edited them, and store it."""
        payload, _changed = self._recomputed_payload(version)
        self._store_reconciliation(version, payload)
        version.reconciled_columns = payload["reconciled_columns"]
        version.total_columns = payload["total_columns"]
        self.db.add(version)
        self.db.flush()

    def _recomputed_payload(
        self, version: DeliveryScheduleVersion
    ) -> Tuple[dict, bool]:
        """The verdict this version's CELL ROWS deserve right now, and whether it moved.

        Deep-copied rather than mutated in place, so a caller may ask what the current
        rules make of a version WITHOUT touching the session's copy of it. That is what
        lets the read path refresh a confirmed version's numbers for display and still
        never write to what was agreed.
        """
        payload = copy.deepcopy(version.reconciliation_json or {})
        stored = version.reconciliation_json or {}
        entries: List[dict] = list(payload.get("columns") or [])
        schedule = self.schedule_for(version)
        po_quantities, po_source = self._po_quantities(schedule, version)

        totals: Dict[str, Decimal] = {}
        seen_codes: Dict[str, dict] = {}
        cells = (
            self.db.query(DeliveryScheduleCell)
            .filter(DeliveryScheduleCell.version_id == version.id)
            .all()
        )
        known = {entry["key"]: entry for entry in entries}
        for cell in cells:
            key = (
                f"product:{cell.product_id}"
                if cell.product_id
                else f"raw:{(cell.customer_code_raw or '').upper()}"
            )
            totals[key] = totals.get(key, Decimal(0)) + Decimal(cell.qty or 0)
            if key not in known:
                # A cell for a column the extraction never produced. Surfaced as its
                # own column rather than silently left out of every total.
                seen_codes[key] = {
                    "index": len(entries) + len(seen_codes),
                    "key": key,
                    "page_no": None,
                    "customer_code_raw": cell.customer_code_raw,
                    "header_code": None,
                    "name": None,
                    "product_id": cell.product_id,
                    "resolution_source": _RESOLUTION_MANUAL,
                    "reported_total": None,
                    "reported_total_source": None,
                    "qty_source": _RESOLUTION_MANUAL,
                }
        entries.extend(seen_codes.values())

        for entry in entries:
            total = totals.get(entry["key"], Decimal(0))
            po_row = po_quantities.get(entry["product_id"]) if entry.get("product_id") else None
            reported = to_decimal(entry.get("reported_total"))
            po_qty = po_row["qty"] if po_row else None
            reconciled, reason, warning = _verdict(total, reported, po_qty)
            entry["column_total"] = qty_str(total)
            entry["po_qty"] = qty_str(po_qty)
            entry["po_qty_source"] = po_source if po_qty is not None else None
            cancelled = po_row["cancelled"] if po_row else Decimal(0)
            entry["cancelled_qty"] = qty_str(cancelled) if cancelled else None
            # A dismissed column stops blocking, but it keeps the reason the check gave:
            # the verdict was not withdrawn, a person overruled it, and the screen has to
            # be able to show both halves of that.
            entry["reconciled"] = bool(reconciled or entry.get("dismissed"))
            entry["reason"] = reason
            entry["warning"] = warning

        payload["columns"] = entries
        payload["reconciled_columns"] = sum(1 for entry in entries if entry["reconciled"])
        payload["total_columns"] = len(entries)
        return payload, payload != stored

    def _refreshed_reconciliation(self, version: DeliveryScheduleVersion) -> dict:
        """The stored verdict, brought up to the CURRENT rules before anybody reads it.

        The payload is only ever recomputed on a WRITE, so a version read today still
        served the refusals it was given when the document was read: after the shortfall
        became a warning, a live version kept reporting "the column adds up to 53, the
        purchase order says 1777" and 31 of 44 reconciled, and the numbers only moved when
        an unrelated dismissal happened to write the row (measured 2026-08-18).

        So the read path refreshes too. An OPEN version is persisted, deliberately
        committed, so the stored payload converges and the confirm agrees with the screen;
        the write is best effort, because a verdict we could not save is not worth a 500 on
        a GET and the caller is served the fresh numbers either way. A CONFIRMED version is
        computed for display and never written: what was agreed, and the acknowledgement
        that carried it, are the record.
        """
        stored = version.reconciliation_json or {}
        if not (stored.get("columns") or []):
            # Nothing has been read yet. The review screen POLLS this every three seconds
            # while a document is being read, and an empty payload would differ from a
            # freshly computed one on every one of those polls: a write per poll for a
            # version that has no columns to judge.
            return stored
        payload, changed = self._recomputed_payload(version)
        if not changed:
            return stored
        if version.confirmed_at is not None:
            return payload
        try:
            self._store_reconciliation(version, payload)
            version.reconciled_columns = payload["reconciled_columns"]
            version.total_columns = payload["total_columns"]
            self.db.commit()
        except Exception:  # noqa: BLE001 - the same reasoning as reconcile_one (S20)
            logger.exception(
                "could not store the refreshed verdict for schedule version %s", version.id
            )
            self.db.rollback()
        return payload

    # ------------------------------------------------------------------ editing

    def update_cells(self, version_id: str, cells: Sequence[dict]) -> DeliveryScheduleVersion:
        """Upsert by (phase, product). A quantity of zero DELETES the cell, because a
        blank means this phase does not take this product.

        A cell may name its column by ``product_index`` instead of ``product_id``, and
        for an unidentified column it MUST: a column whose product nobody has named yet
        has no product id to key on, and it is exactly the column somebody is correcting.
        """
        version = self.get_version(version_id)
        self._assert_open(version)
        touched: Set[str] = set()
        for payload in cells:
            phase_id = _clean(payload.get("phase_id"), 64)
            product_id = _clean(payload.get("product_id"), 64)
            raw_code = _clean(payload.get("customer_code_raw"))
            column = self._column_at(version, payload.get("product_index"))
            if column is not None:
                product_id = product_id or _clean(column.get("product_id"), 64)
                raw_code = raw_code or _clean(column.get("customer_code_raw"))
            value = to_decimal(payload.get("qty"))
            if not phase_id or value is None:
                raise AppException(
                    status_code=422,
                    message="Every cell needs a phase and a quantity.",
                    code="schedule_cell_invalid",
                )
            if not product_id and not raw_code:
                raise AppException(
                    status_code=422,
                    message=(
                        "A cell needs the product it belongs to, or the customer's own "
                        "code where the column is still unidentified."
                    ),
                    code="schedule_cell_no_column",
                )
            phase = self.db.get(ProjectDeliveryPhase, phase_id)
            if phase is None:
                raise AppException(
                    status_code=404,
                    message="That delivery phase is not on this project.",
                    code="delivery_phase_not_found",
                )
            touched.add(
                f"product:{product_id}" if product_id else f"raw:{(raw_code or '').upper()}"
            )
            query = self.db.query(DeliveryScheduleCell).filter(
                DeliveryScheduleCell.version_id == version.id,
                DeliveryScheduleCell.phase_id == phase_id,
            )
            if product_id:
                query = query.filter(DeliveryScheduleCell.product_id == product_id)
            else:
                query = query.filter(
                    DeliveryScheduleCell.product_id.is_(None),
                    func.upper(DeliveryScheduleCell.customer_code_raw)
                    == (raw_code or "").upper(),
                )
            existing = query.first()
            if value == 0:
                if existing is not None:
                    self.db.delete(existing)
                continue
            if existing is not None:
                existing.qty = value
                continue
            self.db.add(
                DeliveryScheduleCell(
                    company_id=version.company_id,
                    version_id=version.id,
                    phase_id=phase_id,
                    product_id=product_id,
                    customer_code_raw=raw_code or self._code_for_product(version, product_id),
                    qty=value,
                )
            )
        self.db.flush()
        self._clear_dismissals(version, touched)
        self._recompute(version)
        return version

    def _clear_dismissals(
        self, version: DeliveryScheduleVersion, keys: Set[str]
    ) -> None:
        """A column whose numbers just changed is judged again from scratch.

        A dismissal says "the check is wrong about THESE numbers". Edit the numbers and
        it is a statement about something else, so it goes.
        """
        if not keys:
            return
        payload = version.reconciliation_json or {}
        entries: List[dict] = list(payload.get("columns") or [])
        cleared = [
            _clear_dismissal(entry) for entry in entries if entry.get("key") in keys
        ]
        if not any(cleared):
            return
        payload["columns"] = entries
        self._store_reconciliation(version, payload)

    def _column_at(
        self, version: DeliveryScheduleVersion, product_index: Any
    ) -> Optional[dict]:
        index = _as_int(product_index)
        if index is None:
            return None
        entry = next(
            (
                item
                for item in (version.reconciliation_json or {}).get("columns") or []
                if item.get("index") == index
            ),
            None,
        )
        if entry is None:
            raise AppException(
                status_code=404,
                message=f"Column {index + 1} is not on this schedule.",
                code="schedule_column_not_found",
            )
        return entry

    def _code_for_product(
        self, version: DeliveryScheduleVersion, product_id: Optional[str]
    ) -> Optional[str]:
        for entry in (version.reconciliation_json or {}).get("columns") or []:
            if entry.get("product_id") == product_id:
                return entry.get("customer_code_raw")
        return None

    def resolve_product_column(
        self,
        version_id: str,
        product_index: int,
        product_id: str,
        *,
        actor_user_id: Optional[str] = None,
    ) -> DeliveryScheduleVersion:
        """Name the product a column means, and remember it for this customer (AC-E4).

        The next schedule from the same customer resolves the same code silently, which
        is the point: a person identifies `BUI-HB-SRTWC8613-RL` exactly once.
        """
        version = self.get_version(version_id)
        self._assert_open(version)
        payload = version.reconciliation_json or {}
        entries: List[dict] = list(payload.get("columns") or [])
        entry = next((item for item in entries if item.get("index") == product_index), None)
        if entry is None:
            raise AppException(
                status_code=404,
                message="That column is not on this schedule.",
                code="schedule_column_not_found",
            )
        product = self.db.get(Product, product_id)
        if product is None:
            raise AppException(
                status_code=404, message="Product not found.", code="product_not_found"
            )
        clash = next(
            (
                item
                for item in entries
                if item.get("product_id") == product_id and item.get("index") != product_index
            ),
            None,
        )
        if clash is not None:
            raise AppException(
                status_code=409,
                message=(
                    f"{product.product_code} is already the column headed "
                    f"{clash.get('customer_code_raw') or clash.get('name') or 'earlier on this sheet'}. "
                    "Correct that column instead of pointing two at one product."
                ),
                code="schedule_column_duplicate_product",
            )

        old_key = entry["key"]
        cells = self.db.query(DeliveryScheduleCell).filter(
            DeliveryScheduleCell.version_id == version.id
        )
        if entry.get("product_id"):
            cells = cells.filter(DeliveryScheduleCell.product_id == entry["product_id"])
        else:
            cells = cells.filter(
                DeliveryScheduleCell.product_id.is_(None),
                func.upper(DeliveryScheduleCell.customer_code_raw)
                == (entry.get("customer_code_raw") or "").upper(),
            )
        for cell in cells.all():
            cell.product_id = product_id

        entry["product_id"] = product_id
        entry["key"] = f"product:{product_id}"
        entry["resolution_source"] = _RESOLUTION_MANUAL
        # This column now means a different product, so it is measured against a
        # different PO quantity. Any dismissal of the old verdict is about numbers that
        # no longer apply.
        _clear_dismissal(entry)
        payload["columns"] = entries
        self._store_reconciliation(version, payload)
        self.db.add(version)
        self.db.flush()
        logger.info(
            "schedule column %s on version %s repointed from %s to product %s",
            product_index, version.id, old_key, product.product_code,
        )

        self._remember_code(version, entry.get("customer_code_raw"), product_id, actor_user_id)
        self._recompute(version)
        return version

    def dismiss_column_verdict(
        self,
        version_id: str,
        column_index: int,
        *,
        dismissed: bool,
        reason: Optional[str] = None,
        actor_user_id: Optional[str] = None,
    ) -> DeliveryScheduleVersion:
        """Set ONE column's failing verdict aside as a false signal, with a reason.

        The checksum reads somebody else's paper and is sometimes wrong about a column
        that is fine: the TOTAL QTY row is transcribed from a print that may itself be
        wrong, and a product the PO never ordered can still legitimately be scheduled.
        The whole-sheet acknowledgement at confirm already covers "I know, bind it
        anyway", but it names no column and is taken at the last moment. This is the
        same judgement made per column, where the person is already looking.

        A dismissal does not withdraw the verdict: the computed reason stays on the
        entry so the screen shows both halves, and only ``reconciled`` flips, which is
        what stops the column blocking the confirm. Anything that CHANGES the column
        clears it -- its product (``resolve_product_column``), its cells
        (``update_cells``) or a re-read of the document -- because the dismissal was
        about the numbers as they stood.
        """
        version = self.get_version(version_id)
        self._assert_open(version)
        payload = version.reconciliation_json or {}
        entries: List[dict] = list(payload.get("columns") or [])
        entry = next((item for item in entries if item.get("index") == column_index), None)
        if entry is None:
            raise AppException(
                status_code=404,
                message="That column is not on this schedule.",
                code="schedule_column_not_found",
            )
        if dismissed:
            note = (reason or "").strip()
            if not note:
                raise AppException(
                    status_code=422,
                    message="Dismissing a column's verdict needs a reason.",
                    code="schedule_dismissal_reason_required",
                )
            entry["dismissed"] = True
            entry["dismissed_reason"] = note[:500]
            entry["dismissed_by"] = actor_user_id
            entry["dismissed_at"] = datetime.utcnow().isoformat()
        else:
            _clear_dismissal(entry)
        payload["columns"] = entries
        self._store_reconciliation(version, payload)
        self._recompute(version)
        logger.info(
            "column %s on schedule version %s %s",
            column_index,
            version.id,
            "dismissed as a false signal" if dismissed else "put back under its verdict",
        )
        return version

    def _remember_code(
        self,
        version: DeliveryScheduleVersion,
        customer_code: Optional[str],
        product_id: str,
        actor_user_id: Optional[str],
    ) -> None:
        customer_id = self.customer_id_for(self.schedule_for(version))
        if not customer_id or not customer_code:
            return
        existing = (
            self.db.query(CustomerItemCodeMap)
            .filter(
                CustomerItemCodeMap.customer_id == customer_id,
                func.upper(CustomerItemCodeMap.customer_code) == customer_code.upper(),
            )
            .first()
        )
        if existing is not None:
            existing.product_id = product_id
            existing.confirmed_by = actor_user_id
            return
        self.db.add(
            CustomerItemCodeMap(
                company_id=version.company_id,
                customer_id=customer_id,
                customer_code=customer_code,
                product_id=product_id,
                confirmed_by=actor_user_id,
            )
        )
        self.db.flush()

    def customer_id_for(self, schedule: DeliverySchedule) -> Optional[str]:
        """The debtor this schedule's codes belong to.

        The PO's issuer first, through the party-to-customer bridge, then the lead's
        buyer. A schedule may be issued by somebody else entirely (AC-E6, and R2 was),
        but the item codes are the BUYER's, so the map is keyed on them.
        """
        po = self.db.get(ProjectPurchaseOrder, schedule.purchase_order_id)
        if po is not None and po.issuing_party_id:
            party = self.db.get(ProjectParty, po.issuing_party_id)
            if party is not None and party.customer_id:
                return party.customer_id
        project = self.db.get(Project, schedule.project_id)
        if project is not None and project.lead_id:
            from app.models.projects import ProjectLead

            lead = self.db.get(ProjectLead, project.lead_id)
            if lead is not None and lead.customer_id:
                return lead.customer_id
        return None

    # ------------------------------------------------------------------ confirm

    def confirm(
        self,
        version_id: str,
        *,
        actor_user_id: Optional[str],
        acknowledge_unreconciled: bool = False,
        reason: Optional[str] = None,
    ) -> DeliveryScheduleVersion:
        """Bind the grid, and promote what this version says about the phases.

        Refused while any column is unreconciled unless a person acknowledges it with a
        reason, which is then kept on the version forever.

        The verdict is re-run first, so what is judged here is the CURRENT rules applied
        to the current cells rather than a verdict cached when the document was read. A
        version read before the shortfall became a warning would otherwise keep blocking
        on a column the screen no longer shows as work, and only an unrelated cell edit
        would have cleared it.
        """
        version = self.get_version(version_id)
        self._assert_open(version)
        self._recompute(version)
        payload = version.reconciliation_json or {}
        entries: List[dict] = list(payload.get("columns") or [])
        if not entries:
            raise AppException(
                status_code=409,
                message="There is nothing to confirm: no product columns were read.",
                code="schedule_nothing_to_confirm",
            )
        # A partial read is not a reconciliation failure, it is a MISSING part of the
        # sheet: the columns on the pages that did not answer are absent altogether, so
        # nothing flags them. Binding that would commit a schedule with a third of its
        # products silently missing, so it takes the same acknowledgement.
        if version.extraction_state == STATE_PARTIAL and not acknowledge_unreconciled:
            raise AppException(
                status_code=409,
                message=(
                    f"Part of this schedule could not be read. {version.extraction_error} "
                    "Finish those pages by hand, or confirm anyway with a reason."
                ),
                code="schedule_pages_unread",
            )
        failing = [entry for entry in entries if not entry.get("reconciled")]
        if failing and not acknowledge_unreconciled:
            named = ", ".join(
                str(entry.get("customer_code_raw") or entry.get("name") or f"column {entry['index'] + 1}")
                for entry in failing[:8]
            )
            raise AppException(
                status_code=409,
                message=(
                    f"{len(failing)} of {len(entries)} columns do not reconcile: {named}. "
                    "Correct those cells, or confirm anyway with a reason."
                ),
                code="schedule_unreconciled_columns",
            )
        acknowledging = acknowledge_unreconciled and (
            bool(failing) or version.extraction_state == STATE_PARTIAL
        )
        if acknowledging and not (reason or "").strip():
            raise AppException(
                status_code=422,
                message="Confirming a schedule the checks doubt needs a reason.",
                code="schedule_acknowledge_reason_required",
            )

        self._promote_phases(version, payload)
        if acknowledging:
            acknowledgement: Dict[str, Any] = {
                "reason": (reason or "").strip(),
                "by": actor_user_id,
                "at": datetime.utcnow().isoformat(),
                "columns": [entry["index"] for entry in failing],
                "partial_read": version.extraction_state == STATE_PARTIAL,
            }
            payload["acknowledgement"] = acknowledgement
        self._store_reconciliation(version, payload)
        version.confirmed_by = actor_user_id
        version.confirmed_at = datetime.utcnow()
        self.db.add(version)
        self.db.flush()
        # Section 9.2: confirming a schedule version is where an authored SO built
        # from an EARLIER version of the same schedule becomes stale. Best-effort,
        # like every post-commit side effect (CLAUDE.md): a notification that fails
        # must never turn a schedule that WAS confirmed into a 500.
        try:
            self._notify_stale_orders(version)
        except Exception:  # noqa: BLE001
            logger.warning(
                "schedule version %s confirmed, but notifying the stale order's "
                "planner failed", version.id, exc_info=True,
            )
        return version

    def _amendment_preview_path(self, order: ProjectSalesOrder, version_id: str) -> str:
        return (
            f"/project-sales/{order.project_id}/sales-orders/{order.id}/revisions"
            f"?schedule_version={version_id}"
        )

    def _stale_orders_for(self, version: DeliveryScheduleVersion) -> List[ProjectSalesOrder]:
        """Authored orders on this schedule's PO that were built from an OLDER
        version -- the ones a fresh confirm just made stale (AC, section 9.2)."""
        schedule = self.schedule_for(version)
        return (
            self.db.query(ProjectSalesOrder)
            .filter(
                ProjectSalesOrder.purchase_order_id == schedule.purchase_order_id,
                ProjectSalesOrder.status.in_(AUTHORED_LIVE_STATUSES),
                ProjectSalesOrder.schedule_version_id.isnot(None),
                ProjectSalesOrder.schedule_version_id != version.id,
            )
            .all()
        )

    def _notify_stale_orders(self, version: DeliveryScheduleVersion) -> None:
        from app.models.projects import Project
        from app.services.notification_service import NotificationService

        orders = self._stale_orders_for(version)
        if not orders:
            return
        label = version.revision_label or f"version {version.version_no}"
        service = NotificationService(self.db)
        for order in orders:
            project = self.db.get(Project, order.project_id) if order.project_id else None
            recipient = (project.owner_user_id if project else None) or order.published_by
            if not recipient:
                continue
            reference = order.autocount_doc_no or order.provisional_ref
            link = self._amendment_preview_path(order, version.id)
            service.create_with_channel_preferences(
                user_id=str(recipient),
                type="project_schedule_confirmed_stale_so",
                title=f"Delivery schedule {label} confirmed - {reference} needs an amendment",
                body=(
                    f"{reference} was built from an earlier version of this schedule. "
                    "Review the suggested revision."
                ),
                data={
                    "project_id": str(order.project_id) if order.project_id else None,
                    "project_sales_order_id": str(order.id),
                    "schedule_version_id": str(version.id),
                    "sales_order_ref": reference,
                    "link": link,
                },
                source_entity_type="project_sales_order",
                source_entity_id=str(order.id),
                dedup_key=f"{order.id}:{version.id}:schedule_confirmed_stale",
                event_type="project_schedule_confirmed_stale_so",
                send_in_app=True,
                send_email=False,
            )

    def _promote_phases(self, version: DeliveryScheduleVersion, payload: dict) -> None:
        """What THIS version says about each phase becomes what the project holds.

        Keyed on (area_group, sequence) and never the label (finding G6). Until this
        moment the phase row still carries the previous version's date, which is what
        gives the amendment engine both ends of a move.
        """
        for item in payload.get("phases") or []:
            if not item.get("phase_id"):
                continue
            phase = self.db.get(ProjectDeliveryPhase, item["phase_id"])
            if phase is None:
                continue
            delivery_date = _parse_date(item.get("delivery_date"))
            if delivery_date:
                phase.delivery_date = delivery_date
            if item.get("label"):
                phase.label = item["label"]
            phase.source_version_id = version.id

    def _assert_open(self, version: DeliveryScheduleVersion) -> None:
        if version.confirmed_at is not None:
            raise AppException(
                status_code=409,
                message=(
                    "This schedule version is confirmed. Upload a revision rather than "
                    "editing what was agreed."
                ),
                code="schedule_version_confirmed",
            )

    # ------------------------------------------------------ revision proposals

    def _proposal_or_404(self, version: DeliveryScheduleVersion, index: int) -> dict:
        proposals = version.revision_proposals or []
        if index < 0 or index >= len(proposals):
            raise AppException(
                status_code=404,
                message="That revision proposal was not found on this version.",
                code="revision_proposal_not_found",
            )
        return proposals[index]

    def _decide_proposal(
        self,
        version_id: str,
        index: int,
        *,
        state: str,
        actor_user_id: Optional[str],
        apply_overrides: bool,
    ) -> DeliveryScheduleVersion:
        version = self.get_version(version_id)
        self._assert_open(version)
        proposals = list(version.revision_proposals or [])
        proposal = self._proposal_or_404(version, index)
        if proposal.get("state") != PROPOSAL_PROPOSED:
            raise AppException(
                status_code=409,
                message=f"This proposal was already {proposal.get('state')}.",
                code="revision_proposal_decided",
            )
        if apply_overrides:
            for cell in proposal.get("cells") or []:
                phase_id = cell.get("phase_id")
                if not phase_id:
                    continue
                row = (
                    self.db.query(DeliveryScheduleCell)
                    .filter(
                        DeliveryScheduleCell.version_id == version.id,
                        DeliveryScheduleCell.phase_id == phase_id,
                        DeliveryScheduleCell.product_id == proposal.get("product_id"),
                    )
                    .first()
                )
                if row is not None:
                    row.delivery_date_override = _parse_date(cell.get("new_date"))
        decided = dict(proposal)
        decided["state"] = state
        decided["decided_by"] = actor_user_id
        decided["decided_at"] = datetime.utcnow().isoformat()
        proposals[index] = decided
        version.revision_proposals = proposals
        flag_modified(version, "revision_proposals")
        self.db.flush()
        return version

    def accept_revision_proposal(
        self, version_id: str, index: int, *, actor_user_id: Optional[str]
    ) -> DeliveryScheduleVersion:
        """Writes the override for every cell the proposal names, and marks it
        accepted. The cells this product does NOT carry a proposal for are
        untouched -- accepting SRT382-6's re-date does nothing to any other
        product's dates."""
        return self._decide_proposal(
            version_id, index, state=PROPOSAL_ACCEPTED,
            actor_user_id=actor_user_id, apply_overrides=True,
        )

    def reject_revision_proposal(
        self, version_id: str, index: int, *, actor_user_id: Optional[str]
    ) -> DeliveryScheduleVersion:
        """Marks the proposal rejected. Writes nothing else: the note and the tint
        stay exactly as read, and the phase dates are untouched."""
        return self._decide_proposal(
            version_id, index, state=PROPOSAL_REJECTED,
            actor_user_id=actor_user_id, apply_overrides=False,
        )

    # --------------------------------------------------------------- serialising

    def get_version_detail(self, version_id: str) -> dict:
        version = self.get_version(version_id)
        # The review screen polls this while a schedule is being read, which makes it the
        # right place to notice that the reader died: a killed work-horse never runs the
        # task's own error handling, so nothing inside it could have said so (S20).
        self.reconcile_stranded([version])
        schedule = self.schedule_for(version)
        # The stored verdict is only written on a WRITE, so it can be older than the rules.
        # Refreshed here, and persisted when the version is still open.
        payload = self._refreshed_reconciliation(version)
        po = self.db.get(ProjectPurchaseOrder, schedule.purchase_order_id)
        project = self.db.get(Project, schedule.project_id)
        po_version = (
            self.db.get(ProjectPOVersion, version.po_version_id)
            if version.po_version_id
            else None
        )
        issuer = (
            self.db.get(ProjectParty, schedule.issuer_party_id)
            if schedule.issuer_party_id
            else None
        )

        phase_rows = {
            str(row.id): row
            for row in self.db.query(ProjectDeliveryPhase)
            .filter(ProjectDeliveryPhase.project_id == schedule.project_id)
            .all()
        }
        phases = []
        for item in payload.get("phases") or []:
            row = phase_rows.get(str(item.get("phase_id")))
            phases.append(
                {
                    "id": item.get("phase_id"),
                    "area_group": item.get("area_group"),
                    "sequence": item.get("sequence"),
                    "label": item.get("label"),
                    "delivery_date": item.get("delivery_date"),
                    # What the project holds today, so a revision shows the move
                    # instead of just the new date.
                    "promoted_delivery_date": (
                        row.delivery_date.isoformat() if row is not None and row.delivery_date else None
                    ),
                }
            )

        products = []
        for entry in payload.get("columns") or []:
            product = (
                self.db.get(Product, entry["product_id"]) if entry.get("product_id") else None
            )
            products.append(
                {
                    "product_index": entry.get("index"),
                    "product_id": entry.get("product_id"),
                    "product_code": product.product_code if product else None,
                    "product_name": product.product_name if product else None,
                    "customer_code_raw": entry.get("customer_code_raw"),
                    "header_name": entry.get("name"),
                    "resolution_source": entry.get("resolution_source"),
                    "column_total": entry.get("column_total"),
                    "reported_total": entry.get("reported_total"),
                    "po_qty": entry.get("po_qty"),
                    "cancelled_qty": entry.get("cancelled_qty"),
                    "qty_source": entry.get("qty_source"),
                    "reconciled": bool(entry.get("reconciled")),
                    "reason": entry.get("reason"),
                    "warning": entry.get("warning"),
                    "note": entry.get("note"),
                    "dismissed": bool(entry.get("dismissed")),
                    "dismissed_reason": entry.get("dismissed_reason"),
                    "dismissed_by_name": self._user_name(entry.get("dismissed_by")),
                    "dismissed_at": entry.get("dismissed_at"),
                }
            )

        # Every cell says which COLUMN it belongs to, not only which product. A column
        # whose product nobody has identified yet has no product id, and keying the grid
        # on product alone left those columns rendering empty while still showing a
        # total, which reads as a bug rather than as work to do.
        index_by_key = {
            entry["key"]: entry.get("index") for entry in payload.get("columns") or []
        }
        cells = []
        for cell in (
            self.db.query(DeliveryScheduleCell)
            .filter(DeliveryScheduleCell.version_id == version.id)
            .all()
        ):
            key = (
                f"product:{cell.product_id}"
                if cell.product_id
                else f"raw:{(cell.customer_code_raw or '').upper()}"
            )
            cells.append(
                {
                    "phase_id": cell.phase_id,
                    "product_index": index_by_key.get(key),
                    "product_id": cell.product_id,
                    "customer_code_raw": cell.customer_code_raw,
                    "qty": qty_str(Decimal(cell.qty)),
                    "highlight": cell.highlight,
                    "delivery_date_override": (
                        cell.delivery_date_override.isoformat()
                        if cell.delivery_date_override
                        else None
                    ),
                }
            )

        extracted = version.extracted_json or {}
        # The customer occasionally writes a revision as PROSE in the margin rather
        # than as a phase-column change (e.g. "ONLY FOR FLOOR TRAP TO BE DELIVER IN
        # 2026, START FROM 23/7/2026"). The extractor reports it verbatim and does
        # NOT turn it into a date -- inferring one here would be exactly the
        # guess-a-date bug this file already had to be pinned against.
        notes: List[Dict[str, Any]] = []
        for page_entry in extracted.get("pages") or []:
            page_data = page_entry.get("data") or {}
            for note_text in page_data.get("notes") or []:
                note_text = note_text.strip() if isinstance(note_text, str) else None
                if note_text:
                    notes.append({"page_no": page_entry.get("page_no"), "text": note_text})

        # Section 9.2: only meaningful once this version is confirmed -- an open
        # version is still being worked on, so nothing downstream is stale yet.
        amendment_preview_url: Optional[str] = None
        if version.confirmed_at is not None:
            stale_orders = self._stale_orders_for(version)
            if stale_orders:
                amendment_preview_url = self._amendment_preview_path(
                    stale_orders[0], version.id
                )

        return {
            "id": str(version.id),
            "delivery_schedule_id": str(version.delivery_schedule_id),
            "purchase_order_id": str(schedule.purchase_order_id),
            "version_no": version.version_no,
            "revision_label": version.revision_label,
            "issuer_party_label": issuer.name if issuer else None,
            "po_version_id": version.po_version_id,
            "po_version_no": po_version.version_no if po_version else None,
            "po_number": po.po_number if po else None,
            "project_id": str(schedule.project_id),
            "project_code": project.project_code if project else None,
            "project_title": project.title if project else None,
            "extraction_state": version.extraction_state,
            "extraction_error": version.extraction_error,
            "extraction_model": version.extraction_model,
            "extraction_elapsed_ms": version.extraction_elapsed_ms,
            "extraction_started_at": (
                version.extraction_started_at.isoformat()
                if version.extraction_started_at
                else None
            ),
            "page_count": extracted.get("page_count"),
            "pages_extracted": len(extracted.get("pages") or []),
            "document_url": self.document_url(version),
            "schedule_date": version.schedule_date.isoformat() if version.schedule_date else None,
            "phases": phases,
            "products": products,
            "cells": cells,
            "date_warnings": payload.get("date_warnings") or [],
            "notes": notes,
            "revision_proposals": version.revision_proposals or [],
            "amendment_preview_url": amendment_preview_url,
            "acknowledgement": payload.get("acknowledgement"),
            # From the payload being SERVED, not from the row's own counters: a confirmed
            # version is refreshed for display without being written, so the counters can
            # legitimately still hold what was agreed. The header must agree with the
            # columns underneath it.
            "reconciliation": {
                "reconciled_columns": int(
                    payload.get("reconciled_columns", version.reconciled_columns) or 0
                ),
                "total_columns": int(
                    payload.get("total_columns", version.total_columns) or 0
                ),
            },
            "uploaded_by_name": self._uploader_name(version),
            "confirmed_by_name": self._user_name(version.confirmed_by),
            "confirmed_at": version.confirmed_at.isoformat() if version.confirmed_at else None,
            "created_at": version.created_at.isoformat() if version.created_at else None,
        }

    # ------------------------------------------------------------------- listings

    def list_schedules(self, project_id: str) -> List[dict]:
        """Every delivery schedule on a project, each headed by its latest version.

        Named by the PO it belongs to and the company that issued it, never by its id:
        a schedule's own label is usually blank, and a UUID heads nothing.
        """
        schedules = (
            self.db.query(DeliverySchedule)
            .filter(DeliverySchedule.project_id == project_id)
            .order_by(DeliverySchedule.created_at.asc())
            .all()
        )
        if not schedules:
            return []
        ids = [row.id for row in schedules]
        versions = (
            self.db.query(DeliveryScheduleVersion)
            .filter(DeliveryScheduleVersion.delivery_schedule_id.in_(ids))
            .order_by(DeliveryScheduleVersion.version_no.asc())
            .all()
        )
        grouped: Dict[str, List[DeliveryScheduleVersion]] = {}
        for version in versions:
            grouped.setdefault(str(version.delivery_schedule_id), []).append(version)

        out = []
        for schedule in schedules:
            own = grouped.get(str(schedule.id), [])
            latest = own[-1] if own else None
            po = self.db.get(ProjectPurchaseOrder, schedule.purchase_order_id)
            issuer = (
                self.db.get(ProjectParty, schedule.issuer_party_id)
                if schedule.issuer_party_id
                else None
            )
            out.append(
                {
                    "id": str(schedule.id),
                    "project_id": str(schedule.project_id),
                    "purchase_order_id": str(schedule.purchase_order_id),
                    "po_number": po.po_number if po else None,
                    "issuer_party_label": issuer.name if issuer else None,
                    "label": schedule.label,
                    "version_count": len(own),
                    "latest_version_id": str(latest.id) if latest else None,
                    "latest_version_no": latest.version_no if latest else None,
                    "latest_revision_label": latest.revision_label if latest else None,
                    "extraction_state": latest.extraction_state if latest else None,
                    "reconciled_columns": int(latest.reconciled_columns or 0) if latest else 0,
                    "total_columns": int(latest.total_columns or 0) if latest else 0,
                    "confirmed_at": (
                        latest.confirmed_at.isoformat()
                        if latest is not None and latest.confirmed_at
                        else None
                    ),
                    "created_at": schedule.created_at.isoformat() if schedule.created_at else None,
                }
            )
        return out

    def list_versions(self, schedule_id: str) -> List[dict]:
        """The revision history of one schedule, newest first.

        R1 and R2 are separate documents of the same commitment (AC-G1), so this list is
        what a person navigates rather than a single mutable grid.
        """
        schedule = self.db.get(DeliverySchedule, schedule_id)
        if schedule is None:
            raise AppException(
                status_code=404,
                message="Delivery schedule not found.",
                code="delivery_schedule_not_found",
            )
        versions = (
            self.db.query(DeliveryScheduleVersion)
            .filter(DeliveryScheduleVersion.delivery_schedule_id == schedule_id)
            .order_by(DeliveryScheduleVersion.version_no.desc())
            .all()
        )
        self.reconcile_stranded(versions)
        po = self.db.get(ProjectPurchaseOrder, schedule.purchase_order_id)
        out = []
        for version in versions:
            po_version = (
                self.db.get(ProjectPOVersion, version.po_version_id)
                if version.po_version_id
                else None
            )
            extracted = version.extracted_json or {}
            out.append(
                {
                    "id": str(version.id),
                    "delivery_schedule_id": str(schedule.id),
                    "purchase_order_id": str(schedule.purchase_order_id),
                    "po_number": po.po_number if po else None,
                    "version_no": version.version_no,
                    "revision_label": version.revision_label,
                    "po_version_no": po_version.version_no if po_version else None,
                    "schedule_date": (
                        version.schedule_date.isoformat() if version.schedule_date else None
                    ),
                    "extraction_state": version.extraction_state,
                    "extraction_error": version.extraction_error,
                    "page_count": extracted.get("page_count"),
                    "pages_extracted": len(extracted.get("pages") or []),
                    "reconciled_columns": int(version.reconciled_columns or 0),
                    "total_columns": int(version.total_columns or 0),
                    "uploaded_by_name": self._uploader_name(version),
                    "confirmed_by_name": self._user_name(version.confirmed_by),
                    "confirmed_at": (
                        version.confirmed_at.isoformat() if version.confirmed_at else None
                    ),
                    "created_at": version.created_at.isoformat() if version.created_at else None,
                }
            )
        return out

    def _user_name(self, user_id: Optional[str]) -> Optional[str]:
        if not user_id:
            return None
        from app.models.user import User

        user = self.db.get(User, user_id)
        return getattr(user, "name", None) or getattr(user, "email", None) if user else None

    def _uploader_name(self, version: DeliveryScheduleVersion) -> Optional[str]:
        """Who uploaded the document, taken from the attachment link that carries it.

        The version row has no ``created_by`` of its own, and the link already records
        the person who put the file there, so it is the same fact rather than a copy.
        """
        from app.models.entity_attachment import EntityAttachmentLink

        link = (
            self.db.query(EntityAttachmentLink)
            .filter(
                EntityAttachmentLink.entity_type == ATTACHMENT_ENTITY_TYPE,
                EntityAttachmentLink.entity_id == str(version.id),
            )
            .order_by(EntityAttachmentLink.created_at.asc())
            .first()
        )
        return self._user_name(getattr(link, "created_by", None))


# ----------------------------------------------------------------- free helpers

_DISMISSAL_FIELDS = ("dismissed", "dismissed_reason", "dismissed_by", "dismissed_at")


def _clear_dismissal(entry: dict) -> bool:
    """Forget a column's dismissal. True when there was one to forget."""
    had = bool(entry.get("dismissed"))
    for field_name in _DISMISSAL_FIELDS:
        entry.pop(field_name, None)
    return had


def _as_int(value: Any) -> Optional[int]:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _row_ordinal(item: dict, fallback: int) -> int:
    value = _as_int(item.get("row"))
    return value if value is not None else fallback + 1


def _col_ordinal(item: dict, fallback: int) -> int:
    value = _as_int(item.get("col"))
    return value if value is not None else fallback + 1


def _code_candidates(header_code: Optional[str], customer_code: Optional[str]) -> List[str]:
    """Our code, hiding inside theirs.

    `BUI-HB-SRTWC8613-RL` is `SRTWC8613-RL` with the customer's prefix bolted on, so
    the candidates are the code the model read plus every suffix of the printed one.
    Longest first: `SRTWC8613-RL` must be tried before `RL`.
    """
    out: List[str] = []
    if header_code:
        out.append(header_code.strip())
    if customer_code:
        cleaned = customer_code.strip()
        out.append(cleaned)
        parts = cleaned.split("-")
        for start in range(1, len(parts)):
            out.append("-".join(parts[start:]))
    seen = set()
    unique = []
    for candidate in out:
        key = candidate.upper()
        if candidate and len(candidate) >= 3 and key not in seen:
            seen.add(key)
            unique.append(candidate)
    return unique


def _verdict(
    total: Decimal, reported: Optional[Decimal], po_qty: Optional[Decimal]
) -> Tuple[bool, Optional[str], Optional[str]]:
    """``(reconciled, reason, warning)`` for one column.

    A SHORTFALL against the purchase order is a WARNING, not a blocker (captain,
    2026-08-18): a delivery schedule is routinely PARTIAL. The customer schedules part of
    what they ordered now and the rest on a later document, so "the schedule asks for 195
    of the 200 ordered" is the normal state of a live project, and blocking on it made the
    screen demand a correction to something that was never wrong.

    What still blocks is the reverse and the internal disagreement:

    - the column asks for MORE than the purchase order ordered: the schedule cannot
      commit quantity nobody bought,
    - the phases do not add up to the schedule's own TOTAL QTY row: one of the two was
      misread and neither number can be trusted until that is settled,
    - there is no purchase order quantity at all. Silence is not agreement: the column is
      unchecked, not clean, and saying so is the whole point of the screen.

    The ceiling is the quantity the named PO version PRINTS, cancelled lines included.
    That is deliberate and is AC-E3a: a schedule drawn before a handwritten cancellation
    reconciles as printed, and netting the cancellation out of the target would reject a
    document the customer considers correct (finding G1). The cancelled portion is
    reported separately as the column's note.
    """
    if reported is not None and total != reported:
        return False, (
            f"the column adds up to {qty_str(total)}, the schedule's own total says "
            f"{qty_str(reported)}"
        ), None
    if po_qty is None:
        return False, "no purchase order quantity to reconcile against", None
    if total > po_qty:
        return False, (
            f"the column adds up to {qty_str(total)}, more than the "
            f"{qty_str(po_qty)} the purchase order orders"
        ), None
    if total < po_qty:
        return True, None, (
            f"The schedule asks for {qty_str(total)} of the {qty_str(po_qty)} on the "
            f"purchase order; the remaining {qty_str(po_qty - total)} is expected on a "
            "later schedule."
        )
    return True, None, None


def _date_warnings(phases: List[_Phase]) -> List[dict]:
    """Dates that run backwards inside an area group (AC-E7).

    `8/3/2026` is either 8 March or 3 August, and the two schedules in the golden set
    use different conventions. The rows run in calendar order, so a date that goes
    backwards is the tell that the reading is wrong, and it is raised rather than
    corrected.
    """
    warnings: List[dict] = []
    previous: Dict[str, Optional[date]] = {}
    for phase in sorted(phases, key=lambda p: (p.area_group, p.sequence)):
        last = previous.get(phase.area_group)
        if last is not None and phase.delivery_date is not None and phase.delivery_date < last:
            warnings.append(
                {
                    "area_group": phase.area_group,
                    "sequence": phase.sequence,
                    "delivery_date": phase.delivery_date.isoformat(),
                    "detail": (
                        f"{phase.area_group} row {phase.sequence} is dated before the row "
                        "above it. Confirm the day and month."
                    ),
                }
            )
        if phase.delivery_date is not None:
            previous[phase.area_group] = phase.delivery_date
    return warnings


def _count_by(items, key) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for item in items:
        value = key(item)
        out[value] = out.get(value, 0) + 1
    return out
