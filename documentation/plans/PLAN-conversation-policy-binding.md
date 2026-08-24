# PLAN - Backend-owned SLA policy binding (conversation) + policy as shared profile

**Status:** Phase 2 implemented (BE wiring + FE off-mocks). Tests pending (tester agent).
**Owner:** jayson
**Slug:** conversation-policy-binding
**Related:** [[PLAN-conversation-sla-idempotent-create]], `documentation/ARCHITECTURE-RULES.md`, `documentation/reference/ADR-PRODUCT-STANDARDS.md`

---

## 1. Problem

1. **Conversation SLA policy is chosen by n8n.** The route
   `POST /api/v1/sla-management/conversation-sla-tracking` accepts `policy_id`
   straight from the n8n payload. The business requires the policy to be **owned and
   defined by the CRM**, derived from the routing context, not supplied externally.
2. **"More policies than expected."** Policies are not consistently treated as
   reusable profiles, so near-duplicate `sla_policies` rows proliferate (one per
   binding instead of one per distinct tier-hour shape).
3. **Per-form SLA differences are real but already modelled.** PR approval = 3 days,
   sponsorship approval = 1 day, warehouse tiers = 0.5h / 1h - these differ even
   "under the same agent and model." Form SLA already supports this via
   `FormSLAConfig.policy_id` keyed by `source_entity_type`; the gap there is *data*,
   not schema.

### Resolution key (decided)

`(agent_code, team_set_code) → exactly one SLA policy`. Same business hours. No other
discriminator (channel/contact-type/message_id do **not** affect policy). Tiers live
**inside** the policy (`SLAPolicyTier.tier_level → response_hours/resolution_hours`).
`team_set_code` examples: `purchasing`, `warehouse`, `general_enquiries`'s sets, etc.

For **forms**, the key additionally includes `source_entity_type` (PR vs sponsorship
share agent+team_set but differ) - which is exactly why form policy stays in
`FormSLAConfig` and is **not** folded into the conversation binding.

---

## 2. Key decisions (from grilling)

| # | Decision |
|---|----------|
| D1 | Conversation policy key = `(agent_code, team_set_code) → one policy`. Tiers inside the policy. |
| D2 | n8n payload: `agent_code` + `team_set_code` become **required**. n8n's `policy_id` and `current_tier` are **ignored**; conversation always starts at **tier 1**. Lenient, not strict-reject. |
| D3 | **No new table.** Add nullable `policy_id` FK on `agent_teams`. One policy per team set, **cast to all tier rows** of `(agent_id, code)` atomically by the write path. |
| D4 | Resolution = distinct `policy_id` over `(agent_id, team_set_code)`: exactly one ⇒ use; none/NULL ⇒ **422** (end-state); multiple distinct ⇒ **409 misconfig**. New tier rows **inherit** the team-set policy. |
| D5 | `sla_policies` = **shared reusable profiles**, named by SLA shape (e.g. `STANDARD`, `WAREHOUSE_FAST`, `APPROVAL_1D`, `APPROVAL_3D`). Many bindings → one policy. Consolidate existing duplicates. |
| D6 | UI: a **group-level SLA-policy picker** (one per `team_set_code` group) on the Access Agent team-assignments form, reusing `getSLAPolicies`. On save the group's `policy_id` is stamped onto every assignment row of that `code`. |
| D7 | **No bind-time tier-coverage validation** (policy tiers and team-set tiers may differ either way). At runtime, when escalation advances past the policy's defined tiers, **clamp to the policy's highest defined tier hours** (logged) - never a phantom 24h. |
| D8 | Rollout uses a **temporary n8n `policy_id` fallback**: resolve from `agent_teams.policy_id`; if NULL, fall back to the n8n-supplied `policy_id` + warn. Remove the fallback once all team sets are bound - then unbound = the D4 422. |
| D9 | Form side = **data entry** into the existing `FormSLAConfig` dialog (PR/sponsorship/warehouse stage rows). No schema change. Optional one-time seed script. |

### Out of scope / unchanged
- Round-robin assignee selection stays n8n's job (`assigned_to` still supplied).
- Form SLA orchestration, escalation, idempotent-create semantics - unchanged.
- `team_set_code → team/tier` resolution (`resolve_team_with_tier_fallback`) - unchanged.

