# PLAN - Product specifications a non-technical staff member can read and use (#1286)

**Slug:** `product-specs-non-technical-26sep` | **Domain:** products (master data)
**Issue:** #1286. **UAC:** `product-specs-non-technical-acceptance-criteria.md` (the contract; where
this plan and the UAC disagree, the UAC wins). **Review:** `UX-REVIEW-product-specifications-26sep.md`
(diagnosis with file:line; its brand verdicts are superseded by the round 1 rulings below).
**Rule appendix:** `rule-engine-built-in-rules.md` (every built-in rule in the new form).
**Mockups:** `mockups/`.
**Classification:** CORE, schema `public`. No new table, no new permission.
**Status:** DRAFT, round 2, 26 Sep 2026. Planned, not built. Round 1 owner rulings applied
(section 8). Round 2 questions posted on PR #1290 (comment 5847720339): waiting on the owner for
Q3, Q8, Q9, Q10 (confirm) and Q11, and on the Lavish review of the regenerated mockups. **Track: full** (one lane, expected diff well over 300 lines, two data
migrations: the Brand specification removal and the rule conversion).
**Lane:** one lane, one branch, one PR; slices land as commits on it (lane merge discipline,
CLAUDE.md). Branch it from `origin/main` when the owner has answered.
**Measured on:** `origin/main` `51d30ccc5`.

## Owner rulings, round 1 (26 Sep 2026, 23:45 MYT, verbatim in PR #1290)

- **Owner ruling, 26 Sep 2026 (Q1, Q2, Q4):** the Brand specification is redundant; the product
  already has a brand field, and that field is the only brand. Applied as D1 to D3.
- **Owner ruling, 26 Sep 2026 (Q5, Q6):** no sentences-plus-Advanced split. Rules must be
  configurable easily and fool-proof, backed by a rule engine; "if the rule engine is not simple
  enough to cover, then the engine is the problem". Applied as D5 and D8 (no Advanced anywhere).
