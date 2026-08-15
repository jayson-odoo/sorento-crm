# PLAN - Divergence reconciliation (slice P8a, module `projects`)

> **Table names in this document predate the schema move.** On 2026-08-15 the projects
> module's 47 tables moved into a dedicated `projects` Postgres schema and the 34 that
> carried a `project_` prefix dropped it: `project_leads` is now `projects.leads`,
> `project_quotation_lines` is `projects.quotation_lines`, and so on. The 13 unprefixed
> ones only changed schema. Nothing else in this document changes. See
> [ADR-0011](../adr/0011-project-sales-tables-live-in-the-projects-schema.md) and
> `documentation/plans/PLAN-projects-schema-move.md` for the full mapping.

**Status:** In build, 2026-08-03. Slice P8a of `PLAN-project-lead-to-so.md`.
**Acceptance criteria:** `UAC-project-lead-to-so.md` Group N (AC-N1..N7), plus AC-F11 and
AC-F11a, which turn out to be unbuilt: `project_sales_orders.autocount_doc_no` and `.so_id`
exist and nothing writes them.
**Slug:** project-so-divergence
**Builds on:** P8 (publish + import file), P11 (amendments), P9/P10 (allocation, order inquiry).

---

## 1. Why

Between P8 and P13 the sales order lives in two systems. CRM authors it, a CS imports the
file into AutoCount by hand, and from that moment either side can be edited. D25 settled the
rule: **neither side silently wins**. The difference is detected, held beside our values, and
reconciled by a person, line by line.

Nothing detects it today. There is no inbound path at all: `master_ingest_service` carries
master data only (products, customers, warehouses), and no route adopts a returned document
number. So P8a brings the inbound seam with it.

## 2. Shape

```
AutoCount SO export (CSV/XLSX)          ESB push (stage 2)
        │                                       │
        │ POST /sales-orders/ingest-file        │ POST /sales-orders/ingest
        └───────────────┬───────────────────────┘
                        ▼
              ProjectSOIngestService
                 match back (AC-F11a natural key)
                   ├─ no candidate  → outcome `unmatched`, nothing written
                   ├─ many candidates → outcome `ambiguous`, raised to CS, nothing written
                   └─ one candidate → adopt autocount_doc_no (+ so_id)
                                        ▼
                        ProjectSODivergenceEngine.compare()   (pure)
                                        ▼
                     agreeing → recorded, collapsed on screen
                     differing → project_so_divergences (+ lines), status `open`
                                        ▼
                     open divergence BLOCKS amendments on that SO (AC-N5)
                                        ▼
                     per line: ACCEPT THEIRS  → our record updates
                               KEEP OURS      → corrective publish queued
                                        ▼
                     all lines answered → resolved, audited (who/when/side/why)
```

## 3. Match back (AC-F11, AC-F11a)

Natural key, because stage 1 carries no spare reference field on the real document:
**customer + customer PO number + area group**, then the **line fingerprint** (sorted
`code|qty|date`, hashed) only to disambiguate.

The ordering matters and is easy to get backwards. A divergent document has a DIFFERENT
fingerprint by definition - that is the whole point of the slice - so the fingerprint cannot
be part of the primary match or every divergence would arrive as `unmatched`. It is the
tie-breaker for finding G4's collision: two sales orders on one PO within one area group.

- exactly one candidate → matched, whatever the fingerprint says.
- several candidates → the one whose fingerprint matches exactly wins; if none or more than
  one does, the outcome is `ambiguous` and a person is asked. Never a guess.
- no candidate → `unmatched`. Nothing is written, and the response says which key was tried.

Re-ingesting the same document is idempotent: the open divergence for that SO is recomputed
in place rather than stacked, so a CS uploading twice sees one reconciliation, not two.

## 4. What is compared (AC-N1)

**Per line:** product, quantity, unit price, delivery date.
**Header:** customer, customer PO number, terms, document total.

Lines are paired on `(product code, delivery date)` in order of appearance, then on product
code alone, and what is left over is `ours_only` or `theirs_only`. Pairing on line number
would be wrong: AutoCount renumbers.

Comparison is exact after quantizing to the stored scale - qty 4dp, unit price 5dp, money
2dp - so a rounding difference reads as a difference, which is what it is.

## 5. Resolution semantics (AC-N4)

| Row kind | ACCEPT THEIRS | KEEP OURS |
|---|---|---|
| `both`, fields differ | our line takes their qty / price / delivery date | corrective publish queued |
| `theirs_only` (a line only AutoCount has) | the line is inserted into our record | corrective publish queued |
| `ours_only` (a line AutoCount dropped) | our line's qty goes to **0**, never deleted | corrective publish queued |
| `header` | the decision is recorded, nothing is rewritten | corrective publish queued |

Two deliberate refusals to be clever:

