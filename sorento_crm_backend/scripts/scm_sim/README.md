# SCM reorder-engine simulation harness

Repeatable snapshot+diff for the SCM reorder engine. This is **not pytest** - nothing here
asserts pass/fail. It seeds a fixed synthetic world, runs the real engine with a pinned
clock, snapshots the outputs to JSON, and diffs the current run against a blessed baseline.
The point is to answer "did today's engine/UI change make the plan better or worse", by
eye, against 38 scenarios that each probe one axis (steady vs spiky demand, MOQ rounding,
cover-by-stock vs SPO vs PO, price staleness, missing FX rate, reorder-level basis, ...).

Run it after any change to `app/services/scm/reorder_engine.py`,
`reorder_run_service.py`, `reorder_level_service.py`, `price_history_service.py`,
`trajectory_service.py`, `po_book_service.py`, or `summary_order_service.py`.

## One-time setup: create the sim database

The harness runs against a **dedicated** Postgres database, never the shared dev database.

```bash
cd sorento_crm_backend
venv/bin/python -m scripts.scm_sim init
```

This:

1. Resolves the sim database URL - by default, whatever `DATABASE_URL` in your `.env`
   points at, with the database name swapped to `sorento_scm_sim`. Override the whole URL
   with `SCM_SIM_DATABASE_URL`, or just the expected name with `SCM_SIM_DB_NAME`.
2. Creates the database if it does not already exist (`CREATE DATABASE`; needs `CREATEDB`
   on the Postgres role - if your role lacks it, `createdb sorento_scm_sim` by hand first
   and re-run `init`).
