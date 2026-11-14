"""SPARE-PART-OR-B (slice 2 of #2381), red-first (Phase 2). R2: the OI number at final approval.

Contract: documentation/plans/purchasing/spare-part-or-b-14nov-acceptance-criteria.md
U2.1 - U2.8 (U2.2b included). Postgres only (`blank_session` via the shared world); every
row is seeded here (CI's database is empty).

NAMED CONTRACT CHOICES (the UAC leaves them open):

1. The column is `OrderInquiry.oi_no` (`projects.order_inquiries.oi_no varchar(20) NULL`),
   declared on the model as well as in the migration, so the blank test schema (built from
   `Base.metadata`) carries it and its partial unique index on (company_id, oi_no).
2. The backfill is a callable in the SERVICE, not only in the migration:
   `app.services.spare_part_request_service.backfill_oi_numbers(db) -> int` (the number of
   headers it gave an oi_no; flushes, never commits). The migration calls it (or the same
   SQL) so the rule is tested once, here.
3. `next_inquiry_no(bind, company_id, ref_date)` for the OI- series counts the highest
   OI- number in `inquiry_no` OR `oi_no` (U2.4); the approval mints through it.
4. U2.7 "OI header detail (`OrderInquiryDetail`)": the header detail route answers with
   `OrderInquiryHeaderDetailOut` (a subclass of `OrderInquiryHeaderOut`), so `oi_no` on
   `OrderInquiryHeaderOut` reaches both the list rows and the detail; asserted on both
   routes. Worklist rows: `OrderInquiryWorklistRow.oi_no` = the row's header's oi_no.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text

from ._forms_chain_support import uid
from ._spare_part_request_support import (  # noqa: F401  (fixtures)
    HEADERS,
    KIND,
    SPR,
    WORKLIST,
    approve,
    body,
    create,
    line,
    raised,
    reload,
    row_for,
    sent,
    staged,
    submitted,
    svc,
    two_staged,
    world,
)

_MY_TZ = ZoneInfo("Asia/Kuala_Lumpur")
OI_PATTERN = re.compile(r"^OI-\d{4}-\d{4}$")


def _oi_prefix(moment: datetime) -> str:
    """`OI-YYMM-` for a naive-UTC moment, by its Asia/Kuala_Lumpur month."""
    local = moment.replace(tzinfo=timezone.utc).astimezone(_MY_TZ)
    return f"OI-{local:%y%m}-"


def _seq(number: str) -> int:
    return int(number.rsplit("-", 1)[1])


def _oi_no(db, inquiry):
    """The header's oi_no off the database (AttributeError until the column exists)."""
    return reload(db, inquiry).oi_no


def _so_inquiry(w):
    from .test_oi_header_list import _header

    inquiry = _header(w.db, w.company_id)["inquiry"]
    w.db.commit()
    return reload(w.db, inquiry)


def _seed_header(w, *, state: str, raised_at: datetime, inquiry_no: str):
    """A spare part request header written directly (the backfill's input), no lines."""
    from app.models.project_so import OrderInquiry

    header = OrderInquiry(
        id=uid(),
        company_id=w.company_id,
        inquiry_type=KIND,
        state=state,
        raised_at=raised_at,
        inquiry_no=inquiry_no,
        requested_by=w.requester,
    )
    w.db.add(header)
    w.db.flush()
    return header


# =============================================================================
# U2.1 - the column, the unique index, the migration
# =============================================================================


def test_U2_1_order_inquiries_has_a_nullable_varchar20_oi_no(world):
    w = world
    row = w.db.execute(
        text(
            "SELECT data_type, character_maximum_length, is_nullable "
            "FROM information_schema.columns "
            "WHERE table_schema = current_schema() || '_projects' "
            "AND table_name = 'order_inquiries' AND column_name = 'oi_no'"
        )
    ).first()
    assert row is not None, "projects.order_inquiries.oi_no exists"
    assert row.data_type == "character varying"
    assert row.character_maximum_length == 20
    assert row.is_nullable == "YES"


