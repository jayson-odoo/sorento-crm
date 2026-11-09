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

# LESSON 123: "A line matched only by its foreign key reads a re-key as a removal".
# SO398322, 4 Nov 2026: an AutoCount re-save gave line Seq 2552 (118 @ 19.35, nothing else
# changed) a new DtlKey. Ingest matched SO lines only by `source_ref`, so it cancelled the
# old line, retired its order inquiry row, queued the purchasing handover email and created
# a new line + project mirror line with no OI row: the demand of 118 was lost. Fixed by
# AC-REKEY-SAME-LINE (`DocumentIngestService._pair_rekeyed_lines`, PR #2219). Postgres:
# replayed through the real SO ingest route, the shape the ESB sends.
# ---------------------------------------------------------------------------

from .test_ingest_documents import env  # noqa: E402,F401 - pytest fixture, imported for reuse

_SO398322_SEQ = 2552
_SAME_ITEM_OTHER_SEQS = (544, 1328)  # the same item at the same qty and price elsewhere on the SO


def _so398322_line(env, seq, **extra):
    from .test_ingest_documents import _so_line

    values = {"qty_ordered": "118", "unit_price": "19.35", "line_number": seq,
              "warehouse_ref": env.warehouse_ref, "required_date": "2026-12-15",
              "qty_delivered": "0"}
    values.update(extra)
    return _so_line(env, **values)


def _so398322_world(env, **subject_extra):
    """The order as it stood before the re-save: the subject line, two more lines of the
    SAME item at the SAME qty and price on other Seqs, and one other item; adopted, with a
    raised ORDER row on the subject line."""
    from .test_ingest_documents import INGEST_SO, _so_line, _so_record
    from .test_oi_cancelled_line_used_confirm import _mirror_for_ingest_line

    subject = _so398322_line(env, _SO398322_SEQ, **subject_extra)
    twins = [_so398322_line(env, seq) for seq in _SAME_ITEM_OTHER_SEQS]
    other = _so_line(env, product_ref=env.product2_ref, line_number=3000, qty_ordered=5)
    record = _so_record(env, lines=[*twins, subject, other])
    response = env.post(INGEST_SO, [record])
    assert response.status_code == 200, response.text
    header = env.header("sales_orders", record["source_ref"])
    by_ref = {line["source_ref"]: line for line in env.so_lines(header["id"])}
    core = by_ref[subject["source_ref"]]
    mirror, row = _mirror_for_ingest_line(
        env, header["id"], core["id"], core["product_id"], qty="118"
    )
    return record, header, subject, twins, other, core, mirror, str(row.id)


def _resave(env, record, lines):
    from .test_ingest_documents import INGEST_SO

    response = env.post(INGEST_SO, [dict(record, lines=lines)])
    assert response.status_code == 200, response.text
    env.db.expire_all()


def _rekey(line, **changes):
    from .test_ingest_documents import _ref

    return dict(line, source_ref=_ref("SOL"), **changes)


def _outbound_counts(env) -> dict:
    from sqlalchemy import text

    return {
        table: env.db.execute(text(f"SELECT count(*) FROM {table}")).scalar()
        for table in ("automation_runs", "notifications", "notification_deliveries",
                      "email_outbox")
    }


def _capture_every_dispatch(monkeypatch) -> list:
    """Every automation dispatch, whatever its trigger, not only the handover."""
    from app.services.automation_service import AutomationService

    calls: list = []

    def _record(self, trigger_type, *args, **kwargs):
        calls.append(trigger_type)
        return {"trigger_type": trigger_type, "fired": 0, "results": []}

    monkeypatch.setattr(AutomationService, "dispatch_event", _record)
    return calls


