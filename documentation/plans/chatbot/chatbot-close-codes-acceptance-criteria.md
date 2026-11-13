# UAC: CHATBOT-CLOSE-CODES (dealer gets up to 3 close codes)

Status: FINAL. Crew answered card v1 13 Nov: Q1-Q5 all (a), as recommended; discontinued codes never offered
(owner 13 Nov ~11:13). New gap from crew data added as AC-24..AC-30 (crew calls it G6; the card calls it G0).

"Dealer" = an availability-only contact. "Offer" = "Couldn't find X." followed by "Did you mean Y?" (one code) or a
numbered list of up to 3 codes, stored as a pick that carries the typed quantity. Every AC runs on seeded catalogue
rows in two companies; no real names, phones or prices.

## Letters-only and multi-code (C1; G1, G3)

- AC-1 Dealer, `<exact code> x 2, <letters-only typo of a 2nd code> x 1`: the first is answered; the second gets an
  offer naming the 2nd code, quantity 1 carried. Not dropped.
- AC-2 Dealer, `<letters-only typo> x 1` alone, where the typed token is a lone prefix of one code: an offer of that code
  (not the refer line, not a direct answer).
- AC-3 Dealer, a letters-only token that sits inside one longer code: an offer of that code.
- AC-4 AC-1 with two typos: each gets its own offer list, numbered on (AC-15d shape of #2370); "1 and 2" answers both.
- AC-5 The offer for a code inside a multi-code ask equals the offer the same code gets alone (same function).

## Direct answer only for an equal code or a set (C2; Q1, Q2)

- AC-6 Dealer and staff, a lone prefix of exactly one code (S08 shape): offered, not answered. (Q2 (a); test S08 is
  updated with the owner's answer, not weakened silently.)
- AC-7 A code equal but for case, dashes or spaces: answered directly, byte-identical to main.
- AC-8 A registered set code (same fold): answered as the set, unchanged.

## Miss beside a question (C3; G2, Q3)

- AC-9 Dealer, `<code needing "how many"> stock, <digit typo> stock`: one reply holding the how-many question and
  "Couldn't find X. Did you mean:" numbered on; a number picks the offered code.
- AC-10 Dealer, a family which-one list plus a typo: the which-one options first, the offer numbered on after them.

## Incoming / ETA asks (C4; G4, Q4)

- AC-11 Dealer ETA ask with one wrong letter and one close code: "Couldn't find X. Did you mean Y?" with no refer line;
  "yes" answers Y's incoming.
- AC-12 Same with 2-3 close codes: a numbered list, no refer line; a number answers that code's incoming.
- AC-13 Dealer ETA ask with no close code: today's refer line, unchanged.

## Ranking (C5, C6; G6, Q5)

- AC-14 A token whose all-parts code is the 6th-15th trigram row: that code is offered in the top 3.
- AC-15 Ranking order identical for staff and dealers, single and multi-code.
- AC-16 A short token with more than 3 all-parts matches: today's which-one list (AC-9 of #2370), unchanged.

## Scope and exclusions

- AC-17 A close code that exists only in another company is never offered to a dealer, on every tier: trigram,
  prefix/substring, all-parts, embedding.
- AC-18 Inactive, discontinued or placeholder codes are never offered.
- AC-19 "no" to an offer: the refer line naming the code.
- AC-20 A greeting, a Malay phrasing (`... bila sampai?`) and a typo each pass through the same path.
- AC-21 Embedding tier (G5, only if crew's data confirms it): a digit typo that the embedding tier matched, then
  dropped by the dealer exact-codes rule, gets the trigram offer instead of the refer line.

## Trace (C7; G7)

- AC-22 Each missed code writes one `code_candidates` entry: typed token, offered codes in order, tier, similarity,
  all-parts flag, `offered` or `no_candidate` (never `answered` for a miss). Written for multi-code and letters-only
  misses too.

## Unchanged (guards)

- AC-23 Exact codes, the `ZZZ999` no-candidate refer line, staff escalation offers and the set reply are
  byte-identical to main; the #2370 suites (`test_code_match_dealer_offers.py`, `test_avail_mode_scenarios.py` except
  S08 per Q2, `test_attribute_asks_round7.py`, `test_narrow_code_own_line.py`) stay green.

## No offer at all, and the data shapes (crew data 13 Nov; replayed on current main first)

Codes below are the shapes from crew's masked dev rows (codes are business data); tests seed same-shaped codes.

- AC-24 Dealer `SRTWT6855-GY got stock?` with a same-company code at trigram > 0.4 (e.g. SRTWT6855-GR) and no
  match: an offer, never "Couldn't find X (product). Please refer to your salesman." with no offer. Company-scoped:
  the same close code in another company only gives the refer line.
- AC-25 Dealer `SRT6537-BL X10 / SRT6532-BL X10 / SRT6534 X10` (third code opens a which-one list): every missed
  code is named in the reply, none vanishes. SRT6537-BL gets its offer. No code is shown twice in one reply (AC-15d), so
  a missed code whose close codes the reply already shows (here SRT6532-BL) is named without an offer of its own.
- AC-26 Dealer `MBF97513 X 2 STOCK / MWC7627-S10 X 3 STOCK` (first answered, second missing a part; MWC7627-SH-S10
  exists): "Couldn't find MWC7627-S10. Did you mean MWC7627-SH-S10?", quantity 3 carried.
- AC-27 Dealer `SRTK39SS / SRTKT1631SS / SRTKT38SS / 5 UNITS` (SRTKT39SS exists): the miss gets its offer.
- AC-28 Dealer `Cb86BL and Cb86gm stock` (CB86-BL found, needs "how many"; CB83-GM close): the how-many question and
  the offer for Cb86gm in one reply, numbered on (AC-9).
- AC-29 Dealer `CB2515SS check ETA`: offer of up to 3 close codes, no refer line, a number answers incoming (AC-12).
- AC-30 Guard: `Srtwt1866ss x ss3 / Have stock` still gives today's numbered list of 3.

## Parser-corrected codes (crew ruling 13 Nov, owner rulings 12 Nov 15:10 and 13 Nov ~17:40)

The parser may hand a code it completed or corrected. The typed text is compared with that code, part by part
(parts = split at dashes, spaces and letter/digit changes), with no word list:
- AC-32 A code part the customer typed with a letter changed, added or dropped (`SRTUB668-BACK INLT` -> INLET,
  `SWTWC8354-SH-UF` -> SRTWC) is a correction: OFFERED "Did you mean X?", never answered.
- AC-33 Typed words the parser mapped onto a code part that no typed word nearly spells (`SRTWT8259 gun metal` ->
  SRTWT8259-GM) are the same code: answered directly (owner 13 Nov "they are the same thing").
- AC-34 A code part nothing typed accounts for (raw `SRTWC287-S`, parser SRTWC287-S-150) is a completion: offered (AC-6).
- AC-35 Dashes and spaces only (`srtwc 8354 sh uf`): answered directly.
