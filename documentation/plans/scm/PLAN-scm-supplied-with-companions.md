# PLAN: "supplied with" companions on the Order Inquiry (CKSW015 rides with CKS1050)

Status: Phase 1 done (a1d8fcfab, aa3a62c88). Phase 2 in progress: red tests written, coder making them green.
UAC: `scm-supplied-with-companions-acceptance-criteria.md` alongside.

## 0. The case, as the owner showed it

SO419595 / OI-000019 on the Order Inquiries worklist:

| item | qty | worklist today | what the supplier actually does |
| --- | --- | --- | --- |
| CKS1050 | 1 | 1 of 1 (linked) | ships the seat cover CKSW015 inside its own line |
| CKSW015 | 1 | Not found (new order) | never appears as its own PO line |
| SRTWCX8605-S-RL-PJ (X, pedestal) | 2 | 2 of 2 | |
| SRTWCY8605-PJ (Y, cistern) | 2 | 2 of 2 | |
| SRTWC8605-SC-RL (seat cover) | 2 | 2 of 2, but only because production linked it to an SPO by hand | ships with the X + Y pair, never its own PO line |

The companion item never has a PO line of its own, so the cascade finds nothing
and tells purchasing to buy it. Purchasing already knows it arrives with the
host. But the same item IS sold alone (a replacement seat cover), and then it
must be bought alone. So the rule is on the sales order, not on the product:
**bundled when it rides with its host on the same order, ala carte otherwise.**

Owner rulings, 9 Sep:

* SC-RL's host is the X + Y PAIR (both present), not either one.
* AutoCount books stock IN for CKSW015 when CKS1050 is received, so the
  companion's on-hand is real and the ala carte path drains real stock.
* Supplier-scoped, "just in case". Nullable, NULL = any supplier.
* About 50 pairs today. Product-page configuration, no import sheet yet.
* Ratio may be fractional (NUMERIC, never Integer).
* Pair cap is `min` over hosts: 3 X + 2 Y bundles 2 seat covers.
* An unlinked host's supplier is its primary supplier.
* No backfill script. Testing phase; the owner relinks the open rows in
  production by hand, and every relink re-derives (3.2 call site 2).

## 1. Why not a product set

`ProductSet` names a flyer code (`SRTWC8608-RL`) whose parts the catalogue
stocks separately. It is a sales-side identity for the chatbot's resolver; it
has no host, no ratio, no supplier, and `contributes_to_price` is a pricing
tick. CKS1050 + CKSW015 is not a set anyone sells under one code. Using sets
would couple flyer naming to procurement behaviour and every future set author
would have to know it changes what purchasing buys. Rejected.

## 2. What is measured in the code

* OI rows are raised ONLY by `ProjectOrderInquiryService.refresh_for_decision`
  (`app/services/project_order_inquiry_service.py:392`) from the fulfilment
  board's confirmed Buy residual. A line covered from stock or timely SPO raises
  no row. So a host with no row means its supply is already in hand, and its
  companion on the same order, if it has a row, is genuinely short: ala carte.
* Coverage is the sum of `projects.order_inquiry_links` per row;
  `_refresh_link_state` (`:2543`) is the one writer of `state` from
  `linked` vs `qty`. `raised` = nothing linked, `partly_linked`, `placed`.
* Demand for the planner is `GREATEST(oir.qty - linked, 0)` in
  `app/services/scm/demand.py:314`, over `raised` and `partly_linked` rows.
* The automatic cascade is `auto_place_for_products` (`:3807`), gated by
  `cascadable` (`:3183`); `_unlinked_need` (`:3303`) is `qty - linked`.
* The worklist tiles are `OrderInquiryWorklistService._kinds`
  (`app/services/order_inquiry_worklist_service.py:1236`): SPO, PO, Buy by
  linked quantity; Buy is the unlinked remainder.
* The cell is the `po_number` column in
  `app/(protected)/project-sales/order-inquiries/components/orderInquiryWorklistColumns.tsx:280`,
  headline plus lightbox since slice A of the 8 Sep batch.
