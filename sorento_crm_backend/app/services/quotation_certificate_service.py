"""QUOTE-CERT-TAB: the Certification tab of a quotation document.

The list is DERIVED: the active certificates that cover a quoted product on the current draft
versions (a set line counts every part), plus the ones a user added by hand, minus the ones a user
removed. `quotation_document_certificates` holds only those user changes. Certificates whose current
revision carries the same file form ONE row (CERT-15), keyed by its representative.
Contract: documentation/plans/certificates/quote-cert-tab-08nov-acceptance-criteria.md.
"""
from __future__ import annotations

import logging
import math
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session, selectinload

from app.models.certificate import Certificate, CertificateProduct, CertificateRevision
from app.models.product import Product
from app.models.projects import (
    ProjectQuotationDocument,
    ProjectQuotationDocumentCertificate,
    ProjectQuotationLine,
)
from app.models.resources import Attachment
from app.services import certificate_pdf_service as pdfs
from app.services.certificate_service import (
    VALIDITY_EXPIRED,
    VALIDITY_EXPIRING_SOON,
    VALIDITY_VALID,
    derive_validity,
    today_malaysia,
)
from app.services.error_handler import AppException


logger = logging.getLogger(__name__)

MAX_BOXES = 200
# CERT-TAB-UX (crew pass, 11 Nov): a file missing from storage is remembered for its revision and
# not fetched again by the list until this long has passed (each miss cost ~150 ms on every load).
MISS_RETRY = timedelta(hours=24)


def _utcnow() -> datetime:
    return datetime.utcnow()


def _miss_fresh(cache: dict) -> bool:
    try:
        checked = datetime.fromisoformat(str(cache.get("checked_at")))
    except (TypeError, ValueError):
        return False
    return _utcnow() - checked < MISS_RETRY


def _remember_miss(db: Session, cp: CertificateProduct, revision_id: Optional[str]) -> None:
    cp.boxes = {
        "revision_id": revision_id,
        "code": cp.model_code,
        "source": "auto",
        "missing": True,
        "checked_at": _utcnow().isoformat(),
        "boxes": [],
    }
    db.info["qcert_dirty"] = True
SCOPE_QUOTE = "quote"
SCOPE_DEFAULT = "default"

_STATE_LABEL = {VALIDITY_VALID: "valid", VALIDITY_EXPIRING_SOON: "expiring", VALIDITY_EXPIRED: "expired"}


def _not_found() -> AppException:
    return AppException(status_code=404, message="Certificate not found.", code="certificate_not_found")


# ----------------------------------------------------------------------------- list building


def _quoted_products(db: Session, document: ProjectQuotationDocument) -> Dict[str, str]:
    """product_id -> product_code for every product quoted on the current draft versions."""
    from app.services import project_spec_sheet_service as spec

    version_ids = spec._draft_version_ids(db, document)
    if not version_ids:
        return {}
    ids: set[str] = set()
    for line in db.query(ProjectQuotationLine).filter(ProjectQuotationLine.version_id.in_(version_ids)):
        if line.product_id:
            ids.add(str(line.product_id))
        for part in line.set_parts_snapshot or []:
            if part.get("product_id"):
                ids.add(str(part["product_id"]))
    if not ids:
        return {}
    rows = db.query(Product.id, Product.product_code).filter(Product.id.in_(ids)).all()
    return {str(pid): code or "" for pid, code in rows}


def _markers(db: Session, document) -> Dict[str, ProjectQuotationDocumentCertificate]:
    rows = db.query(ProjectQuotationDocumentCertificate).filter(
        ProjectQuotationDocumentCertificate.document_id == document.id
    )
    return {str(m.certificate_id): m for m in rows}


def _file_key(cert: Certificate) -> str:
    rev = cert.current_revision
    att = rev.attachment if rev is not None else None
    if att is None:
        return f"cert:{cert.id}"
    return f"hash:{att.file_hash}" if att.file_hash else f"att:{att.id}"


def _validity(cert: Certificate) -> str:
    rev = cert.current_revision
    state, _expired, _days = derive_validity(
        rev.valid_from if rev else None, rev.valid_until if rev else None, today=today_malaysia()
    )
    return _STATE_LABEL.get(state, "unknown")


