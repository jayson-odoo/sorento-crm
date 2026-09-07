# PLAN: Image `Stretch` fit + price badge `Margin`

Status: Implemented, awaiting review (7 Sep 2026)
Branch: `feat/dealer-kit-image-stretch-badge-margin` (worktree `.claude/worktrees/tag-stretch-margin`)
UAC: `tag-image-stretch-badge-margin-acceptance-criteria.md`

## Journey

Captain, 7 Sep, reproducing the Sorento LITE flyer tag in the price tag editor:

1. A wide wavy background image in a tall image layer. `Contain` letterboxes
   (white strip under the picture). `Cover` fills the box but crops to a
   single wave. They want the picture forced to the box: every wave kept,
   distorted if it must be. "yes we need stretch".
2. The list price callout (white rounded box, slanted left edge, `LP RM 151`)
   must sit inset from the tag's edge AND keep the figure inset from the
   callout's own edge. Today `padding` on a price badge does both at once
   (it insets the callout, and the figure draws flush inside that smaller
   box), so the two spacings cannot differ. "we need margin also, not just
   padding".

## What exists (measured on origin/main 59dffc60d)

- `ImageFit = 'cover' | 'contain'` in `lib/dealer-kit/tag-template-types.ts:55`.
  Inspector options at `InspectorPanel.tsx:115`. Canvas geometry in
  `KonvaTagLayer.tsx` `ImageContent` (lines ~480-560): `wide` / `drawW` /
  `drawH` letterbox-or-overflow math, clip only for `cover`. Print page:
  `TagSheetRenderer.tsx:314` `objectFit: props.fit === 'cover' ? 'cover' : 'contain'`.
  Backend doc schema `ImageLayerPropsDoc.fit: Literal["cover", "contain"]`
  (`app/schemas/price_tag.py:281`, strict props). `TagTemplateDocModel` is the
  contract that refuses an unknown value - measured: the tag-template CRUD
  route (`create_tag_template`/`update_tag_template`) stores `doc` as an
  opaque `dict` and does not run it through this schema today, so save/update
  do not themselves 422 on a bad `fit`; the schema is what the seeded
  templates and this plan's own tests validate against.
- Price badge padding: `PriceBadgeLayerProps.padding` (types ~line 220),
  `PriceBadgeLayerPropsDoc.padding` (schema ~line 360). Canvas: `KonvaTagLayer.tsx:318-340`
  insets the whole `PriceBadgeContent` group by `paddedBox(w, h, props.padding, scale)`.
  Print: `TagSheetRenderer.tsx:336-380` `padded = paddedBox(...)` and the
  content container gets `padding: paddingCss(props.padding)`; the callout
  polygon is a 100% child of that container. `paddedBox` lives in
  `lib/dealer-kit/text-reflow.ts`. Inspector padding editor: the four
  `NumberInput`s at `InspectorPanel.tsx:735-765`, fed from `props.padding ?? ZERO_PADDING`.

## Design (simplest thing that works)

### Stretch

- `ImageFit = 'cover' | 'contain' | 'stretch'`. Inspector option `Stretch`
  after `Contain`. Backend Literal gains `"stretch"`.
- Canvas: for `stretch`, `drawW = w`, `drawH = h`, origin 0,0. No clip needed
  (nothing overflows). Circle mask still applies.
- Print: `objectFit: 'fill'` for `stretch` (CSS name for distort-to-box).
- The badge layer (`kind: 'badge'`) and product photo keep their existing fit
  handling; only `image` layers get the option.

### Margin on the price badge

Two insets, resolved in ONE place for both renderers, next to
`priceBadgeTypography` in `lib/dealer-kit/price-badge.ts`:

```ts
export interface PriceBadgeInsets { margin: LayerPadding; padding: LayerPadding }
export function priceBadgeInsets(props: Pick<PriceBadgeLayerProps, 'margin' | 'padding'>): PriceBadgeInsets
```

- `margin` insets the callout (and the figure with it) from the layer box.
- `padding` insets the figure from the callout's own edge.
- **Legacy rule:** a badge saved before this slice has no `margin`. Its
  `padding` used to inset the callout with the figure flush inside, which is
  exactly `margin = old padding, padding = 0`. So: `margin` absent →
  `{ margin: props.padding ?? 0, padding: 0 }`; `margin` present (even all
  zeros) → both read as written. Every saved badge renders pixel-identical.
  The inspector writes `margin` on the first edit of either group, which is
  what moves a badge onto the new semantics; when it does, it seeds `margin`
  from the legacy padding and resets `padding` to 0 so the badge does not jump.
