# Marketing - Catalogue packages on price tags (Combos)

Use this when a product is sold as a catalogue package rather than on its own: a cabinet that goes out with a table top, a mirror, a tap and a pop-up waste, and a basin the customer picks one colour of. Record the package once on the product, and every price tag request a salesperson raises for that product arrives with the parts already under it, prints them on the tag, and prices them together.

## Where

* Record a package: **[Products → Products → All Products](/master-data-management/products)** (URL: `/master-data-management/products`), open the product, **Overview** tab, the **Combos** card.
* Work a request: **[Dealer Kit → Room Designer → Price Tag Requests](/dealer-kit/price-tag-requests)** (URL: `/dealer-kit/price-tag-requests`).
* Choose which product classes are checked for a missing package: **[User Management → Settings](/user-management/settings)**, the **Price tag guarded classes** field.

## What a combo is, and what it is not

A combo is the catalogue's own wording for how a product is sold. It is named the way the page names it (*2 in 1*, *3 in 1*, *4 in 1*), it lives on the real host product, and it carries no code. It can hold its own price. A combo's price is never added up from its parts: with no price stored, the tag prints none (see [What prints on the tag](#what-prints-on-the-tag)). A product printed on two catalogue pages carries two combos.

A combo is deliberately **not** a product set. Sets are separate sellable codes, and the WhatsApp assistant searches them when it answers stock questions. Combos are invisible to it: a stock question about the cabinet still answers for the cabinet alone, exactly as before.

A combo is made of:

* **The main product** - the host the combo lives on.
* **Fixed parts** - always in the box. Every request for the host gets them.
* **Choice groups** - two or more parts sharing a label that you give the group yourself (for example *Kitchen tap* or *Tap colour*). The salesperson picks from it on the request.
* **Upgrades** - a part ticked **Upgrade**, with a top-up.

The group names you type are the names the pickers and templates show, so name them in the words your team uses.

## Steps - record a package on a product

1. Open the product and stay on the **Overview** tab. The **Combos** card sits below the existing cards; a product with none shows **No combos.**
2. Click **Add combo**. Type the catalogue's wording into **Name** (for example *3 in 1*) and click **Add combo** again. A name is used once per product: a second combo with the same name is refused under the field.
3. The new combo opens empty (**No parts yet.**). Use the **Add part** search at the bottom of the combo and pick a product; it lands as a part row showing the code, the name and the dimensions. Repeat for every part. The host product itself, and a product already in this combo, are refused with a message under the picker.
4. Leave a part's group control on **Fixed part** if it always comes with the package. For a part the customer chooses, open the same control, type the group name (for example *Basin*) and choose **Use "Basin"**; the label is then offered on the other rows of this combo so the rest of the group is one click. Rows sharing a label are drawn together in their own block, headed *Basin - pick one*.
5. A combo can carry one cover picture, the single photo of everything in the package. With none set, the combo shows **Upload picture**; pick a jpg, png or webp up to 10 MB. Once one is set, the same spot shows the thumbnail with **Replace** and **Clear** instead. This is separate from any product's own photos, and it becomes the first image a tag prints for a line using this combo - see [What prints on the tag](#what-prints-on-the-tag).
6. Fill in what the tag should say about the package as a whole. **Description** is the combo's own text, for example the cabinet, basin, mirror and tap it includes. **Accessories included** is the combo's own list of accessories, built the same way as the product's **Accessories included** card: pick from **Add accessory** (the accessory library) or **Add product**, drag to reorder, and remove with the cross. The combo's list and each product's list are separate; editing one never changes the other.
7. To print a package price, fill **List price (RM)** and **Sell price (RM)** on the combo. Leave them blank and the tag prints no price for the combo; the prices are never added up from the parts. On a choice group where each option has its own price, such as a sink whose price depends on the tap, fill **Sell price if picked** on each part row instead.
8. To offer an upgrade, tick **Upgrade** on the part's row and fill **Top-up**, the amount it adds to the package price. Upgrades are drawn in their own **Upgrade** block after the choice groups.
9. Remove a part with the trash icon on its row, or a whole combo with the trash icon in its header. Both are countdown actions with a **Cancel**, and there is no confirmation dialog to answer.
10. To give the combo its own price tag templates, use **Price tag templates** in the **Add combo** dialog or on the combo, and with two or more linked pick a **Default template**. A request line on this combo then uses them; a combo with none falls back to the host product's templates. The picker says what each template needs in this combo's words (for example *105 x 148 mm. Needs 3 from Kitchen tap, upgrade*), and greys out a template the combo cannot fill with the reason (for example *Needs 6 from choice group 1; Kitchen tap has 5*). This needs the tag templates manage permission; without it the field does not show.
11. For a product on two catalogue pages, click **Add combo** again and build the second one. Order matters only within a combo: fixed parts print first, then each choice group in the order its label first appears.

### Copy a combo to other products

When many products carry the same package (for example every freestanding bathtub with the same mixer tap upgrades and free items), build it once and copy it.

1. On the combo you want to copy, click **Copy to other products** in its header (next to the trash icon). It shows only if you can edit products.
2. Pick the products that should get it. Search, narrow with **Category** and **Brand** (both take several values), and tick rows; shift-click or drag selects a run of rows, and **Select all** ticks every product the search and filters match. The product you are on cannot be ticked. Discontinued products can still be picked. The footer counts what you picked; one copy takes at most 500 products.
3. Click **Next**. The confirm step says how many products get the combo as a new one, and names any picked product that is itself a part of this combo (it is skipped: a product can never be a part of its own combo).
4. If a picked product already has a combo with the same name (capital letters ignored), it is listed with **Skip** or **Overwrite**. Skip is the default. **Overwrite all** sets every row at once. Overwrite replaces that combo's parts, prices, description, picture, accessories included, box style and price tag templates with this one's, and keeps its place on requests already raised.
5. Click **Copy**. Everything is written in one go: if anything is refused, nothing is copied.

Each copy gets the same name, parts (fixed parts, choice groups, prices if picked, upgrades and top-ups), list and sell price, description with its formatting, cover picture and accessories included. The target product becomes the host. Adjust what differs afterwards, such as the size line in the description or the price. Price tag templates are copied only if you can manage tag templates; otherwise the confirm step says they are not copied, and an overwritten combo keeps its own.

Editing a combo's **parts** takes effect on requests raised **after** the change: a request already submitted keeps the parts that were copied onto it. A change to its **description, accessories included or prices** reaches tags still being designed, with the usual change note and roll back. An approved tag stays as it was, apart from the cover picture, which always shows the current one.

### Reading it from a part's own page

Open any part (the mirror, the tap, a basin) and the **Sold with** card on its **Overview** tab names every host and combo it belongs to, as *SRTBF11834 · 3 in 1*, with the code linking to the host product. A part in three packages lists three rows. The card is read-only: a package is edited on the host, where it is defined. A part in none shows **This product is not part of any combo.**

## What the salesperson does on the portal

Nothing is asked of them that they did not already know. A combo is also matched when they paste a list: codes joined with **+** must equal a saved combo (the host plus exactly its parts), otherwise the row reads **Not found** and they pick the product or an existing combo. Nothing creates a combo from the request form, so record every package here first. They pick the cabinet code they have in front of them, and the parts appear under the line on their own. They can drop a part, add one the package missed, answer a choice group, or leave it open for you. A missing package never blocks their submit; it arrives to you as a note on the line instead. Their side is written up in [Submit via portal](../project-sales-rep/submit-via-portal.md#packages-and-parts-on-a-line).

## Steps - prepare the tags on a request

1. Open the request from **Price Tag Requests** and go to the **Lines** tab. Each line is the product the salesperson asked for, with its parts indented under it and its tags under those. A part the salesperson left open reads *Basin: SRTBS100-WH / SRTBS100-BL / SRTBS100-GR*.
2. Read any **Package warning** pill next to the line name. These texts are possible, all of them written by the check at submit:
   * **No package defined** - the product is in a guarded class and has no combo on it at all. Somebody has to record one (the steps above), or the tag prints the product alone.
   * **No package chosen** - the product has combos and the salesperson picked none.
   * **Missing: SRTMR502-BL** - the chosen package's parts are not all on the line. The codes and group labels named are the ones missing.
   * **Combo has no picture**, **Combo has no description**, or both together - the chosen combo is missing that content, so the tag falls back to the product's own photo or description. Fill it on the Combos card.
3. A line with parts, or more than one tag, still splits into rows: the line row, then each tag labelled by its line position and a letter. A line with a combo keeps **one tag** even when a choice group was left open: that tag lists every option with its price, and if the salesperson picked one, it shows only that one. A line with an open group and no combo still gets **1a**, **1b**, **1c**, one per option, the moment it is saved. A request already split before this rule keeps its tags. Each tag row carries the resolved choice, **Qty**, **List Price**, **Sell Price**, and **Designed** or **No tag**. A line with exactly one tag and no parts is a single row instead - no `1a` label - the line row itself carries the price and status.
4. Click **Design** on a tag to open the designer on it. The **Lines** rail on the left lists each line with its tags nested underneath, a line with a combo as its one tag, a line with an open group and no combo already split into one row per candidate - there is no **Open** pill and nothing to split or pick one from. A line with exactly one tag, no parts and no open choice group is drawn as one block instead, since there's nothing to nest.
5. On a combo tag, a layer's **Product** select offers positions in the combo: **Main product**, **Fixed part n**, one entry per pick in each group (for example **Kitchen tap, pick 2**) and **Upgrade n**. See [In the designer](price-tag-requests.md#in-the-designer). Each position prints its own picture, code, description and list price, and a position the line has not filled prints an empty tile. A price badge's select also offers **Tag total**.
6. Design and [arrange](price-tag-requests.md#arranging-the-sheet) as usual. A tag's quantity follows the line the salesperson asked for; once a line has more than one tag, each keeps its own number, because those are your decisions rather than a copy of theirs. The sheet lays out one tile per tag, times that tag's quantity.
7. To keep a tag but leave it out of the arrangement and the PDF, use its row's **Not printed** toggle instead of removing it - it greys the row and wears a **Not printed** pill, and it stays fully editable. Once 1a alone is drawn to show every basin, mark 1b and 1c **Not printed** and only one tag prints from that line. See [In the designer](price-tag-requests.md#in-the-designer) for the full toggle.
8. To remove a tag entirely, use the bin on its row in the rail: it counts down for a few seconds with a **Cancel**, and removes the tag and its tile when the countdown runs out.

A line always keeps at least one tag, so the last tag on a line cannot be taken away - its bin is greyed out and says so. A price override set on a tag shows on the rail as */ Override RM 1,280.00* and on the **Lines** tab as *Override: RM 1,280.00*; it replaces the **selling** price only, so the tag still prints what the package lists at.

## Design a combo template

Do this once per shape of package (for example a sink with three taps); every combo tag then fills in with nothing further to design.

1. Open **[Dealer Kit → Room Designer → Tag Templates](/dealer-kit/tag-templates)** and open a template. Bathroom furniture and kitchen sink products pick their family's template on a new design.
2. Use **Preview combo** above the canvas to pick a real combo. The canvas now shows that combo's picture, text and options while you design.
3. Select a layer, and in the Inspector's field list choose from the **Combo** group: **Combo Photo**, **Combo Name**, **Combo Description**, **Combo Choices**, **Combo Top-ups**. The combo's **Accessories included** list prints through an **Accessories** box (how to design its box: [Designing the Accessories box](price-tag-accessories.md)), and prices through **List Price** and **Sell Price**.
4. In a text layer, **Insert field** offers the same content in its Combo group: **Combo name**, **Combo description** and **Combo accessories included** (the combo list's names, joined).
5. To draw each product of the combo separately, set the layer's **Product** select to a position: **Main product**, **Fixed part n**, a group pick such as **Kitchen tap, pick 2**, or **Upgrade n**. Preview a combo first and the select shows that combo's own names and codes.
6. A template needs whatever positions its layers use: a template with layers on **Kitchen tap, pick 1** to **pick 3** needs 3 from that group. You do not set this anywhere; it is read from the layers and shown on the combo's **Price tag templates** picker and on the request line.
7. Certificates and logos are pictures you place on the template as image layers. They are not part of the combo.
8. An **Accessories** box has its own **Product** select, which says whose list it prints:
   - **This tag's list (combo or product)**, the default: the combo's **Accessories included** on a combo tag, the product's own on a tag without a combo.
   - **Main product's list**, **Fixed part 1 product's list** and so on: that product's own **Accessories included** card, never the combo's. A box set to **Main product's list** on a combo whose main product has no accessories of its own prints nothing; pick **This tag's list (combo or product)** to print the combo's list.
9. An accessory that does not fit its box does not print. While a previewed product or combo has more accessories than a box can draw, a warning sits under **Preview combo**, for example *1 accessory does not fit its box*. Make the box bigger or the cards smaller until it goes. The same warning shows on the combo's **Tag preview** on the product page and on a request's preview, there with the tag's label (*Tag 1a: 1 accessory does not fit its box*).
10. **Publish**.

One template serves lines with and without a combo. With no combo, **Combo Photo** prints the product's photo, **Combo Name** the product code and **Combo Description** the product's price tag description; **Combo Choices** and **Combo Top-ups** print nothing.

## What prints on the tag

* The parts go into the members block the tag templates already carry, so no template has to be touched. Each resolved part prints as `+ CODE NAME DIMENSIONS`, in part order.
* A custom layout can also pull the parts on their own with the **Parts (codes)** and **Parts (names)** merge fields in the designer's Line group - useful when a template wants just the codes or just the names rather than the whole members block.
* **Which price wins**, highest first: a price override on the tag, a price typed on the line, then the combo's own stored price. Nothing is added up from the parts.
* The combo's own **Sell price (RM)** prints as filled. When the salesperson picked an option with its own **Sell price if picked**, that prints instead. A picked upgrade adds its **Top-up** to the combo's price. While a choice group with its own prices is still open and the combo has no sell price, the sell price layer stays empty, because each option prints its own price.
* A combo's price is never added up. A combo with no stored selling price prints none on an SP line until the salesperson types one. A combo with no stored list price prints none on an LP line and the request needs escalating to marketing.
* **Selling price** applies on a line set to SP; a line on LP prints the list price. It uses the line's own promotion, set on the request's **Price** section or changed later on the request's **Lines** tab: the parent and every part price under that promotion where it offers one, otherwise at that product's list price. A part the promotion lists at RM 0 adds nothing. A line with a typed price instead of a promotion carries that figure straight through as the tag's selling price. A marketing override set on the tag itself wins over either.
* A tag with no parts prints exactly what it always did.
* When the combo carries its own cover picture, that picture is the FIRST image the tag shows, ahead of the host's own gallery; a layer bound to the parent uses it, while a layer bound to one part still shows that part's own photo. A combo with no cover picture leaves the photo pick as it always was - see [Which photo prints](price-tag-requests.md#which-photo-prints) in the main request guide.

## What's captured

* On the product: the combo name, its parts in order, each part's choice group, its optional cover picture, description, free items and prices, and each part's sell price, top-up and upgrade mark. No code and no dates: a combo price stays until marketing changes it.
* On a submitted request line: the package chosen, the parts as they stood at submit (including any group left open, with its candidates), and the package warning text if there was one.
* On each tag: its position under the line, its quantity, the choice it resolves, and any marketing price override and reason.

Combo changes on a product are recorded on that product's **Audit Trail** tab.

## How you'll be notified

Everything here is immediate and in-app: a toast when a combo or part saves, and an inline message under the field when a name, a part or a cover picture is refused. No email, no WhatsApp, and nothing runs in the background, so a package is usable on the very next request.

## Bulk import

There is no import screen. The technical team can load combos from the printed catalogue in one run: name, parts, choice groups, upgrades, description, free items and picture. No price is loaded, so fill those in yourself. The run produces a report listing every code that could not be matched, which part was dropped, and every reading of the page that was a guess, so you can correct them on the product. Re-running never overwrites what you changed. Anything else is recorded by hand, product by product.

## See also

* [Project Sales Rep - Submit via portal](../project-sales-rep/submit-via-portal.md#packages-and-parts-on-a-line) - the salesperson's side of the same package.
* [Designing the Accessories box on a price tag](price-tag-accessories.md) - the card, footer, saved accessories templates and per-list overrides.
* [Product Management - Manage products](../product/manage-products.md) - the rest of the product detail page.
* [Configure Portal Revisions](../user-management/configure-portal-revisions.md) - letting a salesperson revise a submitted price tag request.
