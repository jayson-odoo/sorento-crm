# UAC - Spec registry: every reader is a rule, rules read as sentences, try it on a real product

**Companion to:** `PLAN-spec-rules-readable.md`
**Status:** Pre-code. Approved 31 Aug 2026 (rulings R1-R8 in the plan). Expands #425.
**Legend:** `[BE]` pytest · `[FE]` vitest · `[E2E]` agent-browser · `[MIG]` migration · `[T]` CI guard.

## Journey

**Actor:** master-data staff with `master_data.spec_registry.edit`, on
Master data > Product specifications > a key (say Length).

1. The key opens on **How this is read from a product**: one ordered list, in the order the
   engine runs it. Nothing fires that is not in the list. Rows 1-3 are shipped ("From the
   product's `dimensions_length` column", "Size from `L x W x H`, take the 1st number",
   "Number before `MM`"); row 4 is theirs ("Number after the word `L`"). Every row is a
   sentence with editable blanks, a drag handle and a remove.
2. **Try it on** sits above the list: a product search over the whole master. They pick
   `SRTWC8354-SH-P`; its description shows; every row shows what it reads from it
   ("nothing" ... "nothing"); no winner. They pick a basin; row 3 reads "800 from `(800MM)`"
   and is marked as the winner.
3. They add a row from the sentence menu ("Number between `S-TRAP` and `MM`") and see "300
   from `S-TRAP 300MM`" at once. They remove row 3 with one click; the winner marker moves.
   **Advanced** on any row shows the pattern it compiles to; editing it turns the row into
   a pattern row (still a sentence: "Pattern `...`, capture the 1st number").
4. **Preview on catalogue**: before saving, a count of products whose value would change,
   with a sample of codes and before/after. Runs on the worker; the button waits.
5. Save once. The saved list is exactly what the engine runs. Products re-derive as today.
6. Same shape on every key. Class shows "From the product's category" then "Product name
   head"; Brand shows "From the product's brand field"; Seat cover material shows "Code ends
   with `-UF` -> UF" then "Text contains `PP SEAT` -> PP". All removable.

Decisions per rule: which sentence, its blanks, its position. Try-it and preview cost none.

## Group A - The engine has no hidden phase (S2)

### AC-A.1 [BE] Every hard-wired reader is a shipped rule row
`shipped_rules()` returns, in this order, on these keys (order as MEASURED for AC-A.2 parity,
amended 31 Aug after S2; the pre-code draft had class/brand the other way round):
- `dim_length` / `dim_width` / `dim_height`: `from_field column:dimensions_*`, then
  `size_triple` capture 1/2/3 (applies unless `shape` is round/square), then for
  `dim_length` only the lone-size PATTERN row (`_SINGLE_DIM_RE`, 2-4 digits before MM, read
  from `size_text` = description with the trap span blanked). It is a pattern row, not the
  `number_before MM` sentence: that sentence compiles to `(\d+(?:\.\d+)?)` and reads
  `CABANA GLASS SHELF 8MM` as an 8 mm long shelf (3 live codes).
- `thickness`: `size_triple` capture 4 unless round/square; capture 3 when it is.
- `diameter`: `size_triple` capture 1 when `shape` in round/square; `depth` (not
  `dim_height`) gets `size_triple` capture 2 under the same condition, because that is what
  the engine did.
- `class`: the shipped `ends_with` noun rows, then `name_head` (an engine kind: class text +
  the noun table, which no single regex expresses), then `from_field category` LAST. A
  category row on top would re-class 20,697 of 23,063 live products.
- `brand`: `from_field brand` as the only row, last (a text rule used to overwrite the field).
Each row carries `builder` where a sentence exists and the compiled `pattern` where it is
text-based. A test enumerates the list and pins it. The code-rule phase is gone: list order
is the only order, and migration 450 moves stored code rows below their key's text rows
(behaviour-identical under the old engine; downgrade does not undo the move).

