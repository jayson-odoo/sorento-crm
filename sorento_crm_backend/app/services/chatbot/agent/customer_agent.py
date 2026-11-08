"""`crm_customer_agent`: one row of a pasted table puts a customer account under a sales agent, as the user
(AGENT-BULK-W3-AGENTS).

PLAN-agent-bulk-w3-agents-8nov.md. The row names its customer by EXACT customer code (case and spaces aside); a row
that gives only a name waits with the row's company's active accounts whose name contains it, and nothing is
auto-picked, not even one (`contact_grant.NeedsChoice`). The agent is the one whose code or name (`person_label`, else
`description`) is exactly what the row wrote, among agents that fit the customer's company (its own or shared); not
exact means a pick among the fitting active agents that contain the text. The change is the Customers tab's
(`POST /sales-agents/{id}/customers`, `sales_agents.py:181`), through the same service
(`CustomerService.assign_sales_agent_many`), so the screen's checks and audit apply. Assign only: clearing an agent
stays on the customer form (crew Q3). The customer's agent is CRM-owned; nothing here is sent anywhere (crew Q1).
For a company that credits invoices to the customer's current agent (`companies.sales_agent_source = 'customer'`),
the row says how much invoiced sales of the last 12 months move with it (crew Q2). `read_before` refuses (4xx) a row
that cannot apply; the batch tool shows that message as the row's skip reason.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from app.services.chatbot.agent import writes
from app.services.chatbot.agent.contact_grant import NeedsChoice, _clean, _company_words, _fits, _refuse

WRITE = "crm_customer_agent"
EDIT = "master_data.sales_agents.edit"
EVENT = "customer.sales_agent_agent"
MAX_CHOICES = 10
MOVES = "Past invoiced sales of this customer move to {agent} (RM {amount:,.2f} in the last 12 months)"


def _fold(text: Any) -> str:
    return _clean(text).lower()


def _norm(column):
    from sqlalchemy import func

    return func.lower(func.regexp_replace(func.trim(func.coalesce(column, "")), r"\s+", " ", "g"))


def _code_of(db, company_id: Any) -> str:
    from app.models.company import Company

    row = db.get(Company, str(company_id)) if company_id else None
    return row.code if row is not None else "another company"


def _company(db, written: str, problems: list[str], scope):
    """The row's company, only one the user may see (the read scope is every granted company)."""
    from sqlalchemy import func

    from app.models.company import Company

    rows = db.query(Company).filter(func.lower(func.trim(Company.code)) == written.lower()).all()
    if isinstance(scope, frozenset):
        rows = [r for r in rows if str(r.id) in scope]
    if len(rows) != 1:
        problems.append(f'No company "{written}".')
        return None
    return rows[0]


