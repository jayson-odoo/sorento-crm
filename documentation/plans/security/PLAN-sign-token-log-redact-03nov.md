# PLAN: redact customer link tokens from backend logs

Status: in build. Small fix track (no migration, no auth/RBAC change, no new ingest surface; under 300 lines).
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

No Sentry or other breadcrumb sink is installed (grep `sentry` over the backend: none).
`api_call_log_middleware` records only `/api/v1/external/*` and `X-Source` callers; the public
token routes are neither, so it is not a sink for these links.

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

No user-visible behaviour change: routing, responses and the audit rows are untouched.

## Tests

`tests/test_log_redaction.py` (red first): a request to each token URL through `LoggingMiddleware`
logs no token; the uvicorn access filter strips path and query tokens; ordinary paths are unchanged.
