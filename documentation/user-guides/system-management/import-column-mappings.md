# Import column mappings

Every supplier upload (proforma invoice, packing list) reads its Excel headers against a table of
known column names per system field, in Chinese and English. This page is where those mappings
live, and where a header the readers don't yet recognise gets added.

## Steps

1. Open **[System Management → Import Column Mappings](/system-management/import-field-aliases)**.
2. Pick the **Document type**.
3. The grid lists every **System field** for that document type and the **Headers on file**
   already mapped to it, as chips.
4. Click **Add mapping**. Pick the **System field**, type the **Header** exactly as it appears on
   the supplier's sheet, and optionally its **Locale**. Click **Add mapping** again to save.
5. To remove a mapping, click the chip's remove control - it's a deferred, reversible delete (a
   few seconds to cancel), the same as elsewhere in the CRM.

Editing a mapping here is admin-only. A purchasing user who hits an unmapped header during upload
maps it inline from the upload dialog's **Map to...** chip - that write lands here too and is
remembered for every later upload.

## What's captured

Doc type, the system field it resolves to, the exact header text, and an optional locale.

## See also

* [Upload a proforma invoice (and its packing list)](../purchasing/upload-proforma-invoice.md)
