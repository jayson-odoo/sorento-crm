# PLAN - Product specifications a non-technical staff member can read and use (#1286)

**Slug:** `product-specs-non-technical-26sep` | **Domain:** products (master data)
**Issue:** #1286. **UAC:** `product-specs-non-technical-acceptance-criteria.md` (the contract; where
this plan and the UAC disagree, the UAC wins). **Review:** `UX-REVIEW-product-specifications-26sep.md`
(diagnosis with file:line and the element verdicts this plan builds). **Mockups:** `mockups/`.
**Classification:** CORE, schema `public`. No new table, no new permission.
**Status:** DRAFT, 26 Sep 2026. Planned, not built. Waiting on the owner's Lavish review of the
mockups and answers to the grill questions (section 8). **Track: full** (four slices, one lane,
expected diff well over 300 lines, and S0 may carry a data migration; see Q12).
**Lane:** one lane, one branch, one PR; slices land as commits on it (lane merge discipline,
CLAUDE.md). Branch it from `origin/main` when the owner has answered.
**Measured on:** `origin/main` `51d30ccc5`.

## 1. Journey (PRINCIPLES step 0)

Two actors; the default view of every screen is built for them. The maintainer gets one closed
**Advanced** disclosure per screen and nothing else.

**A. Merchandiser checks a product** (`master_data.products.edit`), Products > a product >
Specifications.

1. The tab opens on the product's specs as a list of plain rows: Brand SORENTO, Product class
   Water closet, Type One piece, Capacity 8 oz. Above them, one line: "Not checked yet" and a
   **Mark as checked** button. Nothing else is open.
2. Brand is wrong. They press the pencil on Brand; a dropdown lists the brands in the Brands
   master (Bravat, Cabana, Infinity, Mocha, Sorento, and the rest the master holds). They pick
   Mocha. The product's own Brand changes (the same field as the Details tab), the Brand row now
   reads Mocha with source "Product's brand", and a toast says so.
3. A value is missing. **Add specification**, pick "Capacity (oz)", type 8, save.
4. They press **Mark as checked**. The line reads "Checked by {their name}, today" with an Undo that
   counts down 5 s.
5. Only when they want it: **Reading and search** (collapsed, at the bottom) opens to the
   product's description, "Search finds this product", "Read specs from a text", and "Read this
   product again".

What they hold at the end: correct specs, a checked stamp, and they never saw a pattern, a slug
or the word "Derived".

**B. Spec owner fixes how a spec is read** (`master_data.spec_registry.edit`), Master data >
Product Specifications.

1. The list shows Specification, Type ("List", "Number (mm)", "Yes or no"), Choices, Products,
   and one status pill at the top: **Up to date** or **Needs a re-read** with a Re-read button.
2. They open Capacity (oz). The Back link sits with the title. Four tabs: **Details**,
   **Choices and words**, **How it is read**, **Products**. Details has Name, Unit oz, In use,
   Highest believable value, and **Other names for this specification**: oz, ounce, ounces.
3. **How it is read** lists one rule: "1. The number just before OZ, in the description or
   flyer." No badge, no pattern. **Advanced** on the row shows the pattern for the maintainer.
4. They open Brand. How it is read: "1. The product's brand." Choices and words lists the
   Brands master read-only, each with its "Words customers say", and **Add a brand** goes to
   the Brands master.
5. They add a rule to Capacity with the sentence menu ("The number before a word: OUNCE"), try
   it on a real product, see what would change, save. The list's status turns **Needs a
   re-read**; they press Re-read; it turns **Reading...** then **Up to date**, and stays so after
   a deploy.

Decisions per journey: A, one per wrong value plus one Mark as checked; B, which sentence and its
blanks. Nothing asks them for a slug, a pattern or a source code.

## 2. What exists (measured; the review has the file:line)

- The FE already turns builder rules into sentences (`lib/ruleSentence.ts` `builderSentence`,
  `:215-249`) and **no screen calls it**. View mode uses `ruleSentence`, which falls back to the
  raw pattern for every number rule (`plainPattern` gives up on parentheses).
