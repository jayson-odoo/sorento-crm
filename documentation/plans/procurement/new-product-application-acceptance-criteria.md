# UAC - New Product Application (NEW-PRODUCT-APP)

Card: `CARD-new-product-application-17oct.md`. Plan: `PLAN-new-product-application-17oct.md`.
Mock: `mockups/new-product-application-v4.html` (paper layout, owner OK 18 Oct). Staff and portal (Q1 = portal too).
v4 (AC-NPA-70..79) supersedes AC-NPA-04's line pickers, AC-NPA-10's required fields and AC-NPA-60's line table.
Every criterion is checked by a named test (pytest `tests/test_new_product_application*.py`, vitest beside the
component) or by the browser pass (B).

## Create and edit (Draft)

- **AC-NPA-01** A holder of `procurement.new_product_applications.create` creates a Draft; the number is
  `NPA-000001`, per company (highest issued + 1 under an advisory lock, never the row count), applicant = the caller.
- **AC-NPA-02** A Draft saves with any subset of fields (every line field may be empty in a draft);
  an empty number field is stored as NULL (never 0).
- **AC-NPA-03** Only the applicant edits or deletes their Draft (403 otherwise). Delete draft is the countdown
  pending action `new_product_application.delete` (10 s, hard delete, lines go with it); no confirm dialog.
- **AC-NPA-04** Item group, base UOM, brand, item type, supplier and customer ids must exist in the caller's
  company; a stock inquiry id must exist (stock inquiries carry no company today; a portal contact may only use its
  own); anything else is 422 naming the field in words (never a silent drop).
- **AC-NPA-05** Created from a stock inquiry (`?stock_inquiry_id=`): the form pre-fills inquiry link, project name,
  customer TEXT (no debtor id), needed-by, and line 1 = proposed code + description + expected qty from the inquiry.
  No customer, product or name matching happens anywhere (B + vitest).

## Submit, approve, reject

- **AC-NPA-10** Submit refuses (422, one message per missing field naming the line) unless: at least one line;
  every line has description, item group and base UOM. The Draft keeps everything typed.
- **AC-NPA-11** Submit moves Draft -> Submitted, stamps `submitted_at`, notifies the approvers (AC-NPA-40).
- **AC-NPA-12** Submit from Rejected is one press: Rejected -> Draft -> Submitted, approvers notified again.
- **AC-NPA-13** Approve / Reject only by holders of `approve` (403 otherwise), only from Submitted (409 otherwise).
  Reject needs a reason (422 empty); the reason shows in the red banner.
- **AC-NPA-14** While Submitted or Approved every header and line write answers 422
  `new_product_application_locked`. Approve, reject, revise, cancel and line linking are not blocked by it.

## Revise and cancel

- **AC-NPA-20** Revise (applicant or approver) from Submitted or Approved needs a reason (422 empty), returns to
  Draft, clears the approval stamp, and writes one audit row carrying the reason.
- **AC-NPA-21** Revise from Submitted notifies the approvers that it was withdrawn; from Approved it notifies nobody.
- **AC-NPA-22** Revise and Cancel are refused (409) once any line is opened or closed.
- **AC-NPA-23** Cancel (applicant) from Draft / Submitted / Approved; reason optional; Cancelled is terminal.

## Purchasing opens the code

- **AC-NPA-30** On an Approved application a holder of `open_code` links a line to an existing ACTIVE product of the
  same company (`opened_product_id`, who, when). Any other status: 409. Other company / inactive / unknown: 422.
- **AC-NPA-31** Product search for linking ignores dashes, spaces and case, only lists matches (limit 20), and
  returns nothing for an empty query. Nothing is preselected or auto-linked (vitest: no auto-pick).
- **AC-NPA-32** "Not opening" closes a line with a required reason (422 empty).
- **AC-NPA-33** Undo (holder of `open_code`) clears a line's link or close on an Approved or Completed application;
  a Completed one returns to Approved.
