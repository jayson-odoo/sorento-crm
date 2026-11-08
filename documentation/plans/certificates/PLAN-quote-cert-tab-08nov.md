# PLAN: Quotation Certification tab (QUOTE-CERT-TAB)

Status: Step 2 (mock + behaviour card) posted as crew-ask on PR #2245, waiting on owner answers + mock approval. No code yet. Track: full (L: migration + new tab + PDF annotation).

Lane: QUOTE-CERT-TAB. Owner request 8 Nov 2026 ~10:15 MYT. Mock: `mockups/quote-cert-tab-08nov.html`.
Behaviour card: `CARD-quote-cert-tab-08nov.md`.

## Owner ask (gist)

Quotation lines already carry photo, drawing and spec sheet. Add ONE more tab, "Certification": the
DISTINCT certificates of the quoted products, in the standard list view. For the customer, the row(s)
of the certificate table that hold the quoted product are boxed (a product "contains" the code, e.g.
the row reads `14A`). Users can remove a box or draw/move one. A certificate can be dropped from the
quote's list or added by hand. Question asked: "can we actually do that in PDF?" Answer: yes, see
Feasibility.

## Step 1: what exists today (read of main 53603f2b)

### Certificates module (built; its plan's Status line is stale at "Draft")

- Tables, `sorento_crm_backend/app/models/certificate.py`:
  - `certificates` (:70), identity = company + normalised `scheme || certificate_number` (:179-184),
    `status` active/archived only (:164), validity derived at read time (:13-16), `__company_shared__` (:71).
  - `certificate_revisions` (:200): `attachment_id` -> `attachments` (:224), `valid_from/valid_until`
    (:229-231), one `is_current` per certificate (:266-271).
  - `certificate_products` (:287): **the explicit product link already exists**: `certificate_id`,
    `product_id`, `source` ai|manual (:290-303), unique pair (:313-318). No model-code column.
  - Created by `alembic/versions/312_certificate_register.py`; `attachment_types.is_certificate`
    (`app/models/resources.py:75`).
- API `app/api/v1/master_data/certificates.py`: list/detail/CRUD, coverage add `POST
  /{id}/products` (:321) and remove (:357). Slugs `master_data.certificates.{view,add,edit,delete,export}`
  (:44-47, seeded `312_certificate_register.py:45-49`).
- List-query: `app/services/list_query_registry.py:169-175` (key `certificates`). MCP tool
  `crm_certificates_list` (`app/services/mcp_catalog_copy.py:207`).
- FE: `app/(protected)/master-data-management/certificates/` (list, `[id]` detail,
  `CertificateCoveredProducts.tsx`, `services/certificateService.ts:68`, `hooks/useCertificates.ts`),
  nav `config/menu.config.tsx:653` and `:2019`. Revision preview opens `AttachmentPreviewModal` ->
  `PdfViewer` (`components/common/AttachmentPreviewModal.tsx:480`).
- Coverage is written by n8n/Gemini through `/api/v1/external/product-attachments`
  (`app/api/v1/external/product_attachments.py:254`). The backend never reads cert PDF text today.

### How certificates link to products

Only through `certificate_products` (explicit rows, `ai` from extraction or `manual`). Nothing ties a
product to a ROW inside the PDF, and products have no model-code column (`app/models/product.py:274`
`product_code`, `:313` `family_code`, no `model_code`/`sku`).

### Quotation detail tabs and line media

- Entities: `quotation_documents` (`app/models/projects.py:1183`) > `quotations` (:1764) >
  `quotation_versions` (:1822) > `quotation_lines` (:1871, `product_id` :1884, `product_code_snapshot`
  :1896, `image_attachment_id` :1898, `drawing_attachment_id` :1903). Issues snapshot:
  `quotation_issues` (:1368).
- Tabs: `app/(protected)/project-sales/[projectId]/quotation-documents/[documentId]/components/QuotationDocumentTabs.tsx:32-44`
  (header, cover-letter, terms, signatures, feedback, spec-sheet); one `(view)/<segment>/page.tsx` each.
  New tab = one entry + `(view)/certification/page.tsx`.
- Photo/drawing: `app/services/project_quotation_image_service.py` (resolved from product attachments,
  frozen at issue :270), `product_image_service.py` (`DRAWING_TYPE` :86).