- 25 built-in rules are raw patterns with no builder (`product_spec_registry.py:268-376`).
- Brand has three sources (Brands master for search, stored values for the model prompt, empty
  registry list for the picker). Derivation reads the product's own brand row
  (`product_spec_derivation.py:833-835`) and stamps it `derived` (`:1254-1260`), which the FE
  labels "Description" (`SpecSourceBadge.tsx:40`).
- **Changing a product's brand does not re-read its specs:** `brand_id` is missing from
  `DERIVATION_INPUTS` (`app/services/product_spec_change_listener.py:66-73`), so the Brand spec
  stays stale until something else re-derives the product.
- `useBrandSelectQuery` (`master-data-management/shared/hooks/use-brand-select-query`) is what
  `ProductForm.tsx:39` already uses for the Brand field. Reuse it.
- Catalogue freshness `finished_at` lives in process memory (`product_spec_rederive.py:32-33`);
  the rules fingerprint is persisted in a `product_spec_search_policy` row
  (`_derived_rules_fingerprint`, `:37,72-74`).
- The record page renders `PageHeader` outside `Container` (`SpecKeyRecordDetail.tsx:100,114,150`).
- `components/ui/collapsible.tsx` is the house disclosure (precedent
  `products/components/ProductAttachmentsTab.tsx:335-358`); there is no shared Advanced component.

## 3. Design decisions (each traces to a grill question in section 8)

- **D1 Brand has one source: the Brands master** (Q1-Q4). The Brand spec on a product is always
  the product's own brand. The product tab's Brand picker lists the Brands master
  (`useBrandSelectQuery`) and saving it updates `products.brand_id` through the existing product
  update route, which (after D2) re-reads the product. The picker never creates a value; "Add a
  brand" links to the Brands master. The registry's `brand` row keeps `allowed_values: []`; the
  API serialises its choices from the Brands master (`brand_names`) so every consumer of
  `GET /spec-registry` sees one list.
- **D2 `brand_id` joins `DERIVATION_INPUTS`.** One word in a tuple, plus its test.
- **D3 Shadow brand values are cleared** (Q2). Any `user_values` / `value_labels` /
  `suppressed_values` on the `brand` row, and any product whose Brand spec is `source: human`,
  are listed in the lane evidence, then the registry lists are emptied and the human stamps on
  `brand` are dropped so the next read writes the product's brand. Words customers say per brand
  (`user_synonyms`) are kept.
- **D4 Product class gets the same picker shape but stays editable** (Q3): its choices are the
  distinct `product_categories.class_label` values, still overridable by hand because the class
  rule list legitimately beats the category.
- **D5 Every rule reads as a sentence** (Q5). View and edit render `builderSentence` for builder
  rows. Each of the 25 built-in pattern rows gains a `says` sentence in the shipped table
  ("The number just before OZ", "The word THERMOSTATIC", "A number of ways, like 2 WAYS"),
  written by hand and pinned by a test that every built-in pattern row has one. The engine does
  not read `says`: derivation output is unchanged (golden parity 0 diffs). A pattern typed by
  hand under Advanced must be saved with a plain description (the server refuses a custom
  pattern row without one).
- **D6 Plain words everywhere** (review section 2 vocabulary table): type chip List / Number (mm)
  / Yes or no / Text; tabs Details / Choices and words / How it is read / Products; source
  "Product's brand" for brand; "The product's brand", "The product's category", "The product's
  length" for from-field rows; no "Seed", "User", "shipped", "default", `_self`, slug, "Derived",
  "Findable by description" in any default view.
- **D7 `_self` moves to Details** as "Other names for this specification" (same stored map,
  `synonyms._self` / `user_synonyms._self`, no backend change). The Choices and words tab never
  lists it.
- **D8 One Advanced disclosure per screen** (Q6): a small `AdvancedSection` on `Collapsible`,
  closed by default, open state remembered per viewer in `localStorage` (try/catch, renders
  closed without it). No new permission. It holds: code (slug), Built in / Added here, rule
  count, the pattern per rule, the product tab's search diagnosis.
- **D9 Product tab order** (Q7): checked line, values table, price tag wording, then one
  collapsed **Reading and search** section (description, search finds it or not, what search
  matches, read specs from a text, read this product again, Advanced diagnosis). The Unverify
  confirm dialog becomes a 5 s deferred Undo (D7 of PRINCIPLES).
