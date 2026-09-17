# PLAN - Order inquiries: the auto-link cascade skips a document arriving outside the row's lead-time window

Status: implemented (review round 2 pending) (owner go 17 Sep 2026: "if it links and suggest to reallocate at the same time, don't link")
UAC: `oi-cascade-skip-early-arrival-acceptance-criteria.md` (AC-EA-xx)
Branch: `feat/oi-cascade-skip-early-arrival` from `origin/main` (792ba8f04)
Worktree: `../sorento_crm-oi-cascade-early`, DB `sorento_oice_ci` (copy of `sorento_sodl_ci`, stamped `undo_0002_seed_undone`)
Origin: SO421645 / OI-000739 on prod, 17 Sep 2026. Delivery 15 Jan 2027. The cascade linked the
BT012-CR and CB1178A-SS-NEW rows to 202607-S0077 (a July purchase order) and every one of those
links carried the yellow `reallocate` pill the moment it was written. Owner: "kinda redundant".

## Measured facts (origin/main, 17 Sep)

All paths `sorento_crm_backend/`.

- `app/services/order_inquiry_worklist_service.py`
  - `_attach_link_suggestions` (line 1170): an open link earns `suggestion = reallocate` /
    `unlink` when `expected_date <= delivery_date - timedelta(days=lead_days)` (line 1212,
    written as the negated `continue`). `lead_days` = `ProjectSupplyService.lead_times`
    (measured supplier average, else stated `product_suppliers.standard_lead_time_days`,
    fastest supplier), else `DEFAULT_LEAD_TIME_DAYS` from `scm/front_planning_engine.py`
    = **90** (line 92 import, line 1211). A received link, or a link/row with no date, never
    triggers. Merged in #973 (`PLAN-oi-replan-received-links.md`, AC-RL-20..23).
- `app/services/project_order_inquiry_service.py`
  - `auto_place_for_products` (line 6206) is the ONE cascade every trigger goes through
    (`autocount_ingest`, `raise`, `po_confirm`, `acknowledge`, `link_now`, `po_book_upload`,
    `decision_confirm`). Per row: horizon check (`_after_horizon`, line 6351), then
    `candidates = self._candidates_for_row(row, credit_own_links=bool(drafts))` (line 6354),
    then `_cascade_take(candidates, need)` (line 5347), which honours `candidate["cascadable"]`
    and returns nothing when the cascadable total cannot cover `need` in full.
  - `_candidate` (line 5213) builds each candidate dict: `kind` (`po` / `spo`),
    `expected_date`, `own_so_claim`, `cited` (`is_cited`, line 5261), `cascadable =
    own_so_claim or not project_locked` (line 5312), sort key = own claim, citation, SPO
    before PO, location tier, PO issue date, expected date, document. **Nothing in the walk
    compares the candidate's arrival with the row's delivery date.**
  - `po_candidates_for_row` (line 5396) feeds the Link dialog off the same
    `_candidates_for_row`; a person may take any listed line by hand.
  - The only cutoff in force today is the link horizon (`resolve_link_horizon`, line 6150):
    an absolute date off the reorder plan's "Plan until". A row due AFTER it is held back and
    counted `after_horizon`. A row due inside it links to whatever ranks first, however early.
  - `from datetime import date, datetime` (line 44); `ProjectSupplyService` is imported
    locally inside methods (line 3924), never at module level (the supply service imports
    this module).
- Frontend `order-inquiries/components/OrderInquiriesClient.tsx` line 825: the Auto link all
  toast's `skipped` = `rowIds.length - placed_rows - after_horizon`. A row this rule leaves
  alone already lands in that figure. `AutoPlaceResult` on the wire is unchanged.
- No local DB holds OI-000739 (prod only); the lane DB is a seed-your-own copy.

## Design (simplest thing that works)

**One predicate, two readers.** The cascade must never write a link the worklist would flag in
the same breath. So the pill's test becomes a module-level function and the cascade reads it
too. No new setting, no new column, no new counter, no FE change.

### S1 - the predicate, shared [BE]

`app/services/project_order_inquiry_service.py`, module level:

```python
def arrives_outside_window(
    expected_date: Optional[date], delivery_date: Optional[date], lead_days: int
) -> bool:
    """True when a document's promised arrival is a full lead time (or more) BEFORE the
    row's delivery date - the stock would sit for a whole buying cycle before this row
    needs it, so a nearer row should have it. Either date missing -> False."""
    if expected_date is None or delivery_date is None:
        return False
    return expected_date <= delivery_date - timedelta(days=lead_days)
```

`_attach_link_suggestions` in the worklist service calls it in place of its inline comparison.
Behaviour identical (the existing `test_order_inquiry_worklist*` suggestion tests stay green
untouched); it now cannot drift from the cascade's copy because there is no copy.

### S2 - the cascade refuses an early candidate [BE]

In `auto_place_for_products`, once per pass: `lead_times = ProjectSupplyService(self.db)
.lead_times({product ids of the rows walked})` (local import, as line 3924 does), default
`DEFAULT_LEAD_TIME_DAYS` from `scm/front_planning_engine.py` (90) - the SAME two sources and
the SAME default the pill reads, or the two would disagree again by another route.

Per row, after `_candidates_for_row` and before `_cascade_take`:

```python
candidates = [
    c for c in candidates
    if c.get("own_so_claim") or c.get("cited")
    or not arrives_outside_window(c.get("expected_date"), row.delivery_date, lead_days)
]
```

- **Own-SO claim and cited document bypass.** A line the supply writer raised FOR this SO, or
  one CS named on the form, already outranks every ordering rule in the walk (`_candidate`'s
  sort key); the window does not overrule a person or the book.
