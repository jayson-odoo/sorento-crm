# Product Management — Units of measure

Maintain the units of measure (UoM) products are stocked and sold in — e.g. *Each*, *Box*, *Carton*, *Kilogram*. Every product must have a **Base Unit of Measure**.

Open **[Product Management → Units of Measure](/master-data-management/units-of-measure)** (URL: `/master-data-management/units-of-measure`). The page is titled **Units of Measure**.

## The list

Columns: **UOM Code**, **UOM Name**, **Base UOM**, **Conversion Factor**, **Status**.

* **Search UOMs...** — matches code / name.
* **Create UOM** — opens the UoM form.

## Create / edit a unit of measure

The form fields:

* **UOM Code \*** — required, up to 50 characters; letters, numbers, dashes, underscores only; unique.
* **UOM Name \*** — required, up to 150 characters.
* **Base UOM** — optional. Set this when this unit is a *derived* unit of another (e.g. *Box* whose base is *Each*). Leave empty for a standalone base unit.
* **Conversion Factor** — optional positive number (up to 4 decimal places). How many base units one of this unit equals (e.g. a *Box* with base *Each* and factor `12` = 12 each).
* **Description** — optional, up to 2000 characters.
* **Active** — switch.

There is a UoM **detail** page (`/master-data-management/units-of-measure/{id}`), and **new**/**edit** pages.

## Delete a unit of measure

Use the per-row **Delete** action → confirmation dialog. **Hard delete, cannot be undone.** A UoM still set as the base unit of a product cannot be removed while products reference it.

## How products reference UoM

On the product form's **Specifications** tab, **Base Unit of Measure \*** is required and chosen from the UoM list (displayed by **UOM Code**). See [Manage products](manage-products.md).

> **Base UOM + Conversion Factor model the relationship between units, not product packaging quantities.** A unit points to its base via `base_uom_id` and the multiplier via `conversion_factor`. Per-product pack sizes are not stored here.

## See also

* [Manage products](manage-products.md)
* [Product categories & brands](product-categories-and-brands.md)
* [Product Management — Data analysis for the AI assistant](data-analysis.md)
