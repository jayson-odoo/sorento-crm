# UAC: CHAT-STATE round 8 - CARRY

Plan: `PLAN-chat-state-carry-r8-20oct.md`. All on the state path unless marked; parser verdicts are fixtures built from
the owner run's turn shapes (masked: codes / ids only, no customer data); a harness proves the state path ran.

- **AC-R8-1** (owner T8). Held: 3 rose-gold basins, warehouse token "frg". "send me srt a3 flyer" (switch_domain +
  set brand + contains_flyer): the State holds no products and no warehouse after the turn; held_family does not run;
  no held product reaches reconcile (no "did you mean <held code> (promotion)").
- **AC-R8-2** (owner T9). "send me sorento a3 flyer" (keep + set brand + set tier + switch_domain) over a held set:
  products, warehouse and extra drop; brand and tier are the restated values; the promotion fetch carries no held
  product_ids.
- **AC-R8-3** (owner T10 / T15). A typed product with a switch ("send me picture of <code>", "<code> promo"): the subject
  is exactly that product; no held warehouse / extra / tier rides along.
- **AC-R8-4** (same result). Each of AC-R8-1..3 run with `switch_domain` and with `new_subject` gives the same State
  (products, warehouse, extra, tier, brands, customers).
- **AC-R8-5** (bare switch, guard). Held product X; "got eta?" / "What price?" as [switch_domain] alone: X stays the
  subject (and its warehouse / tier / extra).
- **AC-R8-6** (refine, guard). Held products; "I mean this got chrome colour?" (set:specification + switch): held
  members of the said spec stay (round 6 membership); a set product with no switch keeps the other axes (card R1).
- **AC-R8-7** (tier). A new subject that does not restate the tier holds no tier.
- **AC-R8-8** (state off). Byte-identical (new_ask_drops_* and held_family unchanged off the state path).
- **AC-R8-9**. No regression on the follow-up bars: the $0 recorded-ops replay lists every TRAIN follow-up item whose
  held axes change; none of them flips a passing grade.
