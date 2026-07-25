# PLAN — Packing list duplicate detection after GRN

**Status:** Implemented + verified (uncommitted). Backend + tests + FE string entry done;
live end-to-end run against the local stack green.
**Date:** 2026-07-25
**Branch:** TBD (`fix/packing-list-duplicate-detection`)
**Scope:** Backend (`sorento_crm_backend`) + 1 FE string map entry. No n8n changes.

---

## 1. Problem

Packing lists enter the system as an attachment upload → n8n extraction → `POST /api/v1/external/packing-lists`.

`InboundShipmentService.create_shipment` (`app/services/procurement_service.py:654`) resolves an existing
shipment in three steps:

1. `shipment_number` exact — **any status**
2. `shipping_container_number` exact — **only where status ∉ (`fully_received`, `completed`)**
3. `attachment_id`

Step 2 deliberately excludes received shipments because a container is reusable: once its shipment is
fully received, the same container can carry a new one later.

**The loophole:** after GRN the shipment is `fully_received`, so step 2 skips it. A user who mistakenly
re-uploads the *same* packing list PDF falls through all three steps and a **duplicate inbound shipment
is created**.

Step 1 does not save us: packing list PDFs carry no shipment number, so `shipment_number` is
NULL on essentially every row (confirmed with user). The container triple is therefore the **primary**
dedup key, not a backstop.

---

## 2. Decisions (grill log)

| # | Question | Decision |
|---|---|---|
| D1 | Why doesn't the `shipment_number` guard catch it? | `shipment_number` is NULL in the attachment/PDF. Triple becomes the primary key. |
| D2 | What counts as "same"? | Field-wise `IS NOT DISTINCT FROM` on `shipping_container_number`, `estimated_arrival_date`, `shipment_date`. NULL==NULL equal; NULL vs value **not** equal. |
| D3 | Make `shipment_date` nullable? | **No.** Stays `nullable=False`; the "sail date NULL" branch is unreachable by design and is not built. |
| D4 | Dedup when container is NULL? | **No.** Dedup gated on incoming `shipping_container_number IS NOT NULL`. Without it the key degenerates to `shipment_date` alone and would falsely block two different suppliers shipping the same day. |
| D5 | Which statuses does rejection apply to? | Only `fully_received` / `completed`. Not-received matches keep today's update-in-place behaviour. |
| D6 | Where does the user see the error? | Backend stamps `integration_log.error_code` + `.error_message` itself, before raising. No n8n workflow change. |
| D7 | Fix the generic `response_payload.error` gap too? | **Yes** — `_build_file` falls back to `response_payload.error` when `error_message` is NULL, fixing every other n8n failure type at the same time. |
| D8 | Orphaned attachment after rejection? | **Leave it.** No auto-delete. Deletes stay explicit user actions; the verdict can be a false positive and the file is evidence. |
| D9 | Container string matching | **Normalize**: uppercase + strip separators, both sides. Portable SQL (`UPPER`/`REPLACE`) so the sqlite test suite works. |
| D10 | Clean up pre-existing duplicates? | **Not needed** — user confirms no affected packing lists exist yet. |
| D11 | Naming the colliding shipment | Container + dates + the existing shipment's received date. `shipment_number` included only when non-null. **No UUID in user-facing text.** |
| D12 | Test coverage | 14 pytest cases + 1 vitest. Marker container numbers, scoped cleanup. |

---

## 3. Matching rule (final)

Replace step 2 with a **single** container lookup that includes received shipments, then branch on status.

```
if payload.shipping_container_number is NULL:
    -> no dedup; fall through to existing attachment_id step / create   (D4)

candidates = shipments where normalize(container) == normalize(payload.container)
             ordered by created_at desc                                  (company-scoped automatically)

for c in candidates:
    if c.status not in (fully_received, completed):
        -> UPDATE IN PLACE                     # unchanged from today    (D5)

    if triple_equal(c, payload):               # IS NOT DISTINCT FROM    (D2)
        -> REJECT as duplicate                 # new behaviour

-> no candidate matched -> CREATE NEW           # container legitimately reused
```

`triple_equal` compares `shipping_container_number` (normalized), `estimated_arrival_date`,
`shipment_date` with NULL-safe equality.

`normalize(x)` = `re.sub(r"[^A-Za-z0-9]", "", x).upper()` in Python; in SQL
`UPPER(REPLACE(REPLACE(REPLACE(col,' ',''),'-',''),'/',''))` — portable across Postgres and the
sqlite test engine (`tests/conftest.py:3`). Mirrors the existing `_spo_match_key`
(`procurement_service.py:117`).

