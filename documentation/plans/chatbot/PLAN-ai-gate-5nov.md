# PLAN: AI-GATE (assistant coverage CI gate)

Status: built 5 Nov 2026, in review on PR #2189 (waiting on QUERY-CORE #2188 to merge first, then owner go). Track: small fix track (no migration, no auth/RBAC change, no
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

## Built (5 Nov)

- The resolver also follows route factories (`register_x_routes(router)`, `build_x_router()`), package
  re-exports and module string constants; its GET paths equal FastAPI's live table (936/936 on main),
  pinned by `test_static_paths_equal_the_apps_live_get_routes`. About 8 s per run.
- A list route is `@x.get` or `@x.api_route(methods=[... "GET" ...])` with a `page` / `limit` parameter,
  or one aliased to them (`Query(alias="page")`, also inside `Annotated`).
- Real-history check: over main's last 60 merges it flags exactly `GET /api/v1/system/client-errors` (#2165).

## Known limits (reviewer, accepted; trigger named)

- Paging only through `params: X = Depends()` or `offset` alone is not seen. None exists today. Trigger:
  the first such list route.
- "Added" = a newly served method + path. Mounting an existing paged router at a second prefix whose
  other paths already exist, or replacing a non-paged GET with a paged list at the same path, stays
  quiet; renaming a list's path fires.
- The opt-out comment is read above the first decorator only (a stacked second `@router.get` is
  flagged: fails safe).
- Registry route strings must be literals inside the `EntityDef(...)` call (constants or f-strings
  are not followed: a clear false positive, never a silent pass). Agreed with QUERY-CORE on #2188.
- Nothing scores `gold/assistant_*.jsonl` yet: rows are validated (`test_committed_assistant_gold_is_valid`)
  and `grade_assistant` grades a digest; wiring it into the eval runner belongs to the first wave lane
  that commits gold rows.
