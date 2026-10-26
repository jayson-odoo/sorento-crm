# PLAN: WhatsApp username-only contacts get a verified phone and join the contact that holds their access (WA-USERNAME-CONTACTS)

Status: Scout. Behaviour card pending; no code until the owner answers. Track: L (new chat flow, contact
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
(filled from the scout round; every claim cites file:line or an official doc URL)

## Open questions (card)
(filed via `crew report --ask`)
