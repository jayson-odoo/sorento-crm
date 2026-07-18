# LESSONS-LEARNT

Running log of hard-won, non-obvious bugs — one **bolded claim** + mechanism + fix each.
Append here when a root cause was surprising or system-wide. Per-feature decision logs live
with their plan in `documentation/plans/<domain>/`. Governed by `PRINCIPLES.md` > `CLAUDE.md`.

---

## CI / deploy

- **A test that opens `.env` at import time crashes CI `pytest --collect-only` and blocks the deploy.**
  `.env` is `.dockerignore`'d, so it is absent from the CI backend image. A module-level
  `open(".env")` (e.g. to derive `DATABASE_URL`) raises `FileNotFoundError` at *collection* time,
  which errors the whole test package (`ERROR tests/scm`) and fails the "Validate backend imports"
  gate → `build-and-deploy` never runs. Locally it passes because `.env` exists. **Fix:** prefer a
  live env var (`os.environ.get("DATABASE_URL")`), fall back to `.env` only `if os.path.exists(env)`,
  else return `None` so the DB-requiring tests skip instead of crashing collection.

- **An optional call-time `import` must still be in `requirements.txt`, or the feature silently no-ops in prod.**
  `market_research_service` does a local `import anthropic` on the key-gated web-search path. It
  worked locally (venv had `anthropic`) but was never added to `requirements.txt`, so the prod image
  lacked it — the live market search returned `[]` and the assistant said "I don't have information"
  **no matter how valid the configured API key was**. "Optional dep, imported lazily" is not a reason
  to leave it out of `requirements.txt`. **Fix:** pin it (`anthropic>=0.96.0`). Quick unblock without
  a redeploy: `docker compose exec backend_<color> pip install <pkg>` (call-time import, no restart).

- **A PR merges at whatever commit exists at merge-time; commits pushed *after* the merge need their own PR.**
  Pushing more commits to a branch whose PR was already merged does NOT put them on `main` — the merge
  captured only the earlier tip. Verify with `git branch -r --contains <sha> | grep origin/main`.
  **Fix:** finish pushing before the human merges; otherwise branch off fresh `origin/main`,
  cherry-pick the stragglers, open a new PR.

## SCM / modules

- **A module's nav stays hidden even for an admin with all permissions until the module is *enabled* in `tenant_modules`.**
  `filterMenuByModule` (sidebar) drops any group whose `moduleKey` is not in the tenant's
  enabled-module set. Admin/superadmin bypass the *permission* gate but NOT the module-enablement gate.
  Granting `scm.*` permissions is not enough. **Fix:** enable the module in the App Store
  (System Management → App Store), which flips the `tenant_modules.enabled` row. Only `base` is
  enabled-by-default (`installer.py` `is_core=(key=="base")`).

- **Reorder cash-ranking and dashboard valuation read two DIFFERENT cost fields.**
  The engine costs a buy from `product_suppliers.unit_cost` (drives cash-impact ranking). The SCM
  dashboard's Total/Dead/Overstock **valuation** is `on_hand × products.cost_price`. Backfilling only
  supplier `unit_cost` makes buys rank correctly but leaves every valuation at **RM 0** (real products
  had `cost_price` NULL). **Fix:** set both — `product_suppliers.unit_cost` for the plan, `products.cost_price`
  for the dashboard/ABC value.

- **The per-warehouse reorder path emitted "buy 0" recommendations; the network path did not.**
  `_emit_cell` appended a `buy` for any triggered cell, even when the order quantity rounded to 0
  (net already at/above order-up-to after MOQ/multiple) → RM0/qty-0 noise flooding the plan. The
  network path already gated on `rounded > 0`. **Fix:** gate the per-warehouse emit on `rounded > 0`
  too — a triggered cell with nothing to order is not an actionable buy.

- **The cash-budget slider ceiling was silently truncated because the buy fetch was capped at `limit=1000`.**
  The slider max is `Σ costed cash` over the loaded buys. `getBuyRecommendationsForCash` fetched only
  the first 1000 rows, so a >1000-line plan capped the slider far below the plan's true cash impact.
  **Fix:** page past 1000 (mirror the disposition full-fetch). Also: max should be the *exact* cash
  impact, not `×1.1` headroom — budgeting past the total funds nothing and just shows wasted "free".

## Postgres / schema

- **`ON CONFLICT (a, b)` fails with `42P10` when the real unique key has a THIRD column the ORM model doesn't show.**
  `product_suppliers` in prod is uniquely keyed on `(product_id, supplier_id, effective_from)` (a
  temporally-versioned table with `effective_from DEFAULT CURRENT_DATE`), but the SQLAlchemy model
  declared `(product_id, supplier_id)`. `INSERT ... ON CONFLICT (product_id, supplier_id)` →
  "no unique or exclusion constraint matching". The model can drift from the deployed schema. **Fix:**
  check the live constraint (`pg_constraint`) before writing `ON CONFLICT`; when in doubt use a
  `NOT EXISTS` anti-join guard for idempotency instead of relying on constraint inference.
