# TRACE-ENTITY-TOOL browser pass (agent-browser 0.27.0, headless, cloud sandbox), 11/11/2026

Branch `claude/trace-entity-tool-display-3hnvf8`, PR #2344. Sandbox DB `sorento_browse` (bootstrapped with
`scripts.bootstrap_env`), seeded by `harness/seed_browse.py` (all invented): a superadmin and three turns for test
contact ZZT-900001, "hi", "srtwc286" (stock check, trace shaped like turn #8322: named stock tool event 157 ms, then
the fetch step's bare `{"domain"}` event, a `resolve` event, a span pass with the code span `skipped`), "thanks".
Backend uvicorn :8000 (`SORENTO_ENV_FILE=.env.browse`), frontend `npm run dev` :3000. Signed in, then System >
Messaging > Chat History by sidebar clicks; the turn opened through `?turn=<id>` (the Chatbot Console's own trace link,
since console/seeded turns write no WhatsApp message row).

| # | Check | Screenshot | Result |
|---|---|---|---|
| 1 | Stock turn: Entity match open, `srtwc286 -> SRTWC286`, badge "all words" | 01 | PASS |
| 2 | Stock turn: Tool open without a click, name `crm_inventory_stock_balance_list`, ms 157, despite the bare domain event after it | 01 | PASS |
| 3 | Span pass: code chip badge reads "sent to the code lookup" | 02 | PASS |
| 4 | Stock turn Order: Ran after `#1 ... "hi"`, Next `#3 ... "thanks"` | 01 | PASS |
| 5 | Turn "hi": Ran after "First message in this conversation" | - | PASS |
| 6 | Turn "thanks": Next "No later message yet" | - | PASS |
| 7 | 375px: document scrollWidth 375 = clientWidth 375, sections readable | 03 | PASS |
| 8 | Console: no errors | - | PASS |

The `resolve` event on a real engine turn (not seeded) is proven by
`tests/chatbot/test_trace_entity_tool_engine.py` (real resolver over a seeded product, stock tool doubled).
