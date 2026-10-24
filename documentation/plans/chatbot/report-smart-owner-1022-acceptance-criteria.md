# UAC: owner console turns 22 Oct (REPORT-SMART-L round S2)

Plan: `PLAN-report-smart-owner-1022.md`.

- AC-D1. A sales ranking whose product word fanned out to codes with no shared prefix runs over all of them
  (`product_ids`) or asks which product; it never names one unrelated code in the header or the answer.
- AC-E1. After a ranking ran, "for product <code>" re-runs the held ranking for that product, held period, axis,
  count and choices kept; never product cards.
- AC-A1. "Project sales top 10 <code>" runs with Channel: Project; never "I don't know 'Project' as a sales agent".
- AC-A0. The parser's user turn carries a Sales channels line (dealer, project) in Block and Index mode.
- AC-A2. "Project is channel" under a held ranking re-runs it with Channel: Project; never a customer / warehouse pick.
- AC-A3. An entity whose hint is not an entity kind never reaches the resolver or a kind pick.
- AC-B1. A pick that binds no row never turns a later fully parsed sales ranking into a customer pick (the no-row pick itself is still held: kind-pick contract).
- AC-B2. A fully parsed sales ranking is never turned into a customer pick by a carried customer.
- AC-C1. A changed axis alone never scopes a fresh ask to an old ranking; only the parser's `ranking_drill` drills.
- AC-Y1 (prompt, v96). "Top 5 salesppl in 2026 for <code>" reads 2026 as the period, never a product.
- AC-F1. "<brand> a3 flyer" looks up that brand's A3 flyer promotions (kind and brand sent), whatever products the
  State holds; with none live, the reply says there is no current one.
- AC-F2 (data + prompt lines). With the brand_alias row, the Known brands line shows "SORENTO (SRT)" in both modes and "srt" resolves to the Sorento brand.
- AC-R. The owner's 13 turns replayed on v96 + this head (Index mode; the 3 flyer turns also in Block mode): before / after table; no turn worse than before.

## Round S3 (23 Oct)

- AC-S3-1. "top salesppl in 2026 for <code>" asks only what is missing (how many, measure, basis); the reply
  "Top 5, by qty, delivered" runs the ranking for 2026 by sales agent; never "Which period?". The parser's State shows
  the ranking question as the Open question with the held period. A reply that is a fresh ask of its own still
  replaces the question.
- AC-S3-2. Under a held ranking, a verdict with `sales_channel` project and an entity 'Project' hinted brand,
  category, customer or sales_agent re-runs with Channel: Project; never "I don't know 'Project' as a ...", never a pick
  list. Near misses: an entity whose raw is not the channel value ('Project Hardware') still resolves; with
  `sales_channel` null the entity is untouched.
- AC-S3-3 (crew 23 Oct). A product entity whose raw equals the year the parser itself set as the period
  (date_filter_start and date_filter_end in that year) is dropped: "Top 5 salesppl in 2026 for <code>" ranks over the
  <code> family only and the header never lists codes that only hold '2026'. The resolver's substring tier is untouched:
  a partial code ('WC7601') still answers its family. A year typed with NO period set stays as-is; the same entity
  with a period in another year stays as-is.
- AC-S3-P. Prompt v98 measured on the crew copy: delivery gold not below v97 (9/11); parser_when_deliver raw `status`
  not below v96 (22/24); channel class rs92-c-* not below v96 (x2); the 13 owner turns: 2, 7, 8, 9 better, none worse
  than the v96 replay.
- AC-S3-4. A WHEN ask parsed with `order_status` outstanding and `status` null keeps outstanding in the State, so the
  follow-up "and <another code>?" re-runs the outstanding ask for that code; with `document` [DO] it reaches the DO
  outstanding path exactly as `status` outstanding + [DO] does (never "SO, DO or both?" for a contact with the SO
  grant). Near misses: `status` outstanding with `order_status` null, `status` delivered, and both null behave as today.

## Round S4 (23 Oct)

- AC-S4-1. With the ranking question open (basis owed) after "top 5 salesman this year vs last year", the reply
  "compare with last year" (parser: compare_to last_year, no owed field filled) keeps the comparison and asks only the
  owed fields again; never "I don't know 'compare with last year' as a basis". The parser's Open question shows the
  held comparison. Near miss: a reply that fills the basis ("delivered") runs the ranking with the comparison.
- AC-S4-2. The access level question for a flyer ask names the kind the parser set ("a3 flyer") with the brand, whether
  or not a flyer entity survived grounding. Near miss: an ask with no promotion_kind is worded as today.

## Round S5 (23 Oct)

- AC-S5-1. After a console Reset (a new test run id, empty session vars), the parser's user block carries no Recent
  exchanges, no Previous response and no Recent conversations line from before the Reset; turns of the current run still
  appear. A real (non-console) contact's history is unchanged.
- AC-S5-2. A sales ranking that returned ranked rows is remembered as answered: its Recent conversations line never says
  "nothing was found"; a ranking that returned no rows still does.

## Round S6 (23 Oct, owner ruling: after a ranking = (B))

- AC-S6-1. With a ranking on screen ("Top 5 of N sales agents by delivered sales", product, channel, period), a message
  that ranks a new axis with `ranking_drill` null, unsure or global ("by customer", "Project customer") runs that ranking
  across all, and its header carries "Across all sales agents" (the noun of the ranking that was on screen); never the
  question "... of the 5 sales agents above, or across all ...?".
- AC-S6-2. `ranking_drill` scoped ("their customers", "of these agents", "only those 5") narrows to the rows on screen,
  as today; no "Across all" line.
- AC-S6-3. Near misses: a refine of the ranking on screen (same axis, "Dealer sales only") and a fresh ask with no
  ranking shown carry no "Across all" line and behave as today; a scope question already held in a session is still
  answered as today.
- AC-S6-4 (owner ruling ~08:25). On screen "Top 5 sales agents by delivered sales, Product SRTWC286-SH, Channel:
  Dealer, 2026"; "by customer" (new axis, ranking_drill null / unsure / global) runs top customers for SRTWC286-SH,
  dealer, 2026 with no question asked, header "Across all sales agents". A product, channel or period the message
  names itself replaces the held one. The final run of an across-all ask that first asked a missing detail still
  carries the header.
- AC-S6-5 (crew on the owner's 'keep what is on screen', 23 Oct ~08:40). The count, measure and basis on screen are held
  too: after "Top 5 sales agents by delivered sales" (qty), "by customer" runs top 5 customers by delivered qty for the
  held product, channel and year, header "Across all sales agents", with no question at all. A count, measure or basis
  the message names itself ("top 10 by customer by amount") replaces the held one.
