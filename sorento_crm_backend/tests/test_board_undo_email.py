"""S3 (#980) - the "Order inquiry undone" email.

RED for Phase 2 of `documentation/plans/scm/PLAN-board-undo-last-confirm.md`, "The email".
Nothing in this file has an implementation yet:

* `order_inquiry_undone` is not in the trigger catalog - `automation_triggers.list_specs()`
  has no entry for it, and `automation_triggers.fire(db, "order_inquiry_undone", ...)` raises
  `ValueError: Unknown trigger type`.
* `undo_last_confirm` does not record anything for the drain to fire - the "one dispatch"
  tests capture zero calls where they expect exactly one, which is this file's other "right
  reason" until the recorder and the third post-commit triple exist.
* No alembic migration under `alembic/versions/` seeds `email_templates.code =
  'order_inquiry_undone_default'` / `automations.trigger_type = 'order_inquiry_undone'` yet -
  `_load_undo_seed_migration()` asserts a discovery failure by name.

Two harnesses, matching `tests/test_order_inquiry_handover_automation.py`'s own split:

* the RECORDER/DRAIN/DISPATCH contract (AC-UC-32/AC-UC-33) reuses the S2 seed helpers from
  `tests/test_board_undo_last_confirm.py` (imported, not duplicated) - the `api` fixture off
  `tests/test_so_supply_confirmation.py`'s blank scratch schema, and
  `AutomationService.dispatch_event` monkeypatched exactly the way the handover suite's own
  `_captured_dispatches` does, for the same reason: the drain's fresh `SessionLocal()` is a
  genuinely separate connection that cannot see this suite's own rolled-back savepoint;
* the TRIGGER CATALOG (AC-UC-35) and SEED MIGRATION + TEMPLATE (AC-UC-34) need no confirm
  chain at all, and use `tests/_pg_fixture.py`'s `blank_session()` directly - the same split,
  and largely the same code, `test_order_inquiry_handover_automation.py` uses for
  `test_trigger_in_catalog` / `test_seed_migration_idempotent` /
  `test_seed_migration_downgrade_removes_both`.
"""
from __future__ import annotations

import importlib.util
import json
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.models.project_so import (
    INQUIRY_PLACED,
    IV_ORDER,
    OrderInquiryLink,
    OrderInquiryRow,
    SOSupplyDecision,
)
from app.services.error_handler import AppException

from ._pg_fixture import blank_session
from .test_board_undo_last_confirm import (  # noqa: F401  (api is a fixture)
    BASE,
    _core_line,
    _core_so,
    _line_payload,
    _link_with_claim,
    _po_line,
    _project_line,
    _project_so,
    _stock,
    _uid,
    api,
)

MARKER = "zzt-undo-email"
TRIGGER = "order_inquiry_undone"


# --------------------------------------------------------------------------- #
# shared harness (mirrors test_order_inquiry_handover_automation.py)          #
# --------------------------------------------------------------------------- #


def _captured_dispatches(monkeypatch) -> list[dict]:
    """Intercepts `AutomationService.dispatch_event` on the drain's fresh session."""
    calls: list[dict] = []

    def _fake_dispatch(self, trigger_type, *, context, source_kind, source_id):
        calls.append(
            {
                "trigger_type": trigger_type,
                "context": context,
                "source_kind": source_kind,
                "source_id": source_id,
            }
        )
        return {"trigger_type": trigger_type, "fired": 0, "results": []}

    monkeypatch.setattr(
        "app.services.automation_service.AutomationService.dispatch_event",
        _fake_dispatch,
    )
    return calls


def _register() -> None:
    """Idempotent (module-global flag), same call site the handover suite uses -
    `TestClient(app)` without `with` never runs FastAPI's lifespan here."""
    from app.services.project_order_inquiry_service import (
        register_order_inquiry_post_commit_dispatch,
    )

    register_order_inquiry_post_commit_dispatch()


def _undo_calls(calls: list[dict]) -> list[dict]:
    return [c for c in calls if c["trigger_type"] == TRIGGER]


