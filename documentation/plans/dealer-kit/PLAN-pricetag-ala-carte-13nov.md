# PLAN: price tag request line, ala carte package choice (PRICETAG-ALA-CARTE)

Status: Plan (behaviour card posted, waiting on owner answers). Track: M + one small migration.

## Ask (owner, 13 Nov)
A product with a combo can also be requested ala carte on a price tag request line.

## Goal
1. Package choice shows for every line whose product has 1+ combos, with "Ala carte (product only)"
   beside each combo. Default unchanged (single combo still auto-picked). Ala carte clears combo + parts;
   tag renders as the product's own ala carte tag.
2. Same product may sit on 2+ lines when the package differs. Same product + same package stays refused
   (form, backend 422, DB unique over request + product + package, no combo = one value).
3. Every create/show path (upload, multi-add, copy, approve/edit, PDF/export, history) uses the same functions.

Details, UAC and test list follow once the behaviour card is answered.
