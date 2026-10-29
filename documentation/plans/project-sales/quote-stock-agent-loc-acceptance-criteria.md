# UAC: quotation line stock = the locations the user's contact may see (QUOTE-STOCK-AGENT-LOC)

Plan: `PLAN-quote-stock-agent-loc-28oct.md` (same folder). Owner rulings 28 Oct 19:00, 19:10, 19:25,
and the later one dropping the linked-agent gate: only the user's contact's Stock visibility decides.

## Journey

1. A salesperson opens a project, then a quotation, then the Lines tab.
2. Each line with a product shows "N avail" under Qty: Available stock summed over the locations
   the salesperson's contact may see (the contact's Stock visibility, the same setting the chatbot
   answers from). There is no "Stock at" picker.
3. Clicking the figure opens the stock table: only those locations, then the incoming SPOs at them.
4. A user with no linked contact, or whose contact may see no location, sees nothing there. Sales
   agents play no part: an admin or purchasing user whose contact has no Stock visibility set sees
   every location, like anyone else.

## Definitions

- **User's contact**: `users.respond_contact_id`.
- **Sales agents play no part**: neither a linked agent nor its `location_group` changes the set.
- **Allowed set**: `scope_warehouse_ids(db, resolve_policy(db, contact))`
  (`app/services/stock_visibility.py:394`, `:229`); None = every active warehouse. Then intersected
  with active warehouses where `fulfilment_planning` is true (the universe the old picker drew from).
- **Planning warehouse**: active `warehouses` row with `fulfilment_planning = true`.

## Phase 2: backend, `GET /api/v1/project-sales/quotation-line-stock?product_id=<uuid>`

Permission: any of `projects.projects.view` / `projects.projects.view_own` (the quotation READ pair).
Response: the existing `StockDetail` shape over the allowed set, or JSON `null` (no stock allowed).

- **AC-QSA-1 [BE]** Given a user with no `respond_contact_id`, when they ask, then 200 `null`.
- **AC-QSA-2 [BE]** Given a user whose contact is linked to NO sales agent and whose contact override
  includes planning warehouse W1, then `locations` lists W1 (no agent gate). Given the same user with
  no Stock visibility rows at all, then every planning warehouse counts.
- **AC-QSA-3 [BE]** Given a contact override that includes planning warehouses
  W1 and W2, and stock of the product at W1, W2 and W3 (another group), then `locations` lists W1 and
  W2 only, and `available_qty` = sum over W1 and W2 of (on hand - SO qty + SPO qty); W3 adds nothing.
- **AC-QSA-4 [BE]** Given a contact and NO Stock visibility rows at all (no override, no access
  type row, no default row), then every planning warehouse counts (two different groups and a site
  pool all contribute). Same answer when the only row is a global default with `warehouse_ids` NULL.
- **AC-QSA-5 [BE]** Given an override that excludes every active warehouse, then
  200 `null`. Same for an override whose include list is empty.
- **AC-QSA-6 [BE]** Given an override that excludes W3 only, then every planning warehouse except W3.
- **AC-QSA-7 [BE]** Given an allowed set containing a warehouse with `fulfilment_planning = false`
  that holds stock, then it is neither listed nor counted.
- **AC-QSA-8 [BE]** Given no override and an access type held by the contact whose row includes W1
  only, then only W1 (the inherited tier applies, `stock_visibility.py:203`).
- **AC-QSA-9 [BE]** Given a contact linked to two active agents with DIFFERENT `location_group`
  values, then the set is the contact's Stock visibility set, unchanged by either group.
- **AC-QSA-10 [BE]** Given an open SPO for the product at W1 (allowed) and one at W3 (not allowed),
  then `incoming` carries only the W1 SPO.
- **AC-QSA-11 [BE]** Given an admin user whose contact has no Stock visibility rows, then every
  planning warehouse counts; given an admin user with no contact, then 200 `null` (no role bypass
  either way, owner Q2). Given a user without either READ permission, then 403. Given a product_id
  that is not a uuid, then 422.

- **AC-QSA-12 [BE]** (review round) The response carries no data the quotation does not draw:
  `sales_orders` and `holds` are empty and every `incoming` row has `supplier_name` null, for every
  caller, including a user holding only `projects.projects.view_own` (who reaches the route through
  `_own_scope._REFERENCE_PATHS`). Inactive warehouses never count, even when nothing is set.

- **AC-QSA-13 [BE]** (owner ruling 28 Oct, security review) A contact whose EFFECTIVE Stock
  visibility Mode is "Availability only" (`availability`, from its own row or merged from its access
  types) gets 200 `null`: nothing shown, same as exclude-all. "Compact" and "Detailed" are unchanged
  (only the location set applies to them; hide-zero is not read).

## Phase 1/2: frontend, Lines tab

- **AC-QSA-20 [FE]** The Lines tab toolbar renders no "Stock at" picker, for any user; the
  `quotation-lines.stock-group` localStorage key is neither read nor written.
- **AC-QSA-21 [FE]** A line with a product reads `quotation-line-stock` for that product and shows
  "N avail", toned against the quoted qty exactly as today (green covers, amber some, red none).
- **AC-QSA-22 [FE]** When the read answers `null`, the Qty cell shows no chip and no text.
- **AC-QSA-23 [FE]** The popover table lists only the read's locations, leaving out rows whose on
  hand, SO qty and SPO qty are all zero. AutoCount's figures (`useStockStatus`) restate those rows
  only: no "Other group" rows are appended, and no separate `group=pools` read is made. Incoming lists
  the read's `incoming` only. (Review round) The AutoCount read is filtered to the read's warehouses
  before the table sees it, so no Group by choice (remembered in `cellStockTable.groupBy`, shared with
  the board) shows on hand or SOs at a location the read did not list. A location the read lists is drawn
  as a normal row when either the CRM figures or AutoCount's figures for it are non-zero, and is never
  drawn as an "Other group" row.
- **AC-QSA-24 [FE]** A set line's parts read the same endpoint per part (no group), with the same
  null = nothing rule: a part answering null leaves the set line's Qty cell with no pill, no skeleton
  and no text. Each part's popover section leaves out all-zero locations, like AC-QSA-23.

## Phase 3: browser (agent-browser, crew test copy)

- **AC-QSA-30 [E2E]** At 1280 and 375 px, via sidebar navigation: a quotation's Lines tab shows no
  picker, figures for the signed-in user's allowed locations only, the popover not clipped.

## Out of scope (owner Q3 (b))

The shared `fulfilment-planning/stock-detail` and `inventory/stock-status` endpoints, the fulfilment
board, and Inventory screens keep today's behaviour. Trigger to revisit: the owner asks for the same
rule outside the quotation screen.
