# PLAN: Order inquiry emails routed by who raised the order inquiry

**Status:** In build. Small fix track (no migration, no auth/RBAC change, no new ingest surface). Crew lane OI-ROUTE-BY-RAISER.

UAC: `oi-route-by-raiser-3nov-acceptance-criteria.md` beside this file. Builds on `PLAN-dealer-oi-route-1nov.md` (class routing).

## Journey

Owner, 3 Nov 22:50: "smc email i am thinking can set by raiser. Agnes is handling project orders at
project locations but I don't think Eling wants to be notified of that." In System Management >
Automation the owner sets Eling's project row to "Sales order class is Project AND Raised by is none
of [Agnes]" and adds a row "Sales order class is Project AND Raised by is any of [Agnes]" with the
people Agnes' orders should reach. Confirms, undos and "Send to purchasing" then follow those rows.

## Measured facts (origin/main 016d6823)

- The only OI email fact is `order_inquiry.salesOrderClass` (`app/rule_engine/registry.py:258-278`),
  read off the dispatch context (`automation_triggers.context_fact_sources`, `:325`).
- `dispatch_event` runs every enabled row whose conditions pass for the context (`automation_service.py:271-317`, `:567-591`).
- The confirm splits drained lines by class only (`handover_class_groups`, `project_order_inquiry_service.py:15164`), one dispatch per class (`:15512`). Undo: one decision per commit, one context (`_build_undo_context`).
- Resend picks the OLDEST enabled row passing for the class (`oi_handover_resend.handover_automation`, `:45-75`).
- The RuleBuilder renders an `enum` fact with options as a searchable multi select for in/not_in (`components/rule-builder/RuleBuilder.tsx:668-680`); options may be a callable(db, user) (`registry.py:18`). So a user-picker fact needs no FE code.
- The raiser is `order_inquiries.raised_by` (user id), read in `handover_item` (`:4736`).

## Build

1. **Fact.** `order_inquiry.raisedBy` ("Raised by"), enum, options = active users (name), resolved off context `raised_by` (a user id string).
2. **Items carry the raiser.** `handover_item` stamps `raised_by` (the OI header's, not the actor). The undo item carries it too; `_build_undo_context` puts it on the context.
3. **One email per matching row set.** `handover_route_groups(db, items)` replaces the class split: lines are grouped by (class, the set of ENABLED handover rows whose conditions pass for that line). Lines matching the same rows share one email; a line never goes to a row it does not match, and never twice. `build_handover_email` stamps the group's class and its first line's raiser on the context; every line in the group passes exactly the same rows, so `dispatch_event`'s own filter fires exactly that row set.
4. **Resend.** `handover_automations(db, facts)` returns every enabled row passing for the OI's class and raiser (the automatic send's rule); when no row is enabled, the oldest switched-off passing row (unchanged fallback). `_plan` yields one email per (OI, row); `send` sends each. `inquiry_total` counts distinct OIs.

## Not changed

- No migration, no FE code (the RuleBuilder already renders the picker), reserve emails untouched.
- A row with no raiser condition keeps matching every raiser: nothing changes on deploy.

## Tests

`tests/test_oi_route_by_raiser.py`.
