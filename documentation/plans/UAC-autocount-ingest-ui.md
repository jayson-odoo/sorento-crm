# UAC — AutoCount ingest targets + read-only mirror UI

> **Status:** Slice 1 in build. Companion to `documentation/plans/autocount/PLAN-autocount-ingest-ui.md` (design) and `.../PLAN-autocount-integration.md` (Group A primitives).
> **Orchestration:** built slice-by-slice, phase-by-phase, quality-gated. A phase advances only after its gate passes; a slice advances only after all its phases pass.

## Journey (Phase 0 — the guided experience)

**Actor:** internal CS / procurement / office staff who already live in the Sorento CRM. They do NOT edit AutoCount; AutoCount is the accounting source of truth. The ESB (shared-service) reads AutoCount and pushes canonical records into Sorento.

- **Arrival:** staff open a business module they already use (Master Data, Order Mgmt, Procurement, Inventory) and see the AutoCount-sourced records sitting alongside native ones, in the SAME list UI they already know.
- **What the system already knows:** everything on the record came from AutoCount via ingest. The user is never asked to type it. A `source` badge tells them "this is AutoCount data".
- **The single decision per screen:** "do I need to leave a note or flag this for follow-up?" That is the only thing they can change. Everything else is read-only.
- **What they hold at the end:** an accurate mirror of the AutoCount record inside the CRM, optionally annotated with a Sorento-only note / follow-up flag that survives every future sync.
- **Every other stakeholder:** the ESB's review/preview surface sees exactly what Sorento did with each pushed record (per-record verdict); nothing is written back to AutoCount (ingest emits no lifecycle events).

Schema is designed backwards from this: read-only mirror tables + two ingest-safe annotation columns. No create/edit/delete UI for ingested entities.

## End goal

12 AutoCount entities absorbed as ingest targets (tables + `/external` endpoints) and mirrored read-only in their natural module, with uniform annotation, delivered in 8 gated slices. Reuse existing system components throughout (shared `DataGrid`, existing detail-page shell, shared form controls) — no bespoke design language.

## Global acceptance criteria (every slice)

- **AC-G1 (read-only):** no create/edit/delete of ingested records from the UI. Ingested rows on reused tables (orders/SO/PO) are read-only + all mutating actions blocked BE-side (403), not just FE-hidden.
- **AC-G2 (annotation):** every ingested entity carries `internal_note TEXT NULL` + `follow_up BOOLEAN NOT NULL DEFAULT false`, editable via a PATCH that touches ONLY those two columns. Ingest column-maps never write them → they survive re-sync.
- **AC-G3 (provenance):** every list row + detail response exposes `source: "autocount" | "manual"`, resolved from `sync_source` (orders) / `source_system` (SCM SO·PO) / `integration_references` (new tables). FE gates read-only on it.
- **AC-G4 (idempotency):** re-pushing the same record updates in place, never duplicates. Key = `DocKey` (documents), `PackageCode` (item packages), snapshot run (stock balance), business code (flat masters, via adoption).
- **AC-G5 (verdict/contract):** masters return the `{dry_run, summary, records:[...]}` verdict at HTTP 200; documents follow GRN 201/400-on-missing-master. Both preserve the two-way contract the ESB renders.
- **AC-G6 (RBAC):** flat masters wire 4 places (ENTITY_SPECS + INGEST_PERMISSIONS + READ_PERMISSIONS + PERMISSION_REGISTRY); non-flat get a dedicated router + EXTERNAL_ENDPOINT_PERMISSIONS entry. Each mirror page has a view slug + menu entry. Coverage tests green.
- **AC-G7 (design reuse):** lists use shared `DataGrid` (fixed layout, resizable, explicit `size`, `truncate`+`title`); detail reuses the existing detail-page shell (Toolbar/Breadcrumb/Container/Card, label/value pattern, always render every section with empty state); annotation editor uses shared `Textarea`/`Switch`/`Button`. No new design language.
- **AC-G8 (migration safety):** every new table ships an Alembic migration with explicit `op.create_table` (legacy create_all DBs miss module tables); `down_revision` chains onto the committed head; single head after any main merge.
- **AC-G9 (no UUIDs in UI):** documents show `DocNo` (`source_doc_no`), never `AC-{DocKey}` or raw UUIDs.

