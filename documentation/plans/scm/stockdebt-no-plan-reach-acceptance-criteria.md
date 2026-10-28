# UAC: STOCKDEBT-NO-PLAN-REACH - a decided line draws as if undecided in Stock Debt

Plan: `PLAN-stockdebt-no-plan-reach-28oct.md`. Status: agreed (owner rule 28 Oct ~09:40).

- **AC-NPR-1 (equivalence).** For every board decision shape (Reserve own / BRW / group take, Borrow at a
  sibling bin, another group or a site pool, Buy) and both the project book and the whole book, every
  line of the product reads the same status, shortfall and sources in the Stock Debt view as when the
  decision is removed.
- **AC-NPR-2 (CB4702).** Project book: three open lines at a project bin with no stock (364, 256, and 36
  planned "Reserve from BRW"), BRW holding 477. All three read short; the 36 line reads Short 36 with no
  source; the month owes 656. No Covered by names a source the Supply tab does not list.
- **AC-NPR-3 (board unchanged).** The board / ladder walk (`assignments_for`, `planning_assignments`) still
  takes the same Reserve-from-BRW as a route and covers the 36 line; capped stand-ins, earliest-due sharing
  and the next-route rule still hold there.
- **AC-NPR-4 (unchanged binders).** OI placement links on an incoming SPO (AutoCount's auto copy and
  hand-made) still pin their SO in the view.
- **AC-NPR-5 (received SPO kept).** A received SPO is not supply, and its on hand stays with the linked SO
  rather than going to an earlier line at the bin.
