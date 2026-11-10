# Behaviour card: QUOTE-DESC-RICHTEXT (rich text line Description on proposals and quotations)

Source: owner 10 Nov ~14:30 MYT, on the proposal / quotation lines table (line SRTWC8518, description "SORENTO ONE
PIECE TWISTER FLUSH WC (S-TRAP 250MM) SRTWC8518-SH C/W PP SEAT COVER" in a plain textarea): "the description should
use rich text editor also to allow styling". Earlier ruling reused here, 5 Nov: "full shared rich text editor w/ colour".
Base: origin/main a4af6565. Paths under `sorento_crm_backend/app/` unless they start with `sorento_crm_frontend/`.

## What already exists (reused, nothing new)

- Editor: `sorento_crm_frontend/components/ui/rich-text-editor.tsx` (`RichTextEditor`, TipTap; full toolbar = undo/redo,
  H1-H3, bold, italic, underline, strike, code, text colour, highlight, link, bullet / numbered list, quote, align
  left / centre / right; `toolbar="inline"` = bold, italic, underline, strike, colour only). Paste already strips
  colour / highlight / alignment and keeps real bold / italic / underline (`rich-text-editor.tsx:154-160,800`).
  Price tag description uses it at `master-data-management/products/[id]/components/ProductSpecificationsTab.tsx:307`.
- Stored format: plain text OR sanitised HTML that starts with a block tag. Server allow-list
  `utils/tag_rich_text.py` (`sanitise_tag_html` on save, `plain_text` for every non-rich reader; only colour /
  background-colour on span / mark and text-align on blocks survive; every other attribute, incl. `href`, is dropped).
- FE parser / view: `sorento_crm_frontend/lib/dealer-kit/rich-text.ts` (`parseRichText`, `richPlainText`,
  `richOneLine`, `toEditorHtml`) and `components/dealer-kit/RichTextView.tsx` (draws React elements, never innerHTML).

## Where the line Description lives today (`quotation_lines.description_snapshot`, Text)

Proposal and quotation are the same rows (`quotation_documents.kind`, `models/projects.py:1260-1285`), so one change
covers both. Write path: `LINE_FIELDS` -> `_write_line` (`services/project_quotation_service.py:54-58,1008-1016`);
catalogue default when empty: `product.description or product.product_name` (`:538-539`); set default: set name (`:569`).

| Reader | Where | After |
|---|---|---|
| Lines grid (edit + view) | `QuotationLinesGrid.tsx:436-464` (Textarea / `<p>`) | editor / `RichTextView` |
| Row label ("Description on X", toasts) | `QuotationLinesGrid.tsx:195`, `QuotationVersionEditor.tsx:403,424,670` | one line, no markup |
| PDF, plain + matrix scopes | `services/project_quotation_pdf_service.py:614,736` (`_multiline`) | styled (re-sanitised at render) |
| Customer sign link | payload `project_quotation_document_service.py:2089`; page `(auth)/quotation-sign/[token]/components/QuotationSignScopes.tsx:79,187` | styled via `RichTextView`; label one line |
| Proposal -> quotation, new revision | `copy_line` `project_quotation_service.py:416-431`, `project_quotation_document_service.py:1016` | copied as stored (styling kept) |
| Excel export | `project_quotation_excel_service.py:597` | plain text |
| Price-change alert to management | `project_quotation_document_service.py:822` -> `project_notify_service.py:~675` | plain text |
| Customer feedback panel (amendment rows) | `quotation_amendment_service.py:473` -> `QuotationFeedbackPanel.tsx:75` | plain text |
| SO draft from quotation | `project_so_draft_service.py:1129,1324` | plain text (SO lines are not rich) |
| Project PO check names | `project_po_service.py:185` | plain text |
| Sample request from quote | `sample_request_service.py:1117` | plain text |
| Spec sheet item description | `project_spec_sheet_service.py:422` | plain text (see Q5) |
| AI / MCP | `crm_project_quotations_list` returns scope totals only, no line text (`sorento_crm_mcp/.../catalog.py:1743-1757`) | no change |
| Search | no search reads `description_snapshot` (grep) | no change |

WhatsApp / email send text carries no line descriptions (grep of `QuotationWhatsAppDialog.tsx`), so no change.

## Rules

R1. The Description cell on a proposal or quotation edits with the shared `RichTextEditor`. Nothing new is built.
R2. Stored in the same column, in the same format as the price tag description: plain text, or HTML sanitised by
    `sanitise_tag_html` on EVERY write path (add, save all, edit one, new form, edit form, amendment apply). No migration.
R3. Plain stays plain. An existing plain description shows exactly as today everywhere (grid, PDF line breaks, sign
    link, Excel). An edit whose result carries no styling at all (paragraphs only) is stored back as plain text, one
    line per paragraph, so typing in an old line does not turn it into HTML.
R4. The catalogue default (product description, else product name; set name for a set) is still the starting text.
R5. Styled text prints the same on the PDF (both the plain and the matrix scope tables) and the sign link as in the
    grid's view mode; the PDF re-sanitises the stored value before it is placed into the page (defence in depth).
R6. Proposal -> quotation and new revisions copy the stored value untouched, so the styling travels.
R7. Every plain-text reader in the table above gets `plain_text()` (server) / `richPlainText` / `richOneLine` (FE):
    no tag ever reaches Excel, a notification, an SO / PO line, a sample request or a label.
R8. Issued (frozen) versions are never re-saved; already-sent PDFs and sign pages do not change.

## Examples

Real dev rows requested (`crew-data-request:` on PR #2304); until they come back, the owner's screenshot line:

1. SRTWC8518, today plain: "SORENTO ONE PIECE TWISTER FLUSH WC (S-TRAP 250MM) SRTWC8518-SH C/W PP SEAT COVER".
   After: unchanged until someone edits it. Sales bolds "SORENTO ONE PIECE TWISTER FLUSH WC" and makes "C/W PP SEAT
   COVER" red: stored `<p><strong>SORENTO ONE PIECE TWISTER FLUSH WC</strong> (S-TRAP 250MM) SRTWC8518-SH <span
   style="color: #dc2626">C/W PP SEAT COVER</span></p>`; PDF and sign link show bold + red; Excel cell reads the
   original sentence; the SO line made from it reads the plain sentence.
2. A two-line plain description ("BASIN MIXER" / "c/w pop-up waste"): prints on two lines exactly as today (`_multiline`).
   Opened in the editor it shows two paragraphs; saved with no styling it is stored back as the same two plain lines.
3. A set line: starts with the set name, as today; same editor.

## Edge cases

- Very long text in the 184 px column: view mode wraps (`break-words`, no clamp), same as today; the PDF cell wraps.
- Pasted Word / Excel: the editor's existing paste filter keeps bold / italic / underline, drops colours, fonts, sizes,
  tables become paragraphs; the server allow-list removes anything left. Excel cell paste = plain text.
- Line breaks: Enter = new paragraph, Shift+Enter = `<br>`; both print as a line break, paragraphs with no gap.
- Matrix scopes: the description column is the same cell; the matrix PDF branch (`pdf_service.py:736`) gets R5 too.
- Empty after stripping: stored null, then the catalogue default applies on save, as today.
- Grid keyboard: Enter / Tab inside the open editor belong to the editor; Escape closes it keeping the text.

## Questions (each with a recommendation)

Q1. Toolbar. (a) The shared editor's existing FULL toolbar (as price tag description; owner 5 Nov "full shared rich
text editor w/ colour"). (b) The existing `inline` set: bold, italic, underline, strike, colour. Rec (a): it is the
owner's standing word and the same component; headings print at most 1.4x the cell size.

Q2. Storage. (a) The price tag format: same column, plain or sanitised HTML via `sanitise_tag_html`, no migration.
(b) A second column holding HTML next to the plain one. Rec (a): one allow-list, one parser, plain rows untouched.

Q3. Where the editor opens. (a) The cell shows the styled text; clicking it (or Enter on it) opens the shared editor
in a popover anchored to the cell, about 440 px wide, full toolbar, closes on Escape / outside click keeping the text.
(b) The editor inline in the 184 px cell with no toolbar (keyboard shortcuts only), colour from a small button.
Rec (a): the full toolbar does not fit 184 px, and a popover keeps this lane to the Description cell (other lanes
are reworking the grid's columns and save path). The editor inside looks exactly like the existing one, so no mock.

Q4. PDF fidelity. (a) Render the re-sanitised HTML in WeasyPrint: bold, italic, underline, strike, colour, highlight,
alignment, lists, headings (1.4 / 1.2 / 1.1x) all print; paragraphs without gaps. Links print as plain text (the
allow-list drops `href`). (b) Bold / italic / colour only, everything else flattened. Rec (a): what the editor allows
prints; the only loss is the link target, which a printed document cannot use anyway.

Q5. Spec sheet item description (made from the quotation lines). (a) Plain text, the product's spec-sheet layout
stays as it is. (b) Styled like the quotation. Rec (a): the owner's ruling names the proposal / quotation; the spec
sheet is a product document, and keeping it plain keeps this lane out of its renderer.

## Owner answers (10 Nov ~15:10 MYT)

Q1 (a) full toolbar. Q2 (a) same column, price tag format. Q3 (a) popover editor. Q4 (a) the PDF prints every allowed
style. Q5 (a) spec sheet stays plain. All five match the recommendations; built as above.