---

## 3. Architecture

### Conversation (changed)
```
n8n POST /conversation-sla-tracking
  required: agent_code, team_set_code, contact_phone_number, (assigned_to optional)
  ignored:  policy_id, current_tier
        │
        ▼
create_tracking():
  1. resolve agent_code → AccessAgent.id            (existing)
  2. resolve policy:  SELECT DISTINCT policy_id
        FROM agent_teams
        WHERE agent_id = :agent_id AND code = :team_set_code
     ├─ one non-null   → use it
     ├─ none / NULL    → [rollout] fall back to n8n policy_id + warn
     │                   [end-state] 422 "no SLA policy bound for agent/team set"
     └─ many distinct  → 409 "policy inconsistent for this team set"
  3. current_tier = 1 (forced)
  4. tier hours = SLAPolicyTier(policy_id, 1); due_at = working(response_hours)
```

### Form (unchanged mechanism, data added)
`FormSLAConfig.policy_id` per `(source_entity_type, stage_code/team_set_code)` - already
the source of truth. Add the missing rows (PR/sponsorship/warehouse).

### Escalation tier clamp (D7)
When `current_tier` advances to N and `SLAPolicyTier(policy_id, N)` does not exist:
use the policy's **max defined** `tier_level` hours for the deadline; still escalate
the team/assignee via `resolve_team_with_tier_fallback`. Applies to both conversation
and form recompute paths.

---

## 4. Affected files (from codebase exploration)

### Backend
- `app/models/access.py` - `AgentTeam` (~line 321): add `policy_id` nullable FK → `sla_policies.id` (`ondelete="RESTRICT"`).
- `alembic/versions/247_agent_team_policy_id.py` - new migration (add column; chains off `246_sla_tier_hours_decimal`).
- `app/schemas/user.py` - `AgentTeamAssignment` (~line 352): add `policy_id: Optional[str]`. `AgentTeamsUpdate` unchanged shape.
- `app/services/user_service.py`
 - `AccessAgentService.set_agent_teams` - stamp the group `policy_id` onto every row of each `code`; new tier rows inherit.
 - New helper `resolve_policy_id_for(agent_id, team_set_code)` → distinct-policy rule (D4).
- `app/services/sla_service.py` - `ConversationSLATrackingService.create_tracking` (~line 2488): replace "policy from body" with resolver + D8 fallback; force `current_tier=1`; D7 tier clamp in `compute_tracking_timings` / due recompute helpers.
- `app/schemas/sla.py` - `ConversationSLATrackingCreate`: make `agent_code`, `team_set_code` required; keep `policy_id`/`current_tier` accepted-but-ignored.
- `app/api/v1/sla/sla_tracking.py` - POST "/": no signature change; resolver lives in service.

### Frontend
- `app/(protected)/user-management/access-agents/components/AccessAgentForm.tsx` (~328 - 481) - add per-group SLA-policy picker; include `policy_id` in each `AgentTeamAssignment` on submit.
- `app/(protected)/user-management/access-agents/services/accessAgentService.ts` - `AgentTeamAssignment` type + `setAgentTeams` payload gain `policy_id`.
- Reuse `getSLAPolicies` from `app/(protected)/sla-management/sla-policies/services/slaPolicyService.ts` for the picker.
- `FormSLAConfig` dialog - no change (already has policy picker); used for D9 data entry.

### Data
- Bind a policy to **every existing `(agent, team_set)`** via the UI before removing the D8 fallback.
- Create `FormSLAConfig` rows: PR approval → `APPROVAL_3D`, sponsorship approval → `APPROVAL_1D`, warehouse stages → `WAREHOUSE_FAST` (0.5/1h tiers).
- Consolidation pass: audit `sla_policies`, merge near-duplicate profiles, repoint bindings.

---

## 5. Phased delivery (three-phase loop)

**Phase 1 - FE prototype**
- Group-level policy picker in `AccessAgentForm` against mock policy list. States: unbound group, bound group, loading, save. Screenshot golden path + unbound case.

