# Project registration is exclusive, enforced by fuzzy match, and always offers recourse

The single most-cited problem in the client's spec is salespeople clashing on the same
property development. Within a company, one development = one Project. Identity is
**Developer (a FK, so "SP Setia" and "S P Setia" cannot fork the namespace) + normalised
title**, with Location as tiebreak. `developer_party_id` and `normalised_title` live on the
`projects` table itself - not on the sales-profile extension - so the unique constraint
`(company_id, developer_party_id, normalised_title)` is enforceable in a single table. It backs
a `pg_trgm` similarity check (GIN `gin_trgm_ops`, threshold a system setting) run at create
time.

Developer is **optional on the form**, and an unstated developer must not weaken the lock.
The check was originally scoped to `developer_party_id == <the value given>`, which meant a
blank Developer field compared the title only against other developer-less projects - in
practice against nothing, so re-registering a claimed title sailed through and the lock became
opt-out with an optional field as the opt-out. A blank developer now searches **every**
developer, and a title at or above the blocking bar (or one containing an existing title)
blocks. The verdict is "sameness cannot be ruled out", not "these are the same": naming a
different developer clears it immediately, so the block is self-correcting as the form is
filled in, and the panel says so rather than only offering join / dispute.

Only projects whose derived outcome is **open** block a new registration. A lost or dormant
match is surfaced as context - "previously pursued by Ali, lost on price, Mar 2024" - and the
registration proceeds. A re-tender three years later must not be blocked by an old loss.

On collision the second salesperson is **blocked** - but never dead-ended. They see the
incumbent's owner, current stage, last activity date and brands, and get two actions:
*request to join as collaborator* (owner or manager approves) or *dispute / request takeover*
(routes to the sales manager with a reason). The recourse path is load-bearing: hard blocking
with no way out produces defensive land-grabbing and pushes the conflict back into WhatsApp,
which is the pain being solved.

Projects are company-scoped, so the lock is per company. Phase 1 has one company using it
(SRT); MOCHA exists but owns no products, customers or brands yet.

## Consequences

- All salespeople can **see** every project read-only. This is the mechanism, not a side
  effect - the collision screen only works if the incumbent is visible. Edit rights stay with
  owner + approved collaborators; management sees financial detail.
- The day-one Excel migration must be a **single consolidated management-run import**, with
  the owner assigned in a spreadsheet column. Ten salespeople importing their own sheets would
  make import order decide ownership. The importer reports collisions as job errors rather
  than silently creating duplicates.
- A registration goes stale on inactivity (measured from the activities feed: any human post,
  plus a whitelist of meaningful system events) or an overdue committed next-action date. The
  ladder is nudge → warn owner and manager → "Unattended" badge that opens it to takeover
  requests. **A manager always pulls the trigger; nothing auto-reassigns** - someone on
  medical leave must not silently lose their pipeline.
