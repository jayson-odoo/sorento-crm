"""Phase 2 RED tests - issue #1262 (Samantha case), slice 2, finding F1c.

Turns T4/T5/T7: the kind-pick label "Sorento (customer)" (never a real `uuid`) gets
copied into a `uuid` field or a `customer_ids` filter at every write/carry seam that
does not check the shape first. The fix is ONE `is_uuid` check re-used at every seam
(plan, slice 2 row): `turn_runtime._spec_row`, `turn_runtime.candidates_by_kind`,
`lanes/business/__init__._outstanding_filters_from`,
`lanes/business/fetch._outstanding_filters_from_ctx`, `turn/apply._settle_question_
subject`, `turn_runtime.outstanding_carry`, and the fetch tool args
(`fetch.entity_ids_transformer`).

AC-S2-1: none of these seams ever writes a non-UUID string into a `uuid` field or a
`customer_ids` filter; a real UUID alongside the label still survives.
AC-S2-2: a session already holding `customer_ids: ["Sorento (customer)"]` on its open
question has the label dropped at read, never reaching `crm_outstanding_report`'s
tool args.
AC-S2-3: partially expressible here - see the module docstring's own note at the
bottom of the file.

Plan: PLAN-chatbot-samantha-slices-26sep.md, slice 2. UAC:
chatbot-samantha-slices-26sep-acceptance-criteria.md.

Postgres-only per repo convention, though none of these seams touch the DB - they are
pure functions/dicts, so no fixture is seeded (nothing here is a DB row).
"""
from __future__ import annotations

# A fixed, `_UUID_RE`-shaped id standing in for the real "Cheng Huat Sentul" customer
# row - these are pure-function tests, so no DB row is actually seeded for it.
CHENG_HUAT_UUID = "b5a1c9de-3f2a-4c1b-9e7d-2a6f8c0d4e5b"
LABEL = "Sorento (customer)"


