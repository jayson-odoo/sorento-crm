# Marketing - Designing the Accessories box on a price tag

Use this when a price tag lists what comes free with a product (a chopping board, a colander, a drainer, a pop-up waste) and you want to design how that list looks: the picture, name, spec lines and colour dots of each accessory, the box around them, and a footer note. You design the layout once, inside the Tag Template designer, and every accessory in the list uses it.

## Where

* Design the box: **[Dealer Kit → Room Designer → Tag Templates](/dealer-kit/tag-templates)** (URL: `/dealer-kit/tag-templates`), open a template and use the **Add Accessories** button in the toolbar.
* Manage saved box designs: **[Dealer Kit → Accessory Templates](/dealer-kit/accessory-templates)** (URL: `/dealer-kit/accessory-templates`), beside **Tag Sizes**.
* Record the accessories themselves (pictures, colours, spec lines, remark): **[Master Data → Products → Accessories](/master-data-management/accessories)**.
* Choose which accessories a product or combo comes with: the **Accessories included** card on the product's **Overview** tab, and the combo's own list in the **Combos** card (see [Catalogue packages on price tags](price-tag-packages.md)).

## What the Accessories box is

The Accessories box is one layer on the tag. It prints every accessory in the list of the product (or combo) the tag is for. You do not design one card per accessory. You design **one card** and the box repeats it for each accessory:

