# PLAN: parser prompt rendered per contact audience

Status: Plan. Behaviour card filed as one crew-ask on PR #1429; build blocked on the owner's
answer AND on #1405 (PROMPT-DYNAMIC) merging. Track: full (it touches what a contact may see,
so security review runs). UAC: `parser-per-audience-2oct-acceptance-criteria.md`.

crew-lane: PARSER-PER-AUDIENCE

## Journey

A dealer asks the bot about stock on WhatsApp. Today the parser is sent the same 33,207-token
prompt a buyer gets, including purchase cost, purchase orders, the sales report, sales analysis,
top selling and the low stock report, none of which the dealer can be answered on. After this lane
the dealer's parser prompt is the same template with those blocks left out (about 26.7k tokens).
The backend refusal stays the control: hiding a block is a size and focus change, never the gate.

## Scout facts (all against #1405 head 8ce60b41, `sorento_crm_backend/`)

### The prompt

- The prod text is `alembic/data/chatbot_semantic_parser.prod-20261001.txt`: 1,741 lines and
  33,207 tokens (o200k_base, which is what `gpt-4o-mini` uses).
- It is rendered per turn at `engine.py:3425-3430` through `head/parser.py:574-610`, which calls
  `ai_prompt_registry.render` (`ai_prompt_registry.py:1415-1440`). That fills `{{current_date}}`
  and the registry tokens from `chatbot_prompt_vars.render_values_safe`
  (`chatbot_prompt_vars.py:389`).
- The text is resolved by the `production` label (`ai_prompt_registry.py:1364-1387`). Its cache
  is a 60 s TTL keyed `(name, label)`.
- At render time the prompt knows nothing about the contact. `access_levels`
  (`chatbot_prompt_vars.py:124-135`) is the catalogue of ALL active access types, not this
  contact's.

### What actually gates a domain

Contact access types do NOT gate any domain.

- **Access types are display and tier facts only.** They are many-to-many on the contact through
  `respond_contact_access_types` (`models/access.py:88-115`, `:302-306`). They drive:
  - the promotion and attachment tier (`lanes/business/tier_gate.py:42-52`);
  - stock visibility (`models/access.py:803-906`);
  - the office-staff exemption from customer scoping (`contact_customer_scope.py:21-41`).
- **The gates that refuse answers are per-contact reveal grants**
  (`contact_field_reveals` -> `ctx.access.attributes`, `head/access.py:42-63,133`):
  - `purchase_orders.cost`: the whole `purchase_cost` domain is refused before any tool
    (`answer.py:1165-1168`, `lanes/business/__init__.py:1459-1474`). Reply: "Sorry, you are not
    allowed to access purchase cost".
  - `sales_orders.sales_report`: the `sales` domain and every `SALES_FIGURE_STATUSES` ask
    (sales_report, sales_analysis, top_selling) are refused (`engine.py:3936-3951`,
    `__init__.py:1601-1611`). Reply: "Sales report is not enabled for your account."
  - `purchase_orders.placed`: gates ONLY the PO rung of the cross-domain climb
    (`answer.py:1156`). **A direct `purchase_order` ask is NOT refused.** It runs, and only the
    restricted fields are stripped (`turn/fetch.py:2644-2713`). See Q2.
  - `scm.low_stock_report`: the low stock report (`__init__.py:1526-1527`).
  - `sales_orders.outstanding`: the SO arm of an outstanding answer is redirected to DO
    (`__init__.py:1846-1849`). The order domain itself stays open.
- **Every domain row already carries its grant.** `chatbot_domains.reveal_key`
  (`models/chatbot_policy.py:44`; seed at `turn/policy_rows.py:149,207,301,323,345`).
  A dormant per-domain gate reads it (`turn/apply.py:2204-2208`), but `load_profile` sets
  `grants=None` (`turn_runtime.py:432-436`), so that gate never fires today.
- **Staff** have no identity in a WhatsApp turn. The console (`api/v1/system/chatbot.py:638`)
  runs as a real contact and inherits that contact's grants.
- **Prompt caching:** there is no `cache_control` anywhere. OpenAI applies its automatic prefix
  cache (1,024 tokens or more, exact prefix). The provider is set in the DB per label, defaulting
  to openai / gpt-4o-mini (`models/ai_assistant.py:31-32`).

## Design (one template, rendered per audience)

1. **Audience = the set of gated grants the contact holds.** It is read from the same
   `ctx.access.attributes` the refusals read, so the prompt can never drop a block the backend
   would answer, and never keep one it would refuse unless that block is untagged. There is no
   new per-contact field and no access-type mapping table.
2. **Tags in the template.**
   - A block is wrapped in `{{#only purchase_cost}}` ... `{{/only}}`, on lines of their own or
     inline for a span inside a shared line.
   - A tag names a `chatbot_domains` row (`purchase_cost`, `purchase_order`, `sales`). The
     renderer reads that row's `reveal_key`, so the tag-to-grant mapping is data.
   - One extra tag, `low_stock_report`, is an intent, not a domain row. It maps in code to
     `scm.low_stock_report`, next to `DOMAIN_GRANT_REQUIRED`.
   - Unknown tag: the block is KEPT and the render logs a warning. Fail open on size, never on
     access, because the backend still refuses.
