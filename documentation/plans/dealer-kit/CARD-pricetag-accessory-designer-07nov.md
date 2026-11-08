# CARD: accessory card layout, designed inside the Tag Template designer (PRICETAG-ACCESSORY-DESIGNER, 07/11/2026)

Behaviour card v2. Owner 7 Nov ~21:35 + ~21:45, rulings ~21:55. Mocks: v1 `pricetag-accessory-designer-mock.html`, v2 `pricetag-accessory-designer-mock-v2.html` (same
folder). **No build before the owner OKs the mock.** Builds on PRICETAG-ACCESSORIES (#2211, card
`CARD-pricetag-accessories-06nov.md`, rulings Q1-Q5 + A13-A16 stand) and coordinates with
PRICETAG-ACC-LABELS (#2235, labels + designer drop warning: this lane reuses that warning, does not
redo it).

## Owner rulings on v1 (7 Nov ~21:55). These win over the v1 rules below.

- Q1 (b) **live link**: a saved accessories template is linked, not copied. Saving it updates every
  box that uses it, in every tag template ("that's how it behaves now": a request line already
  prints with its tag template live, `price_tag_request_lines.tag_template_id`,
  `app/models/price_tag.py:246`). Each box has **Detach** to break the link and keep a private copy.
- Q2 (a), crew's call: shrink together to a 70% minimum, then whole cards only + the warning.
- Q3 (a): the picture chosen on the list entry, default the first; dots show all colours.
- Q4: **nothing fixed**. Colour dots are a freely placed element (move, resize, hide) on the card
  AND in the footer; no fixed spot. The footer dots show the box's colours (de-duplicated) unless
  set by hand on that element.
- Q5 (b) **both**: the designer's Accessories menu AND a management page
  `/dealer-kit/accessory-templates`, like Dealer Kit > Tag Sizes.
- Owner on mock v1: "so where do i design the drag and drop of the accessories, like how do I put
  the colour circles in" / "where do I design the layout of the accesories box?". Mock v2 answers
  both click by click (`pricetag-accessory-designer-mock-v2.html`).

### Rules v2 (replace D6-D8 and F1-F2 where they differ)

V1. **Card editing mode** (the answer to "where do I design"): select the box, then double-click it
    or click **Edit card** in the inspector. The toolbar swaps to `Editing card: Picture | Text |
    Colour dots | Shape | Done`; card 1 is outlined, the others fade and follow live. Click a tool
    to drop that element in the middle of card 1, drag it anywhere inside the card, resize it by its
    corner handles, hide it from the inspector (eye) or delete it (Delete key). Snapping guides as
    on the tag. **Done**, Escape or a click outside the box leaves.
