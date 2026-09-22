# UAC - Chatbot dealer stock verdict (site-pool availability, per-product quantity capture)

Plan: `PLAN-chatbot-dealer-stock-verdict.md`. Numbering: AC-172x to AC-179x. Each criterion names
its evidence (pytest / replay fixture / journey / console check / browser). "Contact" = a Respond.io
contact through `/api/v1/external/chat/turn`. Base: `main` at 2280975f9, which includes the turn
engine re-architecture (#952). "Dealer" below = a contact whose resolved stock visibility policy
mode is `availability` (D12); nothing here reads an access type name.

## Journey

Actor: a dealer on WhatsApp. They arrive from the Respond.io channel with a few product codes in
mind and want to know whether Sorento can supply them. The system already knows the contact, the
contact's stock visibility policy (mode `availability`, the warehouse list the dealer may count
against), every stock row, every open sales order line, every in-transit allocation with its
destination and ETA, every open purchase order line with its destination, the low-stock threshold
and the default lead time. The dealer is never told a quantity of ours.

1. They type "stock for MWT5727SS-CR 5, MHS1028 60, MSK11A-QT and ABC123?". The parser reads a
   stock ask, four products, and a quantity on the first two. Nothing else is asked about products
   it already understood.
2. Two products have no quantity, so the reply is a question, not an answer: it lists what was
   noted (`MWT5727SS-CR x 5`, `MHS1028 x 60`) and asks how many they need for `MSK11A-QT` and
   `ABC123`. No verdict is given yet, for any product.
3. They type "MSK11A-QT 110, ABC123 20". The quantities merge into the noted list. Every product
   now has a quantity, so the bot answers.
4. Or they type "just proceed". The bot answers the noted products only and names the ones it did
   not check.
5. Or they type "make MHS1028 80". The quantity is replaced, the missing list is unchanged, and
   the bot asks again for what is still missing.
6. The answer is one line per product, in the order asked: `CODE x N: Yes, available.`, or
   `... Yes, available, but running low.`, or `... Not available.`, optionally followed by one
   disclaimer: `but there is [limited] incoming, ETA dd/mm/yyyy`, `but there is [limited]
   purchase, ETA in 90 days`, or both joined by `and`. The verdict is judged only against the
   dealer's allowed warehouses: on hand minus open sales orders there, in-transit allocations
   bound there, open purchase order lines bound there.
7. A later message "and MHS1028 100?" re-runs that one product with the new quantity.
8. Halfway through, they ask something else: "any promotion on MSK11A-QT?". The bot answers the
   promotion as it does today and says nothing about the stock check. The noted list and the
   missing list are parked, not lost. Two turns later they type "MSK11A-QT 110, ABC123 20": the
   parked stock check fills and answers. Or they type "back to the stock check": the bot re-asks
   only what is still missing. Or they type "never mind the stock check": the parked check closes.
   Nothing expires on its own.

Other stakeholders: nobody is notified; this is a read. Staff and every contact whose policy mode
is `detailed` or `compact` see no change at all.

## Measured (prod copy `sorento_ai_automation_0921`, 22 Sep 2026)

- `stock_visibility_policies`: one global default row (`detailed`), 11 contact rows, no
  access-type row, no `availability` row. Contact include-lists in use: {BRW, MWH, MOCHA-WH} and
  {DC1, RESERVE, RESERVED}.
- Contact access types by count: `dealer` 30, `cabana_dealer` 32, `mocha_dealer` 46,
  `sorento_office` 29, `cabana_office` 29, `mocha_office` 42, `end_user` 49.
- Warehouses BRW, MWH, DC1, WH3 are plain `warehouse_code` rows, `segment = dealer`; their bins
  (`BRW-BB`, `MWH-IB`, ...) are `segment = project`. No code names them.
- Open PO lines (`line_status = 'open'`, `qty_ordered > qty_received`): 3,888; 944 (24%) have
  no `warehouse_id`, holding 366,713 units. By destination: BRW-BB 1,053 lines, BRW 1,024
  (343,000 units), BRW-IB 326, BRW-IR 221. 26 lines have no `expected_date`.
- Open in-transit allocations (`spo_allocations`, open, allocated > received): 1,020; 6 have no
  `warehouse_id`, 84 have no `expected_date`. Destinations: BRW 333, BRW-BB 324, BRW-IB 111,
  BRW-IR 86, MOCHA-WH 84.
