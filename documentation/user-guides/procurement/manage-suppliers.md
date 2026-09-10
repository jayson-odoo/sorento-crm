# Procurement - Manage suppliers

Create, edit, and delete the vendors you buy from. Use this when you need to add a new supplier, fix a supplier's details, or remove one.

## Where

[**Procurement → Suppliers**](/procurement-management/suppliers). The list shows columns **Supplier Code**, **Supplier Name**, **Contact Person**, **Phone**, **Email**, **Country**, and **Status** (**Active** / **Inactive**). A supplier with no country set shows "-". Use the search box to find a supplier by code or name. Click any row to open its detail page.

## Add a supplier

1. On the Suppliers list, click **Create Supplier** (top-right). This opens a full create page.
2. Fill the form. It's grouped into three sections:
   * **Basic Information** - **Supplier Code** *, **Supplier Name** *, **Contact Person**, **Email**, **Phone Number**, **Website**.
   * **Address Information** - **Address Line 1**, **Address Line 2**, **City**, **State/Province**, **Postal Code**, **Country**.
   * **Payment Terms** - **Payment Terms (Days)** * (defaults to 30) and **Active Status**.
   Fields marked * are required.
3. Click **Create Supplier** to save. You'll return to the list with the new supplier added.

### Country

**Country** is a clearable, searchable dropdown - type to search, pick from
**[Products → Reference Data → Countries](../product/countries.md)**, or clear it back to
empty. It is not free text: a supplier can only carry a country that already exists on that
list, so add the country there first if it is missing.

Whether a supplier already has its country set depends on when it was created: a one-time
script set **Country** to **Malaysia** for existing suppliers whose name already read as
Malaysian (containing `SDN BHD`, `(KL)`, or `MALAYSIA`); every other existing supplier has no
country until someone sets it here or the AutoCount integration sends one (see
[System Management - Data analysis for the AI assistant](../system-management/data-analysis.md)).

A **Supplier Code** that differs from one you already hold only by case or spacing (e.g. `abc`
vs `ABC`) is refused with *"Supplier code already exists."* rather than silently creating a
near-duplicate - the same check applies to warehouses, product categories and units of measure.
A trailing currency note in the **Supplier Name**, e.g. `ACME (RMB)`, is stripped automatically
on both create and edit - the stored name is `ACME`.

## Edit a supplier

1. Open the supplier from the list (click its row).
2. On the detail page, click **Edit**.
3. Change any field and click **Update Supplier**. Note: **Supplier Code** is set at creation - edits cover name, contacts, address, payment terms, and active status.

> Set **Active Status** to inactive instead of deleting if you've stopped buying from a supplier but want to keep its history and links. Inactive suppliers stop appearing in pickers (e.g. when allocating shipments) but stay in the list.

## Delete a supplier

1. Open the supplier's detail page and click **Delete**.
2. A **Confirm Delete** dialog appears: *"Are you sure you want to delete the supplier {name} ({code})? This action cannot be undone."* Click **Delete** to confirm or **Cancel** to back out.

This is a **hard delete** - the supplier row is removed. Its product-supplier links and any inbound shipments referencing it behave per their own rules (shipment references are detached, not cascaded).

## What's captured

A supplier stores: code, name, contact person, email, phone, website, full address (lines 1 - 2, city, state, postal code), a linked **Country** (from the Countries reference list, not free text), payment terms in days, and an active flag. The system also records when it was created and last updated.

## Product-Supplier links (read-only here)

The [**Procurement → Product-Suppliers**](/procurement-management/product-suppliers) list shows which products each supplier can supply (**Product Code**, **Product Name**, **Supplier Code**, **Supplier Name**). **This list is read-only in the UI** - product-supplier links are created through the product-master upload, not added by hand here. To see which suppliers cover a product, search this list or open the product.

## See also

* [Procurement - Data analysis for the AI assistant](data-analysis.md)
* [Countries](../product/countries.md) (where **Country** is maintained)
* [Upload product master](../purchasing/upload-product-master.md) (creates product-supplier links)
* [Upload a packing list](../purchasing/upload-packing-list.md) (shipments reference a supplier)
* [Buy and borrow decisions on Fulfilment Planning](../supply-chain/local-buy-and-borrow-source.md) (why a supplier's country matters on a Buy decision)
