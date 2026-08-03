# S3-pre: extraction accuracy, measured

**Status: RUN 2026-08-03. Verdict: proceed with S3**, with three changes to the documented
contract (below). The spike harness was throwaway and is not merged, per the plan.

**What it answers.** S3's whole journey assumes a consumer uploads a dealer's receipt and
Customer Service then reads a clean pre-filled template. The plan set a bar: *"if shop-name
match lands under ~75%, CS ends up fixing bad guesses instead of reading a clean template,
and the feature inverts - it becomes more work than the WhatsApp group it replaced."*

**Method.** 218 images from the WhatsApp corpus (781 candidates, seeded shuffle so the
sample is reproducible), one `gpt-4o` vision call per image doing classify-and-extract
together, downscaled to a 1400px long edge. 50 purchase documents found. Shop names matched
against `customers` by trigram similarity across `customer_name`, `trading_name` and
`registered_name`, after normalisation. Detail per receipt in the run's JSON.

## The numbers

Of 50 purchase documents, **12 were issued by Sorento itself** - those are AC-C13's dealer
track, where the dealer resolves from a quoted order number and no fuzzy name match should
be attempted. Scoring them as consumer-track receipts would move the headline for the wrong
reason. That leaves **38 consumer-track receipts**, and every number below is out of 38.

| what | result |
|---|---|
| shop name printed and read | **33/38 (87%)** |
| dealer resolved, exact after normalisation | **26/38 (68%)** |
| dealer ambiguous (0.40 to 0.69) - needs CS | 3/38 (8%) |
| dealer unmatched (< 0.40) | 4/38 (11%) |
| no shop name on the document at all | 5/38 (13%) |
| **purchase date extracted** | **37/38 (97%)** |
| **model code extracted** | **37/38 (97%)** |
| illegible | 0/38 (0%) |
| quoted Sorento order number present | 9/38 (24%) |

Dates spread across 2020 to 2026, so the 97% is not an artifact of one recent batch.

## Why 68% is a pass and the 75% bar was aimed at the wrong risk

The bar was set on **volume of misses**. Misses turn out to be cheap: AC-C14 already
guarantees a low-confidence match submits anyway and flags for CS, AC-C10a renders every
extracted value as an editable input, and AC-C10c re-runs the dealer match when the consumer
corrects the shop name. A miss costs one edit.

The expensive failure is the opposite one, and the spike found it: **a confident wrong
match**. Three of the 38 sit in the 0.40 to 0.69 band naming a real but wrong dealer:

```
0.47   printed "SENG HUAT SDN BHD"                -> "CHENG HUAT HARDWARE (SENTUL) SDN BHD"
0.41   printed "LEHAO FURNITURE & INTERIOR DESIGN" -> "LEGIT INTERIOR DESIGN"
0.30   printed "IRC HOME DECOR SDN BHD"            -> "DE HARMONI HOME DECO SDN BHD"
```

Each of those, shown to CS as a resolved dealer, is worse than a blank field: it attributes a
consumer's purchase to a dealer who never sold it, and it is the sell-through ledger that S3
exists to build. **68% resolved with almost no wrong answers beats 76% with three.**

The distribution is what makes this workable. It is **bimodal**: 26 receipts match at exactly
1.00 and nothing at all lands between 0.70 and 0.99. There is no gradient to tune a threshold
against - a match is either the dealer or it is noise.

## Two findings about the matcher itself

**1. Trigram similarity over Malaysian legal names measures how Malaysian a company is.**
On the tenth image a Sorento delivery order printed "SORENTO SDN BHD" and matched **"SL & A
SDN BHD" at 0.42** - over any sane threshold, entirely on the shared "SDN BHD". Stripping
corporate noise from both sides (`SDN BHD`, `BERHAD`, `ENTERPRISE`, `TRADING`, `HARDWARE`,
`MARKETING`, ...) collapsed that to 0.17. **S3's resolver must strip before comparing** or it
will confidently name the wrong dealer on a regular basis.

**2. Receipts print the branch; `customers` stores the company.** "(JLN IPOH BRANCH)",
"(PUCHONG)", "[A/C III]", "(SENTUL)". Stripping bracketed qualifiers and the word BRANCH from
both sides moved three receipts and lifted exact resolution from 23 to 26 of 38:

```
0.33 -> 1.00   DiLOOMA SDN. BHD. (JLN IPOH BRANCH)   -> DILOOMA SDN BHD
0.73 -> 1.00   KBO LOGISTICS & SUPPLY SDN BHD [...]  -> KBO LOGISTICS & SUPPLY SDN BHD (...)
0.77 -> 1.00   THE LIVING DEPOT (PUCHONG) SDN BHD    -> THE LIVING DEPOT (PUCHONG) SDN BHD
```

One row moved the other way and that is the correct outcome: `SAINMART SDN BHD [A/C III]` -
an OCR misread of SANIMART - fell from 0.62 to 0.38, out of the auto-accept band and into
"ask CS". It is a one-character typo, not a name variant, and trigram similarity should not
be the thing that rescues it. **A short-edit-distance fallback is the obvious next lever and
was deliberately not built here** - it belongs in S3 with a test, not in a spike.

## Three changes to S3's documented contract

1. **The extract response returns a dealer match STATE, not a bare confidence float.**
   `resolved | candidate | unmatched`, decided server-side from the measured bands, because a
   float invites the frontend to invent its own threshold and the whole point of the bimodal
   distribution is that only 1.00 may auto-fill. `candidate` never pre-fills the dealer; it
   offers CS a suggestion to accept.
2. **Normalisation is part of the contract, not an implementation detail.** Strip corporate
   suffixes and bracketed branch qualifiers from both sides. Reuse
   `PLAN-suggest-on-miss-variant-graph.md` rather than writing a third normaliser.
3. **The dealer track is 24% of real traffic, not an edge case.** 12 of 50 documents in the
   corpus were Sorento-issued and 9 of 38 consumer-track receipts still quoted a Sorento
   order number. AC-C13's order-number path earns first-class treatment in the Phase 1
   prototype, not a footnote.

## What still has to be watched, and now can be

AC-C10b stores the AI's original extraction beside the human correction, which makes
**production its own measurement harness**: correction rate per field is extraction accuracy,
continuously. This spike is the baseline that number is read against - 87% shop name, 97%
date, 97% model code, 68% auto-resolved dealer. If the live correction rate on the dealer
field runs materially worse than 32%, something regressed in a way this sample did not show.

## Also verified while here, so nobody re-trusts a July claim

- **AC-C12 and AC-C13 still hold against the live database.** All six dealer document numbers
  (`KCS-2112-0054`, `CS002629`, `NV20-2-008850`, `IV01029`, `DO10-2-123494`, `CS40964`) match
  **nothing** in `orders`; the quoted Sorento number `202604-0348` matches exactly one row.
  The two-OCR-strategy premise is intact.
- **AC-C11's tiled picture chooser has no pictures.** `warranty_product_kinds` has 31 rows,
  31 with `consumer_label` and **0 with `consumer_icon`**. Either 31 icons get sourced before
  the S3 prototype draws that screen, or the tiles fall back to text - which weakens "a
  consumer picks by picture, never by code" into something else. **Sorento's call, flagged
  rather than guessed.**