def _rep_order(cert: Certificate):
    rev = cert.current_revision
    until = rev.valid_until if rev is not None and rev.valid_until is not None else None
    return (
        _validity(cert) == "expired",
        -(until.toordinal() if until else 0),
        cert.scheme or "",
        cert.certificate_number or "",
    )


class _Group:
    """One list row: the certificates sharing a file, their coverage and the user's markers."""

    def __init__(self, members: List[Certificate], derived: set[str]):
        self.members = sorted(members, key=_rep_order)
        self.rep = self.members[0]
        self.derived = derived  # certificate ids reached through a quoted product
        self.coverage: Dict[str, tuple[CertificateProduct, Certificate]] = {}
        self._file: Any = False
        self._has_text: Optional[bool] = None
        self._page_count: Optional[int] = None
        self.unreadable = False  # a file is on record but the object could not be read

    @property
    def rev(self):
        return self.rep.current_revision

    @property
    def attachment(self) -> Optional[Attachment]:
        return self.rev.attachment if self.rev is not None else None

    def member_ids(self) -> List[str]:
        return [str(m.id) for m in self.members]

    def file(self, db: Session) -> Optional[bytes]:
        if self._file is False:
            self._file = None
            att = self.attachment
            if att is not None:
                from app.services.resources_service import AttachmentService

                try:
                    self._file = AttachmentService(db).get_file_content_for(att)
                except Exception:  # noqa: BLE001 - an unreadable object is a state, not a crash
                    logger.warning("certificate file unreadable: %s", att.id, exc_info=True)
                if self._file is None:
                    self.unreadable = True
        return self._file

    def release(self) -> None:
        """Drop the file bytes (read again on demand); `unreadable` is kept."""
        if not self.unreadable:
            self._file = False

    def learn(self, cache: Optional[dict]) -> None:
        """Take the text flag and page count a current cache already knows, so no read is needed."""
        if not cache:
            return
        if self._has_text is None and cache.get("has_text") is not None:
            self._has_text = bool(cache["has_text"])
        if self._page_count is None and cache.get("page_count") is not None:
            self._page_count = int(cache["page_count"])

    def page_count(self, db: Session) -> Optional[int]:
        if self._page_count is None:
            data = self.file(db)
            self._page_count = pdfs.page_count(data) if data else None
        return self._page_count

    def has_text(self, db: Session) -> bool:
        if self._has_text is None:
            data = self.file(db)
            self._has_text = bool(data) and pdfs.find_boxes(data, "")["has_text"]
        return self._has_text


def _with_file():
    """CERT-TAB-UX: load each certificate's current revision and its attachment in two queries,
    not two per certificate (79 statements on a 34-certificate quote before, 13 after)."""
    return selectinload(Certificate.current_revision).selectinload(CertificateRevision.attachment)


def _groups(db: Session, document, quoted: Dict[str, str], markers) -> List[_Group]:
    derived: Dict[str, Certificate] = {}
    coverage: Dict[str, List[CertificateProduct]] = {}
    if quoted:
        rows = (
            db.query(CertificateProduct, Certificate)
            .join(Certificate, Certificate.id == CertificateProduct.certificate_id)
            .filter(CertificateProduct.product_id.in_(list(quoted)), Certificate.status == "active")
            .options(_with_file())
            .all()
        )
        for cp, cert in rows:
            derived[str(cert.id)] = cert
            coverage.setdefault(str(cert.id), []).append(cp)
    manual_ids = [cid for cid, m in markers.items() if m.included and m.source == "manual" and cid not in derived]
    certs: Dict[str, Certificate] = dict(derived)
    if manual_ids:
        manual = db.query(Certificate).options(_with_file())
        for cert in manual.filter(Certificate.id.in_(manual_ids), Certificate.status == "active"):
            certs[str(cert.id)] = cert
    certs = {cid: c for cid, c in certs.items() if not (cid in markers and not markers[cid].included)}
    if not certs:
        return []
    # Coverage of manual certificates (they may still cover a quoted product through no auto path).
    all_cov = (
        db.query(CertificateProduct)
        .filter(CertificateProduct.certificate_id.in_(list(certs)), CertificateProduct.product_id.in_(list(quoted)))
        .all()
        if quoted
        else []
    )
    by_key: Dict[str, List[Certificate]] = {}
    for cert in certs.values():
        by_key.setdefault(_file_key(cert), []).append(cert)
    groups = []
    for members in by_key.values():
        group = _Group(members, set(derived))
        for cp in all_cov:
            owner = next((m for m in group.members if str(m.id) == str(cp.certificate_id)), None)
            if owner is None:
                continue
            pid = str(cp.product_id)
            if pid not in group.coverage or owner is group.rep:
                group.coverage[pid] = (cp, owner)
        groups.append(group)
    groups.sort(key=lambda g: (g.rep.scheme or "", g.rep.certificate_number or ""))
    return groups


