# PLAN: AI-GATE (assistant coverage CI gate)

Status: in progress 5 Nov 2026 (Build). Track: small fix track (no migration, no auth/RBAC change, no
ingest surface). Parent plan: `PLAN-ai-tools-standard-5nov.md` section 4 "AI-GATE" and 2.5 (PR #2185).
Lane AI-GATE. Merges after QUERY-CORE (it reads `EntityDef.routes` from `app/services/assistant_registry`).

## Scope

1. `scripts/ci_ai_coverage.py`: diff against the merge base, find ADDED `@router.get` functions that take
   `page` or `limit`; fail unless the route is in some `EntityDef.routes` or the decorator is preceded by
   `# ai: not-for-assistant <reason>` (reason required). Stdlib only, reads the registry by AST so it
   needs no backend deps and runs before the dependency install.
2. Wire it into the PR gate fast checks (`.github/workflows/deploy.yml`, next to `pii_guard.py`) and the
   pre-push hook.
3. DoD lines 6-8 in `PRINCIPLES.md` and the cloud worker contract (`documentation/agents/cloud-lanes.md`).
4. `assistant` case type in `sorento_crm_backend/scripts/chatbot_eval/cases.py` that names the expected
   entity or action.

## Tests

- added paged GET without registration fails;
- with the opt-out comment (and a reason) passes; opt-out without a reason fails;
- with a registered entity route passes;
- an edit to an existing route does not trigger it;
- a GET without `page`/`limit` is ignored.