* The card is made of slots: **Picture**, **Name**, **Code**, **Spec lines**, **Remark**, **Price** (list price, only for a catalogue product used as an entry) and **Colour dots**. You can also add fixed text and shapes.
* A slot with nothing to show for an accessory does not print. A chopping board with no spec lines and no colours prints no spec lines and no dots, while a colander with both prints them. The slot under an empty one moves up, so no gap is left, and no grey placeholder prints. Every card in a box keeps the same height, so the cards line up.
* Colour dots appear only for an accessory that has colours on its pictures (see [Accessory pictures with colours](#accessory-pictures-with-colours-spec-lines-and-remark)). An accessory with none shows no dots.
* The box takes 1, 2, 3 or more cards by itself, so the same design prints a tag with three accessories and a combo tag with two.

## Steps - design the card

1. Open a tag template in **Tag Templates** and add a box with **Add Accessories** then **Default box**, or click an existing Accessories box.
2. With the box selected, double-click it, or click **Edit card** in the Inspector. The toolbar changes to **Editing card:** with **Picture**, **Text**, **Colour dots**, **Shape** and **Done**. Card 1 is outlined; the other cards fade and follow every change you make.
3. Click a tool to drop that element in the middle of card 1:
   * **Picture** - the accessory's picture.
   * **Text** - choose what it shows from the accessory: **Name**, **Code**, **Spec lines**, **Remark**, **Price**, or your own fixed text.
   * **Colour dots** - one dot per colour the accessory has. In the Inspector set the dot size, the **Gap (mm)** and whether the dots run in a row or a column.
   * **Shape** - a line or a rounded box for decoration.
4. Drag an element anywhere inside the card. A pink guide appears when it lines up with another element or the card edge, and it snaps there when you let go.
5. Resize an element with its corner handles. Resizing the **Colour dots** element makes the dots bigger or smaller.
6. To hide an element without losing it, use its eye (**Hide element** / **Show element**). To remove it, select it and press Delete.
7. Click **Done** (or press Escape, or click outside the box) to leave. The whole tag is shown again, with the card applied to every accessory.

An element can be dragged freely, so there is no fixed spot for the dots: put them beside the picture, under it, or anywhere else on the card.

## Box layout

With the box selected (not editing the card), the Inspector sets the box around the cards:

* **Show header** and **Header text** - the heading such as *ACCESSORIES INCLUDED* or *FREE*. **Header on the border** puts it on the top border line, as on the printed Dealer Kit.
* **Direction** - **Vertical** stacks the cards, **Horizontal** runs them left to right.
* **Gap (mm)** - the space between cards.
* **Show frame**, **Box fill**, **Border colour**, **Border (mm)** and **Corner radius (mm)** - the look of the box.
* **Shrink to fit, smallest 70%** - when the cards are too many for the box, all cards shrink together, keeping their look, down to 70% of the size you designed. This is fixed and cannot be changed.

### When cards still do not fit

If the cards do not fit even at 70%, only whole cards print. A card is never cut in half. The Inspector and the canvas warn that some accessories do not fit the box, and the designer shows a warning such as *1 accessory does not fit its box and will not print. Make the box bigger or the cards smaller.* Make the box bigger, make the cards smaller, or shorten the list on the product.

## Footer note

A footer is a strip under the cards for a note such as *\* Accessories Color Follow Kitchen Sink Color* with its own colour dots.

1. With the box selected, tick **Footer note** in the Inspector.
2. Click **Edit footer**. The toolbar offers **Text**, **Colour dots**, **Shape** and **Done** (no Picture).
3. Add the text and type your note, add **Colour dots**, and drag the dots beside the text. Click **Done**.

The footer's dots show all the colours of the accessories in the box, each colour once, unless you pick the colours by hand on that element.

## Accessories box on spec sheet templates

The **Add Accessories** button is also on spec sheet templates. There the box prints every accessory a salesperson picked with **Add accessory** on a spec sheet page, any number. The default card is the picture, then a bold line with the brand and code, then the spec sheet description. The card also offers the fields **Brand**, **Description**, **Spec sheet description** and **Dimensions**.

## Tables

Click **Add Table** in the toolbar of a price tag or spec sheet template.

* Right-click a cell for **Insert row below**, **Insert column right**, **Delete row**, **Delete column**, **Merge cells**, **Merge down** and **Unmerge cells**.
* Click a cell to edit it in the Inspector: its content (with **Insert field**), border colour and width for each side or for all sides, padding, and fill.
* A border shared by two cells draws once; changing either cell's side of it changes that line.

## Insert field on spec sheet templates

A spec sheet template's **Insert field** also lists: **Line** (Description, UOM, Technical spec, Notes, Item label), **Spec sheet** (Subject title, Attn, Recipient, Project code, Page number, Page count) and **Accessories** (Accessory 1 to 3: code, name, brand, description, spec sheet description, dimensions). A price tag template does not offer the spec-sheet-only ones.

## Save the design and reuse it

1. With the box selected, click **Save as accessories template**, type a name and save. A toast confirms *Accessories template saved*. The box design is stored: frame, header, footer, direction, card layout and fit settings. The box's position on the tag and which list it reads from stay with each tag template.
2. In any other tag template, click **Add Accessories**. The menu offers **Default box** and your saved templates (use **Search templates** to find one). Pick one to add a box with that design, then move and size it as you like.

### The live link

A box made from a saved template is linked to it. The Inspector shows *Linked: Dealer Kit included (used in 2 tag templates)*. While you edit such a box, a bar reads *Linked to Dealer Kit included: changes here update 2 tag templates*. When you save, the change reaches **every** tag template that uses the saved template, including requests whose tag is printed from it.

Position, size and which list the box reads from are never linked. They stay per box.

### Detach

To change just one tag template, select its box and click **Detach**. The box keeps its current design as its own private copy and no longer follows the saved template. Edit it freely after that.

## Accessory Templates page

Open **Accessory Templates** under Dealer Kit. The list shows **Preview**, **Name**, **Used in** (the number of tag templates; click it to see which), **Updated** (dd/mm/yyyy) and **By**.

* **Rename template** - in the row menu. The name must be unique.
* **Delete** - a countdown action with a **Cancel**, no confirmation dialog. Deleting a saved template does not change any tag: every box that used it keeps its last design and simply stops being linked.

You cannot edit a design on this page. Designs are always edited in the Tag Template designer.

## Accessory pictures with colours, spec lines and remark

Open **Master Data → Products → Accessories** and open an accessory (**Add accessory** for a new one).

1. **Add picture** one per colour. Pick a jpg, png or webp. Up to 12 pictures per accessory.
2. Set each picture's colour (for example Black or Grey). The first picture is the default one, and you can drag pictures to reorder them. The accessory's colour dots are the colours on its pictures, in order.
3. **Spec lines** takes several lines, with bold or colour if you want (for example `390x200x140`, then `Depth: 160mm`).
4. **Remark** takes one optional note (for example *Colour follows sink*).

A catalogue product used as an entry on a list (a pop-up waste, say) shows its code, its **Price tag description**, its list price and its lead photo by default. It has no colours.

## Different text or picture for one list

The same accessory can read differently on one product or combo. On the **Accessories included** card of the product (or on the combo's list), click the pencil on the row (**Edit for this list**). You can set:

* **Picture choice** - which of the accessory's pictures prints. The default is the first.
* **Name**, **Spec lines**, **Remark** - blank means use the accessory's own.

A row with any override wears an **Own text** pill. The change applies to that list only, and a tag already pinned keeps what it was pinned with. Dots still show all the accessory's colours whatever picture you pick.

## Boxes that already exist

An Accessories box saved before this feature prints exactly as it always did on the canvas, the request preview and the print. It only changes when somebody clicks **Edit card** on it (it then opens with a card built from its old settings, so it still looks the same until edited) or applies a saved template to it.

## What's captured

* On the accessory: its pictures in order with an optional colour each, its spec lines and remark.
* On a list entry: the chosen picture and the name, spec lines and remark overrides.
* On a tag template: the box, its card layout, footer and fit settings, and a link to the saved template if there is one.
* On a saved template: the name, the design, who changed it and when.

## How you'll be notified

Immediate and in-app: toasts when a template is saved, renamed or deleted, a warning on the canvas when accessories do not fit, and an inline message when a picture or name is refused. No email, no WhatsApp, nothing runs in the background.

## FAQ

**Why does a card have no dots?** That accessory has no colours on its pictures. Open it in Master Data → Products → Accessories and set a colour on each picture. A chopping board with one plain picture correctly shows none, and the space closes up.

**Why did my change appear on another tag template?** The box is linked to a saved accessories template, so editing it updates every tag template that uses it. The Inspector says *Linked: ...* when this is the case.

**How do I change just one template?** Select its box and click **Detach** first, then edit. Or insert **Default box** instead of a saved one.

**Why is an accessory missing from the printed tag?** It did not fit even at 70%, so only whole cards print. Look for the *do not fit* warning, then enlarge the box or shrink the cards.

**Why do all cards have the same height when one shows less?** That is intended, so rows line up. A card with less to show leaves its empty slot closed up inside the same height.

**Can one accessory have its own card layout?** Not now. For different wording or a different picture on one product, use the pencil on its row. An empty field already hides its slot.

**What happens if I delete a saved template?** Nothing changes on any tag. Each box keeps its last design and stops being linked.

## See also

* [Catalogue packages on price tags](price-tag-packages.md) - combos and their free items.
* [Price Tag Requests](price-tag-requests.md) - working a request and designing a tag.
* [Project spec sheet](../project-sales-rep/project-spec-sheet.md) - where the spec sheet templates are used.
