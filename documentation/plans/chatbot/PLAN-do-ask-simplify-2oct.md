# PLAN: simplify chatbot DO asks (DO-ASK-SIMPLIFY)

Status: behaviour card posted as crew-ask on PR #1433, waiting on owner answers. Track: FULL
(a data-seed migration for existing staff grants, and a field-reveal (access) change, so the
security reviewer joins).

## Journey

A dealer or staff contact asks the WhatsApp bot about delivery orders (DO). The reply opens
with a short header (one customer name, not every ledger variant), shows only the DO fields
that contact may see, and an ask with no date range gets a "which period?" question with ready
options. A range longer than the cap is refused with a suggestion.

## Behaviour card

### What a "DO ask" is (scope of rules 3 and 4)

An order-domain business turn whose single fetch is `crm_order_management_orders_list` or
`crm_order_management_orders_by_product_list` (the two tools the scope header already covers,
`turn/policy_rows.py:154-160`). NOT covered: `crm_outstanding_report` (SO/DO pending backlog,
its own header and its own `order_date` filter), `crm_sales_report` / sales analysis / top
selling (own lanes), `order_status=so_outstanding` (open SO lines, no DO yet).

### Today (file:line)

| Area | Today |
|---|---|
| Header | `tail/scope_block.py:242-286` `search_scope_header` prints `Customer:` / `Product:` / `Dates:`, prepended by `answer_bridge.py:116-167` `apply_scope_block` (engine call `engine.py:4914-4966`). The customer words come from `_axis_words` (`scope_block.py:115-168`): typed token, else parser raw, else EVERY gate row's `display_name` (one name per ledger, `:165-167`). |
| Fields | `sorento_crm_mcp/presenters.py:411-438` `_orders_list`: Company, Order Number, Customer, Order Date, Actual Delivery Date, Status, Pickup Time, Transporter, Driver, Lorry Plate, Warehouse, Products. `_orders_by_product` (`:614`): Company, Order Number, Customer, Order Date, Actual Delivery Date, Products. Only `company_name` carries a field key (3-tuple); the gate in `lanes/business/fetch.py:2645-2700` skips any field without a key (`_has_key`, `:1570`), so none of these can be hidden today. |
| Date range | Parser `date_filter_start/end` (`head/parser.py:133-135`) map to `actual_delivery_date_from/to` (`lanes/business/fetch.py:435-439`, applied `:707-718`). No date = all dates, no default window, no ask-back, no cap anywhere (`scope_block.py:266`: "all dates"). The route caps rows at 20 without a date (`api/v1/order_management/orders.py:33`). |
| Specific numbers | Entity hint `order` (`contracts.py:190-206`); resolver types `order` / `customer_order` / `order_number` (`turn/state.py:104`, `lanes/business/answer.py:2250`) map to `order_ids` (`fetch.py:313-316`). |
| Staff | `turn/state.py:211-218` `is_staff_profile`: `respond_contacts.chatbot_profile.tier == "office"`. |
| Reveals | `contact_field_reveals` (`models/access.py:753`), keys frozen in `contact_field_reveal_service.py:41-62` `FIELD_REVEAL_KEYS`, pinned to the MCP catalogue's `restricted_fields` by `tests/chatbot/test_field_reveal_keys_pinned_to_catalog.py`. Default hidden. |

### Rule 1: compact header

- The `Customer:` line groups the in-scope customer rows by ledger family (`ledger_family_key`,
  `app/services/ledger_family.py:43`, the rule the narrower and the stock-ask card already use)
  and prints the family label (`ledger_family_label`, `:54`):
  - one family, one row: the row's own name, unchanged (`HANLIM TRADING SDN BHD [A/C I]`).
  - one family, several rows: `HANLIM TRADING SDN BHD (6 accounts)`.
  - once PR #1432 lands and every row shares one `customers.account_level` N:
    `HANLIM TRADING SDN BHD, Account N`.
  - several families: first family label + `and N more` (`CHIN CHUN HARDWARE SDN BHD and 3 more`).
  - a typed word that resolved to many rows keeps printing the typed word (`_one_typed_word`,
    `scope_block.py:199`), unchanged.
- `Product: all products` is dropped when no product was named (the line says nothing). A named
  product prints as today.
- `Dates:` always prints the window (with rule 3 there is no "all dates" on a DO list any more,
  except a numbers-only ask, which prints no Dates line).
- Each DO row keeps its own `*Customer:*` line with the full ledger name, so the reader still
  sees which account each DO is on.

### Rule 2: per-contact DO field reveals