def test_U2_1_a_partial_unique_index_on_company_and_oi_no(world):
    w = world
    defs = [
        r[0]
        for r in w.db.execute(
            text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE schemaname = current_schema() || '_projects' "
                "AND tablename = 'order_inquiries'"
            )
        )
    ]
    matching = [
        d for d in defs
        if "UNIQUE" in d.upper() and "oi_no" in d and "company_id" in d and "WHERE" in d.upper()
    ]
    assert matching, f"a unique (company_id, oi_no) WHERE oi_no IS NOT NULL index; found {defs}"
    assert re.search(r"oi_no IS NOT NULL", matching[0], re.I), matching[0]


def test_U2_1_two_headers_of_one_company_cannot_share_an_oi_no(staged):
    from sqlalchemy.exc import IntegrityError

    w = staged
    first = raised(w)
    second = raised(w)
    number = _oi_no(w.db, first)
    assert number, "precondition: the first approval minted a number"
    second = reload(w.db, second)
    second.oi_no = number
    with pytest.raises(IntegrityError):
        w.db.flush()
    w.db.rollback()


def test_U2_1_one_additive_migration_on_a_single_head():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    script = ScriptDirectory.from_config(config)
    heads = script.get_heads()
    assert len(heads) == 1, f"single alembic head, got {heads}"

    adding = []
    for revision in script.walk_revisions():
        source = Path(revision.path).read_text()
        if re.search(r"add_column\([^)]*order_inquiries", source, re.S) and "oi_no" in source:
            adding.append(revision)
    assert len(adding) == 1, "exactly one migration adds order_inquiries.oi_no"
    revision = adding[0]
    assert len(revision.revision) <= 32, revision.revision
    source = Path(revision.path).read_text()
    assert "drop_column" in source, "downgrade drops the column"
    assert not re.search(r"\b(drop_table|alter_column)\b", source.split("def downgrade")[0]), (
        "upgrade is additive only"
    )


# =============================================================================
# U2.2 / U2.2b - backfill
# =============================================================================


def _backfill_world(w):
    """Sep / Oct 2026 headers (naive UTC raised_at). Highest OI- number already issued in
    Sep 2026 (KL) is OI-2609-0007 (a legacy spare part request's own inquiry_no)."""
    sep = lambda day, hour=2: datetime(2026, 9, day, hour, 0)  # noqa: E731
    h = {}
    from .test_oi_header_list import _header

    so = _header(w.db, w.company_id)["inquiry"]
    so.inquiry_no = "OI-2609-0005"
    so.raised_at = sep(1)
    w.db.flush()
    h["so"] = so
    h["legacy"] = _seed_header(w, state="raised", raised_at=sep(3), inquiry_no="OI-2609-0007")
    h["b"] = _seed_header(w, state="raised", raised_at=sep(5), inquiry_no="OR-2609-0001")
    h["a"] = _seed_header(w, state="raised", raised_at=sep(10), inquiry_no="OR-2609-0002")
    # Same raised_at: inquiry_no breaks the tie (0003 before 0004).
    h["i"] = _seed_header(w, state="actioned", raised_at=sep(20), inquiry_no="OR-2609-0004")
    h["j"] = _seed_header(w, state="raised", raised_at=sep(20), inquiry_no="OR-2609-0003")
    # 30 Sep 17:30 UTC is 1 Oct in Kuala Lumpur: numbered under October.
    h["oct"] = _seed_header(
        w, state="raised", raised_at=datetime(2026, 9, 30, 17, 30), inquiry_no="OR-2610-0001"
    )
    h["draft"] = _seed_header(w, state="draft", raised_at=sep(6), inquiry_no="OR-2609-0005")
    h["pending"] = _seed_header(
        w, state="pending_approval", raised_at=sep(7), inquiry_no="OR-2609-0006"
    )
    h["rejected"] = _seed_header(w, state="rejected", raised_at=sep(8), inquiry_no="OR-2609-0007")
    w.db.commit()
    return h


