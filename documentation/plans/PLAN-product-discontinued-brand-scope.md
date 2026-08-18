# PLAN - Product-discontinued notification: per-(company, brand) recipient scoping

**Status:** In progress (branch `fm/product-discontinued-brand-scope`).
**Classification:** CORE, `public` schema (extends the existing core notification feature;
nothing tenant-installable).
**UAC:** `product-discontinued-brand-scope-acceptance-criteria.md` (the contract).
**Parent:** `PLAN-product-discontinued-notification.md` (stamp-first batch mechanics, toggles,
deep link - all preserved).

Process note: autonomous crewmate run. Grill / lavish / to-tickets steps have no human in the
loop; the firstmate brief carries the requirements and acceptance criteria and stands in as the
grilled contract. Deviation to be recorded in the PR description.

## Design

### Semantics (locked)

- A **scope** = (company_id | NULL, brand_id | NULL) per user. NULL company = all companies
  (and forces NULL brand). NULL brand = all brands in that company.
- A product **matches** a scope iff
  `(scope.company_id IS NULL OR scope.company_id = product.company_id) AND
   (scope.brand_id IS NULL OR scope.brand_id = product.brand_id)`.
  A product with `brand_id IS NULL` therefore matches only all-brands scopes (AC-6).
- Channel toggles keep their meaning (HOW); scopes decide WHAT. Recipient of a company batch =
  user with either toggle on, not trashed, whose scopes yield a non-empty subset of that
  batch's products. Zero scopes = zero notices (AC-4).
- Per-recipient content: count/wording/link built from the recipient's subset. If the subset is
  the full batch (an all-brands scope matched), the link is the existing plain
  `?discontinued_batch_id=` link - byte-compatible with today for migrated all/all users
  (AC-1). Otherwise the link appends `&brand_id=<comma-joined sorted distinct brand ids>` from
  the user's matching specific-brand scopes for that company; the filtered list equals the
  subset because NULL-brand products only ever appear in the full-batch case.

### Schema

New table `user_product_discontinued_scopes` in `app/models/user.py` (or a sibling module the
coder judges cleaner - it is a user-preference table):

- `id` UUID pk (str uuid4 default, matching house style)
- `user_id` UUID FK `users.id` ON DELETE CASCADE, not null, indexed
- `company_id` UUID FK `companies.id` ON DELETE CASCADE, nullable
- `brand_id` UUID FK `brands.id` ON DELETE CASCADE, nullable
- `created_at` naive-UTC default now
- Dedupe guard: unique index on
  `(user_id, coalesce(company_id, '00000000-0000-0000-0000-000000000000'),
    coalesce(brand_id,  '00000000-0000-0000-0000-000000000000'))`
  (expression index; avoids depending on PG15 NULLS NOT DISTINCT).
- **Plain `Base` - NOT CompanyScopedMixin, no `__company_shared__`.** The scheduled task
  applies a session-level company scope filter to every CompanyScopedMixin table; a scoped
  preference table would silently hide recipients during scoped runs (AC-11, AC-9).

### Migration (single Alembic revision)

1. Create table + indexes. `down_revision` chains onto the CURRENT committed single head -
   run `alembic heads` first; if multiple heads exist, stop and report (do not merge heads in
   this branch unless they are this repo's own committed state; per PRINCIPLES.md rejoin with
   an empty merge revision only if `alembic heads` already shows >1 on main).
2. Backfill (same revision, after create): insert one `(user_id, NULL, NULL)` row for every
   user with `notify_email_on_product_discontinued OR notify_whatsapp_on_product_discontinued`
   true, guarded by NOT EXISTS on (user_id, both-null) so re-runs and partial prior runs are
   idempotent (AC-2). Trashed users included (toggle state is what we preserve; fan-out still
   filters trashed).
3. Downgrade drops the table.

### Backend service - `product_discontinued_notify_service.py`

Keep `run_product_discontinued_check` structure (per-company grouping, stamp-first commit,
aggregate return shape). Rework `_run_for_company` fan-out:

- Load candidate users once per run (either toggle on, not trashed) with their scope rows
  (single query + `selectinload` or a second IN query; do NOT query the Brand table here -
  match on `product.brand_id` values already in hand, avoiding the session scope filter).
- Per user, compute subset per the matching rule. Empty subset -> skip silently.
- Full-batch subset -> today's exact title/body/wa_text/link. Partial subset -> same wording
  templates with the subset count and the brand-filtered link. `context_vars` /
  `data` payload keys unchanged in shape; `discontinued_count`, `discontinued_link`,
  `whatsapp_text` etc. reflect the recipient's subset.
- `subscribers` in the per-company return dict = number of recipients with a non-empty subset;
  `notified_users` counts successful sends as today. Best-effort try/except per recipient
  unchanged (AC-8). `create_with_channel_preferences` call signature unchanged (same
  email/whatsapp pref attrs - constraint: no new channels).

### Products list filter - multi-brand

`app/api/v1/master_data/products.py` (both list endpoints that accept `brand_id`) +
`product_service`: accept `brand_id` as comma-separated ids; split/strip, single id keeps
current code path (`==`), multiple use `IN` (AC-10).

