# UAC - Chatbot growth r1

Plan: `PLAN-chatbot-growth-r1.md`. Numbering: AC-9xx. Each criterion names its evidence
(pytest / vitest / world / agent-browser run). "Contact" = a Respond.io contact through
`/api/v1/external/chat/turn`; "dealer" = a contact with no field reveal grants.

## A. Data capabilities

- AC-901 A dealer asks "SRTWC8517 spec" and the EXISTING `crm_master_products_list` answer
  carries every populated spec key as `label: value unit`, ordered by registry `rank_weight`;
  with no attributes asked the reply shows today's four fields plus one compact "Specs:"
  line. No spec tool exists in the catalog. Evidence: pytest on a seeded product with 4
  spec keys asserting the picked tool name; corpus sample `chat-turn-spec-full`.
- AC-902 "wattage of SRTWC8517" (or any registry synonym) returns only that key, and a key
  the product lacks answers "no <label> recorded for <code>". Evidence: pytest, two cases.
- AC-903 The stock answer for a contact WITHOUT `inventory.sellable` is byte-identical to
  today's stock answer. Evidence: world replay stays green on every stock world.
- AC-904 The stock answer for a contact WITH `inventory.sellable` adds "Open SO" and
  "Sellable (on hand minus open SO)" per product, and reads "0 (oversold by N)" when open SO
  exceeds on hand. Evidence: pytest on seeded stock + 2 open SO lines.
- AC-905 "outstanding SO for <customer>" / "ordered but no DO" picks `crm_order_management_orders_list`
  with `order_status=so_outstanding` and lists open SO lines (qty ordered minus delivered
  > 0) with SO number, product, outstanding qty, order date; `group_by=product` and
  `group_by=date` render headed sections. No `sales_order` domain or tool exists. Evidence:
  pytest, three cases asserting tool and bucket; corpus samples.
- AC-905b "how many did <customer> take of <code>" (`include_summary=true`) renders the
  three-line pipeline SO outstanding / DO open / delivered (or the shape the owner picks on
  the review page); "list DO for <customer>" renders one bucket and no pipeline. Evidence:
  pytest, two cases.
