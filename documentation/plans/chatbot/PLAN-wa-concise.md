# PLAN - WhatsApp replies, one fact per line (WA-CONCISE)

Status: planned, awaiting owner approval of behaviour card v3 (feature track M: wording on an
existing surface, no migration, no auth/RBAC, no new ingest).

Owner, 3 Oct 2026: "our messages often contain duplicate info and can be more concise". Card v3
(`documentation/mockups/wa-concise/index.html`) after owner notes on v1 and v2: product code as a
bold heading, then one fact per line as `Label: value`, no separators, no repeated facts.
UAC: `wa-concise-acceptance-criteria.md`.

## Owner answers (card v1/v2, 3 Oct 2026)

| # | Question | Answer |
|---|----------|--------|
| Q1 | Build which rules | everything |
| Q2 | Hide zero locations | no; zero locations print as today, `hide_zero_locations` stays a per-contact toggle, no migration |
| Q3 | Wording for "nothing on order" | `PO: none` |
| Q4 | Footer | `_Updated dd/mm/yyyy hh:mm_` |
| Q5 | List Price / Dimensions on product lists | only when the customer asks for price or dimensions |
| v2 note | `·` separators | rejected: "I need things to be line by line", "No dot" |

## Premise check (measured, dev copy `sorento_cagent_stack`, outgoing 1 Aug to 18 Sep 2026)

12,607 replies, 7.84M chars. Billed messages barely move (12,938 to ~12,931 at WA-MSG-TRIM's
3900 split): this lane is readability. Pattern counts are on the card.

## Where the text is built (render map, verified on main 0f49c9db9)

- Single-domain list replies: `lanes/business/fetch.py::output_structurer` (2604). Intro 2961-2964,
  rows `_item_line` 3015-3041 (flat loop 3098-3101, grouped 3052-3062), footer 3181-3183 and the
  re-slot at 3278. Out as `response` -> `turn_runtime.envelope_of` `lane_text` (3958) ->
  `turn/compose.py::compose` verbatim (400) -> `Answer.text` -> `engine._reply_of` (6237). n8n only
  sends; the presenters.py:1403 comment about n8n walking `fields` is stale.
- Incoming miss with stock (cross-domain): head from `answer.py::not_found_error_message`
  ("Here's what you want" 3690, "But no ... matched these." 3723-3728); block from
  `answer.py::crossdomain_render` (851; rows 987, lead 1001-1004, `only_other_note` 1067-1069,
  `nothing_note` 1085-1096); PO rung `_apply_crossdomain_rung` (1330, 1400-1451); joined by
  `tail/compose.py::crossdomain_compose` (63; miss branch 122-151, hit branch 100-121) via
  `answer_bridge._apply_crossdomain_render` (1546).
- Order scope header: `tail/scope_block.py::search_scope_header` (252-296), prepended by
  `answer_bridge.apply_scope_block` (116-163).
- Footer consumers: `turn/compose.py:451` (rpartition), `answer.py:1564` regex (used 2100).
- Product list "Not defined": `presenters.py:1056-1059`; asked-attribute signal
  `semantic_input.requested_attributes` (fetch.py:2726-2739) + `_names_a_base_property` (1770).
- Positional picks resolve only against an open `Pending` (`turn/decide.py::picked_positions` 237);
  a plain stock list arms none, so grouping detailed rows per product is pick-safe.

## Slices (one lane, one PR, one coder continued across slices)

1. S1 stock lines + intro + footer (fetch.py `_item_line` for stock result types, intro
   suppression, footer + its two consumers).
2. S2 cross-domain: incoming miss / stock miss blocks in the per-product line form, the
   `not_found_error_message` head dropped when the block heads every asked code, the PO rung as
   `PO: none` / `PO: placed`.
3. S3 incoming rows and order rows in the line form; scope header dropped for one named order.
4. S4 product list: List Price / Dimensions only when asked.

Not touched: dealer availability lines (presenters.py:1464-1490), the LOCKED escalation phrase
(tail/compose.py:96-98), the refer sentence, every other tool's rows, Respond.io auto messages,
complaint/SLA notices, one reply per inbound.

## Tests

Red-first: the tester writes exact before->after string tests from the UAC (pytest; MCP presenter
tests where the presenter changes) as ONE `test(red):` commit touching only tests, run and posted
as red proof; then the coder makes them green and updates the pinned replay texts
(`tests/chatbot/replay_turns/**` `expected.text`) and existing exact-string assertions the new
format changes, each listed in the PR. Kill test after green. Reviewer once; browser pass via the
chatbot console on the crew test copy (hand test).
