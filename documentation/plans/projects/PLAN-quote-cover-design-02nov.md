# PLAN: Quotation cover page designer (QUOTE-COVER-DESIGN, follow-up to #2088)

**Status:** Review. PR #2094 open (ready). Rounds: main (red 293ba35f70), fix round 1 (crew browser FAILs +
security should-fix), round 2 (reviewer findings), round 3 (render cap), round 4 (test gaps), round 5 (crew pass 3 Nov: B1 drag
overlay, M1 proposal noun; red 255368ce51). Security PASS at 7c9e02444e. Track: L. UAC: `quote-cover-design-02nov-acceptance-criteria.md`. Mock:
`documentation/mockups/QUOTE-COVER-DESIGN/index.html`.

## Journey

Owner: "for cover letter it should be configurable designable and able to show in the Cover Letter tab". The admin
designs the company cover page once in Quotation Templates. Sales sees the cover live on each quotation's Cover letter
tab, edits the intro and closing for that customer, and the sent PDF and sign link print it.

## Owner decisions (2 Nov 19:46)

- Q1 (a): the Cover letter tab shows a live cover preview, and the old free-text letter becomes the intro block.
- Q2 (a): a form-based designer in Quotation Templates. Reuse every existing piece and build only what has no
  existing piece. The reuse table goes in the PR body.
- Q3: the design controls letterhead on/off, title, rows (on/off, order, printed label), and intro + closing text with
  the existing merge fields. No custom rows and no fonts.
- Q4 (a): the layout comes from the design. Intro and closing are editable per quotation, like terms. There is one
  active design per company.
- Q5 (a): the design is copied onto each revision at send, so sent revisions never change.

## Reuse table (path:line on main 0f3cdbf648; build only the "New" column)

