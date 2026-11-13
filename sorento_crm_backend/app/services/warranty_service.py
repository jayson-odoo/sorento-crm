"""After-sales P2: the warranty engine. Answers "is this part still covered?" from the policy.

Verdicts are computed at read time and never stored. The policy used is the one in force on the
purchase date, for the line's company. Nothing here commits.

* covered / expired: the part's term, judged on today's Malaysian date (the expiry day is covered).
* defect_not_covered: the term lists defect types and the stated defect is not one of them.
* no_term: the policy in force has no term for the kind.
* unknown: a needed input is missing (kind, purchase date, defect for a restricted term) or no
  policy was in force. Never reported as expired or not covered.
"""
from __future__ import annotations

import calendar
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy.orm import Session

from app.models.lookup import LookupOption
from app.models.warranty import WarrantyKindRule, WarrantyPolicy, WarrantyProductKind, WarrantyTerm

logger = logging.getLogger(__name__)

MALAYSIA_TZ = timezone(timedelta(hours=8))

VERDICT_COVERED = "covered"
VERDICT_EXPIRED = "expired"
VERDICT_DEFECT_NOT_COVERED = "defect_not_covered"
VERDICT_NO_TERM = "no_term"
VERDICT_UNKNOWN = "unknown"

KIND_RULE_MATCH_TYPES = ("series", "model_list", "category", "code_prefix")
# Narrowest first: at equal priority the narrower match type wins.
KIND_RULE_SPECIFICITY = ("model_list", "code_prefix", "series", "category")
_SPECIFICITY_RANK = {t: i for i, t in enumerate(KIND_RULE_SPECIFICITY)}


@dataclass(frozen=True)
class WarrantyVerdict:
    verdict: str
    part_name: Optional[str] = None
    expiry: Optional[date] = None
    is_lifetime: bool = False
    installation_included: bool = False
    kind_id: Optional[str] = None
    policy_id: Optional[str] = None
    policy_version: Optional[str] = None
    term_id: Optional[str] = None
    reason: str = ""


def warranty_today() -> date:
    """The Malaysian calendar date. Always read through the module so a test can freeze it."""
    return datetime.now(MALAYSIA_TZ).date()


def add_months(start: date, months: int) -> date:
    """`start` plus whole months, clamped to the month's last day (31 Jan + 1 month = 28/29 Feb)."""
    total = (start.month - 1) + months
    year = start.year + total // 12
    month = total % 12 + 1
    return date(year, month, min(start.day, calendar.monthrange(year, month)[1]))


def dmy(value: date) -> str:
    return value.strftime("%d/%m/%Y")


# ------------------------------------------------------------------ kind suggestion


@dataclass(frozen=True)
class RuleMatch:
    kind: WarrantyProductKind
    rule: WarrantyKindRule
    priority: int
    specificity: int
    matched_length: int

    @property
    def sort_key(self):
        # Higher priority, then narrower type, then longer matched value, then kind code.
        return (-self.priority, self.specificity, -self.matched_length, self.kind.code or "")


def _matched_length(rule: WarrantyKindRule, code: str, category: str, name: str) -> Optional[int]:
    value = (rule.match_value or "").strip()
    if not value:
        return None
    kind = (rule.match_type or "").strip().lower()
    low = value.lower()
    if kind == "category":
        return len(value) if category and low == category else None
    if kind == "code_prefix":
        return len(value) if code and code.startswith(low) else None
    if kind == "model_list":
        for token in value.split(","):
            token = token.strip()
            if token and code and token.lower() == code:
                return len(token)
        return None
    if kind == "series":
        return len(value) if name and low in name else None
    logger.warning("warranty kind rule %s has unknown match_type %r", rule.id, rule.match_type)
    return None


