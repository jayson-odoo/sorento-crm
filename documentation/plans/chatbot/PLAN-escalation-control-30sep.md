# PLAN: escalation control per contact / access type (ESCALATION-CONTROL)

Status: implemented on the lane branch, in review (PR #1406). Track: full (migration). Owner request 30 Sep 2026.

Owner: "we need to be able to control each contact that they cannot access the escalation:
cannot force escalate, won't be offered escalation; this is for dealer".

## Journey
A dealer contact chats with the bot. When the bot cannot answer, it does NOT offer customer
service and does NOT show the member picker. If the dealer asks for a person, or replies "yes"
to an old offer, the bot replies "Please refer to your salesman." (owner ruling 30 Sep 2026:
the existing `turn/task.py::REFER_TO_SALESMAN` line, no salesperson name, per REFER-SALESMAN
AC-RS02) instead of handing off. Staff flip the switch per contact (inherit / allow / block)
or per access type.

## Design
- Migration `esc1_0001_escalation_allowed`: `contact_access_types.escalation_allowed` BOOLEAN
  NOT NULL DEFAULT TRUE, seeded FALSE for EVERY dealer type (owner, 30 Sep 2026: "all dealer
  block escalation by default"; dev has Sorento, Cabana, Mocha and NL Dealer). The table has no
  kind or tier column (`app/models/access.py::ContactAccessType`) and the chatbot's own tier
  reading parses the name (`lanes/business/tier_gate.py::parse_level`), so a dealer type is one
  whose name's last word is "Dealer", any case (`name ~* '(^|\s)dealer\s*$'`).
  `respond_contacts.escalation_allowed` BOOLEAN NULL (override, NULL = inherit).
- `app/services/escalation_policy.py::resolve`: contact override wins, else the contact's
  access types merged PERMISSIVELY by `merge`: allowed when ANY type allows, blocked only
  when EVERY type blocks, else (no types) allowed. Owner hand test 30 Sep 2026 (Mr Loo,
  respond 487555417, Sorento/Mocha/Cabana Office + Dealer + End User): "why doesn't it
  allow to escalate to human?". The first cut copied `stock_visibility.
  _merge_access_type_rows`'s most-restrictive rule and barred him; reversed. The deciding
  type (first in catalogue order among the allowing types, else among all) is shown on the
  Chatbot tab: "Inherited: allowed via Sorento Office".
- `turn_runtime.load_profile` puts it on `Profile.escalation_allowed` (fail-open on a read error).
- `turn/state.py::offers_escalation(profile)` replaces `is_staff_profile` at every offer gate
  (composer offer, cross-domain ladder rung, miss composer, suggest-offer `_cont`, CS roster
  combine, silent-company offer). `escalation_barred(profile)` gates the barred-only paths.
- Forced path: `turn/apply.apply` closes an open escalation offer on entry (a stale "yes" has
  nothing to accept), withholds any offer it would ask or carry, and `_lane` returns
  `escalation_barred` (routed as `out_of_scope`, no new wire branch kind). The engine guards
  in front of `_run_escalation_arm` and answers with the referral.
- Backstop: `escalation_control.strip_offers` runs in `engine._run_answer` and `run_tail` for
  a barred contact, so an offer sentence, routing picker or armed question from any composer
  is removed and the referral stands in its place.
- UI: Contact > Chatbot "Can escalate to customer service" select (clearable = inherit,
  placeholder names the inherited value); access-type editor checkbox.

See `escalation-control-acceptance-criteria.md`.

## Grill (post-hoc, 30 Sep 2026)

The feature skill's grill (step 2) was skipped at the start of this lane; it was run after
the owner's process audit and sent as one crew-ask on PR #1406. Every premise below was
re-checked against the code at 943a9341b after the owner's "get your facts right" ruling;
the two that were wrong are marked CORRECTED.

| # | Decision | Premise, verified | Owner answer |
| --- | --- | --- | --- |
| R-a | Blocked reply wording | `turn/task.py:42` REFER_TO_SALESMAN, returned by `escalation_control.barred_reply` | Ruled (b): "Please refer to your salesman." |
| R-b | Seeded blocked types | `esc1_0001_escalation_allowed.DEALER_NAME_SQL`; `tests/test_migration_esc1_0001_escalation_allowed.py` | Ruled: every "... Dealer" type |
| R-c | Merge across types | `app/services/escalation_policy.py:45-55` `merge`: allowed when any type allows | Ruled after the Mr Loo hand test |
| Q1 | Scope and label | The engine guard is on the branch kind, whatever the team (`engine.py:5258`), and the offer gates cover every team's offer (`turn/state.py:199`); tests: a purchasing team_pick "yes" and a named purchasing team both get the referral (`test_escalation_control.py:372`, `:515`) | Covers every hand-off, so the label is "Can escalate to a person" (applied) |
| Q2 | A blocked miss | CORRECTED: the earlier "Couldn't find X." example was wrong. Measured at 943a9341b: a blocked ORDER miss reads "...Here's what you want: * customer: ...\n\nBut no order matched these." with nothing after it (`_run_order_miss` of the S11 suite); the inventory composer's miss reads "*inventory* for M210-GM:" (same as staff today). A blocked dealer's stock and incoming asks DO still end with "Please refer to your salesman." (the six `test_dealer_eta_stock_routing.py` dealer tests pass with the contact also blocked) | pending |
| Q3 | Dealer + End User | "End User" is not matched by the seed rule (`NOT_DEALERS` in the migration test), so it keeps the column default true, and `merge` allows | pending |
| Q4 | New dealer types | At 5800a59c a new type defaulted to allowed (`contact_access_type_service.py:199` `is not False`) | NO: a new dealer type starts blocked by the seed's rule (applied: `escalation_policy.is_dealer_type_name`, `contact_access_type_service.py:205`; the editor mirrors it) |
| Q5 | Policy read error | `turn_runtime.py:663-665` returns no fact, so `Profile.escalation_allowed` keeps its default true (`turn/state.py:196`); the stock read also fails to "not a dealer" (`turn_runtime.py:682-684`) | Fail open: OK |
| Q6 | Reporting | Blocked turns keep branch kind out_of_scope with lane escalation_barred and create no SLA row (`test_escalation_control.py:372`). CORRECTED: the SQL that expects an SLA row per out_of_scope turn is a one-time rollout precondition for the n8n cutover step 3 (`documentation/plans/chatbot/n8n-changes.md:586-598`), not an ongoing monitor | As recommended: keep out_of_scope; that check excludes lane escalation_barred |
| Q7 | Staff | Offers are gated by `offers_escalation` (`turn/state.py:199`); the forced path has no staff check, so staff can still ask (`test_escalation_control.py:424`) | As recommended: unchanged |
| Q8 | Pickers for blocked contacts | The strip keeps a roster's business options and drops only its member options and escalate stamp (`turn/pending.py::without_escalation`; `test_escalation_control.py:326`) | As recommended: still asked |
