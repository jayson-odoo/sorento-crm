# UAC - Product specifications a non-technical staff member can read and use (#1286)

**Companion to:** `PLAN-product-specs-non-technical-26sep.md` (design),
`rule-engine-built-in-rules.md` (every built-in rule in the new form) and
`UX-REVIEW-product-specifications-26sep.md` (diagnosis).
**Status:** DRAFT, round 2, 26 Sep 2026. Rewritten to the owner rulings of 26 Sep 2026 (Brand
specification removed; a simple rule engine, no Advanced; price tag wording where it is; one
lane). ACs citing Q3, Q7, Q8, Q9, Q10 or Q11 follow the recommendation until the owner answers
round 2; a different answer amends the ACs that cite it.
**Legend:** `[BE]` pytest (Postgres only) · `[FE]` vitest · `[E2E]` agent-browser evidence run
(sidebar clicks from `/`, 375 and 1280) · `[MIG]` migration · `[T]` CI guard.

## Journey

**A. Merchandiser** (`master_data.products.edit`), Products > a product > Specifications.

1. Sees one line "Not checked yet" with **Mark as checked**, then the product's specs as plain
   rows (Specification, Value, Where it came from). No Brand row. Nothing else open.
2. Corrects a wrong value by picking from its list.
3. Adds a missing specification from the Add specification dialog.
4. Marks the product as checked; can Undo within 5 s.
5. Opens **Reading and search** only when needed.

**B. Spec owner** (`master_data.spec_registry.*`), Master data > Product Specifications.

1. Sees the list with Specification, Type, Choices, Products and one status pill; no Brand.
2. Opens a spec; Back sits with the title; tabs Details, Choices and words, How it is read,
   Products.
3. Reads every rule as one sentence; no pattern exists to show.
4. Adds a rule by picking Look in, Find and Answer (and optionally Only when), tries it on a
   product, sees what would change, saves, re-reads the catalogue from the status pill.

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

**AC-S1.6 [FE]** How it is read lists each rule as one numbered sentence built from its builder,
in view and edit mode, and no screen renders a character of a regular expression, a code name, or
a "shipped", "default", "Seed" or "User" badge. (D5, D8)

**AC-S1.7 [FE]** Add a rule and Edit open a modal with, in order: Look in, Find (the five kinds),
Answer (List specs: the spec's choices; Yes or no specs: Yes; hidden for Number, Size and
Product), Only when (optional). Every blank is a pick or a typed word. The sentence at the top of
the modal updates as the form changes. (D5)

**AC-S1.8 [FE]** Inside the rule modal, Try it on a product shows what the rule reads from it, or
"Reads nothing"; See what would change lists the products whose value would change before Save.
(D5)

**AC-S1.9 [FE]** Rules reorder by drag and by keyboard (move up, move down); the order saved is
the order run. (D5)

**AC-S1.10 [FE]** A spec whose rules were changed shows "Changed here" above the list and **Put
back the built-in rules**, a deferred 5 s action with Cancel. (D8)

**AC-S1.11 [FE]** Tabs read Details, Choices and words, How it is read, Products, in that order,
the same in view and edit. (Q9)

**AC-S1.12 [FE]** Details shows Name, Unit (not on List specs), In use, Highest believable value
(numbers), and "Other names for this specification" bound to `synonyms._self` /
`user_synonyms._self`. Choices and words never renders `_self`, a "user" badge or a code name; a
number spec shows an empty state pointing at Details. (D6, D7)

**AC-S1.13 [E2E]** Browser run at 375 and 1280 on Finish or colour (add a Words rule, try it,
see what would change, cancel), Capacity (oz) and Length: every rule reads as a sentence and the
rule modal is usable without horizontal scroll at 375.

## S2 - Product Specifications tab

**AC-S2.1 [FE]** Top to bottom: checked line, values table, price tag wording, **Reading and
search** (collapsed). (Q7; owner ruling 26 Sep 2026 for the price tag wording)

**AC-S2.2 [FE]** No "Derived" pill, no "Findable by description" pill, no footer sentence, no
eyebrow above the values table, no raw search diagnosis. (Review T2, T3, T11, T15; D8)

**AC-S2.3 [FE]** The checked line reads "Not checked yet" with **Mark as checked**, or
"Checked by {name} on {date}" with Undo; "Needs checking again" with what moved when a value
changed after checking. (Review T5)

**AC-S2.4 [FE]** Undo is a deferred 5 s action with Cancel; no confirm dialog opens (PRINCIPLES
D7). (Review T5)

**AC-S2.5 [FE]** Reading and search holds, in order: the product description (not monospace),
"Search finds this product" or "Search cannot find this product yet", what search matches (empty:
"Nothing yet. Read this product again to build it."), Read specs from a text, Read this product
again. Closed by default and remembered per viewer. (Q7)

**AC-S2.6 [FE]** Price tag wording renders below the values, where it is today; empty reads "Not
set, the price tag uses the product description" with Edit. (Owner ruling 26 Sep 2026; Q10)

**AC-S2.7 [FE]** The values table has no Brand row, and the source label never reads
"Description" for a value that came from the product record. (D1; review T12)

**AC-S2.8 [E2E]** On SRTWC7604-SC-SH at 1280 the first values row is visible without scrolling
below the tab strip; at 375 nothing is clipped and no horizontal page scroll appears.

## S3 - List and navigation

**AC-S3.1 [FE]** List columns by default: Specification, Type, Choices, Products. Code, Rules and
Built in are available in the column chooser, hidden by default. (Q11)

**AC-S3.2 [FE]** Type reads List, Number (unit), Yes or no, Text. (Review L7, L8)

**AC-S3.3 [FE]** Choices for Product class equals the category class count; "-" for numbers and
yes or no. (Review L9; Q3)

**AC-S3.4 [FE]** One status pill: Up to date, Needs a re-read (with **Re-read** beside it), or
Reading. The words "Never read" and "Rules changed since" do not render. (Q8)

**AC-S3.5 [BE]** The catalogue read finish time persists in the database; after an API restart the
status reports the last finish time and Up to date when the fingerprint matches. (Q8)

**AC-S3.6 [FE] [E2E]** On a spec's page the Back link sits in the page header inside the same
side gutter as the title and card, reading "Back to specifications", at 375 and 1280, in the
loading, not-found and loaded states. (Review R1)

**AC-S3.7 [FE]** The record card shows the label once (page title) and one type chip; no code
name, no "Unit None", no duplicate "Active". (Review R3, R4)

**AC-S3.8 [FE]** Built-in specs show no Delete item in the row menu or the gear; added specs keep
a deferred delete. (Review L16)
