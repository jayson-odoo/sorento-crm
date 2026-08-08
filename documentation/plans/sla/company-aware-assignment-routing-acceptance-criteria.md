# Company-aware assignment routing - acceptance criteria

> Status: GRILLED 2026-08-09, decisions settled with the user, no code written yet.
> Context: two companies live under the stubbed tenant - Sorento (`SRT`,
> `00000000-0000-0000-0000-000000000001`) and Mocha (`MOCHA`,
> `5e2c68f5-1b35-4f1d-a6e0-e904c0d8260f`). Both share one Respond.io workspace and one
> WhatsApp number (`space_id=364817`, "Sorento Support"). Related: multi-company isolation
> (`documentation/plans/PLAN-multi-company-isolation.md`), market-segment routing
> (`app/services/market_segment_service.py`).
>
> Guardrail: routing must never break. Every resolution step degrades to a defined default;
> no step is allowed to 500 or to return "any company's team".

## Journey

### The customer - never sees any of this

Messages the one WhatsApp number. They are a Sorento customer or a Mocha customer; they do not
say so and are never asked. The system already knows: the contact record carries its company
(`respond_contact_companies`, admin-managed, 58 of 61 contacts tagged today, none in both).

1. They send a message about a promotion.
2. They get a reply from a person who actually handles that brand.

Nothing in the conversation changes. The whole feature is invisible from this side, which is the
point: the company is **derived, never asked**.

### n8n - the router, sends no new field

Classifies intent and calls `POST /api/v1/external/next-assignee` with the same body it sends
today: `contact_phone_number`, `agent_code`, `team_code`, `tier`, and optionally
`policy_code` + `tier`.

1. It does **not** learn about companies. Adding a company decision to the workflow would put
   routing correctness in two places.
2. The backend answers with the assignee **and** echoes which company it resolved, so a
   misrouting is diagnosable from the n8n execution log alone.

### The assigned staff member - gets only their own brand's work

Today a Mocha promotion enquiry can land on a Sorento marketer, because the round-robin pool is
whichever team the team-set code happens to point at.

1. The conversation arrives assigned to them.
2. When it breaches SLA it escalates up **their company's** ladder, not the other one's.

### The admin - configures it once, in the place they already configure teams

Opens Access Agents, then an agent, then Team Sets. The workaround they invented is visible in
the data: `marketing_promotion_sorento` and `marketing_promotion_mocha` are two team-set codes
that mean one team set in two companies.

1. A team now belongs to exactly one company. Mocha teams are built by hand, alongside the
   Sorento ones; the same person may sit in both companies' teams.
2. Each team-set row is therefore company-specific, and the duplicated codes can collapse: one
   `marketing_promotion` code with a Sorento row and a Mocha row per tier.
3. The Teams page follows the company switcher, like every other company-scoped resource.

### Whoever tags contacts - the one new obligation

Because the two brands share one channel, an untagged inbound contact has no company signal at all.

1. An untagged contact routes to Sorento (the incumbent), so nothing stalls.
2. The contact's Companies field is where a human corrects that, and it already exists on Edit
   Contact.

## Decisions taken (post-grill)

- **D1. A team belongs to exactly one company.** `teams.company_id` NOT NULL. The earlier draft
  put company only on the `agent_teams` link so teams could be shared; that was reversed in the
  grill. A ladder shared by both brands (Retail Director) is modelled as one team per company
  holding the same people.
- **D1b. `agent_teams` carries `company_id` too, but cannot drift.** `teams` gains a unique
  `(id, company_id)`; `agent_teams` gets a composite FK `(team_id, company_id)` referencing it.
  Postgres enforces the copy matches the team's real company - no trigger, no sync code. The
  column exists so `(agent_id, code, tier, company_id)` is indexable and the resolver needs no
  join.
- **D2. No `respond_workspaces.company_id` in v1.** One shared channel, so a workspace-to-company
  column would be dormant the day it shipped. Add it when Mocha gets its own number; the
  resolution order below leaves the slot open.
- **D3. n8n sends no new field.** Company is derived server-side from the contact. `company_code`
  is accepted as an override for tests and future use, not as the normal path.
- **D4. Phone is a valid contact identity for ROUTING resolution only.**
  `respond_contacts.phone_number` is unique and `contact_phone_number` is already required by the
  endpoint. Phone is deliberately **not** taught to `company_scope_resolver` - see D6.
- **D5. SLA policies are per company.** `sla_policies.company_id` NOT NULL; the global
  `sla_policies_code_key` is replaced by unique `(code, company_id)`.
- **D6. Two company resolvers exist on purpose, with opposite empty-case behaviour.**
  `company_scope_resolver` (request data isolation) fails closed: unknown contact means zero rows.
  `company_routing_service` (assignment) coalesces: unknown contact means Sorento. Merging them
  would make an untagged contact unroutable.
- **D7. `teams` is a fully company-scoped resource** (`CompanyScopedMixin`), not a plain column.
  Teams drive SLA assignment and, via the hierarchy, the coverage-subscription picker; nothing
  else.
