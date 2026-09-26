# UX review - Product specifications, for a non-technical staff member (#1286)

**Issue:** #1286 (owner, 26 Sep 2026, seven screenshots). **Companions:**
`PLAN-product-specs-non-technical-26sep.md`, `product-specs-non-technical-acceptance-criteria.md`,
mockups under `mockups/`.
**Measured against:** `origin/main` at `51d30ccc5`. Every file:line below is on that commit.
**Status:** Review written 26 Sep 2026. No code changes in this lane. Owner rulings of 26 Sep 2026
supersede its brand verdicts (the Brand specification is removed) and its Advanced verdicts (no
Advanced; a rule engine instead); the plan's section 3 carries the current design.

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

Verdict key used below: **Keep** (stays in the default view, maybe reworded), **Merge** (folded
into another element), **Advanced** (moves behind the one Advanced disclosure on that screen),
**Remove** (goes; nothing depends on a person seeing it). `PS/` is
`sorento_crm_frontend/app/(protected)/master-data-management/product-specifications/`.

---

## 3. Screen: Product Specifications list (screenshot 7)

Who: spec owner. Job: find a spec, open it, add one. 53 specs, most built in.

| # | Element | Where | What it is for | Can a non-technical person use it? | Verdict |
| --- | --- | --- | --- | --- | --- |
| L1 | Page title "Product Specifications" | `PS/page.tsx:11` | Orientation | Yes | Keep |
| L2 | Freshness line: "Reading...", **"Never read"**, "Catalogue read {date}" | `PS/components/CatalogueFreshnessLine.tsx:26-37` | Says whether products were re-read after rules changed | No. "Never read" is also **false after every restart**: `finished_at` lives in the API process's `_STATE` dict (BE `app/services/product_spec_rederive.py:32-33`), so a read catalogue says "Never read" after each deploy | Merge into one status pill (L3) |
| L3 | Badge **"Rules changed since"** | `CatalogueFreshnessLine.tsx:38-42`; BE fingerprint compare `product_spec_rederive.py:90-101` | Says products may carry values from old rules | No: a sentence fragment with no object, and it can sit beside "Never read", contradicting it | Merge: one pill, **Up to date** / **Needs a re-read** (with the Re-read button beside it) / **Reading... 40%**; the date moves to the pill's tooltip |
| L4 | Search "Find a specification, word or product code" | `SpecRegistryGrid.tsx:299-305` | Find a spec by name, by a customer word, or list a product's specs | Yes | Keep |
| L5 | Column **Label** | `:95-107` | The name | Yes | Keep, rename header to **Specification** |
| L6 | Column **Code** (`brand`, `capacity_oz`) | `:108-123` | The storage slug, used by n8n and the parser | No | Advanced (column hidden by default; the column chooser already exists on DataGrid) |
| L7 | Column **Type** (Choice / Number / Yes or no / Text) | `:124-136`, `lib/specTypeLabel.ts:9-19` | What kind of answer | Mostly. "Choice" is the word the owner stumbled on | Keep, reword: **List**, **Number (mm)** (unit folded in), **Yes or no**, **Text** |
| L8 | Column **Unit** | `:137-147` | Unit of a number | Yes, but it is half of the Type | Merge into Type ("Number (mm)") |
| L9 | Column **Values** (a count; Brand shows 0) | `:148-158` | How many choices | Misleading for open lists (Brand 0, Product class 0) | Keep, reword to **Choices**; Brand shows the Brands master count, Product class the category class count; numbers and yes/no show "-" |
| L10 | Column **Rules** (a count) | `:159-169` | How many readers | A count says nothing to a merchandiser | Remove from default (Advanced column) |
| L11 | Column **Seen in** | `:170-184` | How many products carry it | Yes, and it is the most useful number on the page | Keep, header **Products**, links to the Seen in products tab |
| L12 | Column **Source** (Seed / User) | `:185-202` | Built in vs added here | No. "Seed" is a developer word | Advanced column, reworded **Built in** / **Added here** |
| L13 | Add specification | `:274-279` | Add a spec | Yes | Keep |
| L14 | Actions > Try a phrase | `:327-332` | Test what search understands from a customer phrase | Yes for the spec owner, and it is the one tool that answers "why did search not find it" | Keep |
| L15 | Actions > Reread catalogue | `:336-341` | Re-run derivation over every product | Yes once it sits next to the status that asks for it | Merge into L3 (the button appears when the status is Needs a re-read; stays in Actions too) |
| L16 | Row menu > Delete specification, disabled for built-in rows with no reason | `PS/actions.tsx:55-63` | Delete an added spec | The silent disabled item is confusing | Keep, hide the item on built-in rows instead of disabling it |
| L17 | Bulk Delete selected, toast "N skipped (shipped with the product)" | `:251-262` | Bulk delete | Yes | Keep, toast reworded "N built-in specifications were left alone" |

