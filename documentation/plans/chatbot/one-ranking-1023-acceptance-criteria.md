# UAC: one ranking function (owner direction 23 Oct)

Plan: `PLAN-one-ranking-1023.md`. Per round; owner answers Q1-Q3 fill the bracketed parts.

- AC-OR0 (as built, crew 23 Oct). After a ranking, the parser's broaden_axis product or channel with broaden_to 'all'
  drops that held axis and keeps the rest (same-axis refine, across all, a refine naming another axis); broaden_to
  'family' or another axis changes nothing. The live parser emitting broaden_axis 'channel' for "all channels" is a prompt
  item (R5: R-P3-09 lists date, an entity hint or 'all', not channel). Out: date widening (the route requires a period);
  the bare count (R5 prompt line, gold incl. "Top 100 selling item this year by product, delivered qty").
- AC-OR1 (owner Q1 (a), 23 Oct ~09:20). "Top 30 selling item this year" and "top 10 selling items this year by qty
  delivered" run crm_report_ask with group_by product ("which category sells most": category); never the catalogue line
  "I can rank sales by ..." and never a grain / "rank by product or ..." question. What is missing (period, measure,
  basis, count) is asked in ONE reply; the answer ("Delivered qty") runs with everything typed earlier (top 30, items,
  this year). A top_selling verdict reaching the old lane dispatch (a live session) is sent the same way.
- AC-OR2. After an item ranking: "by amount", "ordered", "top 20", "2025", "sorento only" refine it; "by customer" runs
  across all with what is on screen held (header "Across all products").
- AC-OR3. Reply: long lists split for WhatsApp, the "no sale is not ranked" line, the contact's language, category codes;
  the agent fill-rate note; [Q2] row pick / outstanding.
- AC-OR3d. For an ms / zh contact a sales ranking reply (any group_by) prints its head line, its miss line ("No
  <basis> found"), its Period range and the route's refusal lines in the contact's language; rank lines, names, codes and
  every figure are unchanged, an English contact's reply is byte-identical, WhatsApp part markers and the part count
  survive, and the ONE ranking question (period / measure / basis / count) is in the contact's language end to end.
- AC-OR5 (EXPLORE-1023C, owner rulings 24 Oct 08:10). (A) "Top sales for CB6635 in 2026" (no "by ...") asks only what is
  missing for a TOTAL and runs the total; never an axis question or a default axis. (B) After an agent or customer ranking, a
  rank number opens that row's detail for what is on screen (period, product, basis, measure held): an agent's customers, a
  customer's products, each plus by month; the reply under such a ranking offers it ("Reply with a rank number ...", the
  contact's language). A new grouping typed while a question is open ("by customer" under "How many?") changes the grouping
  of the ask being completed, keeps every filter typed, and asks only what is still missing; never "I don't know ... as a
  number".
- AC-OR4. No chatbot path reaches crm_top_selling_report; the route, MCP tool and analytics connector still work.
- AC-OR-ACCESS (owner Q3 + ruling (a), 23 Oct ~09:35: the unification widens nothing). Every ranking (items and categories
  included) needs the contact's Sales report switch (sales_orders.sales_report), except ruling 2 of 22 Oct: a live
  salesperson's "my ..." ask (the parser's self_reference) keeps own-book rankings of THEIR customers, header
  "Limited to: your customers". An ungranted live salesperson asking "top selling items" (no "my") is refused as today.
  A granted contact that the top selling report refuses today (unlinked and not staff, orders.py:2075-2079) is refused an
  item / category ranking the same way. Dealers keep their own-customer scope.
