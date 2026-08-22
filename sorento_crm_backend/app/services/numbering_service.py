"""Service for generating document running numbers from configured rules."""
from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from app.models.numbering import DocumentNumberingRule


class NumberingService:
    def __init__(self, db: Session):
        self.db = db

    def get_next_number(
        self,
        doc_type: str,
        reference_date: Optional[date] = None,
        *,
        company_id: Optional[str] = None,
        commit_rule: bool = True,
    ) -> Optional[str]:
        """
        Generate the next running number for the given doc_type.
        Uses row-level lock (FOR UPDATE) for safe concurrent generation.
        reference_date is used for reset policy (yearly/monthly); defaults to today.
        When commit_rule is False, only flush() so the caller's transaction can commit/rollback atomically.

        `company_id` scopes the rule. Pass it for any document a customer sees: without it this
        query matched on doc_type alone and took `.first()` with no ORDER BY, so once a second
        company had a rule for the same doc_type the counter picked was whichever row Postgres
        happened to return - the same non-determinism that made `system_settings` saves vanish.
        The ORDER BY below keeps the unscoped legacy path at least repeatable.
        """
        if reference_date is None:
            reference_date = date.today()

        def _rule(scoped_to: Optional[str], *, unscoped_only: bool = False):
            query = self.db.query(DocumentNumberingRule).filter(
                DocumentNumberingRule.doc_type == doc_type,
                DocumentNumberingRule.enabled.is_(True),
            )
            if unscoped_only:
                query = query.filter(DocumentNumberingRule.company_id.is_(None))
            elif scoped_to is not None:
                query = query.filter(DocumentNumberingRule.company_id == scoped_to)
            return (
                query.order_by(
                    DocumentNumberingRule.company_id.nulls_last(),
                    DocumentNumberingRule.id,
                )
                .with_for_update()
                .first()
            )

        rule = _rule(company_id)
        if rule is None and company_id is not None:
            # A rule predating the company column applies to everybody, so an install that has not
            # had its rules split per company keeps numbering instead of silently falling back to
            # whatever the caller does when this returns None.
            rule = _rule(None, unscoped_only=True)
        if not rule:
            return None

        # Compute current period key for reset
        if rule.reset_policy == "yearly":
            current_key = str(reference_date.year)
        elif rule.reset_policy == "monthly":
            current_key = f"{reference_date.year}-{reference_date.month:02d}"
        else:
            current_key = rule.last_reset_key or ""

        if current_key and current_key != (rule.last_reset_key or ""):
            rule.next_value = rule.start_value
            rule.last_reset_key = current_key

        # Format prefix: support {year} (4-digit), {yy} (2-digit), {month}, {day}
        yy = str(reference_date.year % 100).zfill(2)  # 2026 -> "26", 2000 -> "00"
        prefix = (rule.prefix_template or "").format(
            year=reference_date.year,
            yy=yy,
            month=reference_date.month,
            day=reference_date.day,
        )

        number_part = str(rule.next_value).zfill(rule.number_digits)
        result = f"{prefix}{number_part}"

        rule.next_value += 1
        if commit_rule:
            self.db.commit()
        else:
            self.db.flush()
        return result

    def list_rules(self):
        """List all document numbering rules."""
        return self.db.query(DocumentNumberingRule).order_by(DocumentNumberingRule.doc_type).all()

    def get_rule(self, doc_type: str) -> Optional[DocumentNumberingRule]:
        """Get a single rule by doc_type."""
        return (
            self.db.query(DocumentNumberingRule)
            .filter(DocumentNumberingRule.doc_type == doc_type)
            .first()
        )

    def update_rule(
        self,
        doc_type: str,
        enabled: Optional[bool] = None,
        prefix_template: Optional[str] = None,
        number_digits: Optional[int] = None,
        next_value: Optional[int] = None,
        start_value: Optional[int] = None,
        reset_policy: Optional[str] = None,
    ) -> Optional[DocumentNumberingRule]:
        """Update an existing rule. Creates one if doc_type missing (for extensibility)."""
        rule = self.get_rule(doc_type)
        if not rule:
            rule = DocumentNumberingRule(doc_type=doc_type)
            self.db.add(rule)
            self.db.flush()

        if enabled is not None:
            rule.enabled = enabled
        if prefix_template is not None:
            rule.prefix_template = prefix_template
        if number_digits is not None:
            rule.number_digits = number_digits
        if next_value is not None:
            rule.next_value = next_value
        if start_value is not None:
            rule.start_value = start_value
        if reset_policy is not None:
            rule.reset_policy = reset_policy

        self.db.commit()
        self.db.refresh(rule)
        return rule