3. Bootstraps it into a runnable schema: `Base.metadata.create_all` + the `scm` schema +
   the `scm.*` reporting views (reusing `scripts/bootstrap_env.py`'s own functions) +
   `scm.import_field_alias` / `scm.priority_policy` seeds + `alembic stamp head`. Deliberately
   **skips** the full RBAC/reference-data seed (`seed_reference_data()`) - the harness calls
   `reorder_run_service` directly, never through an authenticated route, so no roles or
   permissions are needed.
4. Re-applies `scm.committed_v` from `app/services/scm/demand.py`'s `COMMITTED_V_SQL` and
   verifies the fix took (`bootstrap_env.create_views()` only replays migrations
   274/311/327/337, which leaves `committed_v` missing the 340/346 project-demand rule  - 
   this is a known gap in `bootstrap_env.py` itself, not something specific to this harness).

Re-running `init` against an already-bootstrapped database is safe (idempotent).

## Running

```bash
venv/bin/python -m scripts.scm_sim run                    # all 38 scenarios
venv/bin/python -m scripts.scm_sim run --scenario SIM-P025 # one scenario only
venv/bin/python -m scripts.scm_sim run --baseline          # also bless the result
venv/bin/python -m scripts.scm_sim compare                 # diff current vs baseline
venv/bin/python -m scripts.scm_sim compare --strict        # same, but exit 1 on any change
```

Every `run`:

1. Re-validates that the resolved database is literally named `sorento_scm_sim` (or whatever
   `SCM_SIM_DB_NAME` says) - hard refuses otherwise. This check runs again right before the
   `TRUNCATE`, not just at startup.
2. `TRUNCATE`s every table the sim world writes to (`runner._SIM_TABLES`) - safe as a blunt
   reset only because the database is dedicated and provably has nothing else in it.
3. Seeds the shared infra (2 warehouses, 3 suppliers, 2 customers, 1 category, 1 uom, one
   CNY currency rate) + every scenario's product/stock/demand_stat/supplier-link/history
   rows, all dated relative to `world.AS_OF` (2026-09-01), never to `date.today()`.
4. Patches `app.services.scm.reorder_run_service.date` to a frozen subclass whose `.today()`
   returns `AS_OF`, then calls `reorder_run_service.create_run(...)` +
   `run_reorder(run_id, db=db)` synchronously (no worker needed).
5. Asserts the run's status is `completed`; a `failed` run prints `error_text` and exits 1.
6. Snapshots every output into `snapshots/current.json`, prints a one-line-per-scenario
   summary (`rec_type=rounded_qty`, or `NONE`), and - with `--baseline` - also writes
   `baselines/baseline.json`.

## Blessing a new baseline

After deliberately changing engine behaviour and confirming the new numbers by eye:

```bash
venv/bin/python -m scripts.scm_sim run --baseline
```

`baselines/baseline.json` is a plain JSON file - commit it like any other fixture so the
diff is visible in the PR.

## What gets snapshotted, per scenario

- `recommendations`: every `scm.reorder_recommendation` row the run wrote for that product
  (rec_type, quantities, unit_cost/currency/cash_impact, confidence_band, triggered_reason,
  allocation, and the FULL frozen `inputs` JSONB - reproducibility per AC-M3.11).
- `net_position`: the live `scm.net_position_v` row (on_hand, on_order, committed, net).
- `reorder_level`: the raw `scm.reorder_level` row (level / source / suggested_level /
  suggestion_basis / amended_level).
- `level_suggestion`: `level_suggestion_service.suggestions_for_run(...)`, keyed back to
  this product+warehouse.
- `trajectory`: `trajectory_service.trajectory_for_run(..., as_of=AS_OF)["series"]`, keyed
  by product+segment.
- `po_book`: `po_book_service.po_book_for_run(...)`, keyed by product+warehouse.
- `price_history`: `price_history_service.price_history_for_run(..., as_of=AS_OF)`, keyed
  by product+supplier-code.
- `order_summary_row`: `summary_order_service.report(...)`, minus two fields excluded for
  the reason below.

UUIDs are never in the snapshot - everything is keyed and cross-referenced by human code
(`SIM-P0NN`, `SIM-WH-D`, `SIM-SUP-A`), matching the "no UUIDs" rule everywhere else in this
codebase.

## Things that resisted pinning (documented, not fixed)

- **`level_suggestion_service.refresh_for_run`** and **`summary_order_service.write_rows`**
  are called by `run_reorder` itself as a best-effort post-commit hook, WITHOUT `as_of` - so
  the run's own hook computes them against the real wall clock, not `AS_OF`. `snapshot.py`
  re-invokes both explicitly with `as_of=AS_OF` before reading anything back, overwriting
  the unpinned result. This is why the snapshot is deterministic even though one code path
  inside the engine is not.
- **`coverage_service`** (which `summary_order_service.write_rows` calls internally for the
  dated shortfall projection) reads `datetime.now(MALAYSIA_TZ)` inline, with no `as_of`
  parameter at all - it cannot be pinned without patching a third clock. Its two
  date-projected fields, `shortfall` and `max_days_outstanding`, are **excluded** from the
  snapshot (`snapshot._ORDER_SUMMARY_UNPINNED_FIELDS`) because they will differ between two
  runs on two different real days even though nothing about the plan changed. Every other
  `order_summary_row` field (`on_hand`, `project_demand`, `dealer_outstanding`,
  `qty_on_order`, `qty_in_transit`, `suggested_qty`, `avg_daily_demand`, ...) is stable and
  is kept.
- **`inbound_shipments` / `spo_allocations` "open" predicate** (`shipment_status NOT IN
  (...)` / `receipt_status <> 'received'`) is a live status check, not date-driven, so it
  needs no pinning - it was checked, not assumed.

## Documented engine quirks the scenarios pin (NOT bugs to fix here)

- **SIM-P025 ("cover by PO only")**: per ADR / migration 337, `scm.on_order_v` reads the SPO
  allocation, never the purchase order - the PO book (`po_ordered_v`) is informational only
  and does **not** net against demand. This scenario seeds an open PO covering the whole
  deficit and a committed SO line; the actual engine behaviour is a **buy still fires** for
  the full amount, with `po_ordered` merely visible (unused) in the frozen `inputs`. If a
  future engine change makes PO exposure net against demand, this scenario is exactly where
  the diff will show up.
- **SIM-P020 ("MoQ 100, need 20, cold selling")**: a probe, paired with SIM-P019 (same MOQ/
  order-multiple, "hot" instead of "cold" demand). Both currently round up to the full MOQ
  regardless of how weak the underlying demand signal is - `round_order_qty` has no
  confidence/demand-strength gate. Not asserted; the snapshot records whatever the engine
  actually does, so a future change to that gating shows up as a diff on exactly these two
  rows.
- **Price-history "standing_gap_pct" is always 0 whenever a purchase-order history exists**
  for the (product, supplier) pair (SIM-P011 through SIM-P014). `load_supplier_candidates`
  prefers "what we last paid" (`last_po`) over the contract `unit_cost` - so the
  recommendation's frozen `unit_cost` (the "standing" cost `price_history_service` compares
  against) is *already* the last purchase price by construction. There is no gap to report
  by definition, not because the arithmetic is broken. `standing_gap_pct` is only ever
  meaningful when `unit_cost_source == "contract"` (no PO history at all, e.g. SIM-P015
  through SIM-P018).

## The FE simulation page (`/scm/simulation`)

