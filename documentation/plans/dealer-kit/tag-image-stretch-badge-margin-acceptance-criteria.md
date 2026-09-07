# UAC: Image `Stretch` fit + price badge `Margin`

Plan: `PLAN-tag-image-stretch-badge-margin.md`.

## Stretch

- AC-1 An image layer's Fit dropdown offers Cover, Contain, Stretch.
- AC-2 With Stretch, the picture fills the whole layer box on the canvas,
  distorted to the box's proportions, with nothing letterboxed or cropped.
- AC-3 The print page draws a Stretch image identically (`object-fit: fill`),
  so the PDF matches the canvas.
- AC-4 A template saved with Stretch loads back with Stretch; the doc schema
  (`TagTemplateDocModel`) is the contract and still refuses an unknown fit
  value - the tag-template save route does not itself validate `doc` today.
- AC-5 Cover and Contain render exactly as before.

## Margin

- AC-6 A price badge's inspector shows a `Margin (mm)` group (top / right /
  bottom / left) above the existing `Padding (mm)` group.
- AC-7 Margin insets the callout (white box with its slanted corner) from the
  layer box; padding insets the price figure from the callout's own edge. The
  two are independent: margin 2mm + padding 1mm gives a callout 2mm in from
  the layer edge with the figure 1mm in from the callout edge.
- AC-8 Canvas and print page agree on both insets.
- AC-9 A badge saved before this change (padding set, no margin) renders
  pixel-identical to before, in the editor and in print.
- AC-10 Editing Margin or Padding on such a legacy badge does not visibly move
  the badge at the moment of the first edit: the stored padding becomes the
  margin and padding restarts at 0.
- AC-11 Text layers keep Padding only.
- AC-12 No migration, no new table, no new permission. Inspector usable at
  375px and 1280px.

## Currency

- AC-13 A price badge's inspector has a `Show currency` checkbox, on by default.
- AC-14 Unchecked, the badge reads `760` instead of `RM 760` on the canvas and
  on the print page; the promo variant drops `RM` from both lines the same way.
- AC-15 A badge saved before this change still shows `RM`.
- AC-16 A template saved with the checkbox off loads back with it off.
