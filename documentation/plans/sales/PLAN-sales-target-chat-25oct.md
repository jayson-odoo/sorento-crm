# PLAN: sales target achievement and sales opportunities over the chat (SALES-TARGET-CHAT)

Status: **slice 1 built, PR #1861 ready (cff6a82501), ships DARK; waiting on the owner hand test
(laneboard/scripts/1861.md) and the ci label. Reviewer READY, security-reviewer CLEAN. Parser candidate not shipped
(crew decision a30290657, see "Parser gate record"); crew moves the TEST COPY label to B3 for the hand-test window
only (a30577014). Slice 2 (log an opportunity, salespeople only) starts after the slice 1 hand test. Size L, full
track.**

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

## Owner rulings (25 Oct, relayed by crew, verbatim "salesperson see c yes, 2 dealer rebate money ok b, 3 a")

- Q1 (c): a salesperson sees their own target, their team's target and the targets of the dealers they
  own, smallest gap first.
- Q2 (b): tier reached + rate + gap; NO RM rebate / incentive amount until the invoiced basis lands.
- Q3 (a): only salespeople create opportunities in chat (slice 2); dealers later, own slice.
- Q4 (a) crew default: a per-contact "Sales target" grant, default off. Q5 (a) crew default: read back +
  "Reply YES to save" (slice 2). The owner may overrule either.

## Slices

- Slice 1 (this build): read-only target progress in chat, card answers A to G. UAC T1 to T5.
- Slice 2 (after the slice 1 hand test): log an opportunity in chat, salespeople only, card H.
- Not in this lane: the WhatsApp achievement broadcast, dealer-created opportunities, RM incentive.

## Slice 1 design

### Architecture

Layer: the chat read path, unchanged in shape: parser value -> business lane picks the tool in code ->
MCP tool -> contact-scoped backend route -> the existing target engine. Nothing new is decided by the
model beyond one parser value.

Shared mechanisms reused, not copied:
- Target engine: `achievement_service` (achieved by period and account), `commission_service`
  (`threshold_in_rm`, `Tier`, `payout_for`), `target_service` (`_periods`, `_tiers`, `_tier_rates`,
  `_engine_tiers`, `_achieved_by_account`, `point_ratios`, `ratio_on`, `account_label`,
  `agent_progress`). The achieved figure is the engine's own (T2-3); no second achievement query.
- Contact identity: `contact_asker.classify` (contact_asker.py:163; first match wins, :66-97),
  `portal_agent.agents_for_contact` (portal_agent.py:24), `contact_customer_scope`
  (contact_customer_scope.py:86-115), `field_access.resolve_contact_with_null_workspace_fallback`
  (field_access.py:278).
- Per-contact grant: `contact_field_reveal_service.FIELD_REVEAL_KEYS` (:72 pattern); the CRM contact
  access screen renders the registry list (ContactFieldRevealsSection.tsx:29), so no FE change.
- Route gate: `require_permission_with_api_key("sales.reports.view")`, the sibling chat-facing sales
  route's gate (api/v1/sales/analysis.py:67). Measured on the dev copy: the `n8n` integration's
  act-as role holds sales.reports.view and order_management.orders.view; NO integration role holds
  sales.targets.view, so gating on it would need a role grant migration. The sales router's module
  guard already accepts the API key (api/v1/__init__.py:115-120).
- MCP: a `ToolSpec` + presenter exactly like `crm_sales_report` (catalog.py:805-840,
  presenters.py:1950, :2976-3000). English text, like the sales report presenter.
- Parser: one new `order_status` value `sales_target` (the field is a free string, parser.py:261; no
  schema change). Production runs v63 (md5 0f3b48e6, 140,897 chars; production label on the crew dev
  copy sorento_prod_1020 is v63 id 45ea3f69), NOT either repo prompt text (SEMANTIC_PARSER_PROMPT
  md5 1b6ba9ac, parser_template.py md5 ca6e7e47). Crew decision a28595152 (25 Oct): option (a), a
  v63-based ANCHORED INSERT (see "Parser candidate" below), shipped by a migration that inserts it
  UNLABELLED; the owner moves the production label after the hand test. No `chatbot_status_words` row
  and no new `chatbot_domains` row (both render into the live prompt, chatbot_prompt_vars.py:55-66,
  264-271).