## 4. Screen: a spec's record page (screenshots 3, 4, 5, 6)

Who: spec owner. Job: rename, add a value and its words, check how it is read, see which products
carry it.

### 4.1 Page header and card

| # | Element | Where | For | Verdict |
| --- | --- | --- | --- | --- |
| R1 | **"Back to Product Specifications" flush right** (screenshot 6) | `PS/components/SpecKeyRecordDetail.tsx:95,150` | Return to the list | **Fix.** Cause: `<PageHeader>` is rendered bare at `:150` (also `:100`, `:114`) while every other detail page wraps it in `<Container>` (`products/[id]/page.tsx:38-54`, `brands/[id]/page.tsx:97-107`), and `Container` (`components/common/container.tsx:8`) is what adds `px-4 lg:px-6`. Without it the button loses the gutter and hugs the window edge. Wrap it; and follow the house copy "Back to specifications" (lowercase, like "Back to brands") |
| R2 | Title = the record label ("Brand") | `:150` | Orientation | Keep |
| R3 | Card title repeats the label, then **"Choice"** and **"Seed"** badges | `record/SpecKeyRecordCard.tsx:38-49` | Identity | Merge: label shown once (page title); the type chip reads **List** / **Number (mm)** / **Yes or no**; Seed goes to Advanced |
| R4 | Small print **"brand Unit None Active"** | `SpecKeyRecordCard.tsx:51-68` | Slug, unit, active | Remove from the card. Slug to Advanced; unit and active already live on the Header tab (`record/HeaderTab.tsx:52-75`), so this is a duplicate; "Active" can even print twice (`:57-67`) |
| R5 | Pager, gear, Edit | `SpecKeyRecordDetail.tsx:71-83,131-146` | Standard record chrome | Keep |
| R6 | Tabs Header / Values and words / Rules / Seen in products | `:162-168` | Sections | Keep the four, rename: **Details** / **Choices and words** / **How it is read** / **Products** |

### 4.2 Header tab (renamed Details)

| # | Element | Where | Verdict |
| --- | --- | --- | --- |
| H1 | Label | `HeaderTab.tsx:38-50` | Keep, field name **Name** |
| H2 | Unit ("None" when empty) | `:52-65` | Keep; empty shows "-" not "None"; on a List spec the field is not shown at all (a brand has no unit) |
| H3 | Active switch | `:67-75` | Keep, label **In use** |
| H4 | "Ignore values above (unit)" | `:77-99` | Keep for numbers, label **Highest believable value** (empty = "No limit") |
| H5 | (new) **Other names for this specification** | today the `_self` card in Values and words | Moves here: the words that name the spec itself ("oz", "ounce", "ounces"). One token field. This is where `_self` belongs, because it is about the spec, not about a value |
| H6 | (new, Advanced) Code, Built in / Added here, Rules count | today on the card and the list | Advanced disclosure at the bottom of the tab |

### 4.3 Values and words tab (renamed Choices and words) (screenshot 4)

| # | Element | Where | Verdict |
| --- | --- | --- | --- |
| V1 | One card per value: display name | `record/ValuesAndWordsTab.tsx:87-100` | Keep |
| V2 | Raw slug chip `<code>{value}</code>` | `:102` | Advanced (shown only when Advanced is open) |
| V3 | Badge **"user"** | `:103-107` | Remove; Advanced shows "Added here" |
| V4 | The **`_self` card** ("_self _self user") | `:216-220` (built from `Object.keys(words)`), `:84` heading, `:102` chip, `:256-260` badge | **Remove from this tab**; its words move to Details as "Other names for this specification" (H5). `_self` is never rendered anywhere |
| V5 | Display label input | `:142` | Keep, label **Shown as** |
| V6 | Words customers say | `:154` | Keep; the owner's example of a good plain label |
| V7 | Suppress / Put back (built-in values) | `:108-133` | Keep, labels **Stop using** / **Use again** |
| V8 | Empty state "No values yet" + Add value | `:223-245` | Keep. On a **number** spec the tab shows only "Numbers have no choices. Other names for this specification are on Details." as its empty state |
| V9 | **Brand and Product class** | none today: the tab is empty for both | New: Brand lists the **Brands master** read-only (name, logo, "Open in Brands" link per row, and "Add a brand" going to the Brands master); Product class lists the category classes the same way. Words customers say stay editable per brand (the synonyms map keeps them) |

### 4.4 Rules tab (renamed How it is read) (screenshots 3 and 5)