### Truth table

| Existing status | Container | ETA | Sail date | Result |
|---|---|---|---|---|
| `in_transit` / `partial_received` | equal | any | any | update in place |
| `fully_received` / `completed` | equal | equal | equal | **409 duplicate** |
| `fully_received` / `completed` | equal | differs | equal | create new |
| `fully_received` / `completed` | equal | equal | differs | create new |
| `fully_received` / `completed` | equal | NULL both | equal | **409 duplicate** |
| `fully_received` / `completed` | equal | NULL vs value | equal | create new |
| any | payload NULL | — | — | no dedup, create |

Company scoping is free: `InboundShipment` carries `CompanyScopedMixin` (`models/base.py:92`,
auto-filtered by `do_orm_execute`) and the route already calls `scope_to_attachment_company`
(`packing_lists.py:58`).

---

## 4. Error contract

**Machine code:** `DUPLICATE_PACKING_LIST`

**Headline** — `ERROR_CODE_FRIENDLY` in `sorento_crm_frontend/components/upload-activity/translation.ts`:

> Duplicate packing list — this container was already received

**Detail** — 409 `detail` and `integration_log.error_message`:

> Container TEMU1234567 (shipment date 2026-06-01, ETA 2026-06-20) was already recorded and fully
> received on 2026-06-18. This looks like the same packing list uploaded twice. If this container is
> carrying a new shipment, its shipment date or ETA must be different from the previous one.

With a non-null shipment number, the first clause becomes `...already recorded as SH-00123 and fully
received on 2026-06-18.`

### Why the backend stamps the log itself

The n8n error node posts only:

```json
{ "status": "failed", "response_payload": { "error": "<n8n-serialized message>" } }
```

It never sets the `error_code` / `error_message` **columns**, yet every user-facing surface reads
exactly those columns:

- `app/api/v1/resources/upload_activity.py:184-185` (`_build_file`)
- `components/upload-activity/useAttachmentIntegrationLog.ts:132-133`
- `components/upload-activity/IntegrationPanel.tsx:184`

Result today: drawer shows **"Integration failed"**, real reason buried in `response_payload` behind
"View raw log". `IntegrationLogService` uses `model_dump(exclude_unset=True)`
(`app/services/integration_service.py:721`), so n8n's later POST **cannot clobber** columns we write
first.

---

## 5. Implementation

### 5.1 Backend

1. **`app/services/procurement_service.py`**
   - `_container_match_key(value) -> str` (alnum-only, upper), mirroring `_spo_match_key`.
   - `DuplicatePackingListError(Exception)` carrying `error_code`, `message`, `existing` shipment.
   - Rework the step-2 container lookup in `create_shipment` per §3: widen to include received
     statuses, order `created_at desc`, branch on status, raise `DuplicatePackingListError` on a
     triple match against a received shipment.
   - Leave steps 1 and 3, and the existing "already completed, cannot update" 409, untouched.

2. **`app/api/v1/external/packing_lists.py`**
   - Wrap `service.create_shipment(...)` in `try/except DuplicatePackingListError`.
   - On catch: best-effort stamp the latest `integration_log` where
     `business_table='attachments' AND business_id=<attachment_id>` with
     `error_code='DUPLICATE_PACKING_LIST'` + `error_message=<detail>`; **commit**, then raise 409.
   - Stamping is `try/except` + `logger.warning` — a stamping failure must never mask the real error,
     and must never turn a rejection into a 500. No log row (direct API call, no n8n) → skip silently.
   - Commit before raising so the global `AppException` handler cannot roll the stamp back.

3. **`app/api/v1/resources/upload_activity.py`** (D7)
   - In `_build_file`, when `log.error_message` is NULL, fall back to `response_payload.error`.
   - Fixes every n8n failure type, not just this one.

### 5.2 Frontend

4. **`components/upload-activity/translation.ts`**
   - Add `DUPLICATE_PACKING_LIST: 'Duplicate packing list — this container was already received'` to
     `ERROR_CODE_FRIENDLY`.
   - `IntegrationPanel.tsx:184-190` already renders headline + detail; no component change.

### 5.2b Found during implementation (not in the original plan)

5. **`app/api/v1/procurement/packing_lists.py`** — the **manual UI create route** also calls
   `create_shipment`, wrapped in a bare `except Exception -> handle_internal_error`. An uncaught
   `DuplicatePackingListError` there would surface as a **500** instead of the explanatory 409.
   Now caught explicitly and returned as 409 with the same message. Pinned by
   `test_both_create_routes_translate_the_error_to_409`, which asserts both create routes handle the
   error — so a future third caller can't silently regress to a 500.

