# PLAN - Loading Plan goes demand-first: the container request before the CBM fit

**Status:** Direction approved by the captain, 20 Aug 2026 ("we should follow the stakeholder's
flow"). Four shaping decisions taken the same day, recorded in section 2. Implementation
starting on branch `fm/scm-demo-followups-20aug`.

**Contract it amends:** `PLAN-scm-purchasing-fulfilment.md` S7/S8 (the Loading Plan screen and
the supplier notice). Stage 2 below IS today's S7 engine, unchanged; this plan adds the stage
the stakeholder described in front of it.

## 1. Journey (Phase 0 - the stakeholder's flow, 19 Aug, as relayed by the captain)

Actor: Ms Tee (purchasing / fulfilment). Arrives from the sidebar: SCM -> Loading Plan.

1. **She picks the supplier and uploads their stock list** (existing upload, unchanged). CBM
   is NOT considered yet - the list's job at this moment is to identify WHICH products this
   supplier supplies and what they are holding (packed / unfinished).
2. **The system looks at the outstanding sales orders** for those products and suggests a
   quantity per product for the next container: the FULL outstanding SO need (captain's
   decision - it is a request to PACK, the supplier can produce; what they hold is shown
   beside it, never as a cap). Rows are ranked project first, then delivery date, then
   document date, then dealer - through the existing Fulfilment Priority policy, not a second
   sort (decision, section 2).
3. **She reviews, adjusts quantities where she disagrees, and sends the request to the
   supplier** - the same notice machinery S8 built: a generated document, an email when an
   address is on file, an outbox row either way.
4. **The supplier reverts with a packing list / proforma invoice** (existing channels:
   `scm/incoming` packing-list upload; proforma upload gets its FE in the sibling slice
   `PLAN-scm-proforma-invoice-frontend.md`).
5. **Only now does CBM matter:** today's loading-plan engine fits what the supplier actually
   packed into the chosen container count - S7 unchanged, greedy-by-rank over cubic metres,
   deferred lines explained.

What she holds at the end of step 3: a sent request the supplier can pack against, visible in
the notice panel with its document. What the system holds: the notice + lines snapshot, so
"what did we ask for" survives any later product rename or SO churn.

Nothing is asked that can be derived: the product set comes off the stock list, the
quantities off the SO book, the ranking off the active policy. Her decisions are three: the
supplier, any quantity she overrides, and Send.

## 2. Decisions taken (captain, 20 Aug)

| Question | Decision |
| --- | --- |
| How does demand-first fit with CBM fitting? | **Two stages, one screen.** Stage 1 = request (no CBM). Stage 2 = today's CBM fit, runs when the packing list / PI arrives. |
| Suggested qty capped by the stock list? | **No - full outstanding SO need.** Stock list identifies the products and shows what they hold; the request asks for what customers need. *(SUPERSEDED same day: the captain's netting ruling - see the section 4 amendment - makes the suggestion `max(need - on hand - SPO - PO, 0)`, gross need still shown.)* |
| Ranking mechanism? | **The existing priority policy** (`scm.priority_policy`, AC-H5: one policy). `factors_for_demand_rows` already maps need_by_date <- `required_date`, document_age <- `order_date`, demand_class <- the row's class. The ACTIVE policy on the live stack already weights demand_class 3.0 / need_by_date 3.0 / document_age 1.0 / customer_credit 1.0, so project-first-then-dates holds with NO weight change and NO migration. |
| Proforma FE? | Own page `/scm/proforma-invoices` - separate plan file (sibling slice). |

## 3. What already exists and is reused (nothing re-implemented)

- `factors_for_demand_rows` (`app/services/scm/priority.py`) - SO-shaped factor assembly,
  built for exactly this and currently uncalled by any container surface.
- `SupplierNotice` / `SupplierNoticeLine` (`app/models/supplier_notice.py`) - already carry
  `notice_type` (default `'loading'`) and a NULLABLE `loading_plan_id`. A request is a notice
  with `notice_type='container_request'` and no plan. **No new table, no migration.**
- The S8 document generator + email send + outbox flow (`supplier_notice_service`), the
  notice list endpoints, and the FE `SupplierNoticePanel`.
- The supplier stock list upload + `supplier_inventory` (packed / unfinished quantities).
- The outstanding SO book with per-line `demand_class` (project / retail / unclassified).

## 4. Backend contract

### POST `/api/v1/scm/container-requests/build`

Body: `{ "supplier_id": "<uuid>" }`. Permission: same view slug the loading plan screen reads
under. Pure read - persists nothing.

Response:

```json
{
  "supplier_id": "...",
  "stock_list_as_of": "2026-08-18T...",        // latest applied stock list timestamp
  "rows": [
    {
      "product_id": "...", "item_code": "...", "product_name": "...",
      "suggested_qty": 120,                     // full outstanding SO need, all classes
      "project_qty": 80, "retail_qty": 40, "unclassified_qty": 0,
      "earliest_required_date": "2026-09-01",  // soonest required_date behind the row
      "so_count": 3,                            // open SOs behind it
      "qty_packed": 60, "qty_unfinished": 100,  // what the stock list says they hold
      "rank": 1, "rank_score": 0.91,
      "rank_factors": [ {"key": "demand_class", "value": ..., "weight": ...}, ... ]
    }
  ],
}
```

(`stock_list_as_of` is the stock list's own DATE - `supplier_inventory.as_of` - not a
timestamp. A `not_on_stock_list` count was planned here and DROPPED in review: with no
supplier-catalogue master and no stock-list history, "products this supplier supplies but
absent from the list" is not computable honestly.)

**Amended 20 Aug (review + captain, same afternoon):** the row scope widens to stock-list
products with no open demand (`has_demand: false`, the one-table merge); `suggested_qty` is
NETTED (`max(open_so_need - on_hand - incoming_spo - outstanding_po, 0)`) with the gross
`open_so_need` and the three stock figures carried per row (captain's netting ruling); the
demand query applies `is_plan_demand_order()` / `is_plan_demand_line()` like every other
purchasing surface (no double-asking for OI-unnamed project SOs or decision-covered lines);
`include_lines=true` returns the flat SO lines; a top-level `sources` block carries the
latest ingest stamp per document family; supplier resolution goes through `supplier_scope`
(cross-company 404, never 500).

Row scope: products on the supplier's latest stock list ("each identified product" - the
stakeholder's words) that have nonzero outstanding SO need. Ranking: one
`factors_for_demand_rows` call over the product rows (a product row's `required_date` /
`order_date` = the earliest/oldest across its open SO lines; `demand_class` = project when any
project-class line is behind it, else retail, else unclassified), scored by the ACTIVE policy.

### POST `/api/v1/scm/container-requests`

Body: `{ "supplier_id": "...", "lines": [ { "product_id": "...", "qty": 120 } ] }` - the
reviewed lines, edited quantities included. Permission: the same slug S8's approve uses
(sending a document to a supplier is the same class of act).

Behavior: creates `SupplierNotice(notice_type='container_request', loading_plan_id=NULL)` +
lines (item_code / product_name copied at send time, `kind='pack'`), generates the request
document (the S8 generator with request wording: "please pack for the next container", no
container/CBM figures), sends by email when the supplier has an address (status `sent` /
`failed`), else `skipped` with the document still downloadable. Response: the notice row, same
shape the existing notice list returns.

Validation: unknown supplier 404; empty lines 422; a line qty <= 0 422.

### Unchanged

Every existing loading-plan / notice / packing-list endpoint. The notice LIST endpoints
already return `notice_type`, so requests appear in the panel without new routes.

## 5. Frontend

`/scm/loading-plan` becomes two labelled stages on the one screen (decision: two stages, one
screen). Stage order IS the journey order:

- **Stage 1 - "Request (what we need)"**: visible once a supplier is picked. Grid over the
  build response: Rank (with the existing `RankFactorsPopover`), Product, Suggested qty
  (EDITABLE, netted - the one field she owns) beside the gross Need, the stock context
  (On hand / SPO / PO), Project / Retail (/ Unclassified only when nonzero, same rule as
  the Buy view), Earliest need-by, Open SOs (a drill to the SO lines), They hold
  (packed / unfinished). *(The "N products not on their stock list" line was dropped with
  the field - see section 4.)* Toolbar: Refresh suggestion, **Send to supplier**
  (confirmation dialog stating supplier, line count, channel; never a browser confirm).
  After send: toast + the notice appears in the section's own "Requests sent" card (a
  dedicated card with the document download - NOT `SupplierNoticePanel`, whose header is
  coupled to plan approval; the duplication is declared in code), which renders in every
  state, empty state included.
- **Stage 2 - "Container plan (CBM fit)"**: today's screen, byte-for-byte behavior - supplier
  stock tiles, container count, build, fill %, deferred lines, approve -> S8 loading notice.

States per CRUD standard: loading skeletons, empty (no stock list yet -> CTA to upload; no
outstanding demand -> plain empty state), error via `extractApiError`, send-failure shows the
notice's `status_reason` (outbox semantics - a failed email still leaves a document).

Layer rule: UI -> `useFulfilment` hooks -> `fulfilmentService` -> `api-client`. New hooks:
`useContainerRequestBuild`, `useSendContainerRequest` (mutation invalidates the notices
query).

## 6. Tests (Phase 2, not deferred)

- pytest `tests/scm/test_container_request.py`: build happy path (scope = stock-list products
  with open need; netted qty per the section 4 amendment; project ranks ahead of retail at
  equal dates; sooner need-by ranks ahead within a class), build with no stock list ->
  empty-with-reason (DECIDED: the shipped choice, stated in the service docstring - not a
  409), send happy path (notice row + lines snapshot +
  document generated; email skipped without address), send validation (404 / 422 cases), auth
  denial. Every test seeds its own chain (CI database is empty).
- vitest: stage-1 grid component (loading / empty / error / data, editable qty, send dialog
  copy), hook tests for the two new hooks.
- Evidence run (agent-browser, no new Playwright spec per standing order): sidebar -> Loading
  Plan -> upload fixture stock list -> stage 1 rows ranked -> edit a qty -> send -> notice
  appears -> network shows POST /container-requests.

## 6b. Live-test follow-ups (captain, 20 Aug afternoon, same session)

Seen on the working Stage 1 and asked for on the spot:

1. **One table.** The Stage 1 suggestion grid and the supplier-inventory table below it merge:
   the build's row scope widens to stock-list products with NO open demand (suggested 0,
   `has_demand: false`, sorted after the ranked rows), and the standalone supplier-stock
   table leaves the screen. Nothing the stock list holds may vanish in the merge.
2. **Schedule matrix.** A delivery-schedule-style view of the same request: rows by product
   or by order, columns by day / week / month buckets of `required_date`, cells the open
   qty, drill to the SO lines - the `OrderInquiryScheduleMatrix` pattern reused. Backend:
   `include_lines=true` on the build returns the flat SO lines; the FE buckets.
3. **"What SO am I addressing":** the Open SOs figure drills to the lines (so_number,
   customer, class, dates, qty) - same lines feed the matrix.

## 7. Out of scope, named

- Capping or netting the request against what stage 2 later fits - the request is demand, the
  fit is supply; they meet at the packing list.
- Any change to S9 allocation or the packing-list channel.
- The proforma FE (sibling plan).
- Multi-supplier requests in one send - one supplier per request, same as one plan per
  supplier today.
