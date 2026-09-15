# Marketing - Catalogue packages on price tags (Combos)

Use this when a product is sold as a catalogue package rather than on its own: a cabinet that goes out with a table top, a mirror, a tap and a pop-up waste, and a basin the customer picks one colour of. Record the package once on the product, and every price tag request a salesperson raises for that product arrives with the parts already under it, prints them on the tag, and prices them together.

## Where

* Record a package: **[Products → Products → All Products](/master-data-management/products)** (URL: `/master-data-management/products`), open the product, **Overview** tab, the **Combos** card.
* Work a request: **[Dealer Kit → Room Designer → Price Tag Requests](/dealer-kit/price-tag-requests)** (URL: `/dealer-kit/price-tag-requests`).
* Choose which product classes are checked for a missing package: **[User Management → Settings](/user-management/settings)**, the **Price tag guarded classes** field.

## What a combo is, and what it is not

A combo is the catalogue's own wording for how a product is sold. It is named the way the page names it (*2 in 1*, *3 in 1*, *4 in 1*), it lives on the real host product, and it carries no code and no price of its own. A product printed on two catalogue pages carries two combos.

A combo is deliberately **not** a product set. Sets are separate sellable codes, and the WhatsApp assistant searches them when it answers stock questions. Combos are invisible to it: a stock question about the cabinet still answers for the cabinet alone, exactly as before.

A combo has two kinds of part:

* **Fixed part** - always in the box. Every request for the host gets it.
* **A choice group** - two or more parts sharing one label, and the customer picks one of them. The salesperson can answer it on the request, or leave it open for you.

## Steps - record a package on a product

1. Open the product and stay on the **Overview** tab. The **Combos** card sits below the existing cards; a product with none shows **No combos.**
2. Click **Add combo**. Type the catalogue's wording into **Name** (for example *3 in 1*) and click **Add combo** again. A name is used once per product: a second combo with the same name is refused under the field.
3. The new combo opens empty (**No parts yet.**). Use the **Add part** search at the bottom of the combo and pick a product; it lands as a part row showing the code, the name and the dimensions. Repeat for every part. The host product itself, and a product already in this combo, are refused with a message under the picker.
4. Leave a part's group control on **Fixed part** if it always comes with the package. For a part the customer chooses, open the same control, type the group name (for example *Basin*) and choose **Use "Basin"**; the label is then offered on the other rows of this combo so the rest of the group is one click. Rows sharing a label are drawn together in their own block, headed *Basin - pick one*.
5. Remove a part with the trash icon on its row, or a whole combo with the trash icon in its header. Both are countdown actions with a **Cancel**, and there is no confirmation dialog to answer.
6. For a product on two catalogue pages, click **Add combo** again and build the second one. Order matters only within a combo: fixed parts print first, then each choice group in the order its label first appears.

Editing a combo takes effect on requests raised **after** the change. A request already submitted keeps the parts that were copied onto it, so a package you correct today never quietly rewrites a tag marketing already approved.

### Reading it from a part's own page

Open any part (the mirror, the tap, a basin) and the **Sold with** card on its **Overview** tab names every host and combo it belongs to, as *SRTBF11834 · 3 in 1*, with the code linking to the host product. A part in three packages lists three rows. The card is read-only: a package is edited on the host, where it is defined. A part in none shows **This product is not part of any combo.**

## What the salesperson does on the portal

