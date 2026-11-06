"""Regression guards for entries in LESSONS-LEARNT.md that had no test.

Each test here pins a bug that already reached production once. The lesson text
is quoted in the docstring so the intent survives even if the implementation
moves. Keep these cheap and dependency-free - they are the cheapest possible
insurance against re-introducing a known-costly bug.
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# LESSON: "GRN↔SPO link weak matcher" - the import path used a slash-only
# normalizer while the system-wide `_spo_match_key` strips ALL non-alphanumerics.
# `SPO-2026/06-0095` and `SPO-202606-0095` compared UNEQUAL under the weak rule,
# so GRN picking lines were left with `spo_allocation_id` NULL.
# See app/tasks/import_tasks.py:1906 for the in-code warning.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "variant",
    [
        "SPO-202606-0095",
        "SPO-2026/06-0095",
        "SPO-2026.06-0095",
        "SPO 2026 06 0095",
        "spo-2026/06-0095",
        "  SPO-2026/06-0095  ",
    ],
)
def test_spo_match_key_collapses_every_separator_style(variant):
    """All real-world SPO spellings must collapse to ONE key.

    A separator-specific normalizer (e.g. only `/` -> `.`) silently fails to
    match and leaves the allocation unlinked.
    """
    from app.services.procurement_service import _spo_match_key

    assert _spo_match_key(variant) == "SPO2026060095"


def test_spo_match_key_distinguishes_genuinely_different_numbers():
    """Normalization must not over-collapse - different SPOs stay different."""
    from app.services.procurement_service import _spo_match_key

    assert _spo_match_key("SPO-202606-0095") != _spo_match_key("SPO-202606-0096")


@pytest.mark.parametrize("empty", [None, "", "   "])
def test_spo_match_key_empty_never_matches_a_real_spo(empty):
    """Empty input must yield a falsy key, not one that matches a real SPO."""
    from app.services.procurement_service import _spo_match_key

    assert _spo_match_key(empty) == ""
    assert _spo_match_key(empty) != _spo_match_key("SPO-202606-0095")


# ---------------------------------------------------------------------------
# LESSON: "Two SLA systems share `conversation_sla_tracking`, discriminated only
# by `source_entity_type`." Every contact-keyed conversation query MUST apply
# `conversation_tracking_scope()` or it falsely matches a form-SLA row - the
# original bug: an active FORM row alone made n8n's conversation-create 409, and
# thread-assignee lookups could return a form row's assignee.
# ---------------------------------------------------------------------------

def test_conversation_scope_excludes_every_form_sla_type():
    """The scope filter must exclude all FORM_SLA_TYPES, not just some.

    Compiled to SQL and inspected textually so the test does not need a DB and
    cannot be fooled by a filter that merely *looks* right in Python.
    """
    from app.services.form_sla_service import FORM_SLA_TYPES
    from app.services.sla_service import conversation_tracking_scope

    assert FORM_SLA_TYPES, "FORM_SLA_TYPES must not be empty or the scope is a no-op"

    clause = conversation_tracking_scope()
    sql = str(clause.compile(compile_kwargs={"literal_binds": True}))

    for form_type in FORM_SLA_TYPES:
        assert form_type in sql, (
            f"form type {form_type!r} is not excluded by conversation_tracking_scope(); "
            "a contact-keyed conversation query would falsely match this form row"
        )


def test_conversation_scope_admits_null_source_entity_type():
    """n8n-created conversation rows carry a NULL source_entity_type.

    If the filter were a bare NOT IN (...), NULL would evaluate to UNKNOWN and
    every real conversation row would be filtered out.
    """
    from app.services.sla_service import conversation_tracking_scope

    sql = str(
        conversation_tracking_scope().compile(compile_kwargs={"literal_binds": True})
    ).upper()

    assert "IS NULL" in sql, (
        "conversation_tracking_scope() must explicitly admit NULL source_entity_type "
        "or n8n-created conversation rows are excluded"
    )


# ---------------------------------------------------------------------------
# LESSON: "do not read the source-of-truth file at request time if it is not in
# the deployed image" (LESSONS-LEARNT.md, the chatbot allow-list entry). The
# backend image is built from ./sorento_crm_backend alone, so the monorepo's
# sorento_crm_mcp/ is not in it. On 2 Nov 2026 the AI panel's tool pick read the
# MCP catalog from there and every panel data question returned 500
# (FileNotFoundError: '/sorento_crm_mcp/sorento_crm_mcp/catalog.py').
# CI's `validate-backend` job runs this file INSIDE the built image ("Pytest
# regression guards"), the only place the missing directory is real; a lean
# release skips that job and runs it on the full checkout instead, so
# tests/test_mcp_catalog_in_image.py also pins the mechanism directly.
# ---------------------------------------------------------------------------

def test_mcp_tool_catalog_is_readable_from_the_backend_alone():
    """The panel's keyword tool pick and the capability summary build with no monorepo around."""
    from app.services.mcp_tool_capability_service import build_capability_documents, build_live_capability_summary
    from app.services.tool_keyword_rank import rank_tools

    assert len(build_capability_documents(include_planned=False)) > 50
    assert build_live_capability_summary(include_tools=False)["summary"]["total_tools"] > 50
    assert len(rank_tools("stock balance in the warehouse", [], 3)) == 3