- Open PO lines that also carry an open in-transit allocation: 0. The two supplies are disjoint
  today, so they are counted separately and never netted.
- `system_settings.default_product_standard_lead_time_days` = 90 (server default 90).
- The engine never sets `requested_qty` on the stock tool call (0 write sites under
  `app/services/chatbot/`), so an `availability`-mode contact is always asked "How many units do
  you need?" and never answered. `demand_qty` is one scalar per turn; `entities[]` has no
  quantity; `Focus.products` entity dicts have no quantity key.

## Rulings (D-table; "ruled" = owner 19 to 22 Sep 2026, the plan page markup of 22 Sep included; "proposed" = still open)

| # | Decision | Status |
|---|---|---|
| D1 | The dealer's location set is the resolved policy's warehouse list (include or exclude list), nothing else. On hand, open SO, incoming and PO all filter by that same set. No new location setting. | ruled |
| D2 | Available = on hand minus open sales order quantity (`qty_ordered - qty_delivered`, `line_status = 'open'`), both summed over the allowed warehouses. Supersedes the 25 Aug 2026 "on hand only" basis for `availability` mode. Open SO lines with no `warehouse_id` are not subtracted. | ruled |
| D3 | Purchase ETA is the phrase `ETA in N days`, N = `system_settings.default_product_standard_lead_time_days`. No PO date is shown. | ruled |
| D4 | Base `main` (has #952). One lane, one branch `feat/chatbot-dealer-stock-verdict`, one PR. | ruled |
| D5 | Full suite in this lane: verdict engine, site-pool incoming and PO, threshold setting, per-product quantity capture with a continuous ask, proceed-anyway. | ruled |
| D6 | Verdict rule, deficit D = ask - available, T = threshold: ask <= available gives `available`, `running_low` when ask >= T x available. Else `not_available`, and incoming is consulted first: incoming >= D names incoming only (`limited` when D >= T x incoming), PO ignored; 0 < incoming < D and incoming + PO >= D names both (`limited` when D >= T x (incoming + PO)); no incoming and PO >= D names purchase only (`limited` when D >= T x PO); otherwise no disclaimer. Verified by script against all 18 owner rows. | ruled |
| D7 | T is configurable: one threshold for all three comparisons, `system_settings.chatbot_stock_low_threshold_pct`, integer 1 to 100, default 50, card on Settings > Chatbot (owner on the plan page: "make the T configurable"). | ruled |
| D8 | Open PO lines with no destination warehouse are not counted for a dealer (the `on_order_v` and PO-book precedent). Alternative if the owner prefers: count them for every dealer. | ruled |
| D9 | In-transit allocations with no destination warehouse are not counted (6 rows). | ruled |
| D10 | Incoming ETA = earliest `spo_allocations.expected_date` among counted allocations; none dated gives `ETA to be confirmed`; a past date prints as it stands (the book is trusted, `spo_supply.py` rule). | ruled |
| D11 | Incoming and PO are counted from their own tables with no netting (measured disjoint). | ruled |
| D12 | The quantity loop and the verdict apply to every contact whose resolved policy mode is `availability`. Going live for dealers = three access-type policy rows (`dealer`, `cabana_dealer`, `mocha_dealer`; mode `availability`; warehouses BRW + MWH), entered by the owner on the existing admin page. Data, not code. | ruled |
| D13 | Per-product quantities come from the parser: `entities[].quantity` (number or null) and one new generic verdict key `proceed_anyway` (boolean, "go ahead without answering the open question"). Deterministic fallback: exactly one product without quantity and a top-level `demand_qty` assigns it. The prompt change is published by the owner (Prompts page); until then the fallback carries single-product asks. | ruled |
| D14 | While any asked product lacks a quantity, the reply is the noted list plus one question for the missing ones. No verdict is shown for any product until every one has a quantity or the dealer says to proceed. | ruled |
| D15 | "Just proceed" follows the semantic meaning the parser reads, not a fixed rule (owner: "follow semantic meaning"). `proceed_anyway` true = answer with what is noted and drop every product still missing a quantity; a message that names products to drop ("skip C", "forget ABC123") drops only those through the existing `entity_op` remove path and keeps asking for the rest; "check A only" is `scope_exclusive` as today. The reply names the products it did not check: `Not checked: C, D`. | ruled (confirmed on the plan page, round 2) |
| D16 | A restated quantity replaces the earlier one for that product; a new product joins the list; nothing is asked twice for a product already noted. | ruled |
| D17 | No quantity of ours ever reaches the reply: not on hand, not incoming, not PO, not a percentage. Only the dealer's own asked quantity, the ETA date and `in N days`. | ruled |
| D18 | Superseded by D21 to D23: the open stock check is an open TASK on the focus, parked and resumable, not a one-shot pending. | superseded |
| D19 | Contacts under `detailed` or `compact`, and staff, are unchanged: no loop, no verdict, reply byte-identical to today. | ruled |
| D21 | The open task lives ON THE CONTEXT (owner, round 4: "I thought we have focus and it is meant for this; the notepad is context; it is supposed to be semantic, I can instruct the agent"). `Focus` is the context and today holds what the conversation is about (products, customer, dates, ...) but not what is still OWED. One new axis, `Focus.tasks`: a LIST of `Task(kind, domain, slots[key, label, value or null], status open or parked, opened_at_turn, touched_at_turn)`, at most one task per kind, persisted inside the focus wire, filled from ANY turn whose verdict carries a value one of the tasks claims, whatever the current subject, and driven only by the dealer's words through the parser (add a product, change a quantity, drop one, proceed, never mind). It is semantic: the parser reads every open task as one hint line each. A list from day one because a second concurrent collection already exists (the ideation lane keeps its own opaque state in `session.ideation`, owner round 5: "collect ideation and stock demand and other forms at the same time"). `stock_qty` is the first task kind; `TaskKind` (claims / missing / fill / to_fetch / question) is the seam the next kind uses. Concurrency rules (D24). The roster and offer `pending` keeps today's one-shot rules untouched (`handpass5-stale-roster-forms` stays green). | ruled (round 6: approve the list AND wrap the ideation lane as a task kind in this lane, D26) |
| D24 | Several tasks at once. (a) A verdict value goes to the task whose kind `claims` it: a quantity on a product goes to the stock task; a value no kind claims is an ordinary message. (b) When two open tasks could claim the same value (a bare number with one stock product missing and an ideation media menu open), the parser's attribution wins if it names one; otherwise the bot ASKS the dealer which task the number is for, through a `task_pick` roster (`pending.kind = task_pick`, options = the open tasks by label; "1" or the task's word answers it, the value is then applied to that task) (owner round 6). (c) A question turn asks for ONE task, the one this turn touched or opened, never a merged questionnaire. (d) "Back to the stock check" resumes the task whose domain is named; a bare "back to it" resumes the most recently touched. (e) The parser hint lists every open task, most recently touched first. (f) The ideation lane's `session.ideation` state is NOT migrated in this lane; the trigger for wrapping it as a task kind (`ideation`, opaque slots owned by `crm_ideation_turn`) is the first time an ideation and a stock check are both open in a real transcript. | ruled |
| D25 | Who validates (owner round 6: "who says a stock quantity per product is a must, is it the MCP layer?"). Three layers, one job each, the doctrine the archived visibility plan already set ("enforced in the backend; n8n and MCP only present"): (1) the BACKEND endpoint owns the rule, because the rule depends on the contact's policy and the data (today `GET /inventory/stock/balance` answers `needs_quantity: true` per product for an `availability` contact and nothing for staff); a required field is therefore a fact the reply states, never a check the caller performs; (2) the MCP catalog DECLARES the contract in `ToolSpec` (the request param that carries the value, `requested_quantities`, and the reply key that names the gap, `needs_quantity`) and `sync_catalog` writes it to `mcp_tools`, so n8n, the console and the engine read one declaration; the MCP never validates, it is a stateless read-only wrapper also used by direct callers; (3) the ENGINE is generic: a `TaskKind` maps the declared gap key to slots and the declared param to the fetch, and knows nothing about why a quantity is required. For a future form the required fields are declared where the endpoint that needs them lives, exposed once in its `ToolSpec`, and the engine needs a kind, not a rule. In this lane `StockQtyTask` reads `needs_quantity` and writes `requested_quantities` directly; the generic `ToolSpec.collects` declaration is the named trigger for the second kind. | ruled |
| D26 | Ideation as the second task kind, in this lane (D21, round 6). Measured: the ideate lane is a passthrough to the MCP tool `crm_ideation_turn` (`lanes/ideate.py:34`), its state is the opaque `session.ideation` pointer the tail re-persists every turn (`turn/tail.py:33`), it runs whenever the parser puts `ideate` in the plan's domains (`turn/route.py:46, 84`), and its `pending_media` menu is answered with `reference_positions`. So the state already survives a detour and already resumes when the parser routes to `ideate`; what is missing is the open/parked status, the parser hint that an idea is in progress, and the D24 tie. `IdeationTask`: no slots of its own (the tool owns them), `claims` = `domain_hint == "ideate"` or an open `pending_media` answered by positions, `fill` = the lane ran, `question` = none (the tool speaks), close = tool `status == "complete"` or a `topic_reset` aimed at ideation. `session.ideation` stays where it is with the same single writer; the task is a status over it, not a copy. | ruled |
| D27 | One availability entry per product code across the dealer's companies (live pass run 2, 22 Sep: the test dealer spans two companies that both carry MHS1028, so the question read "MHS1028, MHS1028"). The availability block merges entries whose `product_code` matches case-blind within one response: on hand, open SO, incoming and purchase are summed before the verdict, the incoming ETA is the earliest, `product_id` is the first in page order, and a quantity given for any merged id applies to the merged entry. `detailed` and `compact` untouched; `pagination.total` still counts products. | ruled (captain, review round 5) |
| D28 | A JSON-object tool parameter crosses the MCP as an OBJECT-typed param: FastMCP's `pre_parse_json` (`mcp/server/fastmcp/utilities/func_metadata.py`, guard `annotation is not str`) turns a JSON-looking string argument into a dict before Pydantic runs, so a scalar-only union rejects both shapes. `sorento_crm_mcp/server.py` declares such params in `TOOL_OBJECT_QUERY_PARAMS` (typed `dict[str, int] | str`) and `_normalize_query_value` serialises a dict to a compact JSON string for the backend query. Found only by the live pass (run 1 and 2); replay stubs never see the schema. | ruled (captain, review round 4) |
| D22 | Parking is silent: when the customer asks about something else, the other answer is given as today and the reply carries no reminder of the parked form. Resume happens when a slot value arrives, or when the customer names the form's topic again with nothing new ("back to the stock check"), which re-asks only what is still missing. No TTL, no turn counter (owner ruling 12 Sep, "as a user I don't know my TTL"). | ruled |
| D23 | The form is continuous: it is never closed by a Respond.io conversation closing, by a session boundary, by time, or by any manual action (owner, plan page round 3: "it is continuous, not related to any manual closing"). It ends only through the dealer's own words: every slot filled and answered; `proceed_anyway`; a new stock ask with `scope_exclusive` (a fresh product set replaces it); or a `topic_reset` aimed at its own domain ("never mind the stock check": `topic_reset` true and `domain_hint` is the form's domain or null). A `topic_reset` aimed at another domain ("forget that, promotions?") parks it. | ruled |
| D20 | The stock tool keeps `requested_qty` (one number for every product, n8n and direct callers) and gains `requested_quantities` (JSON object product UUID to integer). When both arrive, the map wins per product and the scalar fills the rest. | ruled |

