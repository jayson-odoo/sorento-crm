# UAC: one ranking function (owner direction 23 Oct)

Plan: `PLAN-one-ranking-1023.md`. Per round; owner answers Q1-Q3 fill the bracketed parts.

- AC-OR0 (as built, crew 23 Oct). After a ranking, the parser's broaden_axis product or channel with broaden_to 'all'
  drops that held axis and keeps the rest (same-axis refine, across all, a refine naming another axis); broaden_to
  'family' or another axis changes nothing. The live parser emitting broaden_axis 'channel' for "all channels" is a prompt
  item (R5: R-P3-09 lists date, an entity hint or 'all', not channel). Out: date widening (the route requires a period);
  the bare count (R5 prompt line, gold incl. "Top 100 selling item this year by product, delivered qty").
- AC-OR1. "Top 30 selling item this year" and "top 10 selling items this year by qty delivered" run crm_report_ask with
  group_by product (category for "which category sells most"); never the catalogue line "I can rank sales by ..." and
  never a grain / "rank by product or ..." question; what is missing is asked in one reply [Q1]; the answer ("Delivered
  qty") runs with everything typed earlier (top 30, items, this year).
- AC-OR2. After an item ranking: "by amount", "ordered", "top 20", "2025", "sorento only" refine it; "by customer" runs
  across all with what is on screen held (header "Across all products").
- AC-OR3. Reply: long lists split for WhatsApp, the "no sale is not ranked" line, the contact's language, category codes;
  the agent fill-rate note; [Q2] row pick / outstanding.
- AC-OR4. No chatbot path reaches crm_top_selling_report; the route, MCP tool and analytics connector still work.
- AC-OR-ACCESS. [Q3] who may rank items; an unlinked non-staff contact never sees every customer.