## Phase model (per slice) + gates

| Phase | Work | GATE (must pass to advance) |
|---|---|---|
| **1 — FE prototype** | Read-only mirror pages against mock data / stubbed hooks (cloned from `units-of-measure`, minus create/edit/delete, plus source badge + annotation editor). `npm run dev` HMR. | Playwright MCP via sidebar → list renders (loading/empty/data) → detail renders every section + annotation editor → source badge shows. Console clean. Screenshot golden path. |
| **2 — BE wiring + tests** | Models + migration + canonical schema + ENTITY_SPECS/router + list serializer `source` + annotation PATCH + RBAC slugs + FE off-mocks onto real hooks. Tests: pytest (ingest happy + auth denial + validation 422 + adopt-by-code + dry-run + annotation PATCH) + vitest (list + detail: loading/empty/error/data + read-only gating). | All 3 relevant suites green (pytest + vitest); coverage/permission tests green; Playwright MCP re-run against real stack shows identical states with live data; `browser_network_requests` confirms the right `/api/v1/*` calls. |
| **3 — Review** | `/code-review` on the slice diff; address findings; `/simplify` where apt. | Reviewer findings resolved; CLAUDE.md conventions + PR-CHECKLIST satisfied. |

**Slice gate:** all three phase gates green + `npm run build` clean (prod build) → slice done, advance. Only at final handoff do we run `npm run build && npm start` for the user to eyeball.

## Slice → entity → module → table (see PLAN for full DDL)

| Slice/PR | Entities | Module(s) | Tables | Style |
|---|---|---|---|---|
| 1 | credit_terms, tax_codes | Master Data | new (2) | master |
| 2 | sales_agents, payment_methods, tax_entities | Master Data | new (3) | master |
| 3 | item_packages (+lines) | Master Data | new (2) | master (bespoke parent+lines) |
| 4 | stock_balance | Inventory | snapshot_runs + snapshots (new) | report/run |
| 5 | delivery order | Order Mgmt | orders + order_lines (reuse) | document |
| 6 | quotations (+lines) | Order Mgmt | new (2) | document |
| 7 | request_quotations (+lines) | Procurement | new (2) | document |
| 8 | sales order, purchase order | Order Mgmt / Procurement | reuse + ALTER lines | document |

---

## Slice 1 — credit_terms + tax_codes (detailed)

**Why first:** `credit_terms` unblocks supplier/customer ingest (`_supplier_columns`/`_customer_columns` currently RAISE `MissingReference` on any `payment_terms_code`); `tax_codes` is the resolve-target for future document-line `TaxCode`. Both are the simplest flat masters — the template every later slice clones.

### End-to-end flow

```
ESB → POST /external/ingest/credit_terms {records:[{source_ref, source_doc_no, code, terms, term_days, is_active}]}
    → MasterIngestService: validate CanonicalCreditTerm → adopt-by display_term OR insert → link integration_references → verdict 200
Staff → Master Data → Credit Terms (sidebar) → DataGrid list (source=autocount badge)
      → row → detail (read-only fields + Internal note / Follow-up editor)
      → edit note + toggle follow-up → PATCH /api/v1/master-data/credit-terms/{id}/annotation {internal_note, follow_up} → 200, toast
Re-sync same record → UPDATED in place (note + follow_up untouched)
Supplier ingest with payment_terms_code="30D" → resolves credit_terms.display_term="30D" → writes payment_terms_days=term_days (was: retryable)
```

### AutoCount payload (from collection)

- Credit Term: `{DisplayTerm (key), Terms, TermDays}` — canonical `{code=DisplayTerm, terms=Terms, term_days=TermDays, is_active}`.
- Tax Code: `{TaxCode (key), SupplyPurchase (S/P), TaxRate}` — canonical `{code=TaxCode, supply_purchase, tax_rate, is_active}`.

