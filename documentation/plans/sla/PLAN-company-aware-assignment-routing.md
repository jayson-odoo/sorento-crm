# PLAN - Company-aware assignment routing

> Status: GRILLED 2026-08-09, not started. Contract for
> `documentation/plans/sla/company-aware-assignment-routing-acceptance-criteria.md`.
> Read the UAC first; every step below traces to an AC.

## Problem in one line

`teams` has no company and `agent_teams` maps (agent, team-set code, tier) to a team with no
company axis, so a Mocha conversation and a Sorento conversation resolve to the same team. The
current workaround encodes the company in the code itself
(`marketing_promotion_sorento` / `marketing_promotion_mocha`), which does not survive escalation
and does not compose with SLA policy per team set.

## Shape of the change

A team belongs to one company. Everything else follows from that.

```
contact (phone or respond_io_id)
  -> respond_contact_companies              (existing, admin-managed)
  -> routing company  (coalesced to Sorento when unknown / ambiguous)
  -> agent_teams (agent_id, code, tier, company_id)
       FK (team_id, company_id) -> teams(id, company_id)     <- cannot drift
  -> team_id
  -> round-robin over team_members          (cursor already per team_id, unchanged)
```

Stamped once at tracker creation, then read back for every escalation:

```
conversation_sla_tracking.company_id  NOT NULL
  conversation SLA -> the routing company resolved at create
  form SLA         -> the spawning entity's contact's company, else Sorento
```

## The two resolvers (do not merge them)

| | `company_scope_resolver` | `company_routing_service` (new) |
|---|---|---|
| Purpose | request data isolation | pick an assignee |
| Unknown contact | `frozenset()` -> 0 rows | Sorento |
| Knows about phone | no, deliberately | yes |
| Multi-company contact | the union | none of them, falls to Sorento |

Same input, opposite empty-case semantics. Teaching the scope resolver about phone would make
every untagged contact unroutable (AC-A6).

## Contract

### `POST /api/v1/external/next-assignee`

Request: unchanged. `company_code` accepted as an optional override (D3).

Response gains three fields; everything existing is untouched:

```jsonc
{
  "assignee_id": "...",
  "company_id": "5e2c68f5-1b35-4f1d-a6e0-e904c0d8260f",
  "company_code": "MOCHA",
  "company_source": "contact",          // body | contact | default
  "status_flags": ["ambiguous_company"] // added to the existing flag list when AC-A3 fires
}
```

`policy_code` lookup changes behaviour: `next_assignee.py:43` does
`.filter(SLAPolicy.code == policy_code).first()` against a globally unique code. With per-company
policies it filters by the resolved company, and a code that exists only in another company is a
404 naming the company (same rule as AC-C5).

### `GET /api/v1/external/team-members`

Query gains optional `company_code`. Roster is filtered to the resolved company's team (AC-E1).

### Internal

```python
# app/services/company_routing_service.py  (new)
def resolve_routing_company(
    db, *, company_code=None, contact_id=None, space_id=None, phone=None
) -> tuple[str, str]:      # (company_id, source) - never raises  (AC-A1..A5, AC-J1)
```

```python
# app/services/user_service.py - AccessAgentService, all gain a required company_id
get_team_id_by_tier(agent_id, tier, team_set_code=None, *, company_id)
get_team_id_by_code(agent_id, code, *, company_id)
list_team_ids_for_agent_code(agent_id, code, *, company_id)
get_tier_team_and_notify(agent_id, tier, team_set_code=None, *, company_id)
resolve_team_with_tier_fallback(agent_id, start_tier, team_set_code=None, *, company_id)
get_user_tier_in_team_set(agent_id, user_id, team_set_code=None, *, company_id)
resolve_policy_id_for(agent_id, team_set_code, *, company_id)

# app/services/sla_service.py
get_escalation_assignee_for_tier(..., *, company_id)
_tracking_company_id(tracking) -> str      # the tracker's company, never the request's
```

Two of these were not in the original draft and were found while implementing.
`get_team_id_by_code` is a second lookup path used by the complaint and procurement
fallbacks. `resolve_policy_id_for` matters more than it looks: it returns the DISTINCT
policy ids bound to a team set and raises a 409 on more than one, so once a team set
exists in two companies it would raise a bogus "inconsistent binding" error on every
conversation-SLA create.

Keyword-only and required, deliberately: a positional optional would let a call site silently keep
the old cross-company behaviour, which is exactly the bug class being closed. A missed call site
is a TypeError at import or test time, not a misroute in production.

## Slices

### S0 - Company resolution, observable but inert

