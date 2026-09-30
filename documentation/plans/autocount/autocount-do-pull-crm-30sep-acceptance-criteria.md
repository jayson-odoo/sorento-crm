# UAC: Delivery Orders, Pull from AutoCount (lane DO-PULL-CRM)

Companion to `PLAN-autocount-do-pull-crm-30sep.md`. `[BE]` = pytest on Postgres
(`be/tests/test_autocount_pull_delivery_orders.py`, FoundryX replaced by the SR1 fake
transport). `[FE]` = vitest. `[HT]` = the owner's hand test on the crew test copy.

## Journey

Actor: the Sorento checker who today uploads the "Import delivery order lines" sheet.

1. With ONE company selected, the checker opens Dashboards > Delivery Orders and picks **Pull
   from AutoCount** from the Actions menu (beside Import tracking / Import delivery order
   lines). No file is chosen.
2. The pull page shows the snapshot building, then "Preparing" with N of M documents.
3. In review the counters read Received, New, Updated, Adopted by number, Unchanged, Lines to
   delete, Failed, Retry later; the Changes tab lists one row per document that Confirm would
   create, update or adopt, and every failed or retryable one with its reason; the Excel view
   lists every DO line in the import sheet's shape; Compare lines up the checker's own sheet.
4. Confirm applies the snapshot through the DO ingest. Nothing else in the CRM changes; a
   tracking-uploaded DO adopted by number keeps its tracking columns.

## Entity, permission, gate

- **AC-DP-01 [BE]** `ENTITY_PERMISSIONS`, `JOB_TYPES`, `APPLY_JOB_TYPES` map `delivery_orders`
  to `order_management.orders.autocount_pull`, `autocount_delivery_orders_pull`,
  `autocount_delivery_orders_apply`; the slug is in `PERMISSION_REGISTRY`.
- **AC-DP-02 [BE]** `POST /api/v1/autocount/pulls {"entity": "delivery_orders"}` without the slug
  is 403 and calls FoundryX nothing; with it, one `import_jobs` row of the DO job type is
  created and FoundryX `POST /snapshots` receives `entity: "delivery_orders"`.
- **AC-DP-02b [BE]** A start with `scope: {fromDay, toDay}` (or `docNo`) sends those keys FLAT
  in the FoundryX build body, stores them as `autocount_pull.scope`, and `serialize` returns
  `scope`; a FoundryX 409 `BUILD_IN_FLIGHT` on build answers 409 with that code and leaves no
  job row.
- **AC-DP-03 [BE]** A user holding only the products slug gets 403 on a DO pull they own;
  `GET /current?entity=delivery_orders` finds the caller's open DO pull.
- **AC-DP-04 [BE]** Migration `do_pull_0001_perm` inserts the slug and grants it to every
  non-integration role holding `order_management.orders.import`, plus `admin`.

## Preview

- **AC-DP-10 [BE]** With a snapshot of the live-shape DO sample (two documents, three lines,
  masters seeded, each row carrying `source_ref` `db1:DO:{DocKey}`) the preview ends in
  `review` with counts `received 2, created 2, updated 0, adopted 0, unchanged 0,
  lines_to_delete 0, failed 0, retryable 0, with_warnings 0`, two `success` rows, and NO
  `orders` row written.
- **AC-DP-10b [BE]** A record whose `RefDocNo` names no sales order previews as created with
  `with_warnings 1`; its row's message says "sales order not found" and its identity lists
  the warning; Confirm is not blocked.
- **AC-DP-11 [BE]** A DO already in the CRM without `doc_key` and with the same DocNo (a
  tracking upload's row carrying `transporter` and `driver_name`) previews as `adopted 1`,
  one `updated` row whose message names the adoption, and `lines_to_delete` counts its old
  unmatched lines; the row itself is unchanged after the preview.
- **AC-DP-12 [BE]** A DocNo held by a row with a DIFFERENT `doc_key` previews as `failed 1`
  with a `fail` row coded `DocNo`; an unknown ItemCode previews as `retryable 1` with a `fail`
  row coded `autocount_retryable` naming the product.
- **AC-DP-13 [BE]** Rows without a `source_ref` and a header without `book` fail the preview
  with "names no book" and write nothing; rows naming two books fail the same way.
- **AC-DP-14 [BE]** `preview_progress` reaches `(total, total)` for the pull job.

## Apply

- **AC-DP-20 [BE]** Confirm on a DO pull in review creates the apply job of the DO type; the
  apply task writes the sample's `orders` / `order_lines` rows through the DO ingest
  (`source_book`, `doc_key`, `source_record` set) and stores summary `{total 2, created 2,
  ...}`; the apply job is `finished`.
- **AC-DP-21 [BE]** Applying a snapshot that adopts a tracking-uploaded DO keeps its
  `transporter` / `driver_name` / `actual_delivery_date` and sets its `doc_key`.
- **AC-DP-22 [BE]** Applying the same snapshot a second time answers every record `unchanged`
  and writes nothing (`updated_at` unchanged).
- **AC-DP-23 [BE]** An expired snapshot (FoundryX 410) fails the apply with "pull again" and
  writes nothing.

## Rows, download, compare

- **AC-DP-30 [BE]** `GET /rows` on a DO pull answers one row per DO line with keys `doc_no,
  doc_date, debtor_code, debtor_name, item_code, description, location, qty, uom,
  unit_price, sub_total`; `query` matches Doc No or Item Code.
- **AC-DP-31 [BE]** `GET /download.xlsx` answers a workbook whose header row is `Doc No, Doc
  Date, Debtor Code, Debtor Name, Item Code, Description, Location, Qty, UOM, Unit Price, Sub
  Total`, one row per line.
- **AC-DP-32 [BE]** `POST /compare` with the checker's DO lines rows (`Doc No`, `Item Code`,
  `Location`, `Qty`) answers matched / different (a Qty that differs) / only-in lists keyed by
  (Doc No, Item Code, Location), and the summary is stored on the pull.

## Frontend

- **AC-DP-40 [FE]** `OrdersList` shows "Pull from AutoCount" in the Actions menu only with
  `order_management.orders.autocount_pull`; with an open DO pull the label is "Review pull".
- **AC-DP-41 [FE]** The job page treats `autocount_delivery_orders_pull` as a pull job
  (review card rendered, label "AutoCount Delivery Orders Pull", Back to Delivery Orders).
- **AC-DP-42 [FE]** `AutocountPullReview` renders the nine DO counters for a DO pull in
  review; the Excel view renders the DO columns (quantities at their own precision, dates
  as dd/MM/yyyy); the Compare tab shows a Doc No column and splits a three-part only-in label.

## Hand test

- **AC-DP-50 [HT]** From Delivery Orders, Pull from AutoCount reaches the review page, the
  counters and three tabs show, Confirm applies and the apply job shows the outcomes; the
  pulled DOs appear in the Delivery Orders list.
