# PLAN - Order inquiry handshake: CS raises, purchasing acknowledges, links follow the acknowledgement

Status: RULED 2026-08-27 (captain, morning), build before the Friday UAT walk. Lane `.claude/worktrees/scm-uat` (FE :3080, BE :8080), one PR stacked on part 3 (`feat/scm-uat-so-change`). UAC: `scm-oi-handshake-acceptance-criteria.md`. Friday stations 4 and 6 in `PLAN-scm-friday-uat-journey.md` change when this lands.

## 0. What the captain asked (27 Aug)

CS (Eling's team) approves on the fulfilment board and the rows flow to Order Inquiries. Before purchasing (Joey) has looked at a row, CS must be free to change it. Once Joey has acknowledged it, a change must be visible to her as a change. Links (PO / SPO) are purchasing's: nothing auto-links when a row is raised; links happen when Joey acknowledges, and she may batch-acknowledge. She may reject a row with a reason (the pattern used elsewhere). She uploads the PO and SPO books from the Order Inquiries page, stays there, links from there, and has a button to open the PO page to check.

## 1. Rulings (captain, 27 Aug)

| Question | Ruling |
| --- | --- |
| Reorder planning's project demand | reads ACKNOWLEDGED rows only (and rows changed after acknowledgement); awaiting rows are a count on the plan page, never demand |
| Amend after acknowledgement | row updated IN PLACE with the previous value carried (part 3's settle-in-place), links kept, `ack = changed`; Joey re-acknowledges or rejects from her own page. Planning changes (the batch) stays for SO BOOK changes only |
| Reject | row withdrawn from netting; the board cell shows "Rejected by <name>: <reason>", the line is undecided again, CS re-decides |
| Existing rows | no backfill: the feature is not live; every existing row starts `awaiting` |
| Who may acknowledge / reject | a permission under purchasing (Joey's role); CS cannot acknowledge its own rows |
| When | before Friday |

## 2. Model

Two columns on the row, never merged: `state` (supply: raised / placed / partly_linked / cancelled / withdrawn, exists) and `ack_state` (handshake, new).

`ack_state`: `awaiting` (default) -> `acknowledged` | `rejected` | `changed` (was acknowledged, CS amended; back to `acknowledged` on re-acknowledge).

Columns on `projects.order_inquiry_rows` (one migration, `down_revision` = lane head `427_sales_agents_class_backfill`, id <= 32 chars): `ack_state VARCHAR(16) NOT NULL DEFAULT 'awaiting'`, `acknowledged_by` (users.id, nullable), `acknowledged_at`, `rejected_by`, `rejected_at`, `rejected_reason TEXT`, `changed_at`. Previous value on a change: whatever part 3's settle-in-place already carries (reuse, do not add a second copy). The row's schema declares every one of them (`response_model` drops undeclared fields).

## 3. Behaviour

| Event | Actor | Effect |
| --- | --- | --- |
| Board Approve / Confirm | CS | rows raised `awaiting`; **no cascade**: `_auto_place_after_confirm` leaves `supply.confirm` |
| Amend before acknowledgement | CS | settle-in-place (part 3), stays `awaiting`, silent; supersede path raises the new rows `awaiting` |
| Acknowledge (one or many) | purchasing | `acknowledged` + who/when; the cascade runs for exactly those rows |
| Reject with reason | purchasing | reason required; `rejected` + who/when/reason; row leaves `committed_v` and the plan's demand; the line's decision is uncovered (`supply.confirm`'s `uncover_line_ids` seam) so the board shows it undecided with the reason |
| Amend after acknowledgement | CS | settle-in-place, previous value carried, links kept, `ack_state = changed`; a supersede of an acknowledged row raises its new rows `changed` too |
| Re-acknowledge a changed row | purchasing | `acknowledged`, cascade for the unlinked remainder |
| Upload PO / SPO book on the OI page | purchasing | the reorder page's `UploadDataMenu` / upload dialogs mounted on the OI toolbar (same components, same worker jobs); on completion the drawer offers **Link now** and **Open purchase orders** |
| Link now | purchasing | the cascade over acknowledged / changed unlinked rows of the products the upload touched |
| PO confirm cascade (exists) | system | acknowledged / changed rows only |
| Existing Auto-link on the OI page | purchasing | acknowledged / changed rows only |

Netting: `committed_v` and the S13b demand leg exclude `rejected`; the reorder plan's project demand counts `acknowledged` and `changed` only; the plan page shows "N awaiting acknowledgement" as a count chip (no sentence).

## 4. Screens

- **Order Inquiries (list + schedule):** an Acknowledgement filter (SearchableSelect, clearable: Awaiting / Acknowledged / Changed / Rejected); a column "Acknowledged" reading the name and time, "Awaiting", "Changed <date>" or "Rejected: <reason>" (truncate + title); row checkboxes with a bulk bar: **Acknowledge (N)**; per row **Reject** opening the reason dialog (reuse `scm/reorder/components/BulkRejectDialog.tsx`'s shape); a **Changed** row shows the same Was / Now table part 3 draws on the board. Upload button on the toolbar.
- **Fulfilment board:** a rejected line's cell is undecided and carries "Rejected by <name>: <reason>"; the decision strip counts it under nothing decided.
- **Reorder planning:** count chip "N awaiting acknowledgement" beside the existing header badges.
- Permission slug `project_sales.order_inquiries.acknowledge` gates Acknowledge, Reject, Link now and the upload button; seeded to the purchasing role; CS sees the column and the filter, not the actions.

## 5. Order of work (one PR)

1. Migration + model + schema + `ack_state` on the worklist read (filter, facet count) - test first.
2. Acknowledge (batch) + reject endpoints, permission, cascade moved out of `supply.confirm` and into acknowledge / Link now / PO confirm - test first.
3. Netting and plan demand exclusions, awaiting count - test first.
4. Settle-in-place sets `changed`; supersede inherits it; board reject flag via `uncover_line_ids`.
5. FE: filter, column, bulk bar, reject dialog, Was / Now on changed rows, upload menu + Link now + Open purchase orders, board flag, plan chip.
6. Browser evidence on SO381895, then the Friday sheet's stations 4 and 6 rewritten.

## 6. Tests

pytest: acknowledge one / many, 403 for a CS user, cascade runs only at acknowledge (a board confirm leaves rows unlinked), reject requires a reason (422), rejected row absent from `committed_v` and the plan demand, board line undecided with the reason, amend before ack silent, amend after ack -> `changed` with the previous value and links kept, supersede inherits `changed`, PO confirm cascade skips awaiting rows, Link now scoped to the uploaded products, every new column on the wire. vitest: filter, column states, bulk bar count, reject dialog validation, upload menu mount and the two buttons, board flag, plan chip.