- **Owner ruling, 26 Sep 2026 (Q7):** price tag wording is okay where it is. Applied as D9. The
  owner's line numbered 7 answers the price tag question, which the plan numbered Q10; the
  product tab order (the plan's Q7) is taken as the recommendation and confirmed in round 2.
- **Owner ruling, 26 Sep 2026 (Q12):** one lane.

## 1. Journey (PRINCIPLES step 0)

Two actors; every screen is built for them. There is no Advanced disclosure for a maintainer: if a
case needs one, the rule engine is wrong (owner ruling, Q6).

**A. Merchandiser checks a product** (`master_data.products.edit`), Products > a product >
Specifications.

1. The tab opens on the product's specs as plain rows: Product class Water closet, Type One
   piece, Flush type Twister, Trap S-trap. Above them, one line: "Not checked yet" and a
   **Mark as checked** button. No Brand row: the brand is on the product's Details tab and
   nowhere else.
2. A value is wrong. They press the pencil on Flush type and pick Siphonic from the list.
3. A value is missing. **Add specification**, pick "Capacity (oz)", type 8, save.
4. They press **Mark as checked**. The line reads "Checked by {their name}, today" with an Undo
   that counts down 5 s.
5. Only when they want it: **Reading and search** (collapsed, at the bottom) opens to the
   product's description, "Search finds this product", what search matches, "Read specs from a
   text" and "Read this product again".

What they hold at the end: correct specs, a checked stamp, and they never saw a pattern, a code
name or the word "Derived".

**B. Spec owner changes how a spec is read** (`master_data.spec_registry.edit`), Master data >
Product Specifications.

1. The list shows Specification, Type ("List", "Number (mm)", "Yes or no"), Choices, Products,
   and one status pill at the top: **Up to date**, or **Needs a re-read** with a Re-read button.
   Brand is not in the list.
2. They open Finish or colour. Four tabs: **Details**, **Choices and words**, **How it is read**,
   **Products**.
3. **How it is read** lists numbered rules, each one sentence built from the choices it was made
   with: "1. When the description or flyer says MATT BLACK, Finish is Matt black." Nothing else
   is on the row; no pattern exists anywhere to show.
4. They press **Add a rule**. The rule form asks three things, each a pick or a typed word: **Look
   in** (Description or flyer), **Find** (Words: GUNMETAL, GUN METAL), **Answer** (Gunmetal).
   Optional fourth: **Only when** another spec has a value. The sentence at the top of the form
   updates as they fill it. **Try it on** a real product shows what the rule reads; **See what
   would change** shows the products whose value would change before they save.
5. They save. The list's status turns **Needs a re-read**; they press Re-read; it turns
   **Reading** then **Up to date**, and stays so after a deploy.

Decisions per journey: A, one per wrong value plus one Mark as checked; B, the three picks of a
rule. Nothing asks them for a code name, a pattern or a source code.

## 2. What exists (measured; the review has the file:line)

- **Brand is stored twice.** `products.brand_id` is the product's brand (the Details tab). The
  `brand` specification copies it: its one rule reads `product.brand.brand_name`
  (`product_spec_derivation.py:833-835`), stamps it `derived`, and the picker on the product tab
  lists the registry's empty `allowed_values` (`product_spec_registry.py:585-599`), which is why
  it says "No results found" and why typing a brand there creates a shadow value.
- **Who reads the Brand specification value today:** search binds a brand from the Brands master
  and filters on the stored spec value (`product_spec_search.py:320-332, 342-370, 460-489`); the
  customer sentence leads with it (`product_spec_rendering.py:150`); the understanding prompt
  offers stored values minus the registry row's `excluded_values` OTHERS and NO LOGO
  (`product_spec_understanding.py:151-170, 189, 206`); derivation flags company copies that
  disagree on brand (`product_spec_derivation.py:1680-1692`, 6 rows catalogue wide at the time
  that comment was written).
- `brand_id` is not in `DERIVATION_INPUTS` (`product_spec_change_listener.py:66-73`). With the
  Brand specification gone this stops mattering: nothing derived depends on the brand.
- **The rule engine today** (`_rule_matches`, `product_spec_derivation.py:708-800`) runs nine
  match kinds: `contains`, `ends_with`, `present`, `regex`, `code_suffix`, `code_contains`,
  `code_starts_with`, `from_field`, `name_head`. `regex` and `present` take a raw regular
  expression. The shipped list is 269 rules over 50 specifications; 49 of them carry a regular
  expression (`_rules_from_shipped_tables`, `product_spec_registry.py:283-520`).
- **A sentence layer already exists:** each rule may carry a `builder` (the sentence it was made
  from), compiled server side by `compile_builder` (`product_spec_registry.py:190-250`) and
  client side by `lib/ruleSentence.ts` `compileBuilder`; a save where the two disagree is refused.
  The builder menu has 12 kinds and 41 shipped rules have no builder, which is why those show raw.
- Catalogue freshness `finished_at` lives in process memory (`product_spec_rederive.py:32-33`);
  the rules fingerprint is persisted in a `product_spec_search_policy` row.
- The record page renders `PageHeader` outside `Container` (`SpecKeyRecordDetail.tsx:100,114,150`).

## 3. Design decisions

### Brand (owner ruling, Q1, Q2, Q4)

- **D1 The Brand specification is removed.** The product's brand field (`products.brand_id`) is
  the only brand. The `brand` registry row is deleted, and `brand` is removed from every product's
  stored specifications, provenance, verification stamps and exceptions. It is not in the list,
  not on the product tab, not in Add specification, not in Spec Verification.
- **D2 Every reader of the Brand specification reads the product's brand instead.**
  - Search: a brand the customer names binds to `products.brand_id` (joined through `brands`)
    instead of the stored spec value. Same Brands master names, same longest-name-wins binder.
  - Customer sentence: `product_spec_rendering` reads `product.brand.brand_name`.
  - Understanding prompt: brand names come from the Brands master (`brand_names`, already there).
  - Company copies that disagree on brand: the derivation flag goes (there is nothing derived to
    disagree). The 6 rows are listed in the lane evidence so the owner sees them once.
  - `from_field` loses the `brand` choice (`from_field_choices`, `FROM_FIELD_OPTIONS`).
  S0 starts with a grep for every other reader (`values["brand"]`, `read("brand")`,
  `spec_key == "brand"`, the MCP catalogue) and lists them in the evidence before changing any.
- **D3 What replaces the cases the Brand specification served:**
  - *"Customers never ask for OTHERS or NO LOGO"* (the row's `excluded_values`): a column
    `brands.is_searchable` (default true, false for OTHERS and NO LOGO), the same name and meaning
    `product_categories.is_searchable` already has. The Brand form shows it as "Customers can ask
    for this brand". Search and the prompt skip a brand where it is false; the existing rule that
    "NO LOGO" binds only on the full phrase stays.
  - *"Words customers say for a brand"* (the row's `user_synonyms`): if S0's measurement finds any,
    they move to a `brands.search_synonyms` column, the shape `product_categories.search_synonyms`
    already has. If it finds none, no column is added (trigger named: the first brand word a
    person needs).
  - *"Pick a brand on the product tab"*: the product's Details tab, which already has the Brand
    dropdown over the Brands master (`ProductForm.tsx:39`, `useBrandSelectQuery`).
- **D4 Evidence to clear before the removal migration** (owner ruling, Q2): the lane evidence file
  lists, from the dev database, (1) every value typed into the old empty picker: `user_values`,
  `value_labels`, `suppressed_values` and `user_synonyms` on the `brand` row; (2) every product
  whose Brand spec is `source: human`, with the typed value beside the product's own brand;
  (3) every product whose stored Brand spec differs from its brand field. Where a typed value
  names a real brand and the product's brand field is empty, the evidence says so and the owner
  decides; nothing is copied into `brand_id` silently.

### Rule engine (owner ruling, Q5, Q6)

- **D5 One rule model, five kinds, no patterns.** A rule is three picks and an optional fourth,
  stored as the `builder` the screen already saves. The engine compiles it; nobody types or sees a
  regular expression, and the server refuses a rule without a builder.

  | Part | What the person does | Choices |
  | --- | --- | --- |
  | **Look in** | picks where to read | Description or flyer (default), Description only, Flyer only, The product name (without sizes and extras, the default for Product class). Code and Product rules read their own place, so Look in is not asked. |
  | **Find** | picks a kind, fills its blanks | **Words**: one or more words ("SOFT CLOSE", "SOFT CLOSING"); optionally "only at the end of the name"; optionally "skip it when it comes right after" some words. **Number**: the number before / after / between words, optionally "written in" a unit (metres to mm), optionally "ignore numbers below". **Size**: from a size like 1500 x 750 x 630, the 1st / 2nd / 3rd / 4th number, or the one labelled L / W / H. **Code**: the product code contains / starts with / ends with some text. **Product**: a fact already on the product: its category's class, its length / width / height, or what its name says it is. |
  | **Answer** | picks the value | A choice from the spec's list; Yes for yes or no specs. Number, Size and Product rules answer with what they find, so Answer is not asked. |
  | **Only when** (optional) | adds a condition | Another spec is, or is not, one of some values ("Except when Shape is Round or Square"). |

  **How matching works, the same for every rule, never a setting:**
  - Case never matters.
  - Words match whole words only: "LED" never matches inside "SEALED".
  - Between the words of a phrase, a space, a hyphen or nothing all count: "PULL OUT SHOWER"
    matches "PULL-OUT SHOWER" and "PULLOUT SHOWER"; "SOFT CLOSE" matches "SOFT-CLOSE".
  - "..." inside a phrase means "anything in between, in the same sentence": "PP ... SEAT"
    matches "PP SOFT CLOSE SEAT COVER".
  - A number is a whole number or a decimal, and must stand on its own: the 1008 in SRTKS1008L is
    never read, because a letter or digit touches it in front. Between the number and its word a
    space, a hyphen or nothing all count ("3-WAY", "3 WAYS", "8OZ").
  - Rules run top to bottom; the first rule that reads something wins. Order is set by dragging.

  **Examples, one per kind, all built-in rules today** (all 268 are in the appendix):
  - Words: "When the description or flyer says SOFT CLOSE or SOFT CLOSING, Soft close is Yes."
  - Words with skip: "When the description or flyer says SCREW, Comes with a fixing screw is Yes.
    Skip it when it comes right after W/O or WITHOUT."
  - Words at the end: "When the product name ends with MIRROR CABINET or VANITY CABINET, Product
    class is Bathroom Furniture."
  - Words with "...": "When the flyer says PP ... SEAT, Seat cover material is PP."
  - Number: "The number before OZ, in the description or flyer." (Capacity (oz))
  - Number, written in: "The number before M, written in metres (stored in mm), in the description
    or flyer." (Hose length)
  - Number, between: "The number between S TRAP or P TRAP and MM, in the description or flyer."
    (Trap outlet length)
  - Number, with a floor and a skip: "The number before MM, in the description. Ignore numbers
    below 10. Skip it when it comes right after S TRAP or P TRAP. Except when Shape is Round or
    Square." (Length, the single stated size)
  - Size: "From a size like 1500 x 750 x 630, the 3rd number, in the description. Only when Shape
    is Round or Square." (Thickness)
  - Size, labelled: "From a size, the number labelled W (like W165), in the flyer." (Width)
  - Code: "When the product code ends with -GM, Finish or colour is Gunmetal."
  - Product: "The product category's class." and "What the product's name says it is." (Product
    class); "The product's length. Except when Shape is Round or Square." (Length)

  **Why this covers every case:** the appendix restates all 268 remaining built-in rules in these
  five kinds with none left over (231 Words, 10 Number, 10 Size, 12 Code, 5 Product). Rules next to
  each other with the same answer fold into one rule with several words, so 268 rows become 202.
  If a future case does not fit, that is a defect in the engine to fix in the engine (owner
  ruling, Q6), not a reason to reopen patterns.

  **Parity gate:** the built-in rules are converted to builders and run through the new compiler;
  derivation over the dev catalogue is compared with today's (golden parity). The new matching
  rules above were chosen to reproduce each built-in, but a few are deliberately not identical,
  and every product whose value changes is listed in the lane evidence for the owner before
  merge: Ways and Spray functions now read two-digit numbers (today one digit only); Power now
  needs the number to stand on its own; "OVER FLOW" now also matches "OVER-FLOW"; the flyer's L,
  W and H rows now read the number labelled inside a size.
- **D6 Plain words everywhere** (review section 2 vocabulary table): type chip List / Number (mm)
  / Yes or no / Text; tabs Details / Choices and words / How it is read / Products; "The product's
  category's class", "The product's length"; no "Seed", "User", "shipped", "default", `_self`,
  code name, "Derived" or "Findable by description" on any screen.
- **D7 `_self` moves to Details** as "Other names for this specification" (same stored map,
  `synonyms._self` / `user_synonyms._self`, no backend change). Choices and words never lists it.
- **D8 No Advanced anywhere** (owner ruling, Q6). The code name, "Built in / Added here", the
  rule count and the pattern are not shown on any screen. The product tab's raw search diagnosis
  goes; its plain facts ("Search finds this product", what search matches) stay in Reading and
  search. A rule that was changed shows "Changed here" and **Put back the built-in rules**.
- **D9 Product tab order**: checked line, values table, price tag wording (where it is today, owner
  ruling), then one collapsed **Reading and search** section (description, search finds it or
  not, what search matches, read specs from a text, read this product again). The Unverify
  confirm dialog becomes a 5 s deferred Undo (PRINCIPLES D7).
- **D10 List status is one pill, persisted** (Q8, still open): Up to date / Needs a re-read /
  Reading. The finish time is stored in a second `product_spec_search_policy` row beside the
  fingerprint, so a deploy does not reset it (a row, seeded on first write, no migration).
- **D11 Back sits with the title**: wrap `PageHeader` in `Container` on the record page (all three
  states) and copy "Back to specifications".
- **D12 Product class keeps its list shape** (Q3, still open): its choices are the category class
  labels, editable per product because a product's name can rightly say a different class from
  its category. See the round 2 answer in PR #1290 for class versus category.

Not in this lane (triggers named, per "Simplest thing"): per-brand rule sets; a translated
vocabulary; plural matching ("BOWL" also matching "BOWLS") as an engine rule (trigger: the second
spec where a person had to type both forms and forgot one).

## 4. Slices

Each slice is a commit set on the lane branch. Phase 1 (FE against mocks) runs across S1 to S3
first; S0 is mostly backend and goes test-first straight away.

### S0 - Remove the Brand specification

Scope: D1 to D4.
- Evidence first (section 7), written to the lane evidence file before any code.
- BE: readers switched to the product's brand (D2); `brands.is_searchable` column (and
  `brands.search_synonyms` only if measured); Brand form switch; `from_field` loses `brand`.
- Migration: delete the `brand` registry row; strip `brand` from `product_specifications.values`,
  provenance, verification and exceptions. Idempotent.
- FE: nothing brand-specific is left on the spec screens; the product tab has no Brand row.
**Definition of done:** UAC AC-S0.1 to AC-S0.8 green; search evals that name a brand ("sorento
kitchen sink", "no logo kitchen sink") return the same products before and after; agent-browser
run at 375 and 1280 showing no Brand in the list, the product tab or Add specification.

### S1 - The rule engine and its screen

Scope: D5 to D8 on the spec record page.
- BE: `compile_builder` gains the five kinds and their options; `_rule_matches` runs builders; save
  refuses a rule without a builder or with an empty blank; migration converts the shipped rules
  (from the rewritten `_rules_from_shipped_tables`) and every stored rule to builders, folding
  neighbours with the same answer; a stored rule that cannot convert is listed in the evidence
  (expected none; the owner sees any before merge).
- FE: How it is read lists sentences; Add / Edit a rule is a modal with Look in, Find, Answer,
  Only when, a live sentence, Try it on and See what would change; drag to reorder; Changed here
  and Put back the built-in rules (deferred 5 s).
- Details: Name, Unit (not on List specs), In use, Highest believable value, Other names.
- Choices and words: no `_self` card, no "user" badge, no code name.
**Definition of done:** AC-S1.1 to AC-S1.13 green; golden parity over the dev catalogue with every
changed product listed; browser run on Finish or colour, Capacity (oz) and Length at both widths.

### S2 - Product Specifications tab declutter

Scope: D9.
**Definition of done:** AC-S2.1 to AC-S2.8 green; browser run on SRTWC7604-SC-SH (the owner's
screenshot product) at both widths: first values row visible without scrolling at 1280.

### S3 - List and navigation

Scope: D6 (list), D10, D11.
- Columns: Specification, Type (unit folded in), Choices, Products. Code, Rules and Built in are
  hidden by default in the column chooser (Q11, still open; recommendation restated in PR #1290).
- One status pill, persisted finish time; Re-read beside Needs a re-read.
- Record page header inside `Container`; "Back to specifications".
**Definition of done:** AC-S3.1 to AC-S3.8 green; restart the API and the pill still reads Up to
date; browser run at both widths with the Back link aligned to the title's gutter.

### Phase 3 (once per lane)

`reviewer` + browser verification in parallel. `security-reviewer` runs: S0 changes what the
external search surface binds (the chatbot's product search), which is an external ingest path.

## 5. Files expected to change

BE: `app/services/product_spec_search.py`, `product_spec_rendering.py`,
`product_spec_understanding.py`, `product_spec_derivation.py` (`_rule_matches`, `_record_read`,
the brand flag), `product_spec_registry.py` (seed row, shipped rules as builders,
`compile_builder`, `from_field_choices`, save validation), `product_spec_rederive.py` (persisted
finish time), `app/models/product.py` (`Brand.is_searchable`), two migrations. FE:
`PS/lib/ruleSentence.ts` (the five kinds, mirrored), `PS/components/SpecRuleEditor.tsx` (the rule
modal), `PS/components/record/*`, `PS/components/SpecKeyRecordDetail.tsx`,
`PS/components/SpecRegistryGrid.tsx`, `PS/components/CatalogueFreshnessLine.tsx`,
`products/[id]/components/ProductSpecificationsTab.tsx`, `components/spec-table/*`, the Brand form.

## 6. Risks

- **Search by brand is a customer-facing path.** Mitigation: the brand evals in S0's definition
  of done, and security-reviewer on the lane.
- **Parity changes are real changes.** Every changed product is listed for the owner; none ships
  unseen.
- **Two compilers (server and browser) must agree.** Today's refuse-on-mismatch save stays, and a
  shared fixture (every appendix rule, compiled both sides) pins them.
- **Company scoping:** `Brand` is company scoped; the search join and the Brand form switch read
  through the same scope as the product (LESSONS: scoped reference tables).
- **The MCP catalogue** may list `brand` as a spec key for n8n. S0's grep covers
  `sorento_crm_mcp/`; if it does, the catalogue drops it and says the brand is a product field.

## 7. Evidence to gather at S0 start (read-only, dev DB)

1. On the `brand` registry row: `user_values`, `value_labels`, `suppressed_values`,
   `user_synonyms`, `excluded_values`, verbatim. These are the brands typed into the old empty
   picker, to be cleared by the S0 migration.
2. Products whose Brand spec is `source: human`: code, typed value, product's brand.
3. Products whose stored Brand spec differs from `brands.brand_name` (case-insensitive), by
   source; and products with no `brand_id` but a Brand spec value.
4. The company-copy brand disagreements (the derivation flag's rows).
5. Stored `derivation_rules` rows with no `builder`, per spec (the rules S1 converts), and any
   custom regular expression a person typed.

## 8. Grill questions

### Answered in round 1

1. When a person picks a brand on the Specifications tab, what changes? **Owner ruling, 26 Sep
   2026:** the Brand specification is redundant; the product's brand field is the only brand. (D1)
2. Brands already typed into the old empty picker? **Owner ruling, 26 Sep 2026:** refer to 1.
   Listed in the evidence, then cleared with the Brand specification. (D4)
4. OTHERS and NO LOGO in the brand dropdown? **Owner ruling, 26 Sep 2026:** refer to 1. The
   dropdown is the Details tab's, which already lists every brand; search skips them through
   `brands.is_searchable`. (D3)
5. How does a built-in rule become a sentence? **Owner ruling, 26 Sep 2026:** a rule engine that
   is easily and fool-proofly configured, not just sentences. (D5)
6. Who sees Advanced? **Owner ruling, 26 Sep 2026:** no Advanced; if the engine cannot cover a
   case simply, the engine is the problem. (D5, D8)
7. Price tag wording (the owner's line 7). **Owner ruling, 26 Sep 2026:** okay where it is. (D9)
12. One lane or four? **Owner ruling, 26 Sep 2026:** one lane.

### Open for round 2 (asked in PR #1290, "Answers to the owner's questions (round 2)")

3. Is product class the same as product category? Answered there with an example.
   Recommendation: keep Product class as a specification with its list of class labels (D12).
7. What does the product's Specifications tab show first? Recommendation: checked line, values,
   price tag wording, then collapsed Reading and search. Confirm the owner's line 7 was the price
   tag question (Q10), and whether this order stands.
8. What replaces "Never read" and "Rules changed since"? Recommendation: one pill, Up to date /
   Needs a re-read (with Re-read beside it) / Reading, and it survives a deploy.
9. Tab names on a spec's page? Recommendation: Details, Choices and words, How it is read,
   Products.
10. Where does the price tag wording live? Taken as answered by the owner's line 7 ("okay where
    it is"): stays on the Specifications tab, below the values, with "Not set, the price tag uses
    the product description" when empty. Confirm.
11. Why hide the Code, Rules and Built in columns? Answered there. Recommendation: hidden by
    default in the column chooser, not deleted.

## 9. Mockups (for the owner's Lavish review before build)

Each file has a 1280 frame, a 375 frame and numbered notes citing the UAC ids. Regenerated in
round 2: no Brand specification anywhere, and the rule engine screen.

| File | Screen | Slices |
| --- | --- | --- |
| `mockups/01-spec-list.html` | Product Specifications list (no Brand row) | S0, S3 |
| `mockups/02-spec-details.html` | A spec's Details tab (Capacity (oz)), Back placement | S1, S3 |
| `mockups/03-spec-choices-words.html` | Finish or colour, Choices and words | S1 |
| `mockups/04-spec-how-it-is-read.html` | How it is read: the rule list and the rule form (all five kinds) | S1 |
| `mockups/05-product-specifications-tab.html` | A product's Specifications tab, no Brand row | S0, S2 |
