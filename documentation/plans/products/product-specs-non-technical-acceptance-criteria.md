# UAC - Product specifications a non-technical staff member can read and use (#1286)

**Companion to:** `PLAN-product-specs-non-technical-26sep.md` (design),
`rule-engine-built-in-rules.md` (every built-in rule in the new form) and
`UX-REVIEW-product-specifications-26sep.md` (diagnosis).
**Status:** DRAFT, round 4, 27 Sep 2026. Round 4 adds the Lavish notes of 27 Sep 2026, 00:45
MYT (structured rules grid, never sentences; no snake_case; the system's own dropdown and
multi-select in every rule selector; Reading and search reduced to the read values and one search
box) below the round 3 text. Rewritten to the owner rulings of 26 Sep 2026 (Brand
specification removed; a simple rule engine, no Advanced; price tag wording where it is; one
lane) and the Lavish mockup rulings of 27 Sep 2026 (no re-read pill or button, which answers
Q8; rules on their own tab, basic and non technical; no Advanced anywhere; every list of words
or brands is a data grid; no brand spec or brand picker on the product tab). ACs citing Q3, Q7,
Q9, Q10 or Q11 follow the recommendation until the owner answers or confirms; a different answer
amends the ACs that cite it.

**Owner rulings, 27 Sep 2026 (Lavish notes on mockups 01 to 05, verbatim in PR #1290):**
- Mockup 01, "Needs a re-read" pill: "don't need this"; "Re-read" button: "dont' need this".
  (AC-S3.4, AC-S3.5, AC-S2.5)
- Mockup 02, "Advanced / Code capacity_oz / Built in / 1 rule": "rule should be in own tab and
  don't need advanced, should be basic and non technical". (AC-S1.6, AC-S1.14, AC-S3.7)
- Mockup 03, "Words customers say" per brand: "this should be tabulated with data grid"; on
  "Advanced": "again don't need advanced, i want the system to be as basic as possible".
  (AC-S1.15, AC-S1.12)
- Mockup 04, "Changed here / Put back the built-in rules / Advanced / Pattern": "i don't need
  advanced, i need it to be as basic as possible". (AC-S1.6, AC-S1.10)
- Mockup 05, the brand picker on the Specifications tab: "we don't really need this spec at
  all". (AC-S0.7, AC-S2.7)
**Owner rulings, 27 Sep 2026, 00:45 MYT (Lavish notes on the plan and mockups, verbatim in PR #1290):**
- Plan page: "ok this is fine". Mockups 02 and 03: "ok this is ok" (both accepted as they are).
- Mockup 04, the sentence rules: "hmm can this be more structured?". (AC-S1.6, AC-S1.7, AC-S1.14)
- Mockup 04, the flexible rule row: "ok this is flexible, good, make sure no snake case".
  (AC-S1.17)
- Mockup 04, the "Look in / Find" controls: "use dropdown component in the system"; the chip
  inputs: "use multi select dropdown components in the system where applicable". (AC-S1.18)
- Mockup 05, "Reading and search": "simplify this, too messy". (AC-S2.1, AC-S2.5, AC-S2.10)
**Legend:** `[BE]` pytest (Postgres only) · `[FE]` vitest · `[E2E]` agent-browser evidence run
(sidebar clicks from `/`, 375 and 1280) · `[MIG]` migration · `[T]` CI guard.

## Journey

**A. Merchandiser** (`master_data.products.edit`), Products > a product > Specifications.

1. Sees one line "Not checked yet" with **Mark as checked**, then the product's specs as plain
   rows (Specification, Value, Where it came from). No Brand row. Nothing else open.
2. Corrects a wrong value by picking from its list.
3. Adds a missing specification from the Add specification dialog.
4. Marks the product as checked; can Undo within 5 s.
5. Reads the plain **Reading and search** section below the price tag wording when needed (the
   read values and one search box); never presses a re-read.

**B. Spec owner** (`master_data.spec_registry.*`), Master data > Product Specifications.

1. Sees the list with Specification, Type, Choices, Products; no Brand, no status pill, no
   Re-read.
2. Opens a spec; Back sits with the title; tabs Details, Choices and words, How it is read (the
   rules tab), Products.
3. Reads the rules as a structured grid, one row per rule and one column per part; no rule is
   a sentence and no pattern exists to show.
4. Adds a rule by picking Where to look, Kind, What to find and Value it sets (and optionally
   Only when) in the system's dropdowns and multi-selects, tries it on a product, sees what would
   change, saves; the changed products update by themselves.

## S0 - Remove the Brand specification (owner ruling, 26 Sep 2026, Q1, Q2, Q4)

**AC-S0.1 [MIG] [BE]** Given the `brand` registry row and products carrying a `brand` spec value
(any source, including `human`), when the migration runs, then the registry row is gone and no
product's stored specifications, provenance, verification stamps or exceptions mention `brand`.
Idempotent on a second run. (D1)

**AC-S0.2 [BE]** Before the migration, the lane evidence file lists, verbatim from the dev
database: the `brand` row's `user_values`, `value_labels`, `suppressed_values`, `user_synonyms`,
`excluded_values`; every product whose Brand spec is `source: human` with the typed value beside
its own brand; every product whose Brand spec differs from its brand field; and the company-copy
brand disagreements. (D4)

**AC-S0.3 [BE]** A customer phrase naming a brand ("sorento kitchen sink") binds that brand and
returns products whose `brand_id` is that brand, with the same products as before S0 on the eval
set; nothing reads a stored `brand` spec value. (D2)

**AC-S0.4 [BE] [FE]** A brand with `is_searchable` false (seeded for OTHERS and NO LOGO) is
never offered to the understanding model and a single generic word never binds it; "no logo
kitchen sink" still binds NO LOGO on the full phrase (existing tests stay green). The Brand form
shows the switch as "Customers can ask for this brand". (D3)

**AC-S0.5 [BE]** The customer sentence for a product leads with its brand field's name
("Sorento kitchen sink ..."), unchanged from before S0 for a product whose Brand spec equalled its
brand. (D2)

**AC-S0.6 [BE]** A rule or a spec value naming `brand` is refused on save; `from_field` offers
category and the numeric product columns only. `GET /spec-registry` returns no `brand` row. (D1)

**AC-S0.7 [FE]** Brand appears nowhere on the Product Specifications list, a spec's page, the
product's Specifications tab, Add specification, or Spec Verification. (D1)

**AC-S0.8 [E2E]** By sidebar clicks at 375 and 1280: the list has no Brand row; SRTWC7604-SC-SH's
Specifications tab has no Brand row; its Details tab still shows and edits the brand. (D1)

## S1 - The rule engine and its screen (owner ruling, 26 Sep 2026, Q5, Q6)

**AC-S1.1 [BE]** `compile_builder` accepts exactly five kinds (Words, Number, Size, Code,
Product) with the options in plan D5, and every rule in `rule-engine-built-in-rules.md` compiles
from its builder. A shared fixture of those rules gives the same compiled result server side and
in `lib/ruleSentence.ts`. (D5)

**AC-S1.2 [BE]** Matching follows plan D5 for every rule: case never matters; words match whole
words only; a space, a hyphen or nothing between the words of a phrase all match; "..." matches
anything within one sentence; a number touched in front by a letter or digit is never read.
One test per statement, each with a real catalogue phrase. (D5)

**AC-S1.3 [BE] [MIG]** After the conversion migration every stored rule carries a builder, and
neighbouring rules with the same answer are folded into one rule. A rule that cannot be converted
is listed in the evidence and the migration stops rather than dropping it. (D5)

**AC-S1.4 [BE]** Golden parity over the dev catalogue: every product whose derived value changes
is listed in the lane evidence with before, after and the rule; the only expected groups are the
four named in plan D5. (D5)

**AC-S1.5 [BE]** Saving a rule with no builder, an unknown kind, or an empty blank (no words, no
answer on a Words or Code rule) is refused with a 400 naming the missing part in plain words.
(D5)

**AC-S1.6 [FE]** How it is read shows the rules as a structured grid (AC-S1.14), in view and
edit mode, and no screen renders a rule as a sentence, a character of a regular expression, a
code name, an "Advanced" control, or a "shipped", "default", "built in", "Changed here", "Seed"
or "User" badge. (D5, D8, D14; owner rulings 27 Sep 2026)

**AC-S1.7 [FE]** Add a rule and Edit open a modal with, in order, the grid's parts: Where to
look (hidden for Code and Product), Kind (the five kinds), What to find (the kind's blanks),
Value it sets (List specs: the spec's choices; Yes or no specs: Yes; hidden for Number, Size and
Product), Only when (optional). Every blank is a pick (AC-S1.18) or a number. The modal renders
no sentence; below the fields it shows the rule as the one grid row it will become, updating as
the form changes. (D5, D14; owner ruling 27 Sep 2026, "hmm can this be more structured?")

**AC-S1.8 [FE]** Inside the rule modal, Try it on a product shows what the rule reads from it, or
"Reads nothing"; See what would change lists the products whose value would change before Save.
(D5)

**AC-S1.9 [FE]** Rules reorder by drag and by keyboard (move up, move down) while the grid is
sorted by Order; the order saved is the order run. Sorting by another column changes the view
only and hides the drag handles. (D5, D14)

**AC-S1.10 [FE]** No "Changed here" pill and no "Put back the built-in rules" action render. Removing
a rule is a deferred 5 s action with Cancel; no confirm dialog opens. (D8; owner ruling 27 Sep
2026, mockup 04)

**AC-S1.11 [FE]** Tabs read Details, Choices and words, How it is read, Products, in that order,
the same in view and edit. Rules render on How it is read and nowhere else. (Q9, pending
confirmation; D14)

**AC-S1.12 [FE]** Details shows Name, Unit (not on List specs), In use, Highest believable value
(numbers), and "Other names for this specification" as a data grid bound to `synonyms._self` /
`user_synonyms._self`. Details shows no code name, no "Built in / Added here", no rule count and
no Advanced. Choices and words never renders `_self`, a "user" badge or a code name; a number
spec shows an empty state pointing at Details. (D6, D7, D8, D13)

**AC-S1.13 [E2E]** Browser run at 375 and 1280 on Finish or colour (add a Words rule, try it,
see what would change, cancel; edit a Value it sets cell in place and cancel), Capacity (oz) and
Length: the rules show as grid rows, the rule modal is usable without horizontal page scroll at
375, and no screen shows Advanced, Re-read, a rule sentence, a pattern or an underscore.

**AC-S1.14 [FE]** The rules grid has one column per part: Order, Where to look, Kind, What to
find, Value it sets, Only when, a sortable header on each, and a row action menu (Edit, Move up,
Move down, Remove). What to find renders the kind's blanks as labelled values, never a sentence
("MATT BLACK, MAT BLACK"; "Before: OZ"; "After: S TRAP, P TRAP · Before: MM"; "3rd number";
"Ends with: -GM"; "The product's length"), with the optional parts as a second line ("Skip
after: W/O, WITHOUT", "Written in: metres", "Ignore below: 10"). Value it sets renders the
choice or "The number it finds"; Only when renders "Shape is not: Round, Square" or blank.
Clicking a What to find or Value it sets cell edits it in place with the same controls
(AC-S1.18) and validation as the modal; the pencil opens the full rule modal. The grid uses the
DataGrid fixed, resizable layout with explicit column sizes and truncate plus title for long
text. At 375 it keeps Order, What to find and Value it sets and scrolls inside its frame. (D14;
owner rulings 27 Sep 2026, mockup 02 and mockup 04)

**AC-S1.15 [FE]** Choices and words is a data grid, one row per choice: Choice, Words customers
say, Products, each header sortable. Clicking a Choice or Words cell edits it in place (words as a
comma list); Add a choice adds a row; Remove is deferred 5 s. No chips, token pills or cards
render for words at 1280 or 375; at 375 the grid keeps Choice and Words and scrolls inside its
frame, never the page. The same grid shape is used for Other names (AC-S1.12) and, if D3 adds
them, brand words on Master data > Brands. (D13; owner ruling 27 Sep 2026, mockup 03)

**AC-S1.16 [BE]** Saving a rule, a spec's scope or its highest believable value re-reads exactly
the products whose value changes, through `rederive_codes` (inline for a few, the `imports`
queue above the inline limit), and the save response carries that count for the toast "Saved. N
products updated." A test saves a Words rule over seeded products and asserts their stored value
changed with no other call. (D10; owner ruling 27 Sep 2026, answers Q8)

**AC-S1.17 [FE] [T]** No spec screen (list, record page tabs, rule modal, product
Specifications tab, Add specification, toasts, errors, empty states) renders a value with an
underscore between word characters. A vitest guard renders each screen over fixtures whose spec
keys, choice keys and source codes all carry underscores (`capacity_oz`, `rose_gold`,
`from_category`) and fails on any rendered text matching `\w_\w`; the 400 of AC-S1.5 names the
missing part in plain words. (D15; owner ruling 27 Sep 2026, "make sure no snake case")

**AC-S1.18 [FE]** Every single-pick selector in the rule modal and in the grid's in-place edit
(Where to look, Kind, before / after / between, which number, written in, contains / starts
with / ends with, which product fact, Value it sets, the Only when spec, is / is not) is
`SearchableSelect`, and every several-pick selector (the words to find, the skip-after words,
the code text, the Only when values) is `SearchableMultiSelect`, both from `components/common/`.
No segmented control, radio strip or hand-made chip box renders. In the words multi-select a
typed word not yet offered appears as the first option "Add {WORD}" and picking it adds it. A
test asserts the component used for each field. (D16; owner rulings 27 Sep 2026, "use dropdown
component in the system" and "use multi select dropdown components in the system where
applicable")

## S2 - Product Specifications tab

**AC-S2.1 [FE]** Top to bottom: checked line, values table, price tag wording, **Reading and
search** (always shown, not collapsed, no disclosure control). (Q7, pending confirmation; owner ruling 26 Sep 2026
for the price tag wording; owner ruling 27 Sep 2026, no Advanced anywhere)

**AC-S2.2 [FE]** No "Derived" pill, no "Findable by description" pill, no footer sentence, no
eyebrow above the values table, no raw search diagnosis, no Advanced. (Review T2, T3, T11, T15;
D8)

**AC-S2.3 [FE]** The checked line reads "Not checked yet" with **Mark as checked**, or
"Checked by {name} on {date}" with Undo; "Needs checking again" with what moved when a value
changed after checking. (Review T5)

**AC-S2.4 [FE]** Undo is a deferred 5 s action with Cancel; no confirm dialog opens (PRINCIPLES
D7). (Review T5)

**AC-S2.5 [FE]** Reading and search holds exactly two things, in order: **Read values**, one
plain line of what search reads for this product (empty: "Nothing read yet."), and **one search
box**, "Type what a customer would ask". Nothing else renders in the section: no product
description, no "Search finds this product" pill, no separate "What search matches" label, no
Read specs from a text panel. There is no "Read this product again" button: the product is
re-read by itself when its code, description, category, sizes or flyer reading changes. (Q7; D9;
owner rulings 27 Sep 2026, no re-read concept, and "simplify this, too messy")

**AC-S2.6 [FE]** Price tag wording renders below the values, where it is today; empty reads "Not
set, the price tag uses the product description" with Edit. (Owner ruling 26 Sep 2026; Q10,
pending confirmation)

**AC-S2.7 [FE]** The values table has no Brand row, Add specification offers no Brand, and no
brand picker renders anywhere on the tab; the source label never reads "Description" for a value
that came from the product record. (D1; review T12; owner ruling 27 Sep 2026, mockup 05)

**AC-S2.8 [E2E]** On SRTWC7604-SC-SH at 1280 the first values row is visible without scrolling
below the tab strip; at 375 nothing is clipped and no horizontal page scroll appears.

**AC-S2.9 [BE]** Editing a product's description (or its code, category or sizes), or saving a
new flyer reading for it, re-reads its specifications with no button pressed; the existing
listener tests stay green, and one test per trigger asserts the stored values changed after that
edit alone. (D9, D10)

**AC-S2.10 [FE]** Typing a phrase in the search box and pressing Enter runs the existing preview
search for that phrase and answers in one line: "This product comes up, 1st of 6" (its place among the results) when
the product is among the candidates, or "This product does not come up for this" when it is
not. No score, no matched keys, no understanding panel renders. (D9; owner ruling 27 Sep 2026,
"simplify this, too messy")

## S3 - List and navigation

**AC-S3.1 [FE]** List columns by default: Specification, Type, Choices, Products. Code, Rules and
Built in are available in the column chooser, hidden by default. (Q11)

**AC-S3.2 [FE]** Type reads List, Number (unit), Yes or no, Text. (Review L7, L8)

**AC-S3.3 [FE]** Choices for Product class equals the category class count; "-" for numbers and
yes or no. (Review L9; Q3)

**AC-S3.4 [FE]** The list renders no status pill, no Re-read button, and none of the words
"Never read", "Rules changed since", "Needs a re-read", "Re-read" or "Up to date". (Owner ruling
27 Sep 2026, mockup 01; answers Q8; D10)

**AC-S3.5 [BE]** When the worker starts and the stored rules fingerprint differs from the running
rules (a deploy changed the shipped rules), it queues one catalogue re-read and stores the new
fingerprint when that finishes; when they match it queues nothing. Two tests, one per case. (D10)

**AC-S3.6 [FE] [E2E]** On a spec's page the Back link sits in the page header inside the same
side gutter as the title and card, reading "Back to specifications", at 375 and 1280, in the
loading, not-found and loaded states. (Review R1)

**AC-S3.7 [FE]** The record card shows the label once (page title) and one type chip; no code
name, no "Built in", no rule count, no "Unit None", no duplicate "Active", no Advanced. (Review
R3, R4; owner ruling 27 Sep 2026, mockup 02)

**AC-S3.8 [FE]** Built-in specs show no Delete item in the row menu or the gear; added specs keep
a deferred delete. (Review L16)