def _customer(db, args: dict, company, problems: list[str], choices: list[dict], kept: list[str]):
    """The row's customer (read under the user's companies), or None with a problem or a choice recorded."""
    from sqlalchemy import func

    from app.models.order import Customer

    code, name = _clean(args.get("customer_code")), _clean(args.get("customer_name"))
    row_words = _company_words([company.code]) if company is not None else ""
    if code:
        rows = db.query(Customer).filter(func.lower(func.trim(Customer.customer_code)) == code.lower()).all()
        if not rows:
            problems.append(f'No customer with the code "{code}" in your companies.')
            return None
        mine = [r for r in rows if company is None or str(r.company_id) == str(company.id)]
        if not mine:
            where = _company_words(sorted({_code_of(db, r.company_id) for r in rows}))
            problems.append(f'"{code}" is a {where} customer, but the row\'s company is {row_words}.')
            return None
        if len(mine) > 1:
            problems.append(f'More than one company has the customer code "{code}"; give the company.')
            return None
        if not mine[0].is_active:
            problems.append(f'Customer "{mine[0].customer_code}" is inactive.')
            return None
        kept.append(code.lower())
        return mine[0]
    if not name:
        problems.append("Give the customer code.")
        return None
    if company is None:
        # The same code is often held by two companies' different businesses, so a pick needs the company.
        problems.append(f'Give the company for the customer named "{name}" (or its code).')
        return None
    contains = db.query(Customer.customer_code, Customer.customer_name, Customer.company_id).filter(
        Customer.is_active.is_(True), func.strpos(_norm(Customer.customer_name), name.lower()) > 0
    )
    found = contains.filter(Customer.company_id == str(company.id)).order_by(Customer.customer_code).limit(MAX_CHOICES + 1).all()
    if found:
        choices.append({
            "written": name, "company": company.code, "noun": "customer",
            "candidates": [{"code": r.customer_code, "name": r.customer_name} for r in found[:MAX_CHOICES]],
            "more": len(found) > MAX_CHOICES,
        })
        return None
    elsewhere = sorted({_code_of(db, r.company_id) for r in contains.limit(50).all()})
    if elsewhere:
        problems.append(f'"{name}" is a {_company_words(elsewhere)} customer, but the row\'s company is {row_words}.')
    else:
        problems.append(f'No customer named "{name}" in your companies.')
    return None


def _agent(db, written: str, company_id: str | None, scope, problems: list[str], choices: list[dict], kept: list[str]):
    """The agent the row names, among agents that fit `company_id` (its own or shared; every company the user sees
    when the customer is not known yet), or None with a problem or a choice recorded."""
    from sqlalchemy import func, or_

    from app.models.sales_agent import SalesAgent

    said = _clean(written)
    if not said:
        problems.append("Name the sales agent.")
        return None
    low = said.lower()

    def fits(q):
        if company_id is not None:
            return q.filter(or_(SalesAgent.company_id == str(company_id), SalesAgent.company_id.is_(None)))
        if isinstance(scope, frozenset):
            return q.filter(or_(SalesAgent.company_id.in_(sorted(scope)), SalesAgent.company_id.is_(None)))
        return q

    codes = (SalesAgent.sales_agent,)
    names = (SalesAgent.person_label, SalesAgent.description)
    # An exact code first: tier codes contain each other ("X I" sits inside "X III"), so a code is never matched by
    # containment. Then an exact person name (one person often holds a code per tier: several agents, a pick).
    for columns in (codes, names):
        exact = fits(db.query(SalesAgent).filter(or_(*(_norm(c) == low for c in columns)))).order_by(
            SalesAgent.sales_agent
        ).all()
        if not exact:
            continue
        active = [a for a in exact if a.is_active]
        if not active:
            problems.append(f'Sales agent "{exact[0].sales_agent}" is inactive.')
            return None
        if len(active) == 1:
            kept.append(low)
            return active[0]
        choices.append(_agent_choice(said, active, False))
        return None
    if company_id is not None:
        others = db.query(SalesAgent.company_id).filter(
            or_(*(_norm(c) == low for c in (*codes, *names))),
            SalesAgent.company_id.isnot(None), SalesAgent.company_id != str(company_id),
        )
        if isinstance(scope, frozenset):
            others = others.filter(SalesAgent.company_id.in_(sorted(scope)))
        where = sorted({_code_of(db, c) for (c,) in others.limit(50).all()})
        if where:
            problems.append(
                f'"{said}" is a {_company_words(where)} agent, but the customer is {_company_words([_code_of(db, company_id)])}.'
            )
            return None
    found = (
        fits(db.query(SalesAgent).filter(
            SalesAgent.is_active.is_(True), or_(*(func.strpos(_norm(c), low) > 0 for c in names)),
        ))
        .order_by(SalesAgent.sales_agent)
        .limit(MAX_CHOICES + 1)
        .all()
    )
    if found:
        choices.append(_agent_choice(said, found[:MAX_CHOICES], len(found) > MAX_CHOICES))
    else:
        problems.append(f'No sales agent named "{said}".')
    return None


