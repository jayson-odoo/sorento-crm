# PLAN: Tier-1 membership invariant scoped per team set

**Status:** Implemented on branch `fm/tier1-teamset-invariant` - pending review/PR.

**Phases 0/1 (journey, FE prototype): N/A.** Backend-only invariant relaxation; no user
journey or UI change. Phase 2 (code + tests) and Phase 3 (review) apply as usual.

## Problem

`user_service.py` enforces: a user may belong to at most ONE team linked at tier 1 under any
conversation-SLA agent, per company. Real blocker: Kia Yee is tier-1 in "Marketing - Promotion
Sorento" (agent `general_enquiries`, team set `marketing_promotion`) and must also be tier-1 in
"Marketing - Product" (same agent, team set `marketing_product`). Rosters are disjoint, so team
merging is not viable. The invariant exists so escalation can derive ONE tier-1 team from an
assignee (PLAN-sla-assignee-team-derivation).

## Decision

Scope the uniqueness invariant per TEAM SET (`AgentTeam.code`) instead of per company:
a user may hold tier-1 membership in at most one conversation-SLA tier-1 team PER team set
(still per company). Derivation disambiguates via the tracking's `team_set_code`, which
conversation trackings already carry - no schema change.

## Changes

All in `sorento_crm_backend/`; backend only.

### 1. `app/services/user_service.py` - `_validate_tier1_membership_invariant` (~2965)

Used by `add_team_member`. Today: target team has any conversation tier-1 link AND user is in
any other conversation tier-1 team => 422.

New: collect the target team's conversation tier-1 link CODES (`new_codes`). Conflict only when
the user's other conversation tier-1 team is linked with a code in `new_codes`. Keep every
carve-out: form-SLA agents' tier-1 links still excluded on both sides; same team under many
agents unaffected (team_id != team_id filter already handles it). Do not change company
scoping semantics here (query relies on existing session scoping).

Error message ends: "A user may only belong to one tier-1 team per team set." Include the
conflicting team set code as today.

### 2. `app/services/user_service.py` - `_validate_tier1_invariant_for_assignments` (~2089)

Used by `set_agent_teams` (bulk). Two conflict classes, both become code-scoped:

- Local (within payload): a user in multiple DISTINCT teams among the payload's tier-1
  assignments conflicts only when two of those assignments share the same `code`. Cross-code
  multi-team membership is now legal.
- Cross (other agents' links): keep all existing filters (per-company `AgentTeam.company_id ==
  _active_company_id()`, exclude form-SLA agent codes, exclude this agent, exclude payload
  team_ids), and ADD: only links whose `code` matches a code under which that user holds a
  tier-1 assignment in this payload. Conflict map keyed per (user, code).

Tier-2/3 reuse warn-only block: untouched. Form-SLA-agent short-circuit: untouched.
Both error messages end: "A user may only belong to one tier-1 team per team set."

### 3. `app/services/sla_service.py` - `derive_team_for_assignee` (~3534)

Today: >1 distinct tier-1 team => warn + return None (abort derivation).

New step 1 (conversation tier-1 links, form-SLA-filtered, ordered `(code asc, agent_id asc)`
as today):

1. If `current_team_set_code` is provided and some links match it, restrict to those links.
   Within one team set the invariant guarantees one distinct team; multiple links there are
   the shared-pool case - prefer `current_agent_id`, else first.
2. Otherwise (no team-set context, or no link in that set): if links span >1 distinct team,
   LOG the ambiguity (warning) and fall back deterministically - prefer the link matching
   `current_agent_id`, else the first link in `(code, agent_id)` order. Never return None
   for this case anymore; None remains for "no tier-1 links at all" (steps 2/3 unchanged).

Update the docstring. `apply_assignee_team_derivation` already passes the tracking's
`agent_id` + `team_set_code` - no change there.

### 4. Tests - `tests/test_sla_assignee_team_derivation.py` (+ any other invariant tests)

Mock-chain style as the file already uses. Cover:

- Cross-team-set tier-1 membership allowed via `add_team_member` (Kia Yee scenario) and via
  the bulk path.
- Same-team-set duplicate still 422, both paths, message says "per team set".
- Derivation: dual-membership user + tracking context (`current_team_set_code`) resolves to
  the team of that set.
- Derivation: dual-membership user, no team-set context -> deterministic fallback (prefer
  current agent, else first `(code, agent_id)` link), logged, not None.
- Existing `test_derive_multiple_tier1_teams_is_ambiguous` updated to the new fallback
  contract. Audit sibling invariant tests (grep tier-1/tier1 in tests/) for message or
  behavior drift.

### 5. `app/services/sla_service.py` - `_agent_link_for_user` (takeover / reassign)

Review finding: takeover and reassign re-derive `(team_set_code, tier)` for the target user
via `_agent_link_for_user`, which picked `.first()` among the user's links under the agent
with no code filter. Under the relaxation a user can hold tier-1 links to DIFFERENT teams
under one agent, so the pick became arbitrary (wrong team set, wrong round-robin cursor).
Fix: pass the tracking's `team_set_code`, prefer the link in that set, fall back across sets
with a deterministic `(tier desc, code asc)` ordering.

## Known limitation

A tracking whose `team_set_code` carries a legacy brand suffix (written verbatim by
`update_tracking`, e.g. `marketing_promotion_mocha`) matches no `AgentTeam.code`, so
derivation takes the deterministic fallback rather than the correct set. The same applies
to `_agent_link_for_user` in takeover/reassign: a suffixed code matches no `AgentTeam.code`,
so the filtered query misses and it silently falls back across sets. Pre-existing
normalisation gap (`split_legacy_team_set_code` is applied on create only); behavior is no
worse than the old None-abort. Out of scope here.

Behavior change worth noting in the PR: `derive_team_for_assignee` no longer returns None
on multi-team membership, so invariant-violating legacy data now gets its routing rewritten
AND its tier clock restarted by `apply_assignee_team_derivation` (due_at reset) where it
previously left the tracking untouched. The WARNING log is the signal. Accepted trade per
the Decision section.

## Out of scope

No schema migration, no primary-team flag, no UI change. Per-company separation, form-SLA
carve-outs, shared-pool tier-1 teams, tier-2/3 warn-only reuse: all preserved.
