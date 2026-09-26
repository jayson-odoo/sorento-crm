# UX review - Product specifications, for a non-technical staff member (#1286)

**Issue:** #1286 (owner, 26 Sep 2026, seven screenshots). **Companions:**
`PLAN-product-specs-non-technical-26sep.md`, `product-specs-non-technical-acceptance-criteria.md`,
mockups under `mockups/`.
**Measured against:** `origin/main` at `51d30ccc5`. Every file:line below is on that commit.
**Status:** Review written 26 Sep 2026. No code changes in this lane.

## Contents

1. The brand picker, diagnosed
2. Who uses these screens, and for what
3. Screen by screen: Product Specifications list
4. Screen by screen: a spec's record page (Header, Values and words, Rules, Seen in products)
5. Screen by screen: a product's Specifications tab
6. Cross-cutting findings
7. Verdict table (keep, merge, hide behind Advanced, remove)

---

## 1. The brand picker, diagnosed

**Symptom (screenshot 1).** On a product's Specifications tab, "Every value, and where it came
from", editing the Brand row opens a dropdown whose placeholder is "Type the first brand"; its
Search box says "No results found." The Brands master holds Sorento, Mocha, Cabana, Bravat,
Infinity.

### 1.1 Where a Choice spec's options come from

The picker offers exactly one list: the spec's registry vocabulary, `allowed_values` plus
staff-added `user_values` minus `suppressed_values`.

- `sorento_crm_frontend/components/spec-table/specTableModel.ts:78` builds each row with
  `options: definition?.allowed_values ?? []` (the same in `SpecTable.tsx:136` for the add path).
- `sorento_crm_frontend/components/spec-table/SpecValueCell.tsx:148-162` renders a
  `SearchableSelect` over `row.options` when the key is `enum`, and switches the placeholder to
  `Type the first ${label}` precisely when `row.options.length === 0` (line 161). That is the
  string in the screenshot, so the picker was handed an empty list.
- `allowed_values` on the wire is `merged_allowed_values(row)`
  (`sorento_crm_backend/app/api/v1/master_data/spec_registry.py:78`,
  `app/services/product_spec_registry.py:1477-1489`). Nothing in that chain reads the `brands`
  table.

### 1.2 Why Brand has 0 values

- The seed row declares Brand an enum with an empty closed list on purpose:
  `app/services/product_spec_registry.py:585-599`, `"data_type": "enum", "allowed_values": []`,
  with `excluded_values: ["OTHERS", "NO LOGO"]` (migration `311f_spec_registry_excluded_values.py`
  calls it "an OPEN vocabulary - its options are whatever the catalog holds"). Product class
  (`:572-583`) is seeded the same way.
- The registry list's Values column counts `allowed_values.length`
  (`.../product-specifications/components/SpecRegistryGrid.tsx:150-156`), so Brand shows 0.
- The "Seed" badge is `source !== 'user'` (`SpecRegistryGrid.tsx:199`,
  `record/SpecKeyRecordCard.tsx:48`): the row ships with the code, which is a fact about
  deployment, not about the spec.

So "open vocabulary" was only ever wired for the machine readers, never for the person:

| Reader | Where brand names come from | File |
| --- | --- | --- |
| Search binding (a customer types "sorento basin") | the **Brands master**, `SELECT brand_name FROM brands` | `app/services/product_spec_search.py:320-332` (`brand_names`), used at `:462`, `:593` |
| Understanding model prompt | **distinct values already stored** in `product_specifications.values['brand']`, capped at 60 | `app/services/product_spec_understanding.py:143-170` (`open_vocabulary_values`) |
| Product Specifications tab picker | **registry `allowed_values`**, which is `[]` | `specTableModel.ts:78`, `SpecValueCell.tsx:148-162` |
| Derivation (how a product gets its Brand spec) | the **product's own brand row**, `product.brand.brand_name` | `app/services/product_spec_derivation.py:833-835` |

Three sources for one fact, and the one a person touches is the empty one.

### 1.3 Why the one rule reads "From the product's brand field"

- Shipped rules for `brand` are one `from_field` row with `pattern: "brand"`
  (`app/services/product_spec_registry.py:397-407`); the comment there records why the category
  prefix decode was dropped (it relabelled 1,934 rows wrong).
- The engine reads it at `product_spec_derivation.py:833-835` and stamps source `field`.
- The sentence is hard-coded in the FE: `.../product-specifications/lib/ruleSentence.ts:208`
  `if (field === 'brand') return "From the product's brand field"`. "Field" is a database word.

This rule is correct and is the right one-source-of-truth: a product's Brand spec should be the
product's Brand. What is wrong is everything around it.

### 1.4 What goes wrong when a person uses the picker today

- With zero options, `SpecValueCell.tsx:165-196` offers `createOption`: type "Mocha", the last
  row reads `Add "Mocha" to Brand`, and picking it calls `onAddValueToKey`
  (`products/[id]/components/ProductSpecificationsTab.tsx:594` ->
  `products/hooks/useProductSpecTable.ts:189-205`, `addValueToSpecKey`). That appends "Mocha" to
  the Brand spec's `user_values`: a **second, shadow brand list** that the Brands master never
  sees, and the value is then stored on the product as `source: human`.
