# PLAN: no live LLM / messaging calls from the backend test suite

Status: in progress (small fix track: tests-only diff, no migration, no auth/RBAC change)

## Problem

`pytest` loads the developer's real backend `.env` (`app/config.py` `_resolve_settings_env_file`,
`model_config` `env_file`), which carries OPENAI_API_KEY and RESPOND_API_KEY. Nothing blocks
network calls: the chatbot parser has no global stub, and `llm_provider.resolve_api_key` falls
back to `settings.openai_api_key`. The opt-in `no_live_llm` fixture is unused under
`tests/chatbot`. A test that forgets its stub can spend the real key.

## Fix

1. `tests/conftest.py`: an autouse `_no_live_external_calls` fixture for the whole suite. It
   patches `httpx.HTTPTransport.handle_request`, `httpx.AsyncHTTPTransport.handle_async_request`,
   `urllib.request.OpenerDirector.open` and (if installed) `requests.adapters.HTTPAdapter.send`
   so a request to api.openai.com, api.anthropic.com, generativelanguage.googleapis.com, any
   respond.io host or graph.facebook.com raises `LiveExternalCallBlocked`. Every blocked attempt
   is also recorded and fails the test at teardown, so app code that swallows the exception
   still cannot pass silently. Mock transports (`httpx.MockTransport`, Starlette TestClient) are
   not `HTTPTransport`, so they are untouched.
2. Opt-out: `@pytest.mark.live_external` lifts the guard, and such a test is skipped unless
   `CHATBOT_LIVE_LLM=1`.
3. Keys: at conftest import, OPENAI/ANTHROPIC/GEMINI/RESPOND keys are blanked in `os.environ`
   and on the `settings` object (unless `CHATBOT_LIVE_LLM=1`), so a call that bypasses the
   guard fails on "no key".
4. Red-first test: `tests/chatbot/test_no_live_llm_guard.py`.

Trigger for more machinery: another HTTP client library appearing in `requirements.txt`.