- Canvas: outer group at `margin` inset; `PriceBadgeContent` takes a `padding`
  (mm, scaled) and draws the figure inside `paddedBox(callout, padding)` while
  the callout polygon keeps the full inset box. Promo (two-line) variant gets
  the same figure inset: its SP/figure/NETT row keeps the SAME proportional
  base offsets it always had (`w*0.04`, `h*0.1`, `h*0.15`, `h*0.7`), just
  recomputed against the padded box instead of the unpadded one - the same
  "own base gap + padding" shape the print page's fixed `0.5mm 1mm` gap plus
  `insets.padding` uses, so the two renderers agree (AC-8) exactly as they did
  before this slice.
- Print: `padded` = margin box (frame unchanged, rotation origin unchanged);
  content container `padding: paddingCss(insets.margin)`; the figure's text
  container inside the callout gets `padding: paddingCss(insets.padding)`.
- Inspector: for a price badge, `Margin (mm)` four-input group ABOVE
  `Padding (mm)`. Extract the existing four `NumberInput`s into a small
  `SidesInput` used by both groups (text layer keeps only Padding).
- Types: `margin?: LayerPadding` on `PriceBadgeLayerProps`; schema
  `margin: Optional[LayerPaddingDoc] = None` on `PriceBadgeLayerPropsDoc`.
- No migration, no new table, no new permission.

## Tests

Frontend (vitest):

- `lib/dealer-kit/price-badge.test.ts`: `priceBadgeInsets` legacy rule (no margin + padding → margin=padding, padding=0), explicit margin+padding read as written, both absent → zeros.
- `KonvaTagLayer.price-badge.test.tsx`: margin moves the callout group, padding moves only the figure inside it (assert the group x/y and the figure x/y).
- `KonvaTagLayer` image test (add to an existing image test file or a new `KonvaTagLayer.image.test.tsx`): `stretch` draws at `w` x `h` from 0,0 with no clip group; `contain` and `cover` unchanged.
- `TagSheetRenderer.test.tsx`: `stretch` renders `object-fit: fill`; badge margin lands on the container padding and badge padding on the figure container.
- `InspectorPanel.test.tsx`: `Stretch` appears in Fit; price badge shows Margin and Padding groups; editing Margin on a legacy badge seeds margin from padding and zeroes padding.

Backend (pytest, `tests/test_dealer_kit_tag_template_versions.py` or a new
`tests/test_dealer_kit_tag_doc_stretch_margin.py`, Postgres via `_pg_fixture`):

- a template doc with `fit: "stretch"` and a price badge with `margin` saves (200/201) and reads back unchanged
- `fit: "squash"` still 422 (strict Literal intact)

## Phases

- Phase 1 FE (types, resolver, canvas, print, inspector) with vitest.
- Phase 2 BE schema + pytest (test first).
- Phase 3 `/code-review`, browser verification, DoD gate, PR.

## Added 7 Sep: hide the currency on a price badge

Captain: "for the price can I don't set the currency, like I can choose to
remove the currency from the display". Today `RM` is hardcoded in the figure
formatter (`price-badge.ts` ~line 86), so every badge reads `RM 760`.

- `showCurrency?: boolean` on `PriceBadgeLayerProps` and
  `showCurrency: Optional[bool] = None` on `PriceBadgeLayerPropsDoc`. Absent =
  true, so every saved badge keeps printing `RM`.
- The formatter takes the flag and returns `760` (still `en-MY` grouping,
  whole ringgit) when it is false. Both variants: list-only figure and the
  promo `LP: ... / SP ... NETT` lines drop `RM` the same way, since the
  composition is decided once in `price-badge.ts` for both renderers.
- Inspector: a `Show currency` checkbox beside the existing `NETT` toggle in
  the price badge section. No other copy.
- Tests: `price-badge.test.ts` (absent → `RM 760`; false → `760`; promo lines
  without `RM`), `InspectorPanel.test.tsx` (checkbox toggles the prop), pytest
  round-trips `showCurrency: false` on a saved template.
