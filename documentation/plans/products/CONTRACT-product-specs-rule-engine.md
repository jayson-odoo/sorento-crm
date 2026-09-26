# Contract - the rule engine and the spec screens' API (#1286)

**Companion to:** `PLAN-product-specs-non-technical-26sep.md` (D5, D10, D14 to D16) and
`product-specs-non-technical-acceptance-criteria.md`. Written by the captain before Phase 2 so the
tester, the backend coder and the frontend coder build to one shape. Where this contract and the
UAC disagree, the UAC wins and this file is corrected.

## 1. A stored rule

A rule is its builder and nothing else:

```json
{ "builder": { "kind": "words", "look_in": "any", "words": ["SOFT CLOSE", "SOFT CLOSING"], "value": true } }
```

Shipped rules also carry `"_seed": true` (internal, never rendered, used only by the deploy-time
seed repair). No stored rule carries `match`, `pattern`, `capture`, `scale`, `source`, `unit`,
`applies_when` or `unless` after the S1 migration: those are compiled from the builder at run time.

### 1.1 The builder, per kind

Every builder may carry `only_when`: `{"spec": "shape", "is": false, "values": ["round", "square"]}`
("Only when Shape is not Round, Square"). `is: true` = only when the spec holds one of the values;
`is: false` = except when it does. One condition per rule. `spec` is never `brand`.

