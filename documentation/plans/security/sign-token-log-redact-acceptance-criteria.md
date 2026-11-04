# UAC: redact customer link tokens from backend logs

Plan: `PLAN-sign-token-log-redact-03nov.md`.

1. A request to `/api/v1/public/quotation-sign/<token>` (and its `/accept`, `/view`, ...
   sub-paths) writes no part of `<token>` longer than the redaction marker to the app request log.
2. The same holds for `/ticket-drafts/<token>`, `/supplier-request/<token>`,
   `/portal/ideas/<token>` and `/file-links/<code>`.
3. A `?token=<value>` query parameter (any parameter name ending in `token`) never appears in the
   uvicorn access log or in the `Request URL` error lines.
4. The redacted line keeps the route shape and carries `[redacted:<8 hex>]`, the same marker for
   the same token, so two lines for one link can be correlated.
5. Paths without a token (e.g. `/api/v1/orders/123?page=2`) are logged unchanged.
6. No response, status code or audit row changes for the customer.