| Field | Key | Default for a new contact |
|---|---|---|
| Order Number, Customer, Order Date, Actual Delivery Date, Products, Company | none (always shown) | shown |
| Warehouse | none (always shown) | shown |
| Status | `delivery_orders.status` | hidden |
| Pickup Time | `delivery_orders.pickup_time` | hidden |
| Transporter | `delivery_orders.transporter` | hidden |
| Driver | `delivery_orders.driver` | hidden |
| Lorry Plate | `delivery_orders.lorry_plate` | hidden |

- Built the same way as `purchase_orders.supplier`: the presenter passes the 3-tuple key and
  calls `b.restrict(...)`; the catalogue declares the pairs on both order tools'
  `restricted_fields`; `FIELD_REVEAL_KEYS` gains the five pairs (the pin test enforces both).
  The Contacts > Access > Field reveals checklist then lists them with no UI change.
- Naming: `delivery_orders.<field>` sits beside `sales_orders.*` / `purchase_orders.*`. For
  the ACCESS-MODEL table (`PROMPT_GATES`, PR #1429) these are field parts of domain `order`;
  they gate no prompt block, so nothing is added to `PROMPT_GATES` (crew-note to that lane).
- Existing staff keep what they see today: a data migration inserts `granted=true` rows for
  the five keys for every `respond_contacts` row whose `chatbot_profile->>'tier' = 'office'`
  (idempotent, `ON CONFLICT DO NOTHING`). Dealers and end users get no rows: they lose these
  five fields at deploy. The affected list (count per tier) is produced by the SQL below on the
  dev DB by crew; this sandbox cannot reach it.

```sql
SELECT chatbot_profile->>'tier' AS tier, count(*) FROM respond_contacts GROUP BY 1 ORDER BY 1;
```

### Rule 3: a DO ask carries a date range, unless it names numbers

- A DO ask with no `date_filter_start` and no `date_filter_end` (this turn or carried by
  `_spec_window`, `turn_runtime.py:2327`) fetches nothing and asks back, a new pending kind
  `period_pick`, keeping the subject on focus:

  ```
  Which period for HANLIM TRADING SDN BHD's delivery orders?
  1. This month (Oct 2026)
  2. Last month (Sep 2026)
  Or type a month (e.g. August) or dates (e.g. 15 Sep to 10 Oct).
  ```
  "1"/"2" or a typed month/dates answers it and the original ask runs with that window.
- Exception: the ask names one or more DO/SO/order numbers (entity hint `order`, or a resolver
  hit typed `order` / `customer_order` / `order_number`): no range needed, no cap.
- "This month" means the whole calendar month (01/10/2026 to 31/10/2026), not month to date.

### Rule 4: range cap

- Recommended cap: at most 31 days, inclusive, counted from start to end (rolling, not "same
  calendar month"). So "January", "February", "last week", "this month", "15 Sep to 10 Oct",
  "20 Dec to 10 Jan" are all fine; "January to June" and "January and February" (59 days) are
  refused. A start with no end ("since August") is measured to today.
- Refusal, fetching nothing, with the same `period_pick` options taken from the asked range
  (its last month first, then its first month):

  ```
  That is 6 months (01/01/2026 to 30/06/2026). I can show up to one month of delivery orders at a time:
  1. Jun 2026
  2. Jan 2026
  Or type a month or dates.
  ```

### Real examples (dev replay fixtures under `sorento_crm_backend/tests/chatbot/replay_turns/console/`)

| # | Message | Header today | Header proposed |
|---|---|---|---|
| 1 | "Delivery to hanlim" then pick all (handpass3-owner-17sep..., turn 0) | `*orders* for HANLIM TRADING SDN BHD [A/C II], HANLIM TRADING SDN BHD [A/C I], HANLIM TRADING SDN BHD [A/C III], HANLIM TRADING SDN BHD [A/C IV], HANLIM TRADING SDN BHD, HANLIM TRADING SDN BHD (CERAMIC & ELLECI):` | ask-back "Which period for HANLIM TRADING SDN BHD's delivery orders?"; after "1": `Customer: HANLIM TRADING SDN BHD (6 accounts)` / `Dates: 01/10/2026 to 31/10/2026` |
| 2 | "All" on the Chin Chun picker (same file, turn 2) | `*orders* for CHIN CHUN HARDWARE SDN BHD - [A/C I]` x6, `CHIN CHUN HOMEMART SDN BHD - [A/C I]` x4, `... AND TIMBER TRADING` x3, `JIMMY - I` x2 | `Customer: CHIN CHUN HARDWARE SDN BHD (6 accounts) and 3 more` |
| 3 | "delivery status for hanlim" (case-072, turn 1); rows 202609-0916, 202609-0927 | `Customer: hanlim` / `Product: all products` / `Dates: all dates`, rows with Status `Picked Up / In Transit`, Driver `AZHAR`, Lorry Plate `VQP1678` | ask-back for the period; a dealer then sees rows without Status / Pickup Time / Transporter / Driver / Lorry Plate; a staff contact sees them as today |
| 4 | "delivery for hanlim rpacc" then "only in 2026" (owner-15sep-chain-001, turns 6-7) | `Dates: all dates`, then `Dates: 01/01/2026 to 31/12/2026` | turn 6 asks the period; turn 7 is refused: "That is 12 months ... 1. Dec 2026 2. Jan 2026" |
| 5 | "where is DO 202609-0916" | (no fixture) | no ask-back, no Dates line: `Order: 202609-0916` and the row |

### Edge cases

- A pick answer ("1") after a customer picker: the period question comes after the pick, not
  before (the subject must be known first).
- A carried window: a follow-up ("and chin chun?") keeps the previous window, no re-ask.
- A brand switch inside an open list (`order_list.py` R3/R5) keeps the window.
- Year boundary: "20 Dec to 10 Jan" = 22 days, allowed; "December" asked in January means the
  previous December (parser's job, unchanged).
- Empty result with a valid window: `EMPTY_LIST_LINE` as today.
- A refusal or ask-back never escalates and never offers the team picker.

### Questions (recommendations first)

1. Cap: (a) <= 31 days rolling, (b) one calendar month (start and end in the same month).
   Recommend (a): "15 Sep to 10 Oct" and "last 30 days" are ordinary asks that (b) would refuse.
   Either way "January and February" is refused.
2. Who gets rules 3-4: (a) every contact, staff included, (b) dealers and end users only.
   Recommend (a): one rule is simpler to explain, and staff also get the 20-row cap today.
3. Quantity asks on the same tools ("how many SRT320-CR did hanlim take", `include_summary`):
   (a) exempt, keep today, (b) same range rules. Recommend (a): a total is a report, and a one
   month cap would break the ask.
4. Reveal keys: (a) five per-field keys as tabled, (b) one key `delivery_orders.logistics`
   for all five. Recommend (a): the owner named fields one by one, and status is likely to be
   granted to some dealers without driver/lorry.
5. Header with a product: keep `Product: <code>` (yes), and drop `Product: all products`
   (recommend yes, it carries no information).

## Regression scenarios (DO asks)

Contact D = dealer (no DO reveal grants), S = staff (`tier=office`, seeded grants). Today = Fri 2 Oct 2026.

| # | Contact | Message | Expected |
|---|---|---|---|
| R1 | D | "delivery to hanlim" | period ask-back, options Oct 2026 / Sep 2026; nothing fetched |
| R2 | D | R1 then "1" | list for 01/10/2026 to 31/10/2026, header `Customer: HANLIM ...`, `Dates: 01/10/2026 to 31/10/2026` |
| R3 | D | R1 then "August" | list for 01/08/2026 to 31/08/2026 |
| R4 | D | "delivery to hanlim this month" | list, no ask-back; rows without Status / Pickup Time / Transporter / Driver / Lorry Plate |
| R5 | S | "delivery to hanlim this month" | same rows WITH Status, Pickup Time, Transporter, Driver, Lorry Plate |
| R6 | D | "delivery to hanlim last week" | list 21/09/2026 to 27/09/2026 |
| R7 | D | "delivery to hanlim September" | list 01/09/2026 to 30/09/2026 |
| R8 | D | "delivery to hanlim 15 Sep to 10 Oct" | list 15/09/2026 to 10/10/2026 (26 days, allowed under Q1 (a)) |
| R9 | D | "delivery to hanlim 20 Dec 2025 to 10 Jan 2026" | list, 22 days across the year boundary |
| R10 | D | "delivery to hanlim January to June" | refused with "That is 6 months ..." and options Jun 2026 / Jan 2026 |
| R11 | D | "delivery to hanlim January and February" | refused (59 days) |
| R12 | D | "delivery to hanlim this year" | refused, options Oct 2026 / Jan 2026 |
| R13 | D | "where is DO 202609-0916" | the row, no ask-back, no Dates line |
| R14 | D | "status of 202609-0916 and 202609-0927" | both rows, no ask-back |
| R15 | D | "delivery to hanlim since August" | refused (01/08 to 02/10 = 63 days) |
| R16 | D | R4 then "and chin chun?" | carried window, no re-ask |
| R17 | D | R4 then "mocha only" | brand switch, same window |
| R18 | S | linked to six HANLIM ledgers, "my deliveries this month" | header `Customer: HANLIM TRADING SDN BHD (6 accounts)` |
| R19 | S | "delivery to hanlim account 1 this month" (after #1432) | header `Customer: HANLIM TRADING SDN BHD, Account 1` |
| R20 | D | "outstanding DO for SRTWT7443" | outstanding report, unchanged (not a DO list ask) |