### Tables (new)

`credit_terms`: `id`, `display_term VARCHAR UNIQUE NOT NULL` (adopt key), `terms VARCHAR NULL`, `term_days INTEGER NULL`, `is_active BOOL NOT NULL DEFAULT true` (server_default), `internal_note TEXT NULL`, `follow_up BOOL NOT NULL DEFAULT false` (server_default), `created_at`, `updated_at`.

`tax_codes`: `id`, `tax_code VARCHAR UNIQUE NOT NULL` (adopt key), `supply_purchase VARCHAR(1) NULL`, `tax_rate NUMERIC(9,4) NULL`, `is_active BOOL NOT NULL DEFAULT true`, `internal_note TEXT NULL`, `follow_up BOOL NOT NULL DEFAULT false`, `created_at`, `updated_at`.

### Backend deliverables

1. `app/models/credit_term.py`, `app/models/tax_code.py`; register both in `app/models/__init__.py` (import + `__all__`) — CI builds schema from ORM, so missing = "table does not exist".
2. Alembic migration: `op.create_table` both (explicit; real DDL), unique index on the code column, server_defaults on the bools.
3. Canonical schemas `CanonicalCreditTerm`, `CanonicalTaxCode` in `canonical_masters.py`.
4. Column mappers `_credit_term_columns`, `_tax_code_columns` + register in `ENTITY_SPECS` (`code_column` = `display_term` / `tax_code`).
5. `ingest.py`: add `credit_terms`/`tax_codes` to BOTH `INGEST_PERMISSIONS` (`.edit`) and `READ_PERMISSIONS` (`.view`) — CI asserts equality with `ENTITY_SPECS`.
6. `PERMISSION_REGISTRY`: add `master_data.credit_terms.{view,edit}` + `master_data.tax_codes.{view,edit}`.
7. Rewire `_supplier_columns`/`_customer_columns`: resolve `payment_terms_code → credit_terms.display_term`; found → `payment_terms_days = term_days`; not found → keep `MissingReference` (retryable).
8. Response schemas + list serializer exposing `source` ("autocount" if an `integration_references` row exists for the id, else "manual"); annotation PATCH schema (`internal_note`, `follow_up` only).
9. Routes `app/api/v1/master_data/credit_terms.py` + `tax_codes.py`: `GET /` (page/limit/query/sort), `GET /{id}`, `PATCH /{id}/annotation`. Register in `master_data/__init__.py`. Reuse `require_permission_with_api_key`.

### Frontend deliverables (clone `units-of-measure`, read-only)

Per entity under `master-data-management/credit-terms/` + `tax-codes/`: `page.tsx` (list), `components/<X>List.tsx` (DataGrid, source badge col, drop delete/create), `[id]/page.tsx` (detail: read-only cards always rendered + annotation editor card), `hooks/`, `services/`, `types/`. Menu entries in `config/menu.config.tsx` gated on the view slug. Drop `new/`, `[id]/edit/`, DeleteDialog.

### Tests

- pytest: `test_ingest_credit_terms.py` / `test_ingest_tax_codes.py` — happy create, adopt-by-code, re-push updates-in-place, dry-run writes nothing, validation 422 (bad payload), auth denial (no permission), annotation PATCH touches only 2 cols + survives re-sync; `test_supplier_credit_term_resolution.py` — supplier with resolvable code → payment_terms_days set; unresolvable → retryable.
- vitest: list (loading/empty/error/data + source badge), detail (renders all sections + annotation editor + read-only, save calls PATCH).

### Slice 1 gates

- Phase 1: Playwright — sidebar → Master Data → Credit Terms + Tax Codes render with mock data, detail + annotation editor visible, source badge shows, console clean.
- Phase 2: pytest + vitest green; coverage/permission tests green; Playwright on real stack; network calls correct.
- Phase 3: `/code-review` clean; `npm run build` clean.
