# PLAN: DIMENSION-ANY (a bare measurement matches any dimension)

Status: Review (standard track since the crew audit of 482bc55a: one additive migration, `dimany_0001_unit_aliases`; no auth/RBAC change, no new ingest surface)

## Journey (owner, prod v69, 28 Oct)

- "wc with 150mm got stock" answered "water closets with height 150 mm with stock ... none matched".
- "wc with length 150mm got stock" answered "water closets with length 150 mm ... none matched".
- Owner: "when it comes to dimension, it shouldn't restrict to just 1 dimension, it should search all
  dimension; it stuck to height or length already".

## Rules

1. A measurement with no dimension named ("150mm", "150 mm", "15cm") matches ANY dimension-type spec of
   the product, unit-normalised. The reply never invents a dimension name.
2. A named dimension ("length 150mm") matches that dimension first; when nothing matches, fall back to
   any dimension with a clear line ("None with length 150 mm; these have 150 mm in another dimension:")
   instead of escalating.

Owner 28 Oct ~10:10 confirmed: this supersedes the R6-1 BARE-SIZE rulings (crew a21061914 (a),
a22659272): "a bare size matches width OR length, never height" and "a WC's bare 300 is its trap
length only".

## Root cause (main at 61758cc4)

- `chatbot/head/candidates.py` `_resolve` offered the "size N mm (no dimension named)" candidate line
  only when a `matches_bare_size` key (width, length) held the number. No WC held width/length 150, so
  the parser saw "spec dim_height = 150" first and picked height.
- `chatbot/head/bare_size.py` `ground_bare` pinned a bare size to ONE class-scoped key that held the
  number, else the OR over the flagged keys (width/length) only.
- A named dimension nothing held was a plain miss (`product_predicate_service.resolve_product_set`); the
  only widening was a silent swap to a class key sharing a registry phrase (`bare_size.py`, Q3).
- "15cm" produced no size candidate at all: the registry's units are mm only.

## Design

- "Dimension" is data: every numeric registry key whose unit is millimetres
  (`product_spec_search.dimension_keys`), today diameter, length, width, height, depth, thickness,
  trap outlet length, hose length; a key added later in mm joins without code.
- Unit aliases are registry data (crew audit, owner rule 28 Oct: understanding is the parser's, no
  word lists in code): `product_spec_registry.unit_aliases` (`{"cm": 10, "m": 1000, "in": 25.4, ...}`
  on every mm key, migration `dimany_0001_unit_aliases`).
- Candidates: a number beside a registry unit or alias is offered in the key's unit ("15cm" as
  "size 150 mm (no dimension named)"), and the size line always leads for a length. "5 in stock" is
  offered too; the parser decides (prompt + eval), never a code word list. Parser prompt and output
  contract unchanged (prompt md5 pins unaffected).
- Grounding: a bare length is `size` with `any_keys` = every visible dimension key. The number is the
  parser's pick; its `spec_unit`, when it gives one, converts through the aliases. The message text is
  never read. Other units (L, oz, hp) keep R6-1. The Q3 phrase swap is retired (rule 2 covers it).
- Rule 2: `resolve_product_set` reruns a zero set with its one named dimension widened to every
  dimension; a hit carries `dimension_fallback`, and the set header leads with the line.
- The spec filter stays `membership_clause` (shared with REPORT-UNIFY #1922's `spec_set`); unchanged.

## Tests (`tests/chatbot/test_dimension_any.py`, amended `test_closed_lists_bare_size.py`)

WC bare 150 mm hits height and trap; reply has "150 mm" and no dimension word; depth-only product;
15cm read as 150 mm (grounding and candidate line); named length falls back with the line; named length
held stays strict; named length nothing holds stays an honest miss.
