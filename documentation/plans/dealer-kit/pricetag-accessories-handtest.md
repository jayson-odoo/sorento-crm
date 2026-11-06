crew-handtest: PRICETAG-ACCESSORIES (round 6: replaces round 5; the box is no longer hard coded: picture above or left of text, header shown / hidden / on the border, frame on/off, "+" badge off by default, header, name and spec styled like any tag text)

## URL
crew test copy

## Setup
- The crew-migration block on this PR is already applied (crew pass on 255623ba0).
- Crew has run the seed on the test copy (crew runs every command; the owner runs none): `cd sorento_crm_backend && venv/bin/python scripts/seed_accessories_handtest.py --apply` (dev only, a second run changes nothing). It created, under company SRT:
  - SRTKS7061-BL "Kitchen sink with 1 tap (hand test)": part SRTWT7202; Free items DRAINER, PULL OUT DRAINER.
  - SRTKS7061-BL "Kitchen sink with 2 taps (hand test)": parts SRTWT7202 + SRTKT1632SS; same Free items.
  - SRTWB7065 "Basin with tap (hand test)": part SRTWT7202; Free items = product SRTW5000.
  - Library accessory COLANDER with spec `390x300x140, Depth: 160mm` and a picture.
- After the session crew runs the cleanup: `... seed_accessories_handtest.py --cleanup --apply`.
- Product SRTKS7846's own "Accessories included" list is CHOPPING BOARD, COLANDER, DRAINER (set it in the app if it is not: product page > Overview > Accessories included).
- Steps 1-14: the E2E staff user (or the owner's own login). Steps 15-18 are for the OWNER (Impersonate); the same parity is proven automatically in `sorento_crm_frontend/components/dealer-kit/AccessoriesRenderParity.test.tsx`.
- The toast `Font Century Gothic Bold could not be loaded` is not part of this lane (see the crew-note on round 3); ignore it.

## Steps
1. Dealer Kit > Tag templates: open the 148 x 105 mm sink template (or any template about that size) and click "Add Accessories" in the toolbar. Keep the size it is added at (60 x 80 mm).
2. Click the eye of the template's product block (or "Preview the whole tag" on the frame) and pick product SRTKS7846.
3. Select the Accessories box and look at the inspector, top to bottom.
4. In the inspector, Item layout: click "Picture left of text"; then click "Picture above text" again.
5. Untick "Header on the border".
6. Tick "Header on the border" again, then change Header text to `FREE`.
7. Untick "Show header"; then tick it again.
8. Untick "Show frame"; then tick it again.
9. Tick "Show "+" badge"; then untick it.
10. In "Name text": pick another font in Font Family, set Font Size 10, click Italic, set the colour to red, set Align to Left.
11. In "Spec text": click Underline and set Align to Right.
12. Set Direction Horizontal and preview with combo SRTKS7061-BL "Kitchen sink with 2 taps (hand test)".
13. Clear the combo preview and preview the product block with SRTWT7202 (no accessories list).
14. Save the template, reopen it.
15. OWNER: User Management > Users, open a salesperson linked to customers, "Impersonate user", confirm.
16. OWNER, as that salesperson: Dealer Kit > Price tag requests > New, pick one of the salesperson's debtors, add two lines on this template: SRTKS7846 (no combo) and SRTWT7202 (no combo); submit; end the impersonation from the banner.
17. OWNER, as himself: open that request, click Design (request designer), look at both tags.
18. OWNER: open the request's print preview (the design preview on the request page, or Download PDF) and compare with step 17.

## Expected
1. A box like the printed Dealer Kit one: a rounded frame with `ACCESSORIES INCLUDED` sitting ON its top border (the border broken behind the text), NO "+" badge, and sample cards each with the picture on top and the name, then the spec, centred under it.
2. SRTKS7846's own list in that look: CHOPPING BOARD, COLANDER (with its picture and `390x300x140, Depth: 160mm`), DRAINER (`390x300x140, Depth: 160mm`), stacked, each picture above its bold centred name and centred spec. No "do not fit" warning.
3. Sections in order: Direction, Item layout ("Picture above text" selected), Picture size, Gap, Card fill; "Show frame" (ticked) with Box fill, Border colour, Border, Corner radius; "Show header" (ticked) with Header text `ACCESSORIES INCLUDED`, "Header on the border" (ticked), "Behind the header" colour, Header text style; Name text; Spec text (each with Font Family, Font Size, Bold / Italic / Underline / Strikethrough, Font Weight, colour, Align, Letter Spacing); "Show "+" badge" (unticked).
4. "Picture left of text": every card has its picture on the left and the name and spec left-aligned beside it; back to "Picture above text": picture on top, text centred.
5. The header moves inside the frame, under its top edge; the frame's top border is continuous.
6. The header is back on the border and reads `FREE`, whole, centred.
7. Unticked: no header at all and the cards move up; ticked: `FREE` is back.
8. Unticked: no border and no box fill, only the cards; ticked: the frame is back.
9. Ticked: a round "+" at the frame's top-left, its colour picker appears; unticked: gone.
10. Every card name shows in the chosen font, about 10 pt (smaller only if a long name needs it to fit, never "..."), italic, red, left-aligned.
11. Every spec line is underlined and right-aligned.
12. Both combo cards (DRAINER, PULL OUT DRAINER) side by side with the same styles; names whole.
13. SRTWT7202 has no list: only the dashed "Accessories" outline on the canvas (nothing would print).
14. Every setting from steps 4-12 is still there after reopening.
15. The app shows the impersonation banner with the salesperson's name.
16. The request is submitted with two lines; the banner ends.
17. Tag 1 (SRTKS7846): the styled box with CHOPPING BOARD, COLANDER, DRAINER. Tag 2 (SRTWT7202): only the dashed outline.
18. Tag 1 prints the same box: same frame, same header on the border, same cards in the same order, same fonts, sizes, colours and alignment as in step 17. Tag 2 prints no box at all.