- **D10 List status is one pill, persisted** (Q8): Up to date / Needs a re-read / Reading.
  The finish time is stored in a second `product_spec_search_policy` row
  (`_derived_rules_read_at`) beside the fingerprint, so a deploy does not reset it. No migration
  (a row, seeded on first write).
- **D11 Back sits with the title**: wrap `PageHeader` in `Container` on the record page (all three
  states) and copy "Back to specifications".

Not in this lane (triggers named, per "Simplest thing"): per-brand rule sets, a translated
vocabulary, a rule builder for alternation patterns (trigger: a staff member needs a custom
pattern the sentence menu cannot express, twice).

## 4. Slices

Each slice is a commit set on the lane branch. Phase 1 (FE against mocks) runs across S1 to S3
first; S0 is mostly backend and goes test-first straight away because it is a defect.

### S0 - Brand picker fix and brand source of truth

Scope: D1, D2, D3, D4, plus the brand source label.
- BE: `brand_id` in `DERIVATION_INPUTS`; `GET /spec-registry` serialises brand choices from the
  Brands master (active brands, company scoped) and class choices from category class labels;
  `value_for_registry` refuses a brand value not in the Brands master; a data migration (only if
  the S0 measurement finds rows) clearing the shadow lists and the human brand stamps, evidence
  CSV first.
- FE: Brand row editor = `SearchableSelect` over `useBrandSelectQuery`, no `createOption`, saving
  calls the product update with `brand_id`; source pill "Product's brand"; Product class picker
  lists class labels.
- Rule sentence "The product's brand" (`ruleSentence.ts:208`).
**Definition of done:** UAC AC-S0.1 to AC-S0.9 green (pytest + vitest); agent-browser run at 375
and 1280: open a product by sidebar clicks, change Brand to Mocha, see Details show Mocha and the
spec row read Mocha, change it back; the evidence file lists the pre-migration counts.

### S1 - Plain-language rules and values

Scope: D5, D6 (record page and its tabs), D7, D8 (record page call sites), the tab renames.
- View mode renders `builderSentence`; 25 `says` sentences on built-in pattern rows; server
  refuses a custom pattern row without a description; badges "shipped"/"default" removed; one
  "Changed here" line with **Put back the built-in rules** (clears `derivation_rules`).
- Details tab: Name, Unit (hidden on lists), In use, Highest believable value, Other names.
- Choices and words: no `_self` card, no "user" badge, slug under Advanced; Brand and Product
  class list their master read-only.
- Try it on moves below the rules; in-UI help sentences removed.
**Definition of done:** AC-S1.1 to AC-S1.12 green; golden parity 0 diffs over the dev catalogue
(`says` changes nothing); browser run on Brand, Capacity (oz), Length at both widths with no
pattern, slug or `_self` visible until Advanced is opened.

### S2 - Product Specifications tab declutter

Scope: D9.
- Order: checked line, values, price tag wording, Reading and search (collapsed).
- Remove the Derived pill, the Findable pill (its fact moves into the section), the footer text,
  the eyebrow over the table; "What search matches" always renders with an empty state.
- Unverify confirm dialog becomes a deferred 5 s Undo.
**Definition of done:** AC-S2.1 to AC-S2.9 green; browser run on SRTWC7604-SC-SH (the owner's
screenshot product) at both widths: first screen shows the values without scrolling at 1280.

### S3 - List and navigation

Scope: D6 (list), D10, D11.
- Columns: Specification, Type (unit folded in), Choices (brand = Brands master count), Products;
  Code, Rules, Built in hidden by default through the existing column chooser.
- One status pill, persisted finish time; Re-read button beside Needs a re-read.
- Record page header inside `Container`; "Back to specifications".
- Row menu hides Delete on built-in rows.
**Definition of done:** AC-S3.1 to AC-S3.8 green; restart the API and the pill still reads Up to
date; browser run at both widths with the Back link aligned to the title's gutter.

### Phase 3 (once per lane)

`reviewer` + browser verification in parallel. `security-reviewer`: not run unless S0's brand
write turns out to need a new route (it should not: it reuses the product update, same
permission).

