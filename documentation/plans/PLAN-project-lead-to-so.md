# PLAN - Lead to Sales Order (module `projects`, phase 2)

**Status:** DRAFT, pre-code. Grilled with the client 2026-08-01 (24 decisions, D1-D24), then
the PLAN itself grilled against the source documents (9 findings, G1-G9, all resolved).
**Acceptance criteria:** `UAC-project-lead-to-so.md` (binding). The Journey there governs.
**Slug:** project-lead-to-so
**Classification:** extends the existing MODULE `projects`; `public` schema, normal FKs,
company scoped.
**Builds on:** phase 1 (S0-S6b, all built), `sales_orders` / `sales_order_lines` and
`item_packages` (AutoCount mirrors), SCM reorder engine, form SLA + handling lock.

---

## 1. Why

Phase 1 made the pursuit visible: lead, registration, quotation, samples, forecast, staleness.
It stops at the moment the money actually arrives. Everything after the customer PO is still a
scan walked from desk to desk, 99 lines retyped into AutoCount, and an Excel emailed to
purchasing that is corrected by a second email 42 minutes later.

Three costs, all visible in the client's own files:

1. **Retyping.** `SO397450` is 99 lines across 21 pages, read by hand off a scanned PO and a
   matrix schedule, twice (Yana, then CS).
2. **No structured commitment.** The quotation exists only as a PDF, so "does this PO agree
   with what we quoted" is a human reading two documents side by side. `QT-004188` item 7 was
   cancelled by hand months later because the price had changed. Nothing caught it.
3. **Instructions that go stale between systems.** The order inquiry says ORDER for stock a
   pre-order already covers, and the correction arrives as a third email.

## 2. Shape

```
LEAD ─accept─> PROJECT ─spec in─> QUOTATION(v) ──publish──> AutoCount QT
                 │                    │
                 │                    │ ordered balance
        CUSTOMER PO (scan) ───────────┤
           + DELIVERY SCHEDULE (matrix, phases)
                 │  extract, explode, split, cross check
                 ▼
            SO DRAFT ──gate──> SO(v) ──publish──> AutoCount SO  (stage 1 file / stage 2 ESB)
                 │                 │
                 │                 ├─ allocation (Eling confirms ranked source)
                 │                 └─ ORDER INQUIRY rows ──task──> SCM / purchasing
                 │                        (netted against pre-orders + inbound SPO)
       revised PO / revised schedule
                 │  version + delta
                 ▼
            AMENDMENT ──OCN──> amend in place, or re-point + cancel balance
```

Two invariants worth stating once:

- **Demand is `sales_order_lines`.** The order inquiry says what to DO; it is never a second
  source of how much is committed. SCM's reorder engine is untouched.
- **The project is the anchor, not the customer.** A parking route (Hong Bee) changes the
  customer on a document while the requirement stays with the project. Every join that
  matters goes through the project.

## 3. Data model (indicative)

New tables:

