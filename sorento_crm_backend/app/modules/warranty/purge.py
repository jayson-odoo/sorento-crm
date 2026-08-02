"""Delete the warranty engine's own data (AC-L2).

Policies, terms, kinds, kind rules and the stored verdicts go. The ledger this
module reads through does NOT: it belongs to another module, it is the strategic
asset, and a lifetime ceramic claim years from now needs the receipt whether or not
this engine happens to be installed today. That boundary is the whole justification
for the module split, so nothing here names a table it does not own.

Children first: verdicts reference terms, terms reference policies and kinds, rules
reference kinds.
"""
from __future__ import annotations

import logging
from typing import Dict

from sqlalchemy.orm import Session

from app.models.warranty import (
    WarrantyAssessment,
    WarrantyKindRule,
    WarrantyPolicy,
    WarrantyProductKind,
    WarrantyTerm,
)

logger = logging.getLogger(__name__)


def _deleted(db: Session, model, label: str) -> int:
    count = db.query(model).delete(synchronize_session=False)
    logger.info("Purge %s: deleted %s rows", label, count)
    return count


def purge(db: Session) -> Dict[str, int]:
    out: Dict[str, int] = {}
    out["warranty_assessments"] = _deleted(db, WarrantyAssessment, "warranty_assessments")
    out["warranty_terms"] = _deleted(db, WarrantyTerm, "warranty_terms")
    out["warranty_kind_rules"] = _deleted(db, WarrantyKindRule, "warranty_kind_rules")
    out["warranty_policies"] = _deleted(db, WarrantyPolicy, "warranty_policies")
    out["warranty_product_kinds"] = _deleted(db, WarrantyProductKind, "warranty_product_kinds")
    return out