- **PO lines and SPO allocations alike**: both carry `expected_date` in the dict.
- **A row with no delivery date, or a line with no promised date, is never early** - same as
  the pill (AC-RL-21), same as the horizon (AC-LH4).
- The early candidate is REMOVED from the walk, not marked `cascadable=False`: `_cascade_take`
  sums cascadable `remaining` to decide full cover, and an early line must not count toward
  cover it will not give. `po_candidates_for_row` (the Link dialog) is untouched, so a buyer
  can still take the line by hand; a link so written earns the pill, which is the pill's job.
- **Re-deal** (`redeal_drafts`, Auto link all over a draft): a draft sitting on an early line
  finds that line gone from the walk. With nothing better, `takes` is empty and the row keeps
  its draft (B1, 28 Aug: links come down only for a better answer). Not retro-cleaned: the
  pill on that link IS the instruction, and the owner acts on it from the lightbox.
- **Result counts unchanged.** The row stays raised, `placed_rows` does not count it, and the
  FE toast's `skipped` arithmetic already includes it. The link horizon keeps its own place
  as the absolute date ceiling, checked first, exactly as today.

### S3 - the pill honours the same two exemptions [BE] (review round 1, S1 finding)

Measured by the reviewer: on AC-EA-7's seed the cascade links the cited early line AND the
next worklist read puts `suggestion = unlink` on that same link; same for an own-SO-claimed
line. So the invariant "never link what the pill flags" was still broken for exactly the two
documents the walk is told to honour. Captain's ruling: the pill learns the same exemptions.
A line the supply writer raised FOR this SO (`scm.order_link_claim` naming the row's own SO
and that PO line) or a document CS named on the form (`_cited_documents(row)`, the same
reader the walk uses) is a person's or the book's word; a pill telling the buyer to undo it
is the noise the owner complained about, one door over. `_attach_link_suggestions` skips
such a link (`suggestion = None`), reading claims in ONE batched query for the page's
triggered PO lines and citations off the row it already holds.

### S4 - the Link dialog's recommendation follows the walk [BE] (review round 1, S3 finding)

`po_candidates_for_row`'s docstring promises `default_take` / `recommended` are "the
cascade's own preview computed by the SAME walk", and after S2 that was false: the dialog
pre-recommended the very line the pass refuses. The early line stays LISTED (AC-EA-12, a
buyer may take it by hand) but `recommended` is False and `default_take` is `0` for it - the
preview runs the same window filter the pass runs, through one helper both call. Docstring
corrected to say so.

### Review round 1 nits folded

- `_cascade_take` already sums only cascadable `remaining`, so the "removed, not
  `cascadable=False`" comment gives the wrong reason; the real reason is that
  `po_candidates_for_row` reads `cascadable` to grey a line, and an early line is not
  greyed - it is listed as takeable by hand. Comment corrected.
- The pass resolved product ids three times per row set (`_netting`, the lead-time set, the
  loop). One `product_ids` list hoisted and reused.
- `DEFAULT_LEAD_TIME_DAYS` imports at module level (no cycle); the `ProjectSupplyService`
  local import stays, by the convention at the existing local import, not for a cycle.
- Backticked identifier no longer split across lines in the docstring.
- AC-EA-3 also asserts the worklist row carries no `suggestion`.

Deliberately left alone (reviewer check 1): `follow_book_repairing` re-points an existing
link where the AutoCount book moved a reference; it repeats what the book said rather than
choosing, so it does not consult the window. A link it lands early earns the pill, correctly.

### Phases

Phase 1 (FE mock): none - no FE surface changes. Phase 2: tester writes the reds below, coder
makes them green. Phase 3: reviewer + browser pass on the worklist (Auto link all on a
Jan 2027 row with only an early PO leaves it Not linked, toast reads `1 skipped`).

## No-motion list

- No System Settings knob. The per-product lead time IS the cutoff, and it already exists.
- No new `AutoPlaceResult` field, no new toast wording.
- No change to the Link dialog's candidate list, the reallocate lightbox, or the pill.
- No change to `_cascade_take`, `_candidate`'s sort key or `cascadable`.
- No retro pass over links already written on prod: the pill lists them; owner acts.

## Testing seams

`tests/test_order_inquiry_cascade_early_arrival.py`, Postgres via `tests/_pg_fixture.py`
`blank_session`, seed chain per test (CI DB is empty). Model the SO/OI/PO seeding on
`tests/test_order_inquiry_links.py` and the claim seeding on `tests/test_order_inquiry_dedication.py`.
Lead time: seed `product_suppliers.standard_lead_time_days` (stated) and leave
`scm.supplier_performance` empty, or seed neither for the default.

## Slices and order

S1 then S2, one coder, one commit each. Reviewer + browser pass once, after S2.

## Prod follow-up (owner, after deploy)

Nothing to run. The OI-000739 links already written stay, each with its pill; owner reallocates
or unlinks from the lightbox. New ingests stop producing them.

## Backlog

- `lead_days == 0` would make every document promised on or before delivery "early".
  Measured on the 0915 prod copy: `product_suppliers.standard_lead_time_days` is 90 on all
  14,274 rows and `scm.supplier_performance` is empty, so not live. Clamp to a floor only if
  a zero lead time is ever stated.

- If a fixed "never link more than N days early" tolerance is ever wanted independent of lead
  time, that is one integer on `system_settings` read by `arrives_outside_window`'s callers.
  Trigger: an owner ruling that lead time is the wrong yardstick for a named product.
