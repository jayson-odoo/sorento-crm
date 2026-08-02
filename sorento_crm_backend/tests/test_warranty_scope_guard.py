"""S2 guards that are GREEN on arrival: the slice boundary, and one AC that is false.

Everything here asserts an absence, so none of it can be red before the
implementation exists. It is split out of ``tests/test_warranty_engine.py`` for
exactly that reason: the S2 gate file is entirely red, and mixing in guards that
pass by construction would make the red count read as partial progress. The same
split the S1 author made, for the same reason.

Three families:

1. **The S2 / S2b boundary** (decided 2026-08-02). ``consumer_profiles``,
   ``consumer_purchases``, ``consumer_purchase_lines`` and ``warranty_assessments``
   belong to the consumer module, where the consent model, the anonymisation path
   and the receipt dedupe key are decided. The plan's S2 schema block still shows
   them, so the failure mode is a copy-paste, and nothing else would catch it.
   **S2b DELETES this family** rather than satisfying it.

2. **AC-D2's "never a single FK on products".** A Kind reached by a column on
   ``products`` is the design ADR-0010 exists to refuse, and it is the first thing a
   reader will reach for when the rule table feels like ceremony.

3. **AC-D13, in the only form that can hold today.**

   AC-D13 says ``products.warranty_months`` "is abandoned by this engine and no code
   path reads it". The second clause is FALSE on arrival, exactly as AC-B9 was in
   S1: the column is a declared response field on the product and marketing schemas
   and a registered attachment field-link spec. A test written the way the AC
   describes would be red on arrival and could only be made green by deleting
   behaviours S2 does not own.

   So the enforceable half is the same one S1 settled on: **freeze the reader set.**
   The list below IS the drop worklist. Nothing may be added to it, and every entry
   must be retired before the column is dropped. The complementary red half lives in
   the gate file as
   ``test_the_warranty_module_never_reads_products_warranty_months`` - the NEW code
   S2 adds must not read it.

Run: venv/bin/python -m pytest tests/test_warranty_scope_guard.py -q -p no:randomly
"""
from __future__ import annotations

import pathlib
import re

import pytest

from app.database import Base
from app.models.product import Product

BACKEND_ROOT = pathlib.Path(__file__).resolve().parents[1]
APP_ROOT = BACKEND_ROOT / "app"

# S2b HAS LANDED (2026-08-02). `consumer_profiles`, `consumer_purchases`,
# `consumer_purchase_lines` and `warranty_assessments` now exist, so the guard that
# asserted their absence during S2 is deleted here, exactly as its own docstring
# instructed ("S2b DELETES THIS TEST"). The boundary it protected held: `resolve`
# still takes plain values and never a purchase row.

PATTERNS = {
    "products.warranty_months": (
        r"\bProduct\.warranty_months\b",
        r"\bproduct\.warranty_months\b",
        r'"warranty_months"',
        r"'warranty_months'",
        r"^\s*warranty_months\s*[:=]",
    ),
}

# The frozen inventory, captured 2026-08-02 on feat/after-sales-warranty at head
# 316_after_sales_parties. Model definitions are excluded (app/models/product.py
# declares the column; declaring is not reading).
#
# Not asserted, but part of the same worklist: alembic/versions/128 registers
# ``warranty_months`` as a products list-query field, so the column also has a
# column-config presence to retire. A migration is history and is never edited, so
# the drop slice removes the registry ROW, not the revision.
KNOWN_READERS = {
    "products.warranty_months": {
        "app/schemas/marketing.py",
        "app/schemas/product.py",
        "app/services/field_linkage/registry.py",
    },
}

# AC-D2. Any of these on ``products`` would be the single FK the ADR refuses.
BANNED_PRODUCT_COLUMNS = (
    "warranty_kind_id",
    "kind_id",
    "warranty_product_kind_id",
    "warranty_policy_id",
    "warranty_term_id",
)


