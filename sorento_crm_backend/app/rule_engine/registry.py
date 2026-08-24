"""Fact registry (sprint-2/02 D7) - whitelist + schema inference, NEVER
auto-expose a model's schema (would leak credentials).

A fact source (``promotion``) is a named bundle of ``FactDef`` rows.
Declaration is opt-in but cheap: ``infer_facts(Model, ["start_date",
"end_date"])`` derives type/label/resolver from the SQLAlchemy column;
computed/enum/list facts use an explicit ``FactDef`` with a resolver callable.
The core source registers exactly once (``ensure_core``).
"""
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union

from sqlalchemy import Boolean, Date, DateTime, Float, Integer, Numeric, func
from sqlalchemy.orm import Session

FactType = str  # 'string' | 'number' | 'boolean' | 'date' | 'enum' | 'list'

# Static option list, or a callable(db, user) for tenant-scoped options
# (e.g. access-level catalog). Only the /rule-facts endpoint materializes callables.
OptionsProvider = Union[
    List[Dict[str, str]], Callable[[Session, Any], List[Dict[str, str]]], None
]


from app.lazy_registry import lazy_once as _lazy_once  # noqa: E402  (single shared helper)


@dataclass(frozen=True)
class FactDef:
    """One whitelisted fact. ``resolver(obj, db)`` produces the runtime value
    from the source object (None-safe - missing/None fails closed, D5)."""

    key: str
    label: str
    type: FactType
    resolver: Callable[[Any, Session], Any]
    options: OptionsProvider = None


@dataclass(frozen=True)
class FactSource:
    name: str
    label: str
    facts: Tuple[FactDef, ...]


_REGISTRY: Dict[str, FactSource] = {}


def register_fact_source(name: str, label: str, facts: Sequence[FactDef]) -> None:
    """Idempotent - modules re-register on every bootstrap."""
    _REGISTRY[name] = FactSource(name=name, label=label, facts=tuple(facts))


def get_facts(sources: Sequence[str]) -> List[Tuple[str, str, FactDef]]:
    """(source_name, source_label, FactDef) rows for the requested sources,
    in request order. Unknown sources yield nothing (module uninstalled)."""
    ensure_core()
    rows: List[Tuple[str, str, FactDef]] = []
    for name in sources:
        source = _REGISTRY.get(name)
        if source is None:
            continue
        rows.extend((source.name, source.label, fact) for fact in source.facts)
    return rows


def fact_map(sources: Sequence[str]) -> Dict[str, FactDef]:
    """key → FactDef for validation/prose over the given sources."""
    return {fact.key: fact for _, _, fact in get_facts(sources)}


def resolve_facts(
    db: Session,
    objects: Dict[str, Any],
    only_keys: Optional[set] = None,
) -> Dict[str, Any]:
    """Flat fact dict for the evaluator: ``{source_name: source_object}`` →
    ``{fact_key: value}``. A None object or a raising resolver yields None
    (fail-closed downstream, D5) - stale rules never explode at runtime.

    ``only_keys`` (code-review perf fix): resolve just these fact keys  - 
    computed facts (e.g. a COUNT query) aren't paid for rules that never read
    them. None = resolve everything."""
    ensure_core()
    values: Dict[str, Any] = {}
    for name, obj in objects.items():
        source = _REGISTRY.get(name)
        if source is None:
            continue
        for fact in source.facts:
            if only_keys is not None and fact.key not in only_keys:
                continue
            if obj is None:
                values[fact.key] = None
                continue
            try:
                values[fact.key] = fact.resolver(obj, db)
            except Exception:  # noqa: BLE001 - D5: no runtime errors from stale rules
                values[fact.key] = None
    return values


# ---- inference helper ----


def _camel(snake: str) -> str:
    head, *rest = snake.split("_")
    return head + "".join(part.capitalize() for part in rest)


def _title(snake: str) -> str:
    return " ".join(part.capitalize() for part in snake.split("_"))