- **D8. `agent_teams` is company-scoped too, but `access_agents` is NOT.** An access agent is one
  router serving both brands through two ladders. The Access Agents list is identical in every
  company; what changes with the switcher is the Team Sets rows inside an agent. Making agents
  per-company was considered and rejected: it duplicates every agent and every
  `contact_agent_access` grant, forces `access_agents.code` unique to become `(code, company_id)`,
  and inverts the external resolution order (agent is resolved before the contact today), which
  would breach D3.

## Acceptance criteria

### A. Company resolution (routing)

- **AC-A1.** `next-assignee` resolves a routing company by first hit of: (a) body `company_code`,
  (b) the contact's single `respond_contact_companies` row, (c) the default company
  `00000000-0000-0000-0000-000000000001`.
- **AC-A2.** The contact is identified by `contact_id` / `respond_io_id` when present, else by
  `contact_phone_number`. A phone-only call resolves the same company as an id-only call for the
  same contact.
- **AC-A3.** A contact belonging to more than one company resolves to no company from step (b) and
  falls through to the default. It never picks one arbitrarily. The response says so via a status
  flag (`ambiguous_company`).
- **AC-A4.** An unknown contact and an untagged contact resolve to the default company. A malformed
  or unknown `company_code` is not a hit, so resolution continues down AC-A1's order and lands on
  the contact when it has one, else the default: a typo must not override a correctly tagged
  contact. None of these returns 4xx or 5xx.
- **AC-A5.** The response includes `company_id`, `company_code`, and a `company_source` of
  `body` | `contact` | `default`.
- **AC-A6.** `company_scope_resolver` is **not** extended to resolve by phone. Its empty case is
  zero rows; routing's empty case is Sorento (D6). A test pins that an untagged contact still gets
  an assignee.

### B. Market-segment scoping (existing feature, currently dead on the phone-only path)

- **AC-B1.** Market-segment scoping fires for a call that passes `contact_phone_number` only.
  Today it fires only on `contact_id` / `respond_io_id` (`next_assignee.py:341-355`), so a
  phone-only caller silently gets an unfiltered pool.
- **AC-B2.** Segment and company are independent axes: a Mocha and retail contact is scoped by
  both. The round-robin cursor stays per-segment (`segment_key`) within the company's team.

### C. Team resolution by company

- **AC-C1.** `teams.company_id` is NOT NULL, with a unique `(id, company_id)` supporting the
  composite FK below.
- **AC-C2.** `agent_teams.company_id` is NOT NULL with FK `(team_id, company_id)` referencing
  `teams(id, company_id)`. Inserting a link whose company disagrees with the team's company is a
  database error, not an application check.
- **AC-C3.** `agent_teams` unique keys gain company: `(agent_id, code, tier, company_id)` where
  `tier IS NOT NULL`, and `(agent_id, code, company_id)` where `tier IS NULL`.
- **AC-C4.** Resolving (agent, team-set code, tier) requires a company and returns only that
  company's team.
- **AC-C5.** When the resolved company has no row for that (code, tier), the resolver returns
  nothing for that tier. It does **not** fall back to another company's team. A 404 naming the
  company beats a silent cross-company assignment.
- **AC-C6.** `get_team_id_by_tier` raises an explicit conflict when more than one row survives
  filtering, instead of returning `rows[0]` as it does today
  (`app/services/user_service.py:2235`). Without this, the first duplicate company row becomes a
  silent wrong-company escalation.
- **AC-C7.** `teams.parent_team_id` must reference a team in the **same** company. Enforced on
  write next to the existing cycle guard (`user_service.py:2406`), because
  `descendant_team_ids` grants a parent team's members visibility and act rights over every
  descendant at any depth - a cross-company parent is a data leak.
- **AC-C8.** `agent_teams.policy_id` must reference a policy in the same company, enforced the
  same way as AC-C2 (unique `(id, company_id)` on `sla_policies`, composite FK from
  `agent_teams`).

### D. Round-robin

- **AC-D1.** The rotation pool is the members of the resolved company's team. Cursor isolation is
  automatic (`agent_team_round_robin_cursors` is keyed by `team_id`); no cursor schema change.
- **AC-D2.** Two consecutive calls for a Sorento contact and a Mocha contact against the same
  (agent, code, tier) advance two independent cursors and return members of different teams.
- **AC-D3.** `preferred_assignee_id` is validated against the **resolved company's** team. A member
  of the other company's team is a 404, with the resolved company in the message.

### E. Consistency across every other assignment path

- **AC-E1.** `GET /external/team-members` applies the identical company and segment filter, so an
  id it returns is always accepted by a subsequent `next-assignee` call.
- **AC-E2.** `conversation_sla_tracking.company_id` is NOT NULL. It is stamped at creation from
  the routing company and is the sole company source for every later read of that tracker.
