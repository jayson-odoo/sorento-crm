"""Service for generating document running numbers from configured rules."""
from datetime import date
from typing import Optional

from sqlalchemy.orm import Session

from app.models.numbering import DocumentNumberingRule


class NumberingService:
    def __init__(self, db: Session):
        self.db = db

    def get_next_number(self, doc_type: str, reference_date: Optional[date] = None) -> Optional[str]:
        """
        Generate the next running number for the given doc_type.
        Uses row-level lock (FOR UPDATE) for safe concurrent generation.
        reference_date is used for reset policy (yearly/monthly); defaults to today.
        """
        if reference_date is None:
            reference_date = date.today()

        rule = (
            self.db.query(DocumentNumberingRule)
            .filter(
                DocumentNumberingRule.doc_type == doc_type,
                DocumentNumberingRule.enabled.is_(True),
            )
            .with_for_update()
            .first()
        )
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
        self.db.commit()
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