**An `ours_only` line is cancelled, not deleted.** Allocations, claims and order inquiry rows
point at it. Zero quantity is already this system's word for a cancelled balance
(`CANCEL_BALANCE`), and it keeps the audit trail a delete would destroy.

**A header difference never rewrites the customer PO.** Terms and the PO number belong to the
customer's document. AutoCount's copy of them is not authority over it, so accepting theirs
records the decision and leaves the PO alone. This is the one place ACCEPT THEIRS does not
mutate, and it is called out on screen rather than left to be discovered.

Resolving every row closes the divergence. If any row was answered KEEP OURS, the divergence
carries `corrective_publish_required`, and the corrective import file is generated on request
exactly as the original is - a stored copy goes stale the moment anything republishes.

## 6. Data model

```
project_so_divergences(id, company_id, project_sales_order_id→project_sales_orders,
    autocount_doc_no, ingest_source(upload|esb), status(open|resolved),
    compared_count, agreeing_count, differing_count,
    corrective_publish_required, corrective_publish_sent_at,
    detected_at, resolved_at, resolved_by→users, created_at)

project_so_divergence_lines(id, company_id, divergence_id→project_so_divergences,
    scope(header|line), presence(both|ours_only|theirs_only),
    so_line_id→project_sales_order_lines (SET NULL), line_no, product_code,
    ours_json, theirs_json, differing_fields,
    resolution(accept_theirs|keep_ours), reason, resolved_by→users, resolved_at)
```

Agreeing lines ARE stored. AC-N3 asks for them collapsed, not absent, and "47 lines agree"
is only trustworthy if the 47 were written down.

Partial unique index: one OPEN divergence per sales order.

## 7. Endpoints (BASE `/api/v1/project-sales`)

| Route | Purpose |
|---|---|
| `POST /sales-orders/ingest` | canonical JSON document. The seam the ESB takes in stage 2 |
| `POST /sales-orders/ingest-file` | multipart CSV/XLSX. Stage 1 transport; parses by column heading, not position |
| `GET /divergences` | management list, `status`, `project_id`, with `age_days` (AC-N6) |
| `GET /divergences/{id}` | reconciliation payload: ours, theirs, difference, per row |
| `POST /divergences/{id}/lines/{line_id}/resolve` | `{resolution, reason}` (AC-N4, AC-N7) |
| `GET /divergences/{id}/corrective-import-file` | the corrective publish, stamped when taken |

Reads take `projects.projects.view`; resolving takes `projects.projects.edit` on that
project, checked in the service like every other project write. Ingest takes the same edit
grant, plus the API-key principal, because the ESB is the stage 2 caller.

## 8. Test plan (Phase 2, test first)

- **Engine, golden cases first**: field-by-field differences, pairing when AutoCount reorders,
  duplicate product on two dates, rounding at each stored scale, ours_only / theirs_only,
  header terms, an identical document producing zero differences.
- **Match back**: single candidate wins with a differing fingerprint; two candidates
  disambiguated by fingerprint; two candidates neither matching → `ambiguous`, nothing
  written; unknown PO → `unmatched`.
- **Idempotence**: same document twice → one open divergence, recomputed.
- **Block**: create/publish amendment against an SO with an open divergence → 409
  `so_divergence_unresolved`; passes once resolved.
- **Resolution**: accept theirs applies each field and recomputes the order total; ours_only
  goes to zero and keeps its allocations; theirs_only inserts; keep ours flags the corrective
  publish; last row resolved closes the divergence; audit fields stamped.
- **Routes**: happy path, auth denial, validation error, per the standing rule.
- Every test seeds its own chain (project → PO → SO → lines) with a marker prefix. Nothing is
  borrowed from an existing row: CI's database is empty.

## 9. Frontend

- **Reconciliation screen** at `project-sales/[projectId]/sales-orders/[psoId]/divergence`:
  ours / theirs / difference per row, agreeing rows collapsed behind a count, accept-theirs
  and keep-ours per row with a reason box, and a banner on the sales order itself while one
  is open (it is what blocks amending, so it belongs where the amend button is).
- **Management list** at `project-sales/divergences`: age in days, project, SO, differing
  count, so a stack is visible rather than discovered.
- Both reachable from the sidebar / project detail, never by deep link only.

## 10. Risks

- **The stage 1 upload format is an assumption.** AutoCount's export layout has not been seen.
  The parser reads by column heading with synonyms rather than by position, and the canonical
  JSON route is the seam that does not care. Flagged for the client to confirm with one real
  export; changing the parser then costs a mapping table, not a rebuild.
- **A divergence found on a sales order whose allocation is confirmed** leaves the allocation
  pointing at a quantity that has just changed. Out of scope tonight: recorded here, and the
  reconciliation screen shows the confirmed allocation beside the line so it is at least
  visible.
