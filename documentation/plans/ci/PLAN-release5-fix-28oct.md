# PLAN: RELEASE5-FIX (28 Oct 2026)

Status: PR #1963 ready for CI, small fix track (tests + workflow TZ + 3 stock-position FE files, no migration, no auth/RBAC, no new ingest).

## Problem

Release #5 (deploy.yml full_suite, run 40680704839, main 4af3b42349) failed shard
"Backend test suite (Postgres, xdist) (2)" on two tests. Both were broken by #1958
GEMINI-EXPLICIT-CACHE (merged 28 Oct). PR CI runs only changed test files, so neither ran
on the #1958 PR.

1. `tests/chatbot/test_llm_call_timeout.py::test_gemini_passes_the_timeout_to_its_request`
   fails `assert [8.999992707977071] == [9.0]`.
2. `tests/chatbot/test_import_boundary.py::test_no_module_outside_the_boundary_imports_the_chatbot_package`
   fails because `tests/test_gemini_context_cache.py` imports `app.services.chatbot`.

## Decision

1. The code is right, the test is stale. `GeminiProvider._generate`
   (`app/services/llm_provider.py` 1495-1503) is designed to keep the whole call, cache steps
   included, inside the caller's per-attempt `timeout`: each request gets
   `remaining() = max(timeout - elapsed, 1.0)`. With no cache step the elapsed time is a few
   microseconds, so the request sees 8.99999 s, not 9.0. The test keeps its intent (the
   caller's timeout reaches the request, not `GEMINI_TIMEOUT_SECONDS` = 120) and adds the
   design's own bound: never more than the caller's timeout.
2. The boundary rule (`test_import_boundary.py` docstring) is "core never imports the
   package; `tests/chatbot/` may". `tests/test_gemini_context_cache.py` tests a core service and
   stays where it is; its one chatbot test (the clarifier's per-version `prompt_cache_key`)
   moves to `tests/chatbot/test_llm_cost_parser.py`, beside the parser's identical
   `TestParserSendsPromptCacheKey`.

## Also

Run the chatbot suite and the tests #1957 / #1958 / #1959 added on a throwaway DB, and read
the other release shards' failures once they finish, so the re-dispatch does not fail on a
third test.

## Outcome (rounds 2-6: every failed job of run 40680704839)

| Test | Cause | Fix |
| --- | --- | --- |
| chatbot/test_llm_call_timeout `test_gemini_passes_the_timeout_to_its_request` | #1958 spends the cache steps from the caller's timeout | assert approx 9 s and never more |
| chatbot/test_import_boundary | #1958 cache test imported the chatbot package from core tests | clarifier test moved to tests/chatbot/test_llm_cost_parser.py |
| test_project_customer_from_lead x4 | #1957: register helper always picks a customer; picked wins over the lead's buyer | tests pick the lead's buyer; pin picked-wins + older-project fallback |
| test_project_quotation_approval_notify b4 | #1952 verb "resubmitted" -> "appealed" | assert "appealed" |
| test_chat_local_first fresh push | +08 runner: naive `utcnow().timestamp()` read as local | aware UTC epoch |
| test_respond_webhook_ingest x2 (found by +08 sweep) | same, `.timestamp()` on stored naive UTC | `.replace(tzinfo=utc)` |
| analytics_connector/test_review_round [401/409/410/413] | #1957 added `viewer_user_id` to get_project_or_404 | stand-in absorbs keywords |
| test_filter_multiselect_pr6_lists parties x2 | #1957 parties list on require_any_permission (slug set) | test client answers every slug |
| vitest options.inventory M4-01 | #1913 useStockPosition own placeholderData | spread LIST_QUERY_OPTIONS |
| vitest loading-inventory M5-01, PageHeader S5-05 (found locally) | #1913 no loading.tsx; `c.id.slice(3)` | loading.tsx; named prefix |
| systemic | sorento-mac VM is Asia/Kuala_Lumpur; GitHub-hosted runners and (by inference: no TZ in any tracked Dockerfile/compose/deploy script; the server compose and .env are untracked, UNVERIFIED on the box) prod are UTC | workflow `env: TZ: UTC`, pinned by test_ci_runner_routing |