# ---------------------------------------------------------------------------
# LESSON 122: "The purchasing email has ONE trigger, the board Confirm" (owner, 6 Nov 2026:
# "I only want the email to purchasing to have 1 trigger, which is this button"; SO398322, an
# AutoCount re-key retired an order inquiry row and auto-emailed purchasing a false cancel).
# The gate: `mark_purchasing_email_trigger` marks the root transaction of a press that may email
# purchasing; the handover drain sends only for a marked one and changed-with-links queues only
# inside one. Owner, 18:10: if any integration / sync path ever emails purchasing again, a test
# must fail. The heavy guards (Postgres) are named below; these two cheap ones keep them, and
# the gate's callers, from quietly going away.
# ---------------------------------------------------------------------------

_BACKEND = __import__("pathlib").Path(__file__).resolve().parents[1]

#: Every place allowed to mark a write as a purchasing email trigger: the board Confirm seam
#: both Confirm routes share, and Publish amendment (the owner's named exception, Q4).
_PURCHASING_TRIGGER_CALLERS = {
    ("app/api/v1/projects/fulfilment_planning.py", "_confirm_with_possible_rejects"),
    ("app/api/v1/projects/sales_orders.py", "publish_amendment"),
}

#: The heavy guards and what each must keep covering.
_PURCHASING_EMAIL_GUARDS = {
    "tests/test_purchasing_email_tripwire_so_po.py": (
        "SO line removed", "SO line added", "SO qty changed", "SO date changed",
        "SO item changed", "SO line re-keyed", "SO header cancelled",
        "test_an_autocount_po_push_removing_a_linked_line_emails_purchasing_nothing",
        "test_an_autocount_po_push_that_reruns_auto_confirm_emails_purchasing_nothing",
        "test_positive_control_the_tripwire_sees_a_confirm_shaped_write",
    ),
    "tests/test_purchasing_email_tripwire_docs.py": (
        "test_an_autocount_cancel_so_document_emails_purchasing_nothing",
        "test_an_autocount_delivery_order_emails_purchasing_nothing",
        "test_an_autocount_goods_received_note_emails_purchasing_nothing",
        "test_positive_control_the_tripwire_sees_a_confirm_shaped_write",
    ),
    "tests/scm/test_purchasing_email_one_trigger.py": (
        "test_structural_a_handover_queued_outside_a_trigger_is_dropped_and_logged",
        "test_the_same_apply_outside_a_trigger_emails_nobody",
    ),
}


def test_only_the_board_confirm_and_publish_amendment_mark_a_purchasing_email_trigger():
    """A new caller of `mark_purchasing_email_trigger` (an ingest, a script, a service) is a
    second trigger of the purchasing email: red until the owner rules it in here."""
    import ast

    found = set()
    for path in sorted((_BACKEND / "app").rglob("*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        parents = {}
        for node in ast.walk(tree):
            for child in ast.iter_child_nodes(node):
                parents[child] = node
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = getattr(func, "id", None) or getattr(func, "attr", None)
            if name != "mark_purchasing_email_trigger":
                continue
            owner = node
            while owner in parents and not isinstance(
                owner, (ast.FunctionDef, ast.AsyncFunctionDef)
            ):
                owner = parents[owner]
            found.add((str(path.relative_to(_BACKEND)), getattr(owner, "name", "<module>")))

    assert found == _PURCHASING_TRIGGER_CALLERS, found


def test_the_purchasing_email_guards_still_cover_every_integration_path():
    """Deleting or thinning the tripwire is red too: each guard file is still there and still
    names every scenario the owner asked for (SO line removed / added / qty / date / item /
    re-keyed, header cancelled, PO line removed, PO auto-confirm, Cancel SO document, DO, GRN),
    with its positive control."""
    for relative, needles in _PURCHASING_EMAIL_GUARDS.items():
        path = _BACKEND / relative
        assert path.exists(), f"{relative} is gone: the purchasing-email regression guard"
        source = path.read_text()
        missing = [needle for needle in needles if needle not in source]
        assert not missing, f"{relative} no longer covers {missing}"