def test_U2_2_backfill_numbers_approved_requests_in_raised_order(staged):
    w = staged
    h = _backfill_world(w)
    count = svc().backfill_oi_numbers(w.db)
    w.db.commit()
    assert _oi_no(w.db, h["b"]) == "OI-2609-0008", "first by raised_at, after the highest (0007)"
    assert _oi_no(w.db, h["a"]) == "OI-2609-0009"
    assert _oi_no(w.db, h["j"]) == "OI-2609-0010", "same raised_at: lower inquiry_no first"
    assert _oi_no(w.db, h["i"]) == "OI-2609-0011", "any post-approval state is numbered"
    assert _oi_no(w.db, h["oct"]) == "OI-2610-0001", "by the Kuala Lumpur month"
    assert count == 6, "five fresh numbers plus the legacy one's own"


def test_U2_2_backfill_leaves_draft_pending_and_rejected_null(staged):
    w = staged
    h = _backfill_world(w)
    svc().backfill_oi_numbers(w.db)
    w.db.commit()
    for key in ("draft", "pending", "rejected"):
        assert _oi_no(w.db, h[key]) is None, key


def test_U2_2_backfill_never_touches_a_sales_order_inquiry(staged):
    w = staged
    h = _backfill_world(w)
    svc().backfill_oi_numbers(w.db)
    w.db.commit()
    so = reload(w.db, h["so"])
    assert so.oi_no is None
    assert so.inquiry_no == "OI-2609-0005"


def test_U2_2b_backfill_a_legacy_oi_numbered_request_reuses_its_number(staged):
    w = staged
    h = _backfill_world(w)
    svc().backfill_oi_numbers(w.db)
    w.db.commit()
    legacy = reload(w.db, h["legacy"])
    assert legacy.oi_no == "OI-2609-0007", "oi_no = its own OI- inquiry_no, no new number"
    assert legacy.inquiry_no == "OI-2609-0007"


def test_U2_2_backfill_is_idempotent(staged):
    w = staged
    h = _backfill_world(w)
    svc().backfill_oi_numbers(w.db)
    w.db.commit()
    first = {k: _oi_no(w.db, v) for k, v in h.items()}
    again = svc().backfill_oi_numbers(w.db)
    w.db.commit()
    second = {k: _oi_no(w.db, v) for k, v in h.items()}
    assert again == 0, "a second run numbers nothing"
    assert second == first


def test_U2_2_backfill_continues_after_an_oi_no_already_issued(staged):
    """The highest OI- number counts oi_no too, not only inquiry_no."""
    w = staged
    done = _seed_header(
        w, state="raised", raised_at=datetime(2026, 9, 2, 2, 0), inquiry_no="OR-2609-0010"
    )
    done.oi_no = "OI-2609-0030"
    fresh = _seed_header(
        w, state="raised", raised_at=datetime(2026, 9, 4, 2, 0), inquiry_no="OR-2609-0011"
    )
    w.db.commit()
    svc().backfill_oi_numbers(w.db)
    w.db.commit()
    assert _oi_no(w.db, fresh) == "OI-2609-0031"
    assert _oi_no(w.db, done) == "OI-2609-0030", "an existing oi_no is never changed"


# =============================================================================
# U2.3 / U2.2b - final approval mints once
# =============================================================================


def test_U2_3_final_approval_sets_an_oi_number_by_the_raise_month(staged):
    w = staged
    inquiry = raised(w)
    inquiry = reload(w.db, inquiry)
    assert inquiry.state == "raised", "precondition"
    assert inquiry.oi_no and OI_PATTERN.match(inquiry.oi_no), inquiry.oi_no
    assert inquiry.oi_no.startswith(_oi_prefix(inquiry.raised_at))
    assert inquiry.inquiry_no.startswith("OR-"), "the OR- number stays the request's own"