The scenario grid (`GET /api/v1/scm/simulation/scenarios`) shows both sides of every row:
the OUTPUT the engine decided (Rec / Qty / Cash impact, as before) and the INPUT it decided
against - On hand, SO / OI (the committed-demand figure, labelled "SO" for a dealer-segment
scenario and "OI" for a project-segment one - Order Inquiry vs Sales Order, per the M8
engine target model), SPO (incoming) and PO (open, informational only per ADR/migration
337 - never nets against demand). These four are read off the snapshot's own
`net_position` + first recommendation's frozen `inputs.po_ordered` (falling back to the
blessed baseline when there is no current run) - not off the `ScenarioSpec` the world was
seeded from - so they read exactly like a real Reorder Planning row for the same product,
which is the point: eyeball the sim grid next to the real planning page and the numbers
should agree in shape. `po_open` reads `0`, never `null`, when nothing carried one (a
scenario can have net_position with no recommendation at all - SIM-P031, SIM-P038).

## Serving the sim database to the real UI

Everything above (`run` / `compare`) drives the engine directly - no HTTP, no browser. To
instead see the sim scenarios rendered by the REAL Reorder Planning page (On hand / SO /
SPO / PO / Suggested action / Decision columns, drill-downs, the works), point a whole
backend process at the sim database and open the app against it.

### One-time: copy an admin login into the sim database

```bash
venv/bin/python -m scripts.scm_sim seed-auth
```

Reads `.env`'s own `DATABASE_URL` (the REAL dev database, read-only) and copies every user
whose role is `superadmin` or `admin` into the sim database (idempotent - upsert by id):
their `users` row, the qualifying `user_roles` row, and the `user_role_assignments` link.
Permission-grant rows are deliberately **not** copied - `UserPermissionService.check_user_
has_permission` returns `True` outright for any superadmin/admin role, so per-permission
rows are never consulted for these users (verified against the code, not assumed). The
module guard is a no-op too, as long as `MODULE_GUARD_STRICT` stays off (the local-dev
default; `seed-auth` prints which case applies).

Login on this app is an **opaque per-row session token** (`user_sessions.token`), not a
stateless JWT - `get_current_user` looks the exact token up in whichever database the
process it's called against is actually connected to. So a token from your normal
`:3000`/`:8000` session will not resolve against the sim database on its own. `seed-auth`
copies each copied user's currently-active (non-revoked, unexpired) REAL sessions into
the sim database - if you are already logged in on the normal stack, that same browser
session keeps working the moment you point it at the sim-backed process instead.

No session token is ever minted or printed: a token is a live credential and must not
land in stdout or logs. For browserless `curl` verification use the `X-API-Key` +
`EXTERNAL_API_KEY_ACT_AS_USER_ID` pair from `.env` instead.

Re-run `seed-auth` whenever the real dev database's admin/superadmin roster changes, or
whenever you want a fresh browser-session copy (e.g. you logged in again).

### Serve the backend against the sim database

```bash
venv/bin/python -m scripts.scm_sim serve                 # :8060 (default)
venv/bin/python -m scripts.scm_sim serve --port 8062      # any other port
```

Resolves `DATABASE_URL`/`DIRECT_URL` to the sim database exactly like `run` does (same
guard - refuses anything but `sorento_scm_sim`), then runs `uvicorn app.main:app` on
`--port` in the foreground until Ctrl-C. **Never kills anything**: if the port is already
LISTENing, it exits with a message telling you to stop that process yourself first.

Port **8060** is special: it is the port the committed FE production build's
`NEXT_PUBLIC_API_URL` is baked to (a `next build` bakes env vars into the client bundle -
there is no runtime override), and that build is served at `:3060`. Serve on `:8060` and
`:3060` shows the sim world with zero FE changes. Any other port needs its own frontend
(dev server or a separate build) with `NEXT_PUBLIC_API_URL` pointed at it by hand.

### The full recipe

```bash
# 1. stop whatever is currently serving :8060 (your normal backend, if that's what's there)
# 2. one-time / whenever the admin roster or your login changes:
venv/bin/python -m scripts.scm_sim seed-auth
# 3. run a fresh simulation so there is something to look at (optional - the last `run`'s
#    snapshot is already loaded into the sim database from when you made it):
venv/bin/python -m scripts.scm_sim run
# 4. serve:
venv/bin/python -m scripts.scm_sim serve
# 5. open http://localhost:3060 - Reorder Planning shows the SIM-P rows (the run's own
#    "today or latest completed" fallback picks it up automatically, since it is the only
#    run in the database), the Simulation page's Run button is armed (sim_db_active: true).
# 6. Ctrl-C the serve process, restart your normal backend.
```

## Adding a scenario

Add a `ScenarioSpec(...)` to `scenarios.SCENARIOS` (and `BY_CODE` picks it up
automatically). Every field is documented on the dataclass in `world.py`. Re-run, eyeball
the new row's summary line + full JSON entry, then `run --baseline` once it looks right.
