# UAC: Import barcodes (BARCODE-IMPORT)

1. Products list > Actions shows "Import barcodes" to a user with `master_data.products.edit`.
2. The dialog accepts .xlsx and .csv with a product code column and a barcode column; header
   names are matched case-insensitively from a known list (e.g. "Product Code", "Item Code",
   "Code"; "Barcode", "EAN", "UPC"). The preview names the columns used.
3. Preview shows counts on top and one row per file line with status: New, Change (old -> new),
   Same, Unknown code, Blank barcode, Too long (error), plus warnings Duplicate and
   Not EAN-13 valid. Nothing is written by preview.
4. Apply writes only New and Change rows, in one transaction, and returns counts.
5. Each changed product gets an audit_logs row (old and new barcode).
6. Both endpoints return 403 without `master_data.products.edit`.
7. A template file is downloadable from the dialog.
8. Dialog is usable at 375px and 1280px.

## Audit round (crew audit 21 Oct 09:50 + owner rulings 10:55)

9. The header "Barcode (EAN-13)" is read as the barcode column; a column whose header names
   an image ("Barcode Image") is never the barcode or code column.
10. A barcode cell holding scientific-notation text ("9.55103E+12") is skipped with its own
    status and a row note; it is never written.
11. A duplicate barcode (on another product or twice in the file) is a warning that names the
    product(s) already holding it; it never blocks the row. A Note/Remark column, when present,
    is shown beside the row.
12. Apply is only possible after a Test of the same file: the button stays disabled until a
    preview of the selected file has come back, picking another file clears it, and the server
    refuses an apply whose preview token does not match the file, the user and the
    active company (a token from SRT fails in MCH).
13. The preview names the active company ("Importing into: <company>"); the owner runs the same
    file once per company (SRT, then MCH).
14. A 12k-row file previews without freezing: the table shows rows needing attention first
    (toggle to show all), paged 50 at a time; apply writes in chunks inside one transaction.
15. Size limits (security review 21 Oct): a sheet reaching past row 1,048,576, more than
    50,000 non-empty data rows, more than 20 MB of workbook XML (pictures under xl/media/ do
    not count) or an unreadable file is refused with a plain 400. Only the first 64 columns
    and the first 10 sheets are read, the sheet's declared size is not trusted, and each cell
    is cut to 256 characters. Parsing runs off the event loop.
