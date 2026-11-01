# Marketing - Catalogue packages on price tags (Combos)

Use this when a product is sold as a catalogue package rather than on its own: a cabinet that goes out with a table top, a mirror, a tap and a pop-up waste, and a basin the customer picks one colour of. Record the package once on the product, and every price tag request a salesperson raises for that product arrives with the parts already under it, prints them on the tag, and prices them together.

## Where

* Record a package: **[Products → Products → All Products](/master-data-management/products)** (URL: `/master-data-management/products`), open the product, **Overview** tab, the **Combos** card.
* Work a request: **[Dealer Kit → Room Designer → Price Tag Requests](/dealer-kit/price-tag-requests)** (URL: `/dealer-kit/price-tag-requests`).
* Choose which product classes are checked for a missing package: **[User Management → Settings](/user-management/settings)**, the **Price tag guarded classes** field.

## What a combo is, and what it is not

A combo is the catalogue's own wording for how a product is sold. It is named the way the page names it (*2 in 1*, *3 in 1*, *4 in 1*), it lives on the real host product, and it carries no code. It can hold its own price, and with the price left blank the tag adds up the products instead. A product printed on two catalogue pages carries two combos.

A combo is deliberately **not** a product set. Sets are separate sellable codes, and the WhatsApp assistant searches them when it answers stock questions. Combos are invisible to it: a stock question about the cabinet still answers for the cabinet alone, exactly as before.

A combo has two kinds of part:

* **Fixed part** - always in the box. Every request for the host gets it.
* **A choice group** - two or more parts sharing one label, and the customer picks one of them. The salesperson can answer it on the request, or leave it open for you.

## Steps - record a package on a product

1. Open the product and stay on the **Overview** tab. The **Combos** card sits below the existing cards; a product with none shows **No combos.**
2. Click **Add combo**. Type the catalogue's wording into **Name** (for example *3 in 1*) and click **Add combo** again. A name is used once per product: a second combo with the same name is refused under the field.
3. The new combo opens empty (**No parts yet.**). Use the **Add part** search at the bottom of the combo and pick a product; it lands as a part row showing the code, the name and the dimensions. Repeat for every part. The host product itself, and a product already in this combo, are refused with a message under the picker.
4. Leave a part's group control on **Fixed part** if it always comes with the package. For a part the customer chooses, open the same control, type the group name (for example *Basin*) and choose **Use "Basin"**; the label is then offered on the other rows of this combo so the rest of the group is one click. Rows sharing a label are drawn together in their own block, headed *Basin - pick one*.
5. A combo can carry one cover picture, the single photo of everything in the package. With none set, the combo shows **Upload picture**; pick a jpg, png or webp up to 10 MB. Once one is set, the same spot shows the thumbnail with **Replace** and **Clear** instead. This is separate from any product's own photos, and it becomes the first image a tag prints for a line using this combo - see [What prints on the tag](#what-prints-on-the-tag).
6. Fill in what the tag should say about the package as a whole. **Description** is the combo's own text, for example the cabinet, basin, mirror and tap it includes. **Free items** is plain text printed as you type it, for example *Chopping board, drainer*; free items need no product code.
7. To print a package price, fill **List price (RM)** and **Sell price (RM)** on the combo. Leave them blank to keep the added-up price. On a choice group where each option has its own price, such as a sink whose price depends on the tap, fill **Sell price if picked** on each part row instead.
8. To offer an upgrade, tick **Upgrade** on the part's row and fill **Top-up**, the amount it adds to the package price. Upgrades are drawn in their own **Upgrade** block after the choice groups.
9. Remove a part with the trash icon on its row, or a whole combo with the trash icon in its header. Both are countdown actions with a **Cancel**, and there is no confirmation dialog to answer.
10. For a product on two catalogue pages, click **Add combo** again and build the second one. Order matters only within a combo: fixed parts print first, then each choice group in the order its label first appears.

Editing a combo's **parts** takes effect on requests raised **after** the change: a request already submitted keeps the parts that were copied onto it. A change to its **description, free items or prices** reaches tags still being designed, with the usual change note and roll back. An approved tag stays as it was, apart from the cover picture, which always shows the current one.

### Reading it from a part's own page

Open any part (the mirror, the tap, a basin) and the **Sold with** card on its **Overview** tab names every host and combo it belongs to, as *SRTBF11834 · 3 in 1*, with the code linking to the host product. A part in three packages lists three rows. The card is read-only: a package is edited on the host, where it is defined. A part in none shows **This product is not part of any combo.**

## What the salesperson does on the portal

