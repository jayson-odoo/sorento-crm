# PLAN - The Edition revision workflow (S2.5)

**Status:** written 2026-08-03, NOT yet grilled and NOT started. Unblocked today
by the status engine reaching `main`. Needs the user's grill before code, per
`feedback_grill_plan_before_implementing`.
**Companion UAC:** `dealer-kit-builder-acceptance-criteria.md`, **Group L**
(AC-L1 to AC-L9), plus AC-A9 for the permission. Already written during the S1
grill, so this plan builds against existing ACs rather than inventing new ones.
**Blocked on:** nothing. Verified 2026-08-03 that the status engine is present
(`statuses`, `status_transitions`, 38 seeded rows) and that `dealer_kit` holds
no `edition` table, so this is a from-scratch slice.

---

## Phase 0 - the journey

**The actor is a Designer** who has been asked to produce next season's
catalogue. They arrive from the sidebar, at Catalogue Pages.

**What the system already knows:** last season's Edition, its layout, every
product in it, which of those are now discontinued, which products have appeared
since, and current stock. None of that is asked for.

1. **"Start next Edition."** One click on last season's catalogue. They do NOT
   pick a template, re-add products or rebuild a grid: the new Edition opens as
   a copy of the last one, with discontinued products already struck through,
   products new since the last Edition already badged, and stock shown per
   product (AC-L9). The single decision at this step is what to call it.
2. **They edit.** Ordinary builder work. The Edition sits in `draft` and no
   reader can see it, because a version with no label pointing at it is already
   unreachable - the same mechanism the flyer seed relies on.
3. **"Send for approval."** One decision: it is ready or it is not. The Edition
   moves to `pending_approval`. The Designer cannot approve it, including their
   own (AC-L3).
4. **The Approver opens it** from a queue, sees the catalogue as a reader would,
   and makes one decision: approve or reject. Rejecting asks why, and the reason
   is what the Designer sees.
5. **Approved is not published.** The Approver still holds the decision of WHEN
   it goes live. Moving it to `done` is what moves the `published` label
   (AC-L7), and that is the only transition that publishes anything.
6. **Prices move after approval, and that is expected.** A price correction
   keeps the Edition `approved` (AC-L5); any other edit drops it back to
   `pending_approval` (AC-L4), because an approved Edition must never ship
   silently altered. At `done` the Approver can diff approved-vs-done in one
   action and see exactly which prices changed after they signed it (AC-L6).

**What they hold at the end:** a live catalogue, and a record of who approved
what and what moved afterwards.

**What everyone else is told:** the Designer learns of an approval or rejection
with its reason; nobody else is notified, because publishing a catalogue is not
an event other staff act on.

## What already exists, and is therefore not being built

- **The status engine** (ADR-0001), core, in `main`. `statuses` +
  `status_transitions`, keyed by `entity_type`, with `is_initial` / `is_terminal`
  traits, per-scope graph forking, and `assert_transition_allowed`. AC-L1 says
  explicitly this must drive the Edition, NOT a bespoke enum with hand-written
  checks.
- **Immutable versions and a movable label** - `page_version` plus `page_label`,
  the mechanism S1 shipped and S7.4 leaned on. "Publishing" is moving the
  `published` label, which already exists and needs no new concept.
- **The rule engine** (`app/rule_engine/`), if the price-only test in AC-L4/L5
  is better expressed as a condition tree than as code.

## The design

**An Edition is a named revision cycle over a page**, not a new document. It
points at the page it revises and at the versions that mattered:
`approved_version_id` and `done_version_id` (AC-L5 requires both).

**`dealer_kit.edition`**

| column | why |
|---|---|
| `page_id` | the catalogue being revised |
| `name` | "Spring 2027" - the one thing step 1 asks for |
| `status_id` | FK to `statuses`, entity_type `dealer_kit_edition` |
| `approved_version_id`, `done_version_id` | the diff in AC-L6 is between these two |
| `approved_by`, `approved_at`, `rejection_reason` | who decided, and why if no |
| `previous_edition_id` | what it was duplicated from, for the "new since" badge |

Company-scoped via `CompanyScopedMixin`, like every other owned table. Note the
`test_company_scope` guard asserts the owned-table count and WILL fire - that is
intended, and the count goes up with the reasoning recorded.

**Statuses seeded for `dealer_kit_edition`:** `draft` (initial),
`pending_approval`, `approved`, `rejected`, `done` (terminal). Transitions
manual throughout. AC-L8 needs `done -> draft`, which means `done` cannot
actually be `is_terminal` - **this is the first thing to settle in the grill**,
because it contradicts the natural reading of the state list.

**The permission** is `dealer_kit.edition.approve` (AC-A9), a sixth slug, not
implied by `page.edit` or `page.publish`, with a grant sweep so somebody holds
it on day one.

## Slices

**S2.5.1 - Schema and statuses.** Migration, `edition`, the seeded graph, the
permission plus sweep. Test-first: the graph validates, exactly one initial, and
a Designer cannot approve.

**S2.5.2 - The transitions.** Submit / approve / reject / publish routes, each
through `assert_transition_allowed` rather than an `if`. AC-L7's label move
happens here and ONLY here.

**S2.5.3 - The drop-back rule.** AC-L4 and AC-L5: what counts as "only prices".
Deserves its own slice because it is the one piece of real logic, and getting it
wrong ships an altered catalogue under an old approval.

**S2.5.4 - The diff.** AC-L6, approved version against done version, prices only.

**S2.5.5 - Duplication.** AC-L9. The biggest one: inherit layout, strike
discontinued, badge new-since, show stock. Touches products and stock, not just
the Kit.

**S2.5.6 - The screens.** Designer's submit, Approver's queue and decision,
rejection reason on the Designer's side.

## Open questions for the grill

1. **Is `done` terminal or not?** AC-L8 moves `done -> draft`, so it cannot be
   `is_terminal` in the engine's sense. Either AC-L8 means "start a NEW Edition
   from this one" (which is AC-L9, and then `done` IS terminal), or Editions are
   genuinely reopenable. These are different products and the ACs currently
   imply both.
2. **What exactly is "a price field"** for AC-L4/L5? A tile shows bound prices
   resolved per viewer, and the document stores no prices at all (a price string
   in a saved doc is a defect, per S1). So a "price edit" is not an edit to the
   document - it is a change to a promotion or a price list OUTSIDE it. That may
   mean AC-L4/L5 are about something the Edition cannot observe by diffing its
   own versions, which would change the design substantially.
3. **One Edition open per page, or several?** The plan assumes one; nothing in
   Group L says so.
4. **Does rejection go back to `draft` or stay `rejected`** until the Designer
   picks it up? Affects whether `rejected` is a state or an event.
5. **Who is the Approver in practice** - a role, or a named person per page?