```
project_delivery_phases      project_id, area_group, label, sequence, delivery_date,
                             source_schedule_version_id            (D12)

customer_pos                 project_id, customer_id, po_number, po_date, term_days,
                             customer_order_ref, admin_ref (PS…), remark,
                             status(draft|approved|superseded), superseded_by_po_id,
                             approved_by, approved_at
customer_po_versions         customer_po_id, version_no, document_attachment_id,
                             extracted_json, extracted_by, confirmed_at        (D14)
customer_po_lines            customer_po_version_id, line_no, stock_code_raw, description_raw,
                             qty, uom_raw, unit_price, amount, is_cancelled,
                             resolved_product_id
customer_po_annotations      customer_po_version_id, dedup_key(date,item,text_hash),
                             crop_attachment_id, raw_text, interpretation_json,
                             state(proposed|accepted|edited|rejected), actioned_by  (D11)

delivery_schedules           project_id, customer_po_id, po_version_id, issuer_party_id,
                             label, revision_no, issued_at
                             -- po_version_id is what the checksum reconciles against  [G1]
delivery_schedule_versions   delivery_schedule_id, version_no, document_attachment_id,
                             extracted_json, checksum_state(ok|mismatch), confirmed_at
delivery_schedule_cells      version_id, phase_id, product_id, qty                  (D13)

customer_item_code_map       customer_id, customer_code, product_id, confirmed_by   (AC-E4)
set_explosion_map            customer_id, po_code_or_text, product_id, component_json (D10)

project_sales_orders         project_id, customer_po_id, area_group, so_id(->sales_orders),
                             provisional_ref, autocount_doc_no, is_pre_order,
                             is_sponsorship, sponsorship_form_id, grouping_origin,
                             status(draft|blocked|ready|published|amended)
                             -- every project-side fact lives HERE, never on sales_orders [G5]
so_grouping_preferences      customer_id, grouping_json, learned_from_so_id          [G2]
so_draft_findings            project_sales_order_id, line_id, severity(hard|warn|info),
                             code, detail_json, acknowledged_by, acknowledged_reason (D9)

so_amendments                project_sales_order_id, source_version_ref, ocn_id,
                             verb, delta_json, status, approved_by, published_at   (D14,D15)
order_change_notices         project_id, customer_po_id, project_sales_order_id,
                             reason, approver_id, approved_at, source_document_id  (D15)

order_inquiries              project_sales_order_id, amendment_id, raised_at, state
order_inquiry_rows           order_inquiry_id, so_line_id, item_code, qty, delivery_date,
                             stock_location, verb, spo_ref, state                  (D16)

so_line_allocations          so_line_id, source_type(brw|own|other_project|order),
                             warehouse_id, qty, claim_id, confirmed_by             (D17)
allocation_claims            from_project_id, to_project_id, product_id, qty,
                             state(requested|accepted|refused), decided_by, reason
```

Changed:

```
project_leads.customer_id            -> nullable, means BUYER                       (D6)
project_leads  + informant_source, informant_ref, informant_party_id,
                 informant_contact_id, assigned_at, accepted_at,
                 declined_reason, acceptance_state                                  (D6,D7)
projects       + admin_ref (PS filing reference)                                    (D24)
customers      + ar_outstanding, ar_ageing_json, ar_as_of                           (D23)
(sales_orders is CORE and is left alone: no project_id, no is_pre_order)          [G5]
```

Reused as is: `project_parties` (+ its existing `customer_id` bridge), `item_packages`,
`sales_orders` / `sales_order_lines`, `purchase_requests` (sponsorship forms), the form SLA
and handling lock, the activities adapter, the status engine.

## 4. Slices

Each slice follows the three phase loop (FE prototype on mocks, then BE + tests, then review).
Tests land in phase 2 of each slice, never deferred.

| # | Slice | Delivers | Depends on |
|---|---|---|---|
| **P1** | Lead informant + acceptance handshake | AC-A1..A8. Nullable buyer, informant fields, assign/accept/decline, SLA escalation on silence, marketing's acceptance list | - |
| **P2** | Company profile on `customers` | AC-B1..B6. A client IS a customers row, reused not duplicated; parties cover non-buying roles; one page renders the union across the existing bridge | P1 |
| **P3** | Quotation publish + ordered balance | AC-C1..C5. Publish adapter (stage 1 file), returned doc number stored, per line ordered balance, draft watermark printing | - |
| **P4** | Customer PO intake | AC-D1..D9. Upload, vision extraction, field confirm beside the page, approval + countersign, admin_ref | P3 |
| **P5** | Handwriting review cards | AC-D4..D7. Annotation extraction, crops, accept/edit/reject, dedup across re-scans, successor PO link | P4 |
| **P6** | Schedule intake + phases | AC-E1..E7. Matrix extraction, confirm grid, checksum against PO, customer code map, phases as first class rows | P4 |
| **P7** | SO draft: explosion, split, gate | AC-F1..F9, F12. Set explosion with cached mappings, area split, cross check, hard stops and warnings, SLA + handling lock on drafts | P3, P5, P6 |
| **P8** | Publish + AutoCount round trip (stage 1) | AC-F10, F11. Import file with our ref, adopt returned doc number, ingest match back rather than duplicate | P7 |
| **P8a** | Divergence reconciliation | AC-N1..N7. Line by line compare on ingest, reconciliation screen, accept theirs / keep ours with a corrective publish, amendment block while unresolved, management list | P8 |
| **P9** | Allocation | AC-H1..H5. Ranked sources with live figures, per line confirm, cross project claims | P7 |
| **P10** | Order inquiry + SCM handoff | AC-I1..I7. Derived rows, verb vocabulary, pre-order and inbound netting, SCM task, Excel export, row state | P8, P9 |
| **P11** | Amendments, OCN, delta engine | AC-G1..G7. Version diffing, verb proposals, phase matching, auto drafted OCN, amend in place vs re-point with cancelled balance | P8, P10 |
| **P12** | Pre-order and sponsorship paths | AC-J1..J5, AC-K1..K5 | P11 |
| **P13** | ESB outbound swap + AR ingest | D3 stage 2, AC-F9 real credit figures | ESB team, ESB inbound |