- **AC-NPA-34** When every line is opened or closed the application becomes Completed in the same request and the
  applicant is notified.
- **AC-NPA-35** Linking a line that is already opened or closed answers 409 (two purchasers at once).

## Notifications (only when someone must act)

- **AC-NPA-40** Submitted -> active, non-integration holders of `approve` with a grant for the company, applicant
  excluded. Approved -> the same set for `open_code`. Rejected / Completed -> applicant. Withdrawn (AC-NPA-21) ->
  approvers. Nothing else notifies. Sent after the commit; a notification failure never undoes the move.

## Reads

- **AC-NPA-50** List: holders of `view` see every application of their companies; `create` holders without `view`
  see their own. DataGrid search (number, proposed code, description), Status and Applicant filters, sort, paging
  through `buildDataGridParams`; listing key `procurement.new_product_applications.view`.
- **AC-NPA-51** Detail renders header, lines with the "Opened as" column and the audit trail, each with an explicit
  empty state; prev/next navigation. No UUID is shown anywhere.
- **AC-NPA-52** The stock inquiry detail shows a "New product applications" row: "None yet", or each application's
  number (link), status and opened codes. The gear item "Create new product application" shows only on a
  `responded` inquiry for holders of `create`.
- **AC-NPA-53** Another company's applications are invisible (404) and never listed.

## Layout

- **AC-NPA-60** Create, edit and view are one document card; the line table scrolls inside its card; usable and
  not clipped at 375 and 1280 (B). Every optional select is clearable; every dropdown is SearchableSelect.
- **AC-NPA-61** Menu: Procurement Management > New Product Applications, gated by `view` or `create`.

## v4: the paper layout (owner 18 Oct: D1-D4 yes, PQ1 yes)

- **AC-NPA-70** (D3) The write body, staff and portal alike, takes only: `stock_inquiry_id, customer_id,
  customer_name, project_name, needed_by, remark` and per product `id, proposed_code, description (PRODUCT TYPE),
  dimension, material, thickness, packing, brand_id, expected_qty`. Any other key (`category_id, base_uom_id,
  item_type_id, supplier_id, supplier_item_code, cost_price, selling_price, further_description`, line `remark`) is
  422 naming the field. The applicant never writes cost.
- **AC-NPA-71** (D1) Several products per application. A product sent with its `id` is updated in place (its
  images stay); one without `id` is added; a saved product left out is deleted with its image links. An `id` of
  another application's product is 422. Product numbers follow the body order.
- **AC-NPA-72** Submit needs at least one product and a PRODUCT TYPE on each; otherwise 422 with one message per
  product, "Product N: enter the product type." Item group and base UOM are no longer asked for.
- **AC-NPA-73** Images per product: the applicant (owner of a Draft or Rejected application; 422
  `new_product_application_locked` while Submitted / Approved, 403 for anyone else) uploads a JPEG, PNG or WebP
  (anything else 422), copies a file already attached to the application's stock inquiry (links the same file, no
  second upload; a file not attached to that inquiry is 422), or removes one (unlink only, the file row stays). The
  portal contact does the same on its own application. The detail lists each product's images (name, url, link id).
- **AC-NPA-74** (D2) PURCHASING FEEDBACK: a holder of `open_code` saves LEADTIME (free text, one per application)
  and COST (number >= 0, one per product; empty clears) on an Approved or Completed application (403 without
  `open_code`, 409 in any other status). Saving stamps who and when, writes an audit row, does not change the status
  or the approval, and notifies nobody.
- **AC-NPA-75** Revise clears LEADTIME, every product's COST and the feedback stamp.
- **AC-NPA-76** (D3) Once a product is linked (Link product), the staff detail shows read-only the linked
  product's item group, base UOM, selling price (`list_price`) and supplier (primary supplier first, else the oldest
  supplier row). Nothing is copied into the application.
