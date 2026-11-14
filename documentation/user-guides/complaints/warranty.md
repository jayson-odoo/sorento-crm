# Warranty (is this covered?)

On a service job you can add the products with the problem, together with when each was bought and what is wrong with it. The job then shows, for each covered part, whether the warranty still covers it and why. Admins keep the warranty policy up to date under **After-Sales Service**, **Warranty Configuration**.

Nothing on complaints changes. Complaints keep their own "Within warranty" field exactly as before.

## Steps

### 1. Add the products to the job

1. Open the service job. On the **Details** tab, find the **Products** card.
2. Press **Add product**. In the dialog:
   * **Product**: search the catalogue by code or name. Only catalogue products can be added.
   * **Kind**: what the product is for warranty purposes, for example Water Closet. It is filled in for you when a warranty rule knows the product. You can change it or pick one yourself.
   * **Purchase date**: when the customer bought it, written dd/mm/yyyy, for example 15/03/2020. It cannot be later than today.
   * **Defect**: what is wrong, for example Leakage.
3. Save. The line appears in the **Products** card.

The same product can be added twice (two units). To change a line, right-click it and choose **Edit** (the same dialog). To remove it, right-click and choose **Remove**: the button counts down with a **Cancel**, and the line goes when the countdown ends. There is no confirmation box.

### 2. Read the Warranty card

Below **Products**, the **Warranty** card shows one line per product and covered part:

| Column | Example |
|---|---|
| **Product** | SRTWC6020-SH-UF |
| **Part** | Ceramic body |
| **Answer** | Covered |
| **Until** | 15/03/2025, or "-" for lifetime cover |
| **Reason** | 5 years from 15/03/2020 |

The answers:

* **Covered**: the warranty covers this part today. The last day in **Until** is still covered.
* **Expired**: the cover ended on the date shown.
* **Defect not covered**: this part's cover only lists other defects.
* **No term**: the policy says nothing about this kind of product.
* **Unknown**: something is missing, and the reason says what. For example "Purchase date not entered", "Defect not stated" or "No warranty rule for this product yet". Unknown never means "not covered".

The policy used is the one that was in force on the **purchase date**, not today's. A product bought years ago is judged by the policy of that time.

## Why does a product say "No warranty rule for this product yet"?

The product has no kind. Either pick the **Kind** yourself on the line (right-click, **Edit**), or ask an admin to add a rule for it on **Warranty Configuration**, **Rules**. The system never guesses a kind from a product's category.

## Service Jobs list

The list has a **Warranty** column:

* **Covered**: every part on the job is covered.
* **Partly covered**: some parts are.
* **Not covered**: none is covered.
* **Unknown**: none is covered and something is missing.
* "-": the job has no products.

Click the header to sort. Use the **Warranty** filter to pick one or more answers.

## Warranty Configuration (admins)

Open **After-Sales Service**, **Warranty Configuration**. It has three tabs.

**Policies.** One line per policy version, with **Version**, **In force from**, **In force to**, status and the number of terms. Two versions can never be in force on the same day.

* **Create** adds a version. Right-click a version for **Edit**, **Supersede** (only on the version still in force) or **Delete**. Delete counts down with a **Cancel**; there is no confirmation box.
* **Supersede** starts a new version on a date you pick and ends the current one the day before. The dialog shows both versions' dates before you save. Products bought before the new date keep the old version's answers. The new version starts with no terms: add them on its **Terms** tab.
* Click a version to open it. It opens on **Details** (dates and policy text). **Terms** lists the terms grouped by kind (part, cover, defects, installation); **History** shows every change.
* On **Terms**, press **Create** to add a term: pick the **Kind**, type the **Part**, then either tick **Lifetime** or enter the **Months**, never both. Leave **Defects** empty to cover every defect. Right-click a term to **Edit** or **Delete** it.

**Kinds.** The kinds of product the policy names, for example Water Closet or Mirror Cabinet. A pill such as "29 of 31 kinds have no rule" filters the list to the kinds no rule points at yet. Right-click a kind to **Edit**, **Archive** or **Delete** it. A kind that is used by a term, a rule or a job line cannot be deleted: archive it instead. An archived kind stays on old job lines but is not offered on new ones; right-click it and choose **Restore** to offer it again.

**Rules.** Which products are which kind. A rule matches on a series, a list of model codes, a category or a code prefix, and has a priority. When several rules match, the highest priority wins. Press **Test a product** to see which kind a product lands in and which rule decided it.

## What's captured

* On each job line: product, kind, purchase date and defect.
* The answers are worked out each time you open the job, from the policy in force on the purchase date. They are not stored.
* Policy, kind, rule and job line changes show in the record's **History** tab.

## Who can do what

* Anyone who can see service jobs sees the **Products** and **Warranty** cards and the list's **Warranty** column, and can open Warranty Configuration to read it.
* Anyone with the service jobs dispatch permission can add, edit and remove job products.
* Only admins can change policies, terms, kinds and rules. Everyone else sees Warranty Configuration read-only, without Create or the right-click changes, and does not have it in the sidebar.

## How you'll be notified

Nothing is sent. The answer shows on the job.

## Bulk import

Not available.

## See also

* [Service jobs](./service-jobs.md)
