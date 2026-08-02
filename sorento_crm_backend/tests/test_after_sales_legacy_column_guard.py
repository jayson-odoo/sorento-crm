"""S1 guards that are GREEN on arrival: columns that must never appear, and a
frozen inventory of the legacy readers that must never grow.

Everything here asserts an absence, so none of it can be red before the
implementation exists. It is split out of ``tests/test_after_sales_parties.py`` for
exactly that reason: the S1 gate file is entirely red, and mixing in guards that
pass by construction would make the red count read as partial progress.

Three families:

1. **Columns AC-B1 and AC-M37 forbid.** ``party_kind``, ``door_answered_at`` and
   ``site_maps_url``. Each is something a plausible implementation adds and nothing
   else would catch.
2. **The AC-B13 deferral.** ``technician_id`` and a stub ``technicians`` table are
   both out of scope for S1 and S6 owns them. These two guards are the only tests in
   the after-sales suite that S6 **deletes** rather than satisfies; both say so in
   their failure message, so the S6 implementer is not left guessing whether a red
   here is a regression.
3. **The legacy-reader inventory (AC-B6a, AC-B9).** See the note below - both of
   those ACs are wrong as written, and this list is why.

AC-B6a and AC-B9 as far as they can honestly be enforced today.

**Both ACs are wrong as written, and this file is the evidence.**

AC-B6a says "a guard test asserts no module code READS ``customer_type``,
``customer_name`` or ``complaints.salesperson``". AC-B9 says "no runtime code path
reads ``orders.salesman``". Neither is true today and neither becomes true in S1:

- ``complaints.customer_type`` is read by the complaints list-field registry, the
  search filter, the PDF export, the AI extract schema and the portal.
- ``complaints.customer_name`` and ``complaints.salesperson`` are read by the same
  search filter, the email-template sample map and the portal serializer.
- ``orders.salesman`` is serialized by the orders API schema, mapped by the order
  import, and embedded verbatim by the embedding worker.

A test written the way the ACs describe would be red on arrival and could only be
made green by deleting a dozen behaviours S1 does not own. That is a refactor
request, not an acceptance criterion, and it also contradicts AC-B6's own wording:
a column that is "left in place, READ-ONLY, for one release" is by definition still
read.

So what is enforceable now is the narrower, useful half: **freeze the reader set.**
The list below IS the drop worklist. Nothing may be added to it, and every entry
must be retired before the columns are dropped. That converts an unsatisfiable AC
into a finite, checkable one, and it makes the eventual drop the pure deletion
AC-B6a is actually asking for.

This file is therefore GREEN on arrival, by construction. It is reported separately
from ``tests/test_after_sales_parties.py`` (which is entirely red) so the red count
of the S1 gate is not diluted. The complementary red half lives there as
``test_the_party_module_never_mentions_orders_salesman``: the NEW module S1 adds
must contain no reference to any of these columns.

Run: venv/bin/python -m pytest tests/test_after_sales_legacy_column_guard.py -q
"""
from __future__ import annotations

import pathlib
import re

import pytest

from app.database import Base
from app.models.access import RespondContact
from app.models.complaints import Complaint

BACKEND_ROOT = pathlib.Path(__file__).resolve().parents[1]
APP_ROOT = BACKEND_ROOT / "app"

# Attribute-access and lookup-key patterns only. Bare declaration patterns were
# tried and rejected: ``salesperson:`` and ``customer_name:`` also match the
# procurement, SCM and order schemas, which own their own columns of those names,
# so the guard would trip on changes that have nothing to do with complaints.
PATTERNS = {
    "complaints.customer_type": (
        r"\bComplaint\.customer_type\b",
        r"\bcomplaint\.customer_type\b",
        r'"customer_type"',
        r"'customer_type'",
    ),
    "complaints.customer_name": (
        r"\bComplaint\.customer_name\b",
        r"\bcomplaint\.customer_name\b",
    ),
    "complaints.salesperson": (
        r"\bComplaint\.salesperson\b",
        r"\bcomplaint\.salesperson\b",
    ),
    "orders.salesman": (
        r"\bOrder\.salesman\b",
        r"\.salesman\b",
        r'"salesman"',
        r"'salesman'",
        r"^\s*salesman\s*:",
    ),
}