## 5. Files expected to change

BE: `app/services/product_spec_change_listener.py`, `app/api/v1/master_data/spec_registry.py`
(`_serialise`), `app/services/product_spec_registry.py` (`says` on shipped rows,
`value_for_registry`), `app/services/product_spec_rederive.py` (persisted finish time),
optionally one data migration. FE: `components/spec-table/*` (picker, source label),
`PS/lib/ruleSentence.ts`, `PS/components/record/*`, `PS/components/SpecRuleEditor.tsx`,
`PS/components/SpecKeyRecordDetail.tsx`, `PS/components/SpecRegistryGrid.tsx`,
`PS/components/CatalogueFreshnessLine.tsx`, `products/[id]/components/ProductSpecificationsTab.tsx`,
a new `components/common/AdvancedSection.tsx`.

## 6. Risks

- **The model prompt reads stored brand values** (`product_spec_understanding.py:151-170`). After
  D3 they equal the Brands master, so the prompt improves; no change to the understanding code.
- **Excluded brands** (OTHERS, NO LOGO) stay excluded from search and the prompt; they are still
  real brands and appear in the picker (Q4).
- **Company scoping:** `Brand` is company scoped; the picker and the registry serialiser must read
  through the same scope as the product (LESSONS: scoped reference tables).
- **Anything reading `allowed_values` for brand** (n8n parser via the MCP) now receives the
  Brands master names instead of `[]`. Check the MCP catalogue consumer in S0.

## 7. Evidence to gather at S0 start (read-only, dev DB)

1. `user_values`, `suppressed_values`, `value_labels`, `user_synonyms` on `brand` and `class`.
2. Products whose Brand spec differs from `brands.brand_name` (case-insensitive), by source.
3. Products whose `brand_id` changed after their spec row was last written.

## 8. Grill questions for the owner

Each has a recommendation; the UAC is written to the recommendation. Answer "yes" to take it.

1. **When a person picks a brand on the Specifications tab, what changes?**
   Recommendation: the product's own Brand (the same field as Details), and the spec follows it.
   One place holds the brand; the spec can never disagree with it. Alternative: the Brand spec
   becomes read-only on this tab with a "Change on Details" link (fewer moving parts, but you
   asked for the dropdown here).
2. **What happens to brands someone already typed into the old empty picker?**
   Recommendation: list them in the lane evidence, then clear them; each product's Brand spec
   goes back to the product's brand. Words customers use for a brand are kept.
3. **Does Product class get the same treatment?**
   Recommendation: the same dropdown shape (lists the category classes), but it stays editable
   per product, because a product's name can rightly say a different class from its category.
4. **Should OTHERS and NO LOGO appear in the brand dropdown?**
   Recommendation: yes, they are real brands on 2,600 products; they stay out of search.
5. **How does a built-in rule become a sentence?**
   Recommendation: each of the 25 built-in pattern rules gets a hand-written sentence ("The
   number just before OZ"); the pattern stays under Advanced; how products are read does not
   change at all. A pattern typed by hand must be saved with a plain description.
6. **Who sees Advanced?**
   Recommendation: anyone who can edit specifications, closed by default, remembered per person.
   No new permission.
7. **What does the product's Specifications tab show first?**
   Recommendation: the checked line, then the values, then price tag wording, then one collapsed
   "Reading and search" section holding description, read from a text, what search matches and
   read again.
8. **What replaces "Never read" and "Rules changed since"?**
   Recommendation: one pill, Up to date / Needs a re-read (with Re-read beside it) / Reading,
   and it survives a deploy.
9. **Tab names on a spec's page?**
   Recommendation: Details, Choices and words, How it is read, Products.
10. **Where does the price tag wording live?**
    Recommendation: stays on the Specifications tab, below the values, labelled "Price tag
    wording", with "Not set, the price tag uses the product description" when empty.
11. **The Code, Rules and Built in columns on the list?**
    Recommendation: hidden by default in the list's existing column chooser, not deleted.
12. **One lane or four?**
    Recommendation: one lane, full track, slices S0 to S3 as commits, S0 first so the brand
    picker works as soon as possible; the owner tests once on the lane's stack.