def rank_kind_matches(
    db: Session,
    *,
    product_code: Optional[str] = None,
    category_code: Optional[str] = None,
    product_name: Optional[str] = None,
    extra_rules: Iterable[WarrantyKindRule] = (),
) -> List[RuleMatch]:
    """Every active kind a rule reaches for this product, best first."""
    code = (product_code or "").strip().lower()
    category = (category_code or "").strip().lower()
    name = (product_name or "").strip().lower()
    if not (code or category or name):
        return []
    pairs = (
        db.query(WarrantyKindRule, WarrantyProductKind)
        .join(WarrantyProductKind, WarrantyProductKind.id == WarrantyKindRule.kind_id)
        .filter(WarrantyProductKind.is_active.isnot(False))
        .all()
    )
    extra = [r for r in (extra_rules or ()) if r is not None and r.kind_id]
    if extra:
        kinds = {
            k.id: k
            for k in db.query(WarrantyProductKind)
            .filter(WarrantyProductKind.id.in_({r.kind_id for r in extra}), WarrantyProductKind.is_active.isnot(False))
            .all()
        }
        pairs += [(r, kinds[r.kind_id]) for r in extra if r.kind_id in kinds]
    matches: List[RuleMatch] = []
    for rule, kind in pairs:
        length = _matched_length(rule, code, category, name)
        if length is None:
            continue
        matches.append(
            RuleMatch(
                kind=kind,
                rule=rule,
                priority=rule.priority or 0,
                specificity=_SPECIFICITY_RANK.get((rule.match_type or "").strip().lower(), len(_SPECIFICITY_RANK)),
                matched_length=length,
            )
        )
    matches.sort(key=lambda m: m.sort_key)
    return matches


def resolve_kind_match(db: Session, **product) -> Optional[RuleMatch]:
    matches = rank_kind_matches(db, **product)
    return matches[0] if matches else None


def resolve_kind(db: Session, **product) -> Optional[WarrantyProductKind]:
    match = resolve_kind_match(db, **product)
    return match.kind if match else None


# ------------------------------------------------------------------ verdicts


def policy_in_force(db: Session, purchase_date: date, *, company_id: str) -> Optional[WarrantyPolicy]:
    return _pick_policy(_policies(db, company_id), purchase_date)


def _policies(db: Session, company_id: str) -> List[WarrantyPolicy]:
    return (
        db.query(WarrantyPolicy)
        .filter(WarrantyPolicy.company_id == company_id)
        .order_by(WarrantyPolicy.effective_from.desc(), WarrantyPolicy.id.asc())
        .all()
    )


def _pick_policy(policies: Sequence[WarrantyPolicy], on: date) -> Optional[WarrantyPolicy]:
    """The latest-starting policy whose window holds `on` (both ends inclusive; policies are sorted)."""
    for policy in policies:
        if policy.effective_from <= on and (policy.effective_to is None or policy.effective_to >= on):
            return policy
    return None


def _term_text(months: int, purchase: date) -> str:
    if months % 12 == 0:
        years = months // 12
        return f"{years} year{'s' if years != 1 else ''} from {dmy(purchase)}"
    return f"{months} month{'s' if months != 1 else ''} from {dmy(purchase)}"


def _verdict(term: WarrantyTerm, policy: WarrantyPolicy, name: str, reason: str, expiry: Optional[date] = None) -> WarrantyVerdict:
    return WarrantyVerdict(
        verdict=name,
        part_name=term.part_name,
        expiry=expiry,
        is_lifetime=bool(term.is_lifetime),
        installation_included=bool(term.installation_included),
        kind_id=term.kind_id,
        policy_id=policy.id,
        policy_version=policy.version,
        term_id=term.id,
        reason=reason,
    )


