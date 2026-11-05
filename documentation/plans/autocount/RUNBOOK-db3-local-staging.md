# RUNBOOK: local db3 staging (test every AutoCount integration safely)

Owner, 5 Nov 2026: "we can just use local as our staging". A local CRM copy plus a local Shared
Service (SS) copy, both at main. The CRM company **SRT_DB3** maps to the AutoCount **db3** test
book only. db1 (Sorento) and db2 (Mocha) stay protected by SS's db3-only write guard. Nothing
here touches prod.

Pieces:
- Seed script: `sorento_crm_backend/scripts/staging/seed_db3_staging.py`.
- SS side: `documentation/plans/autocount/CONTRACT-db3-local-staging-ss.md`.

## Start (first time)

1. **CRM database.** Copy the dev database into one whose name carries a staging token:
   `createdb -T <dev db> sorento_staging`. Never seed the shared dev database itself: the
   script re-points the one global `foundryx-esb` row and turns the write switches on, which
   would break every other lane on it. The script refuses a database that:
   - is not on this machine, or could be rerouted elsewhere (`?host=`/`?service=` in the URL,
     or `PGHOST`/`PGHOSTADDR`/`PGSERVICE` set);
   - has no `staging`/`stg` token in its name;
   - has a `prod`/`production`/`live`/`main` token in its name.
2. **CRM env.** Copy `sorento_crm_backend/.env` to `.env.staging` and point `DATABASE_URL` and
   `DIRECT_URL` at `sorento_staging`. Leave the SMTP and Respond.io variables unset so nothing
   reaches a real person.
3. **SS.** Bring up local SS at main with company `SRT_DB3` bound to db3 only (contract
   section 5). Note its URL and an SS API key that can see SRT_DB3.
4. **Seed.** From `sorento_crm_backend/`:
   ```
   export SORENTO_ENV_FILE=.env.staging
   export STAGING_SS_API_KEY=<CRM -> SS key> STAGING_ADMIN_PASSWORD=<choose one>
   export STAGING_SS_PUSH_KEY=$(openssl rand -hex 24)   # SS sends it to the CRM; at least 32 characters
   venv/bin/python -m scripts.staging.seed_db3_staging --ss-base-url http://localhost:<ss port>
   venv/bin/python -m scripts.staging.seed_db3_staging --ss-base-url http://localhost:<ss port> \
     --apply --confirm-db sorento_staging
   ```
   The first command is a dry run that lists what would change. The second applies it; it
   needs the database name typed out in `--confirm-db`. The admin email must be on
   `example.com`/`.org`/`.net`, so the script can never take over a real login. Keep the run's
   output out of tickets and PRs: a minted push key is printed there once.
5. **SS push target.** Configure SS's CRM push target as `http://localhost:8000` with the same
   `STAGING_SS_PUSH_KEY` as its `X-API-Key`.
6. **Run the stack.** Start the backend with `SORENTO_ENV_FILE=.env.staging`, plus the worker
   (pulls run on it), the frontend and the MCP server (CLAUDE.md "Dev sessions"). Sign in as
   `staging-admin@example.com`; its active company is already **SRT_DB3**. Use the company
   switcher to move between SRT_DB3 and the real companies on the copy.

## Refresh data from db3

- Pushes: let SS's poll run, or trigger its "just now" / byLastModified poll for SRT_DB3. Masters
  must land before documents.
- Pulls, run from inside SRT_DB3: Products, Stock, GRN and Orders lists, then **AutoCount pull**.
  Review the result in System > Import jobs > AutoCount pull. The worker must be running.
- Re-run the seed with `--apply` at any time. It is idempotent: it keeps the company, re-points
  the integration and turns the switches back on.

## Reset

1. Stop the backend and the worker.
2. `dropdb sorento_staging`, then repeat Start steps 1 and 4. Keep the same
   `STAGING_SS_PUSH_KEY` so SS needs no change.
3. db3 is AutoCount's own test book. Documents written there stay there; reset it on the
   AutoCount side if needed.

## What to try (inside SRT_DB3)

| Integration | Where | Switch (turned ON by the seed) |
| --- | --- | --- |
| PO line <-> SO line link / unlink / relink (#2168) | Project sales > Stock debt > drill a line > PO actions | `stock_debt_po_link_enabled` |
| Project quotation / SO create, update, cancel (#2173) | Project sales > quotation document / sales order > AutoCount actions | `project_autocount_write_enabled` (only once #2173 is on main; until then the seed reports it skipped) |
| Delivery Order pull + confirm | Orders list > AutoCount pull | none (permission only) |
| GRN pull | Procurement > GRN list > AutoCount pull | none |
| Products / item class / stock pull | Products list, Stock balance grid > AutoCount pull | none |
| SS pushes (branches, customers, suppliers, PO/SPO, SO, GRN, DO, stock) | arrive on their own from SS's poll | none |
| Document finder | not a CRM screen on main (no CRM caller found); it lives in SS or in #2173's document read | - |

Every switch also shows under Settings, and the seed's admin is a superadmin, so every permission
applies.

## Safety

- Every CRM call names `companyCode`. SRT_DB3 only ever reaches the SS company bound to db3, and
  SS's guard refuses writes to any other book.
- **The push key is admin-level.** It acts as the `foundryx-esb` principal (role at parity with
  Admin, `app/services/integration_seed.py:106`), and an `X-API-Key` call without a contact reads
  every company on the copy (`app/services/company_scope_resolver.py:361-365`). Keep the staging
  backend on `127.0.0.1` rather than Tailscale/LAN while the copy holds real data.
- **The real companies on the copy (SRT, MCH) can still reach SS.** If the local SS also holds
  the SRT/MCH companies, a pull from inside them reads db1/db2. Writes are still refused by the
  db3-only guard. Stay in SRT_DB3 to test.