def _agent_choice(written: str, agents: list, more: bool) -> dict:
    return {
        "written": written, "company": "", "noun": "agent", "more": more,
        "candidates": [{"code": a.sales_agent, "name": _clean(a.person_label or a.description)} for a in agents],
    }


def _year_ago(today: date) -> date:
    try:
        return today.replace(year=today.year - 1)
    except ValueError:  # 29 February
        return today - timedelta(days=365)


def moving_amount(db, customer_id: str, today: date | None = None) -> Decimal:
    """The customer's invoiced sales (RM, credit notes negative) of the last 12 months: what moves to the new agent
    in a company that credits the customer's current agent. The same figure the sales reports use
    (`invoiced_sales.posted` / `signed_amount`)."""
    import sqlalchemy as sa

    from app.models.finance import BillingDocument
    from app.services.sales import invoiced_sales

    # Malaysia's date (UTC+8, no DST), as `chatbot.do_ask.today_myt`.
    today = today or (datetime.now(timezone.utc) + timedelta(hours=8)).date()
    total = db.query(sa.func.coalesce(sa.func.sum(invoiced_sales.signed_amount()), 0)).filter(
        invoiced_sales.posted(),
        BillingDocument.customer_id == str(customer_id),
        BillingDocument.doc_date > _year_ago(today),
        BillingDocument.doc_date <= today,
    ).scalar()
    return Decimal(total or 0)


def plan(db, user: dict, args: dict) -> dict:
    """What the row would change, after every check. Raises the refusal the preview shows otherwise. Reads under every
    company the user is granted (the #2241 rule)."""
    from app.models.base import get_company_scope
    from app.models.company import Company
    from app.models.sales_agent import SalesAgent
    from app.services.company_scope_resolver import grants_scope
    from app.services.sales.invoiced_sales import AGENT_FROM_CUSTOMER

    with grants_scope(db, str(user["id"])):
        scope = get_company_scope(db)
        problems: list[str] = []
        choices: list[dict] = []
        kept: list[str] = []
        said_company = _clean(args.get("company"))
        company = _company(db, said_company, problems, scope) if said_company else None
        if said_company and company is None:
            customer = None
        else:
            customer = _customer(db, args, company, problems, choices, kept)
        if customer is not None and company is None:
            company = db.get(Company, str(customer.company_id))
        agent_company = str(customer.company_id) if customer is not None else (str(company.id) if company else None)
        agent = _agent(db, args.get("agent"), agent_company, scope, problems, choices, kept)
        if problems:
            problems += [_fits(c) for c in choices]
            raise _refuse("; ".join(p.rstrip(".") for p in problems) + ".")
        if choices:
            for c in choices:
                c["kept"] = kept
            raise NeedsChoice(choices)
        if str(customer.sales_agent_id or "") == str(agent.id):
            raise _refuse(f"Already under {agent.sales_agent}; nothing to change.")
        current = db.get(SalesAgent, str(customer.sales_agent_id)) if customer.sales_agent_id else None
        old = current.sales_agent if current is not None else "none"
        lines = [f"agent {old} -> {agent.sales_agent}"]
        if company is not None and company.sales_agent_source == AGENT_FROM_CUSTOMER:
            lines.append(MOVES.format(agent=agent.sales_agent, amount=moving_amount(db, str(customer.id))))
        return {
            "customer": customer, "agent": agent, "lines": lines, "old": old,
            "code": customer.customer_code, "name": _name(customer, args),
            "before": {
                "customer_id": str(customer.id),
                "sales_agent_id": str(customer.sales_agent_id) if customer.sales_agent_id else None,
                "target": str(agent.id),
            },
        }


def _name(customer, args: dict) -> str:
    """The account's name in the CRM, with the table's name when it differs (a code typo that hits another account
    shows)."""
    crm, said = _clean(customer.customer_name)[:255], _clean(args.get("customer_name"))[:255]
    if not crm:
        return said
    return crm if not said or said.casefold() == crm.casefold() else f"{crm} (table says {said})"


