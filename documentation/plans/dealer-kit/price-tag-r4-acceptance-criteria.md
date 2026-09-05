# Price Tag Designer Round 4 - acceptance criteria

Plan: `PLAN-price-tag-r4.md`

## S1 fonts
- AC-S1-1 An uploaded `.ttf` brand font, picked in the font dropdown, renders on the canvas in that face (the glyphs visibly differ from Arial; screenshot evidence).
- AC-S1-2 The same tag exported to PDF is set in that face.
- AC-S1-3 `GET /api/v1/public/dealer-kit/fonts/{id}` returns 200 + font content type for a font asset, 404 for a non-font asset and for an unknown id, with no authentication.
- AC-S1-4 A font whose face fails to load produces one toast naming the family; the editor keeps rendering in the fallback.
- AC-S1-5 Existing `.woff2` / `.otf` uploads keep working (content type per extension).

## S2 stale line data
- AC-S2-1 Open a request design, set a barcode on the line's product in another tab, return to the designer tab: a Barcode layer resolves the new value without a reload, and the inspector "Barcode value" placeholder shows it.
- AC-S2-2 The refresh never flashes the loading state or replaces the canvas with an error when the background call fails.
- AC-S2-3 Focus and visibility firing together produce one resolve call.

## S3 inline edit copy
- AC-S3-1 Double-click on a text layer whose whole content is `{{product.code}}` opens the inline editor showing the resolved code (e.g. `SRTWT8267-GM`), fully selected, so Cmd/Ctrl+C copies it.
- AC-S3-2 Typing in that editor changes nothing; Enter, Escape and click-away close it and the layer text is still `{{product.code}}`.
- AC-S3-3 A layer with mixed text (`Code {{product.code}}`) or a plain text layer opens editable on the raw content, exactly as before.
- AC-S3-4 In the template editor with no preview product, a sole-token layer opens on the raw token (nothing to resolve).

## S4 polygon shape
- AC-S4-1 Inspector shape select offers Polygon; choosing it on a rectangle keeps the rectangle's look until a corner is moved.
- AC-S4-2 Double-click a polygon shows a handle on every corner and every edge midpoint; dragging a corner moves only that corner, dragging an edge midpoint moves that edge (both endpoints) parallel to itself.
- AC-S4-3 Handles cannot leave the layer box; resizing the box with the Transformer scales the polygon with it.
- AC-S4-4 Corner radius rounds every vertex and a large radius never draws artefacts (clamped).
- AC-S4-5 Fill, stroke, stroke width, rotation, opacity and z-index work as for a rectangle.
- AC-S4-6 The PDF prints the same polygon (SVG path), matching the canvas.
- AC-S4-7 Escape or clicking empty canvas leaves corner editing; undo reverts one drag.
- AC-S4-8 A saved document from before this change opens unchanged (no `points` field is required).
- AC-S4-9 Works at 1280px; the handles are usable with a mouse.

## S5 barcode override
- AC-S5-1 With a Barcode layer bound to a product that has a barcode, select all in "Barcode value" and press Delete: the box stays empty, the canvas draws no bars, the amber "Unlinked from product data" note and the Relink button show.
- AC-S5-2 Type any value into the empty box: the canvas draws that value.
- AC-S5-3 Click Relink: the box shows the product barcode again and the canvas draws it.
- AC-S5-4 The PDF matches the canvas in all three states.