def _find_group(groups: List[_Group], certificate_id: str) -> _Group:
    for group in groups:
        if str(certificate_id) in group.member_ids():
            return group
    raise _not_found()


def _context(db: Session, document):
    quoted = _quoted_products(db, document)
    markers = _markers(db, document)
    return quoted, markers, _groups(db, document, quoted, markers)


# ----------------------------------------------------------------------------- boxes


def _tag(boxes: List[dict], product_id: Optional[str]) -> List[dict]:
    return [{**b, "product_id": product_id} for b in boxes]


_SAME_ROW = 0.002


def _merge_rows(boxes: List[dict]) -> List[dict]:
    """Two products whose codes share one table row find the same box: keep one per row. The
    merged box belongs to no single product when the products differ, and `product_ids` keeps
    every product that fed it so a default save can give each its own box again."""
    out: List[dict] = []
    for box in boxes:
        twin = next(
            (
                kept
                for kept in out
                if kept["page"] == box["page"]
                and all(abs(kept[k] - box[k]) <= _SAME_ROW for k in ("x", "y", "w", "h"))
            ),
            None,
        )
        pid = box.get("product_id")
        if twin is None:
            out.append({**box, "product_ids": [pid] if pid else []})
            continue
        if pid and pid not in twin["product_ids"]:
            twin["product_ids"].append(pid)
        if twin.get("product_id") != pid:
            twin["product_id"] = None
    return out


