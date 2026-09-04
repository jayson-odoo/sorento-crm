# Seed assets for the eight starter tag templates

Cropped from `Sorento Pricetag Template.pdf` (marketing's Illustrator originals) at 300-600 dpi.
`manifest.json` lists each file with the `dealer_kit.asset` kind and tags the seed script uses.
Files prefixed `reference_` and `brand_header_band_sample` are visual references for the seed
templates' price badge and header band; they are not uploaded as assets.

Connectors (`OR`, `+`) are drawn by the "alternatives row" preset as shape + text layers, so
they carry no asset here.

## Geometry and fonts

`pdf-geometry.json` holds every text span (text, font, pt size, colour, mm box), image box and
filled rectangle per page, in mm on A4. The seed script lays the eight templates out from it.
Tag boxes: sink families 125.9 x 88.6 mm (3-up), WC families 131.6 x 92.1 mm (3-up),
furniture set 94.0 x 134.2 mm (2 x 2). Brand green `#445235`, price red `#ea2329`.

Fonts the originals use: Century Gothic (wordmark, body), Bebas Neue Bold (codes, big numbers),
Myriad Pro, Helvetica, TheBoldFont. Century Gothic and Myriad Pro are licensed: marketing uploads
them as `kind = font` assets and the templates pick them up by family name. The seed uses free
stand-ins so it renders everywhere: Bebas Neue (Google) for codes and prices, Jost (Google,
Futura class) for the wordmark and body.