- Lane: `turn_runtime` maps `sales_target` to the `sales` domain (turn_runtime.py:1983-1997 seam,
  NOT added to `SALES_FIGURE_STATUSES`, contracts.py:517, whose gates require the sales report
  grant). The domain grant gate (lanes/business/__init__.py:1873-1908) takes the grant of the status
  when the status has one (`sales_target` -> `sales.sales_target`), else the domain's
  (`DOMAIN_GRANT_REQUIRED`, answer.py:1237). The tool override (the :2255-2316 pattern) picks
  `crm_sales_target_progress` for that status. The tool joins `UNDOMAINED_CHATBOT_TOOLS`
  (contracts.py:56-77, "a lane reaches for by name"), so no `chatbot_domains` migration.
- No migration, no new table, no crew SQL.

Classes fixed (not one shape): every asker (dealer, salesperson, staff, unclassified); every subject
(agent, team, dealer); every threshold unit (pct, amount, points with and without a ratio); main,
additional and per-account tier rates; per-period tiers (`tiers_per_period`, TS:1372-1376); single and
multi-company contacts.

### Backend

1. `app/services/sales/target_service.py`, new public functions beside `agent_progress`:
   - `tier_ladder(tiers, tier_starts, period, target, ratios)` -> the period's main rungs sorted by RM
     threshold (CS:131-134 ordering), each with tier number (1-based, as `tier_reached` CS:136),
     RM threshold (`threshold_in_rm`), points threshold for points targets, rates (per account label
     from `account_rates`, else the tier rate) and additional rates attached to the rung with the same
     RM threshold (an additional with no matching rung is its own rung).
   - `period_progress(db, targets, *, date_from, date_to)` -> one line per (target, period overlapping
     the window): achieved (engine), reached rung, next rung + gap, ratio_missing, provisional (dealer),
     accounts (code + label), subject label, period dates. No RM incentive field (T2-6), no ids (T2-11).
2. `app/services/sales/target_chat_scope.py` (new): who sees which target, per UAC T1. Salesperson:
   agents = `agents_for_contact`; own agent targets; team targets via dated membership on `on`
   (`_covering_on` pattern, TS:1245-1255); dealer targets whose EVERY counted account has
   `sales_agent_id` in agents. Dealer: dealer targets whose EVERY counted account is a linked customer.
   Named customers narrow the dealer lines; outside scope -> AppException 403 `customer_not_permitted`.
   Staff / unclassified -> 403 `sales_target_not_available`. Reads targets through the session's
   company scope (the API-key + contact request scope, company_scope_resolver.py:244-252); never
   `list_targets` / `acting_company_id` (raises on a multi-company scope).
   `as_of` = latest `sales_orders.order_date` (not after today) in the companies of the lines.
3. `app/api/v1/sales/target_progress.py` (new), mounted on the sales router:
   `GET /api/v1/sales/target-progress?contact_id&space_id&date_from&date_to&customer_ids`, both ids
   required (422 `contact_identity_required`), grant `sales.sales_target` (403
   `sales_target_not_enabled`), then the scope service. Response: `{asker, as_of, own[], team[],
   dealers[]}`; dealers sorted by gap, none last.
4. `FIELD_REVEAL_KEYS`: `("sales.sales_target", "Sales target")`, default off.

### Contract (route response; the tester and coder both build to this)

`GET /api/v1/sales/target-progress?contact_id=&space_id=&date_from=&date_to=&customer_ids=`
(`customer_ids` repeatable). Errors: 422 `contact_identity_required`; 403 `sales_target_not_enabled`,
`sales_target_not_available`, `customer_not_permitted`; 403 from the permission gate.

```json
{
  "asker": "dealer",
  "as_of": "2026-10-23",
  "window": {"date_from": "2026-10-25", "date_to": "2026-10-25"},
  "own": [],
  "team": [],
  "dealers": [
    {
      "target_no": "TGT-000012", "name": "BATH IDEA 2026", "subject_kind": "dealer",
      "subject_label": "BATH IDEA BATHROOM & KITCHEN MARKETING SDN BHD", "company_code": "SRT",
      "period_start": "2026-10-01", "period_end": "2026-12-31", "is_current": true,
      "metric": "amount", "threshold_unit": "amount", "provisional": true,
      "accounts": [{"code": "300-B129", "label": "A/C I"}],
      "target_value": 85000.0, "target_points": null,
      "achieved_value": 17414.05, "ratio_missing": false,
      "tier_reached": null,
      "next_tier": {"tier": 1, "threshold": 85000.0, "threshold_points": null,
                    "rates": [{"label": "A/C I", "rate": 3.0}], "additional_rates": [],
                    "gap": 67585.95},
      "pipeline_value": null
    }
  ]
}
```

