# PLAN: chatbot incoming answer carries ETA delay silently (never a refusal line)

Status: BUILDING - small fix track (24 Sep 2026)
Domain: chatbot / incoming stock
UAC: `chatbot-eta-delay-always-kept-24sep-acceptance-criteria.md`

## Problem (measured)

The parser prompt (`app/services/chatbot_parser_prompt.py`, domain_hint = incoming) maps an
ETA ask to `estimated_arrival_date` only. The owner wants the ETA delay date to ride along
with the ETA. Mapping ETA to `["estimated_arrival_date", "eta_delay_date"]` in the prompt is
the wrong seam: every key in `requested_attributes` means "the customer named this field",
and `app/services/chatbot/lanes/business/fetch.py` renders two things for a NAMED key that
must never appear for an implied one:

- denied (contact lacks the `eta_delay_date` reveal): `fetch.py:2367` appends
  "I can't share the ETA delay - please check with the office."
- blank on the row: `fetch.py:2350` appends a synthetic "not recorded yet" field.

A contact who may see the ETA but not the delay would get the ETA plus a refusal line.

## Fix (one line + tests)

`ALWAYS_KEPT_KEYS` (`fetch.py:1034`) becomes `{"estimated_arrival_date", "eta_delay_date"}`.
`keep_keys` is seeded from it, so the delay field survives the requested-attribute projection
on every incoming answer whenever the CRM sent it. `req_attrs` is untouched, so:

- denied: `field_access.py:563` already strips the field before it reaches the chatbot, and
  the denial note only fires for keys in `req_attrs` - silent.
- blank: the "not recorded yet" note only fires for keys in `req_attrs` - silent.
- explicit "is it delayed" (parser emits `eta_delay_date`) keeps today's behaviour: denial
  note when denied, "not recorded yet" when blank.

Prompt untouched. No new parser field, no config surface (owner ruling 24 Sep: asked whether
this could be prompt-tunable; answer no, `requested_attributes` is the only channel and it
carries "asked" semantics by design).

## Files

- `sorento_crm_backend/app/services/chatbot/lanes/business/fetch.py` - the constant and its
  comment.
- `sorento_crm_backend/tests/chatbot/test_s6b_fetch_lane.py` - new tests (UAC AC-1..AC-4);
  `test_non_checkpoint_ask_does_not_expand` currently asserts `eta_delay_date` is dropped on a
  `liner_code` ask - that assertion flips (delay is now always kept), with the reason in the
  docstring.

## Not in scope

- Prompt vocabulary changes.
- The `__all__` timeline path (already silent on denied keys, unchanged).
- Any other domain's `ALWAYS_KEPT_KEYS` equivalent.
