# UAC: a channel word after a held ranking filters it (REPORT-CHANNEL-FILTER, owner ruling 24 Oct ~19:50)

- AC-CF1. After a sales ranking on screen ("Top 5 salesppl in 2026 for cb6635, by delivered qty"), "Dealer sales only" (parsed group_by
  channel + sales_channel dealer) answers the SAME ranking filtered to dealer: "Top 5 of N sales agents", Channel: Dealer, the same
  product, period, measure and basis. Never "Top 1 channel", never "Across all sales agents".
- AC-CF2. "Project sales top 10 srt102-rg" after that ranking (group_by channel + sales_channel project, its own product and count)
  keeps the agent axis with Channel: Project; the message's own product and count win.
- AC-CF3. "sales by channel" (group_by channel, no sales_channel) after a ranking stays a channel ranking (owner ruling B unchanged).
- AC-CF4. With no ranking held (or a stale one), the same parse behaves as before this change.
- AC-CF5. On the production prompt v63 (Block, composer off, gpt-5.4-mini), rows 14-17 of EXPLORE-1023C give row 15 the dealer-filtered
  agent ranking and no row worse than before (EVAL-BENCH check, cap USD 0.10).