### User API - scopes CRUD rides the existing user endpoints (AC-12, AC-13)

- Pydantic: `ProductDiscontinuedScopeIn {company_id: Optional[str], brand_id: Optional[str]}`,
  `ProductDiscontinuedScopeOut {id, company_id, company_name, brand_id, brand_code,
  brand_name}`. `UserUpdate.product_discontinued_scopes: Optional[list[ScopeIn]]` -
  replace-all when provided, untouched when omitted. Validation via AppException: brand must
  exist and belong to the given company; `company_id NULL` forces `brand_id NULL`; dedupe
  before insert.
- `UserResponse.product_discontinued_scopes: list[ScopeOut] = []`, populated in ALL THREE
  manual `UserResponse(**user_dict)` builders (`users.py:392,532,832` today) - the known
  manual-dict-drops-fields trap.
- Permission: whatever dependency guards the existing profile/toggle update on that route
  guards scopes too (no new permission).

### Frontend - one screen only

1. **Scope editor** in `user-profile-edit-dialog.tsx` notification section, directly under the
   two discontinued toggles (AC-14, AC-15): rows of company `SearchableSelect`
   ("All companies" sentinel + companies from the existing companies service) + brand
   `SearchableMultiSelect` ("All brands" option + brands of the selected company - reuse
   `use-brand-select-query` if it can filter by company, else filter client-side on the
   brands' company_id). All-companies locks brand to All brands. Add/remove row. Toggle-on
   with zero rows pre-populates the all/all row; zero rows shows a short inline hint (one
   line, per no-explanations rule). FE model `user.ts` gains the camelCase scope list; the
   edit dialog submits snake_case `product_discontinued_scopes` on the existing profile
   update path.
2. **Read view parity** (AC-16): render saved scopes read-only in the same position on the
   profile view (company/brand names, never UUIDs).
3. **Deep link** (AC-17): `ProductsList.tsx` param-normalization effect (currently keeps only
   `discontinued_batch_id`, line ~124) must preserve `brand_id` alongside it and pass it
   through to the API query. Multi-id `brand_id` need not be reflected in the single-select
   brand dropdown; the dropdown may stay on "all" while the param filters the grid.

### Tests (tester seat, Postgres only, seed-own-chain per CLAUDE.md)

- pytest `tests/test_product_discontinued_notify_brand_scope.py`: AC-1..AC-9 including the
  Kia Yee scenario (AC-3) asserting per-recipient counts, link params, and absence for the
  unmatched slice; follow the seeding patterns of the existing
  `test_product_discontinued_notify*.py` files (marker-prefixed rows, blank_session or
  rolled-back SessionLocal).
- pytest for products `brand_id` comma filter (AC-10) and for the user update scope
  validation + response round-trip (AC-12, AC-13 happy + denial + validation).
- Migration backfill test: run the revision's upgrade() against seeded pre-migration users in
  a rolled-back transaction (repo idiom), assert idempotency.
- vitest: scope editor states (AC-18); ProductsList deep-link param preservation.

### Slices

- S1 [FE, Phase 1]: scope editor + read view + deep-link preservation against mocked service.
  **Done** (code only; no browser verification run yet). The expected API contract is
  documented at the top of
  `sorento_crm_frontend/app/(protected)/user-management/users/services/productDiscontinuedScopeService.ts`,
  whose `USE_SCOPE_BRAND_MOCKS` flag is the single Phase-1 mock S2 flips. One addition to the
  plan: the editor needs brands OF A GIVEN COMPANY, so the contract asks S2 for a
  `company_id` filter on `GET /api/v1/master-data/brands/select` (brands are
  `CompanyScopedMixin`, and an admin edits scopes for a company they are not switched into).
  Company options come from the existing `useCompany()` grants rather than the superadmin-only
  `/companies/select`, so a non-superadmin admin can use the editor.
- S2 [BE, Phase 2]: model + migration + backfill, service fan-out rework, products
  multi-brand filter, user API scopes; swap FE mock to real. **Done** (migration
  `375_user_discontinued_scopes`, chained onto `374_merge_proj_media_flyer`; still one
  head). Three notes on top of the plan:
  - `GET /brands/select?company_id=` runs the read under `company_scope(db, {company})`
    but first checks the caller can REACH that company (superadmin/admin, or holds the
    grant; the API-key principal is unscoped by design) and 404s the company otherwise,
    mirroring `system/companies.get_company`. The param widens WHICH company is read,
    never WHO may read it - the precedent set by `lookup.resolve`, which refuses to let
    a JWT user re-scope themselves out of a body value.
  - Scope validation raises `handle_unprocessable` (422) for an unknown company, an
    unknown brand, or a brand outside the named company - matching the FE contract.
  - The three existing discontinued suites seed their subscribers with the all/all scope
    the migration backfills, since a user with no scope now hears nothing by design.
- S3 [T, Phase 2]: pytest + vitest suites above.
- S4 [Review, Phase 3]: reviewer agent + /code-review; evidence run (AC-19).

### Out of scope

New notification channels; any admin surface beyond the existing profile dialog; reflecting
multi-brand deep links in the brand dropdown UI; per-scope channel overrides.