- The product's real brand (`products.brand_id`) is not changed. On the next re-derivation the
  rule reads the product's brand row again and the two disagree, which raises a
  `human_override_conflict` exception (`specTableModel.ts:44`, `CONFLICT_REASON`). The person
  has created work for the verification list without knowing it.
- Enum coercion does not stop any of this: `value_for_registry` only enforces membership when the
  merged list is non-empty (`product_spec_registry.py:1562-1567`), so on an empty list any string
  is accepted.

**Measure before S0 ships (dev DB, read-only):** `SELECT user_values, suppressed_values,
value_labels FROM product_spec_registry WHERE spec_key IN ('brand','class')`, and the count of
products whose `values->'brand'->>'value'` differs (case-insensitive) from their
`brands.brand_name`, split by `provenance->'brand'->>'source'`. This lane could not reach a
database from its cloud container, so the numbers are left to S0's first step.

### 1.5 What `_self` is (screenshot 4)

- Inside a spec's `synonyms` map, `_self` is a pseudo-value holding the words that name the
  **spec itself** ("oz", "ounce", "ounces" for Capacity (oz)) rather than one of its values.
  Backend constant: `app/services/product_spec_search.py:176-181` (`SELF_SYNONYM_KEY`); seeded on
  about 15 measurement keys (`product_spec_registry.py:618-1256`, for example `:1110` for
  `capacity_oz`).
- The FE knows about it in one helper, `sorento_crm_frontend/lib/spec-readable.ts:31-41`, where
  `readable('_self')` returns "Words for the spec itself". But the Values and words tab never calls
  that helper for it:
  - `record/ValuesAndWordsTab.tsx:216-220` builds the value list from
    `Object.keys(words)`, so `_self` becomes a "value" card;
  - `:84` renders its heading through `readableValue`, which has no `_self` case, so the heading
    is `_self`;
  - `:102` prints the raw slug in a `<code>` chip, so `_self` again;
  - `:256-260` marks it `isUserAdded` because it is not in the seed values, so the badge reads
    `user`.
- That is the "_self _self user" card. The words themselves are useful (they are how search
  knows "8 ounce tumbler" is about this spec); the card they sit in is wrong.

### 1.6 Summary

| Question | Answer |
| --- | --- |
| Why "No results found" | The picker lists registry `allowed_values`; Brand's is `[]` by seed design. The Brands master is never read by the picker. |
| Why "Seed" and 0 values | "Seed" means "ships with the code"; 0 is `allowed_values.length` for an open-vocabulary key. |
| Why one rule "From the product's brand field" | Derivation reads `product.brand.brand_name`, correct; the sentence is a hard-coded FE string using a database word. |
| What `_self` is | The words for the spec itself, stored under a pseudo-value; the Values tab renders it as if it were a value. |
| What the picker does when used | Creates a shadow brand in the spec registry and a hand-set value that conflicts with the product's real brand on the next read. |

---

## 2. Who uses these screens, and for what

| Person | Permission (measured) | Where they are | What they actually need |
| --- | --- | --- | --- |
| **Merchandiser / master-data staff** (the non-technical majority) | `master_data.products.edit` (`app/api/v1/master_data/product_specifications.py`, 9 routes) | a product's Specifications tab | See the product's specs in words, fix a wrong one by picking from a list, add a missing one, say "this is right" (Verify). |
| **Spec owner** (one or two people, the owner included) | `master_data.spec_registry.view/edit/add/delete` | Master data > Product Specifications list and a spec's page | Rename a spec, add a value and the words customers use for it, see and correct how a spec is read from a description, see which products carry it. |
| **Maintainer** (developer) | same as spec owner | the same pages | The raw pattern, the stored slug, the shipped/stored split, the catalogue re-read. Rare, and never needed by the other two. |

Design rule that follows: the first two rows are the audience of every default view. Anything
only the maintainer reads goes behind one **Advanced** disclosure per screen, closed by default
and remembered per viewer, never deleted outright while the engine still depends on it.

Vocabulary rule that follows (applies to every screen below):

| Today (technical) | Plain replacement |
| --- | --- |
| Choice / Enum | "Pick from a list" (type chip: **List**) |
| Numeric | "Number" (with its unit: "Number, in mm") |
| Boolean | "Yes or no" |
| Seed / User (source badge) | removed from default view; Advanced shows "Built in" / "Added here" |
| `brand` (the code under the label) | removed from default view; Advanced shows it |
| `_self` | "Other names for Capacity (oz)" field on the Header tab, not a value card |
| shipped (rule badge) | removed; a rule someone changed says "Changed here" instead (Advanced keeps "Built in"), and "Put back the built-in rules" undoes it |
| Pattern `(?<![A-Z0-9])(\d+...)OZ\b`, capture the 1 number | "The number just before OZ" |
| From the product's brand field | "The product's brand" |
| Description and flyer | "the description or flyer" in the sentence, not a separate column |
| Never read / Rules changed since | one status pill: "Up to date" / "Needs a re-read" / "Reading..." |
| Derived / Findable By Description | removed from the product tab header; the values table already says where each value came from |