`app/services/company_routing_service.py`. Resolve company from body, contact, or default; add the
phone fallback used by BOTH routing and market-segment resolution (AC-A2, AC-B1). Wire into
`next_assignee.py` so the response echoes `company_*` while team resolution is untouched.

Ships alone. Lets us watch real n8n traffic and confirm which company every live conversation
would have resolved to, before any routing changes.

- `app/services/company_routing_service.py` (new)
- `app/services/market_segment_service.py` - phone fallback in `resolve_contact_segments`
- `app/api/v1/external/next_assignee.py` - resolve and echo
- pytest: resolution matrix (body / contact / phone / unknown / untagged / multi-company / bad
  code), plus AC-A6 (scope resolver still phone-blind)

### S1 - Scope plumbing, no schema

Independent of the migration and safe to ship first, because it is a no-op until `teams` becomes
scoped - and it is the thing that silently breaks escalation if forgotten.

- `app/scheduler/task_scheduler.py` - `set_company_scope(db, None)` at each `SessionLocal()`
  (`:365,384,402,463`) (AC-F2)
- `next_assignee.py` - set request scope to the coalesced routing company (AC-F3)
- pytest: overdue scan escalates under the scheduler's own session setup (AC-F4)

### S2 - Migration

Run `alembic heads` and confirm a single head before writing `down_revision`. The filesystem head
lies after a branch merge, and this branch has already re-chained once.

- `teams`: add `company_id` UUID FK to `companies.id`, backfill default company, set NOT NULL,
  add unique `(id, company_id)` (AC-C1, AC-I1)
- `teams`: check that no `parent_team_id` crosses companies post-backfill (trivially true, one
  company) (AC-C7)
- `sla_policies`: add `company_id`, backfill, NOT NULL, add unique `(id, company_id)`, drop
  `sla_policies_code_key`, add unique `(code, company_id)` (D5, AC-C8)
- `agent_teams`: add `company_id`, backfill, NOT NULL, composite FK `(team_id, company_id)` to
  `teams(id, company_id)` and `(policy_id, company_id)` to `sla_policies(id, company_id)`
  (AC-C2, AC-C8)
- `agent_teams`: drop `uq_agent_teams_agent_code_tier_null` and
  `uq_agent_teams_agent_code_tier_not_null`, recreate with `company_id` in the key (AC-C3)
- `conversation_sla_tracking`: add `company_id`, backfill all rows to default, NOT NULL
  (AC-E2, AC-I1)
- report `team_members` rows whose user lacks a grant for the backfilled company; do not delete
  (AC-G2)
- create no Mocha rows (AC-I2); leave the suffixed codes alone (AC-I3)
- downgrade drops the columns and restores every prior index including `sla_policies_code_key`
  (AC-I4)

### S3 - Thread the company through the resolvers

`AccessAgentService` signatures above, plus AC-C6: `get_team_id_by_tier` raises an explicit
conflict on more than one surviving row rather than returning `rows[0]`.

Then the call sites. Each needs a source for the company, and the source is the tracker or the
entity's contact - never the request:

| Call site | Company source |
|---|---|
| `next_assignee.py` | routing company resolved in S0 |
| `team_members.py` (via `_resolve_round_robin_team_id`) | same resolver as next-assignee, so the two agree (AC-E1) |
| `sla_service.create_tracking` | the contact - this is where the tracker is STAMPED (AC-E2) |
| `sla_service.get_escalation_assignee_for_tier` | caller-supplied; every caller passes the tracker's |
| `sla_service` extension notify fan-up | `_tracking_company_id(tracking)` |
| `sla_tracking.py` both escalate routes | `_tracking_company_id(tracking)` - no n8n change (AC-E3) |
| `form_sla_service._start_for_config` | the spawning entity's contact (AC-E4); also stamps the tracker |
| `form_sla_service` escalate | `_tracking_company_id(tracker)` - runs from the overdue scan |
| `complaints_service` notify helpers | `_company_for_complaint(complaint_id)` |
| `procurement_service` notify helpers | `_company_for_stock_inquiry(inquiry_id)` |
| `cs_routing_service._cs_team_id` | pinned contact's company; defaults to Sorento for the admin dropdown |
| `handling_lock_service.eligible_user_ids` | `_tracking_company_id(tracker)` |
| `tickets_service` submit | Sorento (`tickets` has no contact column at all) |

The notify helpers in `complaints_service` and `procurement_service` turned out to be
chains three deep (`_notify_team_stock_inquiry` to
`_get_team_user_ids_for_agent_team_assignment` to `get_team_id_by_code`), so the
company threads through each link rather than being read at the bottom.