* `ProductSupplier` (`app/models/procurement.py:73`) carries
  `is_primary_supplier`. Product detail tabs: overview, stock, purchases,
  attachments, suppliers, promotions (`ProductDetail.tsx:263`).

## 3. Design

### 3.1 The rule, on the product

Two tables under `master_data`, company-scoped like every product row:

```
product_companion_rules
  id, company_id, companion_product_id (FK products, RESTRICT),
  supplier_id (FK suppliers, nullable: NULL = any supplier),
  ratio NUMERIC(15,4) NOT NULL DEFAULT 1   -- companion units per ONE host unit
  is_active, created_at, updated_at, created_by
  UNIQUE (company_id, companion_product_id, supplier_id)

product_companion_rule_hosts
  rule_id (FK rules, CASCADE), host_product_id (FK products, RESTRICT)
  UNIQUE (rule_id, host_product_id)
```

A rule with two hosts means BOTH must be present (the X + Y pair). A rule
with one host is the common case (CKS1050). Two tables rather than one because
the pair case exists today, not hypothetically; a JSON host list would be
un-indexable and un-joinable from the demand SQL.

Read on the product page: a "Supplied with" section on the companion's
Suppliers tab (the rule is about how the supplier ships it, and the tab already
holds per-supplier facts). Lists rules, Add opens a modal: hosts
(`SearchableMultiSelect` of products, the shared product search), supplier
(`SearchableSelect`, clearable), ratio. Delete = hard delete via the
deferred-action grace window (D7: `ConfirmDeleteDialog` is retired
codebase-wide, PRINCIPLES.md hard-fail rule - a 10s countdown with Cancel
takes its place, `useDeferredRowAction`/`product_companion_rule.delete` once
Phase 2 registers the action). The host's page shows a read-only "Ships
with" list pointing back, so the fact is findable from either side.

### 3.2 Where the rule bites: the OI row

New columns on `projects.order_inquiry_rows`:

```
bundled_qty       NUMERIC(15,4) NOT NULL DEFAULT 0
bundled_with_row_id UUID NULL FK order_inquiry_rows (SET NULL)
```

Derived, never typed. Recomputed by one function,
`ProjectOrderInquiryService.derive_bundles(inquiry_id)`, called from:

1. `refresh_for_decision` after the rows of a revision are written;
2. `_refresh_link_state` (a host row gaining links changes nothing for the
   companion; a host row being cancelled or its qty dropping does);
3. `unplace_all` and `place_on_po` paths, which already end in
   `_refresh_link_state`, so nothing extra: the owner's manual relink of the
   open production rows is what derives them after deploy.

The derivation, per companion row R in inquiry I:

```
rules  = active rules for R.product where supplier is NULL or matches (3.3)
for each rule, host rows H_k = rows of I with product = host_k,
               verb in (ORDER, ORDER_BACK), state not cancelled, ack not rejected
if any host has no row: rule does not apply
host_cap = min over k of ( sum(H_k.qty) * ratio )
bundled  = min( R.qty - linked(R), host_cap )      -- never below 0
R.bundled_qty = bundled
R.bundled_with_row_id = the first host row (display anchor)
```

`R.qty - linked` and not `R.qty`: a link a person already made stays a link.
Production's hand-made SC-RL to SPO links are not unwound by this rule; the
bundle covers whatever they did not.

### 3.3 Supplier scope

A rule with `supplier_id` set applies when the host row's supply is from that
supplier:

* host row has links: the supplier of the linked PO or SPO;
* host row unlinked (a new buy): the host product's `is_primary_supplier`.

No match, no bundle: the companion stays ala carte for that order. NULL
supplier skips the check. This is the whole of the "just in case".

### 3.4 What follows from `bundled_qty`

* **Demand** (`demand.py:314` and the FORM leg beside it):
  `GREATEST(oir.qty - linked - bundled_qty, 0)`. The planner never buys a
  bundled unit.
* **Cascade** (`_unlinked_need`): `qty - linked - bundled_qty`. A row whose
  need is 0 is skipped as it is today.
