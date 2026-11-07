"""The filter params the six ask definitions show on the "Sales & outstanding" screen (REPORT-UNIFY slice 4,
`documentation/plans/reports/PLAN-report-unify-27oct.md` section 3b).

The ask definitions (`datasets/sales_order_lines_ask`, `billing_document_lines.ASK_DEFINITION`,
`delivery_order_lines.PENDING_DEFINITION`, `unpaid_documents`) are the ones `ask.CATALOGUE` runs for the chatbot; the
screen registers THE SAME objects, so the option lists and the `spec` condition below are what staff see and what the
route's own filters mean. Customer, agent, brand and category options reuse the helpers of the Top selling items and
Sales by debtor type reports.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import false, func, or_, and_

from app.models.base import company_scope
from app.models.order import Customer
from app.models.product import ProductCategory
from app.services.reports import spec_set


def customer_options(db: Any) -> List[Tuple[str, str]]:
    rows = db.query(Customer.id, Customer.customer_name).filter(Customer.customer_name.isnot(None)).all()
    return sorted(((str(i), str(n)) for i, n in rows), key=lambda r: r[1].casefold())


def agent_options(db: Any) -> List[Tuple[str, str]]:
    from app.services.reports.definitions.sales_by_debtor_type import agent_options as options

    return options(db)


def person_options(db: Any) -> List[Tuple[str, str]]:
    """The distinct person labels (the `sales_person` filter's options): a person_label, else the agent's code."""
    from app.models.base import get_company_scope
    from app.models.sales_agent import SalesAgent
    from app.services.scm.sales_agent_service import scope_filter

    q = db.query(SalesAgent.sales_agent, SalesAgent.person_label).filter(SalesAgent.is_active.is_(True))
    predicate = scope_filter(get_company_scope(db))
    if predicate is not None:
        q = q.filter(predicate)
    names = {(label or "").strip() or str(code) for code, label in q.all()}
    return [(n, n) for n in sorted(names)]


def brand_options(db: Any) -> List[Tuple[str, str]]:
    from app.services.reports.definitions.top_selling_items import brand_options as options

    return options(db)


def category_options(db: Any) -> List[Tuple[str, str]]:
    rows = db.query(ProductCategory.id, ProductCategory.category_name).filter(ProductCategory.category_name.isnot(None)).all()
    return sorted(((str(i), str(n)) for i, n in rows), key=lambda r: r[1].casefold())


def spec_options(db: Any) -> List[Tuple[str, str]]:
    """One option per enum value of the spec registry: value `key:value` (the route's own `spec=` form), label
    "<registry label>: <value label>"."""
    from app.services.product_spec_registry import display_spec_value, merged_allowed_values

    out: List[Tuple[str, str]] = []
    for row in sorted(spec_set.registry(db).values(), key=lambda r: (str(r.label or r.spec_key).casefold(), r.spec_key)):
        if (row.data_type or "").lower() != "enum":
            continue
        labels = dict(getattr(row, "value_labels", None) or {})
        # The registry's allowed values, then any value staff gave only a label (a label is an offered word too).
        values = list(merged_allowed_values(row))
        values += [v for v in labels if v not in values]
        for value in values:
            out.append((f"{row.spec_key}:{value}", f"{row.label}: {display_spec_value(value, labels)}"))
    return out


def spec_condition(ctx: Any, values: Sequence[str]) -> Optional[Any]:
    """`product_id IN (the products holding the chosen spec values)`: the resolution the route's `spec` param uses
    (different keys ANDed, the values of one key ORed). A term that cannot narrow matches nothing, never the whole set."""
    column = ctx.dataset.product_id_column
    if column is None:
        return None
    try:
        terms = spec_set.parse(list(values))
    except ValueError:
        return false()
    grants = ctx.company_grants
    ids, _echo, _not_applied = spec_set.resolve(ctx.db, terms, set(), None if grants is None else set(grants))
    return column.in_(ids) if ids else false()


# ------------------------------------------------------------------------ account type
#
# A ledger's account type is `customers.autocount_debtor_type`. The AutoCount book also tags a ledger's name with a
# number, `[A/C IV]` at the end; a number means the type most of its tagged ledgers hold, derived per company.

_TAG = r"\[(A/C [IVX]+)\]\s*$"
_ROMAN = {"I": 1, "V": 5, "X": 10}
_NUMBER = re.compile(r"^(?:A/C\s+)?([IVX]+)$")


def roman_to_int(numeral: str) -> int:
    total = 0
    for i, ch in enumerate(numeral):
        value = _ROMAN[ch]
        total += -value if i + 1 < len(numeral) and _ROMAN[numeral[i + 1]] > value else value
    return total


class AccountBook:
    """Per company: the types its typed ledgers hold, and the type each tag number means."""

    def __init__(self) -> None:
        self.types: Dict[str, set] = {}
        self.numbers: Dict[str, Dict[int, str]] = {}

    @property
    def loaded(self) -> bool:
        return any(self.types.values())

    def numbered(self) -> Dict[int, set]:
        out: Dict[int, set] = {}
        for company_numbers in self.numbers.values():
            for number, dtype in company_numbers.items():
                out.setdefault(number, set()).add(dtype)
        return out


def account_book(db: Any, company_ids: Optional[Sequence[str]]) -> AccountBook:
    """One GROUP BY company, tag, type over the ledgers of `company_ids` (None = every company). Only typed ledgers
    count; a number's type is the one most ledgers carrying that tag hold, a tie going to the first type by name."""
    tag = func.substring(Customer.customer_name, _TAG)
    stmt = (
        db.query(Customer.company_id, tag, Customer.autocount_debtor_type, func.count())
        .filter(Customer.autocount_debtor_type.isnot(None), func.btrim(Customer.autocount_debtor_type) != "")
        .group_by(Customer.company_id, tag, Customer.autocount_debtor_type)
    )
    if company_ids is not None:
        stmt = stmt.filter(Customer.company_id.in_([str(c) for c in company_ids]))
    with company_scope(db, None):
        rows = stmt.all()
    book = AccountBook()
    best: Dict[Tuple[str, int], Tuple[int, str]] = {}
    for company, label, dtype, count in rows:
        cid = str(company)
        book.types.setdefault(cid, set()).add(dtype)
        if label:
            key = (cid, roman_to_int(label.split()[-1]))
            current = best.get(key)
            if current is None or count > current[0] or (count == current[0] and dtype < current[1]):
                best[key] = (count, dtype)
    # A type answers to one number only: the one most of its ledgers carry (a tie goes to the lowest number).
    winners: Dict[Tuple[str, str], Tuple[int, int]] = {}
    for (cid, number), (count, dtype) in sorted(best.items(), key=lambda kv: kv[0][1]):
        current = winners.get((cid, dtype))
        if current is None or count > current[0]:
            winners[(cid, dtype)] = (count, number)
    for (cid, dtype), (_count, number) in winners.items():
        book.numbers.setdefault(cid, {})[number] = dtype
    return book


def _asked_number(value: str) -> Optional[int]:
    if len(value) > 50:
        return None
    if value.isascii() and value.isdigit():
        return int(value) if len(value) <= 6 else None
    match = _NUMBER.match(value)
    return roman_to_int(match.group(1)) if match else None


def resolve_account_types(book: AccountBook, values: Sequence[str]) -> Tuple[Dict[str, set], List[str]]:
    """({company: the stored types the asked values mean there}, the values meaning nothing in any company)."""
    per_company: Dict[str, set] = {}
    unknown: List[str] = []
    for raw in values:
        value = raw.strip().upper()
        number = _asked_number(value)
        hit = False
        for cid, types in book.types.items():
            by_name = {t for t in types if t.strip().upper() == value}
            found = by_name or ({book.numbers[cid][number]} if number is not None and number in book.numbers.get(cid, {}) else set())
            if found:
                per_company.setdefault(cid, set()).update(found)
                hit = True
        if not hit:
            unknown.append(raw)
    return per_company, unknown


def unknown_account_message(book: AccountBook, unknown: Sequence[str]) -> str:
    numbered = book.numbered()
    led = {t for types in numbered.values() for t in types}
    stored = {t for types in book.types.values() for t in types}
    names = [str(n) for n in sorted(numbered)] + sorted(stored - led)
    return f"No account type {', '.join(unknown)}. Account types: {', '.join(names)}."


def account_type_options(db: Any) -> List[Tuple[str, str]]:
    rows = db.query(Customer.autocount_debtor_type).filter(Customer.autocount_debtor_type.isnot(None)).distinct().all()
    return sorted(((t, t) for (t,) in rows if t and t.strip()), key=lambda r: r[1].casefold())


def account_type_condition(ctx: Any, values: Sequence[str]) -> Optional[Any]:
    """Customers whose stored type is what each company's own book makes of the asked values."""
    grants = ctx.company_grants
    book = account_book(ctx.db, None if grants is None else sorted(grants))
    per_company, _unknown = resolve_account_types(book, values)
    parts = [
        and_(Customer.company_id == cid, Customer.autocount_debtor_type.in_(sorted(types)))
        for cid, types in sorted(per_company.items())
    ]
    return or_(*parts) if parts else false()


#: The Detail tab's default columns of the line-level asks (the Top selling items report's shape: what, who, how much).
DETAIL_COLUMNS = ("month", "customer", "product", "sales_agent", "qty", "amount")
#: An unpaid invoice has no product and no quantity.
UNPAID_DETAIL_COLUMNS = ("month", "customer", "sales_agent", "amount")
