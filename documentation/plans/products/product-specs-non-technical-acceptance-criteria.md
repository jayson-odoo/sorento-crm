# UAC - Product specifications a non-technical staff member can read and use (#1286)

**Companion to:** `PLAN-product-specs-non-technical-26sep.md` (design) and
`UX-REVIEW-product-specifications-26sep.md` (diagnosis and verdicts).
**Status:** DRAFT, 26 Sep 2026. Written to the recommendations in the plan's "Grill questions for
the owner"; an answer that differs from a recommendation amends the ACs that cite it.
**Legend:** `[BE]` pytest (Postgres only) · `[FE]` vitest · `[E2E]` agent-browser evidence run
(sidebar clicks from `/`, 375 and 1280) · `[MIG]` migration · `[T]` CI guard.

## Journey

**A. Merchandiser** (`master_data.products.edit`), Products > a product > Specifications.

1. Sees one line "Not checked yet" with **Mark as checked**, then the product's specs as plain
   rows (Specification, Value, Where it came from). Nothing else open.
2. Edits Brand: the dropdown lists the Brands master. Picks one; the product's Brand changes and
   the Brand row follows, source "Product's brand".
3. Adds a missing specification from the Add specification dialog.
4. Marks the product as checked; can Undo within 5 s.
5. Opens **Reading and search** only when needed: description, whether search finds the
   product, what search matches, read specs from a text, read this product again.

**B. Spec owner** (`master_data.spec_registry.*`), Master data > Product Specifications.

1. Sees the list with Specification, Type, Choices, Products and one status pill.
2. Opens a spec; Back sits with the title; tabs Details, Choices and words, How it is read,
   Products.
3. Reads every rule as a sentence; the pattern only under Advanced.
4. Brand's choices are the Brands master; its only rule reads "The product's brand".
5. Adds a rule from the sentence menu, tries it, sees what would change, saves, re-reads the
   catalogue from the status pill.

## S0 - Brand picker and brand source of truth

**AC-S0.1 [FE]** Given a product with Brand SORENTO and the Brands master holding Sorento, Mocha,
Cabana, Bravat, Infinity, when the Brand row's pencil is pressed on the Specifications tab, then
the dropdown lists every active brand of the product's company by name, sorted, and never shows
"No results found" while the master has brands. (Journey A2; Q1)

**AC-S0.2 [FE]** The Brand dropdown offers no "Add ... to Brand" row. An empty master shows
"No brands yet" with a link to Master data > Brands. (Q1)

**AC-S0.3 [BE] [FE]** Given the Brand row set to Mocha and saved, then the product's `brand_id`
is Mocha's id (through the existing product update route and permission), the Details tab shows
Mocha, and the Brand spec value reads MOCHA's `brand_name` after the response. (Journey A2; Q1)

**AC-S0.4 [BE]** Given a product whose `brand_id` changes by any write path, when the transaction
commits, then the product is re-derived and its Brand spec equals the new brand's name
(`brand_id` is a derivation input). (Plan D2)

**AC-S0.5 [BE]** `GET /spec-registry` returns for `brand` an `allowed_values` list equal to the
active brand names of the caller's company, and for `class` the distinct
`product_categories.class_label` values; a brand added to the master appears without any change
to the registry row. (Plan D1, D4)

**AC-S0.6 [BE]** Writing a Brand spec value that is not a brand name in the master is refused with
a 400 naming the Brands master; `user_values` on `brand` can no longer be appended. (Q1, Q2)

**AC-S0.7 [MIG] [BE]** Given shadow values on the `brand` registry row (`user_values`,
`suppressed_values`, `value_labels`) or products whose Brand spec is `source: human`, when the
migration runs, then those lists are empty, the human stamps on `brand` are removed, the products
re-derive to their own brand, and `user_synonyms` on `brand` are unchanged. Idempotent on a
second run. Skipped as a no-op when the S0 measurement finds nothing. (Q2)

**AC-S0.8 [FE]** The Brand row's source pill reads "Product's brand"; the Product class row's
dropdown lists the category classes and stays editable per product. (Q3; review T12)

**AC-S0.9 [FE]** OTHERS and NO LOGO appear in the Brand dropdown; search and the understanding
prompt still exclude them (existing tests stay green). (Q4)

## S1 - Plain-language rules and values

**AC-S1.1 [FE]** On How it is read, in view and edit mode, every builder row renders its
`builderSentence` and no row renders a character of a regular expression. Capacity (oz) row 1
reads "The number just before OZ, in the description or flyer". (Journey B3; Q5)

**AC-S1.2 [BE] [T]** Every built-in pattern row returned by `shipped_rules()` carries a non-empty
`says` sentence; a test fails on any built-in pattern row without one. (Q5)