def test_lesson_123_an_autocount_rekeyed_so_line_is_the_same_line(env, monkeypatch):
    """Same SO, Seq, item, qty, price, location and delivery date, nothing delivered, new
    DtlKey: the line keeps its row, its project line and its OI row, and nothing is sent."""
    from sqlalchemy import text

    from app.models.project_so import INQUIRY_RAISED, OrderInquiryRow, ProjectSalesOrderLine
    from app.services.project_order_inquiry_service import (
        register_order_inquiry_post_commit_dispatch,
    )

    register_order_inquiry_post_commit_dispatch()
    record, header, subject, twins, other, core, mirror, row_id = _so398322_world(env)
    lines_before = {line["id"] for line in env.so_lines(header["id"])}
    mirrors_before = (
        env.db.query(ProjectSalesOrderLine)
        .filter(ProjectSalesOrderLine.project_sales_order_id == mirror.project_sales_order_id)
        .count()
    )
    outbound_before = _outbound_counts(env)
    dispatched = _capture_every_dispatch(monkeypatch)
    resaved = _rekey(subject)

    _resave(env, record, [*twins, resaved, other])

    lines = {line["id"]: line for line in env.so_lines(header["id"])}
    assert set(lines) == lines_before, "a re-key must not create a line"
    assert lines[core["id"]]["source_ref"] == resaved["source_ref"]
    assert lines[core["id"]]["line_status"] != "cancelled", "the re-keyed line was cancelled"
    for twin in twins:  # the same item at the same qty and price on another Seq is untouched
        assert any(line["source_ref"] == twin["source_ref"] for line in lines.values())
    mirrors_after = (
        env.db.query(ProjectSalesOrderLine)
        .filter(ProjectSalesOrderLine.project_sales_order_id == mirror.project_sales_order_id)
        .count()
    )
    assert mirrors_after == mirrors_before, "a re-key must not create a project line"
    env.db.refresh(mirror)
    assert str(mirror.core_sales_order_line_id) == str(core["id"])
    row = env.db.query(OrderInquiryRow).filter(OrderInquiryRow.id == row_id).one()
    assert row.state == INQUIRY_RAISED, "the order inquiry row was retired"
    assert "Removed in AutoCount" not in (row.note or "")
    retired = env.db.execute(
        text("SELECT count(*) FROM audit_logs WHERE entity_id = :r AND event = 'OI_ROW_CANCELLED'"),
        {"r": row_id},
    ).scalar()
    assert retired == 0
    assert dispatched == [], f"a re-key dispatched automations: {dispatched}"
    assert _outbound_counts(env) == outbound_before, "a re-key queued outbound mail"


def _seed_do_on(env, core):
    from ._sales_report_do_seed import seed_do

    seed_do(
        env.db, customer_id=None, order_date=None, company_id=env.company_a,
        lines=[{"product_id": str(core["product_id"]), "warehouse_id": str(core["warehouse_id"]),
                "qty": 0, "sales_order_line_id": str(core["id"])}],
    )
    env.db.commit()


@pytest.mark.parametrize(
    "case",
    ["old_line_delivered", "do_against_old_line", "different_qty", "different_delivery_date"],
)
def test_lesson_123_guard_cases_stay_a_removal(env, case):
    """The owner's guards (6 Nov): delivered qty, a DO against the old line, a different qty
    or delivery date. The old line is cancelled under its old key and the push's line is a
    new row: never paired."""
    extra = {"qty_delivered": "18"} if case == "old_line_delivered" else {}
    record, header, subject, twins, other, core, mirror, row_id = _so398322_world(env, **extra)
    if case == "do_against_old_line":
        _seed_do_on(env, core)
    changes = {"qty_delivered": "0"}
    if case == "different_qty":
        changes["qty_ordered"] = "117"
    if case == "different_delivery_date":
        changes["required_date"] = "2027-01-15"
    resaved = _rekey(subject, **changes)

    _resave(env, record, [*twins, resaved, other])

    lines = {line["source_ref"]: line for line in env.so_lines(header["id"])}
    old = [line for line in lines.values() if line["id"] == core["id"]][0]
    assert old["source_ref"] == subject["source_ref"], "the old line took the new key"
    assert old["line_status"] == "cancelled"
    assert resaved["source_ref"] in lines, "the push's line was not created as a new row"