## Phase 0 - verdict engine [BE]

- **AC-1720 [T]** Given `verdict(available, ask, incoming, po, threshold_pct)` in
  `app/services/stock_verdict.py`, When called for each of the owner's 18 rows (available 100, the
  ask / incoming / PO of each row, threshold 50), Then the `(answer, running_low, sources, limited)`
  tuple equals the row's `Stock Answer` + `Disclaimer` columns. pytest, parametrized over the 18 rows.
- **AC-1721 [T]** Given available 0 and ask 10, When incoming is 30, Then `not_available`, sources
  `incoming`, `limited` false; When incoming 5 and PO 5, Then sources `incoming, purchase`, `limited`
  true. pytest.
- **AC-1722 [T]** Given ask 0 or negative, When verdict is called, Then it raises `ValueError`; the
  service never calls it without a positive ask. pytest.
- **AC-1723 [T]** Given threshold 30 and available 100, When ask is 30, Then `running_low` true;
  When ask is 29, Then false. pytest.

## Phase 1 - threshold setting [BE] [FE]

- **AC-1730 [BE]** Given migration `dsv_0001`, When applied, Then
  `system_settings.chatbot_stock_low_threshold_pct` exists, integer, not null, server default 50,
  and `alembic heads` is single. pytest (`SystemSetting` column present, default read back as 50).
