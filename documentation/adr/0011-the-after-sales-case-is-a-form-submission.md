# The after-sales case is a form submission, not a `complaints` row

**Supersedes ADR-0008 narrowly.** ADR-0008 said reuse the existing `complaints` table as the single
after-sales case. That is reversed for the *new* dealer-facing and consumer-facing flows, which are built
as **workflow form definitions** on the ported forms platform. `complaints` keeps **project** complaints
until the forms-platform migration reaches it (`plans/forms-platform/PLAN-forms-platform.md`, F4).

## What changed

Sorento decided to converge every form-shaped thing onto one engine - marketing forms, stock inquiry,
purchase request, sponsorship form and complaints - rather than add a fifth bespoke vertical. After-sales
is the first new work after that decision, so it goes on the engine rather than beside it.

The two after-sales flows also turned out to be different shapes, which the discovery study
(`flowcharts/Sorento_Operational_Discovery_Study_CS.pdf`) made clear:

- **Exchange / return request** - a Dealer asks to return or exchange goods. Commercial. Gated by CS,
  optionally producing an RMA, closing against a REP or a CN. Its own SOP
  (`SORENTO/SA-PRO/003`, Sales Returns Flow Chart), its own actors (Sales Admin, Warehouse, Finance).
- **Service complaint** - a fault needing attendance, spare parts or a plumber. Closest to what ADR-0008
  described.

Two definitions on one engine, rather than one table stretched over both.

## What ADR-0008 got right and keeps

**Its invariant survives intact, and must be enforced on the new substrate too:** one customer issue is
**one case**, never subdivided into more cases. The reasoning was never about the table - it was that
`"complaint"` is a member of `FORM_SLA_TYPES`, so a second case per issue means a second SLA clock, a
second portal card and a second satisfaction survey. That is equally true of a form submission once
`workflow_submission` joins that tuple (forms platform F2).

So the child-table shape ADR-0008 established carries across: execution lives in children (product lines,
Service Jobs, linked RMA/REP orders), never in a sibling case.

## What ADR-0009 and ADR-0010 keep

Unaffected. `service_jobs` is still requester-agnostic - its polymorphic `source_entity_type` /
`source_entity_id` now points at a submission instead of a complaint, which is exactly the flexibility
ADR-0009 was written to buy. Warranty Terms still scope to a Warranty Product Kind.

## Consequences

- **A dependency, not a merge.** After-sales depends on forms platform **F0 to F2** (document model, status
  on the submission, and the SLA / portal / notification / attachment integration layer). It does **not**
  depend on F4, so migrating the four existing forms is never on after-sales' critical path.
- **`complaints` becomes project-only by intent**, not by data. Live rows are `Project` 23, `SMC` 7,
  `Salesperson` 5, `Dealer` 4, `End User` 3, blank 7 - so 19 rows are already in what will be the wrong
  home. Someone must decide per row whether they migrate or age out; this ADR does not decide it.
- **The rebuild cost is real and was accepted knowingly.** `complaints` already carries lifecycle, SLA
  integration, portal submission, the Respond conversation panel, fulfilment-order linkage, root causes and
  resolutions. Rebuilding that as form definitions plus the F2 integration layer is a re-implementation, not
  a schema change. It is justified only because the platform serves five form types, not one.
- **The one-case invariant needs a guard on the new substrate.** A test must assert that one customer issue
  yields one submission, one SLA thread, one portal card and one survey - the same property ADR-0008
  protected, now on a different table.