| # | Element | Where | Verdict |
| --- | --- | --- | --- |
| U1 | Try it on (product search or pasted text) | `SpecTryItPanel.tsx:32-99` | Keep, **moved below the list**: the rules are the subject, trying them is the check. Help sentence at `:94-99` removed (in-UI explanation) |
| U2 | Rule number | `RulesTab.tsx:81-83` | Keep (order matters: first one that reads wins) |
| U3 | Badge "default" (view) vs **"shipped"** (edit) for the same rule | `RulesTab.tsx:84-88`, `SpecRuleEditor.tsx:433-442` | Remove both. A changed rule list says "Changed here" once, above the list, with **Put back the built-in rules** (clears the stored list so the built-in one runs again) |
| U4 | Rule sentence | `RulesTab.tsx:94` via `lib/ruleSentence.ts:42-91` | **Rewrite.** View mode calls `ruleSentence`, which feeds the raw pattern into the sentence whenever `plainPattern` (`:23-39`) gives up, and it gives up on **every number rule** (`number_after`, `number_before`, `number_between`, `size_triple` all compile to parentheses). `builderSentence` (`:215-249`) already produces "Number before `OZ`" and has **no UI caller**. The 25 built-in pattern rules have no builder at all (BE `product_spec_registry.py:268-376`, for example `capacity_oz` at `:326-328`) |
| U5 | "Pattern" + raw regex input + ", capture the 1 number" | `SpecRuleEditor.tsx:478-495` | Advanced |
| U6 | Source select "Description and flyer" | `SpecRuleEditor.tsx:514-524`, options `:98-113` | Merge into the sentence ("...in the description or flyer"); the select stays in edit mode with plain options |
| U7 | "> Advanced" per rule | `SpecRuleEditor.tsx:526-539,558-577` | Keep as the **only** place a pattern shows; one per rule |
| U8 | Kind select options | `SpecRuleEditor.tsx:50-63` | Keep, already plain |
| U9 | From-field options "the `dimensions_length` column", "the `list_price` column" | `SpecRuleEditor.tsx:70-89`, `ruleSentence.ts:205-212` | Reword: "the product's brand", "the product's category", "the product's length", "the product's list price" |
| U10 | "From the product's brand field" | `ruleSentence.ts:208` | Reword **"The product's brand"** (from the Brands master) |
| U11 | Preview on catalogue (edit mode) | `SpecPreviewPanel.tsx:90-154` | Keep, label **See what would change**; idle help text removed |
| U12 | `where` wording for `size_text` and `class_tail` sources says "the description or flyer" (wrong) | `ruleSentence.ts:44-49` | Fix alongside U4 |

### 4.5 Seen in products tab (renamed Products)

| # | Element | Where | Verdict |
| --- | --- | --- | --- |
| P1 | Grid Code, Description, Class, Value, Source | `record/SeenInProductsTab.tsx:98-148` | Keep |
| P2 | Evidence column (mono) | `:159` | Keep, header **Read from**, not mono |
| P3 | Search and Value / Class / Source filters | `:232-265` | Keep |

## 5. Screen: a product's Specifications tab (screenshots 1 and 2)

Who: merchandiser. Job: are this product's specs right? Fix one, add one, say it is right. Today
the values table, which is the answer, is the **eighth** block down, under five blocks of
tooling (`products/[id]/components/ProductSpecificationsTab.tsx`).

