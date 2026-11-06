crew-handtest: PRICETAG-ACCESSORIES (round 5: replaces round 4; a previewed PRODUCT now shows its own list, crew runs every command, COLANDER is seeded with a picture)

## URL
crew test copy

## Setup
- The crew-migration block on this PR is already applied (crew pass on 255623ba0).
- Crew has run the seed on the test copy (crew runs every command; the owner runs none): `cd sorento_crm_backend && venv/bin/python scripts/seed_accessories_handtest.py --apply` (dev only, a second run changes nothing). It created, under company SRT:
  - SRTKS7061-BL "Kitchen sink with 1 tap (hand test)": part SRTWT7202; Free items DRAINER, PULL OUT DRAINER.
  - SRTKS7061-BL "Kitchen sink with 2 taps (hand test)": parts SRTWT7202 + SRTKT1632SS; same Free items.
  - SRTWB7065 "Basin with tap (hand test)": part SRTWT7202; Free items = product SRTW5000.
  - Library accessory COLANDER with spec `390x300x140, Depth: 160mm` and a picture (if the copy cannot store pictures the seed says so; then step 3 uploads one).
- After the session crew runs the cleanup: `... seed_accessories_handtest.py --cleanup --apply` (removes the three "(hand test)" combos and unused `crew-pass-...` accessories).
- Steps 1-20: the E2E staff user (or the owner's own login).
- Steps 21-26 (a real request in the request designer and the print preview) are for the OWNER: his own login can Impersonate a salesperson; crew helpers have neither a salesperson password nor Impersonate. The same parity is proven automatically in `sorento_crm_frontend/components/dealer-kit/AccessoriesRenderParity.test.tsx` (one doc and one request row through the request designer's canvas, the print preview and the print page).
- The toast `Font Century Gothic Bold could not be loaded` is not part of this lane (see the crew-note on round 3); ignore it.

## Steps
1. From the sidebar, open Master Data > Products > Accessories.
2. Click "Add accessory", type Name `drainer` (lower case), Save.
3. Open COLANDER, click "Upload picture" and choose any jpg; close and reopen COLANDER.
4. Open COLANDER, click Replace and choose a different jpg.
5. Click Remove, then upload the first jpg again.
6. Open product SRTKS7846, tab Overview, section "Accessories included", and add CHOPPING BOARD, COLANDER, DRAINER in that order.
7. Drag DRAINER above COLANDER and reload the page.
8. Drag DRAINER back below COLANDER and reload the page.
9. Open product SRTWT7202 (the tap), tab Overview, and look at "Accessories included".
10. Open SRTKS7061-BL > Combos > "Kitchen sink with 1 tap (hand test)" and look at "Free items".
11. Do the same on "Kitchen sink with 2 taps (hand test)".
12. Open SRTWB7065 > "Basin with tap (hand test)" > Free items, then try to add product SRTWT7202.
13. Back in Master Data > Products > Accessories, open DRAINER's row menu, click Delete and wait 10 seconds.
14. Dealer Kit > Tag templates: open the 148 x 105 mm sink template (or any template about that size) and click "Add Accessories" in the toolbar. Keep the box at the size it is added at (60 x 60 mm).
15. Drag the box's right edge in to 45 mm wide, then back to 60.
16. Click the eye of the template's product block (or "Preview the whole tag" on the frame) and pick product SRTKS7846.
17. Preview with combo SRTKS7061-BL "Kitchen sink with 1 tap (hand test)" and set Header text `FREE`.
18. Set Direction Horizontal, untick the "+" badge, and preview with "Kitchen sink with 2 taps (hand test)".
19. Clear the combo preview, then click the product block's eye (or "Preview the whole tag") and pick product SRTWT7202.
20. Preview with combo SRTWB7065 "Basin with tap (hand test)", then Save the template.
21. OWNER: User Management > Users, open a salesperson linked to customers, row or page action "Impersonate user", confirm.
22. OWNER, as that salesperson: Dealer Kit > Price tag requests > New, pick one of the salesperson's debtors, add three lines on this template: SRTKS7846 (no combo), SRTKS7061-BL with combo "Kitchen sink with 1 tap (hand test)", and SRTWT7202 (no combo); submit. End the impersonation from the banner.
23. OWNER, back as himself: open that request from Dealer Kit > Price tag requests and click Design (request designer); look at each tag's Accessories box.
24. OWNER: open the request's print preview (the design preview on the request page, or Download PDF) and compare each tag with step 23.

## Expected
1. The Accessories list shows the 23 migrated rows plus any you added, with columns Picture, Name, Spec, Used on.
2. Refused with `An accessory called "drainer" already exists`; no second DRAINER row.
3. COLANDER shows the picture thumbnail in the modal and in the list's Picture column.
4. Replace swaps the thumbnail.
5. Remove shows "No picture"; the re-upload shows the picture again.
6. The section lists CHOPPING BOARD, COLANDER (with picture), DRAINER in that order, each with its spec.
7. After the reload: CHOPPING BOARD, DRAINER, COLANDER.
8. After the reload: CHOPPING BOARD, COLANDER, DRAINER.
9. "Accessories included" shows the empty state "No accessories".
10. Free items: DRAINER (`390x300x140, Depth: 160mm`), then PULL OUT DRAINER.
11. The same two entries, same order.
12. SRTW5000 shows in bold with `Popup Waste 80mm (w/o Overflow) Brass`, `LP: RM 68` and its photo; adding SRTWT7202 is refused with the toast `This product is already a part of this combo`.
13. The button counts down with a Cancel; when it lapses the delete is refused with a message starting `Used on`, and DRAINER stays.
14. A 60 x 60 mm rounded box: round orange "+" at its top-left, header `ACCESSORIES INCLUDED` fully visible and centred (first letter not under the badge), 2 sample cards.
15. At 45 mm wide the header is still the whole text, just smaller (never "..."); back at 60 mm it is full size.
16. The box shows SRTKS7846's OWN list (step 6), not sample cards: all three cards fit at the default size, stacked: CHOPPING BOARD; COLANDER with its picture and `390x300x140, Depth: 160mm`; DRAINER with `390x300x140, Depth: 160mm`. No "do not fit" warning.
17. Two cards, DRAINER and PULL OUT DRAINER, under the header `FREE`.
18. Both cards side by side in the default-size box (no "do not fit" warning), no badge, box closes up from the right. Every card name is whole: `PULL OUT DRAINER` prints in full, in a smaller size if needed, never `PULL OUT DR...`.
19. SRTWT7202's own list is empty, so the box shows no cards, only its dashed "Accessories" outline (never the sample cards; nothing would print).
20. One card: SRTW5000 / Popup Waste 80mm (w/o Overflow) Brass / LP: RM 68, with the product photo.
21. The app shows the impersonation banner with the salesperson's name.
22. The request is submitted with three lines; the banner ends.
23. Three tags: tag 1 (SRTKS7846): CHOPPING BOARD, COLANDER, DRAINER; tag 2 (1-tap combo): DRAINER, PULL OUT DRAINER under the template's header; tag 3 (SRTWT7202): only the dashed outline.
24. Tags 1 and 2 show the same cards, same order, same box size, header and name sizes as in step 23; tag 3 prints no box at all (no frame, no header, no badge).
