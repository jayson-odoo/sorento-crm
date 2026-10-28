# PLAN: RELEASE5-FIX (28 Oct 2026)

Status: in progress, small fix track (test-only diff, no migration, no auth/RBAC, no new ingest).

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
