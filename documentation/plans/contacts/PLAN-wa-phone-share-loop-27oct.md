# PLAN: WA-PHONE-SHARE-LOOP (tapped contact card read as "no answer")

Status: in review (small fix track: no migration, no auth/RBAC change, no new ingest surface)

## Bug (prod, 27 Oct ~23:40 MYT)
A username-only WhatsApp contact (no phone on its Respond.io contact) says "Hi", gets the phone-share
template, taps Share Contact Info three times, and gets the template three times, then the staff note
"asked for a phone number 3 times in 24 hours with no answer". Every tapped card was rejected by rule 3
(`wa_phone_link.accepted_card_phone`) before any link step ran.

## Rule (owner ruling 27 Oct ~23:40)
- A tapped card (signed respond webhook ingress + origin `contact_request` + non-empty phone) counts as the
  answer, once. Contact with access holds that phone -> merge as today. None -> phone set on the contact
  (Respond.io + CRM row), no-access handling as for any known contact without access. Never ask again.
- Link step fails (Respond.io error) -> one staff hand-off, never a re-ask.
- The ask goes out only while the contact has no phone and no accepted card; max 3 per 24 h stays.

## Tests (red first)
See `wa-phone-share-loop-27oct-acceptance-criteria.md`.

## Root cause (crew prod trace 27 Oct + prod sample)
Card turns 23:30:34 and 23:30:50 closed `phone_ask`: `accepted_card_phone` read `channel.meta.wa_id` from a dict,
but Respond.io sends `channel.meta` as a JSON string `{"meta": {"wa_id": ..., "user_id": ...}}`, so wa_id was always
missing, and a missing wa_id was a refusal. #1888's fixtures used the dict shape, so CI passed.

## Fix
- `wa_phone_link._wa_id`: meta as dict or JSON string, nested `meta` or flat.
- `wa_phone_link.card_refusal`: rule 3 as designed (CARD rule 3): origin `contact_request` + phone; wa_id a cross-check
  only when present. Signed ingress stays mandatory (engine). The reason code goes in the trace (`card_refusal`).
- `engine._phone_unknown_decision`: accepted card, AI off -> `NO_ACCESS_LINE` once + staff comment;
  `_card_accepted_before` stops any later ask for a contact whose card was accepted (only another tap retries).
