"""Rule-facts catalog for the RuleBuilder.

``GET /rule-facts?sources=promotion`` returns the whitelisted facts for the
requested fact sources, with per-type operators and materialized dynamic
option lists (e.g. the ContactAccessType catalog for ``promotion.accessLevels``).
The Automation edit form calls this to render the nested AND/OR condition builder
for triggers that expose a fact source.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_permission
from app.rule_engine.registry import get_facts
from app.rule_engine.schemas import OPERATORS_BY_TYPE
from app.schemas.rule_facts import RuleFactItem

router = APIRouter()


@router.get("", response_model=List[RuleFactItem])
def list_rule_facts(
    sources: Optional[List[str]] = Query(
        None, description="Fact source names to include (repeat or csv), e.g. promotion."
    ),
    current_user: dict = Depends(require_permission("automation.automations.view")),
    db: Session = Depends(get_db),
):
    """Facts for the requested sources — key, label, type, operators, options."""
    # Accept csv-in-one-param as well as repeated params.
    resolved: List[str] = []
    for raw in sources or []:
        resolved.extend(part.strip() for part in str(raw).split(",") if part.strip())

    items: List[RuleFactItem] = []
    for source_name, source_label, fact in get_facts(resolved):
        options = None
        if fact.options is not None:
            options = (
                fact.options(db, current_user)
                if callable(fact.options)
                else list(fact.options)
            )
        items.append(
            RuleFactItem(
                key=fact.key,
                label=fact.label,
                type=fact.type,
                operators=OPERATORS_BY_TYPE.get(fact.type, []),
                source=source_name,
                sourceLabel=source_label,
                options=options,
            )
        )
    return items
