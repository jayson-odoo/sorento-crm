# PLAN: MCP auth token set from the settings screen (no .env)

Status: Build done, in review (full track, size M: auth + additive migration + settings UI). Built against
the design card's recommended answers (PR comment "crew-ask: MCP-TOKEN-UI design card"); owner answers pending.
UAC: `mcp-token-ui-acceptance-criteria.md`
Lane: MCP-TOKEN-UI (owner, 31 Oct 00:35). Releases are on hold until this ships.

Owner, verbatim: "for the auth token can I put it at frontend, I don't want so many thing
relying on .env ... we shouldn't release until we have the MCP token setting at the frontend,
and the deployment will have 0 downtime or breakage of the chatbot working".

## Before (main 625a3751, SEC-MCP-AUTH #1742)

- The MCP server read `MCP_AUTH_TOKEN` from env and exited 1 without a 32+ char value
  (`sorento_crm_mcp/sorento_crm_mcp/server.py:1845`, `__main__.py`). `MCP_AUTH_MODE=permit` let a
  headerless call through.
- The backend sent `settings.mcp_auth_token` (env) from `MCPRuntimeClient._headers`
  (`app/services/ai_assistant_service.py:370`), the one client every in-repo caller uses.

## Design (decisions = card answers (a) on all five)

1. **Store.** Five additive columns on `system_settings` (`mcp_tok_0001_settings_token`):
   current token ciphertext, rotated at, previous token ciphertext, previous expiry, Enforce
   (bool, default false). `encrypt_secret` like the runtime settings. No env fallback (Q4).
2. **Service** `app/services/mcp_auth_token.py`: `rotate` (first call = generate;
   `secrets.token_urlsafe(32)`; old token kept `GRACE_HOURS = 24`, Q2), `set_enforce` (409 with no
   token), `revoke_previous`, `describe` (masked last 4), `mcp_answer` (digests), `current_token`
   (5 s process cache). One `MCP_AUTH_TOKEN` audit row per action, action name only.
3. **Screen.** Settings > Integrations, new "MCP access token" card, gated by the existing
   `user_management.settings.secrets`. Token shown once after Generate/Rotate with Copy (Q3).
4. **MCP server learns the token** from `GET /api/v1/system/mcp-auth` with its X-API-Key:
   `{"enforce": bool, "token_sha256": [...]}`. Any valid integration key (the `tool-capabilities`
   gate the MCP already passes) because a new slug would 403 an MCP whose act-as user lacks it and
   take the chatbot down; the answer is digests of 256-bit random tokens. Cached 30 s; an unknown
   bearer re-fetches at most every 5 s before 401; backend down keeps the last answer; no answer
   yet = 503 on `/mcp` (Q5), `/healthz` still 200. Nothing exits.
5. **States.** No token: headerless passes, any bearer 401 (the deploy probe). Token + Enforce off:
   same, and the backend sends the token. Enforce on: no/wrong token 401.

## Zero-downtime release

1. Migration adds empty columns. New backend sends no header; new MCP is permit-like. The
   `deploy.yml` verify step passes unchanged: wrong bearer 401, backend -> MCP call with no header OK.
   The old colour's backend (pre-#1742) sends no header either.
2. Owner generates the token; backend calls carry it within 5 s; MCP accepts it at once (refresh on miss).
3. Owner pastes it into the n8n Bearer credential (heartbeat + MCP Client nodes), checks the heartbeat.
4. Owner switches Enforce on.
5. Leftover `MCP_AUTH_TOKEN` / `MCP_AUTH_MODE` in the server env are ignored; remove at leisure.

Rotation: Rotate, re-paste into n8n within 24 h, optionally "Revoke previous now".

## Out of scope / triggers

- The "Revoke previous now" button is a plain action, not a server-deferred countdown: it ends a
  credential's grace window, not a record delete. Reviewer to confirm.
- Per-caller tokens (n8n vs backend): build when a second external caller needs separate revocation.
