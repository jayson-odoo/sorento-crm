# PLAN - Project intelligence reports (brands and architects)

**Status:** scoped AND grilled with the client 2026-08-12. Ready to build.
**Slug:** project-intelligence-reports
**UAC:** `project-intelligence-reports-acceptance-criteria.md` (governing)
**Parent:** `AUDIT-project-sales-2026-08-12.md` - these are the audit's two requirement
gaps, the only spec rows not built.

## Why now

The Process Flow spec names both reports ("which brands win, by location & budget band";
"which architects to prioritise visiting") and everything they need is already recorded -
except a groupable location. Nothing here asks the salesperson for new data beyond
confirming a pre-suggested State.

## What the data already says (measured on dev, 2026-08-12)

- `project_sales_profile.location` is FREE TEXT: full street addresses, bare suburb
  names ("Setia Alam"), city-state pairs ("Kepong, Kuala Lumpur"). Groupable only
  through a matcher plus a structured field going forward.
- Won money per brand is fully derivable: won scopes → current-version lines →
  `brand_snapshot` + line totals. The rate-only rule and the decimal-string arithmetic
  already exist and are reused, not copied.
- Architect linkage exists (`project_parties`, `party_type='architect'`, reused across
  projects by design - the model's own docstring says this report is why).

## Slices

| # | Slice | Ships |
|---|---|---|
| **S1** | State field | `state VARCHAR(32) NULL` on `project_sales_profile` (migration, defensively re-runnable). `malaysian_states.py`: the 16 values + `suggest_state(text)` - state names first, then an unambiguous-city table (Klang, Ipoh, Kepong...). Registration + edit form gain the select with auto-suggest (AC-A2). Backfill script per AC-A3, run on dev; prod run listed in DEPLOY notes. |
| **S2** | Brands report | `project_intelligence_service.brand_wins(db, company_id, year=None)` → rows of `(brand_label, state, band, won_amount, won_line_count)` in one pass: won scopes (LIVE current version - grill decision 5) joined to their lines, brand normalised per AC-B2, bands fixed, `year` filtering `decided_at`. Route `GET /project-sales/reports/brands?year=`. |
| **S3** | Architects report | `architect_rollup(db, company_id, year=None)` per AC-C1-C3: scope-level win rate (grill decision 7), year over won-side only, pipeline always current; reuses `project_forecast_service`'s definitions and the staleness constants. Route `GET /project-sales/reports/architects?year=`. |
| **S4** | FE tabs | Forecast & Reports page becomes tabbed (Forecast / Brands / Architects). Brands: matrix DataGrid with a State/Band dimension toggle. Architects: ranked DataGrid, name → party page, quiet-flag badge. Standard toolbar, `_shared/lib/money`, no prose. |
| **S5** | Tests + browser | pytest: seeded-chain tests for both services (brand normalisation incl. unmatched snapshot, Unknown/Unstated buckets, rate-only exclusion, win-rate math, quiet flag). vitest: tab states. Playwright: sidebar → both tabs, 375px overflow check. |

S1 unblocks S2's state dimension but S2/S3 are otherwise independent; S4 needs both
routes; S5 lands with S4 (tests in-phase, never after).

## Contract (written before the FE)

`GET /project-sales/reports/brands`

```jsonc
{ "dimensions": { "states": ["Selangor", "Kuala Lumpur", "Unknown"],
                  "bands": ["<500k", "500k-2M", "2M-10M", ">10M", "Unstated"] },
  "rows": [ { "brand": "SORENTO",
              "by_state": { "Selangor": { "won_amount": "1520000.00", "won_lines": 41 } },
              "by_band":  { "2M-10M":  { "won_amount": "1520000.00", "won_lines": 41 } },
              "total_won": "1520000.00", "share_pct": "84.2" } ] }
```

`GET /project-sales/reports/architects`

```jsonc
{ "rows": [ { "party_id": "...", "name": "GDP Architects", "project_count": 8,
              "won_amount": "4200000.00", "pipeline_amount": "2100000.00",
              "win_rate_pct": "37.5", "last_activity_at": "2026-05-02T04:11:00",
              "is_quiet": true } ] }
```

Money is decimal STRINGS end to end, like every other report.

## Risks / honesty

- **The suggestion table will be wrong somewhere.** An ambiguous or unknown city
  suggests nothing - blank beats a confident wrong state. The backfill reports its
  misses instead of guessing (AC-A3).
- **`brand_snapshot` drift.** Old lines may spell a brand differently from the brands
  table; AC-B2 makes that visible (verbatim row) rather than papering over it. If dev
  data shows heavy drift, a normalisation map goes in the service, not in the data.
- **Sparse today.** Dev has 8 quotations and 1 architect party; the report shapes must
  read correctly at that size (no fake density) AND at 100 projects (single-pass
  queries, AC-B5/C5).
- **The live-valuation instability is accepted, on record.** Grill decision 5: a won
  number can move after the fact. The UAC pins the behaviour with a test so a future
  reader finds a decision, not a bug.
- **Not in scope:** configurable bands, a region rollup, architect detail screens,
  stakeholder-linked architect firms, any change to the registration multi-select's
  meaning, `won_version_id` (deferred until the live number's instability bites).
