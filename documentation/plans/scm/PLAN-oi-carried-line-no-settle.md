# PLAN: a carried line never settles or redirects its row on reconfirm

Status: approved, small fix track (owner ruling 25 Sep 2026), building on
`fix/oi-carried-line-no-settle`. Issue #1226.
UAC: `oi-carried-line-no-settle-acceptance-criteria.md` (beside this file).

## The defect, measured

OI-2609-0755, SO422380 L224 (AP4844, Buy 2, BRW-IB, 15 Oct 2026), 24 Sep 19:00 prod copy:

- 22 Sep 17:43 MYT: revision 1 confirmed; the raise cascade linked the row to
  PO-2026/09-0023 line AP4844 (JAZZING, local supplier, 120-pc stock PO, no
  `from_so_line_ref`, no SPO chain).
- 24 Sep 11:07 MYT: ESB push, AutoCount `TransferedQty` 120 arrives as `qty_received` 120,
  line and PO `closed`. For a local supplier this is a real receipt.
- 24 Sep 11:12 MYT: stock import, 120 on hand at pool BRW (not BRW-IB).
- 24 Sep 17:15 MYT: CS reconfirmed SO422380 for other lines. L224 was CARRIED
  (`_CarriedLine`: previous snapshot copied verbatim, including the 22 Sep proposal
  "Only 0 of 2 can be covered from stock"). `refresh_for_decision` still handed the
  carried line's placed draft row to `_settle_row_in_place`, whose first step
  `_redirect_row_if_received` read the PO link as fully received, the R7 credit as 0, and
  marked the row `redirected_to_pool` (`used`) then raised a fresh ORDER 2 row
  "Replaces 2 used" off the stale Buy. Its Changed dialog prints Was 2 / 15 Oct, Now
  2 / 15 Oct.
- `ProjectSupplyService.proposal_for` run read-only on that copy proposes Reserve 2 from
  pool BRW ("Pool BRW spares 2 of the 60 it may lend a project", `pools_net` 120). The
  fresh Buy would not be proposed today.

Company wide on the copy: exactly one row has this shape.

## Ruling

Owner, 25 Sep 2026: (a) a reconfirm that carries a line unchanged must not settle or
redirect that line's row; "nothing changed, nothing moves". (b) re-planning the replacement
need against current stock: REJECTED, "complicates things more, need to be simpler and more
direct". (b) is also unnecessary: a NAMED line already gets a fresh decision against current
stock, so the only path that reused a stale Buy was the carried one.

## The change

`sorento_crm_backend/app/services/project_order_inquiry_service.py`,
`refresh_for_decision`, the per-entry loop (around the `drafted` list and the
`if (asked_to_settle or drafted) and self._settle_row_in_place(...)` gate):

- For an entry with `carried` true, `drafted` is EMPTY: no placed or partly linked draft row
  of a carried line is handed to `_settle_row_in_place`, so `_redirect_row_if_received`
  never runs for it. `asked_to_settle` (a planning change naming the line) is untouched.
- In the netting loop that follows, a carried line's PLACED row nets its full qty (as
  today) and a carried line's PARTLY_LINKED row ALSO nets its full `qty` and is left
  exactly as it is: no shrink to the linked qty, no "Remainder superseded" note, no
  `refresh_link_state`, no redirect. `outstanding = need - placed` then reads 0 for an
  unchanged line, so nothing is raised.
- A carried line's still-RAISED row keeps today's cancel + re-raise under the new revision
  (the handshake inheritance in `_handshake_for_raise(carried=True)` is unchanged).
- Named lines, planning-change settles (`settle_in_place`), local-origin lines and the
  supersede path are not touched.

Nothing else changes. No migration, no schema, no frontend.

## Tests (test first, pytest on Postgres)

`sorento_crm_backend/tests/test_oi_one_header.py`, beside the S4 (AC-OH-40..42) tests, same
`_settle_capturing_result` / world fixtures:

1. Carried line, placed draft row linked to a fully received PO line: reconfirm naming a
   sibling line only. Row stays `placed`, `redirected_to_pool` false, note unchanged, no
   second ORDER row for the line, no handover record for it.
2. Carried line, PARTLY_LINKED draft row (qty 5, 3 linked): same reconfirm. Row keeps
   qty 5, state, note; no remainder row raised.
3. NAMED line, placed draft row linked to a fully received PO line, credit 0: today's
   redirect still happens (AC-OH-40 stays green) - guards against over-gating.
4. Existing AC-OH-41 and `test_carried_local_line_skipped` stay green.

## Cleanup after merge (owner runs, one row)

```sql
delete from projects.order_inquiry_links where row_id = '2dcb1590-31a7-42f5-8d78-8eacee450cbd';
delete from projects.order_inquiry_rows  where id     = '2dcb1590-31a7-42f5-8d78-8eacee450cbd';
update projects.order_inquiry_rows set redirected_to_pool = false
 where id = '30f4d042-4ca8-47a1-9564-c7e12bf3368b';
```

## Out of scope

- #1215 point on the follow-book PO-number fallback (CWB242 on a closed SPO): owner chose
  not to open that lane now.
- R7 credit ignoring local-supplier PO receipts: not needed once (a) is in; revisit only if
  a NAMED line shows the same shape.