def _column_fact_type(column) -> FactType:
    # TypeDecorators (UTCDateTime) hide the real type behind `.impl` - unwrap
    # before matching.
    col_type = getattr(column.type, "impl", column.type)
    if isinstance(col_type, Boolean):
        return "boolean"
    if isinstance(col_type, (DateTime, Date)):
        return "date"
    if isinstance(col_type, (Integer, Numeric, Float)):
        return "number"
    return "string"


def infer_facts(
    model: Any,
    attrs: Sequence[str],
    *,
    prefix: str,
    overrides: Optional[Dict[str, Dict[str, Any]]] = None,
) -> List[FactDef]:
    """Whitelisted inference (D7): type/label from the SQLAlchemy column,
    resolver = attribute read. ``overrides[attr]`` patches label/type/options."""
    overrides = overrides or {}
    defs: List[FactDef] = []
    for attr in attrs:
        column = model.__table__.columns.get(attr)
        if column is None:
            raise ValueError(f"{model.__name__} has no column '{attr}'.")
        patch = overrides.get(attr, {})

        def _resolver(obj: Any, db: Session, _attr: str = attr) -> Any:
            return getattr(obj, _attr)

        col_type = patch.get("type", _column_fact_type(column))
        defs.append(
            FactDef(
                key=f"{prefix}.{_camel(attr)}",
                label=patch.get("label", _title(attr)),
                type=col_type,
                resolver=_resolver,
                options=patch.get("options"),
            )
        )
        # Relative-to-now day-count facts (sprint-4/03 Slice 6): every date field
        # also exposes "Days since"/"Days until <field>" as NUMBER facts computed
        # against the clock - so time windows are authored with the existing
        # >/≥/</≤ operators.
        if col_type == "date":
            label = patch.get("label", _title(attr))
            defs.extend(_day_count_facts(f"{prefix}.{_camel(attr)}", attr, label))
    return defs


def _day_count_facts(base_key: str, attr: str, label: str) -> List[FactDef]:
    from datetime import datetime as _dt

    from app.services.sla_service import MALAYSIA_TZ

    def today():
        return _dt.now(MALAYSIA_TZ).date()

    def _field_date(obj: Any, _attr: str = attr):
        v = getattr(obj, _attr, None)
        if v is None:
            return None
        return v.date() if isinstance(v, _dt) else v  # UTCDateTime → date

    def _since(obj: Any, db: Session) -> Optional[int]:
        d = _field_date(obj)
        return None if d is None else (today() - d).days

    def _until(obj: Any, db: Session) -> Optional[int]:
        d = _field_date(obj)
        return None if d is None else (d - today()).days

    return [
        FactDef(key=f"{base_key}.daysSince", label=f"Days since {label}",
                type="number", resolver=_since),
        FactDef(key=f"{base_key}.daysUntil", label=f"Days until {label}",
                type="number", resolver=_until),
    ]


# ---- core sources ("module zero") ----


def _register_core() -> None:
    from app.models.marketing import Promotion

    def _access_levels(promo: Promotion, db: Session) -> List[str]:
        levels = getattr(promo, "access_levels", None)
        return list(levels) if isinstance(levels, list) else []

    def _access_level_options(db: Session, current_user: Any) -> List[Dict[str, str]]:
        from app.models.access import ContactAccessType

        rows = (
            db.query(ContactAccessType.code, ContactAccessType.name)
            .filter(ContactAccessType.is_active.is_(True))
            .order_by(ContactAccessType.sort_order, ContactAccessType.code)
            .all()
        )
        return [{"value": code, "label": name} for code, name in rows]

    register_fact_source(
        "promotion",
        "Promotion",
        [
            FactDef(
                key="promotion.name",
                label="Promotion name",
                type="string",
                resolver=lambda obj, db: getattr(obj, "description", None),
            ),
            FactDef(
                key="promotion.accessLevels",
                label="Access levels",
                type="list",
                resolver=_access_levels,
                options=_access_level_options,
            ),
            FactDef(
                key="promotion.isActive",
                label="Active",
                type="boolean",
                resolver=lambda obj, db: bool(getattr(obj, "is_active", False)),
            ),
            *infer_facts(
                Promotion,
                ["start_date", "end_date"],
                prefix="promotion",
                overrides={
                    "start_date": {"label": "Start date"},
                    "end_date": {"label": "End date"},
                },
            ),
        ],
    )

    _register_certificate()


