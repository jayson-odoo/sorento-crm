# sorento_crm_loadtest

k6 stress-test suite for the Sorento CRM stack: FastAPI backend, Next.js frontend, and the three n8n outbound webhooks (attachment, stock-inquiry-revise, crm-chat-outbound).

## Quick start

```bash
# 1. install k6
brew install k6                    # macOS
# or: https://k6.io/docs/get-started/installation/

# 2. configure env
cp .env.example .env
# fill in N8N_LOADTEST_*_URL, BE/FE base URLs, LOADTEST_USER_EMAIL, etc.

# 3. smoke a single scenario
./ci/run.sh smoke n8n/stock_inquiry_revise

# 4. run a full load profile against local docker
TARGET=local ./ci/run.sh load backend/listings_read

# 5. push results to a local Grafana dashboard
docker compose -f docker-compose.observability.yml up -d
K6_OUT=influxdb=http://localhost:8086/k6 ./ci/run.sh load backend/listings_read
# open http://localhost:3001 (admin/admin)
```

## Repo layout

```
lib/         shared helpers (env, auth, fixtures, thresholds, checks)
fixtures/    JSON sample bodies + sample attachment files
scenarios/
  n8n/         hit cloned n8n LOADTEST workflows
  backend/     FastAPI: auth, list-query, write paths, portal, external API
  frontend/    Next.js prod: SSR pages (http) + signin flow (browser mode)
  ai/          LLM endpoints - bounded spike only
profiles/    smoke / load / stress / spike / soak
ci/run.sh    one entrypoint: ./run.sh <profile> <scenario>
results/     summary JSON output (gitignored)
grafana/     local dashboard provisioning
```

## Targets

`TARGET` env var selects base URLs in `lib/env.js`:

| TARGET   | Backend                          | Frontend                           |
|----------|----------------------------------|------------------------------------|
| `local`  | `http://localhost:8000`          | `http://localhost:3000`            |
| `staging`| set in `.env`                    | set in `.env`                      |
| `prod`   | (resolved via FE)                | `https://fe-sorento.foundryx.my`   |

## n8n stress safety

Never point n8n scenarios at the **production** webhook URLs. Clone the workflows in n8n UI, prefix `[LOADTEST]`, replace WhatsApp/email/DB-write nodes with `Set` nodes returning `{status: "ok"}`. Use the cloned URLs in `.env`.

Export the cloned workflows as JSON and commit under `n8n/workflows/` so the loadtest n8n is reproducible.

## Profiles

| Profile | Use                                       | Duration |
|---------|-------------------------------------------|----------|
| smoke   | sanity gate, 1 RPS                        | 1 min    |
| load    | expected peak hour, sustained             | 10 min   |
| stress  | ramp past peak until thresholds break     | 15-20 m  |
| spike   | 0 → 2× peak in 30s, recovery              | 3 min    |
| soak    | peak/2, find leaks                        | 1-4 hr   |

Profiles use `ramping-arrival-rate` so RPS stays stable regardless of latency.

## Authoring rules

1. Every scenario imports thresholds from `lib/thresholds.js` - never inline.
2. Every scenario reads its base URL from `lib/env.js` - never hardcode.
3. JWT acquisition lives in `lib/auth.js`; one login per VU init, cached.
4. Synthetic data uses `LOADTEST-` prefix in any free-text field so a nightly job can purge.
5. Results emitted via `--summary-export` and (optionally) InfluxDB.

## Production runs

Coordinate before stressing prod:
- post in #ops, set window
- run during low-traffic hours
- start with smoke, escalate only after p95 baseline confirmed
- never run `stress`/`spike` against prod without on-call ack

## CI

`workflow_dispatch` GitHub Action (separate follow-up) runs `smoke` against staging on demand. Threshold breaches fail the run (k6 exits non-zero).
