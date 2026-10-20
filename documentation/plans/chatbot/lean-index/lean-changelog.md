# LEAN-INDEX parser candidate: changelog against v88

Base: `chatbot_semantic_parser` v88 (id 4646e9a2-696e-4461-955e-5722b916b763), the consolidated template.
Candidate: `parser-lean.txt` (the template text plus one trailing newline, the same convention as the v88 copy
taken with `psql -t`; psql's backquote strips that one newline when `explore-data.sql` reads the file).
Every `{{variable}}` is kept (14, same set). Kept untouched: grammar particles (R-X-04, R-P3-09), FLYER
(R-P3-15), KNOWN BRANDS (R-P2-09), output and routing rules.

Size (template text): v77 142,657 chars / 35,651 tokens; v88 70,537 / 18,347; lean 70,453 / 18,318
(o200k_base).

## Edits (old -> new)

1. Line 157, R-P2-06 FILE, (a) no implied-photo phrase and (c) spec sheet is not the drawing item:
   - old: `a drawing, TD, CAD or spec sheet is the item that holds drawings; a photo, image, picture, "how does it
     look" or "show me" the item that holds photos`
   - new: `a drawing, TD or CAD is the item that holds drawings; a photo, image or picture the item that holds
     photos`
   - The parenthetical after it is kept: `(a "show me" over one offered list is that pick, see R-P1-05; "show me
     everything" widens the ask, see R-P3-09)`. It says where "show me" is NOT a photo ask, which still applies
     once "show me" is an alias word on the photo line.
2. Line 190, R-P2-12 ACCESS, (b) no hard-coded brand name:
   - old: `A brand with dealer or office is that brand's level ("sorento" + "dealer" -> Sorento Dealer);`
   - new: `A brand with dealer or office is that brand's dealer or office level;`
   - `{{access_levels}}` renders `contact_access_types.name` (data: e.g. "Sorento Dealer", "Mocha Office"); no
     other literal brand is near it.
3. Line 200, R-P3-01 product_attachment, (a) no implied-photo phrase:
   - old: `a file of one product: photos and how it looks, drawings,`
   - new: `a file of one product: photos, drawings,`

## Checked, not edited ("spec")

- Line 162: `A bare "spec" beside a code asks for the product's spec list ... even when a Words line holds "Spec"
  (see R-P3-05); a spec sheet, drawing or PDF the message asks for is a file.` Names spec sheet and drawing as
  two separate files; it does not equate them.
- Line 200: `a spec sheet` is listed beside `drawings` as its own file.
- Lines 133, 140, 231: spec values and the bare-spec attribute rule; no file mapping.
