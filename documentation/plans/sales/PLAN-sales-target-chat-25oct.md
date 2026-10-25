# PLAN: sales target achievement and sales opportunities over the chat (SALES-TARGET-CHAT)

Status: **scout done, waiting on the owner (25 Oct 2026).** Behaviour card v1 filed as one `crew report --ask`;
no product code until the owner answers. Size L, full track. Lane branch
`crew/sales-target-chat`, base origin/main b2f15efb32.

## Owner ask (25 Oct ~19:17 MYT, verbatim)

"btw for sales targer right, we need to look into exposing this via rhe chat for dealer and salesperson to
check the sales target achievements and be able to create sales opportunities to hit the target"

## Scope of the scout

1. What exists: the target engine (salesperson targets #1297, sales teams #1260, dealer targets and incentive
   schemes #1715), its achievement service, endpoints and permission rules.
2. The chatbot seams a new read intent and a new write flow would use (parser route, executor, MCP tool,
   renderer, audience gating, confirm step).
3. What the CRM calls a sales opportunity today and how one is created.
4. Real examples from the crew dev DB (sorento_prod_1020, read-only), personal data masked.

## Behaviour card v1 (as filed, carries the measured facts)

```text
SALES-TARGET-CHAT behaviour card v1 (scout, origin/main b2f15efb32; dev DB sorento_prod_1020 read-only, sales orders up to 23 Oct). Plan: documentation/plans/sales/PLAN-sales-target-chat-25oct.md. 5 questions at the end. Size L.

WHAT EXISTS (code, no guessing)
- One target engine for agent / team / dealer (sales.targets, models/sales.py:331). Achievement is live from sales orders, basis "ordered" or "delivered" only (achievement_service.py:174-190, :238); no invoiced-minus-CN basis yet, so dealer figures are labelled "provisional, incl. tax" in the CRM (TargetRecord.tsx:1258).
- Incentive so far IS computed: payout_for (commission_service.py:85) gives commission, bonus, tier reached; points targets with no RM-per-point ratio return ratio_missing (commission_service.py:97-99). Gap to NEXT tier is computed nowhere (target_detail returns tier_reached only, target_service.py:1724-1765) -> new code.
- Salesperson "my target" already exists in the portal: GET /public/portal/sales-opportunities/my-targets (portal_sales_opportunity.py:186) via agent_progress (target_service.py:1978): target, achieved, gap, open pipeline, projected. Agent targets only; no dealer view anywhere.
- Sales opportunity = sales.opportunities (models/sales.py:210), already built: customer or prospect name, owner agent, title, expected amount, expected close date, stages New 10% / Qualified 25% / Negotiation 75% / Won / Lost (sales_seed_service.py:36-43). Created in CRM (POST /sales/opportunities, sales.opportunities.add) or by a salesperson in the portal (portal_sales_opportunity.py:215-246; own customers only, CUSTOMER_NOT_YOURS, opportunity_service.py:154). No approval step: lands in New (opportunity_service.py:316-346). Open opportunities never count toward achievement; they only show as "pipeline" beside an agent target, unweighted (target_service.py:2040-2047). Dealers have no create path today.
- Chat: no target or opportunity tool (grep of sorento_crm_mcp and services/chatbot). Chat is read-only except ideation, which has no confirm step (lanes/ideate.py). The CRM targets API is staff-login only with all-or-nothing sales.targets.view (targets.py:71-79), so chat needs a contact-scoped route like the sales report (orders.py:1930-1978: contact_id + space_id, enforce_customer_scope).

WHO CAN ASK WHAT (from code)
- Asker is decided per contact, first match wins: salesperson user role > staff > sales_agents.contact_id link (salesperson) > respond_contact_customers link (dealer) (contact_asker.py:66-97).
- Dealer: only targets whose counted accounts (sales.target_accounts) are among the contact's linked customers. Any other dealer name -> existing refusal "only your own accounts" (_customer_scope_gate, engine.py:2269).
- Salesperson: targets of the agents linked to the contact (agents_for_contact, portal_agent.py:24). Team and own-dealer targets depend on Q1.

REAL EXAMPLES (dev copy; company names and codes only, people masked)
1. BATH IDEA BATHROOM & KITCHEN MARKETING SDN BHD (SRT, 300-B129 A/C I; 2 dealer contacts linked). Owner Excel Q4 tiers RM 85,000 3% / 115,000 4% / 135,000 5%. Q4 to 23 Oct: A/C I RM 17,414.05 (gap to Tier 1 RM 67,585.95); A/C I+III+IV RM 57,341.99 (gap RM 27,658.01).
2. BKIN ELECTRICAL SDN BHD (SRT, 300-B111 A/C I). Q3 tiers 50,000 3% / 70,000 4% / 90,000 5%. Q3 A/C I RM 47,407.44 = Tier 1 missed by RM 2,592.56; A/C I+III+IV RM 91,830.92 = Tier 3, 5% = RM 4,591.55 provisional. Which accounts count decides the answer; the reply must name them.
3. A CRAFT IDEA SDN BHD (SRT, 300-A077 A/C I). Q4 Tier 1 RM 60,000 5%; Q4 to date RM 866.40, gap RM 59,133.60.
4. BKIN ELECTRICAL SDN BHD (Mocha, 300-B073 A/C I). Quarterly target 25,000 POINTS, 4%. Q3 RM 22,140.48. sales.point_ratios has 0 rows in the dev copy -> cannot be compared yet.
5. Salesperson agent "Y** I" (SRT, contact linked; owns the 3 SRT dealers above among 50 active customers). Q3 orders RM 548,430.24, Q4 to date RM 93,218.86. No real agent target: the dev copy holds only 4 "Test" targets of RM 0.00 (30 Sep) and 1 test opportunity. #1715 merged 21 Oct, after this 20 Oct copy, so whether the dealer Excel is loaded on prod is UNVERIFIED.

QUESTIONS AND ANSWER SHAPES (one fact per line; en/ms/zh by the existing word lists, language.py:25-53)
A. Dealer (Bath Idea): "how is my target this quarter?"
   Sales target Q4 2026 (1 Oct to 31 Dec)
   Counts: A/C I
   Achieved: RM 17,414.05 (provisional, incl. tax, to 23 Oct)
   Next tier: Tier 1, 3% at RM 85,000.00, RM 67,585.95 to go
B. Dealer (BKIN): "did we hit Q3?" -> Q3 2026 / Achieved: RM 47,407.44 (provisional, incl. tax) / Tier 1 (3%) at RM 50,000.00: not reached, short RM 2,592.56
C. Dealer: "how much rebate so far?" -> per Q2.
D. Dealer: "what is 4 Smart Plus's target?" -> "I can only share figures for your own accounts."
E. Dealer (Mocha BKIN): "my points target?" -> Q3 2026 / Target: 25,000 points / Achieved: RM 22,140.48 (provisional, incl. tax) / "Points are not converted yet, so I can't compare."
F. Salesperson Y** I: "my target?" -> "No sales target is set for you for Q4 2026." With a target: Target / Achieved / To go / Open opportunities closing by period end: RM x (agent_progress fields).
G. Salesperson (Q1=c): "my dealers' targets?" -> one line per dealer, smallest gap first: "BATH IDEA ... [A/C I]: RM 17,414.05 of RM 85,000.00 (Tier 1), RM 67,585.95 to go" / "BKIN ELECTRICAL ...: RM 5,275.80 of RM 50,000.00, RM 44,724.20 to go" / "A CRAFT IDEA ...: RM 866.40 of RM 60,000.00, RM 59,133.60 to go"
H. Salesperson: "log opportunity Bath Idea, condo job Taman X, RM 40k, close mid Dec" -> "Save this opportunity? / Customer: BATH IDEA ... [A/C I] / Title: condo job Taman X / Amount: RM 40,000.00 / Close by: 15 Dec 2026 / Reply YES to save" -> YES -> "Saved OPP-000002, stage New. Open opportunities closing by 31 Dec: RM 40,000.00."

CREATE AN OPPORTUNITY IN CHAT (slice 2)
- Record: sales.opportunities, as the portal creates it. Chat asks one missing field at a time: customer (own customers, numbered pick when A/C I/III/IV match, or a prospect name), title, expected amount (required in chat; the API falls back to the lines' sum, RM 0 with no lines, opportunity_service.py:349-351, and a RM 0 opportunity adds nothing beside the target), expected close date. Products optional, not asked.
- Confirm per Q5. Owner agent: the agent owning the customer, else the contact's first agent (portal rule, portal_sales_opportunity.py:224-229). Source: new value "chat" (one check-constraint migration; created_by_contact_id already exists).
- Who sees it: CRM Sales > Opportunities (sales.opportunities.view) and the salesperson's portal list. Approval: none (as today). Counts toward target: no; only shown as open pipeline beside an agent target until it becomes a sales order.

EDGE CASES (crew defaults unless you object)
- Quarterly and yearly schemes both active: both listed (ruling 4). Replaced target: only the live one. Additional x% lines: the next-tier line names the stacked rate ("6% + additional 1%").
- Dealer linked to SRT and MCH accounts: each company's targets under its company name. Contact that is both salesperson and dealer: answered as salesperson (contact_asker.py order).
- Default period = current period of every active target; "last quarter" / a month name picks that period. As-of date = latest sales order date.
- Chat stays read-only toward targets: nobody sets or edits a target in chat.

QUESTIONS
Q1 Salesperson scope. (a) own targets only (= portal today); (b) (a) + their team's target; (c) (b) + targets of dealers they own (customers.sales_agent_id -> target_accounts, one new query). Rec (c): "create opportunities to hit the target" is mostly about pushing dealers, and example G is the list they would act on.
Q2 Dealer incentive money. (a) tier reached + rate + RM incentive so far, labelled provisional; (b) tier reached + rate + gap only, no RM amount until the invoiced basis lands; (c) achievement + gap only, no tiers or rates. Rec (b): the SO figure includes tax while the payout is on invoiced sales excl. tax (ruling 1), so a provisional RM rebate (BKIN Q3: RM 4,591.55) would read as a promise higher than what is paid.
Q3 Who creates opportunities in chat. (a) salespeople only (same gate as the portal, NOT_A_SALES_AGENT portal_sales_opportunity.py:81); (b) salespeople + dealers (dealer: own accounts only, stamped to that account's salesperson, who is told). Rec (a) first: no approval step exists, so a dealer-logged opportunity needs an owner rule and a notification, which (b) adds as its own slice. Your words named both, so say (b) if dealers must have it in this lane.
Q4 Rollout gate. (a) per-contact grant "Sales target" in contact access, default off, same as "Sales report" (contact_field_reveal_service.py:72); (b) on for every salesperson and dealer contact. Rec (a): you choose who sees money figures, and it ships dark.
Q5 Confirm before saving. (a) bot sums up the fields, "Reply YES to save"; (b) save at once, reply with the OPP number, fix in portal/CRM. Rec (a): amount and date come from free text, and a wrong RM or date silently skews the pipeline shown beside the target.

SIZE AND SLICES: L (contact-scoped route + MCP tool + presenter; new intents on the frozen `sales` policy row need a migration (policy_rows.py:333-339); parser prompt version + parser gate (LLM spend at build, ledger rules; you move the prod label); first confirmed chat write; source migration; security-reviewer for contact scoping).
- Slice 1 read-only: "my target" for dealer + salesperson (A-G), gap to next tier, Q2 shape, Q4 gate.
- Slice 2 write: log opportunity (H) per Q3/Q5.
- Not in this lane: the WhatsApp achievement broadcast (plan S5, not built).
```

## Owner rulings

None yet.

## Slices

Proposed in the card; fixed here after the owner answers.
