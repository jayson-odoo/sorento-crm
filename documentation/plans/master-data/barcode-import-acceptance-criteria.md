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
