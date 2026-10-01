"""The standalone one-off (`scripts/oneoff/dedupe_spo_standalone.py`) on the
SPO-2026/08-0074 shape: the owner runs it on production without deploying
#1411, so it must reach the same end state as the in-app repair on its own.

Fixture reused from `tests/test_spo_xlsx_product_fallback.py`: Excel rows 95
(on PL) + 4 (no PL), HQ, no warehouse; GR picks 22 @ IB + 73 @ NTC + 4 @ NTC;
AutoCount lines IB 22 / NTC 77; plus orphan rows for a product AutoCount does
not list (the L23/L26 shape).
"""
from __future__ import annotations

import ast
import pathlib
import uuid

from sqlalchemy import text

from tests.test_spo_xlsx_product_fallback import (
    MARKER,
    OWNER_SPO,
    _orphan_row,
    _owner_case,
    _pl_figures,
    _picked_on,
    _seed_pre_repair_state,
    _spo_rows,
    env,  # noqa: F401 - pytest fixture, imported for reuse
)

__all__ = ["env"]

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "oneoff" / "dedupe_spo_standalone.py"


def _run(env, *, apply: bool, spo=OWNER_SPO):
    from scripts.oneoff import dedupe_spo_standalone as standalone

    lines: list[str] = []
    code = standalone.run(env.db, env.company_a_code, [spo], apply=apply, out=lines.append)
    return code, "\n".join(lines)


def _ids(env):
    return {str(r["id"]) for r in _spo_rows(env, OWNER_SPO)}


class TestStandaloneOwnerCase:
    def test_dry_run_prints_the_full_plan_and_writes_nothing(self, env):
        case = _owner_case(env, number=OWNER_SPO)
        ib, ntc = _seed_pre_repair_state(env, case)
        o23 = _orphan_row(env, case, line=23)
        o26 = _orphan_row(env, case, line=26)
        before = _ids(env)

        code, out = _run(env, apply=False)

        assert code == 0, out
        assert "DRY-RUN (no writes)" in out
        assert f"delete {case.excel_95.id} line 1 (allocated 95, received 95)" in out
        assert f"delete {case.excel_4.id} line 2 (allocated 4, received 4)" in out
        assert f"carry 22 -> {ib.id}" in out
        assert f"carry 77 -> {ntc.id}" in out
        assert f"move pick {case.pick_ib_22.id} (22) {case.excel_95.id} -> {ib.id}" in out
        assert f"move pick {case.pick_ntc_73.id} (73) {case.excel_95.id} -> {ntc.id}" in out
        assert f"move pick {case.pick_ntc_4.id} (4) {case.excel_4.id} -> {ntc.id}" in out
        assert f"orphan delete {o23.id} line 23" in out
        assert f"orphan delete {o26.id} line 26" in out
        assert "superseded 2, orphans removed 2, orphans BLOCKED 0" in out
        assert _ids(env) == before
        assert _picked_on(env, case.excel_95.id) == 95

    def test_apply_reaches_the_follow_autocount_end_state_and_is_idempotent(self, env):
        case = _owner_case(env, number=OWNER_SPO)
        ib, ntc = _seed_pre_repair_state(env, case)
        _orphan_row(env, case, line=23)
        _orphan_row(env, case, line=26)

        code, out = _run(env, apply=True)

        assert code == 0, out
        assert _ids(env) == {str(ib.id), str(ntc.id)}
        assert _picked_on(env, ib.id) == 22
        assert _picked_on(env, ntc.id) == 77
        assert f"packing list to re-open (refreshes its stored status): {case.shipment_id}" in out
        assert _pl_figures(env, case)[:2] == (99, 99)

        code, again = _run(env, apply=False)
        assert code == 0
        assert "no Excel-era rows: already follows AutoCount" in again

    def test_an_orphan_with_a_receipt_or_link_is_blocked(self, env):
        from app.models.scm import OrderLinkClaim

        case = _owner_case(env, number=OWNER_SPO)
        _seed_pre_repair_state(env, case)
        with_receipt = _orphan_row(env, case, line=23, received=5)
        with_claim = _orphan_row(env, case, line=26)
        env.db.add(
            OrderLinkClaim(
                company_id=env.company_a,
                so_number=f"{MARKER}-SO-{uuid.uuid4().hex[:8]}",
                po_number=OWNER_SPO,
                source="autocount",
                spo_allocation_id=with_claim.id,
            )
        )
        env.db.commit()

        code, out = _run(env, apply=True)

        assert code == 0, out
        assert f"ORPHAN-BLOCKED {with_receipt.id} line 23 (allocated 99, received 5; picks 0, claims 0" in out
        assert f"ORPHAN-BLOCKED {with_claim.id} line 26 (allocated 99, received 0; picks 0, claims 1" in out
        assert {str(with_receipt.id), str(with_claim.id)} <= _ids(env)

    def test_a_guard_failure_rolls_the_spo_back(self, env, monkeypatch):
        from scripts.oneoff import dedupe_spo_standalone as standalone

        real = standalone.distribute

        def lossy(total, quantities):
            shares = real(total, quantities)
            shares[-1] = max(shares[-1] - 1, 0)
            return shares

        monkeypatch.setattr(standalone, "distribute", lossy)
        case = _owner_case(env, number=OWNER_SPO)
        _seed_pre_repair_state(env, case)
        before = _ids(env)

        code, out = _run(env, apply=True)

        assert code == 3, out
        assert "ABORTED, rolled back" in out
        assert _ids(env) == before
        assert _picked_on(env, case.excel_95.id) == 95

    def test_company_guard_and_unknown_spo(self, env):
        from scripts.oneoff import dedupe_spo_standalone as standalone

        case = _owner_case(env, number=OWNER_SPO)
        _seed_pre_repair_state(env, case)
        before = _ids(env)
        lines: list[str] = []
        code = standalone.run(env.db, env.company_b_code, [OWNER_SPO], apply=True, out=lines.append)
        assert code == 0
        assert "no AutoCount lines on this SPO" in "\n".join(lines)
        assert _ids(env) == before