def _read_before(db, user: dict, args: dict) -> dict:
    p = plan(db, user, args)
    return {**p["before"], "_show": {"code": p["code"], "name": p["name"], "changes": p["lines"]}}


def _summary(args: dict, before: dict) -> str:
    who = f"{writes._line(before['code'])} {writes._line(before['name'])}".strip()
    return f"{who}: " + "; ".join(writes._line(c) for c in before["changes"])


def _preview(args: dict, shown: dict | None) -> dict:
    if shown is None:
        return {"Customer": _clean(args.get("customer_code")), "Name": _clean(args.get("customer_name"))}
    return {"Customer": shown.get("code") or "", "Name": shown.get("name") or "",
            "Will change": "; ".join(shown.get("changes") or [])}


def _batch_key(args: dict) -> str | None:
    """The row's customer as the table wrote it: a picked code keeps the written name, so the row stays the same row
    across a pick (the pick check reads it)."""
    if not isinstance(args, dict):
        return None
    who = _fold(args.get("customer_name")) or _fold(args.get("customer_code"))
    return f"{_fold(args.get('company'))}|{who}" if who else None


def _execute(db, user: dict, args: dict) -> dict:
    from app.services import audit_service
    from app.services.company_scope_resolver import grants_scope
    from app.services.order_service import CustomerService

    p = plan(db, user, args)
    customer, agent = p["customer"], p["agent"]
    with grants_scope(db, str(user["id"])):
        # The Customers tab's service: its checks (active agent, the customer's own company or shared), its commit,
        # and the customer listener's before / after audit row.
        CustomerService(db).assign_sales_agent_many([customer], str(agent.id))
        audit_service.record(
            db,
            event=EVENT,
            entity_type="customers",
            entity_id=str(customer.id),
            old_values={"Sales agent": p["old"]},
            new_values={"Sales agent": agent.sales_agent, "Changes": p["lines"]},
            description=f"Agent sales agent change for {p['code']} from a pasted table",
            company_id=str(customer.company_id),
        )
        db.commit()
    return {"id": str(customer.id), "after": {"old": p["old"], "new": agent.sales_agent, "changes": p["lines"]}}


def _changes(args: dict, before: dict, after: dict, shown: dict) -> list[dict]:
    record = f"{shown.get('code') or ''} {shown.get('name') or ''}".strip()
    return [{"record": record, "field": "Sales agent", "before": after.get("old") or "", "after": after.get("new") or ""}]


_TEXT = {"type": "string"}

writes.WRITES[WRITE] = writes.WriteDef(
    name=WRITE,
    user_permission=EDIT,
    schema={
        "type": "function",
        "function": {
            "name": WRITE,
            "description": (
                "Put one customer account under a sales agent, from a row of a pasted table or sheet. The customer is "
                "found by its customer code (a name only lists the accounts to pick from); the agent by its code or "
                "name. For a table, use crm_batch_propose with this write and one row per customer. Use the table's "
                "values as written: never invent a code or an agent. Clearing an agent is not done here. Nothing "
                "changes until the user confirms."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "company": {**_TEXT, "description": "The company code as in the table (e.g. SRT, MCH), if any."},
                    "customer_code": {**_TEXT, "description": "The customer (debtor) code exactly as in the table."},
                    "customer_name": {**_TEXT, "description": "The customer's name from the table."},
                    "agent": {**_TEXT, "description": "The sales agent's code or name exactly as in the table."},
                },
                # No `required`: a row without a code or an agent is listed as Not changed with what to give.
            },
        },
    },
    read_before=_read_before,
    summary=_summary,
    execute=_execute,
    record_key="",
    changes=_changes,
    batchable=True,
    preview=_preview,
    batch_key=_batch_key,
)