# ---------------------------------------------------------------------------
# LESSON 124: "The purchasing email has ONE trigger, the board Confirm" (owner, 6 Nov 2026:
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
    "tests/test_ac_removed_lines_ingest.py": (
        "test_fp_email_one_trigger_s1_a_removed_so_line_emails_purchasing_nothing",
        "test_fp_email_one_trigger_a_removed_lines_open_row_stays_open_until_the_board_confirm",
        "test_fp_email_one_trigger_a_line_dropped_by_a_header_cancel_push_is_still_flagged",
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


@__import__("functools").lru_cache(maxsize=1)
def _app_nodes():
    """(file, enclosing def or class or "<module>", node, enclosing node) for every AST node
    under app/, in one pass (cached: the structural test asks three questions of it)."""
    import ast

    found = []
    scopes = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
    for path in sorted((_BACKEND / "app").rglob("*.py")):
        file = str(path.relative_to(_BACKEND))
        stack = [(ast.parse(path.read_text(), filename=str(path)), None)]
        while stack:
            node, owner = stack.pop()
            found.append((file, getattr(owner, "name", "<module>"), node, owner))
            inner = node if isinstance(node, scopes) else owner
            stack.extend((child, inner) for child in ast.iter_child_nodes(node))
    return tuple(found)


def _calls_named(name_of_call):
    import ast

    return [
        (file, func, node, owner)
        for file, func, node, owner in _app_nodes()
        if isinstance(node, ast.Call)
        and (getattr(node.func, "id", None) or getattr(node.func, "attr", None)) == name_of_call
    ]


def _guarded_by(function, call, test_source):
    """True when a statement directly in `function`'s body, above `call`, is
    `if <test_source>: ... return` (another branch's early return does not count)."""
    import ast

    return any(
        isinstance(node, ast.If)
        and ast.unparse(node.test) == test_source
        and node.body
        and isinstance(node.body[-1], ast.Return)
        and node.lineno < call.lineno
        for node in function.body
    )


_POI = "app/services/project_order_inquiry_service.py"

#: Every place under app/ that may spell a purchasing email's trigger (or the changed-with-links
#: queue key). A literal anywhere else (a new dispatch_event, positional or `trigger_type=`, a
#: module constant fed to a generic drainer) is a new way to email purchasing: red until it is
#: reviewed against the one-trigger rule and listed here.
_PURCHASING_TRIGGER_SPELLINGS = {
    "order_inquiry_handover": {
        ("app/services/automation_triggers.py", "<module>"),  # the trigger registry entry
        ("app/services/oi_handover_resend.py", "<module>"),  # "Send to purchasing" (Q3)
        ("app/services/planning_history_service.py", "_emails"),  # reads past runs only
        (_POI, "handover_route_groups"),  # reads rows to group lines, sends nothing
        (_POI, "send_handover_groups"),  # THE dispatch, called only from the gated drain
        (_POI, "_fire_pending_handover"),  # the gated drain
    },
    "order_inquiry_changed_with_links": {
        ("app/services/automation_triggers.py", "<module>"),
        (_POI, "_fire_pending_changed_with_links"),  # the drain of the gated queue
    },
    "oi_changed_with_links_pending": {(_POI, "<module>")},
}


def test_structural_every_purchasing_dispatch_sits_behind_the_one_gate():
    """LESSON 124, the structural gate, Postgres-free (the heavy twin is
    `tests/scm/test_purchasing_email_one_trigger.py::test_structural_...`). The handover and
    changed-with-links emails leave the app only behind the gate, so a new path that emails
    purchasing without the board Confirm's mark is red here:
    - each trigger is spelled only in the places listed in `_PURCHASING_TRIGGER_SPELLINGS`;
    - `send_handover_groups` has one caller, the post-commit drain `_fire_pending_handover`,
      after `if not was_trigger: return`;
    - the changed-with-links queue is touched only by `_dispatch_changed_with_links` (after
      `if not _may_email_purchasing(self.db): return`), its drain and its rollback discard;
    - `send_match` (sends even with the automation off) only in `oi_handover_resend`, the
      owner's "Send to purchasing" button (Q3 exception).
    Deliberately outside: `order_inquiry_undone`, the board Undo email (owner Q5, kept); it
    only retracts what a board Confirm already sent."""
    import ast

    spelled = {}
    for file, func, node, _ in _app_nodes():
        if isinstance(node, ast.Constant) and node.value in _PURCHASING_TRIGGER_SPELLINGS:
            spelled.setdefault(node.value, set()).add((file, func))
    assert spelled == _PURCHASING_TRIGGER_SPELLINGS, spelled

    senders = _calls_named("send_handover_groups")
    assert [(f, fn) for f, fn, _, _ in senders] == [(_POI, "_fire_pending_handover")], senders
    _, _, call, function = senders[0]
    assert _guarded_by(function, call, "not was_trigger"), (
        "_fire_pending_handover sends the handover without the was_trigger gate"
    )

    queue_users = {}
    for file, func, node, owner in _app_nodes():
        if isinstance(node, ast.Name) and node.id == "_CHANGED_WITH_LINKS_PENDING_KEY":
            queue_users.setdefault((file, func), []).append((node, owner))
    assert set(queue_users) == {
        (_POI, "<module>"),
        (_POI, "_dispatch_changed_with_links"),
        (_POI, "_fire_pending_changed_with_links"),
        (_POI, "_discard_pending_changed_with_links"),
    }, set(queue_users)
    for node, owner in queue_users[(_POI, "_dispatch_changed_with_links")]:
        assert _guarded_by(owner, node, "not _may_email_purchasing(self.db)"), (
            "_dispatch_changed_with_links queues without the purchasing trigger gate"
        )

    manual = {f for f, _, _, _ in _calls_named("send_match")}
    assert manual == {"app/services/oi_handover_resend.py"}, manual
