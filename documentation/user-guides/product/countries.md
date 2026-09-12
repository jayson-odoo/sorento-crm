# Product Management - Countries

Maintain the list of countries suppliers (and later customers/users) are set to - e.g.
**Malaysia**, **China**, **Singapore**. Seeded with the full ISO country list, so most of the
time you are not adding a country, just checking one exists.

Open **[Products → Reference Data → Countries](/master-data-management/countries)** (URL:
`/master-data-management/countries`). The page is titled **Countries**.

## The list

Columns: **Code**, **Name**, **Active**.

* **Search countries...** - matches code or name.
* **Add Country** - opens the add form.

Clicking a row opens the same form in edit mode.

## Add / edit a country

The dialog is titled **Add country** (or **Edit country**):

* **Code** - required, exactly 2 letters (e.g. `MY`). Stored upper case. A code that already
  exists is refused, whatever the case.
* **Name** - required (e.g. `Malaysia`).
* **Active** - switch.

Click **Create** (or **Save changes**) to save.

## Delete a country

Use the per-row **Delete** action. Deleting asks nothing up front - the row dims and a toast
counts down with **Cancel**; the delete only commits once the countdown lapses, even if you
close the tab. **A country still set on any supplier cannot be deleted** - the countdown is
refused and the row stays, with the toast naming how many suppliers reference it. Remove or
change those suppliers' **Country** first.

## Who can see and change this

**Countries** is visible to any role that can already view **Units of Measure** or
**Suppliers** - it is shared reference data, not a separate permission to request. Adding,
editing or deleting a country needs a role with **Manage Reference Data**.

## How suppliers use it

On the supplier form, **Country** is a searchable dropdown fed by this list - see
[Manage suppliers](../procurement/manage-suppliers.md#country). The supplier-master upload
also accepts a country by name or by its 2-letter code (case-insensitive); a value that does
not match anything here is left blank on that row and reported as a warning, without stopping
the rest of the file from importing.

## See also

* [Units of Measure](units-of-measure.md)
* [Manage suppliers](../procurement/manage-suppliers.md)
* [Upload the product master](../purchasing/upload-product-master.md)
