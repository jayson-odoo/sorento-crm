# UAC: MCP-TOKEN-UI

- **TOK-0** After the release migration a token exists (Enforce off), so the backend authenticates and the staff
  AI assistant keeps its company-scoped tools; n8n with no header keeps working.
- **TOK-1** With no token set, the MCP server starts with no env token, `/healthz` is 200, a call with no
  Authorization header is served, and any bearer gets 401.
- **TOK-2** An admin with `user_management.settings.secrets` sees an "MCP access token" card on Settings >
  Integrations; without the slug the card and the four routes are refused (403).
- **TOK-3** Generate shows the full token once with a Copy button; after Hide or a reload only `****` + last 4 shows.
- **TOK-4** About 10 s after Generate/Rotate, the backend's MCP calls carry the new token and the MCP server accepts
  it; no call is refused in between (the previous token, or no header, is sent until then).
- **TOK-5** Enforce cannot be switched on while no readable token exists (409; the switch is disabled). With Enforce on, a call with no or a
  wrong token gets 401 within 30 s.
- **TOK-6** Rotate: the new token works at once; the previous one keeps working until "Previous token valid
  until" (24 h) or "Revoke previous now", then gets 401.
- **TOK-7** Backend unreachable: the MCP server keeps its last answer; before any answer `/mcp` is 503, never an exit.
- **TOK-8** No token, ciphertext or digest appears in an audit row, a log line, a GET response or the query cache.
- **TOK-9** The release verify step passes on a fresh install with no token set.
