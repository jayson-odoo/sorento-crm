# UAC: owner console turns 22 Oct (REPORT-SMART-L round S2)

Plan: `PLAN-report-smart-owner-1022.md`.

- AC-D1. A sales ranking whose product word fanned out to codes with no shared prefix runs over all of them
  (`product_ids`) or asks which product; it never names one unrelated code in the header or the answer.
- AC-E1. After a ranking ran, "for product <code>" re-runs the held ranking for that product, held period, axis,
  count and choices kept; never product cards.
- AC-A1. "Project sales top 10 <code>" runs with Channel: Project; never "I don't know 'Project' as a sales agent".
- AC-A2. "Project is channel" under a held ranking re-runs it with Channel: Project; never a customer / warehouse pick.
- AC-A3. An entity whose hint is not an entity kind never reaches the resolver or a kind pick.
- AC-B1. A pick that binds no row is never held; the next ask is not narrowed by it.
- AC-B2. A fully parsed sales ranking is never turned into a customer pick by a carried customer.
- AC-C1. A changed axis alone never scopes a fresh ask to an old ranking; only the parser's `ranking_drill` drills.
- AC-Y1 (prompt, v95). "Top 5 salesppl in 2026 for <code>" reads 2026 as the period, never a product.
- AC-F1. "<brand> a3 flyer" looks up that brand's A3 flyer promotions (kind and brand sent), whatever products the
  State holds; with none live, the reply says there is no current one.
- AC-F2 (prompt, v95). "srt a3 flyer" reads `promotion_kind` a3_flyer and srt as the Sorento brand.
- AC-R. The owner's 13 turns replayed on v95 + this head: before / after table; no turn worse than before.
