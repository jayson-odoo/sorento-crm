# PLAN: WhatsApp username-only contacts get a verified phone and join the contact that holds their access (WA-USERNAME-CONTACTS)

Status: Card round 2 filed (owner answered Q3/Q4/Q5 + survivor; Q1/Q2 re-asked with research, card section 8), Waiting:owner; no code until Q1/Q2 settle. Track: L (new chat flow, contact
merge across Respond.io and CRM, ownership proof = auth-adjacent, security-reviewer required). LEAD pattern.
UAC: `wa-username-contacts-26oct-acceptance-criteria.md` (written after the card is answered).

## Owner's words (26 Oct ~22:35, verbatim)
"for whatsapp, they allow user to share username only and not contact number, so when they first contact our
respond io, they respond io would not store the contact number, which causes the syncing to fail as phone number is
mandatory, and this also doens't link to our respond contact which control the access by contact number, so we need
a process to react to this kind of scenario to ask for their phone number, fill it in, identify any merge possibiity
(respond io will suggest the merge), do the merging to the contact that has access configured, so the user can start
using"

## Journey (draft, to confirm in the card)
detect username-only contact -> ask for phone -> prove the user owns that phone -> fill the phone -> find the
merge candidate -> merge (or hand to staff) -> access works on the next message.

## Security constraint (binding)
A username-only user who types a phone could claim someone else's number (a dealer's) and inherit that contact's
access after a merge. Nothing links or merges until ownership of the number is proven.

## Scout findings
In `CARD-wa-username-contacts-26oct.md` sections 1-2 (file:line and doc URLs there). Short form:
- Sync drops phoneless contacts silently (`sorento_crm_backend/app/services/respond_sync_handler.py:213-215`);
  `respond_contacts.phone_number` is unique NOT NULL (`app/models/access.py:268`).
- Unknown Respond.io id -> `access_denied` reply (`app/services/chatbot/engine.py:6352-6353`).
- Sync already re-points a CRM row's `respond_io_id` by phone (`respond_sync_handler.py:241-257`).
- Respond.io merge API exists: `POST /v2/contact/merge`, older contact primary (card section 8; round 1 said UI-only, corrected). Owner test: the contact with the phone survives.
- n8n: no contact-create flow; the spine posts the whole Respond.io message to `/external/chat/turn`.

## Open questions (card)
Card section 6, Q1-Q5, filed via `crew report --ask` 26 Oct.