def _register_certificate() -> None:
    """Facts for the ``days_before_certificate_expiry`` trigger (REM-6).

    Scoping an expiry automation to one scheme, one certifying body or one
    company is authored here. Remember the rule-engine trap: an EMPTY tree
    matches every certificate, it does not match none.

    The three computed facts (validity window, coverage count, review flag) each
    run their own query, so they are declared as explicit ``FactDef`` rows rather
    than inferred - and ``resolve_facts(only_keys=...)`` means a rule that never
    reads them never pays for them.
    """
    from app.models.certificate import (
        Certificate,
        CertificateProduct,
        CertificateRevision,
    )
    from app.models.company import Company

    def _current_revision(obj: Any, db: Session) -> Any:
        revision_id = getattr(obj, "current_revision_id", None)
        if revision_id:
            return (
                db.query(CertificateRevision)
                .filter(CertificateRevision.id == revision_id)
                .first()
            )
        return (
            db.query(CertificateRevision)
            .filter(
                CertificateRevision.certificate_id == getattr(obj, "id", None),
                CertificateRevision.is_current.is_(True),
            )
            .first()
        )

    def _days_until_expiry(obj: Any, db: Session) -> Optional[int]:
        from app.services.certificate_service import today_malaysia

        revision = _current_revision(obj, db)
        valid_until = getattr(revision, "valid_until", None) if revision else None
        return None if valid_until is None else (valid_until - today_malaysia()).days

    def _needs_review(obj: Any, db: Session) -> bool:
        revision = _current_revision(obj, db)
        return bool(getattr(revision, "needs_review", False)) if revision else False

    def _covered_product_count(obj: Any, db: Session) -> int:
        return (
            db.query(func.count(CertificateProduct.id))
            .filter(CertificateProduct.certificate_id == getattr(obj, "id", None))
            .scalar()
            or 0
        )

    def _company_name(obj: Any, db: Session) -> Optional[str]:
        company_id = getattr(obj, "company_id", None)
        if not company_id:
            return None
        row = db.query(Company.name).filter(Company.id == company_id).first()
        return row[0] if row else None

    register_fact_source(
        "certificate",
        "Certificate",
        [
            *infer_facts(
                Certificate,
                ["scheme", "certificate_number", "certifying_body", "issuer", "title"],
                prefix="certificate",
                overrides={
                    "scheme": {"label": "Scheme"},
                    "certificate_number": {"label": "Certificate number"},
                    "certifying_body": {"label": "Certifying body"},
                    "issuer": {"label": "Issuer"},
                    "title": {"label": "Title"},
                },
            ),
            FactDef(
                key="certificate.status",
                label="Status",
                type="enum",
                resolver=lambda obj, db: getattr(obj, "status", None),
                options=[
                    {"value": "active", "label": "Active"},
                    {"value": "archived", "label": "Archived"},
                ],
            ),
            FactDef(
                key="certificate.companyName",
                label="Company",
                type="string",
                resolver=_company_name,
            ),
            FactDef(
                key="certificate.daysUntilExpiry",
                label="Days until expiry",
                type="number",
                resolver=_days_until_expiry,
            ),
            FactDef(
                key="certificate.coveredProductCount",
                label="Covered products",
                type="number",
                resolver=_covered_product_count,
            ),
            FactDef(
                key="certificate.needsReview",
                label="Needs review",
                type="boolean",
                resolver=_needs_review,
            ),
        ],
    )


# Call before any registry read - core registers exactly once.
ensure_core = _lazy_once(_register_core)
