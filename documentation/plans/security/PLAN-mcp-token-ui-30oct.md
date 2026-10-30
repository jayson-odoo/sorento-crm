# PLAN: MCP auth token set from the settings screen (no .env)

Status: in review, reviewer READY after one fix round (B1, S1-S3, N1-N2, nit 3; security should-fixes applied), awaiting owner answers on the
design card and hand test (full track, size M: auth + additive migration + settings UI).
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
   The migration also seeds a first random token (Enforce off), never overwriting one (review
   B1): the MCP server honours the staff AI assistant's `X-MCP-Scope: staff` only on a call with
   a valid bearer, so a release with no token would leave the staff assistant's company-scoped
   tools answering `scope_required` until someone clicked Generate.
2. **Service** `app/services/mcp_auth_token.py`: `rotate` (first call = generate;
   `secrets.token_urlsafe(32)`; old token kept `GRACE_HOURS = 24`, Q2), `set_enforce` (409 with no
   token), `revoke_previous`, `describe` (masked last 4), `mcp_answer` (digests), `current_token`
   (5 s process cache). One `MCP_AUTH_TOKEN` audit row per action, action name only.
   After a rotate the backend keeps sending the previous token (none after a first generate)
   for `SEND_NEW_AFTER_SECONDS = 10`, longer than the MCP's 5 s refresh-on-miss interval, so a
   new token is never sent to an MCP that cannot yet know it (review S1). Enforce is refused
   (409) while the token is unset or no longer decrypts (review S2).
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

0. Before releasing (review S5): confirm no n8n MCP node or the heartbeat already sends an
   `Authorization` header (for example a credential prepared for #1742's env token). A presented
   bearer the MCP does not know is 401 in every state, by design (it is what the release probe
   relies on). A node with no header keeps working while Enforce is off.
1. Migration adds the columns and seeds a token; Enforce off. The new backend sends the seeded
   token (after 10 s), so the staff assistant keeps its scoped tools; the new MCP accepts it and
   still serves headerless calls (n8n). The `deploy.yml` verify step passes unchanged: wrong
   bearer 401, backend -> MCP call authenticated. The old colour's backend (pre-#1742) sends no
   header, which passes too.
2. Owner clicks Rotate on Settings > Integrations > MCP access token and copies the value (the
   seeded one stays valid 24 h, and nobody holds it, so nothing breaks).
3. Owner pastes it into the n8n Bearer credential (heartbeat + MCP Client nodes), checks the heartbeat.
4. Owner switches Enforce on. **Owner-assigned, dated release-checklist item**: until it is on, a
   headerless call to 8765 is served, the same exposure as before this lane; the 8765 firewall
   rule stays the outer guard.
5. Leftover `MCP_AUTH_TOKEN` / `MCP_AUTH_MODE` in the server env are ignored; remove at leisure.

Rotation: Rotate, re-paste into n8n within 24 h, optionally "Revoke previous now". Only ONE
previous token is kept (review S4): a second Rotate inside 24 h ends the older token's grace at
once, so n8n must hold the newest-but-one or newer. Changes reach the MCP within 30 s (its cache);
while the backend is unreachable the MCP keeps its last answer, so a revoke waits for the backend.

## Out of scope / triggers

- Stale-while-revalidate in the MCP gate (review N4): a hung backend makes requests wait behind
  one 5 s fetch every 30 s. Build it if that latency is ever seen in the heartbeat.

- The "Revoke previous now" button is a plain action, not a server-deferred countdown: it ends a
  credential's grace window, not a record delete. Reviewer to confirm.
- Per-caller tokens (n8n vs backend): build when a second external caller needs separate revocation.
