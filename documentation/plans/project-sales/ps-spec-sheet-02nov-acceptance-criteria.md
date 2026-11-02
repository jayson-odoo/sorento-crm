# UAC: Project spec sheet from templates (PS-SPEC-SHEET)

**Status:** Final for build (section B rewritten for mock v5, 3 Nov). From card v2 (`CARD-ps-spec-sheet-02nov.md`) with the crew answers of
2 Nov (Q1 c, Q2 both refs, Q3 set parts + hand-pick, Q4 a, Q5 a) and the owner's marker ruling
(21:45: no fixed meaning; the designer places markers). Plan: `PLAN-ps-spec-sheet-02nov.md`.
Mock: `documentation/mockups/PS-SPEC-SHEET/index.html`.

## A. Templates (Dealer Kit > Tag templates)

- **A1** New template families "Spec sheet cover" (`spec_cover`) and "Spec sheet page"
  (`spec_page`) can be picked when creating a template. Any size in mm (the owner's sample is
  338.7 x 190.5 mm).
- **A2** On a spec sheet template, Insert field offers a "Spec sheet" group: Brand, Area, Comment,
  Marker, Project title, Ref (your ref, else quotation no), Your ref, Quotation no, Prepared by,
  Prepared by phone, Date. A price tag template does not offer that group.
- **A3** Slot Binding offers "Drawing" (the technical drawing) beside Product Image.
- **A4** On a spec sheet template every product-reading layer can point at Main item or
  Accessory 1 / 2 / 3, without previewing a combo.
- **A5** On a spec sheet template a layer has "Show only when": Accessory N exists, and / or a spec
  is Yes (e.g. Rimless, Accessible (OKU)). The canvas always draws the layer.
- **A6** Spec sheet templates never appear in a price tag request's template picker, its family
  default, or its size presets.
- **A7** "Accessible (OKU)" is a Yes/No spec right after Rimless in Product Specifications.

## B. Spec sheet tab (quotation document): the pages are the editor (owner, mock v5, 3 Nov 00:14)

- **B1** Every quotation document (proposal or quotation) has a "Spec sheet" tab, last after
  Signatures, at `/spec-sheet`. There is no table of rows.
- **B2** With no issued revision the tab says "No issued revision yet" / "Issue a revision first."
  and Export PDF is off with that reason as its tooltip.
- **B3** With no published spec templates the tab says "No spec sheet templates" with where to
  publish them. Export PDF stays off ("Pick a cover template and a page template first.") until a
  cover and a page template are picked.
- **B4** Pickers: Revision (latest by default), Cover template, Page template, Single item template
  (optional; empty = the page template). Only published templates of the right family are listed,
  with their size.
- **B5** A strip of page thumbnails, drawn as they print: "1 Cover", then one page per item of the
  chosen revision, in quotation order (scope order, then line order) until reordered. An item is a
  line with a product or a product set; the same product or set twice prints once, at its first
  position. A left-out page shows "Left out" and "-" for its number; the numbers count printed
  pages only.
- **B6** Clicking a thumbnail opens that page large, as it prints ("Page N: <code>"); Previous /
  Next walk the strip.
- **B7** AREA starts as the Section heading the line sits under on the Lines tab (blank when it has
  none). Clicking AREA on the open page types over it (saved upper case); clicking COMMENT or the
  marker types those. Only the template's layers that print `{{line.area}}`, `{{line.comment}}` or
  `{{line.marker}}` are clickable. An AREA left equal to its Section heading is not stored as typed,
  so it follows the heading.
- **B8** "Leave out" on the open page removes it from the PDF (it stays in the strip, greyed); "Put
  back" returns it.
- **B9** "Add accessory" on the open page picks other items of the revision; a picked item leaves its
  own page and prints after the set parts. A set line's other parts are accessories by themselves.
  An item cannot be its own accessory, an item that hosts accessories cannot be picked, and an item
  sits on one page only (422 otherwise).
- **B10** Dragging a thumbnail reorders the pages (mouse, or Space / arrows / Space on its handle).
- **B11** Every change saves by itself, keyed by item, so a new revision keeps it.
- **B12** Export PDF queues the file; the toast says "Preparing the spec sheet. It will appear in My
  Downloads." The file is `spec-sheet-<quotation no>.pdf`, page size = the templates' size.
- **B13** A user with view but not edit sees the strip and the pages and can export, but gets no
  edit spots, no Leave out / Add accessory and no drag (PUT answers 403).
- **B14** Templates of different sizes refuse export: "Page templates must be the same size as the
  cover." (422).

## C. Printed pages

- **C1** Page 1 is the cover template. Then one page per printed row: the page template when the
  page has accessories, else the single item template.
- **C2** Price (owner Q-B, 2 Nov 23:29): a page prints the issued line's quoted unit price ONLY where
  the template places a price (the price tag designer's List Price slot or a list-only price badge,
  on the main item or, for a hand-picked accessory, on that accessory). A set's parts carry no price
  of their own, and a zero-priced line (no separate charge) prints no price, as on the quotation PDF.
  A template with no price layer prints no price anywhere (the owner's sample).
- **C3** The main item prints the issued line's frozen photo and drawing (else the product's chosen
  photo / first drawing); an accessory prints its product's photo and first drawing.
- **C3a** Any fixed layer anywhere on the page (the sample's right band, a top or bottom band)
  repeats on every page (owner Q-C); the right band carries the project details (owner Q-A).
- **C4** Ref prints the quotation's Your ref, or the quotation number with revision when Your ref is
  blank. Prepared by / phone = the quotation's signatory, else the project owner. Date = the
  revision's issue date as `02 NOV 2026`.
- **C5** A layer pointed at an accessory the page does not have prints nothing (never the main item
  again); a layer with "Show only when Accessory 2 exists" disappears on a page with one accessory.
- **C6** A layer with "Show only when Rimless is Yes" prints only for an item whose Rimless spec
  is Yes.

## D. Unchanged

- **D1** Price tag requests, their designer, preview and PDF print exactly as before (A4 portrait,
  same layers, parts fall back to the parent as before).
