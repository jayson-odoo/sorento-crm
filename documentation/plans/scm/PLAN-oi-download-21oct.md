# PLAN-oi-download-21oct: Order Inquiry download (Excel | PDF), like the Purchase Request

Status: in review (small fix track: no migration, no auth/RBAC change, no new ingest surface)

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

- `POST /api/v1/project-sales/order-inquiries/{id}/export/pdf` and `.../order-inquiries/export/pdf`
  (filtered rows), same shape as `POST /procurement/purchase-requests/{id}/export/pdf`: a
  `user_downloads` row + an RQ task on `imports`, the file arrives in My Downloads.
- PDF layout = the OI Excel sheet as a PDF (owner ruling below; the first cut printed the OI email layout). Rendered with WeasyPrint (`pdf_render.render_html`), the engine
  the PR / sponsorship form PDF uses (`purchase_request_pdf_service.py`).
- Permission: the same as the Excel export on the same screen. No email is sent.
- FE: "Print / Download PDF" next to "Export Excel" (detail gear menu, lines list toolbar), same
  label and icon the PR detail uses.

## Tests (red first)

- detail route queues an `order_inquiry_pdf` download; the task renders a PDF whose text has the
  header table + item lines; unknown id 404.
- list route queues `order_inquiry_worklist_pdf` with the filters; the rendered rows follow them.
- no email dispatch on either path.

## Add-on (owner, 21 Oct ~22:55 MYT): the OI Excel in the LOW STOCK REPORT's look

"our excel format needs to be nicer ... one of the success ones is the LOW STOCK REPORT ... we
should unify this". The look (dark bold white header, thin borders, wrapped top-aligned text,
frozen panes, explicit widths) was spelled out twice (`summary_order_service.write_sheet`,
`low_stock_report_service._write_workbook`); it now lives once in `app/services/excel_style.py`
and both use it (byte-identical output). The OI workbook (`OrderInquiryWorklistService.
_write_sheet`: the email attachment and both downloads) wears it with per-heading widths and
dd/mm/yyyy dates. Columns and values unchanged (EXPORT_HEADINGS not edited; #1822 adds its
columns there and they take the default width).

## Owner ruling (21 Oct, after the first hand test): the PDF is the Excel, as a PDF

"bruh the pdf needs to be like Excel la, just in pdf format, so I expect 1 table just like the
excel only". Both PDFs drop the email layout: the ORDER INQUIRY title, then ONE table whose header
is the workbook's header row and whose rows come from the same `_sheet_values` the workbook is
written from (no second column list), in the house style, A4 landscape, header repeated per page.
