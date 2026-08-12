# UAC - Project intelligence reports (brands and architects)

**Status:** scoped 2026-08-12, decisions taken with the client the same day. Pre-code.
**Closes the audit's two gaps:** brand intelligence by location and budget band, and the
architect ranking (`AUDIT-project-sales-2026-08-12.md` §1, the last two rows).

## Journey

**Who:** a sales manager, arriving from the sidebar: Project Sales → Forecast & Reports.
The page they already use for pipeline and conversion grows two tabs, **Brands** and
**Architects**. No new sidebar entry: intelligence is a view over the pipeline they
already read, not a place.

**Brands.** The manager opens the tab and reads one matrix: brands down the side, and a
dimension across the top they can flip between **state** and **budget band**. Every cell
is won ringgit, derived from the quotation lines of WON scopes - the paper the customer
accepted - never from anything anybody typed for the report's sake. The single decision
this tab supports: *which brand do we lead with, in this state, at this project size.*
They make it by reading; the screen asks them nothing.

**Architects.** One ranked table: every architect party, the projects they touch, won
RM, open pipeline RM, win rate, and when their pipeline last moved. Sorted by won RM.
The decision it supports: *who do we visit next* - and the row that answers it is high
pipeline + real past wins + gone quiet. Clicking an architect opens the party's own
page, which already lists their projects. Nothing new to maintain.

**Registration (the one journey change).** Below the free-text Location the salesperson
already types, a **State** select appears - auto-suggested from what they typed, so
"Bandar Bukit Raja, Klang, Selangor" arrives with Selangor pre-picked and the usual act
is confirming, not choosing. Existing projects are backfilled by the same matching, and
a project whose text names no state stays honestly Unknown until somebody edits it.

## Decisions taken (client, 2026-08-12)

1. **A brand wins through WON LINES, not through the registration multi-select.** The
   project-level brand list is intent ("brands being pushed"); the money is on the lines
   of the won scope. Derived, never asked (Phase 0 doctrine). The multi-select keeps its
   current job and gets no new one.
2. **Location dimension = a structured State field**, 16 Malaysian states/federal
   territories, auto-suggested at registration from the free text, backfilled for
   existing rows. Free-text Location stays for the address.
3. **Budget bands are fixed**: <RM500k, RM500k-2M, RM2M-10M, >RM10M, over
   `estimated_sales_value`. Configurable only if the fixed cut proves wrong.
4. **Architects rank by won RM with the activity columns beside it** - no composite
   score. A number nobody can argue with teaches nothing.

## Decisions taken at the grill (client, 2026-08-12)

5. **Won money is LIVE, valued at the scope's current version** - the client's call,
   against the freeze recommendation. A won scope revised from v5 (RM 1.8m) to v6
   (RM 2.1m) reports RM 2.1m from that moment, with no outcome re-recorded. The
   consequence is accepted knowingly: the report follows corrections automatically, and
   a period's number can change after the period closes. No ``won_version_id`` column;
   if the instability ever bites, THAT is the fix, and this line is where the decision
   to defer it lives.
6. **A year filter over ``decided_at``, defaulting to All time**, shared by both tabs.
   On Architects it filters won RM and win rate; open pipeline is inherently current
   and ignores it.
7. **Win rate counts SCOPES** - won scopes / decided scopes - the same unit the money
   columns sum over, so a row cannot disagree with itself. The mixed project (guard
   house won, towers lost) truthfully reads 1/3.

## Group A - the State field

- **AC-A1.** Project registration and the project edit form carry a State select with
  the 16 states/territories plus blank. Blank is legal: state is intelligence, not a
  gate, and a form that refuses a project over a report's dimension has its priorities
  backwards.
- **AC-A2.** Typing a Location that names a state (or a city whose state is
  unambiguous - Klang, Kepong, Ipoh) pre-selects the State. The user can override; the
  suggestion never fights an explicit choice.
- **AC-A3.** A backfill sets `state` on existing projects by the same matcher,
  idempotent, JOIN-based ("set to correct value where mismatch"), and reports how many
  rows it could not place rather than guessing.
- **AC-A4.** The matcher lives in ONE place (service), used by the form suggestion, the
  backfill, and nothing else re-implements it.

## Group B - the Brands tab

- **AC-B1.** The matrix shows won RM per brand, from the lines of quotation scopes
  whose outcome is WON, valued at the line totals of the scope's CURRENT version - live,
  per decision 5. Rate-only lines contribute nothing, exactly as the totals already
  compute. A test pins the live behaviour so it reads as chosen, not accidental.
- **AC-B2.** The brand of a line is its `brand_snapshot` - what the paper said -
  normalised against the brands table by name; a snapshot matching no brand appears
  verbatim in its own row, never silently dropped into Other.
- **AC-B2a.** The year filter (decision 6) restricts to scopes with ``decided_at`` in
  the chosen year; All time is the default and the empty-year case renders honestly.
- **AC-B3.** The column dimension flips between State and Budget band. A project with no
  state shows under **Unknown**; no estimated value shows under **Unstated**. Both
  columns render whenever non-empty - honesty about the gap is what makes the backfill
  worth running.
- **AC-B4.** Cells carry won RM and won line count; a row carries its total and share.
  Empty cells are blank, not zero.
- **AC-B5.** The whole tab is one backend read (`/reports/brands`), company-scoped like
  every other report, and answers in one query pass - no per-brand round trips.

## Group C - the Architects tab

- **AC-C1.** One row per architect party that is some project's ``architect_party_id``
  (stakeholder-linked firms are out of scope, stated), with: projects linked, won RM,
  open pipeline RM, win rate per decision 7, and last activity (the newest
  ``last_meaningful_activity_at`` across their projects). Sorted by won RM descending.
- **AC-C1a.** The year filter applies to won RM and win rate; pipeline ignores it
  (decision 6) and the screen does not pretend otherwise.
- **AC-C2.** Won RM and pipeline RM reuse the forecast service's own definitions -
  committed and pipeline respectively - never a second implementation of either number.
- **AC-C3.** An architect whose newest project activity is older than the staleness
  ladder's Unattended threshold carries a quiet-flag on the row. The flag reads from the
  same constants the ladder uses.
- **AC-C4.** The architect's name links to the party page. No new detail screen.
- **AC-C5.** One backend read (`/reports/architects`), company-scoped.

## Group D - conformance

- **AC-D1.** Both tabs are DataGrids under the standard toolbar contract (fixed layout,
  resizable, explicit sizes); money renders through `_shared/lib/money`.
- **AC-D2.** No explanatory prose on either tab. The labels are the explanation.
- **AC-D3.** pytest covers both report services on seeded chains (CI has no data);
  vitest covers the tabs' loading/empty/data states; one Playwright pass reaches both
  tabs by clicking from the sidebar.