- Spec sheet v2: `app/services/project_spec_sheet_service.py`, reader
  `spec-sheet/[sheetId]/components/SpecSheetReader.tsx:124`. **It is not a PDF viewer**: it scrolls
  template-JSON pages (`ReaderPage.tsx`), so it cannot show a certificate PDF.
- The PDF viewer to reuse: `components/common/PdfViewer.tsx` -> `pdf-viewer/PdfViewerImpl.tsx`
  (pdfjs-dist 5.4.624). It already draws a pdf.js `TextLayer` per page (:914), reads every page's text
  (:382), paints search highlights (:437) and knows when a PDF has no searchable text
  (`hasSearchableText`). The box layer is one new optional overlay prop on it, not a second viewer.
- Image pipeline: `app/services/image_thumbnailer.py` (images only; thumbs/medium renditions). Not
  needed here: the certificate is shown as a PDF, not as images.
- Standard list view inside a detail tab: `components/common/PanelDataGrid.tsx` (used by
  `QuotationSpecSheetsList.tsx:258`).

### How the quotation reaches the customer

- PDF: WeasyPrint from HTML, `app/services/project_quotation_pdf_service.py` `render_issue_pdf` (:1105),
  queued via `POST .../issues/{issue_id}/export/pdf` (`app/api/v1/projects/quotation_documents.py:1030`)
  -> RQ `generate_quotation_issue_pdf` (`app/tasks/export_tasks.py:426`) -> My Downloads.
- No package: nothing merges/zips other PDFs into the quote (drawings are inline images, :685-690);
  spec sheet is its own Chromium-rendered PDF (`app/tasks/dealer_kit_export_tasks.py:272`).
- "Send to Customer" (`QuotationDocumentClient.tsx:597-624`): Email only issues (no SMTP send);
  WhatsApp opens a `wa.me` link by hand (`QuotationWhatsAppDialog.tsx:278`). Public counter-sign link
  `app/api/v1/public/quotation_sign.py`. So the customer gets files the salesperson downloads/shares.
- The only PDF merge in the codebase: `app/services/promotions_pdf_service.py:69,110` (`fitz` `insert_pdf`).
  PyMuPDF is already a dependency (`requirements.txt:52`); `project_schedule_service.py:252` already reads word boxes.

## Feasibility ("can we do that in PDF?")

Yes, without a new library.

- **Text PDFs** (has a text layer): PyMuPDF `page.search_for(code)` returns exact rectangles per hit;
  the row box = the hit's band between the table's horizontal rules (`page.get_drawings()`), widened
  to the table's left/right rules; fallback when the table has no rules = the hit's text line padded.
  Boxes are stored as data (page index + rect in PDF points), shown on screen as an overlay on the
  existing `PdfViewer`, and burned into the exported copy with `page.draw_rect` on a copy of the file.
  The original certificate file is never modified.
- **Scanned PDFs** (no text layer): no auto box; the tab shows "No text found, draw the box" and the
  user draws it. OCR is out of v1: tesseract adds a system dependency on every backend image and is
  weak on small table text; a Gemini read is ~1 call per page per revision. Trigger to add it: the
  count of scanned certs on quotes (crew-data-request on #2245) is material.
- Sandbox proof: see `## Proof` below.

## Design (proposed, pending card answers)

Data (one migration):

1. `certificate_products.model_code` VARCHAR(60) NULL: the text exactly as printed on the certificate
   for this product (e.g. `14A`). Empty = the product's own `product_code` is searched. No fuzzy match.
2. `certificate_products.boxes` JSONB NULL: per product-certificate default boxes for ONE revision,
   `{revision_id, boxes:[{page,x0,y0,x1,y1}]}`. NULL or a different revision = auto from the code.
3. `quotation_document_certificates` (document_id, certificate_id, `included` bool, `source`
   auto|manual, `boxes` JSONB NULL override, created_by/at): exists only when a user changed something
   (removed, added by hand, re-boxed). The tab list = derived distinct certs of the quoted products,
   plus manual rows, minus `included=false` rows.
4. Issue snapshot: issuing freezes the included certificates, their revision and final boxes on the
   issue (`quotation_issues`), the same way line images freeze (`project_quotation_image_service.py:270`).

Customer output: one "Certificates" PDF per issue (merged, boxes burned in), queued like the quote
PDF, plus optionally appended to the quote PDF (card Q3).

## Proof

(filled in from the sandbox run)
