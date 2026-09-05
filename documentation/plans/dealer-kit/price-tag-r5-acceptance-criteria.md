# Price Tag Designer Round 5 - acceptance criteria

Plan: `PLAN-price-tag-r5.md`

## S1 shift lock
- AC-S1-1 Holding Shift while dragging a polygon or boxed-badge corner keeps the corner on a horizontal, vertical or 45-degree line from where the drag started; the handle stays on the shape.
- AC-S1-2 Releasing Shift mid-drag frees the corner; pressing it again re-locks from the current cursor direction.
- AC-S1-3 Edge handles under Shift move the edge on a 0, 45 or 90 degree line, the same rule as corners; on a rotated layer the lock is relative to the layer's own axes.
- AC-S1-4 Without Shift, dragging is unchanged.

## S2 duplicate name
- AC-S2-1 LINES rail shows the product code once for a product whose name equals its code; a product with a different name still shows both lines.
- AC-S2-2 On the canvas and in the PDF, a `name` slot layer or `{{product.name}}` token draws nothing when the name equals the code; the layer still exists in Layers and can be deleted.
- AC-S2-3 A product whose name differs from its code renders the name as before.

## S3 padding
- AC-S3-1 Text layer inspector shows Padding (mm) T/R/B/L; values inset the text on canvas and in the PDF identically; wrapping uses the padded width.
- AC-S3-2 Price badge inspector shows the same row; the figure insets inside the box (and the callout when boxed).
- AC-S3-3 Padding of 0 (or absent, for saved documents) renders exactly as before.
- AC-S3-4 Padding larger than the box clamps to zero text area without errors.