**Phase 2 - BE wiring + tests**
- Migration 247, model/schema changes, `set_agent_teams` cast + inherit, `resolve_policy_id_for`, `create_tracking` resolver + D8 fallback + D7 clamp, required field changes.
- FE off-mocks: real `getSLAPolicies`, `policy_id` in `setAgentTeams`.
- Tests:
 - **pytest**: resolver one/none/many; cast-to-all-rows; new-row inherit; create_tracking ignores n8n policy_id when bound; fallback-to-n8n when unbound (rollout flag); tier clamp; required-field 422.
 - **vitest**: `AccessAgentForm` group picker (bound/unbound/save payload includes policy_id).
 - **playwright**: bind a policy to a team set → create conversation via API → asserts resolved policy.

**Phase 3 - review**
- `/code-review`; verify CLAUDE.md rules (extractApiError, no hand-built params, hard-delete N/A here).

**Rollout (D8)**
1. Deploy migration + UI (fallback ON).
2. Admin binds every team set + creates form configs.
3. Verify logs show zero fallback hits.
4. Remove fallback → unbound now 422. Edit n8n to stop sending `policy_id`.

---

## 6. User Acceptance Criteria (UAC)

### Conversation policy binding
- **UAC-1** Admin can set **one SLA policy per team-set group** in the Access Agent edit screen; the picker lists active policies by `name (code)`.
- **UAC-2** Saving a group with a policy writes that **same `policy_id` to all tier rows** (tier 1/2/3) of that team set; DB shows identical `policy_id` across the `(agent, code)` rows.
- **UAC-3** Adding a **new tier row** to an already-bound team set **inherits** that team set's policy automatically (never saved NULL).
- **UAC-4** A conversation create from n8n with `agent_code` + `team_set_code` resolves the policy **server-side**; the response's `policy_id` matches the bound policy, **regardless of any `policy_id` n8n sent**.
- **UAC-5** n8n-supplied `current_tier` is ignored; the created row is always **tier 1**.
- **UAC-6** Conversation create **missing `agent_code` or `team_set_code`** → 422 with a clear field error.
- **UAC-7 (end-state)** Conversation create for an **unbound** `(agent, team_set)` → **422** "no SLA policy bound…". *(During rollout: falls back to n8n `policy_id` + a warning log instead.)*
- **UAC-8** `(agent, team_set)` rows with **inconsistent** policies → **409** "policy inconsistent for this team set" (create blocked; surfaced in UI on bind).

### Tiers & escalation
- **UAC-9** A policy with **more tiers than the team set** is accepted; the unused tiers are simply never reached.
- **UAC-10** A team set with **more tiers than the policy**: escalation still moves to the higher-tier assignee, and the deadline is computed from the **policy's highest defined tier** hours (no 24h phantom). A log line records the clamp.
- **UAC-11** Sub-hour SLAs work: a `WAREHOUSE_FAST` policy with tier-1 `response_hours = 0.5` produces a `due_at` 30 minutes out.

### Forms (data, existing mechanism)
- **UAC-12** PR approval stage uses a 3-day policy; sponsorship approval uses a 1-day policy - both configured as `FormSLAConfig` rows, verified by spawning each form's SLA and checking the due date.
- **UAC-13** Warehouse form stage uses the short (0.5/1h) policy.

### Policies as profiles
- **UAC-14** A single policy (e.g. `STANDARD`) is referenced by **multiple** team-set bindings and/or form configs simultaneously; editing the policy's tiers affects all of them.
- **UAC-15** After the consolidation pass, the `sla_policies` list contains only **distinct tier-hour profiles** (no functional duplicates).

### Regression
- **UAC-16** Existing conversation tracking rows keep their stored `policy_id`; timings, escalation, idempotent-create, and the conversation/form SLA tracking lists behave unchanged.

---

## 7. Open risks / notes
- The D8 fallback must be **removed** (a code change, not a flag left on) - track it as a follow-up so unbound silently using n8n's policy doesn't become permanent.
- Consolidation repoints bindings - do it JOIN-based and idempotent (set binding to canonical policy where it currently points at a duplicate), per the backfill lesson in CLAUDE.md.
- `agent_teams.policy_id` uses `RESTRICT` so a policy in use can't be deleted - matches the existing SLA-policy delete guard.
