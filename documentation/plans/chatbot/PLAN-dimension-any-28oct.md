# PLAN: DIMENSION-ANY (a bare measurement matches any dimension)

Status: Plan (small fix track expected; no migration, no auth change)

## Journey (owner, prod v69, 28 Oct)

- "wc with 150mm got stock" answered "water closets with height 150 mm with stock ... none matched".
- "wc with length 150mm got stock" answered "water closets with length 150 mm ... none matched".
- Owner: "when it comes to dimension, it shouldn't restrict to just 1 dimension, it should search all
  dimension; it stuck to height or length already".

## Rules

1. A measurement with no dimension named ("150mm", "150 mm", "15cm") matches ANY dimension-type spec of
   the product, unit-normalised. The reply never invents a dimension name.
2. A named dimension ("length 150mm") matches that dimension first; when nothing matches, fall back to
   any dimension with a clear line ("None with length 150 mm; these have 150 mm in another dimension:
   ...") instead of escalating.

Findings, design and test list follow once the code is read.
