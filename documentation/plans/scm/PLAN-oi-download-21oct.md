# PLAN-oi-download-21oct: Order Inquiry download (Excel | PDF), like the Purchase Request

Status: in progress (small fix track: no migration, no auth/RBAC change, no new ingest surface)

Owner, 21 Oct ~22:10 MYT: "our order inquiry need to support download either excel / pdf, just
like purchase request and sponsorship form".

## What already exists (measured, not rebuilt)

- Excel, detail: `POST /api/v1/order-inquiries/{id}/export` queues `generate_order_inquiry_xlsx`
  into My Downloads; it renders `OrderInquiryWorklistService.export_xlsx(inquiry_id=...)`, the SAME
  function the OI email attaches (`store_handover_excel`). Gear menu item "Export Excel" on the
  detail page.
- Excel, lines list: `POST /api/v1/order-inquiries/export` (filtered rows, same function). Toolbar
  "Export Excel" on the lines list.
- PDF: none.

## Build

- `POST /api/v1/order-inquiries/{id}/export/pdf` and `POST /api/v1/order-inquiries/export/pdf`
  (filtered rows), same shape as `POST /procurement/purchase-requests/{id}/export/pdf`: a
  `user_downloads` row + an RQ task on `imports`, the file arrives in My Downloads.
- PDF layout = the OI email: one table per S/O (S/O NO, SO DATE, CUSTOMER, PROJECT), then the item
  lines LOCATION / ITEM CODE / QTY / DELIVERY / REMARK. Rendered with xhtml2pdf, the engine the PR /
  sponsorship form PDF uses (`purchase_request_pdf_service.py`).
- Permission: the same as the Excel export on the same screen. No email is sent.
- FE: "Print / Download PDF" next to "Export Excel" (detail gear menu, lines list toolbar), same
  label and icon the PR detail uses.

## Tests (red first)

- detail route queues an `order_inquiry_pdf` download; the task renders a PDF whose text has the
  header table + item lines; unknown id 404.
- list route queues `order_inquiry_worklist_pdf` with the filters; the rendered rows follow them.
- no email dispatch on either path.