def _seed_undo_world(api):
    """Two lines, twice confirmed: rev1 raises+auto-links line1 (standing in for the
    raise-time cascade, the same trick `test_board_undo_last_confirm.py` uses), rev2 (the
    revision the tests below undo) settles line1 in place (qty 20 -> 15, so the undo's
    context has a "back to 20" line) and freshly Buys line2 (a brand new raised row, so the
    undo's context also has a "removed" line).
    """
    client, world = api
    db = world.db
    _stock(db, world.product, world.pool_wh, on_hand=200)
    core_so = _core_so(db, world.company_id)
    core_line_1 = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="20")
    core_line_2 = _core_line(db, core_so, world.product, world.own_wh, qty_ordered="10")
    order = _project_so(db, world.project, so_id=core_so.id)
    # `_handover_order_facts`-style resolution (this trigger's own method, "copied not
    # adapted") reads `autocount_doc_no or provisional_ref` - an adopted order carries the
    # former, and without it here `so_number` would resolve to the mirror's own
    # `ZZT-PSO-...` ref rather than the core SO's `ZZT-CORE-...` number this test expects.
    order.autocount_doc_no = core_so.so_number
    db.flush()
    line_1 = _project_line(db, order, line_no=10, product=world.product, core_line=core_line_1)
    line_2 = _project_line(db, order, line_no=20, product=world.product, core_line=core_line_2)
    db.commit()

    first = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={"lines": [_line_payload(line_1.id, buy_qty="20")]},
    )
    assert first.status_code == 200, first.text
    decision1 = (
        db.query(SOSupplyDecision)
        .filter(SOSupplyDecision.project_sales_order_id == order.id)
        .one()
    )
    row_1 = (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.so_line_id == line_1.id, OrderInquiryRow.verb == IV_ORDER)
        .one()
    )
    po, po_line = _po_line(db, world, qty=20)
    _link_with_claim(db, world, row_1, po_line, qty=20, so_number=core_so.so_number)
    row_1.state = INQUIRY_PLACED
    db.commit()

    second = client.post(
        f"{BASE}/sales-orders/{order.id}/confirm",
        json={
            "lines": [
                _line_payload(
                    line_1.id, buy_qty="15",
                    reserve=[{"warehouse_id": world.pool_wh.id, "qty": "5"}],
                ),
                _line_payload(line_2.id, buy_qty="10"),
            ]
        },
    )
    assert second.status_code == 200, second.text
    decision2 = (
        db.query(SOSupplyDecision)
        .filter(
            SOSupplyDecision.project_sales_order_id == order.id,
            SOSupplyDecision.revision_no == 2,
        )
        .one()
    )
    row_2 = (
        db.query(OrderInquiryRow)
        .filter(OrderInquiryRow.so_line_id == line_2.id, OrderInquiryRow.verb == IV_ORDER)
        .one()
    )
    return {
        "client": client, "world": world, "db": db, "order": order, "core_so": core_so,
        "decision1": decision1, "decision2": decision2, "row_1": row_1, "row_2": row_2,
    }


# --------------------------------------------------------------------------- AC-UC-32