# The frozen inventory, captured 2026-08-02 on feat/after-sales-warranty at head
# 315_wf_submission_attachments. Model definitions are excluded (app/models/*.py
# declares the columns; declaring is not reading).
#
# Not asserted, but part of the same worklist: ``app/schemas/complaints.py`` and
# ``app/schemas/external/complaints.py`` declare customer_type / customer_name /
# salesperson as response fields, so dropping the columns changes the API contract
# for whoever consumes them. Establishing who that is - n8n, the FE, or nobody - is
# the first task of the drop slice.
KNOWN_READERS = {
    "complaints.customer_type": {
        "app/api/v1/complaints/complaints.py",
        "app/services/ai_extract/form_schema_registry.py",
        "app/services/complaint_pdf_service.py",
        "app/services/complaints_service.py",
        "app/services/portal_service.py",
    },
    "complaints.customer_name": {
        "app/services/complaints_service.py",
        "app/services/email_template_service.py",
        "app/services/portal_service.py",
        "app/services/record_context_service.py",
    },
    "complaints.salesperson": {
        "app/services/complaints_service.py",
        "app/services/email_template_service.py",
        "app/services/portal_service.py",
    },
    "orders.salesman": {
        "app/schemas/order.py",
        "app/services/embedding_worker.py",
        "app/services/order_service.py",
    },
}


def test_respond_contacts_has_no_party_kind_and_no_door_answered_at():
    """AC-B1. Kind is derived, and there is no door question to remember.

    A stored ``party_kind`` is the failure mode this AC exists to prevent: it can
    disagree with the bindings, and nothing would ever notice. ``door_answered_at``
    is the same mistake in the time dimension - it only has meaning if a door was
    asked, and AC-B4 says one never is.
    """
    columns = {c.key for c in RespondContact.__table__.columns}
    for banned in ("party_kind", "door_answered_at"):
        assert banned not in columns, (
            f"respond_contacts.{banned} must not exist (AC-B1). Kind is derived from "
            "the bindings; a stored copy is a second source of truth that can "
            "disagree with them."
        )


def test_site_maps_url_is_never_created():
    """AC-M37. The UAC correction overrides the plan's schema block.

    The plan's S1 SQL still says ``site_maps_url text``. It was replaced by
    latitude / longitude / place_id before it was ever written, so creating it means
    shipping a column that has to be dropped and a decision about whether it
    survives. Asserted as an absence because that is the only way to catch a
    copy-paste from the stale plan block.
    """
    assert "site_maps_url" not in {c.key for c in Complaint.__table__.columns}, (
        "complaints.site_maps_url must not exist. See the UAC block 'Slotting and "
        "prior art - added 2026-08-02, before S1'."
    )


def test_s1_does_not_stub_the_deferred_technician_binding():
    """AC-B13. S1 ships two bindings; S6 adds the third with the table it points at.

    **S6 DELETES THIS TEST.** It is not a permanent invariant, it is a slice
    boundary. A red here means either S1 over-reached or S6 landed without removing
    the guard - check which before "fixing" it.

    The reason the deferral is the right call and not just sequencing convenience: a
    stub ``technicians`` table would be a half-defined core entity that S6 then has
    to migrate rather than design, and a nullable FK added later is cheap and purely
    additive. The order the binding will slot into is already pinned, as data, by
    ``test_after_sales_parties.py::test_kind_precedence_is_declared_as_data``, so
    deferring the column costs no decision.
    """
    assert "technician_id" not in {c.key for c in RespondContact.__table__.columns}, (
        "respond_contacts.technician_id is out of scope for S1 (AC-B13). If S6 has "
        "landed, delete this test and the technicians guard below."
    )


def test_s1_does_not_stub_a_technicians_table():
    """AC-B13, the other half. No table either.

    **S6 DELETES THIS TEST** (AC-F6 creates the real entity, bound to a
    respond_contact, with no ``users`` row per technician).
    """
    assert "technicians" not in Base.metadata.tables, (
        "A technicians table appeared. S1 must not stub it (AC-B13); S6 designs it "
        "(AC-F6). If S6 has landed, delete this test and the technician_id guard "
        "above."
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
def test_no_new_reader_of_a_legacy_party_column(column):
    """AC-B6a / AC-B9, in the only form that can hold today.

    A NEW reader is the thing that makes the drop unbounded: every one added after
    this point is another behaviour to unpick in a slice that was supposed to be a
    pure deletion.
    """
    added = _readers(column) - KNOWN_READERS[column]
    assert not added, (
        f"New reader(s) of {column}: {sorted(added)}. This column is deprecated "
        "(AC-B6) and is dropped a release from now. Read the replacement instead: "
        "reported_by_role for customer_type, complaints.customer_id for "
        "customer_name, and customers.account_owner_user_id for salesperson / "
        "salesman."
    )


@pytest.mark.parametrize("column", sorted(PATTERNS))
def test_the_drop_worklist_is_still_accurate(column):
    """The inventory must shrink honestly, not rot.

    A stale allowlist naming files that no longer read the column looks like
    progress and hides that none was made. When a reader is genuinely retired, its
    entry comes out of KNOWN_READERS in the same commit.
    """
    stale = KNOWN_READERS[column] - _readers(column)
    assert not stale, (
        f"KNOWN_READERS[{column!r}] lists {sorted(stale)}, which no longer read it. "
        "Remove them from the inventory in the commit that retired them, so the "
        "remaining list is the real drop worklist."
    )
