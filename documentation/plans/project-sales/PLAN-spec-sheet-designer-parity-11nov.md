# PLAN: spec sheet designer parity with the price tag designer

Status: Slice A in build (small fix track: FE only, no migration, no auth/RBAC change). Slice B is a
behaviour card waiting on the owner; no code for it until answered.

Lane: SPEC-SHEET-DESIGNER-PARITY. Owner feedback 11 Nov 2026 (spec sheet SS1 Draft).

## Slice A (fixes)

1. "Add accessory" options show the code once (code + name only when they differ), fixed in the
   shared option label builder.
2. Clipboard parity: Cmd/Ctrl+C / X / V / D and context-menu Paste work in the spec sheet designer
   as in the price tag designer (elements and OS-clipboard images).
3. Resizable Pages and Inspector panels, same component/behaviour as the template designer.
4. Insert field: `{{product.description}}`.

Acceptance criteria: `spec-sheet-designer-parity-11nov-acceptance-criteria.md`.

## Slice B (card first)

Variable registry, several products on one page, table element, PowerPoint export. Card posted
as a `crew-ask` on the PR; built only after the owner answers.

## Slice B behaviour card (posted as crew-ask, 11 Nov)

Mock: `mock-spec-sheet-designer-parity-11nov.html` (this folder). Each element carries
`data-component` = the existing component it maps to, or `NEW`.

### Variables: one registry for both designers (`lib/dealer-kit/merge-fields.ts` FIELDS)

Already there (source):
- `doc.project_title` projects.title (`project_spec_sheet_service._doc_fields`, service:706; model projects.py:303)
- `doc.ref` your_ref else quotation no (service:710); `doc.your_ref` (model projects.py:1192); `doc.quotation_no` (service:708)
- `doc.prepared_by` document.signatory_name else owner name (service:711; model projects.py:1230)
- `doc.prepared_by_phone` signatory_phone else owner contact_number (service:712; model projects.py:1231)
- `doc.date` doc_date else issue/snapshot time, dd/mm/yyyy (service:715; model projects.py:1193)
- `line.area` page row area else section heading (service:658), `line.comment` (service:660), `line.marker` (service:661)
- `product.code/name/brand/dimensions/spec_lines/price_tag_description/list_price` (tag_data_service.py:403-420; spec rows service:1183-1197)
- `product.description` products.description (slice A; model product.py:276)

Proposed additions (no new column, all read off rows the sheet already loads):
- `line.description` the quoted line's own text (snapshot `description`, service:426; ProjectQuotationLine.description_snapshot projects.py:2062)
- `line.quantity` + `line.uom` real quoted qty / unit (ProjectQuotationLine.quantity :2091, uom :2094; today the spec row hard-codes 1, service:745)
- `line.technical_spec` (projects.py:2078), `line.notes` (projects.py:2112), `line.item_label` (projects.py:2076)
- `doc.subject_title` (projects.py:1215), `doc.attn` (attn_name), `doc.recipient` (recipient_name_snapshot)
- `doc.project_code` (projects.py:302), `doc.page_no` / `doc.page_count`
- `accessory.N.code|name|brand|description|dimensions` = the existing Accessory N position (`subjectPart`) spelled as a token, so a text can say "{{accessory.1.code}}" without a bound layer.

### Several products on one page: it already exists, needs a template

A page's "Add accessory" picks other quotation lines; a picked line's own page is skipped
(`absorbed`, service:587-596) and its product is drawn through the template's Accessory 1..N
layers (`subjectPart`, PS-SPEC-SHEET). The owner's WC + angle valve + hose page is this mechanism
plus a template with two Accessory slots. Gaps: the picker labels (fixed in slice A), no
"Accessory card" block to drop in one go (photo + title + description grouped), and the slot
count is whatever the template draws (a 3rd pick with only 2 slots is not printed, no warning).

### Table element (shared designer, price tag too)

Konva has no table node: it gives Rect, Text (with wrap + measured height) and Group. We build a
`table` layer kind: rows x cols grid stored on the layer, each cell = text (rich, merge fields)
+ border colour/width per side + padding + fill; row height = max(set height, measured text) so
long text grows the row (the table grows down or shrinks text, a setting). Insert/delete
row/col, merge cells via the context menu. Print uses the same layer renderer (one pipeline).
Effort ~3-4 days incl. tests.

### PowerPoint export

(a) python-pptx on the backend worker, built from the same print payload: text layers -> text
boxes (editable, font/size/colour/bold kept), images -> pictures, shapes -> autoshapes, the new
table -> a real pptx table with per-cell borders, page size -> slide size. Lost: rich inline
runs beyond bold/italic/underline/colour, image crop masks (exported pre-cropped), rotation of
grouped items, custom fonts not on the viewer's machine. ~3 days.
(b) pptxgenjs in the browser: same mapping, no worker, but a second renderer to keep in step
and large sheets block the tab.
Recommendation: (a), one server pipeline beside the PDF export.