- **AC-1731 [BE]** Given `PUT /api/v1/user-management/settings` with
  `chatbot_stock_low_threshold_pct: 40`, When read back through `GET /settings`, Then the value is 40
  and it appears in the `settings` dict (the manual builder). Given 0 or 101, Then 422. pytest.
- **AC-1732 [FE]** Given Settings > Chatbot, When it renders, Then a card "Stock low threshold"
  shows the value as a percentage input, saves through `chatbotSettingsService`, and toasts on
  success and on error via `extractApiError`. vitest + browser at 375px and 1280px.
- **AC-1733 [FE] [UX]** No motion is added to the card; the existing card layout is reused.
  reviewer check.

## Phase 2 - server availability block [BE]

Seeds for every test: three warehouses BRW / MWH / DC1 (DC1 outside the policy), one product, a
contact with an `availability` policy `warehouse_ids = [BRW, MWH]`, stock rows, open SO lines,
`spo_allocations` and `purchase_order_lines` as each case needs. All quantities of ours are asserted
absent from the payload with the existing `_assert_no_quantity_anywhere` helper.

- **AC-1740 [BE]** Given on hand BRW 60, MWH 40, DC1 500 and open SO BRW 10, When
  `requested_quantities = {p: 91}`, Then the entry has `available` false (91 > 100 - 10; an ask of
  exactly 90 is `available`, the boundary is inclusive per AC-1720 row 4), and DC1 is not counted.
  pytest.
