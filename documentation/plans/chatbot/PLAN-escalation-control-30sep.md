# PLAN: escalation control per contact / access type (ESCALATION-CONTROL)

Status: in progress (Plan). Track: full (migration). Owner request 30 Sep 2026.

Owner: "we need to be able to control each contact that they cannot access the escalation:
cannot force escalate, won't be offered escalation; this is for dealer".

## Journey
A dealer contact chats with the bot. When the bot cannot answer, it does NOT offer customer
service and does NOT show the member picker. If the dealer asks for a person, or replies "yes"
to an old offer, the bot replies with the salesperson referral instead of handing off.
Staff can flip the switch per contact (inherit / allow / block) or per access type.

## Design
- `contact_access_types.escalation_allowed` BOOLEAN NOT NULL DEFAULT TRUE; seeded FALSE for
  "Sorento Dealer". `respond_contacts.escalation_allowed` BOOLEAN NULL (override).
- Resolution: contact override wins, else any linked access type allows (merged like
  stock_visibility.resolve_policy), else default true.
- Resolved once into turn Profile (`escalation_allowed`); helper `offers_escalation(profile)`
  gates every offer site; forced path blocked in `turn/apply._lane` and guarded before
  `engine._run_escalation_arm`.
- UI: tri-state on contact Chatbot section; switch on access-type editor.

See `escalation-control-acceptance-criteria.md`.
