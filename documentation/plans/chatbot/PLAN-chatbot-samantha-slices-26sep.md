# PLAN: the Samantha case, slices 1 to 11 (issue #1262)

Status: fix lane round 2 done (reviewer pass at 4719a829: B1, S1 to S4, N1 to N6 addressed), PR open. Track: full (migration for the prompt versions, MCP tool
argument, more than 300 lines). UAC: `chatbot-samantha-slices-26sep-acceptance-criteria.md`.

Owner ruling 26 Sep ~11:05Z: "samantha one all also need to fix bro" - every slice of the
explainer is built in this one PR, except F7 / slice 12 (ordering), which a separate lane owns.
Slice 10 (attachments) was dropped by ruling 2 (26 Sep ~06:40Z). Standing rulings: the parser
owns quantity (no regex strip); a real brand filter fed by the live brand list; no rigid rule
that bypasses the parser; no waiting windows or timers.

No frontend change: Phase 1 (FE mock) and browser verification do not apply. The chatbot's
equivalent of a browser pass is the console check (`documentation/agents/chatbot-verification.md`).

## Build order and seams

Code anchors are the scout's (issue #1262); lines may have drifted a little on main.

### Group A: wrong or unsafe replies

| Slice | Finding | Change |
| --- | --- | --- |
| 7 | F1b label | `turn/reconcile.py` kind-pick options carry `code: raw` (and the kind in `entity_type` / `payload.kind`); `turn/apply.py` pick arm builds the entity from the option's code, never from the label. |
| 2 | F1c | One shared `is_uuid` check at every customer-id write and carry: `turn_runtime._spec_row` + `candidates_by_kind` (never promote `canonical_code` into `uuid`), `lanes/business/__init__._outstanding_filters_from`, `fetch._outstanding_filters_from_ctx`, `turn/apply._settle_question_subject`, `turn_runtime` outstanding carry, the `fetch.py` copies into `customer_ids`. A stored customer that is unusable is said, never "Customer: all". |
| 1 | F2 | `MCPRuntimeClient.call_tool` raises on `isError` (the AI assistant loop keeps seeing the text through its own exception handling); `_outstanding_report_output` never passes a non-envelope string as a result; compose replaces any "Error executing tool" text with the neutral fetch-failure line. |
| 6 | F6a | The counted-set header lives only on `header_override`; it is stripped from the lane text when `counted_set` is false. |
| 11 | F8 | Audience-aware offer: profile tier `office` gets no bot-initiated escalation offer on a miss (composer offer, ladder offer, answer-lane offer sites); no audience gets an offer on a turn that asks a clarifying question. Dealer / end user keep R6. |
| 8 | F1b siblings | A kind pick applies the unambiguous entities before asking; one pick per ambiguous token (the rest ride on the pending and are asked in turn). |

### Group B: recall

| Slice | Finding | Change |
| --- | --- | --- |
| 4 | F3 | `turn/decide.py`: an outstanding REFINE requires the verdict's `domain_hint` to be absent or equal to the offer's domain, else NEW_ASK. A verdict with `domain_in_message` naming another domain closes the outstanding offer (T6 half). Both read the parser's own output. |
| 5 | F4 | Parser schema: per-entity `quantity`. Prompt: a leading / trailing "xN" / "N pcs" is the quantity, never part of the raw (new unlabelled version via migration). `media_extract/service.py`: caption and codes on separate lines, per-line quantities as text beside each code. The reply shows the parser's quantity beside the code. No regex. |
| 3 | F5 | `gate._CODE_SHAPED` accepts one leading letter; `build_set_header` drops "Showing N"; the silent-company miss line caps its subject at 5 codes; the paging ban is written in `documentation/reference`. |

### Group C: brand

| Slice | Finding | Change |
| --- | --- | --- |
| 9 | F1a | Round 3 section 6 steps 1 to 3: the engine reads `brands` (the `models/product.py` `Brand`, chosen on purpose over the projects model) for the contact's companies in the session it already holds, and `build_user_block` writes one `Known brands:` line at both parser call sites; the prompt refers to that line. Step 4: a brand entity whose name or code matches a live brand resolves to those brand ids inside the chatbot (no fan-out to customer / transporter); `order` allows a brand; `outstanding_report` + route + MCP tool take `brand_ids` (Product.brand_id); the orders list / summary tools that take `product_ids` take `brand_ids` too. |

## Rulings assumed (owner can overrule)

1. **F3 T6 half:** a turn whose parser verdict names another domain (`domain_in_message` with a
   `domain_hint` different from the open outstanding offer's) closes that offer.
2. **F8 staff signal:** `respond_contacts.chatbot_profile.tier == "office"` marks staff.
3. **F8 staff miss:** staff get no bot-initiated escalation offer on a miss; they can still ask
   to escalate explicitly.
4. **F8 dealer vs R6:** R6 ("a stock question is always suggested to the warehouse team")
   stands for dealers and end users; "dealer never to warehouse" is not built.
5. **F8 clarify first:** no audience gets an escalation offer on a turn that asks a clarifying
   question.
6. **F1b queue:** several ambiguous tokens are asked one pick at a time, first token first.
7. **F1a resolver:** the brand resolves inside the chatbot against the live list; the shared
   resolver's order-domain brand fan-out is left in place for n8n / MCP callers.
8. **F1a other reports:** "other order reports" = the orders list and orders summary tools.
9. **F5 cap:** above 5 codes the miss line says "the N products searched".
10. **Prompt versions:** the amended parser prompt ships as a new unlabelled version; the owner
    promotes it (one label move), as for migrations 475 / 480 / 490 / 521.
11. **Kind-pick order (round 2, N1):** options are ordered by the resolver's hit count per
    kind, most first, ties alphabetical.
12. **Quantity lifetime (round 2, S1 nit):** the parser's quantity belongs to the message that
    typed it; a carried product row drops it (`turn/state.py::focus_from_wire`).

## Tests

One RED test per owner turn per slice, from the scout's named tests, in
`sorento_crm_backend/tests/chatbot/test_samantha_26sep_*.py` (Postgres fixture where a DB is
needed; pure units otherwise). Kill test per slice in Phase 3. The replay corpus
(`tests/chatbot/test_turn_replay.py`, `replay_turns/`) and `tests/chatbot/` stay green.
