# UAC: a sales analysis with a count and one channel, over a held ranking, re-runs that ranking (CHAT-CHANNEL-RANK-ROUTE)

- AC-CR1. After "Top 5 salesppl in 2026 for cb6635, by delivered qty" (and "Dealer sales only"), "Project sales top 10 srt102-rg"
  parsed as sales_analysis + sales_channel project + top_n 10 + product SRT102-RG (no group_by) answers the agent ranking:
  "Top 10 of N sales agents", Channel: Project, product SRT102-RG, the held period, measure and basis. Never a total.
- AC-CR2. With no ranking held (or a stale one), the same parse answers as before this change (the sales analysis).
- AC-CR3. A sales analysis with a channel and no count ("Project sales 2026") answers as before, held ranking or not.
- AC-CR4. A non-channel ranking and its refines ("top 3") answer as before.
- AC-CR5. Live replay of the 3 p4 rows on the prod prompt (md5 0f3b48e6): row 6 t3 gives the project-filtered agent ranking, no
  row worse (crew runs it, cap USD 0.30).
