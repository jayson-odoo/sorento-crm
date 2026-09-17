# PLAN: order inquiry handover email r2, depth-N undo, reconstructed undo

Status: building 18 Sep 2026; issues #996 #997 #998 #999; Phase 2 green on the lane, review in progress
UAC: `documentation/plans/scm/scm-oi-handover-r2-undo-acceptance-criteria.md`
Branch: `feat/oi-handover-r2-undo` from `origin/main` (after #993, head migration
`undo_0003_journal_sql_null`). #992 is open on the same confirm seam; the pre-PR gate merges it in.

## 1. Why (measured, 17 Sep 2026, prod)

SO314593 and SO314594 were confirmed at 02:11Z (rev 1, nine lines) and again at 03:25Z (rev 2, all
eleven lines) because a wifi outage swallowed the first Confirm response and the board re-saved the
confirmed lines as drafts (#989, fixed). Purchasing got two emails. The second one printed
`CANCEL BALANCE 280 NOS` + `ORDER 280` for every line whose rev-1 row was still plain `raised`
(CB2806A, CB2807, SRTWB245, CSH2072), and said nothing about SRTWCX8605 182 to 214, which the first
email had carried, in a Cc list that did not yet include purchasing@. Neither revision has an
`undo_journal` (both predate the 04:37Z undo deploy), so today's undo refuses them, and Reset
planning would delete the sheet-migrated rows purchasing already placed.

Owner rulings, 17 Sep (do not re-litigate):

- Purchasing must read ONE page that matches the board. No Resend button, no snapshot script:
  the fix is process-flow, undo then confirm.
- Layout follows the manual mail: `QTY` old, `QTY CHANGE TO` new, same for the delivery date.
  CUSTOMER / PROJECT stay in the SO table only. Every date `dd/mm/yyyy`. CANCEL BALANCE prints old
  qty, CHANGE TO 0. Reverses R3 of the archived handover plan.
- Undo walks back as many revisions as exist (reverses ruling 3 of the undo plan).
- A journal-less revision gets a reconstructed undo, labelled, from the gear menu.

## 2. Slices

### S1 Email layout (backend + migration)

One template, updated in place by migration `oihr_0001_handover_r2_layout` (down_revision
`undo_0003_journal_sql_null`): `UPDATE email_templates SET subject, body_html, body_text WHERE code
= 'order_inquiry_handover_default'`, insert when absent, downgrade restores the r1 strings (kept
verbatim in the migration file). The automation row and recipients are untouched (the owner typed
purchasing@ by hand on prod; a re-seed must not lose it).

Line table, HTML and text:

```
SO DATE | S/O NO | ITEM CODE | QTY | QTY CHANGE TO | DELIVERY DATE | DELIVERY DATE CHANGE TO | REMARK
```

Cell rule, all in Jinja on the existing `line` dict (no context shape change for S1 except AC-R2-06):

- `QTY` = `line.was.qty` when present, else `line.qty`. `QTY CHANGE TO` = `line.qty` when
  `line.was.qty` present, else blank. Same pair for the delivery date on `line.was.delivery_date`.
- A cancelled line already carries `qty = "0"` and `was.qty = old`, so it prints `280 | 0` with no
  special case.

`derive_for_amendment` (`project_order_inquiry_service.py` ~2320) passes `was={"delivery_date":
from_value}` for DATE_LATER / DATE_EARLIER rows (the value is already in the row dict; no lookup), and
`handover_remark(kind="raised")` skips the note when `was` carries `qty` or `delivery_date`
(CHANGE SO rows keep their note; their `was` carries `so_number`, not a date). `_change_note`
(~2432) formats the date with `_handover_fmt_date` so the worklist note and the email agree.

Amendment rows on the Confirm email (AC-R2-16/17, owner Q4): amendment rows are raised by
`derive_for_amendment` at publish time, not by Confirm, so two undos leave them raised and a fresh
Confirm would not mention them. `refresh_for_decision`, after its own `_record_handover` calls,
queries this order's inquiries with `amendment_id IS NOT NULL` for rows in state `raised` and
records each once as `kind="raised"` with `was` built from `previous_delivery_date` /
`previous_qty` (fallback: parse `Was dd/mm/yyyy` from the note), so the DELAY lines land on the
same page as the buys. Dedup by row id inside one pending queue.

Subject (S3, same file ~7405): build `locations` from non-blank values only; blanks are ignored.
One named location, any number of blanks: `<location> @ <so list>`. Two or more named: bare.

### S2 Named-path equality gate

`refresh_for_decision` (~856): the `drafted` predicate that admits a line to
`_settle_row_in_place` widens to also admit a line whose live rows are exactly one plain
`INQUIRY_RAISED` ORDER / ORDER_BACK row with no links, not redirected, whose verb equals the verb
this confirm would raise. `_settle_row_in_place` already handles that row: unchanged need means
`changed = False`, no handover line, `supply_decision_id` repointed; a changed need means one
`settled` line. Two live rows, a verb switch, or a linked row fall through to the supersede path as
today. Comment AC-H23 is rewritten to name the narrowed case it still covers.

Consequence for the existing test `test_named_line_reconfirmed_new_qty_prints_cancel_and_order`:
it now expects one settled line. `test_retired_row_prints_cancelled_line` (a line dropped from the
revision) is unaffected.

### S4 Depth-N undo with a post-image guard

`project_supply_undo_service.py`:

- `attach` (~360): drop the `supersedes_id` clear. `undo_last_confirm` (~996): drop the `prior_id`
  clear. Every revision keeps its journal for life.
- `_before_flush`: an `update` entry gains `"new"`, captured in `_after_flush` from the object's
  current attribute values for the same keys as `old` (post-flush, so defaults and onupdate values
  are the real written ones). Insert and delete entries are unchanged.
- New refusal `changed` in `_grouped_refusals`: for each `update` entry that carries `new`, read
  the current row (one `SELECT ... WHERE pk IN (...)` per table, grouped) and compare the journaled
  keys. Any mismatch refuses with `table` + `pk`. Entries without `new` (legacy) are skipped. The
  check runs at park time (`refusal_for_order`, synchronous 409) and again inside
  `undo_last_confirm` before `_replay`. It is NOT computed on the board read: `board_undo_map`'s
  trimmed journal stays as it is, so a `changed` order's gear entry is enabled and the park
  answers 409 with the reason, which `useDeferredAction` already surfaces as the error toast.
- `BoardUndo` gains `mode: Literal["journal", "reconstructed"]`; `refusal` adds `"changed"`.

`_journalled_decision_clause` and the `none_as_null` model option stay (#993).

### S5 Reconstructed undo for journal-less revisions

Same action key, same FormAction, same countdown. Payload carries `mode`. `_undo_confirm` in
`record_actions.py` reads the decision: journal present and `mode == "journal"` runs today's
replay; journal NULL and `mode == "reconstructed"` runs `reconstruct_undo` in a new module
`project_supply_undo_reconstruct_service.py`; any other pairing is 409. Admin gate: the board read
sets `undo` for a journal-less active decision only when the requesting user's role slug is
`superadmin` or `admin` (the same two the module guard trusts), and `_undo_confirm` re-checks the
role on execute (403 otherwise). Rationale: every order confirmed before 17 Sep 04:37Z is
journal-less; a planner must not see a best-effort restore on all of them.

`reconstruct_undo(db, order, decision, actor_user_id)`, in this order, all scoped to one order and
one company:

1. Refusals: the existing `linked` / `actioned` time predicates against `decision.confirmed_at`.
2. Rows raised by D: `order_inquiry_rows` with `supply_decision_id = D.id` and `created_at >
   D.confirmed_at - 60 s` (uniform, with or without P: a row P itself raised seconds after P's own
   confirm is a settled row, not one D raised; `_settle_row_in_place` never moves `created_at`). Delete their links via
   `_remove_links` (frees orphan claims), then the rows.
3. Rows settled or repointed by D: the remaining `supply_decision_id = D.id` rows. If `changed_at`
   is within 60 s of `D.confirmed_at`: `qty = previous_qty`, `delivery_date =
   previous_delivery_date`, both previous columns NULL, note appended. Then `supply_decision_id =
   P.id` or NULL.
4. Rows D cancelled: state `cancelled`, note equal to `Superseded by revision {D.revision_no}`:
   state `raised`, note appended.
5. Rows D released: `redirected_to_pool = true` and note containing `released at revision
   {D.revision_no}`: flag back to false (received links are still attached, open links are gone
   and stay gone).
6. `so_line_allocations WHERE decision_id = D.id` deleted. `stock_transfers WHERE
   supply_decision_id = D.id AND state = 'proposed'` deleted; `state = 'cancelled' AND
   cancelled_reason = 'Superseded by revision N'` back to `proposed`, `supply_decision_id = P.id`.
7. D deleted with the audit delete row the journal undo writes; P set `active`, superseded
   columns NULL. No drafts written.
8. `_record_undo` with headline `RECONSTRUCTED`, lines = rows removed + rows restored.

Not restored, stated in the gear entry and the email: saved drafts, the note text a supersede
overwrote, ack stamps, links purchasing removed by hand, the open links a release dropped, a
partly-linked shrink's pre-shrink qty.

### S6 Frontend (Phase 1 first)

`FulfilmentBoardPanel.tsx` gear list: the label gains `, reconstructed` and a second line when
`undo.mode === "reconstructed"`; `UNDO_REFUSAL_TITLES` gains `changed`. `useDeferredAction`
payload gains `mode: order.undo.mode`. Service and hook unchanged otherwise. Mock: the board
service mock returns one order per mode and one refused `changed`.

## 3. Test list (captain's, one line per AC)

- AC-R2-01..05, 09: `test_handover_r2_template_cells` parametrised over settle-qty, settle-date,
  cancel, raise: render the seeded r2 template with a hand-built context, assert cell text per
  column in HTML and text, and `<s>` absent.
- AC-R2-06: `test_amendment_delay_row_carries_previous_date_in_was_and_bare_verb`.
- AC-R2-07: `test_change_note_and_email_dates_are_ddmmyyyy`.
- AC-R2-08: `test_r2_migration_updates_template_in_place_and_is_idempotent` (+ downgrade).
- AC-R2-10..13: `test_named_unchanged_raised_row_settles_silently`,
  `test_named_changed_raised_row_settles_with_one_line`, `test_named_verb_switch_supersedes`,
  `test_named_two_live_rows_supersede`, `test_so314594_shape_full_reconfirm_prints_two_lines`.
- AC-R2-16..17: `test_confirm_email_appends_still_raised_amendment_rows_once`,
  `test_confirm_without_amendment_rows_appends_nothing`.
- AC-R2-14..15: `test_subject_ignores_blank_locations` parametrised over the three sets.
- AC-R2-20..27: `test_attach_keeps_superseded_journal`, `test_undo_keeps_reinstated_journal`,
  `test_undo_twice_then_refuses`, `test_update_entry_carries_new`,
  `test_changed_row_refuses_at_park_and_execute`, `test_legacy_entry_without_new_is_skipped`,
  `test_second_undo_passes_changed_check`, `test_board_undo_carries_mode_and_changed`.
- AC-R2-30..35: `test_reconstructed_visible_to_admin_only`, `test_reconstruct_undo_steps_a_to_h`
  (one test per letter), `test_reconstruct_refuses_linked_and_actioned`,
  `test_so314594_and_so314593_reconstructed_twice_then_one_confirm_one_email`,
  `test_mode_mismatch_409`, `test_non_admin_reconstructed_403`.
- FE: `FulfilmentBoardPanel.undo.test.tsx` gains three cases (mode label, changed refusal, mode in
  payload).

## 4. Rollout

1. Deploy. Migration updates the template on prod.
2. Owner, as admin, on prod: SO314593 then SO314594, gear, reconstructed undo twice each, re-enter
   the two rejects (`local` on TPE-9204 and WESERP10B), Confirm once. Two emails, one per order,
   in the r2 layout.
3. Owner checks System Management > Automation: recipients unchanged.

## 5. What undo never touches (owner question, 18 Sep)

The SO change is an amendment published from the SO page (`ProjectSODeltaService.publish`), which
raises DELAY / ADVANCE / CANCEL BALANCE rows under the amendment's own inquiry with no decision id.
Undo, journaled or reconstructed, reverses only what a Confirm wrote. After two undos an order sits
at "SO changed, amendment rows raised and already emailed, no supply decision", which is the state
the owner asked for. The confirm email that follows carries the confirm's own lines only; the
amendment rows are not repeated. Owner to rule whether the confirm email should also list the
order's still-raised amendment rows (not in scope unless ruled).

## 6. Out of scope

Depth-N undo across a planning-change batch fork beyond what the journal already covers; a
revision-history screen; REPLACE ITEM (slice 2 of the handover plan).
