# 17 (Sorento side) — GRN ingest: Decimal qty + supplier + dry_run/verdicts/idempotency

> **Copied into sorento_crm from foundryx-shared-service** `documentation/plans/sprint-4/17-autocount-grn-picking-SORENTO-SIDE.md` (branch `sprint-4/17-autocount-grn-picking-fx`) on 2026-07-26. Section below is Sorento-side analysis added on copy; everything from "# 17 (Sorento side)" onward is the verbatim handoff.

---

**Status:** DONE (uncommitted) on `fix/ingest-status-codes-and-dry-run`. 1a + 1b + 1c built + verified. Migration `310_autocount_grn_decimal_supplier` (chains onto 309) widens the four picking qty columns to `numeric(15,4)` (drops + recreates the generated `quantity_discrepancy` AND the dependent `scm.receipt_lead_v` view around the ALTER), widens header totals, and adds `supplier_code` + `supplier_id` to `picking_headers`. New `GrnIngestService` (clone of the DO ingest) drives the endpoint: `source_ref` present -> adopt-by-source_ref verdict envelope (200-always, dry_run rolls back, product/warehouse miss -> retryable, supplier/uom resolve-or-null); `source_ref` absent -> legacy create-only 201 (back-compat). pytest `tests/test_ingest_grn.py` (12 cases) green; procurement/SCM procurement files (72) green; FE `grn-schema` vitest (decimal accept) green; live HTTP smoke on :8030 confirmed dry_run/create/update-idempotent + legacy 201. **Gotcha found:** the picking Decimal ALTER is blocked by the `scm.receipt_lead_v` view (depends on `qty_accepted`/`qty_rejected`) - drop + recreate it around the widen (dev DB stamped at foreign 311 so DDL applied directly, not via `alembic upgrade`).

## Sorento context + gap analysis (added 2026-07-26)

**Where this sits vs what's already shipped.** PR #46 (`fix/ingest-status-codes-and-dry-run`) already built the adopt-by-`source_ref` + Decimal + dry_run + per-record-verdict ingest pattern for **12 AutoCount entities** (masters, item_packages, stock_balance, delivery order, quotations, request_quotations, sales/purchase order). The GRN endpoint is the **one remaining legacy ingest** still on the old create-only / `201`/`400` / integer-qty / no-supplier / no-idempotency shape. This plan brings GRN into line with that pattern. The "reuse map" (§4) is 100% satisfied in our tree — `MasterIngestService`, `IntegrationReferenceService` (+ `IngestResult`/`as_dict()`), per-record savepoints, and the string→Decimal coercion validator all exist and are exercised by PR #46's suites.

