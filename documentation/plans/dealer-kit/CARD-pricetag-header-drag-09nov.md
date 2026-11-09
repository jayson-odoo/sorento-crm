# CARD: drag the accessories box header in the Tag Template designer (PRICETAG-HEADER-DRAG, 09/11/2026)

Status: Hand test (built on PR #2278, reviewer READY, browser pass PASS; all five answered 9 Nov ~14:25-14:28). Track: small fix (expected diff under 300
lines, frontend only, no migration, no RBAC change).

## Owner rulings (9 Nov ~14:25, verbatim: "1a, 2 it should be up to my arrangement, 3 i don't need
the setting la, 4 one per box, 5 ..."; Q5 (a) relayed by crew ~14:28). These win over H1-H8 below.

- Q1 (a): anywhere inside the box outline, with snap guides.
- Q2: **no automatic reflow.** Moving the header never moves the cards, the frame or the footer, and
  frees or reserves no space by itself; the owner arranges. Cards keep the spot the box layout gives
  them today (the default top band stays, so existing templates stay pixel-identical).
- Q3 (b): a moved header is plain header text where dropped: no border break, no background. The
  "Header on the border" setting and its "Behind the header" colour are hidden while the header has a
  stored position; unmoved headers keep the setting exactly as today.
- Q4 (a): one header per box.
- Q5 (a): the header position is part of the linked saved accessories template's design, like the
  header text. Moving it in one tag template updates the saved template and every tag template linked
  to it; Detach keeps a one-off. In the request designer (detach mode) a move detaches the box first,
  as any other design edit does there.
- Clicking the header selects its box (the Header controls are in that box's inspector). No scroll
  jump is added.

Owner 9 Nov ~13:55 MYT, on an accessory card ("FREE" header, dark green rounded border, picture,
SRTW5000, name, "LP: RM 68"): "I am okay with editing the FREE but I want to drag and place it at
other places".

## What exists today (measured on origin/main 38c71a4d)

- The header is box data: `headerText`, `headerFontSize`, `showHeader`, `headerOnBorder`,
  `headerBackground`, `headerStyle` (`lib/dealer-kit/tag-template-types.ts:380-393`, default
  'ACCESSORIES INCLUDED' at :1182). It has NO position of its own.
- Its spot is computed, never stored: `accessoryChrome` (`lib/dealer-kit/accessory-box.ts:395-441`)
  puts it centred on the top border (on border) or in a band under the top edge (inside), and
  shrinks the text to fit the box width. Cards always start under that band
  (`accessory-card.ts:96-98`, `accessory-box.ts:343-347`).
- ONE function feeds every render: the designer canvas (`KonvaTagLayer.tsx:1421-1446` and the
  legacy path :1257-1283), the print sheet / PDF (`TagSheetRenderer.tsx:1416`) and the accessory
  template preview (`AccessoryTemplatePreview.tsx:38`) all draw `box.header` from it. A position
  stored on the box and applied inside `accessoryChrome` therefore prints where the designer shows
  it, with no second copy of the rule.
- Clicking anywhere on the box (header included) selects and drags the whole box. The header text
  is edited in Inspector "Header text" (`InspectorPanel.tsx`, hidden while a card element is
  selected). Inside "Edit card" only card elements move (`AccessoryEditOverlay.tsx:105`).
- A card can already carry its own fixed text ("Text" tool in Edit card, V6 "or fixed text"), so a
  "FREE" on every card is possible today without this lane.
- Shared accessories template (V4): everything except `kind`, `subjectSlot`, `subjectPart`,
  `presetId` is the linked design (`accessory-card.ts:576`), so a new header field links by default.

## Proposed rules

H1. **The header becomes a draggable piece of its box.** With the box selected, pressing on the
    header text drags the HEADER, not the box; pressing anywhere else on the box still drags the
    box. Clicking the header selects the box and scrolls the Inspector to the Header section
    (Header text, size, on border, show). Snapping guides as for card elements: box left / centre
    / right, top border, bottom border.
H2. **Where it may go: anywhere inside the box's outline** (Q1). It moves with the box, and it never
    leaves the box. A box that closes up (fewer cards) keeps the header inside: it is pulled in to
    the box's last edge rather than printing outside it.
H3. SUPERSEDED by the Q2 ruling (no reflow). Proposed was: **Cards make room** (Q2): while the header is in its default top spot, cards start under it as
    today. Once it is moved, cards start from the box's top padding and the header draws on top of
    whatever is under it (the designer shows the overlap; the user arranges).
H4. SUPERSEDED by the Q3 ruling (moved = plain text). Proposed was: **On the border** (Q3): "On border" keeps its meaning wherever the header sits: the header paints
    its background (`headerBackground`) behind its text, so placed on the top or bottom border it
    breaks the line there. The frame's top no longer drops by half a header once the header is moved
    off the top.
H5. **One header per box** (Q4), as today. A header on every card is the Edit card "Text" tool.
H6. **Existing templates unchanged**: no stored position = today's computed spot, pixel for pixel. No
    migration (the box props are JSON on the template). Inspector gains one link, **Reset header
    position**, shown only once the header has been moved.
H7. **Shared accessories template** (Q5): the header position is part of the linked design, like the
    header text: moving it in one tag template moves it in every tag template linked to that saved
    accessories template (the existing "Changes here update N tag templates" banner applies).
    Detach keeps it.
H8. **Render parity**: the stored position is applied in `accessoryChrome`, so canvas, request
    preview, print sheet and PDF place the header at the same millimetres. Tested: a moved header's
    left/top on the print sheet equals the canvas's.

Data: one optional box field `headerPos?: { x_mm: number; y_mm: number }`, the header band's
top-left corner relative to the box's top-left, in mm. Absent = H6.

## Examples (crew cannot reach the dev DB from the cloud sandbox; names from the owner's screenshots
in `CARD-pricetag-accessory-designer-07nov.md`, to confirm on the dev copy)

