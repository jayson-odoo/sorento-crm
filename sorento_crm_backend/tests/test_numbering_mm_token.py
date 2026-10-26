"""PROJECT-REG-PORTAL PPF numbering, red-first (UAC C1, C3; C2 lives in the migration test,
C4 in test_project_registration_review.py).

`{mm}` is the zero-padded month; the project rule becomes `PPF{yy}{mm}`, 3 digits, monthly.
"""
from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import text

from app.main import app  # noqa: F401  MUST be first app import (circular import)

from ._pg_fixture import blank_session

DOC = "zzt_mm_token"


def _rule(db, *, prefix, digits=3, next_value=1, reset="none", key=None, doc=DOC):
    from app.models.numbering import DocumentNumberingRule

    row = DocumentNumberingRule(
        id=str(uuid.uuid4()),
        doc_type=doc,
        enabled=True,
        prefix_template=prefix,
        number_digits=digits,
        next_value=next_value,
        start_value=1,
        reset_policy=reset,
        last_reset_key=key,
    )
    db.add(row)
    db.flush()
    return row


def _draw(db, on, doc=DOC):
    from app.services.numbering_service import NumberingService

    return NumberingService(db).get_next_number(doc, reference_date=on, commit_rule=False)


def test_c1_mm_is_the_zero_padded_month_in_a_ppf_code():
    with blank_session() as db:
        rule = _rule(db, prefix="PPF{yy}{mm}", next_value=65, reset="monthly", key="2026-05")
        assert _draw(db, date(2026, 5, 7)) == "PPF2605065"
        assert rule.next_value == 66


def test_c1_the_first_draw_in_a_new_month_restarts_at_start_value():
    with blank_session() as db:
        rule = _rule(db, prefix="PPF{yy}{mm}", next_value=65, reset="monthly", key="2026-05")
        assert _draw(db, date(2026, 6, 2)) == "PPF2606001"
        assert rule.next_value == 2
        assert rule.last_reset_key == "2026-06"


def test_c1_single_digit_and_double_digit_months_are_both_two_characters():
    with blank_session() as db:
        _rule(db, prefix="PPF{yy}{mm}", next_value=1)
        assert _draw(db, date(2026, 1, 5)) == "PPF2601001"
        assert _draw(db, date(2026, 12, 31)) == "PPF2612002"


def test_c1_the_other_tokens_are_unchanged():
    """`{month}` and `{day}` stay unpadded; `{year}` four digits; `{yy}` two."""
    with blank_session() as db:
        _rule(db, prefix="X{year}-{yy}-{month}-{day}-", digits=4)
        assert _draw(db, date(2026, 5, 7)) == "X2026-26-5-7-0001"


def test_c3_the_seed_creates_the_ppf_rule():
    from app.services import project_seed_service as seed

    assert seed.PROJECT_NUMBERING["prefix_template"] == "PPF{yy}{mm}"
    assert seed.PROJECT_NUMBERING["number_digits"] == 3
    with blank_session() as db:
        assert seed.seed_numbering_rule(db) is True
        row = db.execute(
            text(
                "select prefix_template, number_digits, reset_policy, next_value, start_value "
                "from document_numbering_rules where doc_type = 'project'"
            )
        ).one()
        assert tuple(row) == ("PPF{yy}{mm}", 3, "monthly", 1, 1)
        assert _draw(db, date(2026, 5, 7), doc="project") == "PPF2605001"


def test_c3_seeding_never_overwrites_an_existing_project_rule():
    from app.services import project_seed_service as seed

    with blank_session() as db:
        _rule(db, prefix="ACME-", digits=6, doc="project")
        assert seed.seed_numbering_rule(db) is False
        prefix = db.execute(
            text("select prefix_template from document_numbering_rules where doc_type = 'project'")
        ).scalar()
        assert prefix == "ACME-"