def test_U2_3_a_non_final_approval_sets_nothing(two_staged):
    w = two_staged
    inquiry = approve(w, submitted(w), w.stage1.tier1)
    assert inquiry.state == "pending_approval", "precondition: stage 2 still open"
    assert _oi_no(w.db, inquiry) is None
    inquiry = approve(w, inquiry, w.stage2.tier1)
    assert inquiry.state == "raised"
    assert OI_PATTERN.match(_oi_no(w.db, inquiry) or ""), "the final level mints it"


def test_U2_3_two_approvals_take_consecutive_numbers(staged):
    w = staged
    first = _oi_no(w.db, raised(w))
    second = _oi_no(w.db, raised(w))
    assert first and second
    assert first[:8] == second[:8], "precondition: same month"
    assert _seq(second) == _seq(first) + 1


def test_U2_2b_approval_of_a_legacy_oi_numbered_request_reuses_its_number(staged):
    from app.models.project_so import next_inquiry_no

    w = staged
    inquiry = submitted(w)
    prefix = _oi_prefix(datetime.utcnow())
    legacy_no = f"{prefix}0087"
    inquiry.inquiry_no = legacy_no
    w.db.commit()
    inquiry = approve(w, reload(w.db, inquiry), w.stage1.tier1)
    assert inquiry.state == "raised", "precondition"
    assert inquiry.oi_no == legacy_no, "oi_no = its own OI- inquiry_no"
    today = datetime.now(timezone.utc).astimezone(_MY_TZ).date()
    assert next_inquiry_no(w.db, w.company_id, today) == f"{prefix}0088", (
        "no second number was minted for it"
    )


# =============================================================================
# U2.4 - the OI- series counts both columns
# =============================================================================


def test_U2_4_a_sales_order_oi_after_a_spare_part_approval_takes_the_next_number(staged):
    w = staged
    spare = _oi_no(w.db, raised(w))
    assert spare, "precondition: approval minted a number"
    so = _so_inquiry(w)
    assert so.inquiry_no.startswith(spare[:8]), "precondition: same month"
    assert _seq(so.inquiry_no) == _seq(spare) + 1


def test_U2_4_a_spare_part_approval_after_a_sales_order_oi_takes_the_next_number(staged):
    w = staged
    so = _so_inquiry(w)
    spare = _oi_no(w.db, raised(w))
    assert spare and spare.startswith(so.inquiry_no[:8]), (spare, so.inquiry_no)
    assert _seq(spare) == _seq(so.inquiry_no) + 1


def test_U2_4_next_inquiry_no_reads_the_highest_oi_no(staged):
    from app.models.project_so import next_inquiry_no

    w = staged
    header = _seed_header(
        w, state="raised", raised_at=datetime(2026, 9, 2, 2, 0), inquiry_no="OR-2609-0001"
    )
    header.oi_no = "OI-2609-0040"
    w.db.commit()
    assert next_inquiry_no(w.db, w.company_id, date(2026, 9, 15)) == "OI-2609-0041"


# =============================================================================
# U2.5 - revise keeps the number
# =============================================================================


def test_U2_5_revise_and_reapproval_keep_the_one_number(staged):
    w = staged
    inquiry = raised(w)
    number = _oi_no(w.db, inquiry)
    assert number, "precondition"
    svc().revise(w.db, reload(w.db, inquiry), w.requester)
    w.db.commit()
    assert _oi_no(w.db, inquiry) == number, "revise keeps oi_no"
    svc().submit(w.db, reload(w.db, inquiry), w.requester)
    w.db.commit()
    inquiry = approve(w, reload(w.db, inquiry), w.stage1.tier1)
    assert inquiry.state == "raised"
    assert inquiry.oi_no == number, "the re-approval mints nothing new"
    so = _so_inquiry(w)
    assert _seq(so.inquiry_no) == _seq(number) + 1, "no number was burned by the re-approval"


# =============================================================================
# U2.6 - null before approval, on the API
# =============================================================================


