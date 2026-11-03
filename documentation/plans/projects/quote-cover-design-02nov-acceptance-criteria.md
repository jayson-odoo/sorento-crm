# UAC: Quotation cover page designer (QUOTE-COVER-DESIGN)

**Status:** Final. Owner answered card v3 on 2 Nov 19:46 (Q1 a, Q2 a, Q3, Q4 a, Q5 a). Plan:
`PLAN-quote-cover-design-02nov.md`. Mock: `documentation/mockups/QUOTE-COVER-DESIGN/index.html`.

"Design" = a cover page template. "Default design" = the #2088 cover: 12 rows with the #2088 labels, title QUOTATION,
letterhead on, no intro, no closing.

## A. Designing (Project Sales > Configuration > Quotation Templates)

- **A1** The page has line tabs **Terms** and **Cover page**. Terms works exactly as today.
- **A2** Cover page lists the designs the same way Terms lists templates: name, Active/Inactive, Activate, Add. The
  first design added becomes active. One design is active per company. Activating a design never changes the active
  terms template.
- **A3** The design editor shows: Name; Title (default QUOTATION); Show company letterhead (switch, default on); the 12
  rows (Reference No., Date, Attn, Company, Contact, Add, Email, Quotation Purpose, Terms & Conditions, Payment Terms,
  Validity, Prepared By), each with a tick to show, a drag handle to reorder, and a printed label (default = today's
  label); Intro text and Closing text editors with an **Insert field** list of the existing merge fields; and a live
  preview of page 1 filled with a sample quotation, which updates as the form changes.
- **A4** No custom rows can be added. A label or the title holds at most 60 characters. A field token the system does
  not know is refused with a message. A name is required.
- **A5** Same permissions as the Terms templates today (view the page / edit to change).

## B. On a quotation

- **B1** A new quotation copies the active design's intro and closing, with fields filled in (as the old letter was).
  Both stay editable for this quotation only.
- **B2** The **Cover letter** tab shows the cover page as it will print: the design's title, letterhead, rows (order,
  labels, empty rows left out), intro and closing, with the quotation's current values. The reference shows the next
  revision number. In edit mode it also shows the **Intro text** and **Closing text** editors, and the preview follows
  unsaved changes on any tab. In view mode it shows the preview only.
- **B3** The old free-text letter is the intro: an existing quotation's letter text shows and prints as its intro.
- **B4** With no active design, everything follows the default design (#2088 look). Nothing errors.
- **B5** Usable and not clipped at 375px and 1280px. The preview scales to the width.

## C. Sent quotations (PDF and customer sign link)

- **C1** A revision sent after release prints page 1 from the design copied at send: letterhead per the switch, the
  title, the shown rows in the design's order with its labels (upper-case with a colon on the PDF), the intro above the
  rows and the closing below. Empty rows are still left out. The intro is not printed again on page 2.
- **C2** When the Terms row is not shown, the terms print after the price table (as written, with the #2088
  cleaning, never auto-numbered) and the sign page shows its bottom Terms and conditions panel. When it is shown, they print on page 1 only
  (#2088 rule).
- **C3** The sign link shows the same card: title, letterhead per the switch, rows, intro, closing.
- **C4** The design, intro and closing are copied onto the revision when it is sent. Editing, deactivating or
  activating designs afterwards never changes a sent revision's PDF or sign link.

## D. Earlier revisions

- **D1** Revisions sent before #2088 (layout 1) and with #2088 (layout 2) re-download and open exactly as before.

## E. Safety

- **E1** Intro and closing reach the PDF and the sign link only through the #2088 terms cleaning (allow-listed tags,
  escaped text). Every label and the title are escaped.
- **E2** The preview endpoints store nothing and need the same permission as the screen they serve.