def _judge(
    term: WarrantyTerm,
    policy: WarrantyPolicy,
    purchase: date,
    defect_id: Optional[str],
    today: date,
    labels: Dict[str, str],
) -> WarrantyVerdict:
    scope = {str(v).lower() for v in (term.covered_defect_type_ids or []) if v}
    lifetime = bool(term.is_lifetime)
    expiry = None if lifetime or term.duration_months is None else add_months(purchase, term.duration_months)
    if scope:
        if not defect_id:
            return _verdict(term, policy, VERDICT_UNKNOWN, "Defect not stated: this part covers specific defects only.", expiry)
        if str(defect_id).lower() not in scope:
            names = sorted({labels.get(s, "") for s in (str(v) for v in term.covered_defect_type_ids) if labels.get(s)})
            return _verdict(
                term, policy, VERDICT_DEFECT_NOT_COVERED,
                f"This part covers {', '.join(names) or 'specific defects'} only.", expiry,
            )
    if lifetime:
        return _verdict(term, policy, VERDICT_COVERED, "Lifetime cover")
    if expiry is None:
        return _verdict(term, policy, VERDICT_UNKNOWN, "The term has neither a duration nor lifetime cover.")
    text = _term_text(term.duration_months, purchase)
    if today <= expiry:
        return _verdict(term, policy, VERDICT_COVERED, text, expiry)
    return _verdict(term, policy, VERDICT_EXPIRED, f"{text}, ended {dmy(expiry)}", expiry)


Line = Tuple[Optional[str], Optional[date], Optional[str]]  # (kind_id, purchase_date, defect_type_id)


def resolve_lines(db: Session, lines: Sequence[Line], *, company_id: str) -> List[List[WarrantyVerdict]]:
    """Verdicts for each (kind, purchase date, defect) line. Policies, terms and defect labels are
    loaded once for the whole batch, so a page of jobs costs a fixed number of queries."""
    today = warranty_today()
    policies = _policies(db, company_id)
    kind_ids = {k for k, _, _ in lines if k}
    terms: Dict[Tuple[str, str], List[WarrantyTerm]] = {}
    if policies and kind_ids:
        for term in (
            db.query(WarrantyTerm)
            .filter(WarrantyTerm.policy_id.in_([p.id for p in policies]), WarrantyTerm.kind_id.in_(kind_ids))
            .all()
        ):
            terms.setdefault((term.policy_id, term.kind_id), []).append(term)
    defect_ids = {str(d) for ts in terms.values() for t in ts for d in (t.covered_defect_type_ids or [])}
    labels = (
        {o.id: o.label for o in db.query(LookupOption).filter(LookupOption.id.in_(defect_ids)).all()}
        if defect_ids
        else {}
    )

    def part_order(t: WarrantyTerm):
        return ((t.part_name or "").lower(), t.part_name or "", t.id)

    out: List[List[WarrantyVerdict]] = []
    for kind_id, purchase, defect_id in lines:
        if not kind_id:
            out.append([WarrantyVerdict(VERDICT_UNKNOWN, reason="Kind not set")])
            continue
        if purchase is None:
            policy = _pick_policy(policies, today)
            found = sorted(terms.get((policy.id, kind_id), []), key=part_order) if policy else []
            if not found:
                out.append([WarrantyVerdict(VERDICT_UNKNOWN, kind_id=kind_id, reason="Purchase date not entered")])
            else:
                out.append([_verdict(t, policy, VERDICT_UNKNOWN, "Purchase date not entered") for t in found])
            continue
        policy = _pick_policy(policies, purchase)
        if policy is None:
            out.append(
                [WarrantyVerdict(VERDICT_UNKNOWN, kind_id=kind_id, reason=f"No policy in force on {dmy(purchase)}")]
            )
            continue
        found = sorted(terms.get((policy.id, kind_id), []), key=part_order)
        if not found:
            out.append(
                [
                    WarrantyVerdict(
                        VERDICT_NO_TERM,
                        kind_id=kind_id,
                        policy_id=policy.id,
                        policy_version=policy.version,
                        reason=f"Policy {policy.version} has no term for this kind",
                    )
                ]
            )
            continue
        out.append([_judge(t, policy, purchase, defect_id, today, labels) for t in found])
    return out


def resolve(
    db: Session,
    *,
    kind_id: Optional[str],
    purchase_date: Optional[date],
    defect_type_id: Optional[str] = None,
    company_id: str,
) -> List[WarrantyVerdict]:
    return resolve_lines(db, [(kind_id, purchase_date, defect_type_id)], company_id=company_id)[0]
