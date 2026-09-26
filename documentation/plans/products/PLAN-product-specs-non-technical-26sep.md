# PLAN - Product specifications a non-technical staff member can read and use (#1286)

**Slug:** `product-specs-non-technical-26sep` | **Domain:** products (master data)
**Issue:** #1286. **UAC:** `product-specs-non-technical-acceptance-criteria.md` (the contract; where
this plan and the UAC disagree, the UAC wins). **Review:** `UX-REVIEW-product-specifications-26sep.md`
(diagnosis with file:line; its brand verdicts are superseded by the round 1 rulings below).
**Rule appendix:** `rule-engine-built-in-rules.md` (every built-in rule in the new form).
**Mockups:** `mockups/`.
**Classification:** CORE, schema `public`. No new table, no new permission.
**Status:** DRAFT, round 4, 27 Sep 2026. Planned, not built. Round 1 owner rulings, the
round 3 Lavish mockup rulings and the round 4 Lavish notes applied (the three rulings sections
below, and section 8). Plan text accepted by the owner ("ok this is fine"); mockups 02 and 03
accepted as they are. Q8 is answered (no re-read concept on any screen). Waiting on the owner for Q3 and Q11 (answered in PR #1290 comment 5847720339), and
for confirmation of Q7, Q9 and Q10, which stay on the recommendation. **Track: full** (one lane,
expected diff well over 300 lines, two data migrations: the Brand specification removal and the
rule conversion).
**Alignment page:** `alignment-product-specs-27sep.html` (owner review surface in Lavish; it
restates this plan and must not contradict it).
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

## Owner rulings, round 3 (Lavish notes on the mockups, 27 Sep 2026, about 00:05 MYT, verbatim in PR #1290)

- **Owner ruling, 27 Sep 2026 (mockup 01, the "Needs a re-read" pill and the "Re-read"
  button):** "don't need this" / "dont' need this". Answers Q8: no re-read concept is shown on
  any screen. Applied as D10 (reading runs itself on save) and D9 (no "Read this product again").
- **Owner ruling, 27 Sep 2026 (mockup 02, "Advanced / Code capacity_oz / Built in / 1 rule"):**
  "rule should be in own tab and don't need advanced, should be basic and non technical". Applied
  as D8 and D14: rules live only on their own tab, How it is read, shown as a plain data grid.
- **Owner ruling, 27 Sep 2026 (mockup 03, "Words customers say" per brand):** "this should be
  tabulated with data grid". Applied as D13: every list of words or brands on these screens is a
  data grid with sortable columns and inline edit, never cards or chips.
- **Owner ruling, 27 Sep 2026 (mockup 03 and mockup 04, "Advanced", "Changed here / Put back
  the built-in rules / Advanced / Pattern"):** "again don't need advanced, i want the system to
  be as basic as possible" / "i don't need advanced, i need it to be as basic as possible".
  Applied as D8: no Advanced, no collapsed tooling drawer, no pattern, and no "built-in versus
  changed here" distinction on any screen.
- **Owner ruling, 27 Sep 2026 (mockup 05, the brand picker on the product's Specifications
  tab):** "we don't really need this spec at all". Confirms D1: no Brand specification and no
  brand picker on the Specifications tab.

## Owner rulings, round 4 (Lavish notes on the plan and mockups, 27 Sep 2026, 00:45 and 00:50 MYT, verbatim in PR #1290)

- **Owner ruling, 27 Sep 2026 (plan page):** "ok this is fine". Plan text accepted.
- **Owner ruling, 27 Sep 2026 (mockup 02, details; mockup 03, choices and words):** "ok this is
  ok" / "ok this is ok". Both accepted as they are.
- **Owner ruling, 27 Sep 2026 (mockup 01, the round 2 list):** "hmm i have provided my input on
  this before, did you not capture it?" / "like i don't want to needs a re-read and re-read".
  Already captured in round 3 (D10); the owner was looking at the round 2 list. The final list
  mockup carries no re-read pill and no Re-read button.
- **Owner ruling, 27 Sep 2026 (mockup 04, the sentence rules):** "hmm can this be more
  structured?". Applied as D14: the rules screen is a structured grid, one row per rule and one
  column per part (where to look, what to find, which value it sets). No rule is ever shown as a
  sentence, on the grid or in the rule form.
- **Owner ruling, 27 Sep 2026 (mockup 04, the flexible rule row):** "ok this is flexible, good,
  make sure no snake case". Applied as D15: no snake_case on any screen or mockup; every value
  reads in plain words.
- **Owner ruling, 27 Sep 2026 (mockup 04, the "Look in / Find" controls):** "use dropdown
  component in the system". **(mockup 04, the chip inputs):** "use multi select dropdown
  components in the system where applicable". Applied as D16: every selector in the rule form and
  the rules grid is the system's own `SearchableSelect` or `SearchableMultiSelect`
  (`components/common/`), never a segmented control or a hand-made chip box.
- **Owner ruling, 27 Sep 2026 (mockup 05, "Reading and search"):** "simplify this, too messy".
  Applied as D9: that block holds what a merchandiser needs, the read values and one search box,
  nothing else.
- **Owner ruling, 27 Sep 2026, 00:50 MYT (the alignment page):** "chatbot memory, product specs
  also need a final mockup to align, cost price yeah need final mockup ya". The alignment page
  carries the final mockup of every screen this plan touches, at 1280 and 375, with every ruling
  to date applied.

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
5. Below the price tag wording, a plain **Reading and search** section (always open, no drawer)
   holds two things only: the read values, the one line search reads for this product ("Water
   closet · One piece · Twister flush · S-trap · UF seat cover"), and one search box. They type
   "one piece toilet twister" and it answers "This product comes up, 1st of 6" (owner ruling, 27
   Sep 2026, "simplify this, too messy"). There is no "Read this product again": a product is read
   again by itself whenever its code, description, category or sizes change (owner ruling, 27 Sep
   2026).

What they hold at the end: correct specs, a checked stamp, and they never saw a pattern, a code
name, the word "Derived" or a re-read button.

**B. Spec owner changes how a spec is read** (`master_data.spec_registry.edit`), Master data >
Product Specifications.

1. The list shows Specification, Type ("List", "Number (mm)", "Yes or no"), Choices, Products.
   No status pill, no Re-read button (owner ruling, 27 Sep 2026). Brand is not in the list.
2. They open Finish or colour. Four tabs: **Details**, **Choices and words**, **How it is read**
   (the rules tab), **Products**.
3. **How it is read** is a structured grid of rules, one row each, in the order they run, one
   column per part: Order, Where to look, Kind, What to find, Value it sets, Only when.
   "1 · Description or flyer · Words · MATT BLACK · Black · (blank)". Columns sort; clicking a
   What to find or Value it sets cell edits it in place with the system's multi-select or
   dropdown. No rule is written as a sentence, no pattern exists anywhere to show, and nothing
   says "built in" or "changed here".
4. They press **Add a rule**. The rule form asks the same parts as the grid's columns, each a
   system dropdown (`SearchableSelect`) or multi-select (`SearchableMultiSelect`): **Where to
   look** (Description or flyer), **Kind** (Words), **What to find** (GUNMETAL, GUN METAL),
   **Value it sets** (Gunmetal). Optional: **Only when** another spec has some values. Under the
   form, the rule shows as the one grid row it will become. **Try it on** a real product shows
   what the rule reads; **See what would change** shows the products whose value would change
   before they save.
5. They save. The toast says "Saved. 14 products updated." (the same 14 See what would change
   listed). The products carry the new value within moments; nobody presses anything, and the
   list simply shows the current values.

Decisions per journey: A, one per wrong value plus one Mark as checked; B, the picks of a rule.
Nothing asks them for a code name, a pattern, a source code or a re-read, and nothing shows them
a value with underscores in it.

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
- **A product's own edit already re-reads it by itself:** `product_spec_change_listener`
  collects the codes whose derivation inputs changed and calls `rederive_codes`, inline for a few
  codes and on the worker's `imports` queue above `INLINE_REDERIVE_LIMIT`
  (`product_spec_change_listener.py:162-197`). **Saving a rule does not**: the catalogue is only
  re-read when someone presses Re-read (`product_spec_rederive.start`), which is why the list
  needed a status pill and a button at all.
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

- **D5 One rule model, five kinds, no patterns.** A rule is a set of picks, one per part, stored
  as the `builder` the screen already saves. The engine compiles it; nobody types or sees a
  regular expression, and the server refuses a rule without a builder. The parts below are the
  rules grid's columns (D14) and the rule form's fields, in the same order; the control named for
  each is the system's own (D16). The example sentences further down are this plan's shorthand
  for a reader of the plan; no screen shows a rule as a sentence (owner ruling, 27 Sep 2026).

  | Part (grid column and form field) | Control (D16) | Choices |
  | --- | --- | --- |
  | **Where to look** | `SearchableSelect` | Description or flyer (default), Description only, Flyer only, The product name (without sizes and extras, the default for Product class). Code and Product rules read their own place, so the field is not asked and the cell reads "Product code" or "The product". |
  | **Kind** | `SearchableSelect` | Words, Number, Size, Code, Product. |
  | **What to find** | per kind, below | **Words**: one or more words ("SOFT CLOSE", "SOFT CLOSING") in a `SearchableMultiSelect`; optionally "only at the end of the name" (a checkbox); optionally "skip it when it comes right after" some words (a second `SearchableMultiSelect`). **Number**: the number before / after / between (a `SearchableSelect`) some words (`SearchableMultiSelect`), optionally "written in" a unit (`SearchableSelect`: metres to mm), optionally "ignore numbers below" (a number input). **Size**: from a size like 1500 x 750 x 630, the 1st / 2nd / 3rd / 4th number, or the one labelled L / W / H (`SearchableSelect`). **Code**: the product code contains / starts with / ends with (`SearchableSelect`) some text (`SearchableMultiSelect`). **Product**: a fact already on the product (`SearchableSelect`): its category's class, its length / width / height, or what its name says it is. |
  | **Value it sets** | `SearchableSelect` | A choice from the spec's list; Yes for yes or no specs. Number, Size and Product rules set what they find, so the field is not asked and the cell reads "The number it finds". |
  | **Only when** (optional) | `SearchableSelect` (the spec), `SearchableSelect` (is / is not), `SearchableMultiSelect` (its values) | Another spec is, or is not, one of some values ("Shape is not Round, Square"). |

  **Typed words in a multi-select.** `SearchableMultiSelect` offers the words this spec already
  knows (its Choices and words grid, and the words its other rules use); a word not yet in the
  list is offered as the first option, "Add BRUSHED GOLD", built from the search text through the
  component's existing `onSearchChange`. No new component and no chip box: the picked words show
  inside the multi-select's own trigger.

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
  - Rules run top to bottom; the first rule that reads something wins. Order is the grid's Order
    column, changed by dragging a row or Move up / Move down (only while the grid is sorted by
    Order; sorting by another column only changes the view).

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
  each other with the same answer fold into one rule with several words, so 268 rows become 202 (203 after the lane added a Length rule for "(LENGTH-200MM)", see the appendix).
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
  / Yes or no / Text; tabs Details / Choices and words / How it is read / Products (Q9, pending
  confirmation); "The product's category's class", "The product's length"; no "Seed", "User",
  "shipped", "default", "built in", "Changed here", `_self`, code name, "Derived", "Findable by
  description", "Re-read" or "Needs a re-read" on any screen.
- **D7 `_self` moves to Details** as "Other names for this specification" (same stored map,
  `synonyms._self` / `user_synonyms._self`, no backend change), shown as a small data grid (D13).
  Choices and words never lists it.
- **D8 No Advanced anywhere, on any screen** (owner rulings, 26 Sep 2026 Q6 and 27 Sep 2026
  mockups 02 to 04). No Advanced disclosure, no collapsed tooling drawer, no pattern. The code
  name, "Built in / Added here" and the rule count are not on the Details tab; rules are only on
  their own tab (D14). The product tab's raw search diagnosis goes. The "Changed here" pill and
  "Put back the built-in rules" go too: a person sees rules, not where they came from. Removing a
  rule is a 5 s deferred action with Cancel (PRINCIPLES D7), which is the way back from a mistake.
  Trigger named for bringing a reset back: the first time the owner asks to restore a spec's
  shipped rules; until then it is a one-line data fix on request.
- **D9 Product tab order**: checked line, values table, price tag wording (where it is today, owner
  ruling), then a plain **Reading and search** section, always shown, not collapsed, holding two
  things only (owner ruling, 27 Sep 2026, "simplify this, too messy"):
  - **Read values**: one plain line of what search reads for this product ("Water closet · One
    piece · Twister flush · S-trap · UF seat cover"; empty: "Nothing read yet.").
  - **One search box**: "Type what a customer would ask". It runs the existing preview search
    (`POST /product-specifications/preview-search`, the ranker the chatbot uses) and answers in
    one line: "This product comes up, 1st of 6" or "This product does not come up for this".
  Gone from the tab: the description text (it is on Details), the "Search finds this product"
  pill (the box answers it), the separate "What search matches" label (it is the read values
  line) and the "Read specs from a text" panel (`SpecExtractPanel`; its endpoint stays, trigger
  named for bringing the panel back: a merchandiser asks for it). No "Read this product again": the
  change listener already re-reads a product when its code, description, category or sizes change
  (`DERIVATION_INPUTS`, section 2), so the button has nothing left to do (owner ruling, 27 Sep
  2026). S2 starts by checking whether a new flyer reading re-reads the product the same way; if
  it does not, the flyer save calls `rederive_codes` for that one code. The Unverify
  confirm dialog becomes a 5 s deferred Undo (PRINCIPLES D7).
- **D10 Reading runs itself; no re-read concept on any screen** (owner ruling, 27 Sep 2026,
  answers Q8). How a changed rule reaches products without a visible re-read:
  - Saving a rule, a spec's scope or its highest believable value re-reads that one spec's
    products straight away. The save already knows which products change (it is the same list
    See what would change shows), so it hands exactly those codes to `rederive_codes`, the same
    path a product edit uses: a few inline, many on the worker's `imports` queue. The toast says
    "Saved. N products updated."
  - A deploy that changes the shipped rules: the worker compares the stored rules fingerprint
    with the running rules on start and, when they differ, re-reads the catalogue once on the
    queue and stores the new fingerprint. Nobody is asked to do anything.
  - The list and the product tab simply show the current stored values. The "Never read" line,
    the "Rules changed since" badge, the status pill and the Re-read button are removed; the
    catalogue-wide Re-read endpoint stays for support use only, with no button.
  - No persisted finish time is needed any more (the round 2 second policy row is dropped).
- **D13 Every list of words or brands is a data grid** (owner ruling, 27 Sep 2026, mockup 03):
  sortable column headers, inline edit on the cell, Add a row at the foot, deferred remove per
  row. Applies to: Choices and words (one row per choice: Choice, Words customers say, Products;
  the words cell edits in place as a comma list), "Other names for this specification" on
  Details (one row per word), and brand words on Master data > Brands if D3's measurement finds
  any (one row per word: Word, Brand). No chips, no cards, at 1280 or 375; at 375 the grid keeps
  its first two columns and scrolls inside its own frame, never the page.
- **D14 Rules live on their own tab, as a structured grid, never sentences** (owner rulings, 27
  Sep 2026, mockup 02, and mockup 04 "hmm can this be more structured?"). How it is read is the
  rules tab (its name is Q9, pending confirmation). One row per rule and one column per part:
  **Order**, **Where to look** (Description or flyer, Product code, The product name ...),
  **Kind** (Words, Number, Size, Code, Product), **What to find** (the blanks of that kind, as
  labelled values, not a sentence: "MATT BLACK, MAT BLACK"; "Before: OZ"; "After: S TRAP, P
  TRAP · Before: MM"; "3rd number"; "Ends with: -GM"; "The product's length"; the optional parts
  as a second line: "Skip after: W/O, WITHOUT", "Written in: metres", "Ignore below: 10"),
  **Value it sets** (the choice, or "The number it finds"), **Only when** ("Shape is not: Round,
  Square", or blank). No per-rule product count: the stored reading records the matched text,
  not which rule set it, and counting would need new bookkeeping; the Products tab and See what
  would change already answer "which products" (trigger named: the owner asks which rule set a
  given value). Sortable columns; What to find and Value it sets edit in place with the same
  system controls as the form (D16); the pencil opens the rule form (mockup 04) for every part.
  The form has no sentence: under its fields it shows the rule as the one grid row it will
  become.
- **D15 No snake_case anywhere** (owner ruling, 27 Sep 2026, "make sure no snake case"). No
  screen, mockup, toast, error or empty state shows a value with an underscore in it: a spec
  reads by its label ("Capacity (oz)", never `capacity_oz`), a choice by its label ("Rose gold",
  never `rose_gold`), a source by its plain name ("Set by hand", never `human`), and a server
  error naming a missing part names it in plain words ("Add at least one word to find"). A
  vitest guard renders the spec screens over fixtures whose keys carry underscores and fails on
  any rendered `\w_\w`.
- **D16 The system's own selectors, everywhere in the rule form and the rules grid** (owner
  rulings, 27 Sep 2026, "use dropdown component in the system" and "use multi select dropdown
  components in the system where applicable"). A single pick (Where to look, Kind, before / after
  / between, which number, written in, ends with / starts with / contains, which product fact,
  Value it sets, the Only when spec and is / is not) is `SearchableSelect`; a pick of several
  (the words to find, the skip-after words, the code text, the Only when values) is
  `SearchableMultiSelect`, both from `components/common/` (the pair CLAUDE.md already mandates
  for every dropdown). The round 2 segmented Find control and the hand-made chip boxes go. The
  one control that is neither is "ignore numbers below", a number `Input` from `components/ui`.
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
- BE: saving a rule, scope or cap re-reads exactly the products it changes through
  `rederive_codes` (D10); the worker re-reads the catalogue once on start when the stored rules
  fingerprint differs from the running rules.
- FE: How it is read is a structured grid of rules (D14): Order, Where to look, Kind, What to
  find, Value it sets, Only when; sortable; What to find and Value it sets edit in place; drag or
  Move up / Move down while sorted by Order; deferred 5 s remove. Add / Edit a rule is a modal
  with the same parts in the same order, every selector a `SearchableSelect` or
  `SearchableMultiSelect` (D16), the rule previewed as its grid row (no sentence), Try it on and
  See what would change. No Changed here, no Put back the built-in rules. No snake_case (D15).
- Details: Name, Unit (not on List specs), In use, Highest believable value, and Other names as
  a small data grid (D13).
- Choices and words: a data grid, one row per choice, words edited in place (D13); no `_self`
  row, no "user" badge, no code name.
**Definition of done:** AC-S1.1 to AC-S1.18 green; golden parity over the dev catalogue with every
changed product listed; browser run on Finish or colour, Capacity (oz) and Length at both widths.

### S2 - Product Specifications tab declutter

Scope: D9, D15.
**Definition of done:** AC-S2.1 to AC-S2.10 green; browser run on SRTWC7604-SC-SH (the owner's
screenshot product) at both widths: first values row visible without scrolling at 1280.

### S3 - List and navigation

Scope: D6 (list), D10 (list side), D11.
- Columns: Specification, Type (unit folded in), Choices, Products. Code, Rules and Built in are
  hidden by default in the column chooser (Q11, still open; recommendation restated in PR #1290).
- No status pill, no Re-read button, no "Never read" line, no "Rules changed since" badge (owner
  ruling, 27 Sep 2026). The list shows current values only.
- Record page header inside `Container`; "Back to specifications".
**Definition of done:** AC-S3.1 to AC-S3.8 green; browser run at both widths with no re-read
wording anywhere and the Back link aligned to the title's gutter.

### Phase 3 (once per lane)

`reviewer` + browser verification in parallel. `security-reviewer` runs: S0 changes what the
external search surface binds (the chatbot's product search), which is an external ingest path.

## 5. Files expected to change

BE: `app/services/product_spec_search.py`, `product_spec_rendering.py`,
`product_spec_understanding.py`, `product_spec_derivation.py` (`_rule_matches`, `_record_read`,
the brand flag), `product_spec_registry.py` (seed row, shipped rules as builders,
`compile_builder`, `from_field_choices`, save validation, re-read on save),
`product_spec_rederive.py` (fingerprint catch-up on worker start), `worker.py`, `app/models/product.py` (`Brand.is_searchable`), two migrations. FE:
`PS/lib/ruleSentence.ts` (the five kinds, mirrored), `PS/components/SpecRuleEditor.tsx` (the rule
modal), `PS/components/record/*`, `PS/components/SpecKeyRecordDetail.tsx`,
`PS/components/SpecRegistryGrid.tsx`, `PS/components/CatalogueFreshnessLine.tsx` (removed),
`products/[id]/components/ProductSpecificationsTab.tsx` (Reading and search: read values and
one search box over the existing preview search; `SpecExtractPanel` no longer mounted there),
`components/spec-table/*`, the Brand form, and one vitest snake_case guard (D15).

## 6. Risks

- **Search by brand is a customer-facing path.** Mitigation: the brand evals in S0's definition
  of done, and security-reviewer on the lane.
- **Parity changes are real changes.** Every changed product is listed for the owner; none ships
  unseen.
- **Two compilers (server and browser) must agree.** Today's refuse-on-mismatch save stays, and a
  shared fixture (every appendix rule, compiled both sides) pins them.
- **Company scoping:** `Brand` is company scoped; the search join and the Brand form switch read
  through the same scope as the product (LESSONS: scoped reference tables).
- **Re-read on save is now automatic, so a too-broad rule reaches products at once.** Mitigation:
  See what would change is shown in the form before Save, and a removed rule is a 5 s deferred
  action. A rule touching thousands of products goes to the worker like a large import does.
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

### Answered in round 3 (Lavish notes on the mockups, 27 Sep 2026)

8. What replaces "Never read" and "Rules changed since"? **Owner ruling, 27 Sep 2026:** on the
   "Needs a re-read" pill, "don't need this"; on the Re-read button, "dont' need this". No re-read
   concept is shown on any screen; reading runs itself on save and after a deploy, and the list
   simply shows the current values. (D10)

### Still open (asked in PR #1290, "Answers to the owner's questions (round 2)")

3. Is product class the same as product category? Answered there with an example.
   Recommendation: keep Product class as a specification with its list of class labels (D12).
7. What does the product's Specifications tab show first? Recommendation: checked line, values,
   price tag wording, then the plain Reading and search section (no longer collapsed: owner
   ruling, 27 Sep 2026, no Advanced or drawer anywhere; simplified to the read values and one
   search box: owner ruling, 27 Sep 2026, 00:45 MYT). Pending confirmation: confirm the owner's line 7 was the price
   tag question (Q10), and whether this order stands.
9. Tab names on a spec's page? Recommendation, pending confirmation: Details, Choices and words,
   How it is read (the rules tab), Products. Under the other choice only the labels change; the
   rules still sit on their own tab.
10. Where does the price tag wording live? Taken as answered by the owner's line 7 ("okay where
    it is"): stays on the Specifications tab, below the values, with "Not set, the price tag uses
    the product description" when empty. Pending confirmation.
11. Why hide the Code, Rules and Built in columns? Answered there. Recommendation: hidden by
    default in the column chooser, not deleted.

### New in round 4 (asked on the alignment page)

13. "Read specs from a text" leaves the product tab under the 27 Sep 2026 00:45 MYT ruling
    ("simplify this, too messy"; the read values and one search box, nothing else). Agreed?
    Recommendation: yes; the extract endpoint stays, so the panel can return if a merchandiser
    asks (D9). Under the other choice it returns as a third item under the search box, a paste
    box with one "Read specs from this" button.

## 9. Mockups (for the owner's Lavish review before build)

Each file has a 1280 frame, a 375 frame and numbered notes citing the UAC ids. Round 3
regenerated them to the 27 Sep 2026 00:05 MYT notes (no re-read pill or button, no Advanced or
collapsed drawer anywhere, words as data grids, no brand spec or brand picker, a sixth mockup for
the rules tab). Round 4 is the final set, to the 00:45 MYT notes: 02 and 03 accepted as they
are (03's one note no longer spells a snake_case example); 04 and 06 restructured (structured
grid columns, no sentences, the system's `SearchableSelect` and `SearchableMultiSelect` in every
selector); 05's Reading and search simplified to the read values and one search box; 01
unchanged from round 3 (it already has no re-read). All six are embedded in
`alignment-product-specs-27sep.html`.

| File | Screen | Slices |
| --- | --- | --- |
| `mockups/01-spec-list.html` | Product Specifications list: no Brand row, no status pill, no Re-read | S0, S3 |
| `mockups/02-spec-details.html` | A spec's Details tab (Capacity (oz)), Other names as a grid, Back placement (accepted) | S1, S3 |
| `mockups/03-spec-choices-words.html` | Finish or colour, Choices and words as a data grid with inline edit (accepted) | S1 |
| `mockups/04-spec-how-it-is-read.html` | The rule form: Add a rule with system dropdowns and multi-selects, and the five kinds filled with built-in rules | S1 |
| `mockups/05-product-specifications-tab.html` | A product's Specifications tab: no Brand row, Reading and search as read values plus one search box | S0, S2 |
| `mockups/06-spec-rules-grid.html` | How it is read, the rules tab: a structured grid, one column per part | S1 |
