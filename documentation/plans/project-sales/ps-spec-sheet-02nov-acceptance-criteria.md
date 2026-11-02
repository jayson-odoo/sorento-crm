# UAC: Project spec sheet from templates (PS-SPEC-SHEET)

**Status:** Final for build. From card v2 (`CARD-ps-spec-sheet-02nov.md`) with the crew answers of
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

## B. Spec sheet tab (quotation document)

- **B1** Every quotation document (proposal or quotation) has a "Spec sheet" tab, last after
  Signatures, at `/spec-sheet`.
- **B2** With no issued revision the tab says "No issued revision yet" / "A spec sheet prints what
  the customer received. Issue a revision first." and Export PDF is off with that reason as its
  tooltip.
- **B3** With no published spec templates the tab says "No spec sheet templates" with where to
  publish them. Export PDF stays off ("Pick a cover template and a page template first.") until a
  cover and a page template are picked.
- **B4** Pickers: Revision (latest by default), Cover template, Page template, Single item template
  (optional; empty = the page template). Only published templates of the right family are listed,
  with their size.
- **B5** One row per item of the chosen revision, after the cover, in quotation order (scope order,
  then line order). An item is a line with a product or a product set; the same product or set
  twice prints once, at its first position.
- **B6** A set line's row shows its driver part as the item and "With <other part codes>"; those
  parts print as accessory rows.
- **B7** Accessories: other items of the revision can be hand-picked onto a row. A picked item
  leaves its own row and prints after the set parts. An item cannot be its own accessory, an item
  that hosts accessories cannot be picked, and an item sits on one page only (422 otherwise).
- **B8** Area (free text with this sheet's earlier areas as suggestions, printed upper case),
  Comment and Marker (free text) and Print (on/off) save by themselves per row; drag reorders the
  pages. All are kept per item, so a new revision keeps them.
- **B9** The page numbers on the rows count only printed pages (the cover is page 1).
- **B10** A Preview shows the pages exactly as the PDF prints them, one at a time with
  Previous / Next and "Page N of M".
- **B11** Export PDF queues the file; the toast says "Preparing the spec sheet. It will appear in My
  Downloads." The file is `spec-sheet-<quotation no>.pdf`, page size = the templates' size.
- **B12** A user with view but not edit sees everything and can preview and export, but cannot
  change pickers or rows (PUT answers 403).
- **B13** Templates of different sizes refuse export: "Page templates must be the same size as the
  cover." (422).

## C. Printed pages

- **C1** Page 1 is the cover template. Then one page per printed row: the page template when the
  page has accessories, else the single item template.
- **C2** Price (owner Q-B, 2 Nov 23:29): a page prints the issued line's quoted unit price ONLY where
  the template places a price (the price tag designer's List Price slot or a list-only price badge,
  on the main item or, for a hand-picked accessory, on that accessory). A set's parts carry no price
  of their own. A template with no price layer prints no price anywhere (the owner's sample).
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
