# PLAN: WA-PHONE-SHARE-LOOP (tapped contact card read as "no answer")

Status: in progress (small fix track: no migration, no auth/RBAC change, no new ingest surface)

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
