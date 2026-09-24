# Import column mappings

Every supplier upload (proforma invoice, packing list) reads its Excel headers against a table of
known column names per system field, in Chinese and English. This page is where those mappings
live, and where a header the readers don't yet recognise gets added.

The same page also holds the **Stock list words** vocabulary a stock-list upload uses to build a
product code when a supplier's own 型号 column is a bare model number - see "Stock list words"
below.

## Steps

1. Open **[System Management → Import Column Mappings](/system-management/import-field-aliases)**.
2. Pick the **Document type**.
3. The grid lists every **System field** for that document type and the **Headers on file**
   already mapped to it, as chips. A chip mapped only for one supplier carries that supplier's
   name as a second badge beside it; a chip with no supplier badge applies to every supplier. A
   column somebody chose to skip on the upload mapper groups under **Ignored** instead of a
   field name, so it can still be found and removed.
4. Click **Add mapping**. Pick the **System field**, type the **Header** exactly as it appears on
   the supplier's sheet, and optionally its **Locale**. Click **Add mapping** again to save.
5. To remove a mapping, click the chip's remove control - it's a deferred, reversible delete (a
   few seconds to cancel), the same as elsewhere in the CRM.

Adding a mapping here by hand is admin-only, and it's rarely needed anymore for **Proforma
invoice** and **Packing list**. The first time a purchasing user drops one of those files on
**Upload supplier documents**, a column-mapping panel on that dialog lets them pick the field for
each column (or **Ignore**) right there; saving it there writes the same supplier-scoped rows
this page lists, so this is where you review a supplier's saved layout afterwards, or delete a
mapping (including an Ignore) that turned out to be wrong. See [Upload a proforma
invoice](../purchasing/upload-proforma-invoice.md) for that inline mapper.

**Plan a container**'s stock-list upload has the same kind of column-mapping panel (samples,
header text, field picker, **Ignore**, a saved-layout fold, a **Header row** stepper) - see
[Loading Plan - Start a plan](../supply-chain/loading-plan.md) - but its per-supplier column
choices are not one of the **Document type** options here, so they aren't reviewed on this page;
what this page does hold for a stock list is the separate **Stock list words** vocabulary below.

## Stock list words

Pick **Stock list words** as the **Document type**. This is the vocabulary a stock-list upload
uses to compose our product code when a supplier writes a bare model number (e.g. `8613`,
`8066-PP`, `-7055`) in their 型号 column instead of our own code. The reader builds the code from
the sheet's 商标 (brand), 品名 (product type), 型号 (model) and 规格 (trap size) columns, word by
word, using this list to translate each supplier word into our token - for example SORENTO +
连体马桶 + 8613 + 150mm becomes `SRTWC8613-150`.

1. Click **Add mapping**.
2. Type the token our system should use as the **System field** - uppercase letters and digits
   only, up to 10 characters (e.g. `SRT`, `WC`, `HP`).
3. Type the supplier's word as the **Header** - exactly as it appears on their sheet (e.g.
   `SORENTO`, `连体马桶`, `横排`).
4. (Optional) Pick a **Supplier** to scope the word to that supplier only. Leave it blank
   (**Shared - every supplier**) for a word every supplier's sheet can use the same way.
5. Click **Add mapping** to save.

A supplier-scoped word wins over a shared word with the same header, for that supplier's uploads.
The list already comes seeded with the common brand and product-type words (SORENTO/S, CABANA/C,
MOCHA/M for brand; 连体马桶/分体马桶, 座头/分体座头, 水箱, 盆/盆小孔, 盖板 for product type; 横排
for trap layout) - add any word your suppliers use that isn't already there.

If a word on a supplier's sheet isn't in this list yet, that row is left as the raw text the
supplier wrote and shows up on the **Supplier codes** tab of the loading plan waiting for a
manual pick, the same as any other unmatched row. Editing or adding a word here only affects the
*next* upload - a manual pick already made under the old wording may need to be made again.

You can also reach this page from a loading plan's **Supplier codes** tab, via its
**Stock list words** link.

## What's captured

Doc type, the system field it resolves to, the exact header text, an optional locale, and (for
Stock list words) the supplier the word is scoped to, or none for a shared word.

## See also

* [Upload a proforma invoice (and its packing list)](../purchasing/upload-proforma-invoice.md)
* [Loading Plan - stock list upload and Supplier codes](../supply-chain/loading-plan.md)