- AC-906 A DO question with an angle ("DO by transporter this week", "how many DO for
  customer X", "open DO by customer") renders grouped sections or the summary line through
  the EXISTING `crm_order_management_orders_list` with `order_status=outstanding`; no new DO
  tool exists. Evidence: pytest asserting the picked tool name; corpus samples.
- AC-907 "PO for SRTWC8517" lists placed PO lines (ordered minus received > 0, line open) with
  PO number, outstanding qty, expected date; a dealer never sees the supplier; a contact
  holding `purchase_orders.supplier` sees it. Incoming is never subtracted from the PO qty.
  Evidence: pytest, two contacts, same seed.
- AC-908 "last in for SRTWC8517" returns the most recent received SPO allocation (qty,
  date, SPO number, warehouse) and `top_n=3` returns three; the date field label names the
  column used. Evidence: pytest on seeded allocations with `warehouse_arrival_date` and
  without (fallback). Phase 2 records the measured populated ratio on the prod copy in this
  file.
- AC-909 Every list tool in the plan (orders, PO placed, SPO last receipt) accepts `group_by`,
  `include_summary`, `sort`, `dir`, `limit`; an unknown `group_by` value returns 422 naming
  the allowed axes. Evidence: pytest parametrised over the three tools.
- AC-910 The parser emits `group_by` and `top_n`; "last 3 incoming" yields `top_n=3`,
  "by customer" yields `group_by=customer`. Evidence: replay on new captures.
- AC-911 `spo_allocation` is no longer in `DEFAULT_UNSUPPORTED_DOMAINS`; `goods_receive`
  still is. Evidence: pytest on `route.decide`.

## B. Cross-domain ladder

- AC-920 Stock question, code has no stock, incoming has rows: today's incoming block,
  unchanged text. Evidence: existing worlds green.
- AC-921 Stock question, no stock, no incoming, PO placed: reply reads "No stock and no
  incoming for X, but a PO is placed: {qty} expected {date}." then the escalate offer. The
  supplier is absent for a dealer. Evidence: pytest, world `stock-miss-po-rung`.
- AC-922 No stock, no incoming, no PO: "No stock, no incoming and no PO for X." then the
  escalate offer. Evidence: pytest.
- AC-923 The ladder is read from `system_settings.chatbot_crossdomain_ladder`; a tenant with
  `{"inventory": ["incoming"]}` never probes PO. Evidence: pytest with the setting patched.
- AC-924 A code that the probe never asked about is never declared absent (H62 guard kept).
  Evidence: `TestThirdCodeWithNoStockAndNoIncomingIsNamedWithEscalation` still passes.

## C. DOMAIN_SPEC

- AC-930 Every `DOMAIN_HINTS` value has a `DOMAIN_SPEC` row; every name in
  `CHATBOT_READ_ONLY_TOOLS` is claimed by exactly one domain; the parser schema enums equal
  the table. Evidence: guardrail pytest.
- AC-931 `AXIS_BY_DOMAIN`, `BARE_ENTITY_TYPE_BY_DOMAIN`, `DOMAIN_SWITCH_WORDS` and
  `DEFAULT_UNSUPPORTED_DOMAINS` have no independent literal; each is derived from the table.
  Evidence: pytest asserting identity with the derived views; grep in review.

## D. Dialogue state

- AC-940 A product asked at turn N with no product named at turn N+4 (TTL 3) does NOT carry;
  the reply asks which product. The same at N+2 carries. Evidence: two multi-turn worlds.
- AC-941 "that one" (anaphora) with the product slot dead asks which product; the trace holds
  a `decay` line naming the slot, age in turns and reason. No wall-clock TTL exists.
  Evidence: pytest.
- AC-942 "incoming?" after a stock answer keeps the products and switches the domain;
  "what about Y" after that replaces the product and keeps `incoming`. Evidence: world.
- AC-943 "别的" / "another one" clears product, customer, date and domain, keeps tier and
  brands. Evidence: pytest per rule `reset_on_topic`.
- AC-944 A picker of 3 products is offered; "2" resolves to the second frozen option even if
  the product list would resolve differently today; "2" again after the pick, with no open
  question alive, is treated as a new message, not a pick. Evidence: world.
- AC-945 Escalate offer, then "yes" runs the escalation lane; "no" renders the declined copy;
  "SRTWC8517 stock?" instead of yes/no leaves the offer unanswered, answers the stock, and
  the offer is cleared with a trace line after its TTL. Evidence: three worlds.
- AC-946 After a DO result, "for customer ABC instead" replaces the customer slot and reruns
  the DO tool; "last month" then replaces only the date window. Evidence: world.
- AC-947 A quoted reply to an older picker resolves against THAT message's frozen options,
  not the alive open question. Evidence: pytest with `replyTo.id`.
- AC-948 Issue #708: a numbered pick over a partial-miss roster keeps the already-resolved
  siblings. Evidence: the existing #708 test passes against the `product_pick` handler.
- AC-949 Parser v3 never re-emits an entity that is absent from the current message
  (`current_message` is true on every emitted entity across the corpus replay). Evidence:
  replay assertion.
- AC-950 `output_exchange.py` no longer contains rules K2, K4, the switch-word override,
  `_query_brands_carried`, `_tier_carried`, or the date / attribute / `is_active` carry arms;
  each has a named function in `dialogue/focus.py` with its own test. Evidence: grep in
  review + test names.
- AC-951 `SessionVars` still carries `pending`, `dym_offer`, `selection_context` and
  `picker_*`, so every existing world grades. **Amended 7 Sep 2026 during slice B4: the
  mirror runs the other way.** `open_question` is DERIVED from those keys
  (`dialogue/open_question.from_state`) rather than them from it, because making
  `open_question` authoritative means porting the eight-rule did-you-mean lifecycle,
  `_offer_carry` and `_picker_carry` onto one TTL - a behaviour change on the lane that
  already changes reply semantics, against a corpus that cannot grade it until it is
  re-derived. The criterion's purpose is unchanged and met: every existing world grades.
  Inverting the mirror is the named follow-up. Evidence: `test_worlds.py` green (87 graded,
  126 skipped, identical to before the slice) plus the three field-scoped divergences
  (`pending`, `focus`, `open_question`) registered with their reason in
  `tests/chatbot/divergences.py`.
- AC-952 Parser v3 is a new registry version, promoted only after a 3 to 7 day shadow window
  with branch parity 99%+ and reply parity 97%+ on turns with no open question. Evidence:
  shadow report attached to the PR.
- AC-953 An entity with `confident=false` never replaces an alive product slot without a
  picker. Evidence: pytest.

## E. Field reveal

- AC-904b Sellable subtracts open SO only; an open DO (created, not delivered) does not
  reduce sellable a second time. Evidence: pytest with one open SO line and one open DO.
- AC-960 `contact_field_reveals` exists (migration chained on main head); unique on
  (contact, key); default absent = hidden. Evidence: migration test.
- AC-961 `check_access` returns `attributes` = the contact's granted keys and
  `all_attributes_allowed=false`; a contact with no rows gets `[]`. Evidence: pytest.
- AC-962 `output_structurer` drops any field or summary item whose `restricted` key is not
  granted; the MCP envelope itself is unfiltered. Evidence: pytest on both consumers.
- AC-963 Contact detail, Access tab, "Field reveals" checklist lists the keys from
  `GET /system/chatbot/field-reveal-keys` with labels, all off by default; ticking saves,
  unticking confirms first. Evidence: vitest + agent-browser run via sidebar.
- AC-964 A new `restricted=` field in a presenter appears in the checklist after catalog
  sync with no FE change. Evidence: pytest on the sync writing `mcp_tools.restricted_fields`.
- AC-965 375px and 1280px: the checklist is usable and not clipped. Evidence: agent-browser
  screenshots.

## F. Trace view

- AC-970 `GET /system/chatbot/turns/{id}` returns `trace_detail` with stages, parse, decay,
  open_question, focus, tool, crossdomain, reveals and session diff; envelope truncated at
  8 KB with a truncation marker. Evidence: pytest on a real turn through the engine.
- AC-971 Every focus rule that fires writes one `focus` trace entry naming the rule, slot,
  before and after; every decayed slot writes one `decay` entry. Evidence: pytest asserting
  the entries for the AC-940 to AC-946 worlds.
- AC-972 The chat-history list opens a `TurnDetailDrawer` per row showing the sections in
  the order above, collapsible, wide JSON scrolling inside its own container, no horizontal
  page scroll at 375px. Evidence: vitest + agent-browser run.
- AC-973 A failed turn shows the failing stage first with its error text. Evidence: vitest.

## G. Owner console pass

- AC-990 The data lane hands off with a console-pass artifact in the S7 Console Pass shape:
  sanity subset (cases 1 to 20, 23 to 27) plus a new section of about 20 cases covering
  every capability in section A and the ladder in section B, pre-filled with the clone
  results, zero real egress. Evidence: the artifact link in the PR.
- AC-991 The dialogue lane hands off with the full 70 re-run plus the six owner worlds as
  console cases; every section 2 case and every multi-turn case marked by the owner; a
  fail there blocks parser v3 promotion. Evidence: artifact link + owner marks in the PR.
- AC-992 The trace UI lane needs no console pass; an agent-browser evidence run via the
  sidebar stands in. Evidence: the run recorded per `documentation/agents/browser-verification.md`.

## H. Guardrails carried forward

- AC-980 No answer LLM anywhere in the business lane (D1); grep for provider calls under
  `lanes/business/` returns none. Evidence: guardrail pytest.
- AC-981 `CHATBOT_READ_ONLY_TOOLS` equals the catalog's read-only set including the new
  tools. Evidence: existing CI assertion extended.
- AC-982 Dry-run turns (`is_test`) write zero rows to `contact_field_reveals`,
  `chat_histories` and `respond_contacts.session_vars`. Evidence: existing D14 test extended.
