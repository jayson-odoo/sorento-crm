# PLAN: WA-MERGE-KEEP-PHONE (28 Oct)

Status: Build (small fix track: one-file service change + tests, no migration, no auth/RBAC change).

## Problem

Owner rule (26 Oct card, restated 28 Oct): when the phone-share flow merges a username-only contact
with the contact that holds the phone, the surviving contact must have the phone number.

Prod 28 Oct: Respond.io kept the username-only contact (the card sender) as the survivor and the
phone went with the merged-away contact. Respond.io's merge rule is "the contact that is older
becomes the primary contact", so id order in `contactIds` does not decide
(https://developers.respond.io/docs/api/3c34d8547c5c9-merge-two-contacts, card section 8).

`link_phone` (`sorento_crm_backend/app/services/wa_phone_link.py`) reads the survivor from the
merge response (`_merge_survivor`) or a phone re-lookup, re-points the CRM row to it, but writes the
phone only on the no-merge path (`client.update_contact(..., {"phone": ...})`).

## Fix

After a merge whose response names a survivor that is not the phone contact, write the verified
phone onto the survivor with the same `PUT /v2/contact/{identifier}` call (`update_contact`) the
no-merge path already uses. The merge body is left as `{"contactIds": [...]}`: the card notes
optional contact fields on the merge body only from a doc snippet, the PUT is already proven in
prod, and it runs after the phone holder is gone.

- A survivor found by the phone re-lookup already holds the phone: no PUT.
- The PUT failing after a merge is a hand-off like any other Respond.io failure: no CRM write, the
  staff comment goes to the survivor.
- Every existing safety check stays (signed ingress, `origin == contact_request`, wa_id match).

## Tests (`tests/test_wa_phone_link.py`)

1. Card sender survives the merge: PUT `{"phone": "+<num>"}` to the survivor, after the merge; CRM
   row re-pointed to it.
2. Phone contact survives: no PUT.
3. Survivor from the re-lookup: no PUT.
4. PUT fails after the merge: `failed`, survivor named, CRM untouched.

## Hand test

Decision-level replay on a crew test copy (crew runs it); no live Respond.io call.
