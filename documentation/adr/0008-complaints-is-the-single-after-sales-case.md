# `complaints` is the single after-sales case; execution lives in child tables

> **Status: superseded (narrowly) by `adr/0011`, 2026-08-01.** Sorento decided to converge every
> form-shaped thing onto one forms engine, so the new after-sales flows are **workflow form definitions**
> rather than `complaints` rows, and `complaints` keeps project complaints. **The invariant below survives
> and must be enforced on the new substrate:** one customer issue is one case, never subdivided, because a
> second case per issue means a second SLA clock, portal card and survey. Read this ADR for that reasoning;
> read `adr/0011` for where the case now lives.

After-sales for the dealer channel reuses the existing `complaints` table rather than adding a
second case entity, and a Complaint is never subdivided into more Complaints. Work done to settle
it (product lines, Service Jobs, linked RMA/REP orders) lives in children, so one customer issue
is always one row.

## Why not a child Complaint per unit of work

The tempting shape is `parent_complaint_id`, making a collection, a replacement and a site visit
each a child Complaint row. Three things in this codebase make that wrong:

- `"complaint"` is a member of `FORM_SLA_TYPES` (`form_sla_service.py`). Every Complaint row spawns
  its own SLA tracker, its own escalation ladder and its own handling lock. One leaking bidet that
  needs a collect-back and then a replacement would run three independent clocks and escalate three
  times to three managers.
- The portal renders one card per submission. The homeowner who reported one fault would see three
  "complaints", receive three status threads and be sent three satisfaction surveys.
- A child would inherit roughly forty case-level columns that are meaningless on a visit
  (`within_warranty`, `root_cause_id`, `resolution_id`, `customer_type`, `respond_inbox_url`,
  `rejection_reason`). Nullable-everything is how a table stops being reviewable.

## Why the existing table, and not a new one

`complaints` was never project-only. Live data at the time of the decision: 50 rows with
`customer_type` spanning `Project` 23, `SMC` 7, `Salesperson` 5, `Dealer` 4, `End User` 3,
`E Commerce` 1. Dealer and consumer cases already lived there. `project_title` is populated on 28
of 50 and is an optional field, not the table's reason for existing.

The column was, however, incoherent: `customer_type='End User'` held company names
(`SETIAKON BUILDERS SDN BHD`), and `customer_type='Salesperson'` did too. It could not decide
whether it meant *who reported this* or *what kind of account this is*. It becomes
`reported_by_role`, which is what it was always trying to say, and the parties it was conflating
get their own homes: Dealer as a `customers` FK, Submitter as the `respond_contacts` FK that
already exists, Salesperson derived from the dealer's `account_owner_user_id`, and the Site on the
Complaint (because one Consumer may have several, and a Dealer's shop is a Site as readily as a
home).

## Consequences

- Reporting on after-sales must filter `complaints` by `reported_by_role` or by the presence of
  child rows. There is no separate table to count.
- The one-clock, one-thread, one-survey guarantee is load-bearing. Any future feature that wants a
  second SLA clock on the same issue must put it on a child (a Service Job), never on a second
  Complaint.
- `complaint_fulfilment_orders` gains a link role so a collection (`RMA`) and a replacement (`REP`)
  are distinguishable. Both were already `orders` rows; only the link was missing.