| kind | fields | notes |
| --- | --- | --- |
| `words` | `look_in`, `words` (1+), `at_end` (bool, default false), `skip_after` (0+), `value` | `value` is the spec's choice key for a List spec, `true` for a Yes or no spec, a number for a Number spec |
| `number` | `look_in`, `before` (0+), `after` (0+), `written_in` (`null`, `"centimetres"`, `"metres"`), `ignore_below` (number or null), `skip_after` (0+) | at least one of `before` / `after`. Before only = "the number before", after only = "the number after", both = "the number between". Sets what it finds |
| `size` | `look_in`, `pick`: `1`, `2`, `3`, `4`, `"L"`, `"W"` or `"H"` | sets what it finds |
| `code` | `code_match`: `"contains"`, `"starts_with"` or `"ends_with"`, `texts` (1+), `value` | reads the product code only |
| `product` | `fact`: `"class"` (its category's class), `"name"` (what its name says it is), `"length"`, `"width"`, `"height"` | reads the product record only; sets what it finds |

`look_in`: `"any"` (Description or flyer, the default), `"description"`, `"flyer"`, `"name"` (the
product name without sizes and extras, the default for Product class). Absent means the key's
default (`name` for `class`, `any` for everything else).

Words and texts are stored upper case, trimmed, with no empties and no duplicates.

## 2. Matching (the same for every rule, never a setting)

All text is upper cased before matching. The compiled pattern must be valid in BOTH Python `re`
and JavaScript `RegExp` (lookbehind is fine in both).

- **Phrase**: split each word on `...` into segments; split each segment on runs of spaces and
  hyphens into tokens; escape each token with the existing JS-compatible `_escape`; join tokens
  with `[\s\-]*` (a space, a hyphen or nothing). Each segment is bounded by letters only:
  `(?<![A-Z])` before and `(?![A-Z])` after (this is today's `contains` bound, so "LED" never
  matches inside "SEALED"). Segments are joined with `[^.]*?` ("anything in between, in the
  same sentence").
- **Words** pattern: `(?:P1|P2|...)` in the order given; with `at_end`, followed by `\s*$`.
- **Standalone number** `N`: `(\d+(?:\.\d+)?)`. A number read BEFORE a word must stand on its
  own: preceded by `(?<![A-Z0-9.])(?<![A-Z0-9]-)` (a letter or digit touching it, directly or
  across a hyphen, means it is part of a code: the 1008 in SRTKS1008L, the 809 in F-809L).
- **Number** pattern: before only `{standalone}N[\s\-]*(?:W...)(?![A-Z])`; after only
  `(?:A...)[\s\-:,]*N`; between `(?:A...)[\s\-:,]*N[\s\-]*(?:W...)(?![A-Z])`. `A` and `W` are
  phrases as above. A colon or comma after the word also counts on the "after" side
  ("S-TRAP:250MM").
- **Size** pattern: the size regex, 2 to 4 labelled-or-not parts:
  `PART = (?:([LWHD])\s*)?(\d+(?:\.\d+)?)\s*(?:MM)?`, `SIZE = PART\s*[X*]\s*PART(?:\s*[X*]\s*PART)?(?:\s*[X*]\s*PART)?`.
  Labels are groups 1, 3, 5, 7; numbers 2, 4, 6, 8. `pick: n` reads the nth number of the FIRST
  size in the text (skipped when that part is absent); `pick: "L"` reads the number labelled L in
  the first size that labels one.
- **skip_after**: compiled to `(?<![A-Z])(?:S1|S2)[\s\-:,(]*$`, searched against the text BEFORE a
  hit; when it matches, that hit is skipped and the next hit is tried.
- **ignore_below**: a found number below it is skipped and the next hit is tried.
- **written_in**: `centimetres` multiplies by 10, `metres` by 1000 (the catalogue stores mm).
- **Code**: `contains` / `starts_with` / `ends_with` on the upper-cased code, any of `texts`.
  `ends_with "-GM"` is exactly today's `code_suffix GM`.
- Rules run top to bottom; the first rule that reads something wins (Finish keeps its
  multi-value collection from one origin, exactly as today). A gate (`only_when`) is answered
  from what the same derivation has read so far, exactly as `applies_when` / `unless` are today.

### 2.1 The compiled result (what the shared fixture pins)

`compile_builder(builder)` (Python, `app/services/product_spec_rules.py`) and `compileBuilder(builder)`
(TypeScript, `lib/ruleSentence.ts`) both return:

```json
{ "kind": "number", "scope": "any", "pattern": "...", "capture": 1, "skip": null,
  "scale": null, "min": null, "pick": null, "code_match": null, "texts": null, "fact": null }
```

`scope` is `look_in` (or `null` when absent), `"code"` for code, `"product"` for product.
`pattern` is `null` for code and product. `capture` is 1 for number, `null` otherwise.
The fixture `sorento_crm_frontend/app/(protected)/master-data-management/product-specifications/lib/__fixtures__/rule-builders.json`
is a list of `{"spec_key", "builder", "compiled"}` for every shipped rule plus the plan's
examples; pytest and vitest both assert their compiler reproduces `compiled` exactly.

## 3. Save validation (PATCH `/spec-registry/{key}` `derivation_rules`, `/try`, `/preview`)

Refused with **400** and a plain message naming the missing part (no underscore in any message):

| Case | message |
| --- | --- |
| rule without a builder, or not an object | `Rule {n} has no parts. Open it and pick what it reads.` |
| unknown `kind` | `Rule {n}: pick a kind (Words, Number, Size, Code or Product).` |
| unknown `look_in` | `Rule {n}: pick where to look.` |
| words: no words | `Rule {n}: add at least one word to find.` |
| words / code: no value | `Rule {n}: pick the value it sets.` |
| number: no before and no after | `Rule {n}: add at least one word next to the number.` |
| size: bad `pick` | `Rule {n}: pick which number of the size to read.` |
| code: bad `code_match` | `Rule {n}: pick how the code is matched.` |
| code: no texts | `Rule {n}: add at least one piece of code to find.` |
| product: bad `fact` | `Rule {n}: pick which fact about the product to read.` |
| `only_when` without a spec or values, or naming `brand` | `Rule {n}: pick the specification and at least one value for Only when.` |
| value not one of a List spec's choices | today's message (`spec_registry_unknown_rule_value`) reworded without key names |
| a rule on the `brand` key, or a spec write to `brand` | `Brand is not a specification. The product's brand is on its Details tab.` |

A rule the client sends with a `pattern` alongside its builder is compared with the server's
compile, and a mismatch is a 422 `Rule {n} does not match what the screen showed. Open it and save it again.`
The stored rule is `{"builder": cleaned}`.

## 4. Responses the screens read

- `GET /spec-registry`: each key's `effective_rules` is a list of `{"builder": {...}}`. The
  `shipped` tag and `rules_are_default` are gone. No `brand` key. Every other field unchanged.
- `PATCH /spec-registry/{key}`: the serialised key as today, plus `products_updated: int` when the
  save changed `derivation_rules`, `applies_when` or `max_value` (0 otherwise). The products
  whose stored value for that key would change are re-read through `rederive_codes` before the
  response returns (inline for a few, the `imports` queue above `INLINE_REDERIVE_LIMIT`), and the
  stored rules fingerprint is updated so the worker's start-up catch-up does not re-read them
  again.
- `POST /spec-registry/{key}/try`: unchanged shape (`reads[index]`, `winner_index`).
- `POST /spec-registry/{key}/preview` + poll: unchanged shape.
- Brands: `GET/POST/PATCH /master-data/brands` carry `is_searchable: bool` (default true).
  OTHERS and NO LOGO are seeded false by the S0 migration.

## 5. Catch-up after a deploy (AC-S3.5)

`product_spec_rederive.catch_up_on_worker_start()` runs once in `worker.py` start-up when the
worker drains the `imports` queue. It compares the stored fingerprint
(`product_spec_search_policy` row `_derived_rules_fingerprint`) with the running one (configured
rules, scopes and caps, plus `DERIVATION_VERSION`). Different: it enqueues one catalogue re-read
on `imports`, which stores the new fingerprint when it finishes. Same: it enqueues nothing.
