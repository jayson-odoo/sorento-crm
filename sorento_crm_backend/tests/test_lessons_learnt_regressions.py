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
# LESSON 122: a post-commit side effect opens a fresh `SessionLocal()` with NO
# company scope (UNSET, fail-closed: 0 rows), and conftest's after_begin default
# hides it in tests. OI-ROUTE-BY-RAISER's handover rows read `raised_by`;
# `_queue_saved_line` queued no `raised_by` and the header fallback read it on
# that fresh session, so every saved-line Confirm (qty / date / donor moves)
# emailed nobody on prod for three days (OI-SAVED-LINE-RAISER-HOTFIX, 7 Nov 2026).
# Behaviour: tests/test_oi_saved_line_raiser_route.py.
# ---------------------------------------------------------------------------

def test_saved_line_handover_items_carry_their_raiser_and_the_fallback_reads_unscoped():
    """Both legs of the fix: the item names its raiser, and the fallback never reads scoped."""
    import inspect

    from app.services import project_order_inquiry_service as svc

    queue_src = inspect.getsource(svc.ProjectOrderInquiryService._queue_saved_line)
    assert '"raised_by":' in queue_src, "_queue_saved_line must put raised_by on its item"
    groups_src = inspect.getsource(svc.handover_route_groups)
    assert "company_scope(db, None)" in groups_src, (
        "handover_route_groups' OI-header fallback must read unscoped: its post-commit "
        "session carries no company scope"
    )