Not every `AgentTeam` query goes through these resolvers: `sla_service` has ad-hoc ones
(the takeover queue lookup, the user-standing lookup, the tier-1 agent list). A required
kwarg cannot catch those, which is why `agent_teams` also carries `CompanyScopedMixin`
in S4 - the auto-filter is the backstop for every query a signature change cannot reach.

Also in this slice: `form_sla_service.py:858` stamps `company_id` at tracker creation from the
entity's contact (AC-E4); `sla_tracking.py:858` (`/integration/escalate`) reads it off the tracker
and needs no n8n change (AC-E3).

Highest-risk slice. Every escalation path in the product runs through these.

### S4 - Scope `teams`, wire the endpoints, enforce the guards

- `teams` and `agent_teams` gain `CompanyScopedMixin`; `access_agents` deliberately does not
  (AC-F1, D8). Check the external paths first: `next_assignee.py` and `team_members.py` read
  `agent_teams`, and under AC-F3 that request runs scoped to the coalesced routing company, which
  is exactly the row set they want. Background readers of `agent_teams` need S1's `None` scope
- verify the coverage-subscription picker
  (`coverage_subscription_service.py:88-98`) still behaves - it is the one non-SLA consumer of the
  team hierarchy and becomes company-scoped as a side effect
- same-company parent guard beside the cycle guard (`user_service.py:2406`) (AC-C7)
- team-member write validates the `user_companies` grant (AC-G1)
- `next_assignee.py` and `team_members.py` pass the resolved company into team resolution
- `preferred_assignee_id` validated against the resolved company's team (AC-D3)
- team not configured for this company gives a 404 naming the company, never a cross-company
  fallback (AC-C5)

### S5 - Admin configuration (FE)

- Team create/edit requires Company; Teams list follows the active company (AC-H1)
- Access Agents list stays unfiltered; the agent detail's Team Sets tab shows only the active
  company's rows, team picker offers only that company's teams, empty state plus add CTA when the
  agent has no rows there (AC-H2, AC-H2b)
- `set_agent_teams` dedupe key gains company; `_validate_tier1_invariant_for_assignments`
  evaluated per company (AC-H3, AC-H4)
- Per methodology the FE is prototyped against a stubbed hook before the backend lands. Small
  surface, so Phase 1 here is two screens, not a branch.

### S6 - Tests

- pytest: AC-J2 (Mocha contact never gets a Sorento assignee for a team set configured in both),
  independent cursors (AC-D2), missing-company-tier 404 (AC-C5), ambiguity conflict (AC-C6),
  `preferred_assignee_id` cross-company rejection (AC-D3), escalation staying in-company (AC-E3),
  team-members and next-assignee agreement (AC-E1), untagged contact still routes (AC-A6),
  overdue scan under scheduler scope (AC-F4), cross-company parent rejected (AC-C7), grant rule
  (AC-G1)
- Seed the whole chain per test: companies, agent, two teams, members, policies, agent_teams rows.
  CI's DB has no data; no `LIMIT 1` off an existing table, no assertion about a production row
- vitest: Team company field, Team Sets company column - render, required validation, duplicate
  message
- playwright: configure a second company's team set through the UI, then assert the roster the
  external endpoint returns

## Risks

- **Forgetting S1 breaks escalation silently.** Scoping `teams` while the scheduler sits at
  `UNSET` gives zero teams and no error. S1 ships before S4 for exactly this reason, and AC-F4
  pins it.
- **S3 is a wide edit across live escalation paths.** Mitigated by required keyword-only args and
  by S0 shipping first so company values are observable in production logs before anything routes
  on them.
- **Untagged contacts route to Sorento.** With one shared channel this is the whole safety net; 3
  of 61 contacts are untagged today. Worth a follow-up listing of untagged contacts for the admin.
- **Hard 404 depends on provisioning order.** AC-C5 is only safe because AC-I2 creates no Mocha
  rows and the admin configures Mocha teams, team sets and policies before tagging any contact
  Mocha. Tag first and that contact stops routing.
- **`sla_policies_code_key` is dropped.** Any code path assuming a globally unique policy code
  breaks; `next_assignee.py:43` is the known one, `sla_service.py:191` (duplicate-code check on
  create) is the other.
- **Collapsing the suffixed codes is a live routing change** and is deliberately left to a human
  after the migration (AC-I3).

## Open

- Nothing blocking. One item to confirm during S2: how many existing `team_members` rows violate
  the grant rule (AC-G2). Needs the dev database, which was unreachable at the time of writing
  (Docker daemon down).