- **AC-1741 [BE]** Given on hand 100 (allowed) and open SO 0, When ask 50, Then `available` true and
  `running_low` true; ask 49 gives `running_low` false; ask 100 gives true; ask 101 gives
  `available` false. pytest.
- **AC-1742 [BE]** Given on hand 100, ask 110, an open allocation of 10 to BRW dated 2026-10-12 and
  an open PO line of 25 to BRW, When fetched, Then `available` false, `disclaimer.sources ==
  ["incoming"]`, `limited` true, `incoming_eta == "2026-10-12"`, and PO is not named (D6). pytest.
- **AC-1743 [BE]** Given on hand 100, ask 110, allocation 5 to BRW, PO 10 to BRW, Then sources
  `["incoming", "purchase"]`, `limited` true, `purchase_eta_days == 90`. pytest.
- **AC-1744 [BE]** Given on hand 100, ask 110, no allocation, PO 25 to BRW, Then sources
  `["purchase"]`, `limited` false. pytest.
- **AC-1745 [BE]** Given ask 110, allocation 50 to DC1 and PO 50 to DC1 (outside the policy), Then
  no disclaimer: `sources == []`. pytest.
- **AC-1746 [BE]** Given an open PO line of 500 with `warehouse_id NULL` and an allocation of 500
  with `warehouse_id NULL`, Then neither is counted (D8, D9). pytest.
- **AC-1747 [BE]** Given two counted allocations dated 2026-11-01 and 2026-10-05, Then
  `incoming_eta == "2026-10-05"`; given none dated, Then `incoming_eta` null. pytest.
- **AC-1748 [BE]** Given `system_settings.default_product_standard_lead_time_days = 120`, Then
  `purchase_eta_days == 120`; given `chatbot_stock_low_threshold_pct = 30`, Then ask 30 of 100 is
  `running_low`. pytest.
- **AC-1753 [BE]** Given products A and B in two companies with the same code, contact scoped
  to both, When `requested_quantities` names either id, Then one entry with the summed available
  (D27). pytest (review round 5).
- **AC-1749 [BE]** Given products A and B asked and `requested_quantities = {A: 5}`, Then A carries
  a verdict and B has `needs_quantity` true with `available` null and no disclaimer. Given
  `requested_qty = 7` as well, Then B is judged at 7 (D20). pytest.