6. **Ordering tie in log selection.** `_integration_log` rows created in the same clock tick share a
   `created_at`, so "stamp the latest" is only well-defined when timestamps differ. The stamping
   query mirrors the drawer's ordering exactly (`created_at desc`, first row —
   `upload_activity.py:284`) so both always agree on which row is "the latest"; the test sets
   `created_at` explicitly rather than relying on the server clock.

### 5.3 Not in scope

- No n8n workflow changes.
- No migration, no new column.
- No attachment auto-delete.
- No pre-existing-duplicate cleanup script (D10).

---

## 6. Tests (test-first)

**Safety:** all fixtures use marker container numbers (`DEDUPTEST%`); cleanup is scoped to those rows
only, symmetric before and after. Never an unscoped `DELETE FROM inbound_shipments` — the local DB is a
prod-data copy.

### pytest — `tests/test_packing_list_duplicate_detection.py`

| # | Scenario | Expect |
|---|---|---|
| 1 | triple equal, existing `fully_received` | 409 `DUPLICATE_PACKING_LIST`, no new row |
| 2 | triple equal, existing `completed` | same |
| 3 | container equal, ETA differs, received | creates new |
| 4 | container equal, sail date differs, received | creates new |
| 5 | ETA NULL both sides, container+date equal, received | 409 |
| 6 | ETA NULL on payload, set on existing | creates new |
| 7 | container NULL on payload | no dedup, creates (regression guard) |
| 8 | existing `in_transit`, triple equal | update in place (regression guard) |
| 9 | existing `partial_received`, triple equal | update in place |
| 10 | `temu 1234567` vs `TEMU1234567` | 409 (normalization) |
| 11 | 2 received rows same container, one matches triple | 409, names newest |
| 12 | `integration_log` exists | stamped; later n8n POST doesn't clobber |
| 13 | no `integration_log` row | no crash, still 409 |
| 14 | `shipment_number` present and matches | existing 409 path unchanged |

Cases 3, 4 and 6 are the load-bearing ones — they prove legitimate container reuse still works.
Cases 8 and 9 prove the pre-GRN correction flow is intact.

### vitest

- `translation.ts` renders the friendly headline for `DUPLICATE_PACKING_LIST` with the detail line
  beneath it.

---

## 7. Three-phase note

Per `CLAUDE.md`, Phase 1 (FE prototype against mocks) is **not applicable** — this is a backend
correctness fix with a single FE string-map entry and no new UI. Phase 2 (backend + tests) and
Phase 3 (`/code-review`) apply as normal.

---

## 8. Verification — results

**pytest:** 33 passed across `test_packing_list_duplicate_detection.py` (20),
`test_packing_list_container_match.py` (3) and `test_upload_activity_endpoint.py` (10, incl. 2 new
fallback tests).

`test_fully_received_container_does_not_match_creates_new` in the pre-existing container-match file
was **updated, not deleted**: its two payloads shared a container, a sail date and a NULL ETA — i.e.
exactly the identity triple — so it was asserting the loophole. It now gives the second shipment a
later sail date, which is what genuine container reuse looks like.

**vitest:** 29 passed across `components/upload-activity/` (translation entry + friendly-headline
test).

**Live end-to-end** against the running local stack (backend :8000, real Postgres), marker container
`CLAUDEDUP0000001`, all rows removed afterwards:

| Step | Result |
|---|---|
| First upload | 201 created |
| Driven to `fully_received` | ok |
| Same packing list re-uploaded | **409** with the full explanatory message |
| `integration_log` | `error_code=DUPLICATE_PACKING_LIST` + message stamped; `status` left as n8n's `sent` |
| Same container, different ETA | **201** — genuine reuse unaffected |
| Rows for that container | 2 (original + reuse), no duplicate |

Note: the external route is `POST /api/v1/external/packing-lists/` — **the trailing slash matters**
(without it FastAPI 307-redirects). And the bound attachment must carry a `company_id`, or the
company-scope guard rejects the create with `company_scope_required` before dedup is ever reached.

## 9. Original verification plan

- pytest matrix above, green.
- vitest for the translation entry.
- Manual end-to-end against the local stack: upload a packing list PDF, let n8n create the shipment,
  run SPO + GRN to `fully_received`, re-upload the same PDF → confirm no second shipment row, and
  confirm the upload-activity drawer row reads the duplicate headline (not "Integration failed").