3. **Registry variables filter by the same audience.** `{{domains}}`, `{{domains_detail}}`,
   `{{domain_words}}` and `{{statuses}}` drop rows whose domain is hidden. On prod most of these
   are still literal text (#1405 identical report), so the literal lines carry inline tags
   instead.
4. **The render is one step after label resolution.** It uses the same version, the same
   `production` label and the same text cache. The tag strip runs on the resolved text, so there
   is no second version stream.
   - Full audience: markers are removed and the result is byte-identical to today's render.
     There is a test for this.
   - The prompt editor preview gains an audience picker (later slice, if the owner wants it).
5. **Rollout switch (Q3).** A `system_settings` boolean `chatbot_parser_per_audience`, default
   off. Off: everyone gets the full render, so there is no behaviour change on deploy.
6. **The security control stays the backend.**
   - A test drives a dealer contact (no grants) with a FORCED parser output of `purchase_cost`,
     `sales_report` and `purchase_order`, and asserts the refusal for each.
   - The PO assertion needs Q2's answer: today a direct PO ask is answered with fields
     stripped.

## Tag map on the owner's prod text (prod-20261001 line numbers)

| Tag | Grant | Whole-line blocks | Tokens | Inline spans |
| --- | --- | --- | ---: | --- |
| purchase_cost | purchase_orders.cost | 81, 727-729, 985-1004 (LAST PURCHASE COST), 1675 | 410 | 82 enum entry, 87 "purchase cost", 928-929, 933 |
| purchase_order | purchase_orders.placed | 414-416, 698, 918-933 (PURCHASE ORDERS), 957-963, 971-973, 1674 | 586 | 46, 87 "PO", 583, 655, 693-694, 777, 786, 792 supplier, 803, 820, 968, 1621 |
| sales | sales_orders.sales_report | 651-652, 1027-1134 (SALES REPORT), 1250-1296 (SALES ANALYSIS), 1397-1560 (TOP SELLING) | 5,267 | 778 `sales_report` |
| low_stock_report | scm.low_stock_report | 1006-1025 (LOW STOCK REPORT) | 278 | 1666 intent `low_stock_report` |

Kept for everyone: the SO outstanding vocabulary (`so_outstanding`, `do_outstanding`), because
the DO rules share it; SPO / last in (`spo_allocation`, no grant); incoming, stock, promotion,
product, attachments, forms, portal and ideate.

## Measured sizes (o200k_base, whole-line blocks only; inline spans take roughly 100 more off)

| Audience | Tokens | Share of full |
| --- | ---: | ---: |
| Full (all four grants: buyer, admin console) | 33,207 | 100% |
| No cost (PO + sales + low stock) | 32,797 | 98.8% |
| Sales only (linked dealer holding the sales report grant) | 31,933 | 96.2% |
| Dealer (none of the four) | 26,666 | 80.3% |

### Real dev contacts (crew, read-only, sorento_cagent_stack, 100 contacts, 2 Oct 2026)

| Gated grants held | Contacts | Example | Tokens | Share |
| --- | ---: | --- | ---: | ---: |
| purchase_orders.placed only | 88 | ...6092 "Am", End User | 27,252 | 82.1% |
| cost + placed | 5 | | 27,662 | 83.3% |
| none | 5 | | 26,666 | 80.3% |
| cost + placed + sales_report | 1 | Mr Loo, all 7 types | 32,929 | 99.2% |
| all four | 1 | Jayson, type dealer | 33,207 | 100% |

All reveal rows are `granted=true`. 95 of 100 contacts hold `purchase_orders.placed`, an end
user among them. With Q1(a) as asked, nearly every dealer keeps the PO blocks: on dev data the
grant does not separate dealers from office. See the revised Q2 on #1429.

Prompt cache:

- `{{current_date}}` sits at line 14 (126 tokens in), so the cache already turns over daily.
- The first gated span is line 46, at 692 tokens in. That is under the 1,024-token minimum, so
  each audience is its own cache entry and no prefix is shared across audiences.
- With at most a handful of live grant combinations, each audience still gets heavy traffic, so
  the hit rate per audience stays close to today's. The cost is one cold miss per audience per
  day.
- No `cache_control` is used today, so the Anthropic path is uncached either way.

## Slices (after the owner answers and #1405 merges, rebased on main)

1. Red tests (tester), from the UAC:
   - full render byte-identical;
   - dealer render free of the forbidden terms;
   - tag parser edge cases (nested, unbalanced, unknown);
   - backend refusal under a forced parser output;
   - setting off means full render.
2. Renderer: `chatbot_prompt_audience.py` (tag strip plus the audience from grants). Wire it into
   `head/parser.resolve_config` behind the setting. Variable filtering.
3. Migration: an unlabelled new version of the prod text with the tags inserted, like
   `pdyn_0003` (verbatim-proof first, no label moves). The owner promotes it.
4. Q2, if approved: `purchase_order` joins `DOMAIN_GRANT_REQUIRED` on `purchase_orders.placed`.
5. Kill tests, reviewer, security review, hand-test script, PR ready.

## Kill list (tests must fail when these are broken)

- The strip keeps a tagged block for a contact without the grant.
- The audience is read from access types instead of grants.
- The setting is ignored.
- The full render differs by one byte from today's.
- The backend refusal is removed (the forced-intent test must go red).