- **AC-1750 [BE]** Given a `detailed` or `compact` policy, or no `contact_id`, When
  `requested_quantities` is passed, Then the response is byte-identical to today (no
  `stock_availability`, no verdict keys). pytest.
- **AC-1751 [BE]** Given a received allocation (`receipt_status = 'fully_received'`), a closed PO
  line, or a shipment in a received state, Then none is counted. pytest.
- **AC-1752 [BE]** `GET /inventory/stock/balance?requested_quantities=<json>` with a non-object or
  a non-UUID key returns 400; the `response_model` declares every new key (`verdict`,
  `running_low`, `disclaimer`) so none is dropped. pytest through the client.

## Phase 2 - MCP presenter [BE]

- **AC-1755 [T]** Given a `stock_availability` payload of one product with `verdict = available`,
  `running_low = false`, When rendered, Then the item line reads `MWT5727SS-CR x 5: Yes, available.`
  MCP pytest.
- **AC-1756 [T]** `running_low` true renders `Yes, available, but running low.`; `not_available`
  with no sources renders `Not available.`; sources incoming limited renders `Not available, but
  there is limited incoming, ETA 12/10/2026.`; both renders `... limited incoming, ETA 12/10/2026
  and limited purchase, ETA in 90 days.`; purchase only, not limited renders `Not available, but
  there is purchase, ETA in 90 days.`; incoming with null ETA renders `ETA to be confirmed`. MCP
  pytest, one case each.
- **AC-1757 [T]** Given entries where one has `needs_quantity` true, When rendered, Then the intro
  lists the noted products (`Noted: A x 5, B x 60`) and asks `How many units do you need for C and
  D?`, and no verdict line appears for any product. MCP pytest.
- **AC-1758 [T]** The rendered envelope contains no integer other than the asked quantities, the
  ETA date and the lead-time days (regex sweep in the test). MCP pytest.
- **AC-1759 [T]** `crm_inventory_stock_balance_list` catalog lists `requested_quantities` as a query
  param and the tool description tells the caller when to pass it. `sync_catalog` seeds it
  (`mcp_tools` row updated). MCP pytest + backend pytest.

## Phase 2 - engine: the form, capture, ask, proceed, park, resume [BE]

Every test here is an engine-level pytest with the parser verdict supplied and the MCP tool call
stubbed (`tests/chatbot/replay_turns/console/*.json` shape, run by `test_turn_replay.py`), or a
table test on `turn/apply.py`. No live parser call in CI.

- **AC-1760 [T]** Parser schema: `entities[].quantity` is declared `["number","null"]`,
  `proceed_anyway` is declared `["boolean","null"]`, both are in `required`, and the fallback prompt
  text names both (schema guard test extends the existing one). pytest.
- **AC-1761 [T]** Given a verdict with four products, two carrying `quantity`, and a contact whose
  stock tool reply has `needs_quantity` true for the other two, When the turn runs, Then
  `branch_kind = business_query`, the reply lists the two noted products with their quantities and
  asks for the two missing by code, no verdict line appears, and `session.focus.tasks[0] == {kind:
  "stock_qty", domain: "inventory", status: "open", slots: [A:5, B:60, C:null, D:null]}`.
  `session.open_question` is null (a task is not a roster). replay fixture.
- **AC-1762 [T]** Given the open task from AC-1761 and a verdict with entities C
  (quantity 110) and D (quantity 20), When the turn runs, Then the stock tool is called once with
  `requested_quantities` holding all four, the reply has four verdict lines in asked order, and
  `session.focus.tasks` is empty. replay fixture.
- **AC-1763 [T]** Given the same task and a verdict `proceed_anyway = true` with no entities,
  When the turn runs, Then the tool is called with the two noted quantities only, the reply has two
  verdict lines and ends with `Not checked: C, D`, and `session.focus.tasks` is empty. replay fixture.
- **AC-1764 [T]** Given the same task and a verdict with entity B `quantity = 80` only, Then
  B's quantity is replaced, C and D are still asked, and `Noted:` shows `B x 80`. replay fixture.
- **AC-1765 [T]** Given the same task and a bare-number verdict (`demand_qty = 110`, no
  entities) with exactly one product missing, Then the number is assigned to it (D13 fallback);
  with two missing, Then the bot asks again naming both. apply table test.
