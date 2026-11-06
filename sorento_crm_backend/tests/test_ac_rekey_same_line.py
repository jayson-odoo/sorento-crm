"""AC-REKEY-SAME-LINE, red tests: an AutoCount re-keyed SO line is the SAME line.

Card: documentation/plans/scm/ac-rekey-same-line-behaviour-card.md (rules K1-K5).

An AutoCount re-save can give an unchanged SO line a new DtlKey. The push then drops the old
`source_ref` and carries a new one with the same Seq (`line_number`), item, qty, price and
location. Today `_sync_lines` reads that as "line removed" + "line created": the old core line is
cancelled, its Order Inquiry rows are retired, the purchasing handover is queued, and the new
line gets a fresh project mirror line with no OI row. After: the old row is re-keyed in place.

Every test pushes a two-line AutoCount SO (x is re-keyed or removed, y stays), seeds the adopted
project mirror + an OI row on x (`_mirror_for_ingest_line`), then pushes again. Postgres only;
every test seeds its own chain; no real customer data.
"""
from __future__ import annotations

from sqlalchemy import text

from app.models.project_so import (
    INQUIRY_CANCELLED,
    INQUIRY_RAISED,
    ProjectSalesOrderLine,
)

from .test_ac_removed_lines_ingest import _row_snapshot
from .test_ingest_documents import (
    INGEST_SO,
    _ref,
    _so_line,
    _so_record,
    env,  # noqa: F401 - pytest fixture, imported for reuse
)
from .test_oi_cancelled_line_used_confirm import _mirror_for_ingest_line
from .test_order_inquiry_handover_automation import (
    _captured_dispatches,
    _handover_calls,
    _register,
)

__all__ = ["env"]

SEQ_X = 2552
SEQ_Y = 544


def _line(env, *, seq, product_ref=None, qty="118", price="19.35", **extra) -> dict:
    return _so_line(
        env,
        product_ref=product_ref,
        qty_ordered=qty,
        unit_price=price,
        line_number=seq,
        warehouse_ref=env.warehouse_ref,
        **extra,
    )


def _world(env):
    """Push x + y, then seed the adopted mirror and one raised OI row on x."""
    x = _line(env, seq=SEQ_X)
    y = _line(env, seq=SEQ_Y, product_ref=env.product2_ref)
    record = _so_record(env, lines=[x, y])
    res = env.post(INGEST_SO, [record])
    assert res.status_code == 200, res.text
    header = env.header("sales_orders", record["source_ref"])
    line_x = {l["source_ref"]: l for l in env.so_lines(header["id"])}[x["source_ref"]]
    mirror, row = _mirror_for_ingest_line(
        env, header["id"], line_x["id"], line_x["product_id"], qty="118",
        row_state=INQUIRY_RAISED,
    )
    return record, header, x, y, line_x, mirror, str(row.id)


def _repush(env, record, lines):
    res = env.post(INGEST_SO, [dict(record, lines=lines)])
    assert res.status_code == 200, res.text
    env.db.expire_all()


def _core(env, line_id) -> dict:
    return dict(
        env.db.execute(
            text(
                "SELECT id, source_ref, line_status, qty_ordered, line_no, removed_unreferenced"
                " FROM sales_order_lines WHERE id = :i"
            ),
            {"i": str(line_id)},
        ).mappings().one()
    )


def _mirror_count(env, pso_id) -> int:
    return (
        env.db.query(ProjectSalesOrderLine)
        .filter(ProjectSalesOrderLine.project_sales_order_id == str(pso_id))
        .count()
    )


def _rekeyed(x: dict, **changes) -> dict:
    """x as AutoCount sends it after a re-save: a NEW DtlKey, everything else as given."""
    return dict(x, source_ref=_ref("SOL"), **changes)


# ===================================================================== the re-key (K1, K3, K5)
def test_a_rekeyed_line_keeps_its_core_row_and_takes_the_new_key(env):
    record, header, x, y, line_x, mirror, row_id = _world(env)
    new_x = _rekeyed(x)

    _repush(env, record, [new_x, y])

    lines = env.so_lines(header["id"])
    assert len(lines) == 2, lines  # no extra row created
    core = _core(env, line_x["id"])
    assert core["source_ref"] == new_x["source_ref"]
    assert core["line_status"] != "cancelled", core
    assert core["line_no"] == SEQ_X
    assert not core["removed_unreferenced"]


def test_a_rekeyed_line_keeps_its_order_inquiry_row_live(env):
    record, header, x, y, line_x, mirror, row_id = _world(env)

    _repush(env, record, [_rekeyed(x), y])

    snap = _row_snapshot(env, row_id)
    assert snap["state"] == INQUIRY_RAISED, snap
    assert "Removed in AutoCount" not in (snap["note"] or ""), snap