1. **Wash basin combo SRTWB7065 + SRTWT7202, "FREE" box** (the owner's screenshot today: dark green
   rounded border, SRTW5000, "LP: RM 68"): drag "FREE" from the top border to the bottom border,
   centred. Prints breaking the bottom border; the card moves up into the freed top band.
2. **SRTKS7846, vertical "ACCESSORIES INCLUDED"**, header on the top border: drag it to the top-left
   corner (snaps to box left + top border). Prints at the same mm on the PDF.
3. **SRTKS7061-BL horizontal box from #2211, never edited**: opens and prints exactly as before (H6).
4. **Saved accessories template "FREE vertical"** used in two tag templates: move the header in one;
   the banner warns "Changes here update 2 tag templates"; the second template shows it moved (H7).
5. **Box closes up**: header dragged near the bottom of a 3-card box, then the list has only 1
   accessory: the box closes up and the header is pulled in to the new bottom edge, still inside.

## Questions (crew-ask, at most 5, each with a recommendation)

Q1. Where may the header go?
    (a) **Anywhere inside the box's outline, with snap guides** (recommended: "other places" without
        a fixed menu, and it travels with the box and its saved template).
    (b) Anywhere on the tag, even outside the box (it becomes its own element; moving the box no
        longer moves it).
    (c) Only fixed spots: top / bottom border x left / centre / right.
Q2. When the header is moved away from the top, what fills the space it left?
    (a) **Cards move up into it** (recommended: no empty band; the header then may overlap a card,
        which the designer shows).
    (b) The band stays reserved, cards stay where they are.
Q3. "On border" once the header is moved:
    (a) **Keep the setting: it paints the header background behind the text wherever it sits, so on
        the bottom border it breaks that line** (recommended: one rule, nothing new to learn).
    (b) Moving the header turns "On border" off; it is plain text where you drop it.
Q4. One header per box or one per card?
    (a) **One per box, as today** (recommended: a per-card "FREE" is already the Edit card Text tool).
    (b) One per card, dragged inside the card in Edit card.
Q5. Saved accessories template (live link, V4): is the header position shared?
    (a) **Yes, part of the linked design like the header text** (recommended: it is how the box looks;
        Detach for a one-off).
    (b) No, per box like the box's own position and "Reads from".

## Mock

None: the answers add only drag + one "Reset header position" link to the existing inspector.
A mock follows only if an answer adds new controls (e.g. Q1 (c) spot picker, Q4 (b)).