### AC-A.2 [BE] Golden parity
`derive_all` over the derivation test fixtures and over a 2,000-product sample of the
dev DB (codes listed in the test) yields identical `values` and `provenance` before and
after the change, except: trap-only descriptions (already fixed in #424) and nothing else.
Any difference fails the test with the code and key named.

### AC-A.3 [BE] Removing a shipped row removes the reader
Given `dim_length` rules stored WITHOUT the `number_before MM` row,
When `MARBLE TOP BASIN (800MM)` is derived,
Then `dim_length` is not set. Same for `from_field category` on `class` (class comes from
the name head only) and `from_field brand` on `brand` (no brand).

### AC-A.4 [BE] Order is priority across all kinds
Given `dim_length` rules reordered so `number_after L` is first and the column row last,
When a product has column 700 and description `L 300 x ...`,
Then the value is 300 from the text row, and the existing `column_conflict` exception is
raised naming 700 (a winning text row that disagrees with a `from_field column` row below
it still flags, so curated data is never silently outranked).

### AC-A.5 [BE] The plausibility cap is a per-key field
`product_spec_registry.max_value NUMERIC NULL`; migration seeds 5000 on mm keys. A
number above it is dropped and flagged `implausible_dimension` as today; blank = no cap;
editable through the PATCH. Test: 440180 dropped at 5000, kept at blank.

### AC-A.6 [MIG] Owned keys keep their readers
For every registry row whose `derivation_rules` is non-empty on an affected key, the
migration PREPENDS the new shipped rows for that key (so the reader that used to run
silently now runs visibly, in the same place). Rows with empty `derivation_rules` are
untouched (they inherit shipped rules at read time, as today). Downgrade removes only rows
it added (tagged `shipped_backfill: true`).

### AC-A.7 [BE] `builder` round-trips
PATCH with a rule carrying `builder` and no `pattern` compiles the pattern server-side;
PATCH with `pattern` and no `builder` stores it as a pattern row; PATCH with both where
they disagree is 422 `spec_rule_builder_mismatch`. GET returns both.

### AC-A.8 [BE] Sentence kinds compile as specified
Table test, one line per kind (plan section "Sentence kinds"): the compiled pattern and
the value it reads from a fixture description. Includes: number after word, number before
word, number between A and B, text contains, text ends with, word present -> yes, code
contains / starts with / ends with, from field, size triple take Nth, name head.

## Group B - Try it and preview (S3)

### AC-B.1 [BE] Try endpoint
`POST /master-data/spec-registry/{spec_key}/try` body `{ productId | text, rules }`
(the DRAFT rules, unsaved) returns `[{ index, value, evidence }]` for every row plus
`winner_index`, computed with the same engine code path derivation uses, against that
product's description, code and fields (or the pasted text, no fields). 404 unknown
product or key; a malformed rule is refused by the same validator PATCH uses (400
`spec_registry_bad_rule` naming the row, 422 `spec_rule_builder_mismatch` for a sentence that
disagrees with its pattern; amended 31 Aug to the shared validator's codes). `index` and
`winner_index` are 0-based, matching the S1 frontend type. Requires
`master_data.spec_registry.view`.

### AC-B.2 [BE] Preview endpoint
`POST /master-data/spec-registry/{spec_key}/preview` body `{ rules }` enqueues a worker
job that derives the key for every active product with the draft rules and returns
`{ jobId }`; `GET .../preview/{jobId}` returns `{ status: "pending" }`, `{ status: "done", changed, added,
removed, unchanged, sample: [{ code, before, after }] (20) }` or `{ status: "failed", error }`. Hand-set values are never counted as
changed (they are not derived). Requires `master_data.spec_registry.edit`. Runs the way `reread-catalogue` does: an in-process background thread with a polled
in-memory job record (measured 31 Aug; it was never an RQ job), all-companies scope.

### AC-B.3 [FE] Try-it panel
Product search = `SearchableSelect` in `fetchOptions` mode over the products select
endpoint (whole master, R5 of flyer-code-adopt). Picking a product shows its description;
each rule row shows its read ("300 from `S-TRAP 300MM`" / "nothing"); the winner row is
marked; edits to any row re-run try-it (debounced) without saving. A paste box is the
alternative source. Loading, no product, error states render.

### AC-B.4 [FE] Preview panel
"Preview on catalogue" button; while pending shows a spinner with no countdown; result
shows the four counts and the sample table (code, before, after) with `truncate` + `title`;
Save stays enabled throughout (preview is advice, not a gate).

### AC-B.5 [E2E]
Sidebar from `/`: open Length; try it on `SRTWC8354-SH-P` (every row reads nothing) and
on a basin (row 3 wins with 800); add "Number between `S-TRAP` and `MM`", see 300 on the
WC; remove it; Preview shows counts; Save; re-open shows the same list. 375px and 1280px.

## Group C - Sentences in the editor (S1, Phase 1 first)

### AC-C.1 [FE] Rows read as sentences
Each rule renders as its `builder` sentence with inline inputs for the blanks; the kind
menu lists the sentence kinds by their prose; a row without `builder` renders as
"Pattern `...`, capture the Nth number" and is the only place raw regex appears.

### AC-C.2 [FE] Advanced
Every row has "Advanced": expands to the compiled pattern read-only; "Edit pattern" turns
the row into a pattern row (builder dropped) after a confirm-free inline switch.

### AC-C.3 [FE] Shipped rows are ordinary rows
Shipped rows show a small `shipped` tag; drag, remove and edit work on them exactly as
on user rows; removing one and saving stores the list without it (AC-A.3).

### AC-C.4 [FE] No explanatory prose in the UI
The two sentences about "rules ship with the product" and "the size in the description
always wins" are removed; the list itself is the explanation. Guides carry the rest.

### AC-C.5 [FE] `max_value` field on numeric keys
"Ignore values above" input beside the unit; blank allowed.

## Out of scope
- New sentence kinds beyond the list (Advanced covers them until a second ask).
- Multi-language sentences.
- Bulk re-derive of prod after this lands is an operations step, not a slice.
