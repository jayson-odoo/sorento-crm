# UAC: parser prompt v107 (PROMPT-V107)

Plan: `PLAN-prompt-v107-gate-25oct.md`.

- AC-1: "Top 10 dealer selling SRTWC286-SH this year by amount delivered" parses as sales_ranking,
  `group_by` customer, `sales_channel` null, SRTWC286-SH the product, `top_n` 10. Same for
  "which dealer sold the most <code>" (`top_n` 1).
- AC-2: "Project sales top 10 srt102-rg" parses as sales_ranking, `group_by` channel,
  `sales_channel` project, `top_n` 10, srt102-rg the product; after a held sales agent ranking the
  bot answers the agent ranking filtered to the Project channel (#1844), never "No sales found".
- AC-3: "seat cover for srtwc6031-sh-uf" keeps SRTWC6031-SH-UF as a product entity (hint product)
  with the relation in `find` (key fits); the product is never empty.
- AC-4: v107 is no worse than production v63 (md5 0f3b48e6) on the four gate parts of the plan.
- AC-5: v107 is saved only on copy DBs; production is untouched; every result names both md5s.
