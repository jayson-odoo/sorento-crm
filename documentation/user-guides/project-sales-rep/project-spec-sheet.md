# Project spec sheet (project catalogue)

Use this when a customer's QS or consultant wants the project catalogue: a cover page, then one page per item you quoted, each with the photo, the drawing, the code and specs, its valve, hose or trap, and a title block with the project, ref, area, your name and the date. A price prints only if the template has a price area (see below).

The pages are designed once by marketing as templates (see "Designing the templates" below). You only choose the templates, check the pages (type an area where the Section heading is not right), and export.

## Steps

1. Open the project, then the quotation (proposal or quotation) under **Quotation**.
2. Click the **Spec sheet** tab (after **Signatures**).
3. **Revision**: the latest issued revision is picked for you. Pick an older one if the customer is working from it. A quotation that was never sent shows **No issued revision yet**: issue a revision first.
4. Pick the **Cover template** and the **Page template**. **Single item template** is optional: when set, an item with no accessories uses it; when empty, every page uses the page template.
5. The pages show as a strip of thumbnails, the cover first, then one page per quoted item in quotation order. Click a thumbnail to open that page large, exactly as it prints (**Previous** / **Next** walk the strip). On the open page:
   - **AREA**: starts as the **Section heading** the line sits under on the **Lines** tab (for example `UNIT`). Click it on the page to type something else, for example `UNIT & PODIUM FACILITIES`; it prints in capitals.
   - **COMMENT** and the marker next to the code: click them on the page to type.
   - **Leave out**: the page is not printed (for example a sealant); it stays in the strip, greyed, with **Put back**. The quotation is not changed.
   - **Add accessory**: puts another quoted item on this page instead of its own page (for example a bottle trap under a basin). A product set (a WC with its angle valve and flexible hose) brings its other parts by itself.
   - Drag a thumbnail to change the page order.
   Every change saves by itself and stays with the quotation, so the next revision keeps it.
6. Click **Export PDF**. The file is prepared in the background and appears in **My Downloads** as `spec-sheet-<quotation no>.pdf`.

## What's printed

* Page 1: the cover template as designed (for example a photo collage and the logo).
* One page per printed item: the main item's photo and drawing (as frozen on the issued revision), brand, code, name and specs, and up to the number of accessory rows the template has.
* Title block fields come from the quotation: **Ref** is the quotation's Your ref, or our quotation number when Your ref is empty; **Prepared by** is the quotation's signatory (else the project salesperson) with their phone; **Date** is the revision's issue date.
* **Price**: only when the template has a price area: the quoted unit price of that item on the revision (the item's own price, not added up with its accessories). An item quoted at zero prints no price. An item quoted twice at two prices shows the first one. The sample catalogue has none.
* The same product quoted twice (for example in two blocks) prints once.

## Who can do what

* Anyone who can see the project can open the tab, preview and export.
* Changing the templates or the rows needs the right to edit the quotation.

## Designing the templates (marketing)

1. **Dealer Kit**, **Tag Templates**, **New Template**. Family **Spec sheet cover** for the cover, **Spec sheet page** for item pages. Give the size in mm (the sample catalogue is 338.7 x 190.5, 16:9). The cover and every page template must be the same size.
2. Design the page as any tag template. **Insert field** has a **Spec sheet** group: Brand, Area, Comment, Marker, Project title, Ref, Your ref, Quotation no, Prepared by, Prepared by phone, Date.
3. For the drawing, bind an image layer to **Drawing** under **Slot Binding**.
4. For an accessory row, point its photo and text layers at **Accessory 1** (or 2, 3) under **Product**, and set **Show only when** to **Accessory 1 exists** on the row's frame, so a page with fewer accessories prints no empty row.
5. For a price, bind a text layer to **List Price** under **Slot Binding** (or add a list-only price badge); it prints the item's quoted unit price. Leave it out for a catalogue without prices. Anything you place that is not tied to the item (a band with the project details, a logo, a frame) repeats on every page.
6. For a badge (Rimless, Accessible), set **Show only when** to the spec, for example **Rimless is Yes**. Mark a product **Accessible (OKU)** under its Product Specifications.
7. **Publish**. Only published templates are offered on the Spec sheet tab. Spec sheet templates are never offered on price tag requests.

## How you'll be notified

* A toast says **Preparing the spec sheet. It will appear in My Downloads.**, and the file shows in **My Downloads** when ready.

## See also

* [Working a project quotation](./work-a-project-quotation.md)
* [Price tag requests (marketing)](../marketing/price-tag-requests.md)
