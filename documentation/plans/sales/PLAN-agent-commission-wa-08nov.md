# PLAN: distance to the next tier and what it would pay (AGENT-COMMISSION-WA)

Status: Plan (stub). Track: small fix (registry only, no migration, no new permission).

Wave W-A of `PLAN-agent-commission-all-08nov.md` "Next waves". Stacks on #2242
(branch `claude/agent-commission-dealers-teams-tvf434`).

Question: "How far is Agent A / dealer D1 / Team T1 from the next tier, and what would it pay?"

Approach: computed fields on the per-subject period rows, from `target_service.tier_ladder` /
`agent_progress` (no new calculation), same single `crm_query`, same permission rules as #2242.
