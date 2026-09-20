# PLAN - FoundryX pull connection configured in the UI, not in env

Status: in progress (2026-09-21, owner go given in the Sorento session; SR6 of the AutoCount pull + review work, follows PR #1051)

Owner ruling (2026-09-21, relayed by the FoundryX session, confirmed by the owner here with "yes"):
the FoundryX AutoCount pull connection is configured in Sorento's Integration Management screen
and stored in the database. The backend env vars `FOUNDRYX_BASE_URL` / `FOUNDRYX_API_KEY` go
away. The per-company FoundryX company code stays `companies.code` (SRT / MCH), which is what
the pull already sends. The joint rehearsal with FoundryX then runs through the UI: the owner
types the base URL and the key into the form himself.

## Journey

The owner opens Integration Management, opens the seeded **FoundryX ESB** integration, types the
gateway base URL and the API key FoundryX issued, saves, and presses **Test**. The screen says
"Connected" (or exactly why not). From then on, **Pull from AutoCount** on Products and Stock
Balance works with no host access and no restart. Changing the key later is the same edit; a
wrong key shows up on Test and as a clear refusal on the Pull button, never as a stack trace.

## What already exists (measured on origin/main 86547d074)

- `integrations` table: `config_json` JSONB (non-secret, holds `base_url`) and
  `credentials_json` Fernet ciphertext, write-only over the API (`app/models/integration.py:49-52`).
  Encryption helper `app/utils/field_encryption.py` (key derived from `JWT_SECRET`), used by
  `integration_admin_service.py` (`_encrypt`, `decrypt_credentials`) and the Respond.io keys.
- CRUD + key lifecycle routes `app/api/v1/integrations/admin.py`, gated by
  `integration.integrations.{view,add,edit,delete,manage_keys}`.
- FE `integration-management/integrations`: `IntegrationFormDialog` has `base_url`
  (`config_json.base_url`) and a write-only credential input ("Stored - leave blank to keep")
  that posts `credentials_json: { api_key }` only when filled. Read responses carry
  `has_credentials`, never the value. `IntegrationDetailView` has Issue key / Rotate buttons.
- Seeded row `foundryx-esb` (type `autocount_esb`, label "FoundryX ESB") from migration 297,
  already the identity of the FoundryX PUSH caller (`integration_seed.py`).
- `FoundryxAutocountClient.__init__` (`app/services/foundryx_autocount_client.py:57-64`) is the
  ONLY place the two env settings are read; every caller (`autocount_pull_service.py:183,268,364`,
  `app/tasks/autocount_pull_tasks.py:197,235,341,418`) constructs `FoundryxAutocountClient()`
  with no arguments.
- Company code: `_company_code()` in `autocount_pull_service.py:119` and
  `autocount_pull_tasks.py:328` read `companies.code`. `companies.autocount_ref` exists and is in
  the Company form but the pull never reads it. Unchanged by this plan.
- Test-connection precedents: `POST /system/ai-assistant/test-connection` (probe from request
  body, returns `{ok, message, latency_ms}`) and `POST /user-management/settings/smtp/test`
  (probes the persisted row).

## What is new

### S1 - the client reads the integration row (backend)

`FoundryxAutocountClient.__init__(db)` takes the session it already runs inside and resolves:

1. `Integration` row `name == "foundryx-esb"` (the seeded FoundryX identity; one row, one
   connection, both books share the key because FoundryX scopes the key to SRT + MCH).
2. `base_url = config_json["base_url"]`, `api_key = decrypt_credentials(row)["api_key"]`.
3. Missing row, inactive row, blank base URL or missing key -> `FoundryxPullError(NOT_CONFIGURED,
   503)` exactly as today, so the Pull button keeps saying "AutoCount connection is not set up".

`settings.foundryx_base_url` / `foundryx_api_key` are deleted from `app/config.py`; the
`.env.example` lines go; `CLAUDE.md` env quick reference and the three user guides drop the env
mention. No dev fallback: one source of truth. Tests seed the row (helper in
`tests/support/fake_foundryx.py`) instead of monkeypatching settings.

Every construction site passes its `db`: three in the service (already have `db`), four in the
tasks (each task opens its own `SessionLocal()` already; the client is built inside that scope).
The RQ task never caches the client across jobs, so a key rotated in the UI is used by the next
job with no worker restart.

### S2 - Test action (backend + frontend)

`POST /api/v1/integrations/manage/{id}/test` (the admin router mounts at `/integrations/manage`), gated `integration.integrations.edit`, only for
`type == "autocount_esb"` (other types answer 400 `TEST_NOT_SUPPORTED`). Probes the PERSISTED
row (SMTP-test shape, so what is tested is what the pull will use): builds the client from the
row and calls `GET /api/v1/autocount/snapshots/00000000-0000-0000-0000-000000000000`.

| Gateway answer (confirmed by FoundryX from their code, 2026-09-21) | Result shown |
| --- | --- |
| JSON 404 `UNKNOWN_SNAPSHOT` (or 410) = key accepted | `ok: true`, "Connected" |
| 401 `INVALID_API_KEY` | `ok: false`, "Key rejected" |
| 403 `SERVICE_NOT_ENABLED` | `ok: false`, "AutoCount service is not enabled on FoundryX" |
| 429 `TOO_MANY_REQUESTS` | `ok: false`, "Too many attempts, try again shortly" |
| 404 with no JSON body / HTML | `ok: false`, "Not a FoundryX gateway" |
| connect / timeout error | `ok: false`, "Unreachable: <reason>" |
| NOT_CONFIGURED | `ok: false`, "Base URL or key missing" |

What Test proves: base URL reachable, key valid, service enabled. It does NOT prove the key
covers the current company: the gateway checks company membership only on `POST /snapshots`,
which starts a real build and must never be used as a probe. A key bound to the wrong company
surfaces on the first Pull click as 403 `COMPANY_NOT_ALLOWED` (already shown as the server's
message). The guide says so in one sentence. Trigger for more: FoundryX adds an authed
`whoami` returning the key's company codes (offered by them, not requested).

Budget: each probe costs 1 of the key's 600 requests / 5 min and writes one FoundryX audit
row; each 401 counts against Sorento's egress IP failure bucket. One probe per click, no
auto-retry, no polling.

Base URL: the integration stores the ORIGIN (`https://host`), the client appends
`/api/v1/autocount/...` as it does today. FoundryX's prod gateway is https-only; the client
does not validate the scheme (accepted note from #1051).

Response `{ok, message, latency_ms}`. The key never appears in the response, a log line or
`last_error`. `last_used_at` is not touched (that column means inbound use).

FE: a **Test** button beside Issue key on `IntegrationDetailView` for `autocount_esb` rows only;
result inline as a `Badge` (success / destructive) plus the message, no toast, no modal. Disabled
while running. Rendered at 375px without clipping.

### S3 - rehearsal and cut-over (no code)

Owner enters `http://localhost:8009` + the fresh lane key on the lane stack (clone DB), Test says
Connected, runs SRT products -> SRT stock -> MCH products -> MCH stock, then does the same on
prod with the prod URL + key. FoundryX keeps the gateway unchanged.

## Not built, with the trigger that would build it

- Per-company connection rows: one FoundryX key already covers both books. Trigger: FoundryX
  issues per-company keys.
- A dedicated `/health` or `/whoami` probe: the nil-snapshot GET is enough to tell auth from
  reachability. Trigger: FoundryX adds an authed probe endpoint (asked, 2026-09-21).
- `autocount_ref` as the FoundryX code: `companies.code` is what FoundryX expects today.

## Test list (Phase 2, tester writes red first)

pytest `tests/test_foundryx_connection_ui.py`:
- CN-1..CN-4 client resolution (row present -> works; no row / inactive / blank base_url /
  no credentials -> NOT_CONFIGURED 503).
- CN-5 no attribute `foundryx_base_url` on `settings` (env retired).
- CN-6 pull start with the row present reaches the fake gateway with the decrypted key in
  `X-API-Key` (fake_foundryx records the header).
- CN-7 a key rotated in the row is used by the next task without a process restart
  (build client twice across two sessions).
- TS-1..TS-6 the Test route table above, one test per row, plus TS-7 permission (view-only user
  -> 403) and TS-8 non-autocount type -> 400.
- TS-9 the key value is absent from the response body and from caplog.
vitest `IntegrationDetailView.test.tsx`: Test button only for `autocount_esb`, disabled while
pending, badge + message on ok and on failure, 375px layout not asserted here (browser run).

## Tickets

One issue for the slice (SR6); the UAC is `foundryx-pull-connection-ui-acceptance-criteria.md`.
