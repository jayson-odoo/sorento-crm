# Contract: PRICETAG-COMBO-FORMAT (Phase 2)

Shapes the tester writes against and the coder implements. UAC: `pricetag-combo-format-acceptance-criteria.md`.
Test list: `pricetag-combo-format-test-list.md`. Base: main 311a6b52 (includes #2172).

## Backend

### `app/utils/tag_rich_text.py` (NEW)

```python
ALLOWED_TAGS = {"p","br","strong","em","s","u","code","h1","h2","h3","ul","ol","li","blockquote","a","span","mark"}
BLOCK_TAGS   = {"p","h1","h2","h3","ul","ol","blockquote"}   # a value is "rich" iff it starts with one of these

def is_rich(value: str | None) -> bool          # lstrip, case-insensitive "<p" "<h1".. "<blockquote" followed by ">" or whitespace
def sanitise_tag_html(value: str | None) -> str | None
    # None / "" / whitespace -> None
    # not is_rich(value): plain text. No "<" -> unchanged. Contains "<" -> the same parser runs in TEXT mode:
    #   every tag removed (script/style/iframe/object/embed WITH content), text kept UNescaped, newlines kept.
    #   "a < b" stays "a < b"; "<img src=x onerror=alert(1)>x" -> "x" (defence in depth; captain ruling 5 Nov)
    # rich -> allow-list re-serialisation (stdlib html.parser), then if no text content remains -> None
def plain_text(value: str | None) -> str | None
    # None -> None; not rich -> unchanged; rich -> blocks joined by "\n",
    # "• " per <ul><li>, "1. " "2. " per <ol><li> (restart per list), nested level indent "  " per level,
    # <br> -> "\n", entities unescaped, no markup
```

Sanitiser rules (UAC AC-5..AC-8): attributes all dropped except `style`; within `style` keep only
`color` and `background-color` whose value matches `^#[0-9a-fA-F]{3}$|^#[0-9a-fA-F]{6}$|^rgb\(\s*\d{1,3}\s*,\s*\d{1,3}\s*,\s*\d{1,3}\s*\)$`
(on `span`, `mark`) and `text-align: left|center|right` (on `p h1 h2 h3 li`). Kept declarations are
re-emitted lower-case as `prop: value` joined by `; `. A tag left with an empty style has no style attribute.
`script style iframe object embed` dropped with content; other unknown tags dropped, text kept and escaped.
Comments, doctype, processing instructions dropped. Unclosed allowed tags are closed at the end. Text is
always escaped (`& < > "`). Idempotent.

### Write paths that call `sanitise_tag_html`
- `product_combo_service` create + update (`description`), before the existing 5000 limit check (the limit
  applies to the sanitised value, so the schema's raw `max_length` moves into the service).
  `ProductComboCreate` gains optional `description` (captain ruling 5 Nov).
- product update `price_tag_description` (`app/schemas/product.py` / product service).
- `scripts/import_product_combos.py` when it writes `description`; its compare uses `plain_text` on both
  sides.

### Template price type
- `dealer_kit.tag_template.price_type` `VARCHAR(16) NULL`, CHECK `price_type IN ('list','selling','both')`.
- Schemas: `TagTemplateCreate/Update/Response.price_type: Optional[Literal["list","selling","both"]]`.
- `GET /api/v1/dealer-kit/tag-templates?price_type=list|selling|both|unset` filters (`unset` = NULL).

### Link defaults
- `product_tag_template` and `combo_tag_template`: `is_default` replaced by
  `default_list BOOLEAN NOT NULL DEFAULT false`, `default_selling BOOLEAN NOT NULL DEFAULT false`;
  partial unique indexes `uq_dealer_kit_product_tag_template_default_list` (product_id WHERE default_list),
  `..._default_selling`, and the same two for combo (`combo_id`).
- Backfill: `is_default = true` -> both flags true. Downgrade: `is_default = default_selling`, or
  `default_list` where the owner has no `default_selling` row.
- `ProductTagTemplatesUpdate`: `template_ids`, `default_list_template_id`, `default_selling_template_id`,
  and legacy `default_template_id` (when the two new ones are both absent, it sets BOTH).
- A default must be among `template_ids` (existing 422) and fit its type: `default_list` needs price_type
  in (list, both, NULL); `default_selling` needs (selling, both, NULL). Else 422
  `TEMPLATE_PRICE_TYPE_MISMATCH`.
- A lone link that fits a type is that type's implicit default (today's lone-link rule, per type).
- `ProductTagTemplateItem` adds `price_type`, `default_list: bool`, `default_selling: bool`; keeps
  `is_default` = `default_list or default_selling` (compat).

### Request lines
- `fits(template, price_type)`: list -> template.price_type in (list, both, None); selling -> (selling, both,
  None). A line with `price_type` NULL fits everything (pre-LPSP data).
- `line_links` keeps its shape; filtering by the line's price type happens in `line_template_id`,
  `require_line_templates`, the live preview (`first_fallback` path), and `published_items`.
- `line_template_id(..., price_type=...)`: a sent pick that does not fit -> 422
  `TEMPLATE_PRICE_TYPE_MISMATCH`; no pick -> that type's default -> lone fitting link -> None.
- Submit / Approve: a product line whose (product/combo) has >=1 published link but NONE fitting its price
  type -> 422 `NO_TEMPLATE_FOR_PRICE_TYPE`, `detail=f"line:{idx}"`, message
  `f"{label}: No SP template linked"` (or `LP`), label = combo name for a combo line, else product code.
  A line whose item has NO links at all keeps today's behaviour (unchanged NO_TEMPLATE path).
- A re-sent pick equal to the line's stored `tag_template_id`, with the line's price type unchanged, is kept
  even if it no longer fits (no 422; captain ruling 5 Nov). Only a changed pick or a changed price type is
  checked.
- Approve uses the same gate as Submit (`require_line_templates` / the no-fitting-template check).
- Existing saved lines are not rewritten: resolve/print uses the stored `tag_template_id` even if it no
  longer fits (AC-37); only save with a NEW pick or a changed price type re-filters.
- Portal: `GET /lookups/product-tag-templates/{product_id}?combo_id=&price_type=list|selling` filters;
  absent `price_type` = unfiltered (compat); any other value 422.
- Combo link indexes: `uq_dealer_kit_combo_tag_template_default_list` / `..._default_selling`.

### Migration
- One revision, id <= 32 chars, e.g. `ptag_0015_combo_format`, `down_revision` = main's head at build time
  (re-parent with `scripts/alembic-reparent.sh` before the PR is ready).

## Frontend

- `components/ui/rich-text-editor.tsx`: new toolbar buttons (aria-labels exact): "Underline", "Text colour",
  "Highlight", "Align left", "Align centre", "Align right". Colour + highlight popovers use
  `components/common/ColorPicker.tsx` (moved from `app/(protected)/dealer-kit/tag-templates/components/ColorPicker.tsx`,
  same props), with a "Remove colour" action. Emitted HTML: `<span style="color: #6b7280">`,
  `<mark style="background-color: #fde68a">` (or span, per tiptap's output; the sanitiser accepts both),
  `<p style="text-align: center">`, `<u>`.
- `lib/dealer-kit/rich-text.ts` (NEW):
  ```ts
  export type RichRun = { text: string; bold?: boolean; italic?: boolean; underline?: boolean; strike?: boolean; code?: boolean; color?: string | null; highlight?: string | null };
  export type RichBlock = { kind: 'p' | 'h1' | 'h2' | 'h3' | 'li' | 'quote'; runs: RichRun[]; align?: 'left' | 'center' | 'right' | null; marker?: string | null; level?: number; sizeFactor: number; bold?: boolean };
  export function isRich(value: string | null | undefined): boolean;
  export function parseRichText(value: string | null | undefined): RichBlock[];   // DOMParser, never innerHTML
  export function richPlainText(value: string | null | undefined): string;        // same rules as BE plain_text
  ```
  sizeFactor: h1 1.4, h2 1.2, h3 1.1, else 1. Headings `bold: true`. `li.marker` "•" or "1." etc.
- `textLayerLines` (existing) accepts blocks and returns lines of runs measured per run face; one function
  for canvas and print.
- Template dialog: "Price type" toggle group, labels "LP", "SP", "LP & SP" -> `list|selling|both`; unset
  allowed (no button pressed).
- Template list: badge text "Set price type" for NULL; filter "Price type" options LP, SP, LP & SP, Not set.
- Request line: "No SP template linked" / "No LP template linked" pill; Submit reason
  `"<label>: No SP template linked"`.
- Combo photo: button `aria-label="Preview photo of <combo name>"` opening
  `components/common/AttachmentPreviewModal.tsx` with `items=[{ id: image.attachment_id, name: combo.name, url: image.url }]`.
