# Product Management - Verify product specifications

Verification is a person vouching that a product code's specification values are correct. Every code is in one of three states, shown as the same pill everywhere:

* **Verified** - someone checked the values and stamped them, with who and when.
* **Needs re-verify** - the code was verified, but a value changed afterwards. The stamp is withdrawn automatically and the page shows exactly what moved.
* **Unverified** - nobody has vouched for this code yet, or someone withdrew the stamp by hand.

Open **[Product Management → Spec Verification](/master-data-management/spec-verification)** (URL: `/master-data-management/spec-verification`). The page is titled **Spec Verification**.

## The worklist

A progress line above the table reads **Verified N of M live codes** (discontinued codes are excluded unless you include them via the filter).

Columns: **Code**, **Name**, **Class**, **Brand**, **Coverage** (values held / applicable keys), **Exceptions** (open "Needs a human" items - verify is refused while any are open), **Verification** (the state pill; hover it for who verified and what changed), and a per-row **Verify** / **Unverify** button.

* Default order puts **Needs re-verify** rows first, then **Unverified** grouped by class, with **Verified** last - the top of the list is always the work.
* **Search code or name** - press Enter to apply.
* **Filters** (popover) - **Verification** state, **Class**, and an **Include discontinued** switch (off by default). Filters, sort, and page live in the URL, so a link to the list is a shareable slice.
* Clicking a row opens that product's detail page on its **Specifications** tab.

**Verify** and **Unverify** appear only for users who can edit products; everyone else gets a read-only list.

## Verify or unverify one code

* **Verify** on a row is one click. The code is stamped with your name and the time.
* **Unverify** on a row asks for confirmation first: it withdraws the verification, the code reads **Unverified** again, and the history keeps who originally vouched and who withdrew.

A verify can come back **skipped** for two reasons, reported in the result toast:

* **exceptions open** - the code still has open "Needs a human" items. Fix those values first (see below).
* **changed while you were reviewing** - a value moved after the list was loaded. The row refreshes; review the new values and verify again.

## Verify or unverify in bulk

1. Select rows with the checkboxes. Selection is page-scoped: it clears when you change page, so a code you can no longer see is never carried into a bulk action.
2. Click **Verify selected** or **Unverify selected** in the toolbar. Each opens a confirmation stating the count.
3. The result toast breaks down what happened per code, e.g. *42 verified, 3 skipped - exceptions open, 1 skipped - changed while you were reviewing*. Skipped rows stay selected so you can deal with them; acted rows are released and updated in place.

## On the product page (Specifications tab)

The verification block sits at the top of the **Specifications** tab and is always shown, whatever the state:

* The state pill, plus who verified and when.
* For **Needs re-verify**: a **What moved since it was verified** list showing each changed key with its *was* and *now* values.
* After a manual unverify: a **Withdrawn by** line naming who withdrew it and when, alongside the original verifier.
* **Verify** stamps the code as rendered on this page. If open exceptions block it, the toast names the keys (*Still needs a human: ...*). If the values changed under you, the page reloads them and you verify again.
* **Unverify** asks for confirmation, same as the worklist.

Each item in the **Needs a human** card offers an **Edit** button that opens that key's own row in the values table. Correcting the value is what answers the exception - there is no "dismiss".

Editing any specification value (or re-reading the product against the rules, when that changes a value) automatically withdraws an existing stamp: the code moves to **Needs re-verify** with the was/now diff, and shows back up near the top of the worklist.

## See also

* [Manage products](manage-products.md)
* [Product attachments](product-attachments.md)
