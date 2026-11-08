# UAC: accessory card layout in the Tag Template designer (PRICETAG-ACCESSORY-DESIGNER, 07/11/2026)

Plan: `PLAN-pricetag-accessory-designer-07nov.md`. Card: `CARD-pricetag-accessory-designer-07nov.md`.

1. An Accessories box saved before this lane prints exactly as before on canvas, request preview and print
   until somebody clicks Edit card or applies a saved template to it.
2. Selecting a box and double-clicking it (or Enter, or "Edit card") enters card editing mode on the same
   canvas: the toolbar shows Picture, Text, Colour dots, Shape, Done; card 1 is editable, the others are faded
   and follow every change. Done, Escape or a click outside leaves.
3. "Colour dots" adds a dots element to card 1; it can be dragged and resized; on a tag the colander card
   shows Black and Grey dots and the chopping board card shows none.
4. A slot whose field is empty for an accessory does not print, and a slot directly under it moves up; every
   card in a box keeps the same height.
5. The box flows any number of cards: when they do not fit, all cards shrink by the same factor down to 70%;
   below that only whole cards print and "N of M accessories do not fit this box" shows on the canvas, in the
   inspector and as the print toast. No card is ever cut.
6. Footer note: "Footer note: Show" then "Edit footer" lets the user place a text and a colour dots element
   freely; the footer dots show all colours in the box unless picked by hand.
7. "Save as accessories template" names and stores the box design; the Accessories toolbar menu in any tag
   template lists it and inserts a linked box.
8. Saving a change to a linked box updates every tag template (drafts, published versions, request tag sheets)
   using that saved template; Detach stops a box following.
9. Dealer Kit > Accessory Templates lists saved templates (preview, name, used in, updated dd/mm/yyyy, by),
   renames them, and deletes with the deferred countdown; deleting one keeps every box's last design.
10. An accessory holds several pictures, each optionally with a colour; spec lines and remark are rich text.
11. A product or combo list entry can choose the picture and override name, spec and remark for that list only;
    the tag prints the override.
12. A product used as an entry prints its Price tag description in a Spec slot unless overridden.
13. Usable at 375 px and 1280 px (management page, accessory modal, entry dialog).