Nothing is asked of them that they did not already know. They pick the cabinet code they have in front of them, and the parts appear under the line on their own. They can drop a part, add one the package missed, answer a choice group, or leave it open for you. A missing package never blocks their submit; it arrives to you as a note on the line instead. Their side is written up in [Submit via portal](../project-sales-rep/submit-via-portal.md#packages-and-parts-on-a-line).

## Steps - prepare the tags on a request

1. Open the request from **Price Tag Requests** and go to the **Lines** tab. Each line is the product the salesperson asked for, with its parts indented under it and its tags under those. A part the salesperson left open reads *Basin: SRTBS100-WH / SRTBS100-BL / SRTBS100-GR*.
2. Read any **Package warning** pill next to the line name. These texts are possible, all of them written by the check at submit:
   * **No package defined** - the product is in a guarded class and has no combo on it at all. Somebody has to record one (the steps above), or the tag prints the product alone.
   * **No package chosen** - the product has combos and the salesperson picked none.
   * **Missing: SRTMR502-BL** - the chosen package's parts are not all on the line. The codes and group labels named are the ones missing.
   * **Combo has no picture**, **Combo has no description**, or both together - the chosen combo is missing that content, so the tag falls back to the product's own photo or description. Fill it on the Combos card.
3. A line with parts, or more than one tag, still splits into rows: the line row, then each tag labelled by its line position and a letter. A line with a combo keeps **one tag** even when a choice group was left open: that tag lists every option with its price, and if the salesperson picked one, it shows only that one. A line with an open group and no combo still gets **1a**, **1b**, **1c**, one per option, the moment it is saved. A request already split before this rule keeps its tags. Each tag row carries the resolved choice, **Qty**, **List Price**, **Sell Price**, and **Designed** or **No tag**. A line with exactly one tag and no parts is a single row instead - no `1a` label - the line row itself carries the price and status.
4. Click **Design** on a tag to open the designer on it. The **Lines** rail on the left lists each line with its tags nested underneath, a line with a combo as its one tag, a line with an open group and no combo already split into one row per candidate - there is no **Open** pill and nothing to split or pick one from. A line with exactly one tag, no parts and no open choice group is drawn as one block instead, since there's nothing to nest.
5. On a combo tag, every layer that reads product data (the photo slot, code, name, specs, a price badge, a barcode, or a text layer with a product or spec token) offers a **Product** select in the Inspector. It lists the parent product first, then every product in the line's whole combo, grouped by role (for example *Basin*) - not just the candidate this particular tag resolved to, so tag **1a** can bind its slots to any of the basins and show all of them even though 1a itself resolved to one colour. The candidate this tag chose is marked **(this tag)**. Leave a layer on the parent (the default) for most layers - a single-product tag shows no **Product** select at all, since there's nothing to choose between. A price badge's select carries one extra first entry, **Tag total**, the parent plus this tag's own resolved parts added together - the default, and what a price badge has always shown, unchanged even when other slots on the same tag point at a different candidate. A layer pointed at a product has its name suffixed with that product's code in the **LAYERS** panel, so a scan of the list tells you which product each layer draws. Copying a design onto another tag with **Apply to all** falls a part-pointed layer back to the parent when the target has fewer parts, and names the layer in a toast.
6. Design and [arrange](price-tag-requests.md#arranging-the-sheet) as usual. A tag's quantity follows the line the salesperson asked for; once a line has more than one tag, each keeps its own number, because those are your decisions rather than a copy of theirs. The sheet lays out one tile per tag, times that tag's quantity.
7. To keep a tag but leave it out of the arrangement and the PDF, use its row's **Not printed** toggle instead of removing it - it greys the row and wears a **Not printed** pill, and it stays fully editable. Once 1a alone is drawn to show every basin, mark 1b and 1c **Not printed** and only one tag prints from that line. See [In the designer](price-tag-requests.md#in-the-designer) for the full toggle.
8. To remove a tag entirely, use the bin on its row in the rail: it counts down for a few seconds with a **Cancel**, and removes the tag and its tile when the countdown runs out.

A line always keeps at least one tag, so the last tag on a line cannot be taken away - its bin is greyed out and says so. A price override set on a tag shows on the rail as */ Override RM 1,280.00* and on the **Lines** tab as *Override: RM 1,280.00*; it replaces the **selling** price only, so the tag still prints what the package lists at.

## Design a combo template

Do this once per kind of package; every combo tag then fills in with nothing further to design.

1. Open **[Dealer Kit → Room Designer → Tag Templates](/dealer-kit/tag-templates)** and open a template. Bathroom furniture and kitchen sink products pick their family's template on a new design.
2. Use **Preview combo** above the canvas to pick a real combo. The canvas now shows that combo's picture, text and options while you design.
3. Select a layer, and in the Inspector's field list choose from the **Combo** group: **Combo Photo**, **Combo Name**, **Combo Description**, **Combo Choices**, **Combo Top-ups**. Free items print through the existing **Accessories** field, and prices through **List Price** and **Sell Price**.
4. In a text layer, **Insert field** offers the same content in its Combo group: combo name, combo description and free items.
5. **Publish**.

One template serves lines with and without a combo. With no combo, **Combo Photo** prints the product's photo, **Combo Name** the product code and **Combo Description** the product's price tag description; **Combo Choices** and **Combo Top-ups** print nothing.

## What prints on the tag

* The parts go into the members block the tag templates already carry, so no template has to be touched. Each resolved part prints as `+ CODE NAME DIMENSIONS`, in part order.
* A custom layout can also pull the parts on their own with the **Parts (codes)** and **Parts (names)** merge fields in the designer's Line group - useful when a template wants just the codes or just the names rather than the whole members block.
* **Which price wins**, highest first: a price override on the tag, a price typed on the line, the combo's own price, then the added-up price below.
* The combo's own **Sell price (RM)** prints as filled. When the salesperson picked an option with its own **Sell price if picked**, that prints instead. A picked upgrade adds its **Top-up** to the combo's price. While a choice group with its own prices is still open and the combo has no sell price, the sell price layer stays empty, because each option prints its own price.
* With no combo price, **List price** on the tag is the host's list price plus the list price of every part.
* **Selling price** uses the line's own promotion, set on the request's **Price** section or changed later on the request's **Lines** tab: the parent and every part price under that promotion where it offers one, otherwise at that product's list price. A part the promotion lists at RM 0 adds nothing. A line with a typed price instead of a promotion carries that figure straight through as the tag's selling price. A marketing override set on the tag itself wins over either.
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
* [Product Management - Manage products](../product/manage-products.md) - the rest of the product detail page.
* [Configure Portal Revisions](../user-management/configure-portal-revisions.md) - letting a salesperson revise a submitted price tag request.