def test_an_undo_dispatches_one_undone_event_after_commit_with_the_lines(api, monkeypatch):
    _register()
    calls = _captured_dispatches(monkeypatch)
    fixture = _seed_undo_world(api)
    db = fixture["db"]
    order = fixture["order"]
    world = fixture["world"]
    # Captured BEFORE the undo: it deletes this exact row by design (AC-UC-16/17/29), and
    # `expire_on_commit` would otherwise SELECT a row that is already gone the moment
    # either attribute is touched after `db.commit()` below (`ObjectDeletedError`).
    expected_source_id = str(fixture["decision2"].id)
    expected_revision_no = fixture["decision2"].revision_no
    # Same reason: `row_1` does not survive the undo either, so its own `order_inquiry_id`
    # (the header this fixture's rows share - one header per SO) is read now too.
    expected_header_id = str(fixture["row_1"].order_inquiry_id)

    from app.services.project_supply_undo_service import undo_last_confirm

    undo_last_confirm(db, order, actor_user_id=world.eling)
    assert _undo_calls(calls) == [], "nothing may dispatch before the write commits"

    db.commit()

    matches = _undo_calls(calls)
    assert len(matches) == 1, "exactly one dispatch per undo"
    call = matches[0]
    assert call["source_kind"] == TRIGGER
    assert call["source_id"] == expected_source_id

    ctx = call["context"]
    assert set(ctx.keys()) >= {"undo", "actor", "today"}
    undo_ctx = ctx["undo"]
    for key in ("so_number", "customer", "project", "revision_no", "lines", "link"):
        assert key in undo_ctx, key
    assert undo_ctx["so_number"] == fixture["core_so"].so_number
    assert undo_ctx["revision_no"] == expected_revision_no

    from app.services.automation_triggers import build_order_inquiry_link

    # `build_order_inquiry_link` now takes the HEADER id, not the SO number (S3,
    # `PLAN-oi-header-list-detail.md`, AC-LK-01) - a self-comparison against the same call
    # cannot catch a wrong id being passed in, so also assert the real shape.
    assert undo_ctx["link"] == build_order_inquiry_link(expected_header_id)
    assert undo_ctx["link"].endswith(
        f"/project-sales/order-inquiries/{expected_header_id}"
    )
    assert ctx["today"] == date.today().strftime("%d/%m/%Y")

    lines = undo_ctx["lines"]
    for line in lines:
        for key in ("item_code", "qty", "delivery_date", "outcome"):
            assert key in line, key

    removed = [entry for entry in lines if entry["outcome"] == "removed"]
    assert len(removed) == 1, "line2's freshly-raised row is gone - outcome 'removed'"
    assert removed[0]["item_code"] == world.product.product_code
    assert removed[0]["qty"] == "10"

    back_to = [entry for entry in lines if entry["outcome"].startswith("back to")]
    assert len(back_to) == 1, "line1's row existed before the undone confirm"
    assert "20" in back_to[0]["outcome"]
    assert back_to[0]["qty"] == "20"


# --------------------------------------------------------------------------- AC-UC-33


@pytest.mark.parametrize("arm", ["refused_manual_link", "rolled_back"])
def test_a_refused_or_rolled_back_undo_dispatches_nothing(api, monkeypatch, arm):
    _register()
    calls = _captured_dispatches(monkeypatch)
    fixture = _seed_undo_world(api)
    db = fixture["db"]
    order = fixture["order"]
    world = fixture["world"]

    from app.services.project_supply_undo_service import undo_last_confirm

    if arm == "refused_manual_link":
        po, po_line = _po_line(db, world, qty=5)
        db.add(
            OrderInquiryLink(
                id=_uid(), company_id=world.company_id, row_id=fixture["row_2"].id,
                po_line_id=po_line.id, document=po.po_number, qty=Decimal("5"),
                linked_by=world.eling, auto=False,
                linked_at=fixture["decision2"].confirmed_at + timedelta(minutes=1),
            )
        )
        db.commit()
        with pytest.raises(AppException):
            undo_last_confirm(db, order, actor_user_id=world.eling)
        db.commit()
    else:
        savepoint = db.begin_nested()
        undo_last_confirm(db, order, actor_user_id=world.eling)
        savepoint.rollback()
        db.commit()  # an unrelated commit: nothing rolled back above may still fire

    assert _undo_calls(calls) == [], f"arm={arm!r} must dispatch nothing"


# --------------------------------------------------------------------------- AC-UC-34


def _find_undo_seed_migration_path() -> Path | None:
    """Locate the coder's seed migration by its OWN revision id, not by content-
    sniffing its body for the template code and trigger type - `oihr_0002_undone_
    headline.py` (the follow-up migration in this same file that teaches this exact
    template its RECONSTRUCTED distinction) contains BOTH `order_inquiry_undone_
    default` and `order_inquiry_undone` too, so the old sniff matched two files and
    returned whichever one `Path.glob` happened to yield first - unsorted, OS- and
    filesystem-dependent order. CI shard 1 (run 35279796069) returned `oihr_0002`
    first, so this "seed" migration actually ran the HEADLINE body: it seeded a
    template with the RECONSTRUCTED branch already in it and no automation row at
    all, failing this file's own sanity assertion and `assert 0 == 1` on the
    automation count - while a local run, whose glob order happened to return
    `undo_0002_seed_undone_automation.py` first, saw none of it. The revision id
    (`revision = "undo_0002_seed_undone"`) is the ONE thing that is unique to this
    file and never shared with a migration that extends it later."""
    versions_dir = Path(__file__).resolve().parents[1] / "alembic" / "versions"
    matches = [
        path
        for path in versions_dir.glob("*.py")
        if _file_declares_revision(path, "undo_0002_seed_undone")
    ]
    assert len(matches) <= 1, (
        "more than one alembic migration under alembic/versions/ declares "
        f"revision = \"undo_0002_seed_undone\": {[p.name for p in matches]}"
    )
    return matches[0] if matches else None


