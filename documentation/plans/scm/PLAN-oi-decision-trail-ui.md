# PLAN: who saved, who confirmed, what raised - the decision trail on screen

Status: approved, small fix track (owner ruling 25 Sep 2026, "after got the data then we close
the UI gap"), building on `feat/oi-decision-trail-ui`. Issue #1238.
UAC: `oi-decision-trail-ui-acceptance-criteria.md` (beside this file).

**Round 3 (reviewer, code-correct-not-ready pass):** a `sheet` entry's `at` is now the
row's own `created_at` instead of `None` - the row is a real fact with a real time,
only the uploader is unknown, so it sorts among the trail's other entries instead of
always trailing at the end. `DecisionTrailDialog` (moved to `_shared/components/` -
shared code must not import from a route folder) omits the actor line entirely and
prints only the date whenever `actor_name` is null - a plain, kind-agnostic rule (not a
`sheet`-specific sentence): "Unknown" would claim a person was simply left unnamed,
which both a `sheet` mark and an anonymous backfill `raised`/`reconfirmed` event
(`raised_by` is nullable) are not. A `sheet` row's own origin match never touches
`order_inquiry_raises` at all, so a LATER raise event on the same inquiry (SO390524 /
OI-2609-0731's own 20 Sep 11:22 UTC reconfirm, on a fully sheet-migrated inquiry) never
surfaced anywhere; `_raise_entries` now emits one additional entry per `(inquiry, event)`
for any event more than 10 minutes past a row's own birth that no row's own origin match
already reported. See AC-DT-10.

**Deviation (coder, implementation):** `OrderInquiryWorklistRow` already carries
`raised_by_name` / `raised_at` (AC-H2/H3/H4, `test_order_inquiry_worklist_raised_by.py`) -
a coalesce of the covering decision's confirmer, the row's own acknowledger, then the
header's raiser, sortable and filterable. That is a DIFFERENT fact from section 3's
match against the actual `order_inquiry_raises` event, and reusing the same names would
have silently redefined an already-shipped, tested column. The new trio ships as
`raise_event_kind` / `raise_event_by_name` / `raise_event_at` instead, on the same row.
Both fields are named "raised" in the AC text below; read `raised_kind` there as
`raise_event_kind` and the by/at pair as `raise_event_by_name`/`raise_event_at`.

## The gap, measured

SO390524 (MAH SING / M TERRA, OI-2609-0731), prod, 25 Sep 2026: CS expected 3 advanced lines
to reach purchasing; 10 went out. The answer lived only in the DB:

- `projects.so_supply_decisions` revision 1, confirmed by Nurain 01:20:34 UTC, 11 line
  snapshots, all decided Buy (two of them against a pool proposal).
- `projects.order_inquiry_raises`: raised 20 Sep (sheet migration), reconfirmed 20 Sep
  (act-as user), reconfirmed 25 Sep 01:20:34 by Nurain; every disputed row `created_at`
  01:20:33.559 in that same call.
- `projects.so_supply_decision_drafts.saved_by / saved_at` per line.

On screen today: the board prints "by <name>" only inside `SupplyCompositionSection.tsx`
(line ~252, per composition), the OI General tab prints a Raised / Reconfirmed timeline for
the header. Nothing per line, nothing in the board header, nothing on the OI Lines tab. The
owner could not trace it.

## The change

Three surfaces, each fed by fields that already exist in the DB. No migration, no new table,
no UUID on screen, no explanation text in the UI (guides carry that).

### 1. Board header (`FulfilmentBoardPanel.tsx`)

Beside "N to confirm · N rejected": `Revision 1 · confirmed by Nurain, 25 Sep 2026 09:20 ·
11 lines`, or `No decision yet`. Source: the board payload's active decision for the order
being planned (the same object `SupplyCompositionSection` reads `confirmed_by_name` from).
If the board plans several orders, print one segment per order, order number first.

### 2. Verdict chip per line (`BoardDecisionPill.tsx` / `BoardVerdictActions.tsx`)

The Confirmed chip gets a tooltip (existing `Tooltip` primitive):
line 1 `Confirmed by Nurain, 25 Sep 2026 09:20 (revision 1)`;
line 2, only when a draft exists for the line, `Saved by <name>, <date time>`.
Backend: the board line payload gains `decided_by_name`, `decided_at`, `decision_revision`
(from the active decision the line's snapshot sits in) and `draft_saved_by_name`,
`draft_saved_at` (latest `so_supply_decision_drafts` row for that core line). Names resolved
through the existing `resolve_user_names`, never ids. Assert the new fields in a test on the
board response (response_model drops undeclared fields).

### 3. OI "Raised" column (Lines tab `orderInquiryHeaderLinesColumns.tsx` and the worklist)

New column `Raised`, after `Instruction`, hidden by default on the worklist and visible on
the Lines tab: `Reconfirmed by Nurain · 25 Sep 2026 09:20`. Kind words: `Raised`,
`Reconfirmed`; a row whose note starts with `Migrated from order inquiry sheet` prints
`Sheet`; a row raised by a planning change (note carries `Advance` / `Delay` wording written
by `planning_change_service`) prints `Planning change`. Backend: the worklist row serializer
(`order_inquiry_worklist_service.py`, the dict that carries `redirected_to_pool`) gains
`raised_kind`, `raised_by_name`, `raised_at`: the `order_inquiry_raises` event of the same
inquiry with the smallest `raised_at >= row.created_at - 1 second` (rows and their raise
event are written in one call; the prod gap measured 1.3 s). One grouped query per page,
not one per row. `None` on all three when no event matches (rows migrated before raises
were recorded).

## Tests (test first)

Backend, pytest on Postgres:
- board response carries the five new line fields and the header decision block for an order
  with a confirmed revision and one saved draft; `None` where absent.
- worklist rows carry `raised_kind / raised_by_name / raised_at` matched to the raise event
  written 1.3 s after the row; a row with no event within the window carries `None`.

Frontend, vitest:
- `FulfilmentBoardPanel` header renders the revision line and the "No decision yet" state.
- Verdict chip tooltip renders both lines / one line.
- `orderInquiryHeaderLinesColumns` renders the Raised cell for each kind and a dash when null.

Browser (agent-browser, sidebar navigation from `/`, on this lane's :3086 stack against the
24 Sep prod copy): SO390524's board header and the OI-2609-0731 Lines tab, recorded run.

## Out of scope

- Scoping Confirm to selected lines: #1216, its own plan.
- Any change to how decisions, drafts or raises are written.
