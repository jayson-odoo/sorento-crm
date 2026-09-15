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
  select that tag, no separate `1a` row underneath.
* The **Tag Size** panel is collapsed by default, showing the current size beside its heading (for
  example *95 x 44.5 mm*). Click the heading to open the preset, width/height and **Apply to all
  lines** controls. It remembers whether you left it open the next time you design.
* A spec merge field such as `{{spec.dim_length}}` now prints the number on its own, with no unit -
  type the unit into the layer text yourself, for example `L{{spec.dim_length}}XW{{spec.dim_width}}XH{{spec.dim_height}}mm`.
* On a layer whose **Content** holds a merge field, the Inspector shows the rendered text under the
  box with a **Copy rendered text** button, so you can copy exactly what will print without reading
  it off the canvas.
* On a price badge, the amount now follows the layer's own **Text Colour** setting (it used to stay
  black regardless); the empty placeholder still shows muted grey until a price resolves.

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
*Printing: Not set*) and in the **Request** tab. The salesperson chooses it when they submit. If it
is wrong or missing, use the gear then **Edit request** and set it; you can do that any time the
request is still open.

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

The tags are drawn from the product data as it was when the request went into designing, and that
snapshot stays put. A price change, a new dealer image, an edited spec or an expired promotion does
not silently redraw a design somebody is already reviewing. It also means a tag keeps the old price
or the old promotion until somebody decides otherwise.

When master data has moved since the snapshot, the request says so:

* The record header shows an amber **Product data changed · N** pill, and **Update all** next to it
  when more than one line changed.
* The **Lines** tab shows a **Changed** pill on the affected row with a **Review** action.
* The designer's **LINES** rail shows a red dot on the line (*"Product data changed - review"*).

**Review** opens the **Product data changed** dialog: one row per field, the value **On the tag**
beside the value **Now in the product**, with thumbnails for images and a note such as
*"promotion ended"* when an offer price has disappeared. Two answers:

* **Keep current** - the tag stays as drawn and the label goes away until the product changes again.
* **Update tag** - the tag takes the new values. A version is saved first, named
  *"Before product update: ..."*, so the previous state is never lost.

**Update all** applies **Update tag** to every changed line at once.

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
* [Configure Portal Revisions](../user-management/configure-portal-revisions.md) - letting a dealer revise a submitted price tag request.
* [Form SLA Configuration](../sla/form-sla-configuration.md) - the stage rules that assign and time a request.
