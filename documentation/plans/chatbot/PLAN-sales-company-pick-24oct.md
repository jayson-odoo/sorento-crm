# PLAN: SALES-COMPANY-PICK - the reply to the bot's company question picks the company; a new ask drops the held channel

**Status:** Build, round 2 (24 Oct 2026): item 3 below (crew blocker found verifying a33d1be011). Round 1 reviewed
(Opus READY, security PASS). Track: urgent fix round (crew, during the d02152a607 deploy), lead pattern: tester red,
coder, Opus reviewer + security-reviewer (multi-company scoping). Branch crew/chat-sales-company off main d02152a607.
**UAC:** `sales-company-pick-acceptance-criteria.md` (alongside). Found by crew running #1841's script on the :3109 copy.

## Defects
1. "<code> <channel> sales <month>" (e.g. "B2155-NL-BLUE dealer sales Sep 2026") reaches crm_sales_analysis, whose route
   asks "Sorento or Mocha?" (`app/api/v1/sales/analysis.py`). The MCP presenter returns that as plain text, so the chat
   stores no question, and a stale "By product / Delivery orders" question stays open. The reply "Sorento" was read
   against it: an escalation (out_of_scope "Routed to your PIC") or a brand filter (A611).
   NOT a regression of main vs prod b3661280a6 (crew-note on #1841 6379645516).
2. After "SRT102-RG dealer sales May 2026", the new full question "SRT102-RG sales 2026" ran with channel dealer.

## Rules
- (1) The reply to the bot's own company question picks the company: the analysis runs for it with the held channel
  and period; never a brand filter, never an escalation.
- (2) A NEW ASK drops every axis it did not itself name (owner hand pass 6, 17 Sep 2026); the channel carry is for
  follow-ups only (PLAN-chatbot-sales-report.md:188-191). A top selling narrowing keeps its ranking and channel
  (apply.py, `_narrows_the_ranking`).

## Architecture
- (1) Existing required-fields ask (as low stock and report asks use it): `lanes/business/sales_company_ask.py`; the
  sales analysis lane asks before fetching when the turn names no company and the contact holds 2+ companies, using
  one helper shared with the route (same companies, order and text). The answer is read from parser fields only
  (declared pick, sales_company, company_pick, or a message entity matching an offered option through the pickers'
  own label matching). A lane that asks a required field clears the stale stored question.
- (2) `turn/apply.py` new-ask branch drops `focus.sales_channel` beside the date window, except a top selling
  narrowing.
- Not in scope: the parser's own prompt for a sales_analysis read of a message that names a product or customer
  (parser_template.py:315, a parser-input item; item 3 makes the code safe whichever way it parses); the top selling
  narrowing losing its date window (pre-existing).

## Round 2: item 3 (crew blocker, 24 Oct, verifying a33d1be011 + #1841 on sorento_prod_1020)
3. "b2155-nl-blue dealer sales september 2026" sometimes parses as order_status sales_analysis WITH the product entity
   (X2 trace, gpt-5.4-mini v63: entities [B2155-NL-BLUE hint product, current_message true, canonical_code null],
   sales_channel dealer, domain_hint sales, scope_intent specific). With round 1 the bot asks "Sorento or Mocha?" and
   "Sorento" then runs the company analysis, which has NO product or customer filter (`app/api/v1/sales/analysis.py:448-460`):
   it answers the whole company's dealer total for September (RM 6.28M) under a product question. Confidently wrong scope.
   The same message parsed as sales_report runs crm_sales_report for the product (X2 other run).
- Rule: the code picks the tool from the parser's params, no keyword rule. A sales_analysis parse whose CURRENT message
  names a product or a customer (entity hint product / customer, current_message true) is a sales report of that subject:
  it runs crm_sales_report exactly as the sales_report parse of the same message does (same args), never the company
  analysis and never the company question. A customer is the same class (the route filters neither).
- Architecture: one predicate over parser fields (named subject this message), read at the two seams that today treat
  every sales_analysis parse alike: the resolve+gate bypass (`lanes/business/__init__.py` ~:948, `sales_analysis_ask`,
  so the subject is resolved like a sales_report ask) and the tool pick (~:2135 analysis branch / ~:2163 sales report
  branch). The tool pick is traced (`_tool_pick.source`). Carried entities (current_message false) never reroute: a new
  "dealer sales this year" after a product report stays the company analysis.