- **AC-E3.** Escalation climbs tiers within the tracker's company. `POST /sla/integration/escalate`
  (`sla_tracking.py:858`) needs no n8n change: it already resolves the tracker first, so the
  company comes off the tracker.
- **AC-E4.** Form-SLA trackers stamp company from the spawning entity's contact (complaints,
  purchase requests, sponsorship forms and stock inquiries all carry `contact_id`). A contact in
  more than one company, an entity with no contact (`tickets` has no contact column at all), or an
  unresolvable contact all stamp Sorento.
- **AC-E5.** Every call site that resolves a team by (agent, code, tier) supplies a company:
  `form_sla_service:501,790`, `sla_service:2160,2651`, `complaints_service:915,1279`,
  `procurement_service:2439,5744`, `cs_routing_service:78`, `handling_lock_service:86`,
  `tickets_service:1072`, `next_assignee:108,112`. The company comes from the tracker
  (AC-E2) or from the entity's contact (AC-E4). It is never re-derived from the request.
- **AC-E6.** A `respond_contact_cs_routing` pin only wins when the pinned user is a member of the
  resolved company's team; otherwise it falls back to round-robin exactly as an inactive pin does.

### F. Company scope plumbing

- **AC-F1.** `teams` and `agent_teams` carry `CompanyScopedMixin`. `access_agents` does not (D8).
- **AC-F2.** Every scheduler session sets `set_company_scope(db, None)`.
  `app/scheduler/task_scheduler.py` opens raw `SessionLocal()` at `:365,384,402,463` and never
  sets a scope, so it sits at the `UNSET` default, which is zero rows
  (`app/models/base.py:53-56`, `app/database.py:40`). Without this,
  `form_sla_overdue_scan` (`:245`) reads zero teams and escalation stops **silently**.
  Precedent: `import_tasks.py:76`, `export_tasks.py:29`.
- **AC-F3.** `next-assignee` sets the request scope to the single **coalesced** routing company
  (AC-A1), not to the contact's raw company set. An untagged contact therefore runs the request
  under Sorento rather than under the empty set.
- **AC-F4.** A regression test asserts the overdue scan escalates at least one tracker with the
  scheduler's own session setup, so a future scope change cannot silently zero it.

### G. Team membership and company grants

- **AC-G1.** A user may only be added to a team when they hold a `user_companies` grant for that
  team's company. Validated on team-member write.
- **AC-G2.** The migration **reports** existing `team_members` rows whose user lacks a grant for
  the backfilled company; it does not delete them. Removing a person from a team silently changes
  live routing.

### H. Admin configuration

- **AC-H1.** Team create/edit requires a Company. The Teams list follows the active company.
- **AC-H2.** The Access Agents list is the same under every company (D8). Opening an agent shows
  only the active company's Team Sets rows, and the team picker offers only that company's teams.
  Switching company on an open agent re-reads its rows.
- **AC-H2b.** An agent with no team sets in the active company still appears in the list, and its
  Team Sets tab renders an explicit empty state with an add CTA. It is never hidden
  (`docs/ADR-PRODUCT-STANDARDS.md`: always render every section).
- **AC-H3.** Saving two rows with the same (code, tier, company) is rejected with a readable
  message. Same (code, tier) under different companies is valid and is the new normal.
- **AC-H4.** The tier-1 invariant (`_validate_tier1_invariant_for_assignments`) is evaluated per
  company: a team set with a Mocha tier 2 but no Mocha tier 1 is rejected.

### I. Migration and backfill

- **AC-I1.** Every existing `teams`, `agent_teams`, `sla_policies` and
  `conversation_sla_tracking` row is backfilled to the default company. No routing behaviour
  changes on deploy for any Sorento conversation.
- **AC-I2.** The migration creates **no** Mocha rows. Mocha teams, team sets and policies are
  built by an admin before any contact is tagged Mocha. This is what makes AC-C5's hard 404 safe.
- **AC-I3.** The company-suffixed codes (`marketing_promotion_sorento`,
  `marketing_promotion_mocha`) are **not** auto-collapsed. They are left intact and re-pointed by
  an admin afterwards, because collapsing them rewrites live routing.
- **AC-I4.** The migration is reversible: downgrade drops the columns and restores the prior
  unique indexes, including the global `sla_policies_code_key`.

### J. Fail-safety

- **AC-J1.** No routing-company resolution step raises. Failures are logged and degrade to the
  default (mirrors `_portal_token_scope`, which already resolves contact companies this way).
- **AC-J2.** A pytest asserts a Mocha contact never receives a Sorento assignee for a team set
  configured in both companies. The single test that would have caught the whole class of bug.

## Out of scope

- Per-company Respond.io workspaces and WhatsApp numbers (D2).
- Auto-tagging a new inbound contact's company. Untagged means Sorento until a human says
  otherwise.
- `company_id` on complaints, purchase requests, stock inquiries or tickets. Those tables have no
  company column and are not gaining one here; form-SLA company comes from the contact (AC-E4).
- Any change to the n8n workflow.