def _resolve(
    db: Session, group: _Group, quoted: Dict[str, str], marker, hand_added: bool = False, trust_miss: bool = True
) -> Dict[str, Any]:
    """CERT-3/4/5/14: the products' codes and states, the boxes in force and the marked state.

    `trust_miss`: the list takes a remembered missing file at its word and never calls storage for
    it; the box editor (`detail`) passes False and reads the file itself, so a file that is back
    is seen and the miss forgotten."""
    rev = group.rev
    rev_id = str(rev.id) if rev is not None else None
    override = marker.boxes if marker is not None and marker.boxes and rev_id and marker.boxes.get("revision_id") == rev_id else None
    products: List[dict] = []
    all_boxes: List[dict] = []
    any_manual = any_needed = False

    for pid, (cp, owner) in sorted(group.coverage.items(), key=lambda kv: quoted.get(kv[0], "")):
        owner_rev = owner.current_revision
        owner_rev_id = str(owner_rev.id) if owner_rev is not None else None
        entry = {
            "product_id": pid,
            "product_code": quoted.get(pid, ""),
            "coverage_id": str(cp.id),
            "model_code": cp.model_code,
            "model_code_source": cp.model_code_source,
            "code_used": None,
            "number_only": False,
            "state": "code_needed",
        }
        products.append(entry)
        if group.attachment is None:
            continue
        cache = cp.boxes if isinstance(cp.boxes, dict) else None
        current = bool(cache) and cache.get("revision_id") == owner_rev_id
        if current and cache.get("missing"):
            if trust_miss and _miss_fresh(cache):
                group.unreadable = True
                continue
            cache, current = None, False
        manual_cache = current and cache.get("source") == "manual"
        if current:
            group.learn(cache)
        if not cp.model_code and not manual_cache and not current:
            # First look at this revision with no code: read once, then remember the answer
            # (a suggestion, or the negative result) so no later read parses the file again.
            data = group.file(db)
            if data is None:
                if group.unreadable:
                    _remember_miss(db, cp, owner_rev_id)
                continue
            has_text = group.has_text(db)
            suggestion = pdfs.suggest_code(data, quoted.get(pid, "")) if has_text else None
            if suggestion:
                cp.model_code, cp.model_code_source, cp.boxes = suggestion, "ai", None
                entry["model_code"], entry["model_code_source"] = suggestion, "ai"
            else:
                cp.boxes = {
                    "revision_id": owner_rev_id,
                    "code": None,
                    "source": "auto",
                    "has_text": has_text,
                    "page_count": group.page_count(db),
                    "boxes": [],
                }
            db.info["qcert_dirty"] = True
            cache = cp.boxes if isinstance(cp.boxes, dict) else None
        code = cp.model_code
        entry["code_used"] = code
        entry["number_only"] = bool(code) and pdfs.is_number_only(code)
        if manual_cache:
            boxes = _tag(cache.get("boxes") or [], pid)
            entry["state"] = "edited"
            any_manual = True
        elif not code:
            any_needed = True
            continue
        else:
            valid = (
                bool(cache)
                and cache.get("revision_id") == owner_rev_id
                and (cache.get("source") == "manual" or cache.get("code") == code)
            )
            if valid:
                boxes, has_text = _tag(cache.get("boxes") or [], pid), bool(cache.get("has_text", True))
                group.learn(cache)
            else:
                data = group.file(db)
                if data is None:
                    if group.unreadable:
                        _remember_miss(db, cp, owner_rev_id)
                    continue
                found = pdfs.find_boxes(data, code)
                has_text = found["has_text"]
                boxes = _tag(found["boxes"], pid)
                group._has_text = has_text
                cp.boxes = {
                    "revision_id": owner_rev_id,
                    "code": code,
                    "source": "auto",
                    "has_text": has_text,
                    "page_count": group.page_count(db),
                    "boxes": boxes,
                }
                db.info["qcert_dirty"] = True
            if not has_text:
                entry["state"] = "no_text"
            elif boxes:
                # CERT-TAB-UX (owner, 11 Nov): a box found by a guessed (`ai`) code is just marked;
                # there is no separate "Suggested, check" state. The pencil still fixes a wrong code.
                entry["state"] = "found"
            else:
                entry["state"] = "not_found"
        all_boxes.extend(boxes)

    if override is not None:
        boxes, source = list(override.get("boxes") or []), SCOPE_QUOTE
    else:
        boxes, source = _merge_rows(all_boxes), SCOPE_DEFAULT
    count = len(boxes)
    _unmark_boxless(products, boxes)

    if group.attachment is None or group.unreadable:
        state = "no_file"
    elif override is not None or any_manual:
        state = "edited"
    elif not products:
        state = "none"
    elif count == 0 and (
        group._has_text is False
        or (any(p["code_used"] for p in products) and all(p["state"] == "no_text" for p in products if p["code_used"]))
    ):
        state = "no_text"
    elif count > 0:
        state = "found"
    elif any_needed:
        state = "code_needed"
    else:
        state = "not_found"
    # CERT-16: an AI-linked certificate of a text file that prints none of the quoted codes is
    # listed but not verified. Hand-added rows, manual links, scans and missing files always are.
    verified = True
    if (
        state in ("not_found", "code_needed")
        and not hand_added
        and all(cp.source != "manual" for cp, _owner in group.coverage.values())
    ):
        verified = False
        state = "not_on_certificate"
    return {
        "products": products,
        "boxes": boxes,
        "box_source": source,
        "marked": {"count": count, "state": state},
        "verified": verified,
    }


def _unmark_boxless(products: List[dict], boxes: List[dict]) -> None:
    """CERT-TAB-UX (crew pass, 11 Nov): a product's state follows the boxes in force. A product
    marked by its code whose box was deleted (for this quote, or as its default) reads `unmarked`.
    A box that names no product (drawn for this quote) may be any product's, so then none is."""
    named: set[str] = set()
    for box in boxes:
        ids = [str(i) for i in (box.get("product_ids") or []) if i]
        if box.get("product_id"):
            ids.append(str(box["product_id"]))
        if not ids:
            return
        named.update(ids)
    for product in products:
        if product["state"] in ("found", "edited") and product["product_id"] not in named:
            product["state"] = "unmarked"


