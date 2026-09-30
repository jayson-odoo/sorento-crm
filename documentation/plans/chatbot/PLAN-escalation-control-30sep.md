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
  NOT NULL DEFAULT TRUE, seeded FALSE for the type named "Sorento Dealer" (admin-created, so
  matched by name); `respond_contacts.escalation_allowed` BOOLEAN NULL (override, NULL = inherit).
- `app/services/escalation_policy.py::resolve`: contact override wins, else the contact's
  access types merged most-restrictive-first (any barring type bars, the direction
  `stock_visibility._merge_access_type_rows` ranks in), else allowed.
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