**AC-S1.3 [BE]** Derivation output over the dev catalogue is identical before and after S1
(golden parity, 0 diffs): `says` is display only. (Q5)

**AC-S1.4 [BE]** Saving a rule list containing a custom pattern row with no plain description is
refused with a 400 asking for one. (Q5)

**AC-S1.5 [FE]** No "shipped", "default", "Seed" or "User" badge renders in the default view. A
spec whose rules were changed shows "Changed here" above the list and **Put back the built-in
rules**, which clears the stored list (deferred 5 s). (Review U3)

**AC-S1.6 [FE]** Brand's only rule reads "The product's brand"; from-field rows read "The
product's category", "The product's length" and so on, never a column name. (Review U9, U10)

**AC-S1.7 [FE]** Tabs read Details, Choices and words, How it is read, Products, in that order,
the same in view and edit. (Q9)

**AC-S1.8 [FE]** Details shows Name, Unit (not on List specs), In use, Highest believable value
(numbers), and "Other names for this specification" as a token field bound to
`synonyms._self`/`user_synonyms._self`. (Plan D7)

**AC-S1.9 [FE]** Choices and words never renders `_self`, never renders a "user" badge, and shows
a value's stored slug only inside Advanced. A number spec shows an empty state pointing at
Details. (Review V2-V4, V8)

**AC-S1.10 [FE]** Brand's Choices and words lists the Brands master read-only with each brand's
"Words customers say" editable and **Add a brand** linking to the Brands master; Product class
lists category classes the same way. (Plan D1, D4)

**AC-S1.11 [FE]** Each rule's pattern appears only inside that rule's Advanced; Advanced is closed
by default, its open state is remembered per viewer, and the page renders correctly with storage
unavailable. (Q6)

**AC-S1.12 [FE] [E2E]** Try it on sits below the rule list; no help paragraph renders on How it is
read or See what would change. Browser run on Brand, Capacity (oz), Length at 375 and 1280.
(Review U1, U11)

## S2 - Product Specifications tab

**AC-S2.1 [FE]** Top to bottom: checked line, values table, price tag wording, **Reading and
search** (collapsed). (Q7)

**AC-S2.2 [FE]** No "Derived" pill, no "Findable by description" pill, no footer sentence, no
eyebrow above the values table. (Review T2, T3, T11, T15)

**AC-S2.3 [FE]** The checked line reads "Not checked yet" with **Mark as checked**, or
"Checked by {name} on {date}" with Undo; "Needs checking again" with what moved when a value
changed after checking. (Review T5)

**AC-S2.4 [FE]** Undo is a deferred 5 s action with Cancel; no confirm dialog opens (PRINCIPLES
D7). (Review T5)

**AC-S2.5 [FE]** Reading and search holds, in order: the product description (not monospace),
"Search finds this product" or "Search cannot find this product yet", what search matches,
Read specs from a text, Read this product again, and Advanced (the search diagnosis). (Q7)

**AC-S2.6 [FE]** What search matches always renders; empty shows "Nothing yet. Read this product
again to build it." (Review T10)

**AC-S2.7 [FE]** Price tag wording renders below the values; empty reads "Not set, the price tag
uses the product description" with Edit. (Q10)

**AC-S2.8 [FE]** Reading and search is closed by default and remembered per viewer. (Q6, Q7)

**AC-S2.9 [E2E]** On SRTWC7604-SC-SH at 1280 the first values row is visible without scrolling
below the tab strip; at 375 nothing is clipped and no horizontal page scroll appears.

## S3 - List and navigation

**AC-S3.1 [FE]** List columns by default: Specification, Type, Choices, Products. Code, Rules and
Built in are available in the column chooser, hidden by default. (Q11)

**AC-S3.2 [FE]** Type reads List, Number (unit), Yes or no, Text. (Review L7, L8)

**AC-S3.3 [FE]** Choices for Brand equals the Brands master count, for Product class the category
class count, "-" for numbers and yes or no. (Review L9)

**AC-S3.4 [FE]** One status pill: Up to date, Needs a re-read (with **Re-read** beside it), or
Reading. The words "Never read" and "Rules changed since" do not render. (Q8)

**AC-S3.5 [BE]** The catalogue read finish time persists in the database; after an API restart the
status reports the last finish time and Up to date when the fingerprint matches. (Q8)

**AC-S3.6 [FE] [E2E]** On a spec's page the Back link sits in the page header inside the same
side gutter as the title and card, reading "Back to specifications", at 375 and 1280, in the
loading, not-found and loaded states. (Review R1)

**AC-S3.7 [FE]** The record card shows the label once (page title) and one type chip; no slug, no
"Unit None", no duplicate "Active". (Review R3, R4)

**AC-S3.8 [FE]** Built-in rows show no Delete item in the row menu or the gear; added rows keep a
deferred delete. (Review L16)