# ----------------------------------------------------------------------------- rows


def _effective_send(marker, validity: str, has_file: bool, verified: bool = True) -> bool:
    if marker is not None and marker.send_to_customer is True:
        return True
    if not verified:
        return False
    if marker is not None and marker.send_to_customer is not None:
        return bool(marker.send_to_customer)
    return validity != "expired" and has_file


def _row(db: Session, group: _Group, quoted, markers, trust_miss: bool = True) -> Dict[str, Any]:
    cert, rev = group.rep, group.rev
    marker = markers.get(str(cert.id))
    hand_added = str(cert.id) not in group.derived and marker is not None
    resolved = _resolve(db, group, quoted, marker, hand_added, trust_miss)
    validity = _validity(cert)
    has_file = group.attachment is not None
    return {
        "certificate_id": str(cert.id),
        "also_filed_as": [
            {"certificate_id": str(m.id), "scheme": m.scheme, "certificate_number": m.certificate_number}
            for m in group.members[1:]
        ],
        "scheme": cert.scheme,
        "certificate_number": cert.certificate_number,
        "title": cert.title,
        "certifying_body": cert.certifying_body,
        "valid_until": rev.valid_until.isoformat() if rev is not None and rev.valid_until else None,
        "validity_state": validity,
        "source": "manual" if str(cert.id) not in group.derived and marker is not None else "auto",
        "products": [{"product_id": p["product_id"], "product_code": p["product_code"]} for p in resolved["products"]],
        "marked": resolved["marked"],
        "send_to_customer": _effective_send(marker, validity, has_file, resolved["verified"]),
        "verified": resolved["verified"],
        "has_file": has_file,
        "_resolved": resolved,
    }


def _public(row: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in row.items() if k != "_resolved"}


def list_rows(db: Session, document) -> List[Dict[str, Any]]:
    quoted, markers, groups = _context(db, document)
    rows = []
    for group in groups:
        rows.append(_row(db, group, quoted, markers))
        group.release()  # a first look reads files one at a time, never all of them at once
    rows.sort(key=lambda r: not r["verified"])  # stable: verified first, scheme and number kept
    db.flush()
    return [_public(r) for r in rows]


def get_row(db: Session, document, certificate_id: str) -> Dict[str, Any]:
    quoted, markers, groups = _context(db, document)
    group = _find_group(groups, certificate_id)
    row = _public(_row(db, group, quoted, markers))
    db.flush()
    return row


def detail(db: Session, document, certificate_id: str) -> Dict[str, Any]:
    quoted, markers, groups = _context(db, document)
    group = _find_group(groups, certificate_id)
    row = _row(db, group, quoted, markers, trust_miss=False)
    resolved = row["_resolved"]
    out = _public(row)
    out.update(
        {
            "revision_id": str(group.rev.id) if group.rev is not None else None,
            "page_count": group.page_count(db) if group.attachment is not None else None,
            "has_text": group.has_text(db),
            "box_source": resolved["box_source"],
            "boxes": resolved["boxes"],
            "products": resolved["products"],
        }
    )
    db.flush()
    return out


def file_for(db: Session, document, certificate_id: str) -> bytes:
    _quoted, _markers_, groups = _context(db, document)
    group = _find_group(groups, certificate_id)
    data = group.file(db)
    if data is None:
        raise _not_found()
    return data


# ----------------------------------------------------------------------------- writes


def _marker_for(db: Session, document, certificate_id: str, user_id: Optional[str], *, source: str = "auto"):
    marker = (
        db.query(ProjectQuotationDocumentCertificate)
        .filter(
            ProjectQuotationDocumentCertificate.document_id == document.id,
            ProjectQuotationDocumentCertificate.certificate_id == certificate_id,
        )
        .first()
    )
    if marker is None:
        marker = ProjectQuotationDocumentCertificate(
            company_id=document.company_id,
            document_id=document.id,
            certificate_id=certificate_id,
            included=True,
            source=source,
            created_by=str(user_id) if user_id else None,
        )
        db.add(marker)
        db.flush()
    return marker