- **AC-1766 [T]** Given the same task and a verdict `topic_reset = true` with `domain_hint =
  "inventory"` (or null) and no entities, Then `session.focus.tasks` is empty (D23 close). Given
  `topic_reset = true` with `domain_hint = "promotion"`, Then the task is `parked` and the
  promotion is answered. Given the session's Respond.io conversation is closed and reopened
  between turns, Then the task is unchanged (D23: continuous). apply table test.
- **AC-1767 [T]** Given a `detailed`-policy contact and the same four-product verdict, When the
  turn runs, Then no task is opened and the reply is today's detailed listing (the tool reply
  carries no `stock_availability`). replay fixture.
- **AC-1768 [T]** `apply()` stays pure: the existing source-scan test in
  `test_rearch_s2_apply_is_pure.py` passes with the new branch (no `message.text` read, no I/O).
  pytest.
- **AC-1769 [T]** Given a verdict whose `entities[]` carry `quantity`, When `Focus.products` is
  persisted and reloaded through `focus_to_wire` / `focus_from_wire`, Then the quantity survives
  the round trip. pytest.

### The open task on the focus (D21 to D23)

- **AC-1770 [T]** Given an open `stock_qty` task on the focus, When `session_payload` is written
  and read back through `focus_to_wire` / `focus_from_wire`, Then kind, domain, status,
  opened_at_turn, touched_at_turn and every slot (uuid, code, quantity or null) survive; a
  focus with no `tasks` key loads an empty list. pytest.
- **AC-1771 [T]** Detour and fill. Turn 1 opens the form (C, D missing). Turn 2 verdict:
  `domain_hint = promotion`, entity MSK11A-QT, no quantity. Then the promotion tool is called, the
  reply is today's promotion answer with no stock text, and `session.focus.tasks[0].status == "parked"`
  with slots unchanged, even though `focus.products` now holds only MSK11A-QT (the detour's
  same-axis replace does not touch the task). Turn 3 verdict: entities C (110) and D (20), `domain_hint` null. Then the
  stock tool is called once with all four quantities, four verdict lines, `session.focus.task` null.
  replay chain.
- **AC-1772 [T]** Resume by naming. After the detour of AC-1771 turn 2, a verdict `domain_hint =
  inventory, intent_hint = check_stock`, no entities, no quantity, Then no tool is called, the
  reply is `Noted: A x 5, B x 60` plus `How many units do you need for C and D?`, and the task is
  `open` again. replay chain.
- **AC-1773 [T]** A roster does not break the task. Turn 1 opens the task with C missing. Turn 2
  arms any roster or offer pending (`open_question` non-null; a `product_pick` is not reachable
  for the inventory domain since AC-1690 retired product rostering under `list_all`, so the
  fixture uses whatever pending the engine arms for an unresolved token). Then the task is still
  `open` with its slots untouched. Turn 3 answering that pending leaves the task untouched too.
  The earlier "picked product joins the task as a slot" clause is withdrawn (no product roster
  exists for inventory today; named trigger: a domain with a product roster gains a task). replay
  chain.
- **AC-1774 [T]** Proceed while parked. After a detour, a verdict `proceed_anyway = true` with
  `domain_hint` null, Then the stock tool is called with the noted quantities only, verdict lines
  plus `Not checked: C, D`, task null. replay chain.
- **AC-1775 [T]** No expiry. After the detour, 12 casual or out-of-scope turns (`CARRY`), the
  task is still `parked` with its slots, and turn 15's quantities fill it. apply table test over a
  loop.
- **AC-1776 [T]** Roster rules untouched. `tests/chatbot/journeys/handpass5-stale-roster-forms.json`,
  `handpass6-open-offer-not-swallowed.json`, `handpass6-answered-roster-does-not-linger.json` and
  every existing replay fixture stay green: a stale roster still closes on a new ask; only a
  TASK parks. CI.
- **AC-1777 [T]** Mechanism, not a special case. `turn/task.py` exposes `TASK_KINDS` with two
  entries (`stock_qty`, `ideation`) and a `TaskKind` protocol (`claims`, `missing`, `fill`,
  `to_fetch`, `question`). A test registers a throwaway third kind with two text slots, runs
  the same `decide` and `apply` seams, and shows it opens, parks on a detour, fills from a later
  turn and closes, with no engine change. pytest.
