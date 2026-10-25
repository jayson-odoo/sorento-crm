# PLAN: price tag barcode renders like staff's barcode, one renderer (PRICETAG-BARCODE-MATCH)

Status: Review (round 2: text layers added by owner, 25 Oct 17:07). Small fix track (S): FE only, no migration, no auth/RBAC, no new ingest. Mock v1 approved by owner in Lavish (17:07).

## Journey

Owner, 25 Oct 2026, after a price tag request on prod (PT-202610-0001): the barcode staff use
today, the barcode in the Room Designer canvas and the barcode in the request preview all look
different. They must match 100%, and the target is the staff barcode:

- product code ABOVE the bars, centred, black serif, no box behind it;
- standard EAN-13: start, centre and end guard bars run longer, down into the digit row;
- large human-readable digits: first digit left of the start guard, six digits between the start
  and centre guards, six between the centre and end guards;
- white background, clear quiet zones left and right.

## Today (why the three differ)

Two renderers draw the barcode layer:

| Surface | Code | Draws |
| --- | --- | --- |
| Canvas (tag template editor, request designer) | `KonvaTagLayer.tsx:611` `BarcodeContent` | Konva rects + Konva Text; bars PNG from `jsbarcode` on an offscreen canvas (`:575`), STRETCHED to `barsWidth x barsH` (`:690`) |
| Preview (request > Design, lightbox) | `components/dealer-kit/ScaledSheet.tsx:14` imports `TagSheetRenderer` | same DOM as print, CSS-scaled |
| Print / PDF export | `TagSheetRenderer.tsx:829` `BarcodeLayer` | DOM divs; bars PNG as `<img>` with `objectFit: contain` (`:904`), so bars keep jsbarcode's own aspect and shrink inside the band |

Both share only `barcodePlateGeometry` (`lib/dealer-kit/barcode.ts:116`). Differences:
stretch vs contain on the bars (different bar-block width and height), Konva's default Arial vs
DM Sans on the strip, canvas text metrics vs CSS line boxes for the digits, and neither draws the
EAN guard layout: both print one centred line `9 551028 474331` under flat bars, with a black
header strip (part of the barcode layer, `show_code`, not of the template).

## Fix

One pure function, `barcodeSvg()` in `lib/dealer-kit/barcode.ts`, returns the whole label as one
SVG string (viewBox in mm of the layer box): white background, code text above in serif, the
bars as rects, EAN-13 guards extended, each digit centred in its own 7-module cell. Both surfaces
draw that same SVG through the browser's own SVG rasteriser:

- canvas: `HTMLImageElement` from the SVG data URL, drawn as a `Konva.Image` at the layer box;
- preview and print: `<img src=SVG data URL>` filling the layer box.

Same string, same rasteriser, same box: identical at any zoom by construction. The layout is a
function of the box only (no absolute mm floors), so a zoomed or resized box scales uniformly.

Geometry (module X = box width / total modules):
- EAN-13: 11X left quiet zone (holds the first digit), 95X symbol, 7X right quiet zone = 113X.
- Digit font 10.5X (a monospace digit is about 0.6em, so it fills its 7X cell), capped at 22% of the
  box height for a squat box. Code text uses the same size, serif; a code too long for the width
  is compressed with `textLength` rather than clipped.
- Guard bars run 0.45 x digit font below the normal bars.
- Code128 (any value that is not a checksum-valid 13-digit EAN; 8 and 12 digit values included,
  as today): 10X quiet zones, no guards, the value centred under the bars, code above as for EAN.

`show_code` off drops the code row; the bars take its height.

## Tests (red first)

- `lib/dealer-kit/barcode-svg.test.ts`: decode the SVG's bars with `@zxing/library`
  (`EAN13Reader`, `Code128Reader`) back to the input digits; code text above the bars, serif,
  black, no black strip; guards longer than normal bars; digit 1 left of the start guard, 2-7
  and 8-13 between guards; digit font at least 10 modules; quiet zones; uniform scaling.
- Canvas and print draw the SAME data URL for the same layer
  (`KonvaTagLayer.barcode.test.tsx`, `TagSheetRenderer.test.tsx`).

## Text layers (round 2, owner 25 Oct: "100% canvas = preview = print")

A product title showed cut to `SRTWT914SS-GM-` in the preview. Cause: two wrap engines and
two sets of units for the same text layer.

| | Canvas (`KonvaTagLayer.tsx` text case) | Preview / print (`TagSheetRenderer.tsx` `renderTextLayer`) |
| --- | --- | --- |
| Wrap | Konva `wrap="word"` | browser `pre-wrap` + `break-word`, fixed height, `overflow: hidden` |
| Font size | `pt * 0.35` mm | `pt` (0.3528 mm) |
| Letter spacing | `0.1` mm per unit | `1px` (0.2646 mm) per unit |
| No face named | Konva default (`fontFamily` empty) | DM Sans |
| Weight | bold only at 600+ | exact weight |

So the same title broke at different places, and the print box clipped its second line.

Fix: `lib/dealer-kit/text-layout.ts`. `textLayerLines()` breaks a layer's text ONCE, from its mm
box, inside its padding, at a fixed scale (CSS px per mm), with Konva's own word-wrap rule
(ported as `wrapTextLines`, pinned against real Konva in `text-layout.test.ts`). The canvas
draws those lines with Konva wrap off; the print page prints them with `white-space: pre`.
`textFace()` gives both the same units, the canvas's own (0.35 mm per pt, 0.1 mm per
letter-spacing unit), DM Sans as the fallback face and the exact weight. A live resize
re-breaks with the same function (`TagCanvasEditor.tsx` transform handler), and both surfaces
re-measure when a font face finishes loading (`useFontsEpoch`).

No shrink-to-fit exists on either surface; a title longer than its box shows the lines that
fit on both, at the same break. Making the box taller (or the type smaller) shows it whole.

## Out of scope / reported

- Price badge typography still converts its own way on each surface (its own shared helper,
  `priceBadgeTypography`); not reported as differing, not touched.