Sequencing note: P1 to P3 carry no AI and no external dependency, so they can land while the
extraction work is still being tuned. P13 is deliberately last and is the only slice that
cannot be finished by us alone.

## 5. What the AI does, precisely

Four jobs, each with a deterministic check behind it. This matters: everywhere the AI produces
a number, something arithmetic verifies it.

| Job | Input | Deterministic check behind it |
|---|---|---|
| PO extraction | Scanned PDF or photo | Line amounts must equal qty x unit price; total must equal the sum of lines |
| Handwriting reading | Region crops | Never applied without a human accept; item numbers must exist on the PO |
| Schedule extraction | Customer formatted matrix | Column totals must equal the quantities on the PO VERSION the schedule names, and the customer's own TOTAL QTY row where present [G1] |
| Set explosion | PO line + catalogue | `item_packages` is authoritative; the quotation fallback must reproduce the quoted quantities exactly |

The AI never decides a price, a quantity or a date on its own. It proposes, and something
countable agrees or the draft is blocked.

## 5a. The golden set (client instruction)

Their uploaded documents ARE the acceptance test. Committed to `e2e/fixtures/project-cs/`.

```
INPUT   Buimaco Bulk PO R1 (scan, 21 lines, 2 handwritten amendments)
      + Delivery Schedule R1 (matrix, 15 phases)
EXPECT  SO397450  99 TOWER lines   ] line for line: product, qty,
        SO397460  COMMON AREA      ] delivery date, unit price
      + order inquiry rows matching (04).03.2026 MARYAM TUJU RESIDENCE.xlsx
      + NO order row for quantity the SO383057 pre-order covers
INPUT   Delivery Schedule R2
EXPECT  12 tower DELAY rows + 3 common area rows, quantities unchanged
```

This is the difference between "the AI extracts POs" and "the AI extracts THIS PO correctly".
It runs in CI; an extraction change that regresses it does not merge. It also gives P4, P5, P6
and P7 an objective done condition instead of a demo.

## 6. Open risks

- **Vision quality on Malaysian site handwriting.** Mitigated by reject-by-default cards, but
  a missed annotation is a silent wrong commitment. Worth a measured sample before P5 sizing.
- **Schedule layout drift.** Every customer differs and the same customer may restructure
  between revisions. The checksum catches quantity errors; it does not catch a phase label
  that changed meaning. AC-G3 raises unmatched labels rather than guessing.
- **ESB outbound may not land.** Stage 1 covers it, at the cost of one manual import click.
- **AR ingest may not land.** The credit warning degrades and says so on screen.
- **Two systems of record during the transition.** RESOLVED as D25: the ingest match back
  (AC-F11) detects it, the difference is flagged and reconciled per line (Group N), neither
  side auto-wins, and an unresolved divergence blocks further amendments on that SO. Ships as
  slice P8a, immediately after the first publish path exists.
- **Scope pressure toward delivery.** 5B (DO, transport, invoice) is out. It will be asked for
  the moment the SO works.
- **Natural-key match-back can collide [G4].** Two SOs on one PO within one area group would
  key identically but for the line fingerprint. The fingerprint is therefore part of the key,
  and an ambiguous match must be raised to CS rather than resolved by guessing.
- **The Yana step stays (D21), and CS reviews rather than retypes** (client confirmed at plan
  review). The day in the process remains; the keying does not. If they later want the day
  back, it is a workflow change, not a rebuild.

## 7. What this does not touch

Delivery and invoicing, purchase request returns and RMA, flower stand claims, new product
code application, physical stock transfer execution, and the historical Excel import. All
listed in the UAC with reasons.