def test_U2_6_draft_pending_and_rejected_answer_oi_no_null(staged):
    w = staged
    draft = create(w)
    pending = submitted(w)
    rejected = submitted(w)
    svc().reject(w.db, rejected, w.stage1.tier1, "Too dear")
    w.db.commit()
    for inquiry in (draft, pending, rejected):
        res = w.as_user(w.requester).get(f"{SPR}/{inquiry.id}")
        assert res.status_code == 200, res.text
        data = res.json()
        assert "oi_no" in data, "the detail names oi_no"
        assert data["oi_no"] is None, inquiry.state


# =============================================================================
# U2.7 - oi_no on every read
# =============================================================================


def test_U2_7_the_spare_part_request_detail_returns_oi_no(staged):
    w = staged
    inquiry = raised(w)
    number = _oi_no(w.db, inquiry)
    res = w.as_user(w.requester).get(f"{SPR}/{inquiry.id}")
    assert res.status_code == 200, res.text
    assert res.json().get("oi_no") == number and number


def test_U2_7_the_spare_part_request_list_rows_return_oi_no(staged):
    w = staged
    done = raised(w)
    draft = create(w)
    number = _oi_no(w.db, done)
    res = w.as_user(w.requester).get(SPR, params={"limit": 50})
    assert res.status_code == 200, res.text
    rows = {r["id"]: r for r in res.json()["data"]}
    assert "oi_no" in rows[str(draft.id)], "the list row names oi_no"
    assert rows[str(draft.id)]["oi_no"] is None
    assert rows[str(done.id)]["oi_no"] == number and number


def test_U2_7_the_oi_header_list_rows_return_oi_no(staged):
    w = staged
    done = raised(w)
    so = _so_inquiry(w)
    number = _oi_no(w.db, done)
    res = w.as_user(w.buyer).get(HEADERS, params={"state": "all", "limit": 100})
    assert res.status_code == 200, res.text
    rows = {r["id"]: r for r in res.json()["data"]}
    assert rows[str(done.id)].get("oi_no") == number and number
    assert "oi_no" in rows[str(so.id)] and rows[str(so.id)]["oi_no"] is None


def test_U2_7_the_oi_header_detail_returns_oi_no(staged):
    w = staged
    done = raised(w)
    number = _oi_no(w.db, done)
    res = w.as_user(w.buyer).get(f"{HEADERS}/{done.id}")
    assert res.status_code == 200, res.text
    assert res.json().get("oi_no") == number and number


def test_U2_7_each_worklist_row_returns_its_headers_oi_no(staged):
    w = staged
    done = raised(w)
    number = _oi_no(w.db, done)
    res = w.as_user(w.buyer).get(WORKLIST, params={"inquiry_id": str(done.id), "limit": 100})
    assert res.status_code == 200, res.text
    rows = res.json()["data"]
    assert len(rows) == 2, "precondition"
    for row in rows:
        assert row.get("oi_no") == number and number


# =============================================================================
# U2.8 - the header list search matches oi_no
# =============================================================================


def test_U2_8_the_header_list_search_finds_a_request_by_its_oi_no(staged):
    w = staged
    done = raised(w)
    other = raised(w)
    number = _oi_no(w.db, done)
    assert number, "precondition"
    res = w.as_user(w.buyer).get(HEADERS, params={"state": "all", "limit": 100, "query": number})
    assert res.status_code == 200, res.text
    ids = {r["id"] for r in res.json()["data"]}
    assert str(done.id) in ids, "found by oi_no"
    assert str(other.id) not in ids


def test_U2_8_the_header_list_search_still_finds_by_inquiry_no(staged):
    w = staged
    done = raised(w)
    done = reload(w.db, done)
    res = w.as_user(w.buyer).get(
        HEADERS, params={"state": "all", "limit": 100, "query": done.inquiry_no}
    )
    assert res.status_code == 200, res.text
    assert str(done.id) in {r["id"] for r in res.json()["data"]}