| # | Element | Where | For | Verdict |
| --- | --- | --- | --- | --- |
| T1 | Card title "Specifications" | `:477` | | Keep |
| T2 | Pill **"Findable by description"** / "Not findable" | `:482-489` | Whether search can find the product from its text | Merge into the quiet section's header as a plain line ("Search finds this product" / "Search cannot find this product yet") |
| T3 | Pill **"Derived"** (status with `_` replaced, capitalised) | `:490-495`, `lib/status-pill.ts:93-94` | Whether values were read, set by hand or need review | Remove. The Source column already says it per value, and Verify says whether a person agrees |
| T4 | Kebab "Read this product again" | `:496-508` | Re-derive this product | Keep, moves into the quiet section |
| T5 | Verification strip: **Unverified** pill, Verify button, "by X, date", what moved since | `VerificationStrip` `:147-232` | A person vouching the specs are right | Keep **on top**, one line: "Not checked yet [Mark as checked]" / "Checked by X on date [Undo]". The Unverify confirm `AlertDialog` (`:617-640`) is a D7 defect (confirm dialog on a reversible action) and becomes a 5 s deferred Undo |
| T6 | Diagnosis alert when not findable ("Spec derivation currently runs for Kitchen Sink only", "BRAND-CLASS", "ranker") | `:523-531`, copy `:79-132` | Explain why search misses the product | Advanced (inside the quiet section, reworded) |
| T7 | Product description (mono) | `:533-540` | The text the values were read from | Merge: shown once, as the quiet section's first line, not mono |
| T8 | Price tag description, "(none)", Edit | `PriceTagDescriptionBlock` `:243-405` | The dealer-kit price tag wording | Keep, but it is not a specification: moves below the values as its own labelled row "Price tag wording", empty state "Not set, the price tag uses the product description" + Edit |
| T9 | **Read specs from a text** (textarea, "Read specs from this") | `SpecExtractPanel.tsx:67-170`, mounted `:558-563` | Paste a flyer card or supplier line and get proposed values | Merge into the quiet section, collapsed |
| T10 | **What search actually matches** | `:565-574` | The sentence search indexes | Merge into the quiet section; always renders (today it vanishes when empty, breaking the every-section rule) |
| T11 | **Every value, and where it came from** (values table) | `:580-598`, `components/spec-table/SpecTable.tsx` | THE answer | **Keep, first**, eyebrow removed (the tab is the heading) |
| T12 | Values table: Specification, Value, Source pill, Actions | `SpecTable.tsx:155-298` | | Keep; Source labels already plain (`SpecSourceBadge.tsx:39-47`); the Brand source reads **"Product's brand"** instead of "Description" (today every derived value is stamped `derived` and `SpecSourceBadge.tsx:40` labels that "Description", so a brand read off the product's brand row claims it came from the description; the rule kind has to reach the label) |
| T13 | Brand row editor (the empty picker) | `SpecValueCell.tsx:148-196` | | **Fix (S0).** Brand is not edited here at all: it shows the product's brand, with "Change on Details" linking to the product's Brand field, which is where the fact lives. Product class does the same pointing at the category |
| T14 | "Add a specification" button | `SpecTable.tsx:318-325` | | Keep, copy "Add specification" (matches the list) |
| T15 | Footer "To try a customer phrase ... use Product Specifications." | `:642-651` | | Remove (in-UI explanation) |

## 6. Cross-cutting findings

1. **Three sources for brand** (section 1.2). One must win: the Brands master.
2. **The FE already has the plain sentence and does not use it** (`builderSentence`, no caller).
   Most of S1 is wiring plus 25 hand-written sentences for built-in pattern rules.
3. **In-UI explanations** at `SpecTryItPanel.tsx:94-99`, `SpecPreviewPanel.tsx:150-154`,
   `ProductSpecificationsTab.tsx:642-651`, and the T6 diagnosis copy break PRINCIPLES "No feature
   explanations inside the UI".
4. **A confirm dialog on Unverify** (`ProductSpecificationsTab.tsx:617-640`) breaks D7.
5. **"Never read" after every deploy** (L2): catalogue freshness is held in process memory and
   must move to the database (the fingerprint already lives in `ProductSpecSearchPolicy`, so the
   finish time can sit beside it).
6. **No shared Advanced disclosure** exists. The only one is ad hoc in `SpecRuleEditor.tsx:378`.
   House precedent for a disclosure is `components/ui/collapsible.tsx` as used in
   `products/components/ProductAttachmentsTab.tsx:335-358`. One small `AdvancedSection` built on
   `Collapsible` is justified here by four call sites in this lane (record Details, Choices and words,
   How it is read, the product tab's quiet section).
7. **Every section renders**: "What search actually matches" hides when empty (T10).

## 7. Verdict table

| Screen | Keep | Merge | Advanced | Remove |
| --- | --- | --- | --- | --- |
| List | L1, L4, L5 (as Specification), L7 (reworded), L9 (as Choices), L11 (as Products), L13, L14, L16, L17 | L2 + L3 + L15 into one status pill; L8 into L7 | L6 Code, L10 Rules, L12 Source | "Never read", "Rules changed since", "Seed", "User" |
| Record header | R2, R5, R6 (renamed tabs) | R3 into the page title + one type chip | slug, Seed/User | R4 small print, the second and third copy of the label |
| Details | H1-H4 (reworded), H5 new | `_self` words into H5 | Code, Built in, Rules count | |
| Choices and words | V1, V5-V8, V9 new | | V2 slug | V3 "user", V4 `_self` card |
| How it is read | U1 (moved below), U2, U8, U11 | U6 into the sentence | U5 pattern, U7 per rule | U3 default/shipped badges, U1 help text |
| Product Specifications tab | T1, T5 (on top, reworded), T11 first, T12, T14 | T2, T4, T7, T9, T10 into one quiet section "Reading and search"; T8 below the values | T6 diagnosis | T3 Derived pill, T15 footer, T11 eyebrow, the Unverify confirm dialog |