* **State** (`_refresh_link_state`): `linked + bundled_qty >= qty` reads
  `placed`; between, `partly_linked`. The stored word does not change, so
  filters, `scm.committed_v` and saved column layouts are untouched.
* **Tiles** (`_kinds`): a bundled quantity counts in NONE of the three cards
  (owner, 9 Sep, plan review). The cards total quantity that has its own
  PO / SPO / buy; a unit that rides inside another line's supply is not
  owed anywhere, so it joins `_NOT_OWED_STATES` in effect: subtract
  `bundled_qty` from every card. The `kind` filter follows the same rule.
* **Cell** (`po_number` column): headline `Included with CKS1050`, then the
  host's own coverage headline in the muted style, e.g.
  `Included with CKS1050 · 1 of 1`. A rule with two or more hosts reads
  `Included with 2 items` and the lightbox names them (owner, 9 Sep: never
  the word "host" in the UI, and no list of codes in the cell). The info
  icon opens the HOST row's lightbox. A row that is part bundled, part ala
  carte reads `1 with CKS1050 · 2 of 2` and the lightbox lists both the
  anchor and the row's own documents. No explanatory sentence in the UI.
* **Serializer** (`serialize_rows`, `_serialize` in the worklist service):
  `bundled_qty`, `bundled_with` (host item code and row id). Both asserted in
  a test, because `response_model` drops what it is not told about.

### 3.5 Not in scope

* GRN / stock side. AutoCount already stocks the companion in on the host's
  receipt (owner, 9 Sep).
* The fulfilment board's own Reserve / Borrow arithmetic. A companion with
  stock reserves from it exactly as today; only the Buy residual is bundled.
* An import sheet for rules. Fifty rows go in by hand on the product page;
  the trigger for a sheet is the owner asking for one.
* Unwinding production's manual SC-RL links.
* A backfill. Owner relinks in production (testing phase).

## 4. Slices (one lane, one PR, slices = commits)

Phase 1, frontend against mocks:

* S1. Suppliers tab "Supplied with" section + Add / Delete modal on the
  companion product; read-only "Ships with" list on a host.
* S2. Worklist cell and lightbox for a bundled row; tile counts.

Phase 2, backend test-first:

* S3. Migration: the two rule tables, the two row columns. Chain onto the
  current main head (`alembic heads` right before PR).
* S4. Rule CRUD routes under `master_data/product_companions.py`, gated on
  the products permission; `product_companion_service.py`.
* S5. `derive_bundles` + its three call sites + demand SQL + `_unlinked_need`
  + `_refresh_link_state` + `_kinds` + serializers.

Phase 3: `/code-review`, browser evidence on SO419595 after the two rules
(CKSW015 with CKS1050; SC-RL with X + Y) are keyed on the dev copy.

Tests to add or extend:

* `tests/test_product_companion_rules.py` (new): CRUD, company scope, pair
  host uniqueness, RESTRICT on product delete.
* `tests/test_order_inquiry_bundles.py` (new): the table in UAC group B
  (single host, pair host, ratio, partial, ala carte, supplier match and
  mismatch, host cancelled, existing link kept).
* `tests/test_project_order_inquiry_import_creates_demand.py`: bundled units
  leave demand.
* `tests/test_order_inquiry_worklist.py`: serializer fields, tile attribution.
* Vitest on `orderInquiryWorklistColumns.test.tsx` for the bundled headline.

## 5. Rulings (9 Sep, owner)

1. Ratio = companion units per ONE host unit, fractional allowed.
2. Pair host cap = `min` over hosts. Matches the supplier's behaviour.
3. Unlinked host supplier = the host product's primary supplier.
4. Configuration lives on the companion product's Suppliers tab.
5. The UI never says "host". One: `Included with CKS1050`. Several:
   `Included with 2 items`, codes in the lightbox.
6. A bundled quantity never reaches reorder planning, whatever the item it
   rides with is covered by. Only the ala carte remainder does.
7. The three cards above the worklist (Use SPO / Use PO / Buy) count only
   quantity with its own supply. A bundled quantity is in none of them.
