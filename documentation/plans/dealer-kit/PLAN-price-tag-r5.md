# PLAN - Price Tag Designer Round 5 (shift-locked corners, no duplicate name, padding)

Status: in progress, lane `feat/price-tag-r5` stacked on `fix/price-tag-r4` (PR #682), 5 Sep 2026
UAC: `documentation/plans/dealer-kit/price-tag-r5-acceptance-criteria.md`
Predecessor: `PLAN-price-tag-r4.md`

User test on the r4 lane stack, 5 Sep 2026, three asks.

## S1 - Shift locks a corner or edge drag to a straight line

PowerPoint behaviour: with Shift held while dragging a polygon or badge corner handle, the
move is constrained to horizontal, vertical or 45 degrees, whichever is closest to the
cursor's direction from the drag start; releasing Shift mid-drag frees it again. Edge handles
already move along one axis by construction when the edge is axis-aligned; for a slanted edge
Shift constrains the edge's translation the same way.

- `handlePolygonDragMove` (`TagCanvasEditor.tsx:1350`) reads `e.evt.shiftKey`; the delta from
  the drag start is snapped by a pure helper `snapDelta(dx, dy)` in `polygon-path.ts` (angle
  bucketed to 0/45/90 degrees: the dominant axis when |dx| and |dy| differ by more than the
  tan(22.5 deg) ratio, else the diagonal with equal magnitudes). Preview and drag end both use
  the snapped delta. Track the start position in `polygonDragRef` (it already carries the drag
  state); the node's own position is set to the snapped point on each move so the handle does
  not drift from the shape.
- Tests: `snapDelta` (pure); `TagCanvasEditor.polygon.test.tsx` a shift-drag with dx=20,
  dy=3 moves the corner by (20, 0); dx=10, dy=12 moves by (11, 11) (equal magnitudes).

## S2 - Product name that equals the code is redundant

Sorento's product name IS the product code. Today it shows twice in the request designer's
LINES rail (`RequestTagDesigner.tsx:1108-1109` renders `code` then `name`) and twice on the
canvas (seeded product blocks carry a `name` slot layer under the `code` layer).

- Rail: render the `name` line only when `name.trim().toLowerCase() !==
  code.trim().toLowerCase()`.
- Canvas + print: in `resolveSlotText` (`lib/dealer-kit/product-block.ts`), slot `name` and
  merge token `product.name` resolve to `''` when the name equals the code (same comparison),
  for product, set-member and line data. One place, both renderers, every existing template.
  The layer stays in the document (the designer can delete it); an empty text layer draws
  nothing.
- Starter template (`request-tags.ts` `starterTemplateFor`) and the seeded docs
  (`scripts/tag_template_seed_docs.py`) keep their `name` layer: the resolver rule already
  blanks it, and seeds never rewrite existing templates, so a seed edit buys nothing.
- Also: `formatSetMemberLine` (set-member lines `- CODE (NAME)`) and `buildAlternativesRow` (bakes code/name as literals with no slot) apply the same rule. A set's own `name` vs `set_code` gets the rule too (harmless widening, review nit 5).
- Tests: `product-block.test.ts` name==code resolves ''; rail test in
  `RequestTagDesigner.test.tsx` shows one line for a duplicate name and two for a different one.

## S3 - Padding on text-bearing layers

Word / PowerPoint internal margins. Margin on an absolutely placed layer is its position, so
the control is PADDING: four sides, mm, default 0, on `TextLayerProps` and
`PriceBadgeLayerProps` (`padding?: {top, right, bottom, left}`; absent = 0, so saved docs
are unchanged).

- Inspector: a "Padding (mm)" row of four `NumberInput`s (T R B L) in the shared
  `TypographyControls`, so text and badge get it together.
- Konva: the `Text` node is offset by (left, top) and sized `w - left - right` by
  `h - top - bottom` (clamped at 0); the badge's figure/box text likewise inside its box.
  Text reflow (`text-reflow.ts`, the live resize path) must use the padded width.
- Print: `padding: <t>mm <r>mm <b>mm <l>mm` with `box-sizing: border-box` on the text frame
  and on the badge's text container.
- Tests: `KonvaTagLayer` text with padding renders the Text at the inset; print renderer
  emits the padding; `text-reflow` uses the padded width; `InspectorPanel` writes `padding`.

## Verification

Agent stack moves to this worktree (deepest of the stack): FE :3080 / BE :8080 / worker.