- `asker`: `dealer` or `salesperson`. A dealer's `own` and `team` are always `[]`.
- `window`: the dates the periods were picked by; with no dates given, both are today
  (`team_service._today()`, which tests monkeypatch).
- A rung (`tier_reached`, `next_tier`): `tier` 1-based among main tiers sorted by RM threshold;
  `threshold` RM (units on a quantity target); `threshold_points` only on a points target; `rates`
  one entry per account rate (`label` = `account_label`) or one entry with `label: null` for a tier
  rate; `additional_rates` the additional tiers at the same RM threshold. `next_tier` adds `gap`.
- Points target with no ratio: `ratio_missing: true`, `target_value` null, `target_points` set,
  `tier_reached` and `next_tier` null.
- `pipeline_value`: agent lines only (`agent_progress`), else null. `target_end_date`: agent lines only (the
  whole target's end, the date the pipeline counts to), else null.
- Numbers are JSON numbers rounded to 2 decimals. No UUID anywhere. No RM incentive field.
- Team membership is read on TODAY (`team_service._today()`), whatever window was asked.
- `customer_ids` given: `own` and `team` are `[]`; only dealer lines counting a named customer remain.
- `additional_rates` entries have the same shape as `rates` (`{label, rate}`). An additional tier whose
  RM threshold matches no main rung is left out of the ladder (the importer always gives it the
  threshold of the tier it follows, dealer_target_import.py:188-199).
- `tier_reached` has the rung shape without `gap`.
- `target_points`: the period target in points on every points target (null otherwise);
  `target_value` is its RM at the ratio, null when the ratio is missing.
- `provisional`: true on dealer lines, false on agent and team lines.
- Order: `own` and `team` by period start then target_no; `dealers` by `next_tier.gap` ascending,
  lines with no `next_tier` last, then subject_label.

### Reply text (presenter rules; the card shapes A to G are the examples)

- Money: "RM 85,000.00" (2 decimals, thousands commas); a quantity target prints plain numbers, no "RM".
- Period label: calendar quarter "Q4 2026", month "Oct 2026", year "2026", else "1 Oct to 15 Nov 2026".
- Rate: "3%"; " + additional 1%" per additional rate; " on A/C I" after a rate ONLY when the line counts
  more than one account (card A counts one, so it reads "3%"); several account rates join with ", ".
- Dealer block (dealer asker): header `Sales target <period> (<d Mon> to <d Mon>)`, plus `, <subject>`
  when the reply holds more than one target; `Counts: <labels joined ", ">`; `Achieved: RM x
  (provisional, incl. tax, to <as_of d Mon>)` (the "to <date>" only for a current period);
  then one of: `Tier reached: Tier n, <rate>` (if any) and `Next tier: Tier n, <rate> at RM t, RM g to
  go`; top reached: `Top tier reached: Tier n, <rate>`; closed period below tier 1:
  `Tier 1 (<rate>) at RM t: not reached, short RM g`; a target with no tiers: `Target: RM t, RM g to
  go` (or `Target reached: RM t`); ratio missing: `Target: <n> points` and the line
  `Points are not converted yet, so I can't compare.`
- Salesperson: block 1 `Your sales target <period> (...)` lines as above without "provisional" and with
  `Open opportunities closing by <d Mon>: RM p` when p > 0; none -> `No sales target is set for you
  right now.` (or `... for <window label>.` when a period was asked). Block 2 per team target
  `Team <subject> target <period> (...)` lines as above. Block 3 `Your dealers, smallest gap first:` one
  line per dealer target `<subject> [<labels>]: RM a of RM t (Tier n), RM g to go`; top reached
  `<subject> [<labels>]: RM a, top tier reached (Tier n)`; no ratio `<subject> [<labels>]: RM a, points
  not converted yet`; no tiers `<subject> [<labels>]: RM a of RM t, RM g to go`. Blocks with no lines
  are left out; blocks are separated by one blank line.
- Dealer asker with no lines: `No sales target is set for your accounts right now.` (or `... for
  <window label>.`).
- Route errors arrive as the MCP error envelope (`status_code`, `detail.code`); the lane words them
  (T4-6).

### MCP (`sorento_crm_mcp`)

`crm_sales_target_progress` ToolSpec (read-only GET, contact + space + dates + customer_ids,
`restricted_fields=(("sales.sales_target","Sales target"),)`, escalation_team "sales"), presenter
`_sales_target_envelope` per UAC T3, `PRESENTER_TOOLS`, `_LANE_GATED_KEYS` in
tests/test_field_reveal_keys_declared.py.

### Chatbot

`contracts`: `SALES_TARGET_STATUS`, `UNDOMAINED_CHATBOT_TOOLS`, `BRAND_SCOPE_TREATMENT`
(`no_products`); `mcp_tool_domains.CHATBOT_TOOL_DOMAINS` -> "sales"; fetch.py date table (:464),
`CUSTOMER_SCOPED_TOOLS` (:1566), arg builder (customer ids not carried on `self_reference`, the
:1085-1110 rule), output passthrough; status lists that must know it (order_list.py:33,
resolve_gate.py:91, `run_until_exit` bypass :967-970) as the tests require; refusal lines:
"Sales target is not enabled for your account." and, on the route's 403 `customer_not_permitted`,
"I can only share targets for your own accounts."

### Parser candidate (crew decision a28595152)

- Anchor (must occur exactly once in the base text): the line
  `== SALES REPORT: order_status "sales_report", domain_hint "order" ==` (v63 line 1141).
- Insert: a `== SALES TARGET: order_status "sales_target", domain_hint "order" ==` section placed
  immediately BEFORE the anchor (target words en / ms / zh decide it; "tier" of a target or rebate is
  not an access-level tier; asks with no target word stay sales report / analysis / ranking; a named
  period fills `date_filter_start` / `date_filter_end`; "my" sets `self_reference`; a named dealer is a
  customer entity). The section text lives once, in app code
  (`app/services/chatbot/prompt_inserts.py`: `SALES_TARGET_ANCHOR`, `SALES_TARGET_SECTION`,
  `insert_sales_target(text) -> str | None`, None when the anchor is not there exactly once or the
  section is already present), so crew can re-apply it to whatever text the label moves to.
- `SALES_TARGET_SECTION` is EXACTLY the text below (copy verbatim, it ends with one blank line so the
  anchor keeps its own blank line above it); the gate measures this text:

```text
== SALES TARGET: order_status "sales_target", domain_hint "order" ==
A question about a SALES TARGET - what has been achieved against a target, how far it is
to the target or to the next tier of it, which tier or rebate / incentive rate has been
reached - is order_status "sales_target", domain_hint "order", intent_hint "check_order".
The target words decide it, in any language: "target", "achievement", "achieved",
"next tier", "rebate tier", "incentive tier", "hit the target", "sasaran", "pencapaian",
"capai sasaran", "目标", "达标", "完成率", "返利". It is a DIFFERENT ask from the sales
ranking, sales report and sales analysis asks around it, which carry no target word; an ask
with no target word is never "sales_target". "tier" here is a level of a sales target or
rebate, never an access level.
  - "how is my target this quarter" -> order_status "sales_target", self_reference
    true, date_filter_start / date_filter_end the current quarter's first and last day,
    entities []
  - "did we hit the Q3 target?" -> order_status "sales_target", self_reference true,
    date_filter_start / date_filter_end the first and last day of Q3 of the current year
  - "how far to the next rebate tier" -> order_status "sales_target", entities []
  - "BKIN ELECTRICAL target achievement" -> order_status "sales_target", entities
    [BKIN ELECTRICAL as customer]
  - "my dealers' targets" -> order_status "sales_target", self_reference true,
    entities []
  - "sasaran jualan saya bulan ini" -> order_status "sales_target", self_reference
    true, date_filter_start / date_filter_end the current month
  - "我这个季度的销售目标完成了多少" -> order_status "sales_target", self_reference true,
    date_filter_start / date_filter_end the current quarter
A SALES TARGET ask leaves sales_channel and group_by null and requested_attributes [].

```

- Migration `stc_0001_parser_sales_target`: base = the `chatbot_semantic_parser` version whose
  md5(template) is 0f3b48e6 (the production-labelled one first); none, or anchor not found exactly once
  -> skip + log; result already published -> skip (idempotent); else insert the next version number,
  UNLABELLED. Never replaces a full text. CHAT-SLIM-INDEX-PLAN also builds v63-based variants: a
  crew-note on the PR names this anchor so that lane can check it survives its edits.
- Gate on a private TEMPLATE copy of sorento_eval_base (sorento_stc_eval; eval_base untouched): arm A =
  v63 (pinned by md5 0f3b48e6), arm B = insert applied to it; TRAIN 118 x1 per arm + the 14-row
  sales_target gold x3 per arm; gpt-5.4-mini, dev eval key ..bG4A; cap USD 2.5; stop on any 429 or 2
  busy replies; every run logged in the crew eval spend ledger.

### Parser gate record (25 Oct; ledger crew/state/eval/stc/LEDGER.md, USD 3.97 of a 4.1 cap, dev key ..bG4A)

| Arm | Text | sales_target gold (12 target asks) | near misses | TRAIN 118 x1 |
|---|---|---|---|---|
| A | v63 (0f3b48e6) | 0/12 | reference | 91 |
| B | + section v1 | 36/36 | "my sales this quarter" -> sales_report 3/3 (A: sales_analysis) | 92 |
| B2 | + section v2 (no near-miss example) | 36/36 | "my sales this quarter" -> sales_target 2/3 | not run |
| B3 | + section v3 (contrast line) | 36/36 | all held (= A, or inside A's own unstable answers) | 88 (paired 4/1/113, p=0.375) |

Re-measure of the 12 TRAIN items whose routing moved (x3 per arm, crew rule a30290657): G028 (A 3/3, B3 1/3) and
G125 (A 2/3, B3 1/3) are majority-wrong on B3 while majority-right on A, so B3 does not ship. No arm ever emitted
sales_target on a TRAIN item. Copy DB `sorento_stc_eval` keeps the unlabelled versions 93 / 94 / 95 (B / B2 / B3)
for the next prompt lane; eval_base untouched.

Hand-off to the next prompt lane (e.g. CHAT-SLIM-INDEX-PLAN): the best candidate is section v3 below, inserted
immediately before the anchor `== SALES REPORT: order_status "sales_report", domain_hint "order" ==`; gold rows
`sorento_crm_backend/scripts/chatbot_eval/gold/sales_target.jsonl` (16 rows, plus the 4 extra near misses in
crew/state/eval/stc/cand/gold_nearmiss_new.jsonl). The lane code already acts on `order_status = sales_target`, so
the feature turns on with a published prompt that emits it plus the per-contact grant.

```text
== SALES TARGET: order_status "sales_target", domain_hint "order" ==
A question about a SALES TARGET - what has been achieved against a target, how far it is
to the target or to the next tier of it, which tier or rebate / incentive rate has been
reached - is order_status "sales_target", domain_hint "order", intent_hint "check_order".
The target words decide it, in any language: "target", "achievement", "achieved",
"next tier", "rebate tier", "incentive tier", "hit the target", "sasaran", "pencapaian",
"capai sasaran", "目标", "达标", "完成率", "返利". It is a DIFFERENT ask from the sales
ranking, sales report and sales analysis asks around it, which carry no target word; an ask
with no target word is never "sales_target". "tier" here is a level of a sales target or
rebate, never an access level.
  - "how is my target this quarter" -> order_status "sales_target", self_reference
    true, date_filter_start / date_filter_end the current quarter's first and last day,
    entities []
  - "did we hit the Q3 target?" -> order_status "sales_target", self_reference true,
    date_filter_start / date_filter_end the first and last day of Q3 of the current year
  - "how far to the next rebate tier" -> order_status "sales_target", entities []
  - "BKIN ELECTRICAL target achievement" -> order_status "sales_target", entities
    [BKIN ELECTRICAL as customer]
  - "my dealers' targets" -> order_status "sales_target", self_reference true,
    entities []
  - "sasaran jualan saya bulan ini" -> order_status "sales_target", self_reference
    true, date_filter_start / date_filter_end the current month
  - "我这个季度的销售目标完成了多少" -> order_status "sales_target", self_reference true,
    date_filter_start / date_filter_end the current quarter
  - "my sales this quarter" has no target word -> order_status "sales_analysis", as SALES
    ANALYSIS below says, never "sales_target"
A SALES TARGET ask leaves sales_channel and group_by null and requested_attributes [].

```

### Parser gate (T5, superseded by the record above)

Gold file `scripts/chatbot_eval/gold/sales_target.jsonl`: at least 8 target asks (en / ms / zh, dealer
and salesperson words, a named period, a named dealer) expecting `order_status = sales_target`, plus at
least 4 near misses that must stay `sales_report` / `sales_ranking` ("my sales this quarter", "top 5
dealers"). Run `scripts.chatbot_eval.parser_gold live` on the published unlabelled version, OpenAI eval
key only (`--require-key-last4`), `--max-usd 0.25`, `--repeats 3`, plus the existing sales gold rows for
regression; stop on any 429 or 2 busy replies. Per-PR gate only; no full hidden run without the owner's
OK; never the Gemini org key. Numbers go in the PR.

### Test DB

`sorento_stc_throwaway` (bootstrapped to head oihr_0010), `sorento_crm_backend/.env.ci-tests`
(gitignored); run with `SORENTO_ENV_FILE=.env.ci-tests`. Drop both after merge.