class TestStandaloneSafetyRails:
    def test_preflight_passes_on_a_migrated_database(self, env):
        from scripts.oneoff import dedupe_spo_standalone as standalone

        assert standalone.preflight(env.db) == []

    def test_preflight_aborts_on_a_missing_column(self, env, monkeypatch):
        from scripts.oneoff import dedupe_spo_standalone as standalone

        required = dict(standalone.REQUIRED)
        required[("public", "spo_allocations")] = (
            *required[("public", "spo_allocations")],
            "column_from_a_future_migration",
        )
        monkeypatch.setattr(standalone, "REQUIRED", required)
        code, out = _run(env, apply=True)
        assert code == 2
        assert "PREFLIGHT FAILED" in out
        assert "spo_allocations.column_from_a_future_migration is missing" in out

    def test_cli_requires_company_and_spo_and_defaults_to_dry_run(self):
        import pytest

        from scripts.oneoff import dedupe_spo_standalone as standalone

        args = standalone.build_parser().parse_args(
            ["--company", "SRT", "--spo", OWNER_SPO, "--spo", "SPO-2026/09-0001"]
        )
        assert args.spo == [OWNER_SPO, "SPO-2026/09-0001"]
        assert args.apply is False
        with pytest.raises(SystemExit):
            standalone.build_parser().parse_args(["--company", "SRT"])

    def test_imports_nothing_from_the_app(self):
        """Requirement (1): it must run against whatever code the prod container
        holds, so no import of any `app.*` module (every service #1411 changed
        lives there)."""
        tree = ast.parse(SCRIPT.read_text())
        modules = {
            node.module if isinstance(node, ast.ImportFrom) else alias.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in (node.names if isinstance(node, ast.Import) else [None])
        }
        assert not any((m or "").split(".")[0] in {"app", "scripts", "tests"} for m in modules), modules


class TestStandalonePaths:
    def test_claims_move_to_the_first_autocount_line(self, env):
        from app.models.scm import OrderLinkClaim

        case = _owner_case(env, number=OWNER_SPO)
        ib, _ntc = _seed_pre_repair_state(env, case)
        claim = OrderLinkClaim(
            company_id=env.company_a,
            so_number=f"{MARKER}-SO-{uuid.uuid4().hex[:8]}",
            po_number=OWNER_SPO,
            source="autocount",
            spo_allocation_id=case.excel_95.id,
        )
        env.db.add(claim)
        env.db.commit()
        claim_id, excel_id, ib_id = str(claim.id), str(case.excel_95.id), str(ib.id)

        code, out = _run(env, apply=True)

        assert code == 0, out
        assert f"move claim {claim_id} {excel_id} -> {ib_id}" in out
        env.db.expire_all()
        assert str(env.db.get(OrderLinkClaim, claim_id).spo_allocation_id) == ib_id

    def test_a_pick_spanning_two_lines_is_split(self, env):
        case = _owner_case(env, number=OWNER_SPO)
        ib, ntc = _seed_pre_repair_state(env, case)
        case.pick_ib_22.quantity_picked = 30
        case.pick_ib_22.quantity_expected = 32
        case.pick_ntc_73.quantity_picked = 65
        case.pick_ntc_73.quantity_expected = 65
        env.db.commit()
        pick_id, header_id = str(case.pick_ib_22.id), str(case.pick_ib_22.picking_header_id)

        code, out = _run(env, apply=True)

        assert code == 0, out
        assert f"split pick {pick_id} (30): keep 22 on {ib.id}" in out
        assert _picked_on(env, ib.id) == 22
        assert _picked_on(env, ntc.id) == 77
        expected = env.db.execute(
            text(
                "SELECT quantity_picked, quantity_expected FROM picking_lines "
                "WHERE picking_header_id = :h AND source_warehouse_id = :w ORDER BY quantity_picked DESC"
            ),
            {"h": header_id, "w": case.ib_id},
        ).all()
        assert [tuple(r) for r in expected] == [(22, 22), (8, 10)]

    def test_an_excel_row_at_the_same_warehouse_supersedes_whole(self, env):
        case = _owner_case(env, number=OWNER_SPO)
        ib, ntc = _seed_pre_repair_state(env, case)
        # Excel 95 names BRW-NTC itself; AutoCount NTC is 77 - a keyed group the
        # owner's data does not have, checked so the keyed path is covered too.
        case.excel_95.warehouse_id = case.ntc_id
        case.excel_95.allocated_quantity = 77
        case.excel_95.quantity_received = 77
        env.db.commit()
        excel_id = str(case.excel_95.id)

        code, out = _run(env, apply=True)

        assert code == 0, out
        assert "group same destination: 1 Excel row(s) -> 1 AutoCount line(s)" in out
        assert excel_id not in _ids(env)
