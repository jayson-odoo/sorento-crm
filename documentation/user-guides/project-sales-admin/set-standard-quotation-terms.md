# Set the standard terms and conditions for quotations

Use this when every new quotation should start with the same terms and conditions, payment terms
and validity.

## Steps

1. Open **Project Sales**, then **Configuration**, then **Quotation Templates**. You need the project setup permission to see the page; editing needs the edit permission.
2. Select **Add template** and type a **Name**.
3. Type the company's usual **Payment Terms** (for example *30 days from invoice date*) and **Validity** (for example *30 days from quotation date*). Both are optional.
4. Write the terms in **Terms and conditions**. Use headings in bold, blank lines between blocks, and the bullet list button for bullets (press Tab inside a bullet to indent it).
5. Select **Add template**. The first template you add becomes the active one.
6. To change which template new quotations use, find the inactive one in the list and select **Activate**. The previous one becomes **Inactive**.
7. To change wording, payment terms or validity, select the row, edit, and select **Save changes**.

## What's captured

* Each template keeps its name, its payment terms, its validity, its wording and whether it is **Active**. One template is active at a time.
* A new quotation copies the active template's wording, payment terms and validity when it is created.

## Good to know

* Quotations that already exist keep what they were created with. Editing or activating a template never changes them. Edit the quotation itself if that one needs a change.
* The terms print on the quotation's cover page exactly as written: headings, blank lines and bullets (indented bullets too) stay as you typed them, and nothing is numbered for you. If you want numbered clauses, use the numbered list button. Bold text prints bold.
* **Validity** is printed for the customer only. The customer's sign link keeps working after it.
* Quotations sent before the cover page existed keep their old layout, with numbered clauses after the total.

## Design the cover page

Use this to set how page 1 of every quotation looks (the cover page), for the PDF and the customer's sign link.

1. Open **Project Sales**, then **Configuration**, then **Quotation Templates**, and click the **Cover page** tab.
2. Select **Add**, type a **Name**, and set the **Title** (for example *QUOTATION*).
3. Turn **Show company letterhead** off if the cover page should start without the logo and company name.
4. In the row list, tick the rows to show, drag a row by its handle to move it, and type a new printed name beside it if needed (for example *ATTENTION* instead of *ATTN*). If you untick **Terms & Conditions**, the terms print after the price table instead.
5. Write the **Intro text** (above the rows) and **Closing text** (below the rows). Use **Insert field** to add a field such as the project name; it is filled in on each quotation.
6. Watch the preview on the right: it shows page 1 with a sample quotation. Save.
7. The first design you add becomes active. To switch, select **Activate** on another design. One design is active at a time; the terms template is not affected.
8. To go back to the standard cover page, select **Deactivate** on the active design. An inactive design can then be deleted.

* New quotations copy the active design's intro and closing text; sales can change them per quotation on the **Cover letter** tab.
* Each sent quotation keeps the design it was sent with. Editing or switching the design never changes a quotation already sent.
* With no design, the standard cover page is used.

## See also

* [project-sales-rep/work-a-project-quotation.md](../project-sales-rep/work-a-project-quotation.md) for filling the cover page and sending a quotation.