- **AC-NPA-77** (D4) Download Excel, staff (anyone who can view the record) and portal (own application only,
  404 otherwise): one sheet per product named "Product N"; column A labels bold right-aligned, column B values
  wrapped, thin borders; rows in this order: title NEW PRODUCT APPLICATION, REFF:, DATE: (dd/mm/yyyy, MYT),
  SALES PERSON:, PRODUCT CODE:, PRODUCT TYPE:, DIMENSION:, MATERIAL:, THICKNESS:, PACKING, BRAND:, IMAGE:,
  CUSTOMER:, PROJECT:, QTY:, TARGET DELIVERY:, REMARK:, PURCHASING FEEDBACK, COST:, LEADTIME:. A4 portrait, fit to
  one page. File name `NPA_<YYYYMMDD>_<applicant initials, or the application number when raised on the
  portal>_<customer> (<code> <product type>) (<code> <product type>).xlsx`, characters a file name cannot hold
  removed, length capped; the REFF cell holds the same name without `.xlsx`. COST is filled on both sides (PQ1).
  A value starting with `=`, `+`, `-` or `@` is written as text. The first image of the product sits in the IMAGE
  row; an image over 40 megapixels or one that cannot be read shows its file name instead.
- **AC-NPA-78** (PQ1) The portal shows each product's COST, the application's LEADTIME and the linked product's
  supplier, read-only ("Purchasing fills this after approval." until filled). It never shows item group, base UOM
  or selling price, and has no feedback route.
- **AC-NPA-79** (B + vitest) Staff create, edit and view and the portal form and view are the paper sheet: title
  NEW PRODUCT APPLICATION, bordered label:value rows with the paper's labels, REFF = the NPA number, "Product N of M"
  blocks with Remove and "+ Add product", PRODUCT TYPE marked required, PURCHASING FEEDBACK at the bottom
  (read-only to the applicant, editable in place with "Save feedback" for `open_code` on Approved / Completed),
  OPENED AS per product on staff, "Download Excel" in the gear menu. Labels sit above values under 640 px; nothing
  scrolls sideways at 375; usable at 1280.

## v5: table form like Stock Inquiry (owner hand test 20 Oct; supersedes AC-NPA-73 and AC-NPA-79)

- **AC-NPA-80** (B + vitest) Staff create, edit and view and the portal form and view: the header is Stock Inquiry's
  bordered table rows under the title NEW PRODUCT APPLICATION (REFF, DATE, SALES PERSON, STOCK INQUIRY, CUSTOMER,
  PROJECT, TARGET DELIVERY, REMARK); the products are ONE line table, one row per product (No., Product code,
  Product type *, Dimension, Material, Thickness, Packing, Brand, Qty) with "Add row" and a remove control per row; no
  per-product cards. PURCHASING FEEDBACK shows LEADTIME as a row and COST as a per-row column: read-only for the
  applicant ("Purchasing fills this after approval." while empty), editable in place with "Save feedback" for
  `open_code` on Approved / Completed. Staff detail rows show Opened as and the read-only From AutoCount values.
  Under 640 px the header rows put the label above the value and the line table scrolls sideways inside its card;
  the page never scrolls sideways at 375.
- **AC-NPA-81** Attachments belong to the application (`entity_type new_product_application`), any type the shared
  attachment flow accepts. Staff: the applicant links an attachment of the caller's company from the attachment
  library on a saved Draft / Rejected application and unlinks it (unlink drops the link only), same behaviour as the
  Stock Inquiry attachments section; locked (422) while Submitted / Approved; another user 403. Portal: the contact
  adds files with the shared dropzone (also while creating: uploaded right after the first save) and removes them,
  on its own application only (another contact's 404). The detail lists the attachments (name, url, link id).
- **AC-NPA-82** The per-product image routes, the inquiry-attachments routes and the copy-from-inquiry picker are gone
  (404); lines carry no `images`.
- **AC-NPA-83** Excel: the IMAGE row of every product sheet embeds the application's first image attachment (stored
  thumbnail first; originals over 10 MB without a thumbnail, images over 40 MP and non JPEG/PNG/WebP show the file
  name); no image attachment leaves the cell empty.