def _file_declares_revision(path: Path, revision_id: str) -> bool:
    """Whether THIS file is the migration whose own `revision` equals `revision_id` -
    a bare `revision = "..."` LINE (module scope, no leading whitespace), never
    `down_revision = "..."`: that variable name ends in the very same substring
    (`revision = "..."`), so a plain `in text` check over the whole file matches a
    CHILD migration naming this one as its parent too, which is exactly how the
    first version of this fix over-matched `undo_0003_journal_sql_null.py` (its own
    `down_revision = "undo_0002_seed_undone"`) alongside the real seed file."""
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return False
    target = f'revision = "{revision_id}"'
    return any(line.strip() == target for line in lines)


def _load_undo_seed_migration():
    path = _find_undo_seed_migration_path()
    assert path is not None, (
        "no alembic migration seeding email_templates.code="
        "'order_inquiry_undone_default' / automations.trigger_type="
        "'order_inquiry_undone' was found under alembic/versions/ - the coder must add it "
        "(PLAN-board-undo-last-confirm.md 'The email', AC-UC-34)."
    )
    spec = importlib.util.spec_from_file_location("zzt_undo_seed_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_upgrade(module, db) -> None:
    ctx = MigrationContext.configure(db.connection())
    with Operations.context(ctx):
        module.upgrade()


def _run_downgrade(module, db) -> None:
    ctx = MigrationContext.configure(db.connection())
    with Operations.context(ctx):
        module.downgrade()


def test_the_migration_seeds_an_enabled_automation_and_template_once():
    module = _load_undo_seed_migration()
    with blank_session() as db:
        _run_upgrade(module, db)
        _run_upgrade(module, db)  # idempotent re-run: no duplicates, never an update

        templates = db.execute(
            sa.text(
                "SELECT count(*) FROM email_templates WHERE code = "
                "'order_inquiry_undone_default'"
            )
        ).scalar()
        assert templates == 1

        rows = db.execute(
            sa.text(
                "SELECT enabled, trigger_type, action_type, recipient_config FROM "
                "automations WHERE trigger_type = 'order_inquiry_undone' "
                "AND name = 'Order inquiry undone'"
            )
        ).fetchall()
        assert len(rows) == 1
        enabled, trigger_type, action_type, recipient_config = rows[0]
        assert enabled is True
        assert trigger_type == "order_inquiry_undone"
        assert action_type == "send_email"
        cfg = (
            recipient_config
            if isinstance(recipient_config, dict)
            else json.loads(recipient_config)
        )
        # No handover automation row exists in this blank schema, so the "copied from the
        # handover row when present" branch falls to its own default - the same shape
        # `oihe_0001_seed_handover_automation.py` seeds when no purchasing role exists.
        assert cfg.get("include_actor") is True
        assert cfg.get("one_email") is True
        assert cfg.get("user_ids") == []
        assert cfg.get("extra_emails") == []
        assert cfg.get("role_ids") == []

        _run_downgrade(module, db)

        templates_after = db.execute(
            sa.text(
                "SELECT count(*) FROM email_templates WHERE code = "
                "'order_inquiry_undone_default'"
            )
        ).scalar()
        assert templates_after == 0
        automations_after = db.execute(
            sa.text(
                "SELECT count(*) FROM automations WHERE trigger_type = 'order_inquiry_undone'"
            )
        ).scalar()
        assert automations_after == 0


# --------------------------------------------------------------------------- B3 (review
# round 1): oihr_0002_undone_headline, the follow-up migration that teaches the ALREADY-
# seeded template the RECONSTRUCTED distinction. Kept in THIS file, next to the seed
# migration's own test above, rather than in test_board_undo_reconstructed.py where it
# was originally written - both tests write the SAME `email_templates` row
# (code='order_inquiry_undone_default'), and under CI's `pytest-xdist --dist loadfile`
# a different file can land on a different worker against the SAME database, so two
# files racing to upgrade/downgrade one shared row is a real flake (CI run
# 35276083512, PR #1001) even though every test here passes serially. One file, one
# worker, one lock on the row - the fix is proximity, not a synchronisation primitive.


def _find_undone_headline_migration_path() -> Path | None:
    """Locate the coder's migration that teaches the already-seeded
    `order_inquiry_undone_default` template to print the RECONSTRUCTED headline
    distinctly (B3, review round 1) - by its OWN revision id, the same fix
    `_find_undo_seed_migration_path` above needed: a content sniff over this
    migration's own body text is exactly the same class of hazard even though this
    particular pair of strings does not collide with `undo_0002_seed_undone_
    automation.py` TODAY - the next migration that touches this template and
    happens to mention RECONSTRUCTED (a downgrade note, a comment) would collide
    silently, and CI's own glob order is not something to depend on either way."""
    versions_dir = Path(__file__).resolve().parents[1] / "alembic" / "versions"
    matches = [
        path
        for path in versions_dir.glob("*.py")
        if _file_declares_revision(path, "oihr_0002_undone_headline")
    ]
    assert len(matches) <= 1, (
        "more than one alembic migration under alembic/versions/ declares "
        f"revision = \"oihr_0002_undone_headline\": {[p.name for p in matches]}"
    )
    return matches[0] if matches else None


def _load_undone_headline_migration():
    path = _find_undone_headline_migration_path()
    assert path is not None, (
        "no alembic migration teaching order_inquiry_undone_default to print the "
        "RECONSTRUCTED headline was found under alembic/versions/ - the coder must "
        "add one (review round 1, B3, PLAN-scm-oi-handover-r2-undo.md S5, AC-R2-31h)."
    )
    spec = importlib.util.spec_from_file_location("zzt_undone_headline_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_undone_headline_migration_updates_template_idempotently_and_downgrades():
    """B3 (review round 1): the migration that teaches `order_inquiry_undone_default`
    the RECONSTRUCTED distinction updates the template IN PLACE, idempotently, and
    downgrade restores the pre-headline body verbatim - the same contract
    `test_r2_migration_updates_template_in_place_and_is_idempotent`
    (`test_order_inquiry_handover_automation.py`) pins for the handover template."""
    undo_seed = _load_undo_seed_migration()
    headline_migration = _load_undone_headline_migration()

    with blank_session() as db:
        _run_upgrade(undo_seed, db)
        original_body = db.execute(
            sa.text(
                "SELECT body_html FROM email_templates WHERE code = "
                "'order_inquiry_undone_default'"
            )
        ).scalar()
        assert "RECONSTRUCTED" not in original_body, (
            "sanity: the seeded undo_0002 body has no headline branch yet"
        )

        _run_upgrade(headline_migration, db)
        row = db.execute(
            sa.text(
                "SELECT subject, body_html, body_text FROM email_templates WHERE code = "
                "'order_inquiry_undone_default'"
            )
        ).mappings().one()
        rendered_text = (row["subject"] or "") + (row["body_html"] or "") + (row["body_text"] or "")
        assert "RECONSTRUCTED" in rendered_text, (
            "the migration must teach the template the RECONSTRUCTED word somewhere"
        )
        count = db.execute(
            sa.text(
                "SELECT count(*) FROM email_templates WHERE code = "
                "'order_inquiry_undone_default'"
            )
        ).scalar()
        assert count == 1

        # Idempotent re-run.
        _run_upgrade(headline_migration, db)
        row_again = db.execute(
            sa.text(
                "SELECT body_html FROM email_templates WHERE code = "
                "'order_inquiry_undone_default'"
            )
        ).scalar()
        assert row_again == row["body_html"]

        # Downgrade restores the pre-headline body verbatim.
        _run_downgrade(headline_migration, db)
        restored = db.execute(
            sa.text(
                "SELECT body_html FROM email_templates WHERE code = "
                "'order_inquiry_undone_default'"
            )
        ).scalar()
        assert restored == original_body


# --------------------------------------------------------------------------- AC-UC-35


def test_the_undone_trigger_is_in_the_catalog():
    from app.services import automation_triggers

    spec = next(
        (s for s in automation_triggers.list_specs() if s.type == TRIGGER),
        None,
    )
    assert spec is not None, f"{TRIGGER!r} must be registered in the trigger catalog"
    assert spec.label == "Order inquiry undone"
    assert spec.config_schema == {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }

    with blank_session() as db:
        matches = automation_triggers.fire(db, TRIGGER, {}, "Asia/Kuala_Lumpur")
    assert matches == [], "pull-mode evaluation yields nothing - this trigger is event-driven"


# --------------------------------------------------------------------------- review round: the undone email never leaks a donor's rows (contract I)


def test_the_undone_email_lists_only_this_orders_rows(api, monkeypatch):
    """Contract I (review round): the undone email must list only the UNDONE order's own
    rows, never a donor's - a cross-project borrow's journal also carries the donor's own
    decision entries (`test_board_undo_journal.py`'s AC-UC-12 test proves this), and
    `retire_supply_borrow_rows` can touch the donor's own OI rows too when the borrowed
    line carried a step-3 placement. `_undo_email_lines` today filters the journal by
    table alone, with no per-pso check, so a donor row entry sitting in the SAME journal
    would leak into the borrower's own undo email.

    The donor side is injected directly onto the real journal the confirm wrote (a real
    donor project/order/OI row exists in the database; only the JOURNAL ENTRY naming it
    is fabricated) rather than reproducing the rare step-3-covered-donor-borrow shape
    end to end - the contract is the FILTER `_undo_email_lines` must apply, and it reads
    the same journal shape regardless of which caller produced the entry.
    """
    _register()
    calls = _captured_dispatches(monkeypatch)
    fixture = _seed_undo_world(api)
    db = fixture["db"]
    order = fixture["order"]
    world = fixture["world"]

    from app.models.project_so import IV_ORDER, OrderInquiry
    from app.services.project_service import register_project

    donor_project = register_project(
        db, company_id=world.company_id, actor_user_id=world.eling, developer_party_id=None,
        title=f"{MARKER} Donor Email Leak Check",
    )
    donor_core_so = _core_so(db, world.company_id)
    donor_core_line = _core_line(
        db, donor_core_so, world.product, world.own_wh, qty_ordered="9"
    )
    donor_pso = _project_so(db, donor_project, so_id=donor_core_so.id)
    donor_line = _project_line(
        db, donor_pso, line_no=10, product=world.product, core_line=donor_core_line
    )
    donor_inquiry = OrderInquiry(
        id=_uid(), company_id=world.company_id, project_sales_order_id=donor_pso.id,
        state="raised", inquiry_no=f"ZZT-OI-{_uid()[:8]}",
    )
    db.add(donor_inquiry)
    db.flush()
    donor_row = OrderInquiryRow(
        id=_uid(), company_id=world.company_id, order_inquiry_id=donor_inquiry.id,
        so_line_id=donor_line.id, item_code="ZZT-DONOR-ONLY", qty=Decimal("9"),
        delivery_date=date.today(), verb=IV_ORDER, state="cancelled",
    )
    db.add(donor_row)
    db.commit()

    db.expire_all()
    decision2 = (
        db.query(SOSupplyDecision).filter(SOSupplyDecision.id == fixture["decision2"].id).one()
    )
    journal = list(decision2.undo_journal)
    journal.append(
        {
            "seq": 999, "op": "update", "table": "projects.order_inquiry_rows",
            "pk": str(donor_row.id),
            "old": {"qty": "9", "delivery_date": date.today().isoformat(), "state": "raised"},
        }
    )
    decision2.undo_journal = journal
    db.commit()

    from app.services.project_supply_undo_service import undo_last_confirm

    undo_last_confirm(db, order, actor_user_id=world.eling)
    db.commit()

    matches = _undo_calls(calls)
    assert len(matches) == 1
    lines = matches[0]["context"]["undo"]["lines"]
    item_codes = {line["item_code"] for line in lines}
    assert "ZZT-DONOR-ONLY" not in item_codes, (
        "the donor's own row must never appear in the undone order's email"
    )
    assert item_codes, "the undone order's OWN rows must still be listed"