def add(db: Session, document, certificate_id: str, user_id: Optional[str]) -> Dict[str, Any]:
    quoted, markers, groups = _context(db, document)
    try:
        _find_group(groups, certificate_id)
    except AppException:
        cert = db.query(Certificate).filter(Certificate.id == certificate_id, Certificate.status == "active").first()
        if cert is None:
            raise _not_found()
        marker = markers.get(str(cert.id))
        if marker is None:
            _marker_for(db, document, str(cert.id), user_id, source="manual")
        else:
            marker.included = True
        db.flush()
    return get_row(db, document, certificate_id)


def remove(db: Session, document, certificate_id: str, user_id: Optional[str] = None) -> None:
    """Take a certificate (and every certificate filed as the same file) off the list."""
    _quoted, markers, groups = _context(db, document)
    group = _find_group(groups, certificate_id)
    for member in group.members:
        cid = str(member.id)
        marker = markers.get(cid)
        if cid in group.derived:
            marker = marker or _marker_for(db, document, cid, user_id)
            marker.included = False
        elif marker is not None:
            db.delete(marker)
    db.flush()


def assert_removable(db: Session, document, certificate_id: str) -> None:
    _quoted, _markers_, groups = _context(db, document)
    _find_group(groups, certificate_id)


def set_send(db: Session, document, certificate_id: str, value: Optional[bool], user_id: Optional[str]):
    _quoted, _markers_, groups = _context(db, document)
    group = _find_group(groups, certificate_id)
    existing = _markers_.get(str(group.rep.id))
    if existing is None and value is None:
        return get_row(db, document, certificate_id)  # nothing stored, nothing to clear
    marker = existing or _marker_for(db, document, str(group.rep.id), user_id)
    marker.send_to_customer = value
    db.flush()
    return get_row(db, document, certificate_id)


MAX_BOX_PAGE = 2000


def _invalid(message: str = "A box is not valid.") -> AppException:
    return AppException(status_code=422, message=message, code="certificate_box_invalid")


def validate_boxes(boxes: List[dict], page_count: Optional[int] = None) -> List[dict]:
    """Every box inside the page (fractions), finite, on a page that exists (the file's page count
    when known, else at most 2000), with a UUID or null product."""
    if len(boxes) > MAX_BOXES:
        raise _invalid("Too many boxes.")
    last_page = page_count if page_count else MAX_BOX_PAGE
    clean = []
    for box in boxes:
        try:
            page, x, y, w, h = int(box["page"]), float(box["x"]), float(box["y"]), float(box["w"]), float(box["h"])
        except (KeyError, TypeError, ValueError, OverflowError):
            raise _invalid()
        if not all(math.isfinite(v) for v in (x, y, w, h)):
            raise _invalid()
        eps = 1e-9
        if page < 1 or page > last_page or not (0 <= x <= 1 and 0 <= y <= 1) or w <= 0 or h <= 0:
            raise _invalid("A box is outside the page.")
        if x + w > 1 + eps or y + h > 1 + eps:
            raise _invalid("A box is outside the page.")
        product_id = box.get("product_id")
        if product_id is not None:
            try:
                if len(str(product_id)) > 36:
                    raise ValueError
                uuid.UUID(str(product_id))
            except (TypeError, ValueError):
                raise _invalid()
            product_id = str(product_id)
        item = {"page": page, "x": x, "y": y, "w": w, "h": h, "product_id": product_id}
        # A box merged from several products keeps them (CERT-TAB-UX), so a quote-only save still
        # knows which products each box marks.
        product_ids = box.get("product_ids") or []
        if product_ids:
            if not isinstance(product_ids, list) or len(product_ids) > 50:
                raise _invalid()
            try:
                item["product_ids"] = [str(uuid.UUID(str(i))) for i in product_ids if len(str(i)) <= 36]
            except (TypeError, ValueError):
                raise _invalid()
        clean.append(item)
    return clean


