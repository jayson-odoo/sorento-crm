# UAC: an open ideation draft keeps short and question-shaped turns in the ideate lane

Plan: `PLAN-chatbot-ideation-draft-keeps-lane.md`
Issue: #1178

"Open draft" everywhere below = the session's five-key `ideation` pointer is a dict carrying a
`draft_id` (`{"draft_id": "ZZT-draft-1", "status": "collecting", ...}`), and the focus carries
`domains: ["ideate"]` unless an AC says otherwise. "Branch" = `route(plan)` over
`apply(state, verdict, policy)` with `tests/chatbot/_turn_helpers.build_policy()`; the verdict
is the parser's structured emission and never the message text.

Pure seam, `[BE]`, `sorento_crm_backend/tests/chatbot/test_ideation_draft_keeps_lane.py`:

- **AC-1 a question about the field stays in ideate.** Open draft; verdict
  `message_type: clarification`, `domain_hint: null`, no entities. Branch is `ideate`.
- **AC-2 the parser's own ideate domain is honoured on a question.** Open draft; verdict
  `message_type: clarification`, `domain_hint: "ideate"`, `intent_hint: "submit_idea"`. Branch
  is `ideate` (today: `clarify_menu`).
- **AC-3 a bare confirm stays in ideate.** Open draft; verdict `message_type: confirmation`,
  `is_affirmative: true`, `domain_hint: null`. Branch is `ideate` (today: `low_signal`).
- **AC-4 a hesitation stays in ideate.** Open draft; verdict `message_type: casual`,
  `domain_hint: null` ("dunno lah, can skip this one?"). Branch is `ideate`.
- **AC-5 the rule is named on the trace.** For AC-1 the plan's `trace.rules_fired` contains
  `open_idea_draft_keeps_lane` and `trace.lane` is `None`.
- **AC-6 no draft, nothing changes.** Same verdicts as AC-1 and AC-3 with `ideation: null`
  (and with a pointer carrying no `draft_id`). Branches are `clarify_menu` and `low_signal`
  exactly as today.
- **AC-7 a decisive domain switch still wins.** Open draft; verdict `message_type:
  business_query`, `domain_hint: "inventory"`, `domain_in_message: true`, one product entity.
  Branch is `business_query`, plan domains `["inventory"]`.
- **AC-8 an escalation still wins.** Open draft; verdict `message_type: escalation`. Branch is
  `out_of_scope`. Open draft; verdict `message_type: request_for_help`, `domain_hint: null`.
  Branch is `out_of_scope` (the escalation lane).
- **AC-9 a standing subject in another domain is not pulled back.** Open draft but focus
  `domains: ["inventory"]` (the customer asked stock mid-idea); verdict as AC-3. Branch is
  `low_signal`, unchanged: the draft resumes by a fresh ideate turn.

Engine, `[BE]`, Postgres (`session_factory`, the `tests/chatbot/test_engine.py` fixtures), same
file:

- **AC-10 "what do you mean impact?" reaches the ideation tool.** A seeded contact whose
  session carries an open draft and `focus.domains: ["ideate"]`; the parser stub answers a
  `clarification` verdict with no domain; `lanes.ideate.call_ideation_tool` is stubbed. After
  `engine.run_turn`, `result.branch_kind == "ideate"`, the tool was called exactly once with
  `message_text == "what do you mean impact?"` and the seeded pointer as `session_vars.ideation`.
- **AC-11 "confirm" reaches the ideation tool.** Same seed; the parser stub answers a
  `confirmation` verdict (`is_affirmative: true`, no domain). Same assertions with
  `message_text == "confirm"`.

Console, `[T]`, not collected by pytest:

- **AC-12 the two review turns as one conversation.**
  `tests/chatbot/console_cases/2026-09-24-ideation-draft-keeps-lane.yaml` injects an open draft
  through `previous_conversation_state`, then sends "what do you mean impact?" and "confirm";
  each turn expects `branch_kind: ideate` and a reply that is not the low-signal greeting. Each
  turn carries a `parser:` block so `--mock-parser` grades the head deterministically; without
  the flag the same file exercises the live parser.

- **AC-13 existing suites green.** `tests/chatbot/test_s3_canned_and_ideate.py`,
  `test_rearch_port_route_unit.py`, `test_rearch_s2_apply_is_pure.py`, `test_s4_casual_lane.py`
  and `test_engine.py` pass unchanged.