- **AC-1779 [T]** Two tasks at once (D24). Given the stock task open (C missing) and the
  ideation task open with `pending_media` set (the session's `ideation` pointer is handed to
  `apply()` as a keyword argument beside `resolved` / `candidates`, so `apply` stays pure and
  `IdeationTask.claims` can read it), When a verdict carries `entities[C].quantity =
  110`, Then only the stock task fills; When a verdict has `domain_hint = ideate`, Then only the
  ideation lane runs; When a bare number arrives (`reference_positions = [2]`, no domain, no
  entity) and both could claim it, Then no task changes, `open_question.kind == task_pick` with
  two options (stock check, idea), and the next turn's `reference_positions = [1]` applies the
  number to the stock task; When the stock domain is named with nothing new, Then the stock task
  alone is re-asked. apply table test + replay chain.
- **AC-1784 [T]** Ideation task opens. Given a verdict `domain_hint = ideate` and the ideation
  tool stub returning `status = in_progress` with a `session_vars.ideation` pointer, When the
  turn runs, Then `session.focus.tasks` holds `{kind: ideation, status: open}` and
  `session.ideation` is the tool's pointer, unchanged in shape. replay fixture.
- **AC-1785 [T]** Ideation parks and resumes. After AC-1784, a stock ask turn parks it (status
  `parked`, `session.ideation` untouched, stock answered as today); a later verdict `domain_hint
  = ideate` with no entities runs the ideation lane with the same pointer and sets it `open`.
  replay chain.
- **AC-1786 [T]** Ideation task closes on the tool's word. The replay harness runs dry, so the
  ideation tool is never called there; the tool-status half is a unit test on the kind
  (`TASK_KINDS["ideation"].closes_on_tool_status("complete")` true, `"in_progress"` false) and
  the engine removes the task where the ideate lane's `ideate_status` is read (both the
  `run_turn` path and, if it is live, the `complete_turn` / `run_tail` path call the same
  helper). Given `topic_reset = true` with `domain_hint = ideate`, Then the task is removed
  (apply table test).
- **AC-1787 [T]** Hint. With an ideation task open or parked, `build_user_block` emits `Open
  task: idea in progress.` (and `media menu open` when `pending_media` is set). pytest.
- **AC-1788 [T]** Existing ideation tests (`tests/chatbot/test_ideate*.py`, the ideate replay
  fixtures) stay green: the lane's arguments and reply are byte-identical. CI.
- **AC-1778 [T]** Parser hint. When a task is open or parked, `build_user_block` emits one line
  `Open task: stock check. Noted: A x 5, B x 60. Still needs a quantity for: C, D.` per open task
  (an ideation task prints `Open task: idea in progress.`), most recently touched first; when none, no such line. The system prompt names the rule: a quantity given for a product in the open
  task sets `entities[].quantity` for it, whatever the current subject; "add X", "drop Y",
  "make B 80", "proceed", "never mind the stock check" are read as instructions on the task.
  pytest on the block + the schema guard.

## Phase 3 - verification

- **AC-1780 [E2E]** Journey `tests/chatbot/journeys/dealer-stock-verdict.json` drives the owner's
  chains (steps 1 to 8 of the journey, the detour and resume included, plus the 18-row verdict
  spot checks on seeded products)
  against the lane stack once; assertions are the rulings above. Run once at the end of the lane
  and pasted in the PR. `scripts/chatbot_journey.py`.
- **AC-1781 [E2E]** Console YAML `tests/chatbot/console_cases/2026-09-22-dealer-stock-verdict.yaml`
  covers the ask, answer, proceed and detailed-contact cases; run once per
  `documentation/agents/chatbot-verification.md`.
- **AC-1782 [T]** Kill test: commenting out the incoming-first branch in `stock_verdict.py` turns
  AC-1720 red; commenting out the `stock_qty` branch in `apply.py` turns AC-1762 red. reviewer.
- **AC-1783 [BE]** DoD: new column reaches the FE (settings builder), migration re-parented onto
  main's head before PR, `alembic heads` single, guide updated (`guide-writer`), prompt publish
  step and the three policy rows listed in the PR as owner steps.
