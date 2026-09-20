# UAC - FoundryX pull connection configured in the UI

Plan: `PLAN-foundryx-pull-connection-ui.md`. Every criterion is a test or a browser check.

## Connection resolution (backend)

- AC-CN-1 With the `foundryx-esb` integration row active, `config_json.base_url` set and
  `credentials_json.api_key` stored, `FoundryxAutocountClient(db)` builds and every FoundryX call
  carries that key in `X-API-Key` and hits that base URL.
- AC-CN-2 No `foundryx-esb` row -> `FoundryxPullError(code="NOT_CONFIGURED", status=503)`; the
  Pull button toast reads "AutoCount connection is not set up for this company." (unchanged text).
- AC-CN-3 Row present but `is_active` false, OR `base_url` blank, OR no credentials, OR
  credentials without `api_key` -> the same NOT_CONFIGURED refusal. Nothing is called.
- AC-CN-4 `app.config.settings` has no `foundryx_base_url` / `foundryx_api_key` attribute;
  `.env.example` and `CLAUDE.md` carry no `FOUNDRYX_*` line; the three user guides describe the
  Integration form, not env vars.
- AC-CN-5 A key changed through `PATCH /api/v1/integrations/{id}` is used by the very next pull
  or task: two client builds in two sessions observe the two different keys, no restart.
- AC-CN-6 Preview and apply RQ tasks build the client inside their own session and behave as
  AC-CN-1 / AC-CN-2 (existing SR1/SR3/SR4 suites stay green with the row seeded instead of the
  settings monkeypatch).
- AC-CN-7 The decrypted key never appears in a log line, in job metadata, in `last_error`, or in
  any API response (`has_credentials` only).

## Test action

- AC-TS-1 `POST /api/v1/integrations/{id}/test` on an `autocount_esb` row whose gateway answers
  404/410 JSON to the nil-snapshot GET returns `{ok: true, message: "Connected", latency_ms}`.
- AC-TS-2 Gateway 401 -> `{ok: false, message: "Key rejected"}`.
- AC-TS-3 Gateway 403 -> `{ok: false, message: "Key is not allowed for this company"}`.
- AC-TS-4 Non-JSON 404 (a web server, not the gateway) -> `{ok: false, message: "Not a FoundryX gateway"}`.
- AC-TS-5 Connection refused / timeout -> `{ok: false, message: "Unreachable: <reason>"}`, within
  the client's connect timeout.
- AC-TS-6 Row not configured (AC-CN-3 cases) -> `{ok: false, message: "Base URL or key missing"}`,
  HTTP 200 (a test result, not an error).
- AC-TS-7 A user with `integration.integrations.view` but not `.edit` -> 403.
- AC-TS-8 A row whose type is not `autocount_esb` -> 400, code `TEST_NOT_SUPPORTED`.
- AC-TS-9 The route touches neither `last_used_at` nor `last_error` and does not write an
  `integration_logs` row.

## Frontend

- AC-FE-1 `IntegrationDetailView` shows a **Test** button only when `integration.type ===
  'autocount_esb'`; other types show no such button.
- AC-FE-2 While the request is pending the button is disabled and reads "Testing…" via the shared
  loading convention (no bare "Loading…" string).
- AC-FE-3 On `ok: true` a success `Badge` reads "Connected"; on `ok: false` a destructive `Badge`
  carries the returned message. Inline, no toast, no dialog. A new click replaces the old result.
- AC-FE-4 Browser (agent-browser, sidebar navigation, lane stack on the clone): open Integration
  Management -> FoundryX ESB -> edit, enter the fake gateway URL + a key, save, Test -> Connected;
  change the key to a wrong one, save, Test -> Key rejected; Products -> Pull from AutoCount then
  refuses with the gateway's 401 message; restore the key, Pull works. Screenshots at 1280 and
  375, no UUID on screen, no console errors.

## Docs

- AC-DC-1 `manage-products.md`, `upload-stock.md`, `data-analysis.md`: the "AutoCount connection"
  paragraph says where the URL and key are entered and what Test shows; no env var named.