| Need | Reused as is / extended | New |
|---|---|---|
| Design storage + one active per company | `quotation_templates` (`app/models/projects.py:1171`): `kind` is a free String(32), so `cover_page` is a new kind with no constraint change (`QUOTATION_TEMPLATE_KINDS` :832-834, `_assert_kind` `project_quotation_template_service.py:281`); the partial unique index on active per (company, kind) :1213; routes list/get/create/update/activate/delete `app/api/v1/projects/quotation_templates.py:65-165` | one JSONB column `design` (letterhead, title, rows, closing_html) |
| Admin list + activate | `QuotationTemplatesClient.tsx:35` (DataGrid, Active badge, Activate), hooks `useQuotationTemplates.ts:18/:25`, service `quotationTemplateService.ts:36-72` (kind-keyed) | line tabs Terms / Cover page on `quotation-templates/page.tsx:16`; the client takes `kind` instead of the hardcoded 'terms' (:36-37) |
| Editor form layout + live preview beside it | `dealer-kit/tile-designs/components/TileDesignDialog.tsx` (drag list :200-232, checkboxes :243, Name Input :167, preview :259-265) as the pattern; `Sortable`/`SortableItem`/`SortableItemHandle` `components/ui/sortable.tsx:538/:644/:699`; label Input per row as in `WorkflowHeaderSectionsEditor.tsx:107-116`; `switch.tsx`, `checkbox.tsx`, `input.tsx`, `label.tsx` | the cover design form (composition only) |
| Intro / closing text + Insert field | `RichTextEditor` `components/ui/rich-text-editor.tsx` with `onEditorReady` (:72, :573) + `insertContent`, copied from `system-management/email-templates/components/EmailTemplateForm.tsx:63-70, :178-194`; merge fields GET `/quotation-templates/merge-fields` (`quotation_templates.py:49`, no FE caller yet), `MERGE_FIELDS` :51, unknown-token refusal `assert_tokens_known` :139, `render` :160 | none (wire the existing endpoint into an Insert field list) |
| Letterhead | `_sender` `project_quotation_pdf_service.py:307`, `_letterhead_html` :435, `fetch_logo_data_uri` :366; sign page `sender_name`/`sender_logo_url` | none (a switch only; there is no letterhead picker in the app) |
| Rows, labels, terms cleaning, reference | `quotation_cover_service.py`: `cover_rows` :136 (keys/labels :151-164), `clean_terms_html` :120, `cover_reference` :31 | `cover_rows` takes a design (filter, order, relabel) and works for a draft (values from the document; reference with the next revision number) |
| PDF page 1 | `_cover_html` :599, cover CSS + A4 portrait `@page` :785-795, `build_issue_html` :800 | title from the design, intro above and closing below the rows |
| Sign link card + preview card | `CoverCard` :106 and `SenderRow` :82 in `QuotationSignClient.tsx` | extracted to one shared component used by the sign page, the quotation Cover letter tab and the designer preview |
| A4-shaped scaled preview | `components/dealer-kit/ScaledSheet.tsx:49` (scale-in-box), `TagVersionViewer.tsx:59` (fit to width), A4 794px note `CatalogueRenderer.tsx:283` | a small A4 frame using that pattern |
| Draft preview (nothing stored) | POST `/email-templates/preview-draft` `app/api/v1/system/email_templates.py:60`, `preview_draft` `email_template_service.py:503`; `build_document_context` `project_quotation_template_service.py:216`, `render_for_document` :264 | POST cover-preview for a quotation draft and for an unsaved design (sample values) |
| Per-quotation intro | `quotation_documents.cover_letter_html` + `quotation_issues.cover_letter_rendered` (already copied at send); seeded at create by `_render_templates_onto` `project_quotation_document_service.py:218` | the cover_page design's intro seeds it; closing gets `cover_closing_html` / `cover_closing_rendered` |
| Old revisions frozen | `quotation_issues.layout_version` (#2088) | layout 3 + `quotation_issues.cover_design` JSONB snapshot |
| Terms row display | `lib/terms-html.ts` `TERMS_HTML_CLASS` | none |

## Architecture

- **Design shape** (`quotation_templates.design`, validated server side): `{show_letterhead: bool, title: str<=60,
  rows: [{key, shown, label<=60}] (exactly the 12 known keys, each once), closing_html}`. The intro lives in `body_html`,
  the same place the terms template keeps its text. Validation: no unknown keys, no duplicates, no custom rows, and
  unknown tokens are refused with the existing 422. `body_html` may be empty for `cover_page`.
- **Default design** = the #2088 cover (12 rows, #2088 labels, title QUOTATION, letterhead on, no intro or closing).
  It applies whenever no cover_page design is active.
- **Create**: the active cover_page design's intro renders into `cover_letter_html` and its closing into
  `cover_closing_html`, through the existing render path. The old cover_letter template kind stays as a fallback for
  the intro only if no cover_page design is active.
- **Send (`issue()`)**: stamps `layout_version = 3` and copies the design (active or default) into
  `quotation_issues.cover_design`, plus `cover_closing_rendered` (`cover_letter_rendered` is already copied).
- **Render**: layout 3 builds page 1 from `issue.cover_design`: letterhead per the switch, title, rows shown in order
  with design labels, intro above, closing below. The letter is not printed on page 2. Terms print on page 1 only when
  the Terms row is shown; otherwise they print after the total (the #2088 page-1-only rule applies when shown).
  Layouts 1 and 2 are untouched byte for byte.
- **Countersign**: the layout-3 payload adds the title, show_letterhead and intro/closing html (cleaned) beside
  `cover_rows`. The shared card renders them. The bottom terms panel shows only when the Terms row is hidden.
- **Preview**: POST `.../quotation-documents/cover-preview` (project-scoped, body = the form's staged header/terms
  fields + intro/closing, works before the first save) and POST `/quotation-templates/cover-preview` (body = an unsaved
  design, filled with fixed fake sample values). Both store nothing, return the same payload shape as the sign page
  cover, and are gated like their parent screens.
- **Migration** `qcd_0001_cover_designs` on `qcp_0001_cover_page_fields`: `quotation_templates.design JSONB NULL`,
  `quotation_documents.cover_closing_html TEXT NULL`, `quotation_issues.cover_design JSONB NULL`,
  `quotation_issues.cover_closing_rendered TEXT NULL`. Additive, IF NOT EXISTS.

## Added during review (2 Nov)

- **Deactivate** POST `/config/quotation-templates/{id}/deactivate`, cover_page only (terms keep the refusal to delete or
  deactivate their only active template), gated like activate. With no active design the default design applies.
- **Default design endpoint** GET `/config/quotation-templates/cover-default` (gated like the list): the one source of
  the 12 rows, labels and title; the frontend holds no copy.
- **Merge fields filled on every save**: `{{tokens}}` in cover_letter_html, cover_closing_html and terms_html are filled
  on create AND PATCH and in both previews (crew saw a raw token because the form pre-fills the template's raw text).
  An unknown token is refused with 422 everywhere.
- **Size limits** (security review): every HTML input capped at 50000 characters on create/update/preview (not on
  responses); the filled-in result of `render()` is sized before it is built and refused over 50000 with a 422
  (`quotation_template_rendered_too_long`); the HTML cleaner and the token scan are linear.
- **Shared helpers** (reviewer, reuse requirement): `sender_of` (name + logo for the sign page and previews; the PDF's
  `_sender` adds address and Tel from system settings), `_cover_row_html` (one row renderer for #2088 and designed
  covers), `next_issue_no` (send and preview).
- **Drag**: rows are direct children of `Sortable`; an extra wrapper left the DragOverlay clone empty.
- **Drag overlay out of the dialog** (crew pass 3 Nov, B1): the shared `Sortable` portals its `DragOverlay` to
  `document.body`. Inside the Radix dialog (translate transform) the fixed overlay was offset by the dialog's corner and
  dnd-kit collided against that rect, so a drag landed on the wrong row. Shared fix, so `TileDesignDialog` gets it too.
- **Document noun on the CRM preview** (M1): the Cover letter tab passes `documentNoun(document)` to `CoverPagePreview`,
  so a proposal prints "Proposal from" like the sign page. The designer's sample stays "Quotation".

## Test list (tester, red first)

Backend:
1. Design validation: unknown or duplicate row key refused; a label or title over 60 refused; an unknown token in
   intro/closing refused (422); create/update round-trip; activate keeps one active per company for cover_page and does
   not touch the active terms template.
2. Create: a new quotation gets the rendered intro (cover_letter_html) and closing from the active design. With no
   design, the closing is empty and the intro follows the old rule.
3. Send: layout 3, cover_design equals the active design (or the default), cover_closing_rendered copied. Editing or
   activating another design afterwards changes neither the PDF nor the sign payload of that revision.
4. PDF layout 3: title, letterhead off, hidden rows absent, order and labels from the design, intro above and closing
   below the rows, letter not on page 2. Terms row hidden: terms after the total, not on the cover. Layout 2 is
   unchanged.
5. Countersign layout 3: same rows/labels/order, title, intro/closing cleaned, show_letterhead. Terms hidden: bottom
   panel present (`terms` still sent).
6. Previews: the quotation draft preview with unsaved values (next revision number, fields as sent in the body), and
   the design preview with sample values. Both store nothing (row counts unchanged) and are permission-gated (no
   permission: 403).
7. Global guards: `tests/test_schema_uuid_id_principle.py`, `tests/test_list_pagination_limit.py`.

Frontend:
8. Quotation Templates: Terms | Cover page tabs. The Cover page list and Add. The editor: tick, drag (keyboard or
   handler), rename, letterhead switch, title, intro/closing with Insert field, preview updates.
9. Cover letter tab: the preview card shows the design's rows/title. In edit, Intro text + Closing text editors; the
   save body carries cover_letter_html + cover_closing_html.
10. Sign page: the shared card renders title/intro/closing, and the letterhead is hidden when off. Layout 2 payloads
    render as today.

## Lane steps

UAC -> tester red (`test(red):`) -> coder green -> migration on the throwaway DB (upgrade/downgrade) + crew SQL ->
kill-proof -> reviewer + security-reviewer -> browser pass on crew's copy (designer, Cover letter tab preview, real
PDF, sign 1280/375, old revisions) -> guides (`set-standard-quotation-terms.md`, `work-a-project-quotation.md`) ->
hand test.
