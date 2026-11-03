# PLAN: redact customer link tokens from backend logs

Status: review READY (round 3). Small fix track by kind (no migration, no auth/RBAC change, no new ingest surface); the diff is ~410 lines, about half of it tests and this plan.
Lane: SIGN-TOKEN-LOG-REDACT. UAC: `sign-token-log-redact-acceptance-criteria.md`.

## Problem

Crew browser pass on #2126 (3 Nov 2026): the backend request log writes a customer's counter-sign
link token in plain text, so anyone who can read the logs can open that customer's sign page.

## Where a link token reaches a log line today (measured)

| Sink | Source | What leaks |
| --- | --- | --- |
| App request line | `app/middleware/logging_middleware.py` (`logger.info(f"{method} {path} ...")`) | path tokens |
| uvicorn access log | `gunicorn.conf.py` `accesslog = "-"` (UvicornWorker) and `run.sh` uvicorn: `uvicorn.access` logs the path WITH its query string | path and query tokens |
| Unhandled-error log | `app/main.py` `global_exception_handler`, `Request URL: {request.url}` | path and query tokens |
| 422 log | `app/main.py` `validation_exception_handler`, `Request URL: {request.url}` | path and query tokens |
| Staff auth debug | `app/dependencies.py` debug line prints the first 20 chars of the bearer token (debug only) | staff session token prefix |
| DB error text | `app/database.py` engine: SQLAlchemy puts bound parameters in every error message (`[parameters: {'token_1': ...}]`), logged by the handlers and services | any token used in a failing query |
| httpx INFO line | `app/api/v1/public/portal_ideas.py` proxies to `/public/ideas/{token}`; httpx logs each request URL at INFO | idea tokens |
| `api_call_logs` table | `app/services/api_call_log_service.py` `sanitize_body` masks secret KEYS only; `/external` responses carry `view_url`, `portal_url`, sign `path` values | view, portal and sign links in stored bodies |
| Frontend container nginx | `sorento_crm_frontend/nginx.conf`: Alpine's default access log writes the full request URI and Referer | every page and API link |

No Sentry or other breadcrumb sink is installed (grep `sentry` over the backend: none).

Token-bearing URLs (`app/api/v1/public/__init__.py` prefixes):

- Path segment: `/api/v1/public/quotation-sign/{token}` (counter-sign), `/ticket-drafts/{token}`,
  `/supplier-request/{token}`, `/portal/ideas/{token}`, `/file-links/{code}` (share link code).
- Query param `token`: `/public/view`, `/public/approval`, `/public/print`, `/public/portal/token-info`,
  `/notifications/preferences/daily-sla-summary/unsubscribe`.

## Fix (simplest thing that works)

One helper, `app/utils/log_redaction.py`:

- `redact_url(text)` replaces the token segment after each prefix above, and the value of any
  query parameter whose name ends in `token`, with `[redacted:<first 8 hex of sha256>]`. The hash
  prefix is not reversible and still lets two log lines for the same link be correlated.
- `RedactUrlTokensFilter`, a `logging.Filter` installed on the `uvicorn.access` logger at app
  import (`app/main.py`), rewrites the access record's path argument.

Call sites: the middleware request line and both `Request URL` lines in `app/main.py` pass through
`redact_url`. The `app/dependencies.py` debug line logs only the token length.

Round 2 (security review): `redact_url` also masks the customer page URLs the backend builds
(`/quotation-sign/`, `/portal/ideas/`, `/portal/ticket-draft/`, `[/c/<co>]/supplier-request/`,
`/onboarding/`, `/f/`, anchored to a path start, host or quote); `sanitize_body` runs it over the
stored body; the `httpx`/`httpcore` loggers sit at WARNING; the engine sets
`hide_parameters=not settings.debug`; the frontend nginx uses a `redacted` log format (token
segment masked, a query with a token dropped, a link Referer dropped).

## Residual, not fixed here

- nginx's ERROR log prints the raw request line when an upstream fails (backend down during a
  deploy). Its format is not configurable; only on failures.
- The host nginx in front of production is not in this repo; it needs the same log format.
- A dealer-kit render timeout's error text can name the print URL with its short-lived render JWT
  (`app/tasks/dealer_kit_export_tasks.py`); low impact, follow-up.
- `webhook_service.py` logs n8n payloads at INFO; none carries a link token today.
- `hide_parameters` hides SQLAlchemy's bound parameters, not Postgres's own error detail
  (`Key (token)=(...) already exists`).

No user-visible behaviour change: routing, responses and the audit rows are untouched.

## Tests

`tests/test_log_redaction.py` (red first): a request to each token URL through `LoggingMiddleware`
logs no token; the uvicorn access filter strips path and query tokens; ordinary paths are unchanged.
