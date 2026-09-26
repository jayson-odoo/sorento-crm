"""Cost-price change sets: upload, review, apply (#1288, Lane A, plan sections 5-7).

Backs the routes under `/api/v1/procurement/cost-price-changes`. Matching reuses the shared
engine `proforma_invoice_service`/`supplier_code_matcher` already use for the PI, packing-list
and loading-plan uploads (plan section 6, AC-S1-08) - called MODULE-QUALIFIED
(`pi_service._products_by_code(...)`, `matcher.resolve(...)`) so a caller spying on the source
module (a preview that must not remember anything) observes the same calls the PI apply makes.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal
from typing import Iterable, Optional

from fastapi import Request
from sqlalchemy.orm import Session

import app.services.scm.proforma_invoice_service as pi_service
import app.services.scm.supplier_code_matcher as matcher
from app.services.error_handler import AppException
from app.services.procurement.supplier_price_list_reader import read_supplier_price_list
from app.services.scm.currency_resolution import supplier_price_list_currency

UPLOAD_PERM = "procurement.cost_price_changes.upload"
VIEW_PERM = "procurement.cost_price_changes.view"
VERIFY_PERM = "procurement.cost_price_changes.verify"

_UNRESOLVED_STATES = {"needs_attention"}

_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def _require_uuid(value, *, field: str = "id", code: str = "invalid_id") -> str:
    """A malformed id is a 422, not a 500 from a raw `WHERE id = :value` against a
    UUID column (Nits, security review). Distinct from `validate_uuid_path`
    (`app.services.uuid_path_param`), which answers 404 for a detail GET - every
    OTHER route in this file (apply, submit, decide, patch, ...) reads a bad id as
    a validation failure instead."""
    s = str(value or "")
    if not _UUID_RE.match(s):
        raise AppException(422, f"Invalid {field}.", detail={"code": code}, code=code)
    return s.lower()


def _actor_id(request: Optional[Request], current_user: Optional[dict]) -> Optional[str]:
    """The REAL user id for created_by/submitted_by/decided_by/applied_by/mapped_by and
    every `log_audit` call (B2, security review): during an impersonation session
    `current_user` is the EFFECTIVE (target) identity, and the real admin driving it
    is on `request.state.real_user` - `get_actor_user_id` resolves that; outside
    impersonation (or with no request, e.g. a background/worker caller) the two are
    the same id."""
    if request is not None:
        from app.dependencies import get_actor_user_id

        return get_actor_user_id(request, current_user or {})
    return (current_user or {}).get("id")

# `product_suppliers` and `product_supplier_costs` are `__audit_track__ = True` (#1288,
# AC-AU-01) - production registers the listener once at `app.main`'s startup event, but a
# bare `TestClient(app)` (no `with` block, this lane's whole test harness) never fires that
# event. Calling the idempotent registration here, at IMPORT time of the module every route
# in this file pulls in, is what makes the auto-tracked rows exist under that harness -
# exactly the pattern `tests/test_customer_audit.py` and its siblings use per-file, except
# this one file is shared by every cost-price test.
from app.services.audit_service import register_audit_listeners  # noqa: E402

register_audit_listeners()


def _u(value) -> str:
    return str(value)


def _norm_match(value: Optional[str]) -> str:
    text = unicodedata.normalize("NFKC", value or "").upper()
    return re.sub(r"[^0-9A-Z一-鿿]+", "", text)


def _suggest_supplier(db: Session, letterhead_texts: list[str]):
    from app.models.procurement import Supplier

    norms = [n for n in (_norm_match(t) for t in letterhead_texts) if n]
    if not norms:
        return None
    hits = []
    for supplier in db.query(Supplier).filter(Supplier.is_active.is_(True)).all():
        code_norm = _norm_match(supplier.supplier_code)
        name_norm = _norm_match(supplier.supplier_name)
        for n in norms:
            if (code_norm and code_norm in n) or (name_norm and name_norm in n) or \
               (code_norm and n in code_norm) or (name_norm and n in name_norm):
                hits.append(supplier)
                break
    unique = {s.id: s for s in hits}
    return next(iter(unique.values())) if len(unique) == 1 else None


def _serialize_supplier(supplier) -> Optional[dict]:
    if supplier is None:
        return None
    return {
        "id": _u(supplier.id),
        "supplier_code": supplier.supplier_code,
        "supplier_name": supplier.supplier_name,
    }


def _serialize_product(product) -> Optional[dict]:
    if product is None:
        return None
    return {
        "id": _u(product.id),
        "product_code": product.product_code,
        "description": product.product_name,
    }


def _file_date(filename: str) -> Optional[str]:
    m = re.search(r"(20\d{2})(\d{2})(\d{2})", filename or "")
    if not m:
        return None
    yyyy, mm, dd = m.groups()
    try:
        return date(int(yyyy), int(mm), int(dd)).isoformat()
    except ValueError:
        return None


def _sheets_summary(parsed) -> list[dict]:
    return [
        {
            "name": s.name,
            "header_row": s.header_row,
            "rows": len(s.rows),
            "skipped_reason": s.skipped_reason,
        }
        for s in parsed.sheets
    ]


def _resolve_currency(db, parsed, *, requested: Optional[str], supplier_id: Optional[str]):
    """`(code, source)` - AC-S1-07: the header's own token wins, else the supplier's
    existing links, else what the caller typed, else nothing."""
    if parsed.header_currency:
        return parsed.header_currency, "header"
    if supplier_id:
        code = supplier_price_list_currency(db, supplier_id)
        if code:
            return code, "supplier"
    if requested:
        return requested.strip().upper(), "form"
    return None, None


def probe(db: Session, data: bytes, filename: str, *, company_scope=None) -> dict:
    if company_scope is not None and len(company_scope) != 1:
        raise AppException(422, "Pick one company before uploading a price list.", detail={"code": "pick_one_company"}, code="pick_one_company")
    parsed = read_supplier_price_list(data, filename)
    suggested = _suggest_supplier(db, parsed.letterhead)
    code, source = _resolve_currency(db, parsed, requested=None, supplier_id=(str(suggested.id) if suggested else None))
    return {
        "file_name": filename,
        "file_date": _file_date(filename),
        "sheets": _sheets_summary(parsed),
        "total_rows": parsed.total_rows,
        "suggested_supplier": _serialize_supplier(suggested),
        "currency": {"code": code, "source": source},
    }


def _match_codes(db: Session, supplier_id: Optional[str], codes: set[str]) -> dict[str, dict]:
    """`{code: Match}` - the exact company-scoped lookup, then the supplier code ladder,
    `remember=False` (AC-S1-08). Module-qualified calls so a spy on the source module sees
    them; the ladder's own `Match` (with its rung) is kept, unlike
    `proforma_invoice_service._with_supplier_codes`, which flattens it away."""
    out: dict[str, dict] = {}
    known = pi_service._products_by_code(db, codes) if codes else {}
    for code in codes:
        hit = known.get(code.upper())
        if hit and hit.get("id"):
            out[code] = {"product_id": hit["id"], "outcome": "exact", "rung": None}
    missing = {c for c in codes if c not in out}
    if missing and supplier_id:
        found = matcher.resolve(db, supplier_id, missing, remember=False)
        for code, m in found.items():
            if not m.product_id:
                continue  # a product-set bind is refused on this screen (plan section 6)
            outcome = "alias" if m.rung == "alias" else "ladder"
            rung = None if outcome == "alias" else m.rung
            out[code] = {"product_id": m.product_id, "outcome": outcome, "rung": rung}
    return out


def _line_state_for(link, set_currency: str, new_price: Optional[Decimal], has_dates: bool) -> tuple[str, Optional[Decimal], Optional[str]]:
    """`(line_state, current_unit_cost, current_currency)` for a MATCHED, priced code."""
    if link is None:
        return "new_link", None, None
    current_cost = link.unit_cost
    current_currency = link.currency
    if (
        current_cost is not None
        and new_price is not None
        and current_cost == new_price
        and (current_currency or None) == set_currency
        and not has_dates
    ):
        return "unchanged", current_cost, current_currency
    return "changed", current_cost, current_currency


def _change_pct(current: Optional[Decimal], new: Optional[Decimal]) -> Optional[float]:
    if current is None or new is None or current == 0:
        return None
    return float((new - current) / current * 100)


def _build_lines(db: Session, parsed, *, supplier_id: str, set_currency: str, has_dates: bool) -> list[dict]:
    from app.models.procurement import ProductSupplier

    all_rows = [(sheet.name, row) for sheet in parsed.sheets for row in sheet.rows]
    codes = {row.supplier_code for _, row in all_rows if row.supplier_code}
    matches = _match_codes(db, supplier_id, codes)

    # Existing links for every matched product, one query.
    matched_product_ids = {m["product_id"] for m in matches.values()}
    links_by_product: dict[str, "ProductSupplier"] = {}
    if matched_product_ids:
        for link in (
            db.query(ProductSupplier)
            .filter(
                ProductSupplier.supplier_id == supplier_id,
                ProductSupplier.product_id.in_(matched_product_ids),
            )
            .all()
        ):
            links_by_product[str(link.product_id)] = link

    lines: list[dict] = []
    product_line_idx: dict[str, list[int]] = {}
    for sheet_name, row in all_rows:
        match = matches.get(row.supplier_code) if row.supplier_code else None
        product_id = match["product_id"] if match else None
        match_outcome = match["outcome"] if match else "unmatched"
        match_rung = match["rung"] if match else None

        current_cost = current_currency = None
        line_state = "needs_attention"
        if row.price is None:
            line_state = "needs_attention"
        elif product_id is None:
            line_state = "needs_attention"
        else:
            link = links_by_product.get(str(product_id))
            line_state, current_cost, current_currency = _line_state_for(
                link, set_currency, row.price, has_dates
            )

        line = {
            "sheet": sheet_name,
            "row_no": row.row_no,
            "line_no": row.line_no,
            "supplier_code_raw": row.supplier_code_raw,
            "supplier_code": row.supplier_code,
            "code_note": row.code_note,
            "configuration": row.configuration,
            "flags": set(row.flags),
            "match_outcome": match_outcome,
            "match_rung": match_rung,
            "product_id": product_id,
            "current_unit_cost": current_cost,
            "current_currency": current_currency,
            "new_unit_cost": row.price,
            "line_state": line_state,
        }
        lines.append(line)
        if product_id:
            product_line_idx.setdefault(str(product_id), []).append(len(lines) - 1)

    for product_id, idxs in product_line_idx.items():
        if len(idxs) > 1:
            for i in idxs:
                lines[i]["flags"].add("duplicate_code")

    return lines


def _create_change_set_code(db: Session, company_id: Optional[str]) -> str:
    from app.services.numbering_defaults import (
        COST_PRICE_CHANGE_SET_DOC_TYPE,
        seed_cost_price_change_set_rule,
    )
    from app.services.numbering_service import NumberingService

    def _next() -> Optional[str]:
        return NumberingService(db).get_next_number(
            COST_PRICE_CHANGE_SET_DOC_TYPE, date.today(), company_id=company_id, commit_rule=False
        )

    number = _next()
    if not number:
        seed_cost_price_change_set_rule(db, company_id=company_id)
        number = _next()
    return number or f"CPC-{datetime.utcnow().strftime('%H%M%S%f')[:8]}"


#: S3 (security review): none of these belong in a real filename, and each is a
#: building block of a `Content-Disposition` header parameter (`filename="..."`,
#: `filename*=...`) - stripping them here means the stored name can never read
#: back as a second parameter, whatever escaping `content_disposition` applies.
_UNSAFE_FILENAME_RE = re.compile(r'["=;\r\n]')


def _sanitize_filename(name: str) -> str:
    return _UNSAFE_FILENAME_RE.sub("_", name or "")


def _truncate_filename(name: str, max_len: int = 255) -> str:
    """S3 (security review): `file_name` is `VARCHAR(255)` - a longer name 500s at
    commit instead of truncating. Keeps the extension when there is a sane one."""
    if not name or len(name) <= max_len:
        return name
    dot = name.rfind(".")
    if 0 < dot < len(name) - 1 and len(name) - dot <= 20:
        ext = name[dot:]
        base_len = max_len - len(ext)
        if base_len > 0:
            return name[:base_len] + ext
    return name[:max_len]


def upload(
    db: Session,
    current_user: dict,
    *,
    data: bytes,
    filename: str,
    supplier_id: str,
    currency: Optional[str],
    start_date: Optional[str],
    end_date: Optional[str],
    company_scope,
    request: Optional[Request] = None,
) -> dict:
    from app.models.company import Company
    from app.models.cost_price import CostPriceChangeLine, CostPriceChangeSet
    from app.models.procurement import Supplier

    if not company_scope or len(company_scope) != 1:
        raise AppException(422, "Pick one company before uploading a price list.", detail={"code": "pick_one_company"}, code="pick_one_company")
    company_id = next(iter(company_scope))

    supplier = db.query(Supplier).filter(Supplier.id == supplier_id).first()
    if supplier is None:
        raise AppException(404, "Supplier not found.", code="NOT_FOUND")

    open_set = (
        db.query(CostPriceChangeSet)
        .filter(
            CostPriceChangeSet.supplier_id == supplier_id,
            CostPriceChangeSet.status.in_(("draft", "pending_verification")),
        )
        .first()
    )
    if open_set is not None:
        raise AppException(
            409, "This supplier already has an open price change.",
            detail={"code": "open_set_exists", "open_set": {"id": _u(open_set.id), "code": open_set.code}},
            code="open_set_exists",
        )

    parsed = read_supplier_price_list(data, filename)
    resolved_currency, _source = _resolve_currency(db, parsed, requested=currency, supplier_id=supplier_id)
    if not resolved_currency:
        raise AppException(422, "Enter the currency this price list is in.", detail={"code": "currency_required"}, code="currency_required")

    try:
        start = date.fromisoformat(start_date) if start_date else None
        end = date.fromisoformat(end_date) if end_date else None
    except ValueError:
        raise AppException(422, "Enter a valid date.", detail={"code": "invalid_date"}, code="invalid_date")
    if start and end and end < start:
        raise AppException(422, "Valid to cannot be before Valid from.", detail={"code": "end_before_start"}, code="end_before_start")

    actor_id = _actor_id(request, current_user)
    filename = _truncate_filename(_sanitize_filename(filename))
    code = _create_change_set_code(db, company_id)
    cs = CostPriceChangeSet(
        code=code, supplier_id=supplier_id, channel="staff_upload", status="draft",
        currency=resolved_currency, start_date=start, end_date=end,
        file_name=filename, source_meta={"sheets": _sheets_summary(parsed), "letterhead": parsed.letterhead},
        created_by_user_id=actor_id,
    )
    db.add(cs)
    db.flush()

    lines = _build_lines(db, parsed, supplier_id=supplier_id, set_currency=resolved_currency, has_dates=bool(start or end))
    for line in lines:
        db.add(CostPriceChangeLine(
            change_set_id=cs.id,
            sheet=line["sheet"], row_no=line["row_no"], line_no=line["line_no"],
            supplier_code_raw=line["supplier_code_raw"], supplier_code=line["supplier_code"],
            code_note=line["code_note"], configuration=line["configuration"],
            flags=sorted(line["flags"]),
            match_outcome=line["match_outcome"], match_rung=line["match_rung"],
            product_id=line["product_id"],
            current_unit_cost=line["current_unit_cost"], current_currency=line["current_currency"],
            new_unit_cost=line["new_unit_cost"], line_state=line["line_state"],
        ))

    cs.source_file_bytes = data
    cs.source_file_size = len(data)

    from app.services.audit_service import log_audit

    log_audit(
        db, "cost_price_change_sets", _u(cs.id), "COST_SET_UPLOAD",
        new_values={"file_name": filename, "rows": parsed.total_rows},
        user_id=actor_id,
    )
    db.commit()
    return get_detail(db, _u(cs.id), current_user)


# --------------------------------------------------------------------------- shared helpers


def _get_set_or_404(db: Session, set_id: str, *, for_update: bool = False):
    from app.models.cost_price import CostPriceChangeSet

    set_id = _require_uuid(set_id, field="id")
    q = db.query(CostPriceChangeSet).filter(CostPriceChangeSet.id == set_id)
    if for_update:
        # Nits (security review): every MUTATING call (apply/return/submit/decide/
        # patch) locks the set row first, closing the window where two requests
        # race a status transition against each other.
        q = q.with_for_update()
    cs = q.first()
    if cs is None:
        raise AppException(404, "This price change was not found. It may have been discarded.", code="NOT_FOUND")
    return cs


def _require_single_company_scope(db: Session, cs) -> None:
    """B1 (security review): patch/apply must refuse unless the session's own
    resolved scope is EXACTLY the set's company - not "the set happens to be
    visible", which an all-companies admin/superadmin scope would also satisfy
    while leaving cross-company writes unguarded."""
    from app.models.base import get_company_scope

    scope = get_company_scope(db)
    if (
        not isinstance(scope, (frozenset, set))
        or len(scope) != 1
        or next(iter(scope)) != str(cs.company_id)
    ):
        raise AppException(
            422, "Pick one company before making this change.",
            detail={"code": "pick_one_company"}, code="pick_one_company",
        )


def _display_name(db: Session, user_id: Optional[str]) -> Optional[str]:
    if not user_id:
        return None
    from app.models.user import User

    u = db.query(User).filter(User.id == user_id).first()
    if u is None:
        return None
    return u.name or u.email


def _user_has_permission(db: Session, user_id: Optional[str], slug: str) -> bool:
    if not user_id:
        return False
    from app.services.user_service import UserPermissionService

    return UserPermissionService(db).check_user_has_permission(user_id, slug)


def _verification_enabled(db: Session) -> bool:
    from app.models.user import SystemSetting

    row = db.query(SystemSetting).first()
    return bool(getattr(row, "cost_price_verification_enabled", False)) if row else False


def _line_mapper_ids(db: Session, set_id: str) -> set[str]:
    from app.models.cost_price import CostPriceChangeLine

    return {
        str(row[0])
        for row in (
            db.query(CostPriceChangeLine.mapped_by_user_id)
            .filter(
                CostPriceChangeLine.change_set_id == set_id,
                CostPriceChangeLine.mapped_by_user_id.isnot(None),
            )
            .distinct()
            .all()
        )
    }


def _assert_not_same_person(
    db: Session, cs, current_user: dict, *, request: Optional[Request] = None
) -> None:
    """Four-eyes (B2/S5, security review): blocks whoever uploaded, submitted, OR
    mapped any line of this set - checked against BOTH the effective principal
    (`current_user`) and the REAL actor behind it (`_actor_id`, so an admin cannot
    launder their own upload through an impersonated verifier's identity),
    superadmin included (this is a manual set-membership check, never routed
    through a permission bypass)."""
    ids = {str(uid) for uid in ((current_user or {}).get("id"), _actor_id(request, current_user)) if uid}
    if not ids:
        return
    blocked = {str(b) for b in (cs.created_by_user_id, cs.submitted_by_user_id) if b}
    blocked |= _line_mapper_ids(db, cs.id)
    if ids & blocked:
        raise AppException(
            403, "You cannot verify a set you uploaded, submitted or mapped yourself.",
            code="SAME_PERSON_CANNOT_VERIFY",
        )


_COUNT_KEYS = (
    "changed", "unchanged", "new_link", "unmatched", "duplicate_code",
    "needs_attention", "skipped", "accepted", "rejected", "undecided",
)


def _counts(db: Session, set_id: str) -> dict:
    from app.models.cost_price import CostPriceChangeLine

    counts = {k: 0 for k in _COUNT_KEYS}
    lines = db.query(CostPriceChangeLine).filter(CostPriceChangeLine.change_set_id == set_id).all()
    for ln in lines:
        if ln.skipped:
            counts["skipped"] += 1
            continue
        if ln.line_state in counts:
            counts[ln.line_state] += 1
        if ln.match_outcome == "unmatched":
            counts["unmatched"] += 1
        if ln.flags and "duplicate_code" in ln.flags:
            counts["duplicate_code"] += 1
        if ln.line_state in ("changed", "new_link"):
            if ln.decision == "accepted":
                counts["accepted"] += 1
            elif ln.decision == "rejected":
                counts["rejected"] += 1
            else:
                counts["undecided"] += 1
    return counts


def _unresolved_count(db: Session, set_id: str) -> int:
    from app.models.cost_price import CostPriceChangeLine

    n = 0
    for ln in (
        db.query(CostPriceChangeLine)
        .filter(CostPriceChangeLine.change_set_id == set_id, CostPriceChangeLine.skipped.is_(False))
        .all()
    ):
        if ln.line_state == "needs_attention" or (ln.flags and "duplicate_code" in ln.flags):
            n += 1
    return n


def _undecided_count(db: Session, set_id: str) -> int:
    from app.models.cost_price import CostPriceChangeLine

    return (
        db.query(CostPriceChangeLine)
        .filter(
            CostPriceChangeLine.change_set_id == set_id,
            CostPriceChangeLine.skipped.is_(False),
            CostPriceChangeLine.line_state.in_(("changed", "new_link")),
            CostPriceChangeLine.decision.is_(None),
        )
        .count()
    )


def _largest_rise(db: Session, set_id: str) -> Optional[dict]:
    from app.models.cost_price import CostPriceChangeLine

    best = None
    best_pct = None
    for ln in (
        db.query(CostPriceChangeLine)
        .filter(CostPriceChangeLine.change_set_id == set_id, CostPriceChangeLine.skipped.is_(False))
        .all()
    ):
        pct = _change_pct(ln.current_unit_cost, ln.new_unit_cost)
        if pct is None or pct <= 0:
            continue
        if best_pct is None or pct > best_pct:
            best, best_pct = ln, pct
    if best is None:
        return None
    return {"supplier_code": best.supplier_code, "change_pct": best_pct}


def get_detail(db: Session, set_id: str, current_user: Optional[dict]) -> dict:
    from app.models.procurement import Supplier

    cs = _get_set_or_404(db, set_id)
    supplier = db.query(Supplier).filter(Supplier.id == cs.supplier_id).first()
    verification_enabled = _verification_enabled(db)
    counts = _counts(db, set_id)
    unresolved = _unresolved_count(db, set_id)
    undecided = _undecided_count(db, set_id)

    uid = (current_user or {}).get("id")
    holds_upload = _user_has_permission(db, uid, UPLOAD_PERM)
    holds_verify = _user_has_permission(db, uid, VERIFY_PERM)
    is_same_person = bool(uid) and (
        uid in {cs.created_by_user_id, cs.submitted_by_user_id} or uid in _line_mapper_ids(db, set_id)
    )

    can_apply = can_submit = can_decide = can_return = False
    apply_blocked_reason = None
    if cs.status == "draft":
        # S1 (security review): a non-staff-channel draft (a RETURNED supplier
        # submission, back to draft) always needs a submit, whatever the global
        # setting - only a `staff_upload` draft can ever apply straight from here.
        if cs.channel == "staff_upload":
            if not verification_enabled and holds_upload:
                if unresolved:
                    apply_blocked_reason = f"{unresolved} row(s) still need you"
                else:
                    can_apply = True
            elif verification_enabled and holds_upload:
                can_submit = not unresolved
        elif holds_upload:
            can_submit = not unresolved
    elif cs.status == "pending_verification" and holds_verify and not is_same_person:
        can_decide = True
        can_return = True
        can_apply = not unresolved and not undecided

    can_discard = cs.status == "draft" and holds_upload
    sheets = (cs.source_meta or {}).get("sheets", [])
    largest_rise = _largest_rise(db, set_id)

    return {
        "id": _u(cs.id), "code": cs.code, "status": cs.status, "channel": cs.channel,
        "supplier": _serialize_supplier(supplier),
        "currency": cs.currency,
        "start_date": cs.start_date.isoformat() if cs.start_date else None,
        "end_date": cs.end_date.isoformat() if cs.end_date else None,
        # S4 (security review): `source_file_size` is a plain, non-deferred column -
        # reading it (unlike `source_file_bytes`) never forces the retained
        # spreadsheet's bytes to load on a list/detail read.
        "file_name": cs.file_name, "has_source_file": bool(cs.source_file_size),
        "sheets": sheets,
        "total_rows": sum(s.get("rows", 0) for s in sheets),
        "uploaded_by_name": _display_name(db, cs.created_by_user_id),
        "created_at": cs.created_at.isoformat() if cs.created_at else None,
        "submitted_by_name": _display_name(db, cs.submitted_by_user_id),
        "submitted_at": cs.submitted_at.isoformat() if cs.submitted_at else None,
        "returned_reason": cs.returned_reason,
        "returned_by_name": _display_name(db, cs.returned_by_user_id),
        "returned_at": cs.returned_at.isoformat() if cs.returned_at else None,
        "applied_by_name": _display_name(db, cs.applied_by_user_id),
        "applied_at": cs.applied_at.isoformat() if cs.applied_at else None,
        "verified": cs.verified,
        "verification_enabled": verification_enabled,
        "counts": counts,
        "largest_rise": largest_rise,
        "actions": {
            "can_apply": can_apply, "apply_blocked_reason": apply_blocked_reason,
            "apply_count": counts["changed"] + counts["new_link"],
            "can_submit": can_submit, "can_decide": can_decide, "can_return": can_return,
            "can_discard": can_discard, "decide_blocked_reason": None,
        },
    }


def list_sets(db: Session, *, page: int, limit: int, sort: str, dir: str, query: Optional[str],
              status: Optional[str], supplier_id: Optional[str]) -> dict:
    from app.models.cost_price import CostPriceChangeLine, CostPriceChangeSet
    from app.models.procurement import Supplier

    q = db.query(CostPriceChangeSet)
    if supplier_id:
        q = q.filter(CostPriceChangeSet.supplier_id == supplier_id)
    if status:
        statuses = [s.strip() for s in status.split(",") if s.strip()]
        if statuses:
            q = q.filter(CostPriceChangeSet.status.in_(statuses))
    if query:
        like = f"%{query.strip()}%"
        q = q.outerjoin(Supplier, Supplier.id == CostPriceChangeSet.supplier_id).filter(
            (CostPriceChangeSet.code.ilike(like))
            | (CostPriceChangeSet.file_name.ilike(like))
            | (Supplier.supplier_name.ilike(like))
            | (Supplier.supplier_code.ilike(like))
        )
    sort_map = {
        "code": CostPriceChangeSet.code,
        "created_at": CostPriceChangeSet.created_at,
        "applied_at": CostPriceChangeSet.applied_at,
    }
    sort_col = sort_map.get(sort or "created_at", CostPriceChangeSet.created_at)
    q = q.order_by(sort_col.desc() if (dir or "desc") == "desc" else sort_col.asc())

    total = q.count()
    rows = q.offset((page - 1) * limit).limit(limit).all()
    data = []
    for cs in rows:
        supplier = db.query(Supplier).filter(Supplier.id == cs.supplier_id).first()
        lines_changed = (
            db.query(CostPriceChangeLine)
            .filter(
                CostPriceChangeLine.change_set_id == cs.id,
                CostPriceChangeLine.skipped.is_(False),
                CostPriceChangeLine.line_state.in_(("changed", "new_link")),
            )
            .count()
        )
        data.append({
            "id": _u(cs.id), "code": cs.code, "status": cs.status,
            "supplier": _serialize_supplier(supplier),
            "channel": cs.channel, "file_name": cs.file_name, "currency": cs.currency,
            "start_date": cs.start_date.isoformat() if cs.start_date else None,
            "end_date": cs.end_date.isoformat() if cs.end_date else None,
            "lines_changed": lines_changed,
            "uploaded_by_name": _display_name(db, cs.created_by_user_id),
            "created_at": cs.created_at.isoformat() if cs.created_at else None,
            "applied_at": cs.applied_at.isoformat() if cs.applied_at else None,
            "verified": cs.verified,
            "verified_by_name": _display_name(db, cs.applied_by_user_id) if cs.verified else None,
        })
    return {"data": data, "total": total, "page": page, "limit": limit}


def _serialize_line(db: Session, line) -> dict:
    from app.models.product import Product

    product = db.query(Product).filter(Product.id == line.product_id).first() if line.product_id else None
    return {
        "id": _u(line.id), "sheet": line.sheet, "row_no": line.row_no, "line_no": line.line_no,
        "supplier_code_raw": line.supplier_code_raw, "supplier_code": line.supplier_code,
        "code_note": line.code_note, "configuration": line.configuration,
        "flags": list(line.flags or []),
        "match_outcome": line.match_outcome, "match_rung": line.match_rung,
        "product": _serialize_product(product),
        "current_unit_cost": float(line.current_unit_cost) if line.current_unit_cost is not None else None,
        "current_currency": line.current_currency,
        "new_unit_cost": float(line.new_unit_cost) if line.new_unit_cost is not None else None,
        "change_pct": _change_pct(line.current_unit_cost, line.new_unit_cost),
        "line_state": line.line_state, "skipped": line.skipped, "skip_reason": line.skip_reason,
        "new_link_lead_time_days": line.new_link_lead_time_days,
        "decision": line.decision, "decision_reason": line.decision_reason,
        "decided_by_name": _display_name(db, line.decided_by_user_id),
        "stale": (
            {"live_unit_cost": float(line.stale_live_unit_cost), "live_currency": line.stale_live_currency}
            if line.stale_live_unit_cost is not None else None
        ),
    }


def get_lines(db: Session, set_id: str) -> dict:
    from app.models.cost_price import CostPriceChangeLine

    _get_set_or_404(db, set_id)
    lines = (
        db.query(CostPriceChangeLine)
        .filter(CostPriceChangeLine.change_set_id == set_id)
        .order_by(CostPriceChangeLine.sheet, CostPriceChangeLine.row_no)
        .all()
    )
    return {"data": [_serialize_line(db, ln) for ln in lines]}


def _recompute_duplicates(db: Session, set_id: str) -> None:
    from app.models.cost_price import CostPriceChangeLine

    lines = db.query(CostPriceChangeLine).filter(CostPriceChangeLine.change_set_id == set_id).all()
    groups: dict[str, list] = {}
    for ln in lines:
        if ln.product_id and not ln.skipped:
            groups.setdefault(str(ln.product_id), []).append(ln)
    dup_ids = {pid for pid, group in groups.items() if len(group) > 1}
    for ln in lines:
        flags = set(ln.flags or [])
        if ln.product_id and not ln.skipped and str(ln.product_id) in dup_ids:
            flags.add("duplicate_code")
        else:
            flags.discard("duplicate_code")
        ln.flags = sorted(flags)


def _recompute_line_price(db: Session, line, cs) -> None:
    from app.models.procurement import ProductSupplier

    link = (
        db.query(ProductSupplier)
        .filter(ProductSupplier.supplier_id == cs.supplier_id, ProductSupplier.product_id == line.product_id)
        .first()
    )
    if line.new_unit_cost is None:
        line.line_state = "needs_attention"
        line.current_unit_cost = link.unit_cost if link else None
        line.current_currency = link.currency if link else None
        return
    has_dates = bool(cs.start_date or cs.end_date)
    state, cur_cost, cur_ccy = _line_state_for(link, cs.currency, line.new_unit_cost, has_dates)
    line.line_state = state
    line.current_unit_cost = cur_cost
    line.current_currency = cur_ccy


def _find_company_scoped_product(db: Session, product_id: str):
    """Resolve `product_id` for a manual map, or `None` when it is not a real
    product in the CALLER's own company (B1, security review). `Product` is
    `CompanyScopedMixin`, so the query itself is already filtered to the
    session's resolved scope - a foreign-company id simply is not found."""
    from app.models.product import Product

    return db.query(Product).filter(Product.id == product_id).first()


def patch_line(
    db: Session, set_id: str, line_id: str, body: dict, current_user: dict,
    *, request: Optional[Request] = None,
) -> dict:
    from app.models.cost_price import CostPriceChangeLine

    cs = _get_set_or_404(db, set_id, for_update=True)
    _require_single_company_scope(db, cs)
    if cs.status != "draft":
        raise AppException(409, "Only a Draft set can be edited.", detail={"code": "not_draft"}, code="not_draft")
    line = (
        db.query(CostPriceChangeLine)
        .filter(CostPriceChangeLine.id == line_id, CostPriceChangeLine.change_set_id == set_id)
        .first()
    )
    if line is None:
        raise AppException(404, "Line not found.", code="NOT_FOUND")

    actor_id = _actor_id(request, current_user)
    mapped_now = False

    if "product_id" in body:
        product_id = body["product_id"]
        if product_id:
            product_id = _require_uuid(product_id, field="product", code="invalid_product")
            product = _find_company_scoped_product(db, product_id)
            if product is None:
                raise AppException(
                    422, "That product was not found.",
                    detail={"code": "invalid_product"}, code="invalid_product",
                )
            line.product_id = product.id
            line.match_outcome = "manual"
            line.match_rung = None
            _recompute_line_price(db, line, cs)
        else:
            line.product_id = None
            line.match_outcome = "unmatched"
            line.match_rung = None
            line.current_unit_cost = None
            line.current_currency = None
            line.line_state = "needs_attention"
        mapped_now = True
    if "skipped" in body:
        line.skipped = bool(body["skipped"])
        mapped_now = True
    if "skip_reason" in body:
        line.skip_reason = body["skip_reason"]
        mapped_now = True
    if "new_link_lead_time_days" in body:
        lead_time = body["new_link_lead_time_days"]
        if lead_time is not None and lead_time < 0:
            raise AppException(
                422, "Lead time cannot be negative.",
                detail={"code": "negative_lead_time"}, code="negative_lead_time",
            )
        line.new_link_lead_time_days = lead_time
        mapped_now = True

    # S5 (security review): whoever decided which product a code maps to (or
    # skipped/adjusted the line) is not neutral either - `mapped_by_user_id`
    # joins the same-person set `_assert_not_same_person` checks at decide/apply.
    if mapped_now and actor_id:
        line.mapped_by_user_id = actor_id

    db.flush()
    _recompute_duplicates(db, set_id)
    db.commit()

    line = db.query(CostPriceChangeLine).filter(CostPriceChangeLine.id == line_id).first()
    return {
        "line": _serialize_line(db, line),
        "counts": _counts(db, set_id),
        "actions": get_detail(db, set_id, current_user)["actions"],
    }


def _notify_users(db: Session, user_ids: Iterable[str], cs, *, event_type: str, title: str, body: str) -> None:
    from app.services.notification_service import NotificationService

    svc = NotificationService(db)
    for uid in user_ids:
        svc.create(
            uid, "cost_price_change_set", title, body=body,
            source_entity_type="cost_price_change_set", source_entity_id=_u(cs.id),
            event_type=event_type,
        )


def _verifier_user_ids(db: Session, company_id: Optional[str] = None) -> list[str]:
    from app.models.user import User, UserPermission, UserRoleAssignment, UserRolePermission

    rows = (
        db.query(User.id)
        .join(UserRoleAssignment, UserRoleAssignment.user_id == User.id)
        .join(UserRolePermission, UserRolePermission.role_id == UserRoleAssignment.role_id)
        .join(UserPermission, UserPermission.id == UserRolePermission.permission_id)
        .filter(UserPermission.slug == VERIFY_PERM)
        .distinct()
        .all()
    )
    ids = [r[0] for r in rows]
    if not company_id:
        return ids
    # Nits (security review): a verify-holder with no `user_companies` grant for
    # the set's own company must not be notified about it, superadmin/admin
    # (whose grant set is every company) included on the right side of this.
    from app.services.company_scope_resolver import resolve_user_grant_ids

    return [uid for uid in ids if str(company_id) in resolve_user_grant_ids(db, uid)]


def submit(db: Session, set_id: str, current_user: dict, *, request: Optional[Request] = None) -> dict:
    from app.services.audit_service import log_audit

    cs = _get_set_or_404(db, set_id, for_update=True)
    _require_single_company_scope(db, cs)
    # S1 (security review): a supplier submission always waits for a Sorento
    # verifier, whatever the global setting - only a `staff_upload` draft is ever
    # gated on it (plan section 7.2).
    if cs.channel == "staff_upload" and not _verification_enabled(db):
        raise AppException(409, "Verification is off; apply this set directly.", detail={"code": "verification_off"}, code="verification_off")
    if cs.status != "draft":
        raise AppException(409, "Only a Draft set can be submitted for verification.", detail={"code": "wrong_status"}, code="wrong_status")
    if _unresolved_count(db, set_id):
        raise AppException(422, "Some lines still need attention before this can be submitted.", detail={"code": "unresolved_lines"}, code="unresolved_lines")

    actor_id = _actor_id(request, current_user)
    cs.status = "pending_verification"
    cs.submitted_by_user_id = actor_id
    cs.submitted_at = datetime.utcnow()
    log_audit(db, "cost_price_change_sets", _u(cs.id), "COST_SET_SUBMIT", user_id=actor_id)
    db.commit()

    _notify_users(
        db, _verifier_user_ids(db, cs.company_id), cs, event_type="submitted",
        title=f"{cs.code} needs verification",
        body=f"A supplier price change ({cs.code}) is waiting for you to verify.",
    )
    return get_detail(db, set_id, current_user)


def decide(
    db: Session, set_id: str, line_id: str, body: dict, current_user: dict,
    *, request: Optional[Request] = None,
) -> dict:
    from app.models.cost_price import CostPriceChangeLine

    cs = _get_set_or_404(db, set_id, for_update=True)
    if cs.status != "pending_verification":
        raise AppException(409, "Only a Pending set can be decided.", detail={"code": "wrong_status"}, code="wrong_status")
    if not _user_has_permission(db, (current_user or {}).get("id"), VERIFY_PERM):
        raise AppException(403, "Permission required to decide.", code="FORBIDDEN")
    _assert_not_same_person(db, cs, current_user, request=request)
    line = (
        db.query(CostPriceChangeLine)
        .filter(CostPriceChangeLine.id == line_id, CostPriceChangeLine.change_set_id == set_id)
        .first()
    )
    if line is None:
        raise AppException(404, "Line not found.", code="NOT_FOUND")

    decision = body.get("decision")
    if decision not in (None, "accepted", "rejected"):
        raise AppException(422, "Invalid decision.", code="VALIDATION_ERROR")
    reason = body.get("reason")
    if reason and len(reason) > 500:
        raise AppException(422, "Reason is too long.", detail={"code": "reason_too_long"}, code="reason_too_long")

    line.decision = decision
    line.decision_reason = reason
    line.decided_by_user_id = _actor_id(request, current_user)
    line.decided_at = datetime.utcnow()
    db.commit()

    return {
        "line": _serialize_line(db, line),
        "counts": _counts(db, set_id),
        "actions": get_detail(db, set_id, current_user)["actions"],
    }


def decide_all(
    db: Session, set_id: str, decision: str, current_user: dict,
    *, request: Optional[Request] = None,
) -> dict:
    from app.models.cost_price import CostPriceChangeLine

    cs = _get_set_or_404(db, set_id, for_update=True)
    if cs.status != "pending_verification":
        raise AppException(409, "Only a Pending set can be decided.", detail={"code": "wrong_status"}, code="wrong_status")
    if not _user_has_permission(db, (current_user or {}).get("id"), VERIFY_PERM):
        raise AppException(403, "Permission required to decide.", code="FORBIDDEN")
    _assert_not_same_person(db, cs, current_user, request=request)
    if decision not in ("accepted", "rejected"):
        raise AppException(422, "Invalid decision.", code="VALIDATION_ERROR")

    actor_id = _actor_id(request, current_user)
    now = datetime.utcnow()
    lines = (
        db.query(CostPriceChangeLine)
        .filter(
            CostPriceChangeLine.change_set_id == set_id,
            CostPriceChangeLine.skipped.is_(False),
            CostPriceChangeLine.line_state.in_(("changed", "new_link")),
        )
        .all()
    )
    for ln in lines:
        ln.decision = decision
        ln.decided_by_user_id = actor_id
        ln.decided_at = now
    db.commit()
    return get_detail(db, set_id, current_user)


def return_set(
    db: Session, set_id: str, reason: str, current_user: dict,
    *, request: Optional[Request] = None,
) -> dict:
    from app.models.cost_price import CostPriceChangeLine
    from app.services.audit_service import log_audit

    cs = _get_set_or_404(db, set_id, for_update=True)
    if cs.status != "pending_verification":
        raise AppException(409, "Only a Pending set can be returned.", detail={"code": "wrong_status"}, code="wrong_status")
    if not _user_has_permission(db, (current_user or {}).get("id"), VERIFY_PERM):
        raise AppException(403, "Permission required to return this set.", code="FORBIDDEN")
    _assert_not_same_person(db, cs, current_user, request=request)
    if not (reason or "").strip():
        raise AppException(422, "A reason is required to return this set.", detail={"code": "reason_required"}, code="reason_required")
    if len(reason) > 500:
        raise AppException(422, "Reason is too long.", detail={"code": "reason_too_long"}, code="reason_too_long")

    actor_id = _actor_id(request, current_user)
    cs.status = "draft"
    cs.returned_reason = reason
    cs.returned_by_user_id = actor_id
    cs.returned_at = datetime.utcnow()
    db.query(CostPriceChangeLine).filter(CostPriceChangeLine.change_set_id == set_id).update(
        {"decision": None, "decision_reason": None, "decided_by_user_id": None, "decided_at": None},
        synchronize_session=False,
    )
    log_audit(db, "cost_price_change_sets", _u(cs.id), "COST_SET_RETURN", user_id=actor_id)
    db.commit()

    if cs.submitted_by_user_id:
        _notify_users(
            db, [cs.submitted_by_user_id], cs, event_type="returned",
            title=f"{cs.code} was returned", body=f"{cs.code} was returned: {reason}",
        )
    return get_detail(db, set_id, current_user)


def _default_lead_time(db: Session, supplier_id: str) -> Optional[int]:
    from sqlalchemy import func

    from app.models.procurement import ProductSupplier

    rows = (
        db.query(ProductSupplier.standard_lead_time_days, func.count())
        .filter(ProductSupplier.supplier_id == supplier_id)
        .group_by(ProductSupplier.standard_lead_time_days)
        .order_by(func.count().desc())
        .all()
    )
    return rows[0][0] if rows else None


def apply(db: Session, set_id: str, current_user: dict, *, request: Optional[Request] = None) -> dict:
    from app.models.cost_price import CostPriceChangeLine, ProductSupplierCost
    from app.models.procurement import ProductSupplier
    from app.models.scm import SupplierProductCodeAlias
    from app.services.audit_service import log_audit
    from app.services.procurement.supplier_cost_service import refresh_link

    cs = _get_set_or_404(db, set_id, for_update=True)
    _require_single_company_scope(db, cs)

    if cs.status == "applied":
        raise AppException(409, "This set is already applied.", detail={"code": "already_applied"}, code="already_applied")
    if cs.status == "draft":
        # S1 (security review): a non-staff-channel draft (a RETURNED supplier
        # submission) always needs re-submitting - it never applies straight from
        # draft, whatever the global setting says.
        if cs.channel != "staff_upload":
            raise AppException(409, "Submit for verification first.", detail={"code": "submit_first"}, code="submit_first")
        if _verification_enabled(db):
            raise AppException(409, "Submit for verification first.", detail={"code": "submit_first"}, code="submit_first")
        if not _user_has_permission(db, (current_user or {}).get("id"), UPLOAD_PERM):
            raise AppException(403, "Permission required to apply.", code="FORBIDDEN")
        verified = False
    elif cs.status == "pending_verification":
        # A Pending set - staff or supplier channel alike - is a `verify` action
        # regardless of the setting (plan 7.2): holding `upload` is not enough.
        if not _user_has_permission(db, (current_user or {}).get("id"), VERIFY_PERM):
            raise AppException(403, "Permission required to apply.", code="FORBIDDEN")
        _assert_not_same_person(db, cs, current_user, request=request)
        verified = True
    else:
        raise AppException(409, "Unexpected status.", detail={"code": "wrong_status"}, code="wrong_status")

    if _unresolved_count(db, set_id):
        raise AppException(422, "Some lines still need attention.", detail={"code": "unresolved_lines"}, code="unresolved_lines")
    if verified and _undecided_count(db, set_id):
        raise AppException(422, "Some lines are still undecided.", detail={"code": "undecided_lines"}, code="undecided_lines")

    lines = (
        db.query(CostPriceChangeLine)
        .filter(
            CostPriceChangeLine.change_set_id == set_id,
            CostPriceChangeLine.skipped.is_(False),
            CostPriceChangeLine.line_state.in_(("changed", "new_link")),
        )
        .all()
    )
    if verified:
        lines = [ln for ln in lines if ln.decision == "accepted"]

    # B1 (security review): re-check every line's product before writing anything -
    # a line bound to a foreign-company product some OTHER way (a future channel, a
    # data-repair script) must refuse here independently of `patch_line`'s own gate.
    for ln in lines:
        if ln.product_id and _find_company_scoped_product(db, ln.product_id) is None:
            raise AppException(
                422, "A line is bound to a product that is not in this company.",
                detail={"code": "invalid_product"}, code="invalid_product",
            )

    links_by_line: dict[str, Optional["ProductSupplier"]] = {}
    stale: list[tuple] = []
    lead_time_missing = False
    for ln in lines:
        link = (
            db.query(ProductSupplier)
            .filter(ProductSupplier.supplier_id == cs.supplier_id, ProductSupplier.product_id == ln.product_id)
            .with_for_update()
            .first()
        )
        links_by_line[str(ln.id)] = link
        if link is None:
            if not ln.new_link_lead_time_days and _default_lead_time(db, cs.supplier_id) is None:
                lead_time_missing = True
        else:
            live_cost, live_currency = link.unit_cost, link.currency
            recorded_cost, recorded_currency = ln.current_unit_cost, ln.current_currency
            if live_cost != recorded_cost or (live_currency or None) != (recorded_currency or None):
                stale.append((ln, live_cost, live_currency, recorded_cost, recorded_currency))

    if lead_time_missing:
        raise AppException(
            422, "Set a lead time for the new supplier link before applying.",
            detail={"code": "lead_time_required"}, code="lead_time_required",
        )

    if stale:
        for ln, live_cost, live_currency, _rc, _rcc in stale:
            ln.stale_live_unit_cost = live_cost
            ln.stale_live_currency = live_currency
        db.commit()
        raise AppException(
            409, "Some prices changed after this set was parsed. Refresh and try again.",
            detail={
                "code": "stale_lines",
                "lines": [
                    {
                        "line_id": _u(ln.id), "supplier_code": ln.supplier_code,
                        "recorded_unit_cost": float(rc) if rc is not None else None,
                        "recorded_currency": rcc,
                        "live_unit_cost": float(lc) if lc is not None else None,
                        "live_currency": lcy,
                    }
                    for ln, lc, lcy, rc, rcc in stale
                ],
            },
            code="stale_lines",
        )

    actor_id = _actor_id(request, current_user)
    changes_summary = []
    for ln in lines:
        link = links_by_line.get(str(ln.id))
        if link is None:
            lead_time = ln.new_link_lead_time_days or _default_lead_time(db, cs.supplier_id)
            link = ProductSupplier(
                product_id=ln.product_id, supplier_id=cs.supplier_id,
                standard_lead_time_days=lead_time,
            )
            db.add(link)
            db.flush()

        db.add(ProductSupplierCost(
            product_supplier_id=link.id, unit_cost=ln.new_unit_cost, currency=cs.currency,
            start_date=cs.start_date, end_date=cs.end_date,
            source_change_line_id=ln.id, created_by_user_id=actor_id,
        ))
        db.flush()
        refresh_link(db, link)

        if ln.match_outcome == "manual":
            # Nits (security review): UPSERT the manual alias - a line remapped by
            # hand through an EXISTING alias must update that same row, not insert
            # a second one and hit `uq_scm_supplier_code_alias_identity`.
            from sqlalchemy import func

            existing_alias = (
                db.query(SupplierProductCodeAlias)
                .filter(
                    SupplierProductCodeAlias.supplier_id == cs.supplier_id,
                    func.upper(SupplierProductCodeAlias.supplier_code) == ln.supplier_code.upper(),
                )
                .first()
            )
            if existing_alias is not None:
                existing_alias.product_id = ln.product_id
                existing_alias.source = "manual"
                existing_alias.matched_by = "cost_price_set"
            else:
                db.add(SupplierProductCodeAlias(
                    supplier_id=cs.supplier_id, supplier_code=ln.supplier_code,
                    product_id=ln.product_id, source="manual", matched_by="cost_price_set",
                ))
        changes_summary.append({
            "supplier_code": ln.supplier_code,
            "old_unit_cost": float(ln.current_unit_cost) if ln.current_unit_cost is not None else None,
            "new_unit_cost": float(ln.new_unit_cost) if ln.new_unit_cost is not None else None,
            "currency": cs.currency,
        })

    # The ladder-bound codes are remembered NOW, exactly as the PI apply does (plan section 6).
    ladder_codes = {ln.supplier_code for ln in lines if ln.match_outcome == "ladder"}
    if ladder_codes:
        matcher.resolve(db, cs.supplier_id, ladder_codes, remember=True, actor=actor_id)

    cs.status = "applied"
    cs.applied_by_user_id = actor_id
    cs.applied_at = datetime.utcnow()
    cs.verified = verified
    db.flush()

    log_audit(
        db, "cost_price_change_sets", _u(cs.id), "COST_SET_APPLY",
        new_values={"verified": verified, "changes": changes_summary},
        user_id=actor_id,
    )
    db.commit()
    return get_detail(db, set_id, current_user)


def discard(db: Session, set_id: str) -> None:
    cs = _get_set_or_404(db, set_id)
    if cs.status != "draft":
        raise AppException(409, "Only a Draft set can be discarded.", detail={"code": "not_draft"}, code="not_draft")
    db.delete(cs)
    db.commit()


def get_source_file(db: Session, set_id: str) -> tuple[bytes, str]:
    cs = _get_set_or_404(db, set_id)
    # S4 (security review): `source_file_bytes` is `deferred` - undefer it only
    # here, the one place that actually needs the retained spreadsheet's bytes.
    db.refresh(cs, attribute_names=["source_file_bytes"])
    if not cs.source_file_bytes:
        raise AppException(404, "No file is retained for this set.", code="NOT_FOUND")
    return bytes(cs.source_file_bytes), cs.file_name or "price-list.xlsx"


def get_history(db: Session, set_id: str) -> dict:
    from app.models.audit import AuditLog

    _get_set_or_404(db, set_id)
    rows = (
        db.query(AuditLog)
        .filter(AuditLog.entity_type == "cost_price_change_sets", AuditLog.entity_id == set_id)
        .order_by(AuditLog.changed_at.desc())
        .all()
    )
    return {
        "data": [
            {
                "action": row.action,
                "actor_name": _display_name(db, row.user_id),
                "at": row.changed_at.isoformat() if row.changed_at else None,
                "summary": row.description,
            }
            for row in rows
        ]
    }