def test_no_non_uuid_customer_id_reaches_state_or_tool_args():
    """AC-S2-1 (F1c). One test, one seam per assertion block - `_spec_row`,
    `candidates_by_kind`, both `_outstanding_filters_from*`, `_settle_question_
    subject`, the outstanding carry, and the fetch tool args. Each currently lets
    `LABEL` (or the entity carrying it) through unchecked; a real uuid alongside it
    must survive every seam.
    """
    from app.services.chatbot import jsc
    from app.services.chatbot.lanes.business import _outstanding_filters_from
    from app.services.chatbot.lanes.business.fetch import (
        _outstanding_filters_from_ctx,
        entity_has_resolved_uuid,
        entity_ids_transformer,
    )
    from app.services.chatbot.turn.apply import _settle_question_subject
    from app.services.chatbot.turn.pending import Pending
    from app.services.chatbot.turn.state import Focus
    from app.services.chatbot.turn_runtime import _spec_row, candidates_by_kind, outstanding_carry

    # ---- turn_runtime._spec_row -------------------------------------------------
    labeled_entity = {"raw": "Sorento", "hint": "customer", "canonical_code": LABEL}
    row = _spec_row(labeled_entity)
    assert row["uuid"] != LABEL, (
        f"_spec_row promoted the label into `uuid`: {row!r}"
    )

    # ---- turn_runtime.candidates_by_kind ----------------------------------------
    gate: dict = {}
    compatible = [
        {"entity_type": "customer", "code": LABEL},  # no uuid - the label alone
        {"entity_type": "customer", "code": "Cheng Huat Sentul", "uuid": CHENG_HUAT_UUID},
    ]
    grouped = candidates_by_kind(gate, compatible)
    customer_rows = grouped.get("customer") or []
    uuids_seen = [r.get("uuid") for r in customer_rows]
    assert LABEL not in uuids_seen, (
        f"candidates_by_kind promoted `code` into `uuid` with no uuid check: {customer_rows!r}"
    )
    assert CHENG_HUAT_UUID in uuids_seen, "a real uuid alongside the label must still survive"

    # ---- lanes/business/__init__._outstanding_filters_from ----------------------
    entities = [
        {"entity_type": "customer", "uuid": LABEL},
        {"entity_type": "customer", "uuid": CHENG_HUAT_UUID},
    ]
    filters = _outstanding_filters_from(entities, {})
    assert LABEL not in filters["customer_ids"], (
        f"_outstanding_filters_from copied the label straight into customer_ids: {filters!r}"
    )
    assert CHENG_HUAT_UUID in filters["customer_ids"]

    # ---- lanes/business/fetch._outstanding_filters_from_ctx ---------------------
    ctx = {"entities": entities, "semantic_input": {}}
    filters_ctx = _outstanding_filters_from_ctx(ctx)
    assert LABEL not in filters_ctx["customer_ids"], (
        f"_outstanding_filters_from_ctx copied the label straight into customer_ids: {filters_ctx!r}"
    )
    assert CHENG_HUAT_UUID in filters_ctx["customer_ids"]

    # ---- turn/apply._settle_question_subject -------------------------------------
    focus = Focus()
    pending = Pending(
        kind="outstanding_scope",
        expects=None,
        options=[],
        team=None,
        payload={"filters": {"customer_ids": [LABEL, CHENG_HUAT_UUID]}},
        asked_at_turn=None,
    )
    _settle_question_subject(focus, pending, None)
    settled_uuids = [e.get("uuid") for e in focus.customers]
    assert LABEL not in settled_uuids, (
        f"_settle_question_subject wrote the label straight into focus.customers[].uuid: {focus.customers!r}"
    )
    assert CHENG_HUAT_UUID in settled_uuids

    # ---- turn_runtime.outstanding_carry -------------------------------------------
    carry_focus = Focus(customers=[{"uuid": LABEL}, {"uuid": CHENG_HUAT_UUID}])
    out = outstanding_carry({}, carry_focus, {"detail": "so"})
    carried_ids = out.get("outstanding_carried_customer_ids") or []
    assert LABEL not in carried_ids, (
        f"outstanding_carry copied the label into outstanding_carried_customer_ids: {out!r}"
    )
    assert CHENG_HUAT_UUID in carried_ids

    # ---- the fetch tool args (entity_ids_transformer) -----------------------------
    trigger = {
        "tool": "crm_outstanding_report",
        "entities": [],
        "semantic_input": {"outstanding_carried_customer_ids": [LABEL, CHENG_HUAT_UUID]},
    }
    args = entity_ids_transformer(trigger)
    tool_customer_ids = args.get("customer_ids") or []
    assert LABEL not in tool_customer_ids, (
        f"the label reached crm_outstanding_report's own tool args: {args!r}"
    )
    assert CHENG_HUAT_UUID in tool_customer_ids

    # Sanity: the shared uuid check the fix is meant to re-use already exists and
    # already agrees the label is not a uuid (it just is not called at the seams
    # above yet).
    assert entity_has_resolved_uuid({"uuid": LABEL}) is False
    assert entity_has_resolved_uuid({"uuid": CHENG_HUAT_UUID}) is True
    assert jsc  # imported for parity with the seams above, silences unused-import lints


def test_session_already_holding_the_label_is_cleaned_at_read():
    """AC-S2-2. A session's open outstanding question already carries
    `filters.customer_ids: ["Sorento (customer)"]` (T5's own poisoned state, per the
    explainer section 2) - the NEXT turn must never send that string on to
    `crm_outstanding_report`.
    """
    from app.services.chatbot.lanes.business.fetch import entity_ids_transformer

    trigger = {
        "tool": "crm_outstanding_report",
        "entities": [],
        "semantic_input": {"outstanding_carried_customer_ids": [LABEL]},
    }
    args = entity_ids_transformer(trigger)
    assert args.get("customer_ids", []) == [], (
        f"a session-carried label must never reach the tool call: {args!r}"
    )


# AC-S2-3 could not be fully expressed here: "the reply says the customer could not
# be used (or asks which customer) and never prints 'Customer: all'" is rendered by
# `sorento_crm_mcp`'s presenter (`present_response`), a separate package this backend
# explicitly cannot import (see `lanes/business/fetch.py::_outstanding_report_output`'s
# own docstring). The precondition this file CAN pin - that an unusable stored
# customer never reaches the tool call as a live filter - is covered by both tests
# above (`customer_ids` ends up empty, not the label). The "say so" wording itself
# needs either an MCP-side test or a signal threaded back through this backend that
# does not exist yet; flagged to the captain rather than guessed at.
