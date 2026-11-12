# PLAN: every Respond.io call honours the configured base URL (RESPOND-BASE-URL-LEAK)

Status: built, in review (PR #2272). Small fix track (no migration, no auth/RBAC change, no new ingest surface).

## Problem

On a crew test copy (prod-clone DB, real Respond credentials) RESPOND_BASE_URL was set to an
`.invalid` host, yet each Stock Inquiry submit/void made two attempts at `api.respond.io`.

## Findings (main @ 7ad8c368)

Every real Respond.io HTTP request goes through `RespondClient` (`app/services/integration_service.py`),
which builds each URL from `self.base_url`. The leak is the precedence that sets it:

- `integration_service.py:286` `base_url or settings.respond_base_url or "https://api.respond.io"`:
  a workspace row's `base_url` BEATS the env override. A contact whose own workspace row carries
  `https://api.respond.io` (the admin form's placeholder value) sends there whatever env says.
- `config.py:123` defaults `respond_base_url` to the real host, so "env unset" and "env set" are
  indistinguishable.
- `respond_sync_handler.py:131` re-derives the base URL by hand for its log row.
- Integration-log `endpoint` labels hard-code `https://api.respond.io/...` (they record a URL that was
  never the one called): `procurement_service.py:7774,7810,9989,10005`, `stock_ask_service.py:425`,
  `price_tag_notify.py:215,237`, `integration_service.py:1335`, `respond_chat_template_service.py:190,210,433`,
  `ticket_comment_service.py:140`, `activities_service.py:642`, `ticket_notification_service.py:205,221`.

## Fix

1. One resolver in `integration_service.py`: env RESPOND_BASE_URL (when set) > workspace base_url >
   `RESPOND_DEFAULT_BASE_URL`. `config.respond_base_url` defaults to None.
2. `respond_endpoint(path)` builds every log label from the same resolver.
3. Guard test: no `api.respond.io` (or bare `respond.io/` host) in backend or MCP code outside
   `integration_service.py`.
4. Red-first test: SI submit with RESPOND_BASE_URL=https://api.respond.invalid and a workspace row on
   `https://api.respond.io` makes zero requests to api.respond.io (httpx transport mocked, no network).

## Follow-on (review)

- `scripts/inbox_queue_replay.py` reached its local lookup server through the workspace row, which
  the env now beats: `check_env` accepts a loopback RESPOND_BASE_URL and preflight warns when the env
  does not name the run's server.
- Out of scope, own ticket: `chatbot_sender_url`, `chatbot_retry_ingress_url` and n8n webhook URLs are
  not covered by RESPOND_BASE_URL on a prod-clone copy.