def test_a_rekeyed_line_queues_no_handover(env, monkeypatch):
    record, header, x, y, line_x, mirror, row_id = _world(env)
    _register(None)
    calls = _captured_dispatches(monkeypatch)

    _repush(env, record, [_rekeyed(x), y])

    assert _handover_calls(calls) == [], [c["trigger_type"] for c in calls]


def test_a_rekeyed_line_creates_no_new_project_line(env):
    record, header, x, y, line_x, mirror, row_id = _world(env)
    before = _mirror_count(env, mirror.project_sales_order_id)

    _repush(env, record, [_rekeyed(x), y])

    assert _mirror_count(env, mirror.project_sales_order_id) == before
    env.db.refresh(mirror)
    assert str(mirror.core_sales_order_line_id) == str(line_x["id"])


def test_a_rekeyed_line_takes_non_key_changes_like_any_update(env):
    """K3: delivered qty / required date are not part of the key."""
    record, header, x, y, line_x, mirror, row_id = _world(env)

    _repush(env, record, [_rekeyed(x, qty_delivered="18", required_date="2027-02-01"), y])

    got = env.db.execute(
        text("SELECT qty_delivered, required_date FROM sales_order_lines WHERE id = :i"),
        {"i": str(line_x["id"])},
    ).mappings().one()
    assert float(got["qty_delivered"]) == 18
    assert str(got["required_date"]) == "2027-02-01"
    assert len(env.so_lines(header["id"])) == 2


# ============================================================ not a re-key: today's behaviour
def _assert_removed(env, header, line_x, row_id, expected_lines=3):
    core = _core(env, line_x["id"])
    assert core["line_status"] == "cancelled", core
    assert core["source_ref"] == line_x["source_ref"]
    assert _row_snapshot(env, row_id)["state"] == INQUIRY_CANCELLED
    assert len(env.so_lines(header["id"])) == expected_lines


def test_a_genuine_removal_still_retires_and_hands_over(env, monkeypatch):
    record, header, x, y, line_x, mirror, row_id = _world(env)
    _register(None)
    calls = _captured_dispatches(monkeypatch)

    _repush(env, record, [y])

    _assert_removed(env, header, line_x, row_id, expected_lines=2)
    assert len(_handover_calls(calls)) == 1


def test_a_different_seq_is_not_a_rekey(env):
    """Q2: near misses with a different Seq are real restructures."""
    record, header, x, y, line_x, mirror, row_id = _world(env)

    _repush(env, record, [_rekeyed(x, line_number=SEQ_X + 8), y])

    _assert_removed(env, header, line_x, row_id)


def test_a_different_qty_is_not_a_rekey(env):
    """Q1 (b): near misses with a different qty are real restructures."""
    record, header, x, y, line_x, mirror, row_id = _world(env)

    _repush(env, record, [_rekeyed(x, qty_ordered="117"), y])

    _assert_removed(env, header, line_x, row_id)


def test_a_different_price_is_not_a_rekey(env):
    record, header, x, y, line_x, mirror, row_id = _world(env)

    _repush(env, record, [_rekeyed(x, unit_price="19.40"), y])

    _assert_removed(env, header, line_x, row_id)


def test_a_different_item_is_not_a_rekey(env):
    """An item swap on the same Seq is a real replacement."""
    record, header, x, y, line_x, mirror, row_id = _world(env)

    swap = _line(env, seq=SEQ_X, product_ref=env.product2_ref)  # its own ref and item code
    _repush(env, record, [swap, y])

    _assert_removed(env, header, line_x, row_id)


def test_a_new_line_without_seq_is_not_a_rekey(env):
    record, header, x, y, line_x, mirror, row_id = _world(env)
    new_x = _rekeyed(x)
    new_x.pop("line_number")

    _repush(env, record, [new_x, y])

    _assert_removed(env, header, line_x, row_id)


def test_two_new_candidates_for_one_old_line_is_not_a_rekey(env):
    """K2: ambiguous, never a guess."""
    record, header, x, y, line_x, mirror, row_id = _world(env)

    _repush(env, record, [_rekeyed(x), _rekeyed(x), y])

    _assert_removed(env, header, line_x, row_id, expected_lines=4)


def test_a_line_whose_key_did_not_change_is_untouched_by_the_rekey(env):
    """The ordinary same-key re-push, beside a re-key of another line."""
    record, header, x, y, line_x, mirror, row_id = _world(env)
    line_y = {l["source_ref"]: l for l in env.so_lines(header["id"])}[y["source_ref"]]

    _repush(env, record, [_rekeyed(x), y])

    assert _core(env, line_y["id"])["source_ref"] == y["source_ref"]


def test_a_different_location_is_not_a_rekey(env):
    record, header, x, y, line_x, mirror, row_id = _world(env)
    other = env.link_warehouse(env.company_a)
    env.db.commit()

    _repush(env, record, [_rekeyed(x, warehouse_ref=other), y])

    _assert_removed(env, header, line_x, row_id)
