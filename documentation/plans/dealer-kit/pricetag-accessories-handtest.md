crew-handtest: PRICETAG-ACCESSORIES (round 3: replaces round 2; default box fits 3 cards, header shrinks instead of truncating, request created as salesperson-a, cleanup at the end)

## URL
crew test copy

## Setup
- The crew-migration block on this PR is already applied (crew pass on 255623ba0).
- Seed the hand-test combos on the test copy's DB (dev only; it refuses outside a dev ENVIRONMENT, and a second run changes nothing):
  `cd sorento_crm_backend && venv/bin/python scripts/seed_accessories_handtest.py --apply`
  It creates, under company SRT:
  - SRTKS7061-BL "Kitchen sink with 1 tap (hand test)": part SRTWT7202; Free items DRAINER, PULL OUT DRAINER.
  - SRTKS7061-BL "Kitchen sink with 2 taps (hand test)": parts SRTWT7202 + SRTKT1632SS; same Free items.
  - SRTWB7065 "Basin with tap (hand test)": part SRTWT7202; Free items = product SRTW5000.
  If it prints `missing products`, rerun with `--taps SRTWT7202,<any other tap code on dev>`.
- In-app instead (about 2 minutes, if you prefer): on SRTKS7061-BL > Combos, add combo "Kitchen sink with 1 tap (hand test)" with part SRTWT7202, then "Kitchen sink with 2 taps (hand test)" with SRTWT7202 and a second tap. On SRTWB7065 > Combos, add "Basin with tap (hand test)" with part SRTWT7202. Steps 9-11 below fill their Free items.
- Sign in as a user who can edit products and edit Dealer Kit tag templates (the E2E staff user) for every step except 19.
- Step 19 creates the request as the dev salesperson login `salesperson-a`: "New price tag request" is the salesperson's own form and needs a salesperson linked to debtors; the E2E admin has none, so it gets 403 on `debtors-for-agent`.
- The toast `Font Century Gothic Bold could not be loaded` is not part of this lane (see the crew-note on this round); ignore it.

## Steps
1. From the sidebar, open Master Data > Products > Accessories.
2. Click "Add accessory", type Name `drainer` (lower case), Save.
3. Open COLANDER, click "Upload picture", choose any jpg, close and reopen COLANDER.
4. Open COLANDER again, click Replace and choose a different jpg; then click Remove; then upload the first jpg again.
5. Open product SRTKS7846, tab Overview, section "Accessories included": add CHOPPING BOARD, COLANDER, DRAINER, in that order.
6. Drag DRAINER above COLANDER, reload the page.
7. Drag DRAINER back below COLANDER, reload the page.
8. Open product SRTKS7061-BL, tab Overview, and look at "Accessories included".
9. In its Combos, open "Kitchen sink with 1 tap (hand test)" and look at "Free items" (set it to DRAINER, PULL OUT DRAINER if you created the combo in the app).
10. Do the same on "Kitchen sink with 2 taps (hand test)".
11. Open SRTWB7065 > "Basin with tap (hand test)" > Free items; if empty, click Add product and pick SRTW5000. Then try to add product SRTWT7202.
12. Back in Master Data > Products > Accessories, open DRAINER's row menu, click Delete and wait 10 seconds.
13. Dealer Kit > Tag templates: open the 148 x 105 mm sink template (or any template about that size), click "Add Accessories" in the toolbar and keep the box at the size it is added at (60 x 60 mm). Then drag its right edge in to 45 mm wide and back to 60.
14. Preview the template with product SRTKS7846.
15. Preview with combo SRTKS7061-BL "Kitchen sink with 1 tap (hand test)", set Header text `FREE`.
16. Set Direction Horizontal, untick the "+" badge, preview with "Kitchen sink with 2 taps (hand test)".
17. Preview with product SRTKS7061-BL alone (no combo).
18. Preview with SRTWB7065 "Basin with tap (hand test)". Save the template.
19. Sign in as `salesperson-a`, open Dealer Kit > Price tag requests > New, pick any debtor, add three lines on this template: SRTKS7846 (no combo), SRTKS7061-BL with combo "Kitchen sink with 1 tap (hand test)", and SRTKS7061-BL with no combo; submit. Sign back in as the staff user, open that request and click Design (request designer).
20. In the request designer look at each tag's Accessories box.
21. Open the print preview of the same request and compare each tag with step 20.
22. Cleanup (dev copy): `cd sorento_crm_backend && venv/bin/python scripts/seed_accessories_handtest.py --cleanup --apply`.

## Expected
1. The Accessories list shows the 23 migrated rows plus any you added, with columns Picture, Name, Spec, Used on.
2. Refused with `An accessory called "drainer" already exists`; no second DRAINER row.
3. COLANDER shows the picture thumbnail in the modal and in the list's Picture column.
4. Replace swaps the thumbnail; Remove shows "No picture" and the list column empties; the re-upload shows it again.
5. The section lists CHOPPING BOARD, COLANDER (with picture), DRAINER in that order, each with its spec.
6. After the reload: CHOPPING BOARD, DRAINER, COLANDER.
7. After the reload: CHOPPING BOARD, COLANDER, DRAINER.
8. "Accessories included" shows "No accessories" unless you added some yourself (the product list is independent of its combos).
9. Free items: DRAINER (`390x300x140, Depth: 160mm`), then PULL OUT DRAINER.
10. Same two entries, same order.
11. SRTW5000 shows in bold with `Popup Waste 80mm (w/o Overflow) Brass`, `LP: RM 68` and its photo. Adding SRTWT7202 is refused with the toast `This product is already a part of this combo`, and the list stays SRTW5000 only.
12. The button counts down with a Cancel; when it lapses the delete is refused with a message starting `Used on` (it names how many products and combos list it), and DRAINER stays.
13. A 60 x 60 mm rounded box with a round orange "+" at its top-left, the header `ACCESSORIES INCLUDED` fully visible and centred (first letter not under the badge), 2 sample cards. At 45 mm wide the header is still the whole text, just smaller; it never ends in "...".
14. All three cards fit at the default size, stacked: CHOPPING BOARD; COLANDER with picture and `390x300x140, Depth: 160mm`; DRAINER with `390x300x140, Depth: 160mm`. No "do not fit" warning.
15. Two cards, DRAINER and PULL OUT DRAINER, under the header `FREE` (whole word visible beside the badge).
16. Both cards side by side in the default-size box (no "do not fit" warning), no badge, header uses the full width, box closes up from the right.
17. No cards: the canvas shows only the dashed "Accessories" outline (nothing would print).
18. One card: SRTW5000 / Popup Waste 80mm (w/o Overflow) Brass / LP: RM 68, with the product photo.
19. The request is created by salesperson-a and opens in Design for the staff user with three tags.
20. Tag 1 (SRTKS7846, no combo): CHOPPING BOARD, COLANDER, DRAINER. Tag 2 (1-tap combo): DRAINER, PULL OUT DRAINER. Tag 3 (SRTKS7061-BL, no combo, empty product list): only the dashed outline.
21. Print preview: tags 1 and 2 show the same cards, same order, same box size and spacing as in step 20; tag 3 prints no box at all (no frame, no header, no badge).
22. It lists and deletes the three "(hand test)" combos and the unused `crew-pass-...` accessories (a used one is listed as kept); DRAINER, COLANDER and the other library rows stay.
