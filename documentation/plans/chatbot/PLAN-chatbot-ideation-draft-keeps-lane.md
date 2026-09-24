# PLAN: an open ideation draft keeps short and question-shaped turns in the ideate lane

Status: small fix track, PR open (#1185), fix round 1 addressed
Plan created: 2026-09-24T08:35:54Z
Domain: chatbot / ideation intake
Issue: #1178 (evidence: PR #1176, `documentation/plans/ideation/REVIEW-ideation-flow-ux-24sep.md`
findings 2 and 3)
UAC: `chatbot-ideation-draft-keeps-lane-acceptance-criteria.md`

## Problem (measured on origin/main, 028083e2)

The review's Run 1 turn 3 ("what do you mean impact?") left the ideate lane for `clarify_menu`
and answered with the eight-topic domain menu; Run 2 turn 3 (a bare "confirm", the very word
the intake's own template asks for) left it for `low_signal` and answered "Hi! How can I help
today?". Both happened while the contact was mid-draft.

Reproduced deterministically on the pure seam (`turn/apply.py::apply` + `turn/route.py::route`,
no LLM, focus carrying `domains: ["ideate"]`):

| verdict                                              | branch       | why                                                            |
| ---------------------------------------------------- | ------------ | -------------------------------------------------------------- |
| `clarification`, `domain_hint: null`                 | clarify_menu | `_lane` returns `clarification` before the domain is consulted |
| `clarification`, `domain_hint: "ideate"`             | clarify_menu | same: the verdict's own domain is ignored                      |
| `confirmation`, `is_affirmative: true`, no domain    | low_signal   | `_is_idle_chat` empties the carried `ideate` focus, lane casual |
| `confirmation`, `domain_hint: "ideate"`              | ideate       | works                                                          |
| `casual`, no domain                                  | low_signal   | idle chat, as above                                            |

Diagnosis. Finding 2 is the HEAD overriding the verdict: `_lane` sends every
`clarification`-typed verdict to `clarify_menu` regardless of the domain it carries, and
`route()` reads `trace.lane` before it reads `"ideate" in plan.domains`, so even a verdict
that honoured the prompt's IDEATION CONTINUATION rule (`domain_hint: ideate`) lands on the
domain menu, which `route.py`'s own docstring reserves for "a turn with no domain at all".
Finding 3 is both halves: the parser emitted a domainless `confirmation` (the prompt's
continuation rule is keyed on "the previous turn's domain was ideate", and the head tells the
parser only "Current subject: domain ideate.", nothing about a draft being open), and the head,
which does know a draft is open (the five-key `ideation` pointer is loaded on every turn), never
reads it: `turn/state.py::State` has no draft field, so `apply()` treats a domainless
confirmation as idle chat and drops the carried `ideate` domain. In both cases the head has the
fact the verdict lacks and does nothing with it.

## Fix (one seam, deterministic, after the parse)

The open draft is state, so `apply()` reads it as state, the same way it reads the open
question:

1. `turn/state.py::State` gains `ideation: Any = None`; `turn_runtime.load_state` fills it from
   the five-key `ideation` pointer (`session_state.five_keys`, both session shapes).
2. `turn/apply.py`: after `_lane`, one rule. When the contact's session carries an open idea
   draft (a pointer with a `draft_id`; the intake itself pops the pointer on `complete` /
   `duplicate`, `ideation_turn_service._TERMINAL_STATUSES`), and the verdict placed the turn on
   the `clarification` or `casual` lane, and the message names nothing of its own (no other
   `domain_hint`, no `asks` outside ideate, no current-message entity, no `domain_in_message`,
   none of the subject signals `_IDLE_CHAT_DISQUALIFIERS` already lists), and the standing
   subject is the idea or nothing (`focus.domains` all `ideate`), and the message did not answer
   an open question, then the turn is planned as `ideate`: `domains = ["ideate"]`, `trace.lane =
   None`, rule `open_idea_draft_keeps_lane` on the trace. `route()` then reaches `ideate` the way
   it already does for a verdict that named the domain.

What the rule never touches: a decisive domain switch (the parser named another domain, the
prompt's own "asking stock/ETA/price mid-idea switches domain normally"), an escalation or a
request for a human (`_lane` returns `escalation` before this rule runs), a turn that answers an
open roster, and a contact whose standing subject has already moved to another domain (the draft
then resumes by a fresh ideate turn, again the prompt's own wording). No keyword is read; every
input is the parser's structured verdict or persisted state. The parser prompt is unchanged.

Not done here, recorded as the trigger for a second seam: the parser's user block still says
nothing about an open draft. If live verdicts on draft turns keep naming another domain wrongly
(a switch the customer did not ask for), the fix is a "Pending: the assistant is collecting an
idea" line in `head/parser.py::build_user_block`, beside the existing `pending_kind` line.

## Files

- `sorento_crm_backend/app/services/chatbot/turn/state.py` - the `ideation` field.
- `sorento_crm_backend/app/services/chatbot/turn_runtime.py` - `load_state` fills it.
- `sorento_crm_backend/app/services/chatbot/turn/apply.py` - `open_ideation_draft`,
  `_continues_open_draft`, the rule.
- `sorento_crm_backend/tests/chatbot/test_ideation_draft_keeps_lane.py` - AC-1 to AC-11 (pure
  apply+route, plus two engine turns on Postgres with a seeded open draft).
- `sorento_crm_backend/tests/chatbot/console_cases/2026-09-24-ideation-draft-keeps-lane.yaml` -
  the two review turns as one conversation over an injected open draft, gradable with
  `--mock-parser` (deterministic) or against the live parser.

## Track

Small fix track: backend only, under 300 changed lines, no migration, no auth/RBAC change, no new
ingest surface. One coder, tests first (red shown before green), one reviewer, no browser pass
(no screen changed), `security-reviewer` not run (diff outside its surface).

## Fix round 1 (reviewer pass at 5466562b)

Two deviations from the version the reviewer read, both recorded here per coder.md ("update the
contract doc + adjust both sides in the same change"):

- **S1 narrowed the rule's message types (AC-4 superseded).** `_DRAFT_ABSORBS` keys on the LANE
  `_lane()` returns, and `_lane()` sends `casual`, `unknown` and `confirmation`-typed turns to the
  same "casual" lane - so the rule as written absorbed idle chat too, and the draft pointer has no
  expiry. Added `_DRAFT_MESSAGE_TYPES = {"clarification", "confirmation"}`, checked beside the lane
  in `_continues_open_draft`. AC-4 ("a hesitation stays in ideate") is superseded: a `casual`-typed
  turn over an open draft now routes exactly as it would with no draft (`low_signal`), matching the
  ruling's own wording ("short AND question-shaped turns" - confirm is short, a question is
  question-shaped; a hesitation is neither).
- **S3 dropped the `reference_positions` exemption.** `_DRAFT_OWN_KEYS` no longer carves it out;
  the plan's own wording ("none of the subject signals `_IDLE_CHAT_DISQUALIFIERS` already lists")
  already had no carve-out, and no test exercised the media-menu justification the code comment
  gave for it. An actually-open roster's answer is unaffected - it is caught earlier by the
  `decision.answers` guard.

B1's AC-7b (parametrized, one case per guard, both a clarification and a confirmation verdict) and
S2 (an `ideate` row with `intents: ["submit_idea"]` added to the test policy fixture,
`_turn_helpers.py`) are additive - no behaviour change, coverage only. N1 and N2 are additive tests
pinning existing behaviour. N3 and N4 are the reviewer's own call / pre-existing and out of scope.
