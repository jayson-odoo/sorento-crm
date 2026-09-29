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
- **AC-4 a hesitation does NOT stay in ideate (superseded, fix round 1, S1).** Open
  draft; verdict `message_type: casual`, `domain_hint: null` ("dunno lah, can skip this
  one?"). Branch is `low_signal`, unchanged from the no-draft baseline. Reviewer S1
  (PR #1185): `_lane` sends `casual`, `unknown` AND `confirmation`-typed turns to the
  same "casual" lane, so keying the rule on the lane (rather than the message type)
  absorbed idle chat too - and the draft pointer has no expiry, so a contact who
  abandoned a draft and later said "hi" would have had it resurrected. Narrowed to the
  two message types the ruling actually names, `clarification` and `confirmation`
  (`_DRAFT_MESSAGE_TYPES`); a `casual` or `unknown` turn over an open draft now routes
  exactly as it would with no draft at all.
- **AC-5 the rule is named on the trace.** For AC-1 the plan's `trace.rules_fired` contains
  `open_idea_draft_keeps_lane` and `trace.lane` is `None`.
- **AC-6 no draft, nothing changes.** Same verdicts as AC-1 and AC-3 with `ideation: null`
  (and with a pointer carrying no `draft_id`). Branches are `clarify_menu` and `low_signal`
  exactly as today.
- **AC-7 a decisive domain switch still wins.** Open draft; verdict `message_type:
  business_query`, `domain_hint: "inventory"`, `domain_in_message: true`, one product entity.
  Branch is `business_query`, plan domains `["inventory"]`.
- **AC-7b every guard, one at a time (added fix round 1, B1).** Open draft, focus
  `domains: ["ideate"]`. Parametrized over both a `clarification` and a `confirmation`
  verdict, each carrying exactly one of: a current-message entity; `domain_in_message:
  true`; `asks: [{domain: "inventory", intent: "check_stock"}]`; a non-ideate
  disqualifier (`requested_attributes`); `intent_hint: "check_stock"` with no domain
  hint; an answer to an open roster (a `product_pick` pending plus `is_affirmative:
  true` - `decide()`'s "affirmative" path, which isolates the `decision.answers` guard
  without also tripping the AC-7d disqualifier a positional pick would). For every
  case, the branch with the draft open equals the branch computed for the identical
  verdict with no draft, and `open_idea_draft_keeps_lane` is not in
  `trace.rules_fired`.
- **AC-7c the ideate domain's own intent passes for real (fix round 1, S2).** Same as
  the `intent_hint: submit_idea` case the original plan measured, but against a policy
  built with a real `ideate` row (`intents: ["submit_idea"]`, matching
  `policy_rows.py:273`) rather than the fixture's previous no-`ideate`-row gap. Branch
  is `ideate`, `open_idea_draft_keeps_lane` fires. Clarification only: the same intent
  on a confirmation verdict disqualifies `_is_idle_chat` first and reaches `ideate` by
  the ordinary carried-focus path instead, which is a real difference worth keeping
  visible rather than a second case for this guard.
- **AC-7d a stray position with no roster open still names something (fix round 1,
  S3).** Open draft, no pending; `clarification` verdict carries `reference_positions:
  [1]` and nothing else. Branch equals the no-draft baseline (the rule's
  `reference_positions` exemption is dropped - it does not answer any actually-open
  roster, so it is read like every other `_IDLE_CHAT_DISQUALIFIERS` key). Clarification
  only: `reference_positions` is itself one of `_is_idle_chat`'s own disqualifiers, so a
  bare confirm carrying it never reaches the "casual" lane at all (`_lane` sees a
  carried, non-idle `domains` and returns a business lane); the guard this AC pins is
  reachable only through `clarification`, which `_lane` sets from the message type
  alone.
- **AC-7e the domain_hint guard's second line of defence (fix round 1, N1).** Open
  draft; verdict `message_type: clarification`, `domain_hint: "inventory"`. Branch
  equals the no-draft baseline for the same verdict. (`_focus_rules` already moves
  `focus.domains` to `["inventory"]` off `domain_hint` before this rule runs, so the
  focus-axis guard alone would already reject it; this case pins that the explicit
  `domain_hint is not None` guard agrees.)
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
- **AC-11b the flat five-key session shape carries the pointer too (fix round 1, N2).**
  Same as AC-10, but the contact's `session_vars` is seeded with the five keys directly
  at the top level (no `variables` wrapper) rather than through the n8n-nested shape
  AC-10/AC-11 already cover. Pins `turn_runtime.py:325`'s "both session shapes" claim.

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
