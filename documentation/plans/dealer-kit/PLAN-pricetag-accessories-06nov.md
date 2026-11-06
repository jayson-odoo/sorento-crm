# PLAN: price tag "Accessories included" (PRICETAG-ACCESSORIES, 6 Nov)

Status: Plan. Measured; behaviour card (`CARD-pricetag-accessories-06nov.md`) goes to
the owner (crew-ask on the PR), waiting for Q1-Q5 before the Lavish mock. Track: full (expected migration + new master data).

Owner ask (6 Nov ~09:45 MYT): price tag 148 x 105 mm for sink SRTKS7846 carries a rounded
"ACCESSORIES INCLUDED" box with 3 mini-cards (picture + name + spec): CHOPPING BOARD, COLANDER
390x300x140 Depth 160mm, DRAINER 390x300x140 Depth 160mm. These are not product codes. Today the
designer can only paste the whole box as a static asset.

Target (crew proposal, owner said go; details confirmed in the card):
1. Accessory master data (picture, name, short spec) attached as an ordered list to a product
   (combo inherits from its main product unless overridden: to confirm).
2. One "Accessories included" designer layer: styled frame + header + optional badge, repeating a
   mini-card per accessory; closes up when fewer; "N of M do not fit" warning; hidden when none.
3. One render function for canvas, preview and print.

Details follow as the lane is measured.
