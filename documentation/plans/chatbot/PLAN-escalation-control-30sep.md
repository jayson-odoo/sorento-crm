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
