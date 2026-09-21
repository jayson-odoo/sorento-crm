# Marketing - Work a price tag request (design, change requests, printing, collection)

How the office takes a price tag request from the salesperson's submission to printed tags in
their hands: reading the design without opening the editor, working off the salesperson's pinned
change requests, handing the tags over, and deciding what to do when product data moves under a
design that is already drawn.

Open **[Dealer Kit → Room Designer → Price Tag Requests](/dealer-kit/price-tag-requests)** and click
a row to open it.

## Steps

1. On the list, use the status filter (**All statuses**, **New**, **Designing**, **Design Ready**,
   **Changes Requested**, **Approved**, **Ready for collection**, **Collected**, **Rejected**,
   **Void**) to find the request, and click the row.
2. Press **Claim** if nobody owns it yet. Claiming (or being assigned it automatically) moves the
   request to **Designing**, and at that moment the product data on every line is pinned to the
   tags - see [When product data changes](#when-product-data-changes).
3. Press **Design tags** to open the designer and draw the tags.
4. Back on the request, press **Mark design ready**. The salesperson gets a WhatsApp with a link to
   the design.
5. The salesperson either approves or sends pinned change requests. See
   [Working off change requests](#working-off-change-requests).
6. After they approve, finish the request according to **Printing** - see
   [Printing and collection](#printing-and-collection).

## The Design section

The first block of the **Request** tab is **Design**: the same drawing the salesperson sees, drawn
from the current draft, so nobody has to load the editor just to check which request is being
talked about.

* Before there is anything to draw it reads **No design yet** with the hint *"Claim the request and
  open the designer to draw the tags."*
* **Open** gives the full-screen view: sheet pager, zoom control, and the same behaviour as the
  attachment viewer - **Ctrl + wheel** (**Cmd + wheel**) zooms at the pointer, a plain wheel
  scrolls, drag pans, **+ - 0** zoom and reset to Fit, arrow keys change sheet.
* **History** opens the request's own versions - see [Design history](#design-history).

## In the designer

* The **Lines** rail lists each line with its tags nested underneath. A line with exactly one tag,
  no parts and no open choice group is drawn as a single block instead - click the block itself to
  select that tag, no separate `1a` row underneath. The rail fills the panel, with **Tag Size**
  pinned at its foot, directly above the resize handle - no dead space between them, whatever the
  panel's height. Selecting a different tag no longer resets the rail's scroll position, so picking
  one near the bottom of a long list keeps it in view. On a phone the rail is hidden; use a tablet
  or desktop screen to design.
* Each tag's row in the rail carries a **Not printed** toggle (an eye-off icon button). Turn it on
  for a tag you drew but don't want to print - for example 1b and 1c once 1a alone is set up to
  show every variation - and the row greys with a **Not printed** pill. The tag stays open and
  editable; it only leaves [arranging the sheet](#arranging-the-sheet), the proof and the exported
  PDF. Turn it off again at any time to bring it back.
* The **Tag Size** panel is collapsed by default, showing the current size beside its heading (for
  example *95 x 44.5 mm*). Click the heading to open the preset, width/height, **Per A4** and
  **Apply to all lines** controls. It remembers whether you left it open the next time you design.
  **Per A4** shows the sheet fit worked out from the tag's own size - columns, rows and a **Turn**
  checkbox - greyed until you type your own numbers; **Auto** clears them back to the worked-out
  fit. A grid too small for the tag is refused with a message and the worked-out fit is used
  instead. See [Arranging the sheet](#arranging-the-sheet).
* On a combo tag, every layer that reads product data (the photo slot, code, name, specs, a price
  badge, a barcode, or a text layer with a product or spec token) offers a **Product** select in the
  Inspector. It lists the parent product first, then every product in the line's whole combo,
  grouped by role (for example *Kitchen Tap*) - not only the candidate this particular tag resolved
  to, so one tag can bind its slots to every variation and show all of them at once. The candidate
  this tag itself chose is marked **(this tag)**. Leave a layer on the parent (the default) for most
  layers - a single-product tag shows no **Product** select at all, since there's nothing to choose
  between. A price badge's select carries one extra first entry, **Tag total**, the parent plus this
  tag's own resolved parts added together - the default, and what a price badge has always shown,
  unchanged even when other slots on the same tag point at a different candidate. A layer pointed at
  a product has its name suffixed with that product's code in the **LAYERS** panel, so a scan of the
  list tells you which product each layer draws. Copying a design onto another tag with **Apply to
  all** falls a part-pointed layer back to the parent when the target has fewer parts, and names the
  layer in a toast.
* The merge field `{{product.price_tag_description}}` prints the text from the product's own
  **Price tag description** field verbatim, line breaks included; an empty field prints nothing. It
  sits in the Insert list under **Product**, right after **Spec lines**. See
  [Manage products](../product/manage-products.md) for where the field lives on the product.
* A spec merge field such as `{{spec.dim_length}}` now prints the number on its own, with no unit -
  type the unit into the layer text yourself, for example `L{{spec.dim_length}}XW{{spec.dim_width}}XH{{spec.dim_height}}mm`.
* On a layer whose **Content** holds a merge field, the Inspector shows the rendered text under the
  box with a **Copy rendered text** button, so you can copy exactly what will print without reading
  it off the canvas.
* On a price badge, the amount now follows the layer's own **Text Colour** setting (it used to stay
  black regardless); the empty placeholder still shows muted grey until a price resolves.
* A spec merge field such as `{{spec.material}}` prints a reader-friendly word - *Stainless Steel*,
  *PVC*, *Rose Gold* - instead of the stored code, with no change to the layer itself.

### Which photo prints

A product can have more than one image linked to it. The tag always uses the brochure image (the
one marked as the product's main photo) first. Failing that, a **Product Photos** image beats a
**Technical Specifications** drawing, so a product whose only linked photo happens to be a spec
drawing still gets it - nothing is filtered out, only ordered. The canvas, the portal preview and
the exported PDF all agree. A line whose combo carries its own cover picture puts that picture
first instead - see [What prints on the tag](price-tag-packages.md#what-prints-on-the-tag).

## Arranging the sheet

Arrange is automatic - there is nothing to lay out by hand. Sheets are always upright (portrait
A4). Tags are grouped by their printed size; each group packs edge to edge inside a 5 mm margin on
every side, turned 90 degrees when that fits more of them per sheet, and spills onto as many
further sheets as it needs. A request mixing sizes - two Kitchen Sink tags and thirty Small tags -
lays the Kitchen Sink tags out on their own sheet and the Small ones on the sheets after.

Each sheet in the Arrange view reads **\<template name\> - C x R, used of N**, for example
*Small Price Tag SP - 3 x 9, 27 of 30*. There are no page, bleed or gap fields to fill in, and
nothing to drag - the layout follows the tag's size on its own. A tag marked **Not printed** never
takes a slot and never appears on a sheet.

The **Tag Size** panel's **Per A4** control (see [In the designer](#in-the-designer)) decides the
grid for a size: leave it on **Auto** for the worked-out fit, or type your own columns, rows and
turn to force a specific layout.

## Changing a line's price

The salesperson's own **Promotion** pick or typed price can be wrong, or a promotion can move, by
the time you look at a request. Open the request and go to the **Lines** tab: in **Selling price**
mode, every product line carries its own **Promotion** select and **Selling price** cell, the same
rules as the portal form - pick from the promotions that cover the line, or type a price when none
does. A change saves on its own, no separate save button.

Changing a line's price re-resolves its tags. If the tag was already pinned (the request has been
claimed), the change shows up the same way any other product-data move does - see
[When product data changes](#when-product-data-changes).

These cells are read only once the request is terminal (**Collected**, **Rejected**, **Void**), or
for a viewer who can't process price tag requests.

## Working off change requests

The salesperson does not type a paragraph any more; they click on the tag and leave a numbered pin
where the problem is. You see those pins in two places.

**On the request page.** The pins are drawn over the design, and a **Change requests** list sits
under it. Each row names the tag the pin is on, the round it came from, who wrote it, and the text.
Press **Done** when you have fixed it; the pin and the text go grey. **Reopen** puts it back.

**In the designer.** Numbered markers sit over the matching tag on the canvas, everywhere that tag
appears on the sheet. Clicking a marker opens its comment and never selects a layer, so you can read
a comment without disturbing the design. The comment carries the same **Done** / **Reopen** button
the request page has, so you can close a pin right there without going back to the page. The
trailing toolbar button reads **Hide change requests (N open)** / **Show change requests (N open)**
and only appears when the request has comments. In the **LINES** rail an orange count sits on every
line that still has open pins.

While pins are open, the main button reads **Mark design ready (2 open)**. The count is a reminder,
not a block: press it anyway when a comment does not apply, and say so on the request instead.

Each time you mark the design ready, a new round starts. Earlier rounds stay on the design and draw
grey on the salesperson's side, so round two is read against what round one asked for.

A change request that covers the whole design rather than one spot arrives as a **General** row in
the same list.

## Printing and collection

**Printing** is on the record header (*Printing: Office prints* / *I print myself* /
*Printing: Not set*) and in the **Request** tab. Every request now arrives as **I print myself** -
the portal no longer asks the salesperson to choose. If a particular request needs office printing
instead, use the gear then **Edit request** and set it; you can do that any time the request is
still open.

Once the salesperson approves, the record's primary action is **Open design** - it takes you back
into the designer, and the per-tag **Design** buttons on the **Lines** tab come back too. Printing
and hand-over happen from the designer's own bar, in the slot **Mark design ready** occupied while
designing:

* **I print myself** - the designer's bar shows **Export PDF** only. The PDF export runs on its own
  and the salesperson downloads it from the portal.
* **Office prints** - the designer's bar shows **Export PDF** and, as the primary button,
  **Mark ready for collection**. Print the tags, then press it. The status becomes
  **Ready for collection**, the salesperson gets a WhatsApp, and the header shows
  *"Ready since <date> · auto-collects <date>"*.
* When the tags are handed over, press **Mark collected** (the salesperson can also do it from the
  portal). **Collected** is the end of the request.

**Mark ready for collection** is hidden while Printing is **Not set** - set it first.

A request nobody collects closes itself after the configured number of days, and the header then
reads *Collected <date> automatically*. See [Admin setup](#admin-setup).

## When product data changes

The tags are drawn from the product data as it was when the request went into designing, so a
price change, a new dealer image, an edited spec or an expired promotion never silently redraws a
design without you knowing. What happens next depends on how far the request has got.

**While the request is Designing or Changes Requested**, a change is applied to the tag
automatically - nobody has to click Update.

* The designer's **LINES** rail shows a red dot on the affected tag.
* The record header shows an amber **Product data updated · N** pill.
* Clicking the dot (or the pill's **Review**) opens the **Product data updated** dialog: one row
  per field, **Was** beside **Now**, with thumbnails for images.
* **Dismiss** clears the indicator and keeps the new values.
* **Roll back** puts the tag's data back to what it carried before the update. A rollback is itself
  saved as a version, so it can be undone from [Design history](#design-history) too.

**From Design Ready onward**, nothing changes by itself - the office is already reviewing or the
salesperson has already approved what is on the tag.

* The record header shows an amber **Product data changed · N** pill.
* The **Lines** tab shows a **Changed** pill on the affected row with a **Review** action.
* **Review** opens the **Product data changed** dialog: one row per field, **On the tag** beside
  **Now in the product**, and two answers: **Keep current** (the tag stays as drawn and the label
  goes away until the product changes again) or **Update tag** (the tag takes the new values,
  saving a version first, named *"Before product update: ..."*, so the previous state is never
  lost).

A finished request (self print approved, collected, rejected or void) is never checked for changes
and never shows the label.

Note: a marketing price override typed on the request still wins over the pinned offer price.

## Design history

**History** on the **Design** section, and the same entry in the designer's trailing toolbar, open
**History / PT-...**: every saved version, newest first, with the message it was saved under.

* **View** opens that version read-only in the full-screen viewer, drawn with the product data as it
  was at the time.
* **Restore** writes that version's design and product data back onto the request. It asks nothing
  first because it adds a version (*"Restored v3"*) rather than destroying one, so the way back is
  the list itself.

Versions are written when the design is saved, when the design is marked ready, and before an
**Update tag**.

## How you'll be notified

* **The salesperson** gets a WhatsApp at every status change, with a link back to the portal, plus
  one when the PDF finishes on a self-print request. Nobody in the office has to send it.
* **The assignee** gets a CRM bell notification on two events only: the salesperson asking for
  changes (*"PT-... - the salesperson asked for changes"*) and the salesperson approving
  (*"PT-... approved"*), both linking to the request. Repeats inside the same round do not
  duplicate.
* SLA notifications for a price tag request name the request by its **PT-YYYYMM-NNNN** number and
  link to the request page.

## Admin setup

Three settings sit behind this flow, and all of them are an admin job, not a per-request one:

* **[SLA Management → Form SLA Configuration](/sla-management/form-sla-config)** needs a
  **Price Tag Request** stage row for new requests to be assigned automatically and tracked. Without
  it, requests still arrive but sit unassigned. See
  [Form SLA Configuration](../sla/form-sla-configuration.md).
* **[User Management → Settings → General](/user-management/settings)** carries
  **Auto-mark price tags collected after (days)**: *"An office-printed request waiting to be picked
  up closes itself after this many days. 0 leaves it open."* Default 7, accepted range 0 to 90.
* **[System Management → WhatsApp Templates](/integration-management/whatsapp-templates)**,
  under **Default templates for auto-send**, carries a **Price Tag Request - Update** row. Set a
  template there so the salesperson still gets their status update when their 24 hour WhatsApp
  window is closed - without it, that update is silently skipped for anyone outside the window. Map
  a parameter to **Full update message** at minimum; add **Entity number** and **Portal URL** if the
  approved template carries them.

## See also

* [Project Sales Rep - Review a price tag design, ask for changes, approve and collect](../project-sales-rep/price-tag-request-review-and-collection.md) - the same flow from the salesperson's side.
* [Project Sales Rep - Submit via portal](../project-sales-rep/submit-via-portal.md#price-tag-request) - how the request is raised.
* [Catalogue packages on price tags](price-tag-packages.md) - combos, choice groups and the combo's own cover picture.
* [Manage products](../product/manage-products.md) - the Price tag description field on the product page.
* [Configure Portal Revisions](../user-management/configure-portal-revisions.md) - letting a dealer revise a submitted price tag request.
* [Form SLA Configuration](../sla/form-sla-configuration.md) - the stage rules that assign and time a request.