@pytest.mark.parametrize("column", BANNED_PRODUCT_COLUMNS)
def test_a_kind_is_never_a_single_fk_on_products(column):
    """AC-D2 and the whole of ADR-0010.

    A column on ``products`` cannot express what the mapping needs: some terms name
    a model list, some a series, and the codes people actually report
    (``SRTWC8152``, ``WC189-G2``, ``SRTWC8517-200mm``) resolve to no product row at
    all. Cover has to be decided BEFORE the exact model is known, which a per-row FK
    makes impossible - and it would need maintaining on all 11,415 rows besides.
    """
    assert column not in {c.key for c in Product.__table__.columns}, (
        f"products.{column} exists. AC-D2: a product resolves to a Kind through "
        "warranty_kind_rules (category, model prefix, model list, series), never "
        "through a single FK."
    )


def _readers(column: str) -> set[str]:
    patterns = PATTERNS[column]
    found = set()
    for path in APP_ROOT.rglob("*.py"):
        if path.parent.name == "models":
            continue  # declaring a column is not reading it
        source = path.read_text(encoding="utf-8", errors="ignore")
        if any(re.search(pattern, source, re.M) for pattern in patterns):
            found.add(path.relative_to(BACKEND_ROOT).as_posix())
    return found


@pytest.mark.parametrize("column", sorted(PATTERNS))
def test_no_new_reader_of_products_warranty_months(column):
    """AC-D13, narrowed to what can honestly hold today.

    A NEW reader is what makes the eventual drop unbounded. It is also, for this
    particular column, a functional bug on arrival: 0 of 11,415 rows are populated,
    so anything reading it reads NULL every time.
    """
    added = _readers(column) - KNOWN_READERS[column]
    assert not added, (
        f"New reader(s) of {column}: {sorted(added)}. The column is abandoned "
        "(AC-D13, ADR-0010) - read the warranty engine instead: a Kind's terms carry "
        "part, duration or lifetime, defect scope and installation."
    )


@pytest.mark.parametrize("column", sorted(PATTERNS))
def test_the_drop_worklist_is_still_accurate(column):
    """A stale allowlist looks like progress and hides that none was made."""
    stale = KNOWN_READERS[column] - _readers(column)
    assert not stale, (
        f"KNOWN_READERS[{column!r}] lists {sorted(stale)}, which no longer read it. "
        "Remove them in the commit that retired them, so the remaining list is the "
        "real drop worklist."
    )


def test_no_warranty_code_enforces_the_residential_restriction():
    """AC-D15. Clause 17 is modelled, not enforced, pending Sorento's ruling.

    23 of 50 existing Complaints are Project cases (hotels, commercial fitouts).
    Read literally, clause 17 covers none of them, so a well-meaning branch on
    "residential" inside the engine would refuse half of Sorento's live complaints
    the day it shipped.

    Scoped to the warranty module's own files: the words appear in unrelated
    comments elsewhere in ``app/``, and the policy TEXT itself lives in a database
    column and a seed script, where recording the restriction is exactly right.
    """
    offenders = []
    for path in APP_ROOT.rglob("*.py"):
        if "warranty" not in path.name:
            continue
        source = path.read_text(encoding="utf-8", errors="ignore")
        # Code, not prose: an assignment, a comparison or a branch on the concept.
        for pattern in (
            r"is_residential",
            r"residential_only",
            r"==\s*['\"]residential['\"]",
            r"==\s*['\"]commercial['\"]",
            r"==\s*['\"]Project['\"]",
        ):
            if re.search(pattern, source):
                offenders.append(f"{path.relative_to(BACKEND_ROOT).as_posix()} ({pattern})")
    assert not offenders, (
        "The warranty engine branches on installation context: "
        f"{offenders}. AC-D15 says clause 17 is MODELLED (policy text, term "
        "exclusions) and NOT ENFORCED until Sorento rules on it."
    )