**Current state (verified in `sorento_crm-autocount`):**
- `app/api/v1/external/grn.py` — `POST /` is create-only, `status_code=201`, raises `400` on missing products / empty lines. No `dry_run`, no `source_ref`, no verdict envelope. (The delivery-order ingest service `app/services/delivery_order_ingest_service.py` from PR #46 is the closest working template — same document-with-lines adopt/replace shape.)
- `app/models/procurement.py` `PickingLine` — `quantity_expected` / `quantity_picked` / `qty_accepted` / `qty_rejected` are `Integer`; `quantity_discrepancy` is `Integer` `Computed(...)`. **All need Decimal widen (1a).**
- `PickingHeader` (`:212`, `class PickingHeader(Base, CompanyScopedMixin)`) — has NO `supplier_code` / `supplier_id` / `source_ref` columns. **Add supplier (1b).**
- `app/schemas/external/procurement.py` — `GRNLine.quantity: int` (`:103`), `GRNHeader` has no `supplier_code`/`source_ref`. The `coerce_quantity`-style validator exists on `PurchaseRequestExternalLine` (`:75`) — copy it onto `GRNLine`.
- `IntegrationReferenceService.SUPPORTED_ENTITY_TYPES` already includes `"picking_headers"` (the allowlist entry is the **real table name**, interpolated into the existence-check SQL). Decision: use `entity_type="picking_headers"` directly (already allowed) rather than adding a logical `"goods_received_note"` alias — a logical name that isn't a real table would break the existence check (learned in slice 5: DO used `entity_type="orders"`, not `"delivery_orders"`).

**Net-new work (three changes, all GRN-specific):**
1. **1a Decimal widen — the "sleeper".** Migration (chain onto our current head `309_autocount_so_po_pricing`) + model `Numeric` + the downstream sweep. Verified sweep scope: BE `app/schemas/procurement.py` (int fields `quantity_expected`/`quantity_picked`/`quantity_discrepancy`/`total_items_discrepancy` + SPO-related), and readers in `spo_allocations.py`, `procurement_service.py`, `embedding_worker.py`, `scm/purchase_order_service.py`, `scm/analytics_service.py`, `mcp_tool_capability_service.py`; **FE** `procurement-management/grn/` (types/forms/GRNForm/GRNDetail) + `procurement-management/picking-lines/` (types/service/list). A response field left `int` silently truncates `2.5 → 2` — this is the real cost.
2. **1b Supplier on `picking_headers`.** Additive migration (`supplier_code String(50) NULL`, `supplier_id UUID NULL FK→suppliers ON DELETE SET NULL`) + model + `GRNHeader` schema (`supplier_code` + `source_ref`, both optional for back-compat). Resolve-or-null; a supplier miss must NOT 400.
3. **1c GRN endpoint → verdict envelope + dry_run + idempotency.** Rewrite `create_grn` to route through a `GrnIngestService` (clone `delivery_order_ingest_service.py`): adopt-by-`source_ref` via `integration_references`, product miss ⇒ `retryable` (not 400), `dry_run` rolls back (service savepoint + endpoint top-level), `200`-always verdict envelope. Keep the create-only array-of-one path for callers that omit `source_ref` (back-compat).

**Two Sorento-specific gotchas the handoff predates:**
- **Multi-company (post-#46 merge).** `PickingHeader` AND `PickingLine` are `CompanyScopedMixin`. The GRN ingest's ORM header insert auto-stamps `company_id`, but any **raw-SQL line insert bypasses the auto-stamp** and the fail-closed SELECT filter then hides the lines — carry the header's `company_id` onto each raw line insert (exactly the fix applied to DO/SO/PO line inserts in PR #46). If the GRN ingest reuses `PickingHeaderService.create_grn` (ORM) for lines too, this is moot.
- **Migration chaining.** The Decimal-widen + supplier migrations must chain onto `309_autocount_so_po_pricing` (our head), keeping a single alembic head. Same discipline as PR #46's 302→309 re-root.

**Effort read:** 1c is mechanical (a near-verbatim clone of the DO ingest service). 1b is small (2 columns + resolve). **1a is the bulk** — the column widen is trivial, but the BE+FE `int`→`Decimal` sweep across ~8 BE files + ~7 FE files is the work, and a missed field truncates silently. Blast radius stays zero until FoundryX flips `AUTOCOUNT_GRN_DELIVERY_ENABLED=true` (§2), so this can ship incrementally.

---

> **Repo:** `sorento_crm` (the AutoCount checkout — verified against `sorento_crm-autocount`, branch `fix/ingest-status-codes-and-dry-run`). This is a **standalone handoff** for the Sorento team — no FoundryX-repo access needed.
> **Counterpart:** the FoundryX ESB side is DONE and merged behind a flag (`AUTOCOUNT_GRN_DELIVERY_ENABLED`, default OFF). It will not send a single GRN until Sorento ships these three changes AND the flag is flipped ON. So this work has no live blast radius on either side until both are deployed + coordinated.
> **Goal:** turn the existing single-doc `POST /api/v1/external/grn/` (create-only, 201/400, integer qty, no supplier, no idempotency) into an **adopt-by-`source_ref`, Decimal-quantity, dry-run-capable, per-record-verdict** endpoint — reusing the EXACT pattern slice 14 already shipped for the masters ingest.
> **North star: reuse the masters ingest, don't invent a second convention.** `MasterIngestService` + `IntegrationReferenceService` + the `IngestResult`/`as_dict()` verdict envelope + per-record savepoints already exist and are battle-tested. The GRN endpoint must return the *same* envelope shape and adopt via the *same* `integration_references` table. Every "how do I…?" below has a masters answer to copy.

---

## 0. The wire contract FoundryX now sends (frozen — build to this exactly)

FoundryX delivers **one GRN per HTTP call** (chunk size 1 — the sink already loops), to `POST /api/v1/external/grn/`, `X-API-Key` auth (unchanged). Two call shapes:

**Preview:** `POST /api/v1/external/grn/?dry_run=true` — resolve + predict + **roll back, write nothing**.
**Commit:** `POST /api/v1/external/grn/` (no param) — resolve + write.

Body (a single `GRNRequest`, NOT `{records:[...]}`):

```json
{
  "goods_receive_notes": {
    "picking_number": "GRN-0012",        // display doc no. — MUTABLE, never the identity key
    "picking_date": "2024-01-15",
    "notes": "Received goods",
    "supplier_code": "400-A001",         // NEW — resolve to a supplier; miss must NOT 400
    "source_ref": "AED_VSOFT:100"        // NEW — the STABLE identity ({autocount_db}:{AutoKey})
  },
  "grn_lines": [
    { "product_code": "ITEM-1", "quantity": "2.5", "location": "MAIN", "uom": "UNIT" },
    { "product_code": "ITEM-2", "quantity": "1",   "location": "MAIN", "uom": "BOX"  }
  ]
}
```

Contract notes that drive the design:
- **`quantity` arrives as a JSON STRING** (`"2.5"`) — it is a `Decimal` on the FoundryX side, serialized as a string to avoid float drift. Parse it as `Decimal`, never `int(...)`.
- **`source_ref` is identity, `picking_number` is display.** Adopt/idempotency is keyed on `source_ref` only. `picking_number` is the human doc no. and can change on the AutoCount side; never adopt by it, never rely on any `picking_number` uniqueness.
- **`supplier_code` is captured-if-resolvable.** A supplier miss must NOT fail the GRN — products are the hard requirement (they already 400 on miss); supplier resolves-or-null.
- **`uom` is a CODE string (`"UNIT"`), not a `uom_id`.** The current `GRNLine` schema has `uom_id` — FoundryX cannot send an id (AutoCount has no knowledge of Sorento's uom ids). Either resolve `uom` code → `uom_id` (like `location` → warehouse already works), or accept it best-effort. See §1c wire-gap note.
- **`spo_allocation` is NOT sent in v1** (deferred on the FoundryX side — logged there as a follow-up). The endpoint's existing SPO-allocation resolution stays as-is for other callers; a FoundryX GRN simply omits it.
- **Response (both dry_run and commit): the masters verdict envelope, one record.** FoundryX parses `summary` + `records[].{source_ref, outcome, entity_id, diff?}` and will not read anything else. A single-doc GRN is a **one-record envelope**.

Expected response (HTTP **200**, even on a per-record failure — see §1c):

```json
{
  "summary": { "total": 1, "created": 1, "updated": 0, "failed": 0, "retryable": 0 },
  "records": [
    { "source_ref": "AED_VSOFT:100", "outcome": "created", "entity_id": "<picking_header_id>" }
  ]
}
```

`outcome ∈ {created, updated, failed, retryable}` — identical semantics to masters:
- **created** — new picking written (+ `integration_reference` written), or predicted (dry_run).
- **updated** — existing picking (adopted by `source_ref`) overwritten; include a `diff` (before/after) when dry_run, like masters.
- **retryable** — a referenced master is missing (product / warehouse). **Nothing written.** The ESB re-drains after the masters sync. This REPLACES the current `400 "Missing product codes"`.
- **failed** — bad data that will never resolve. Nothing written. Quarantine, do not retry.

---

## 1. The three changes

Do them in order, each with its own tests, then run the full procurement/SCM suite green. This is on the branch `fix/ingest-status-codes-and-dry-run` (already cut).

### 1a. Widen picking quantities to Decimal (AC-17-01)

**Grounded:** `app/models/procurement.py` — `PickingLine.quantity_expected` / `quantity_picked` / `qty_accepted` / `qty_rejected` are `Column(Integer)`; `quantity_discrepancy = Column(Integer, Computed("(quantity_expected - quantity_picked)"))`.

- **Migration** (Alembic): `ALTER COLUMN … TYPE numeric USING col::numeric` for the four qty columns. The `Computed` discrepancy follows automatically once its operands are numeric (drop+recreate the generated column if Postgres won't alter it in place). No loss on existing whole-number rows.
- **Model:** `Column(Numeric(...))` on all four (+ keep the `Computed` discrepancy).
- **The real cost is the downstream sweep, not the column.** `grep` every reader of these four columns — `procurement_service.py`, `scm/*`, analytics, exports, any `int(...)` cast, and **any Pydantic response field typed `int`** (`app/schemas/procurement.py PickingLine*`, discrepancy/received fields). A response field typed `int` silently truncates `2.5 → 2`. Fix the schema types to `Decimal` too. This is the sleeper — budget for it.

### 1b. Supplier on the picking header (AC-17-02)

**Grounded:** `PickingHeader` (`app/models/procurement.py:211`) has NO supplier column. `Supplier.supplier_code` (`:22`) is `String(50), unique`. The masters lookup helper for code-normalised supplier resolution already exists (used by the masters ingest).

- **Migration** (additive, existence-checked): `picking_headers.supplier_code String(50) NULL` + `supplier_id UUID NULL FK → suppliers(id) ON DELETE SET NULL`.
- **Model:** add both columns to `PickingHeader`.
- **Schema:** `GRNHeader` (`app/schemas/external/procurement.py`) gains `supplier_code: Optional[str] = None` + `source_ref: Optional[str] = None` (the latter for §1c). Keep them optional on the wire — a caller that omits both still works (back-compat).
- **Ingest resolves** `supplier_code` → `Supplier` by normalised code (reuse the masters' code lookup). **Miss ⇒ keep `supplier_code`, `supplier_id = NULL`. Do NOT 400** — supplier is captured-if-resolvable, products are the hard requirement.

### 1c. dry_run + per-record verdicts + idempotency on the GRN endpoint (AC-17-04/05/06)

This is the core. **Model it on `app/services/master_ingest_service.py` + `app/api/v1/external/ingest.py`.**

**Schema (`app/schemas/external/procurement.py`):**
- `GRNHeader`: add `supplier_code` + `source_ref` (done in 1b).
- `GRNLine.quantity`: `int` → `Decimal` (coerce from the string the wire sends; copy the `PurchaseRequestExternalLine.coerce_quantity` validator already in this file — it does exactly `Decimal(s.strip())`).
- **`uom` wire-gap (decide + document):** the wire sends `uom` (code) but the schema has `uom_id`. Add `uom: Optional[str] = None` and, in the endpoint, resolve `uom` code → `uom_id` (mirror the existing `location` → warehouse resolution via a units-of-measure code lookup). A `uom` miss should be tolerant (leave `uom_id` NULL, do not 400) unless your picking-line model requires it — in which case surface it as a `retryable` (a master not yet synced), NOT a hard failure.

**Endpoint (`app/api/v1/external/grn.py`) — add `dry_run: bool = Query(False)` and route through a service that returns the verdict envelope:**

Reuse the masters shape precisely (`ingest_masters` in `ingest.py` is the template):
1. Resolve everything a real ingest would — products (missing ⇒ this record is **retryable**, not a 400), warehouse-by-`location`, `uom` code, `supplier_code`, SPO linkage (existing logic), and the **adopt-or-create decision** (below).
2. Run the write inside a **savepoint** (`db.begin_nested()`) so a bad record can't poison the session — copy `MasterIngestService._ingest_one`'s savepoint pattern verbatim.
3. **dry_run:** do all of the above, build the prediction (with a before/after `diff` for an adopt-overwrite), then **`db.rollback()`** — assert in a test that ZERO `picking_headers` / `picking_lines` / `integration_references` rows leak. Two locks like masters: the service rolls back its savepoint AND the endpoint rolls back at the top level.
4. **commit:** `db.commit()` once.
5. Return the `{summary, records:[...]}` envelope (build an `IngestResult`-equivalent; the masters `IngestResult.as_dict()` at `master_ingest_service.py:126` is the exact shape — for GRN it always has one record).

**Idempotency = adopt by `source_ref` via the existing `integration_references` table (`app/models/integration_reference.py` + `IntegrationReferenceService`):**
- Add `"goods_received_note"` to `IntegrationReferenceService`'s `SUPPORTED_ENTITY_TYPES` allowlist (it maps `entity_type → table name` — point it at `picking_headers`).
- Lookup `refs.resolve(entity_type="goods_received_note", source_ref=payload.goods_receive_notes.source_ref, source_system="autocount")`:
  - **Hit** → `outcome="updated"`: UPDATE that `PickingHeader` (header fields) + **REPLACE its lines** (delete existing `picking_lines`, insert the new set). Refresh `last_synced_at` on the reference.
  - **Miss** → `outcome="created"`: CREATE the picking (existing `PickingHeaderService.create_grn` path) + `refs.link(entity_type="goods_received_note", entity_id=<new picking id>, source_ref=…, source_system="autocount", source_doc_no=picking_number)` **in the same transaction/savepoint**.
- **Never adopt by `picking_number`** — it is display + mutable. The `uq_integration_ref_source (source_system, entity_type, source_ref)` constraint is your idempotency guarantee; a unique `picking_number` collision must never 500 (a re-sync with a renamed doc no. is legal).
- If `source_ref` is **absent** (a legacy caller), keep the current create-only behaviour (the array-of-one path stays) — back-compat.

**Status codes:** the endpoint returns **200 with the verdict envelope** for any per-record outcome (created/updated/failed/retryable), exactly like `ingest_masters`. A non-2xx now means only a batch-level failure (auth, malformed body, batch-too-large). This is a behaviour change from the current `201`/`400` — intended, and matches the masters convention the ESB already speaks.

### 1d. Tests (`[BE-SOR][T]`)

- Decimal qty round-trips (`"2.5"` → `2.5` stored + read back through the response schema, not truncated) + the downstream sweep (any `int`-typed reader/exporter now Decimal-correct).
- Supplier resolve: hit → `supplier_id` set; miss → `supplier_code` kept, `supplier_id` NULL, GRN still created.
- `uom` code resolve: hit → `uom_id` set; miss → tolerant per your decision.
- Missing product → `retryable`, **zero rows written**; not a 400.
- `dry_run=true`: predicts the outcome, returns a `diff` on an adopt-overwrite, and **asserts no `picking_headers`/`picking_lines`/`integration_references` rows were written** (the masters dry-run test is the template).
- Idempotent create → update: same `source_ref` twice ⇒ ONE picking, second call `outcome="updated"`, lines replaced, no duplicate `integration_reference`, `picking_number` collision never 500s.
- Verdict envelope shape matches masters (`summary` counts + `records[]` with `source_ref/outcome/entity_id`).
- Full procurement/SCM suite green.

---

## 2. Migration + deploy sequencing (both repos)

1. **Sorento first.** Land 1a + 1b + 1c on `fix/ingest-status-codes-and-dry-run`, `alembic upgrade head` on the target env (two migrations: Decimal widen + supplier add). Verify the endpoint answers the §0 contract (a `curl` with `?dry_run=true` returning the one-record envelope is the smoke test).
2. **Then FoundryX.** Flip `AUTOCOUNT_GRN_DELIVERY_ENABLED=true` in the FoundryX backend env + **restart the process** (the flag is read at import). Only then does a real GRN cross the wire.
3. **Live-verify end-to-end:** sync a real AutoCount GRN in FoundryX → preview (real Sorento `?dry_run=true`) → approve → confirm a `goods_received` `picking_header` in Sorento with `supplier_code`, Decimal qty, and an `integration_references` row → re-sync the same GRN → confirm an idempotent **update** (no duplicate).

**Do NOT flip the FoundryX flag before Sorento is deployed** — with the old endpoint, a FoundryX `?dry_run=true` "preview" would hit a create-only endpoint that ignores the param and WRITE a real picking, and the 201/400 response would not parse as the verdict envelope.

---

## 3. Risks / notes

- **The Decimal sweep is the sleeper cost** (§1a). Widening four columns is trivial; finding every downstream `int` assumption (schemas, analytics, exports, any JS number handling on the Sorento frontend that renders picked/discrepancy qty) is the work. A missed `int` response field silently truncates.
- **`dry_run` must truly roll back** — no `picking_header` / `picking_line` / `integration_reference` leak. Two locks (service savepoint + endpoint top-level), asserted by a "zero rows written" test. This is the masters precedent, not a new invention.
- **`source_ref` is identity, `picking_number` is display** — never adopt by `picking_number`; the `uq_integration_ref_source` constraint is the identity guarantee.
- **Masters-before-GRN is a real operational prerequisite** — a GRN whose product/warehouse/uom isn't synced yet comes back `retryable` (nothing written), and the FoundryX review UI surfaces "sync the masters first". Do not turn a missing master into a hard `failed`/400.
- **`uom` code vs `uom_id`** is the one genuine wire divergence — resolve it (§1c) rather than silently dropping `uom` (the current schema's `uom_id` would just stay NULL).
- **Back-compat:** a caller that omits `source_ref` + `dry_run` still creates a picking exactly as today (the array-of-one path stays). Existing GRN consumers are unaffected until they start sending `source_ref`.

---

## 4. Reuse map (copy these, don't reinvent)

| Need | Sorento file to copy from |
|---|---|
| dry_run flag + rollback-or-commit + `200`-always verdict endpoint | `app/api/v1/external/ingest.py ingest_masters` |
| Per-record savepoint + `IngestResult`/`RecordResult`/`as_dict()` envelope | `app/services/master_ingest_service.py` (`_ingest_one`, `IngestResult`, lines ~84-147, ~427-450) |
| Adopt-by-`source_ref` (`resolve`/`link`) + entity_type allowlist | `app/services/integration_reference_service.py` + `app/models/integration_reference.py` (add `goods_received_note`) |
| Decimal coercion validator (string → `Decimal`) | `app/schemas/external/procurement.py PurchaseRequestExternalLine.coerce_quantity` |
| `location` → warehouse resolution (mirror for `uom` code → `uom_id`) | `app/api/v1/external/grn.py` (`get_warehouses_by_code_or_name`) + `utils.py` |
| Existing GRN create (the create branch of the adopt/create decision) | `app/services/procurement_service.py PickingHeaderService.create_grn` |