Nothing is asked of them that they did not already know. They pick the cabinet code they have in front of them, and the parts appear under the line on their own. They can drop a part, add one the package missed, answer a choice group, or leave it open for you. A missing package never blocks their submit; it arrives to you as a note on the line instead. Their side is written up in [Submit via portal](../project-sales-rep/submit-via-portal.md#packages-and-parts-on-a-line).

## Steps - prepare the tags on a request

1. Open the request from **Price Tag Requests** and go to the **Lines** tab. Each line is the product the salesperson asked for, with its parts indented under it and its tags under those. A part the salesperson left open reads *Basin: SRTBS100-WH / SRTBS100-BL / SRTBS100-GR*.
2. Read any **Package warning** pill next to the line name. Three texts are possible, all of them written by the check at submit:
   * **No package defined** - the product is in a guarded class and has no combo on it at all. Somebody has to record one (the steps above), or the tag prints the product alone.
   * **No package chosen** - the product has combos and the salesperson picked none.
   * **Missing: SRTMR502-BL** - the chosen package's parts are not all on the line. The codes and group labels named are the ones missing.
3. A line with parts, or more than one tag, still splits into rows: the line row, then each tag labelled by its line position and a letter - **1a**, then **1b**, **1c** if it is split - carrying the resolved choice, **Qty**, **List Price**, **Sell Price**, and **Designed** or **No tag**. A line with exactly one tag and no parts is a single row instead - no `1a` label - the line row itself carries the price and status.
4. Click **Design** on a tag to open the designer on it. The **Lines** rail on the left lists each line with its tags nested underneath; a line with exactly one tag, no parts and no open choice group is drawn as one block instead, since there's nothing to nest.
5. A tag whose line left a choice group open carries an **Open: Basin** pill and two ways to answer it:
   * **Split into 4 tags** - the tag stays where it is, keeps its design, and takes the first candidate; the remaining candidates each get their own tag after it, with the design copied. Use this when the customer should see every colour. Toast: *"Split into one tag per basin."*
   * **Pick one** - a select beside it that resolves the group on this tag alone, leaving the line with a single tag.
6. Design and arrange as usual. A tag's quantity follows the line the salesperson asked for; once a line is split, each tag keeps its own number, because those are your decisions rather than a copy of theirs. The sheet lays out one tile per tag, times that tag's quantity.
7. To drop a tag you no longer want to print, use the bin on its row in the rail: it counts down for a few seconds with a **Cancel**, and removes the tag and its tile when the countdown runs out.

A line always keeps at least one tag, so the last tag on a line cannot be taken away - its bin is greyed out and says so. A price override set on a tag shows on the rail as */ Override RM 1,280.00* and on the **Lines** tab as *Override: RM 1,280.00*; it replaces the **selling** price only, so the tag still prints what the package lists at.

## What prints on the tag

* The parts go into the members block the tag templates already carry, so no template has to be touched. Each resolved part prints as `+ CODE NAME DIMENSIONS`, in part order. A group still open prints as `Basin: SRTBS100-WH / SRTBS100-BL / SRTBS100-GR`.
* A custom layout can also pull the parts on their own with the **Parts (codes)** and **Parts (names)** merge fields in the designer's Line group - useful when a template wants just the codes or just the names rather than the whole members block.
* **List price** on the tag is the host's list price plus the list price of every resolved part. A group still open adds nothing until it is resolved or split.
* **Selling price** is the promotion engine's answer for each of those products, added up; where the engine has no offer for a product, its list price is used, because a price with no promotion behind it is simply the price. A marketing override on the tag wins over that sum.
* A tag with no parts prints exactly what it always did.

## What's captured

* On the product: the combo name, its parts in order, and each part's choice group. No price, no code, no dates.
* On a submitted request line: the package chosen, the parts as they stood at submit (including any group left open, with its candidates), and the package warning text if there was one.
* On each tag: its position under the line, its quantity, the choice it resolves, and any marketing price override and reason.

Combo changes on a product are recorded on that product's **Audit Trail** tab.

## How you'll be notified

Everything here is immediate and in-app: a toast when a combo, part or split saves, and an inline message under the field when a name or a part is refused. No email, no WhatsApp, and nothing runs in the background, so a package is usable on the very next request.

## Bulk import

None. Packages are recorded by hand, product by product, off the catalogue pages. That is a deliberate choice for the sixty to a hundred packages in the current catalogue; reading them off the catalogue page automatically is a job for the next season.

## See also

* [Project Sales Rep - Submit via portal](../project-sales-rep/submit-via-portal.md#packages-and-parts-on-a-line) - the salesperson's side of the same package.
* [Product Management - Manage products](../product/manage-products.md) - the rest of the product detail page.
* [Configure Portal Revisions](../user-management/configure-portal-revisions.md) - letting a salesperson revise a submitted price tag request.