def put_boxes(
    db: Session, document, certificate_id: str, scope: str, boxes: List[dict], user_id: Optional[str]
) -> Dict[str, Any]:
    """`scope=default` is gated by the route (certificates.edit)."""
    quoted, _markers_, groups = _context(db, document)
    group = _find_group(groups, certificate_id)
    boxes = validate_boxes(boxes, group.page_count(db))
    rep_id = str(group.rep.id)
    if scope == SCOPE_QUOTE:
        marker = _marker_for(db, document, rep_id, user_id)
        marker.boxes = {"revision_id": str(group.rev.id) if group.rev is not None else None, "boxes": boxes}
    else:
        for box in boxes:
            if not box["product_id"] or str(box["product_id"]) not in group.coverage:
                raise AppException(
                    status_code=422,
                    message="A box must belong to a product this certificate covers.",
                    code="certificate_box_product_invalid",
                )
        has_text = group.has_text(db)
        for pid, (cp, owner) in group.coverage.items():
            owner_rev = owner.current_revision
            cp.boxes = {
                "revision_id": str(owner_rev.id) if owner_rev is not None else None,
                "code": cp.model_code,
                "source": "manual",
                "has_text": has_text,
                "page_count": group.page_count(db),
                "boxes": [b for b in boxes if str(b["product_id"]) == pid],
            }
        marker = (
            db.query(ProjectQuotationDocumentCertificate)
            .filter(
                ProjectQuotationDocumentCertificate.document_id == document.id,
                ProjectQuotationDocumentCertificate.certificate_id == rep_id,
            )
            .first()
        )
        if marker is not None:
            marker.boxes = None
    db.flush()
    return detail(db, document, certificate_id)


def drop_quote_boxes(db: Session, document, certificate_id: str) -> Dict[str, Any]:
    _quoted, markers, groups = _context(db, document)
    group = _find_group(groups, certificate_id)
    marker = markers.get(str(group.rep.id))
    if marker is not None:
        marker.boxes = None
        db.flush()
    return detail(db, document, certificate_id)


# ----------------------------------------------------------------------------- freeze and export


def _sendable(db: Session, document) -> List[tuple[_Group, Dict[str, Any]]]:
    quoted, markers, groups = _context(db, document)
    pairs = [(group, _row(db, group, quoted, markers)) for group in groups]
    pairs.sort(key=lambda pair: not pair[1]["verified"])
    return [(group, row) for group, row in pairs if row["send_to_customer"]]


def snapshot(db: Session, document) -> List[dict]:
    """CERT-11: the list that goes out with an issue, frozen."""
    out = []
    for group, row in _sendable(db, document):
        out.append(
            {
                "certificate_id": str(group.rep.id),
                "revision_id": str(group.rev.id) if group.rev is not None else None,
                "attachment_id": str(group.attachment.id) if group.attachment is not None else None,
                "scheme": group.rep.scheme,
                "certificate_number": group.rep.certificate_number,
                "boxes": row["_resolved"]["boxes"],
            }
        )
    db.flush()
    return out


def live_export_rows(db: Session, document) -> List[dict]:
    """The live list in the snapshot's shape (CERT-12 without an issue)."""
    return snapshot(db, document)


def export_entries(db: Session, document, issue) -> List[dict]:
    """What an export carries: the issue's frozen list; the live list for a draft, and for a
    revision issued before certificates were frozen (snapshot NULL, never frozen)."""
    if issue is not None and issue.certificates is not None:
        return list(issue.certificates)
    return live_export_rows(db, document)


def export_count(db: Session, document, issue) -> int:
    if issue is not None and issue.certificates is not None:
        return len([c for c in issue.certificates if c.get("attachment_id")])
    return len([r for r in live_export_rows(db, document) if r["attachment_id"]])


def export_filename(document, issue) -> str:
    """`<document no> <rev> Certificates.pdf`; a draft has no revision."""
    if issue is None:
        return f"{document.document_no} Certificates.pdf"
    rev = issue.revision_label or f"R{issue.issue_no}"
    return f"{document.document_no} {rev} Certificates.pdf"