V2. **Colour dots element**: inspector sets dot size, gap, row or column, outline, and which colours
    (this accessory's, the default; or hand-picked). Resizing the element by its handle resizes the
    dots.
V3. **Box layout** (box selected, inspector): Header (text, on border, show), Direction (vertical /
    horizontal), Gap between cards, Inner margin, Shrink to fit (on; minimum 70%), Frame (fill,
    border, corners), Footer (show). **Edit footer** (or double-click the footer) enters footer
    editing mode, same tools minus Picture; the footer note and its dots are placed freely there.
V4. **Live link**: a box made from a saved accessories template shows `Linked: <name> (used in N
    tag templates)`. Editing its card, footer or box layout in place edits the saved template: a
    banner says "Changes here update N tag templates" before the first change sticks (Undo works).
    Position, size and "Reads from" stay per box and never link. **Detach** keeps the current design
    as this box's own copy; it no longer follows.
V5. **Management page** `/dealer-kit/accessory-templates` (Dealer Kit sidebar, beside Tag Sizes):
    DataGrid with thumbnail, name, used in (N tag templates, click to list them), updated
    (dd/mm/yyyy), by. Rename in a modal, deferred-action delete (10 s countdown, no confirm). Deleting
    one detaches every box using it (each keeps its last design). No design editing on the page:
    the design is always edited in the Tag Template designer. Permission `dealer_kit.tag_templates.view`
    / `.manage`, as Tag Sizes.

### Rules v3 (owner on mock v2: "some got the dot, some don't have, some product / combo has 2, some have 3")

Mock v3: `pricetag-accessory-designer-mock-v3.html`.

V6. **One card layout per box, applied to EVERY accessory** in whatever list prints there (the
    tag's product list or combo list, `accessoriesOf`). You never design "the colander card": you
    design one card of slots, and each slot is bound to a field: Picture, Name, Code, Spec lines,
    Remark, Price (LP) or Colour dots (or fixed text).
V7. **A slot whose field is empty for that accessory does not print** (chopping board: no spec, no
    colours, so no spec lines and no dots; colander: everything). A slot directly under it in the
    same column moves up into its space, so no hole is left. No grey placeholder ever prints.
V8. **The box flows 1, 2, 3 or N cards by itself**: stack or row, then shrink together to 70%, then
    whole cards only + the warning (V3, Q2). The same template prints SRTKS7846 (3 cards) and the
    SRTKS7061-BL combo with 1 tap (2 cards) with nothing redesigned.
V9. **Per-accessory own layout: not now** (proposed). Different wording or picture for one product
    is the list-entry pencil (P1); an empty field already hides its slot. Built when the first real
    tag needs one accessory to look different.

Open (v3 crew-ask): Q-v3-1 card height when one accessory shows less: (a) **every card in a box the
same height** (recommended, rows line up) / (b) each card as tall as its own content (vertical
only). Q-v3-2 per-accessory own layout: (a) **not now** (recommended) / (b) build now.

## Owner asks (verbatim intent)

- The printed Dealer Kit look: "INCLUDED:" / "ACCESSORIES INCLUDED" / "FREE" box, header on the
  top border; per item a picture, a name, spec lines (COLANDER "390x200x140 / Depth: 160mm"), colour
  dots (black / grey) beside the picture; a box note "* Accessories Color Follow Kitchen Sink Color"
  with the dots.
- COLANDER has several pictures (one per colour) and sometimes a remark; descriptions differ per use.
- SRTW5000 pop-up waste used FREE on combo SRTWB7065 + SRTWT7202 needs a tag-specific description.
- A box that is too small today drops items silently; SRTKS7846's box cut COLANDER in half.
- 21:35 "we have the same designer in the tag template, don't want to go to too many places to design".
- 21:45 "similar to tag size or price tag designer la, after I save ady i can save it as like an
  accessories template to be reused, but the key idea is i don't want to navigate to multiple
  designer canvas".

## What exists today (measured on origin/main 56b5458b)

- Data: `Accessory` = name String(100), spec String(200 in the model, 1000 in the schema), ONE
  picture `image_attachment_id` (`sorento_crm_backend/app/models/accessory.py:39-60`). Lists
  `ProductAccessory` (:65) and `ProductComboAccessory` (:102): an entry is an accessory OR a
  catalogue product (CHECK :93 / :127), plus `sort_order`. **No per-entry field** (no picture choice,
  no text override). No colour anywhere: `products` has no colour column (`app/models/product.py`),
  only `price_tag_description` (Text, rich, :325).
- Product entry prints code, description-else-name, "LP: RM 68"
  (`sorento_crm_frontend/lib/dealer-kit/accessory-box.ts:265-273`), read live.
- Box = layer kind `accessories` (`lib/dealer-kit/tag-template-types.ts:371-414`): direction,
  picture above or left of text (`itemLayout`), header on border, header/name/spec text styles,
  fill, stroke, radius, picture size, gap, card width. **The card is fixed code**: one picture, one
  name line, up to 2 more lines (`accessoryCardInner`, `accessory-box.ts:418-455`; `cardSize`
  :290-302). Nothing can be moved inside a card, nothing added.
- Fit: whole cards only; extra cards dropped (`accessoryBoxLayout` :319-410); the inspector warns
  (`InspectorPanel.tsx:2209`), the canvas warning arrives with #2235. Text inside a card shrinks
  by an ESTIMATE (`fitLinePt`, :57), so a long name or 3 spec lines can still overrun the card
  (the owner's half COLANDER).
- Designer already has, and this lane reuses: groups you enter by double-click / Enter
  (`TagCanvasEditor.tsx:1461-1485` `entered`, `enterSelectedGroup` :2084), text / image / shape
  layers and their inspectors (`InspectorPanel.tsx`), rich text runs (`lib/dealer-kit/rich-text.ts`,
  `InlineTextEditor.tsx`, `components/ui/rich-text-editor.tsx`), the saved-preset pattern for tag
  sizes (`dealer_kit.tag_size_preset`, `app/models/dealer_kit.py:907-935`; service
  `app/(protected)/dealer-kit/services/tagSizeService.ts`; "Save tag size" dialog
  `price-tag-requests/[id]/design/components/SaveAsSizeDialog.tsx`; picker with "Saved sizes" +
  delete in `dealer-kit/components/TagSizeControl.tsx`).

## Proposed rules

**Designing (all in the Tag Template designer, no new screen, no second canvas)**

D1. The Accessories box stays one layer. **Double-click it (or Enter, or "Edit card" in the
    inspector) to step inside**, exactly as you step into a group. Inside, the FIRST card becomes
    an editable frame on the same canvas; the other cards stay drawn, live, faded, and repeat every
    change. Escape or a click outside steps back out.
D2. Inside the card you place ordinary designer elements, freely, with the usual handles, snapping,
    arrange and inspector: **Picture**, **Text**, **Colour dots**, **Shape** (line, rounded box).
    Each Picture / Text says what it shows from the accessory: Picture, Name, Code, Spec lines,
    Remark, Price (LP), or fixed text. Text is rich (bold, colour, size, alignment per run), set with
    the same text controls a tag text layer uses.
D3. **One card layout per box; every card in that box uses it.** A card's design size is the size
    of the card frame you draw. Vertical boxes stack cards, horizontal boxes run them left to right
    (existing setting).
D4. The box itself keeps today's settings (fill, border, corner radius, header on the border,
    header text, show/hide header, "+" badge off by default) and gains a **footer**: an area under
    the cards you also step into and place Text / Colour dots in ("* Accessories Color Follow
    Kitchen Sink Color" + dots). Footer hidden by default.
D5. **Default card = today's look.** A box saved before this lane opens with a card layout built
    from its old settings (picture above or left of the text, name, spec, LP for a product), so it
    prints the same until somebody edits it (target: pixel-identical; tested on the seeded templates).
D6. **Save as accessories template.** In the box inspector (box level), "Save as accessories
    template" asks for a name (the "Save tag size" dialog). It stores the box design: frame, header,
    footer, direction, card layout and fit settings. NOT stored: position on the tag, "Reads from".
D7. **Use a saved one.** The toolbar's Accessories button opens a small menu: "Default box" plus
    "Saved accessories templates" (name + thumbnail), searchable. Picking one adds a box with that
    design to the current template. On an existing box, the inspector's "Accessories template"
    select applies one to it (keeps its position, size and "Reads from"). Either way you can still
    tweak it in place afterwards.
D8. Saved templates are renamed / deleted from that same menu (the Tag Size control's saved-size
    delete, deferred-action delete, no confirm). Name unique per company. Who: whoever may manage
    tag templates (`dealer_kit.tag_templates.manage`, the tag-size rule).

**Accessory data (Master Data > Products > Accessories, same modal)**

A1. **Pictures: several, ordered.** Each picture may carry a colour (name + swatch from a short
    palette: Black, Grey, Silver, White, Gold, Gunmetal; custom hex allowed). First picture is the
    default. The accessory's colour dots = the colours on its pictures, in order.
A2. **Spec lines** become rich text (several lines, bold / colour allowed), replacing the one-line
    spec (old text migrates as is).
A3. **Remark**: one optional rich line (e.g. "Colour follows sink").
A4. A **catalogue product used as an entry** (SRTW5000) shows by default: code, its existing
    **Price tag description** (rich, already edited on the product), LP, lead photo. No new product
    fields.

**Per use (the entry on a product's or a combo's list)**

P1. Each entry can set, for this list only: **which picture** (default: the accessory's first),
    **name**, **spec lines**, **remark** (blank = use the accessory's). Edited from a pencil on the
    entry row in the existing `AccessoryListField`. A product entry's description override replaces
    its Price tag description on this tag only.

**Fit (never cut a card)**

F1. Cards keep their design size when they fit. When they do not, **every card in the box shrinks by
    the same factor** (text and pictures together, so the card keeps its look) down to a minimum of
    **70%** of its design size.
F2. Still not fitting at 70%: **only whole cards print** and the warning shows in the designer
    (on the canvas and inspector, the #2235 warning), in the request preview and as the print-sheet
    toast ("Tag 2a: 1 accessory does not fit its box"). Never a card cut in half; nothing silent.
F3. Text inside a card element that is too long for its element shrinks to fit (existing rule) and
    never spills out of the element.

**Unchanged**: lists stay independent on product and combo (Q1); one system, no second free-items
list (Q5); "Reads from" picks the list as today; pinned tags freeze the list (A9) and now also
freeze each entry's per-use text and picture choice; one layout function feeds canvas, request
preview and print (A10).

## Examples (owner screenshots; crew to confirm names on the dev DB, SQL below)

1. **SRTKS7846, vertical "ACCESSORIES INCLUDED"**: CHOPPING BOARD (1 picture, no spec); COLANDER
   (2 pictures: Black, Grey; spec "390x200x140 / Depth: 160mm"); DRAINER (2 pictures, spec). Card:
   picture left, dots under the picture, name bold + spec right. Box 60 x 80 mm on the 148 x 105 mm
   tag: 3 cards need 84 mm at 100%, so they shrink to 95% and all 3 print whole (today COLANDER is
   cut). Footer "* Accessories Color Follow Kitchen Sink Color" + dots.
2. **Wash basin combo SRTWB7065 + SRTWT7202, "FREE" box**: one product entry SRTW5000. Product's
   Price tag description "Popup Waste 80mm (w/o Overflow) Brass"; this combo overrides it on its
   entry to "Pop-up waste 80mm, brass" (P1); LP: RM 68.
3. **Combo + 1 tap, "FREE" vertical beside the tap**: DRAINER + PULL OUT DRAINER, saved accessories
   template "FREE vertical" (D6) inserted into a second template (D7) and nudged smaller in place.
4. **Too many**: 5 entries in a box that holds 3 at 70%: 3 print whole, warning "2 of 5 accessories
   do not fit this box" on canvas, preview and print toast.
5. **Old box, never edited**: SRTKS7061-BL "ACCESSORIES INCLUDED" horizontal from #2211 prints
   exactly as before (D5).

Edge cases: accessory with no picture (Picture element prints nothing, text keeps its place; no
grey box); no colours (dots element prints nothing); per-use picture deleted from the library
(falls back to the first picture); saved template deleted (boxes that used it keep their design,
D7 copy rule); entering a box with an empty list (2 sample cards to style, as today, A7); a card
element bound to Price on a library accessory (prints nothing: accessories have no price).

## Questions (v1, ANSWERED 7 Nov ~21:55, see "Owner rulings on v1" at the top)

Q1. When a saved accessories template is changed, what happens to tag templates already using it?
    (a) **Nothing automatically: applying copies the design. A box remembers which saved template
        it came from and shows "Saved template changed - update this box" in its inspector**
        (recommended: a published tag never changes by surprise, and each tag template keeps its
        own versions; one click per template to follow).
    (b) Live link: every box using it changes at once (a "Detach" option to stop following).
    (c) As (a), plus a "Also update the N templates using it" tick when you save over it.
Q2. Shrink-to-fit minimum: (a) **70% of the card's design size** (recommended: smaller than that
    is hard to read on a 148 x 105 tag) / (b) 50% / (c) no shrink, warn only.
Q3. Which colour picture prints when an accessory has several?
    (a) **The one chosen on the list entry, default the first; the dots show all colours**
        (recommended: products carry no colour today, so nothing to match on).
    (b) Match the tag product's colour (needs a colour on products first: a separate lane).
Q4. The box footer dots ("* Accessories Color Follow Kitchen Sink Color"): which colours?
    (a) **All colours across the box's accessories, de-duplicated** (recommended: matches the
        screenshot, nothing to type).
    (b) Colours you pick on the footer element by hand.
Q5. Where are saved accessories templates managed?
    (a) **Only in the designer's Accessories menu (rename, delete), no list page** (recommended: the
        owner asked for one place).
    (b) Also a list page under Dealer Kit like Tag Sizes (`/dealer-kit/tag-sizes`).

## Dev data the crew can measure (no DB from the cloud sandbox)

```sql
SELECT p.product_code, a.name, a.spec, (a.image_attachment_id IS NOT NULL) AS has_pic
FROM product_accessories pa JOIN products p ON p.id = pa.product_id
LEFT JOIN accessories a ON a.id = pa.accessory_id
WHERE p.product_code IN ('SRTKS7846', 'SRTKS7061-BL') ORDER BY 1, pa.sort_order;

SELECT pc.name, ip.product_code, ip.price_tag_description
FROM product_combo_accessories pca JOIN product_combos pc ON pc.id = pca.combo_id
JOIN products ip ON ip.id = pca.item_product_id WHERE ip.product_code = 'SRTW5000';
```
