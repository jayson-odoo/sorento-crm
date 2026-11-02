# PLAN: AGENTIC-WA-S2 - agent on WhatsApp slice 2: warranty / complaint claim with photos

Status: BUILDING (Phase 2 red-first) on #2095. Card v1 answered 2 Nov by crew (Q1-Q4); Q5 with the owner, built
as a one-line switch defaulting to "allow". Track: M (cloud lane).
UAC: `agentic-wa-s2-acceptance-criteria.md` (written after the answers).

Parent: `PLAN-agentic-wa-w2-01nov.md` (slice 1 merged in #2072, 46de2f6d77). Out of scope: slice 3 (purchase
request, sponsorship, sample, price tag), staff contacts getting dealer tools (owner ask pending).

Rulings in force: W-Q1a, W-Q2a, W-Q3a, W-Q4 all safe dealer writes each with a confirm, W-Q5a, router cut-off
0.70; W2-Q1..Q5 (undo = 10-minute withdraw of an untouched submission, console = test, no extra cap); #2090
crew ruling: a complaint's AI extract is never split.

## Behaviour card v1

### What exists today (measured on main 46de2f6d77)

- The W2 dealer seam: `agent/portal_writes.py` runs the PORTAL's own service calls under a transient
  `PortalToken` (`:53`, `:65` `run_as_contact`); kinds offered follow `resolve_visible_form_types` (`:85`);
  `complaint` is already a note kind (`:34`) but has no create tool.
- Portal complaint path, the one we reuse: `portal_service.py:1106` `create_or_update_draft` ->
  `:1153` `submit_draft` (complaint branch `:1182`: draft/rejected only, `require_complete`, status on submit),
  numbering `:1413` (`complaint_number`), lines `:1723` `_replace_complaint_lines_if_needed`, team notice
  `:2009` `notify_team_complaint_external_created`, form SLA `submit` event `:1336`.
- Required on submit (`portal_required_fields.py:22`): DO number, customer name, contact person, contact
  number, customer type, complaint date, within warranty, defects discovered, complaint type, defect
  description, salesperson, product lines. The four lookups (`complaints_customer_type`,
  `_within_warranty`, `_defects_discovered`, `_complaint_type`) are enforced on flush by
  `lookup_write_listener.py` (server side, every path).
- Portal form defaults (`SubmissionForm.tsx:299-337`, `:815-842`): complaint date = today, salesperson = the
  contact's full name, each lookup = its binding default; picking a DO fills customer name from the DO's
  debtor and product lines from the DO's products (`:1642`).
- DO lookup (`api/v1/public/portal.py:643`): `orders` under the contact's portal company scope; submit does
  NOT re-check the DO (free text on the row).
- Files: portal upload (`portal.py:1681`) = ownership check, portal attachment type quota (`:1109`
  `_check_quota`: extension, size, count), storage under `portal/<contact>/`, thumbnail, link on the
  complaint, uploader = contact. It allows files on a submitted complaint too (no editable check for
  complaint).
- WhatsApp photos: a photo goes to the bot (`router.py:79` `has_media` -> chat); the media lane reads it and
  `media_tasks.py:118` `_store_media_bytes` stores the SAME bytes as an `attachments` row linked to
  `chatbot_turn`, `uploaded_by_contact_id` = the contact. Fail-closed gate (`media_access_service.py:633`):
  a contact without photo reading allowed gets no read AND no stored photo. Documents, videos, stickers are
  never stored.

### Proposed mechanism

Three dealer tools on the W2 seam, no new path:

1. Read `crm_my_chat_photos`: the contact's own stored chat photos (image mime only) from the last 24 hours,
   newest first, at most 10, each with id, sent time and what the bot read on it (its stored read).
2. Write `crm_complaint_create`: DO number(s), product lines (code + qty), defect description in the dealer's
   own words, within warranty, optional complaint type / defects discovered / customer type / contact person /
   number / address / project, and `photo_ids` from the read. Proposal checks: form visible; each DO exists
   under the contact's portal scope (the DO lookup's query); each product code is on one of those DOs; lookup
   values valid (else the options are listed back to the model); photos are the contact's own, images, and
   pass the portal attachment type's extension / size / count; `missing_on_submit` empty. Confirm: draft ->
   each photo through the portal upload body (extracted into one helper both call; bytes read from our own
   storage, never respond.io's URL) -> `submit_draft`. Any refusal deletes the draft and its uploads.
   Reply note, by code: "Complaint <number> is with the team. Reply undo within 10 minutes to withdraw it."
3. Write `crm_complaint_withdraw`: the W2 withdraw rule for a complaint (first submission, 10 minutes,
   untouched: no response, comment by anyone else, form action, touched SLA stage, file added by anyone
   else). Deletes the row, its lines, history, notifications, own notes, untouched stages, view link, and
   the files the claim attached.

Proposed confirm block (English, built by code as in W2; the dealer's text is kept verbatim in its language):

> 1. File a warranty claim: DO DO2026-01234, ELP3754 x1, "leaking after 3 months", within warranty: Yes,
>    complaint type: Product defect, customer <DO debtor>, contact <name> <number>, 3 photos from this chat
>    (sent 10:02-10:05).

### Real-shaped examples (masked; the sandbox cannot reach dev data, crew-data-request posted for real rows)

1. Photos first: 3 photos of a leaking basin mixer, then "ELP3754 leaking after 3 months, DO2026xxxx, want to
   claim warranty". Bot reads each photo; next text goes to the agent -> photos read -> proposal with the 3
   photos -> "yes" -> CMP-26-0xxx.
2. Text first: "CB1506SS from DO2026xxxx, colour peeling, customer angry" -> proposal with 0 photos, the reply
   says photos can be sent now -> dealer sends 2 photos (bot) -> "add these" -> a new proposal replaces the
   old one (newest-only) with 2 photos.
3. DO of another dealer's company: "DO2025yyyy SRT5733 cracked" -> "I can't find DO2025yyyy on your account."
   No proposal.
4. zh: "ELP3754 漏水, DO2026xxxx, 还在保修期" -> same tool; the description is stored as typed.
5. Same DO + product sent again next day while CMP-26-0xxx is open -> Q5.

### Edge cases (become UAC rows)

- Photos before the claim text: picked up by the read (24 h window, newest 10).
- Photos after the proposal: not on it; the proposal stays as shown. After submit: Q4.
- More than N photos: the read returns the newest 10; the portal type's `max_count_per_entity` refuses
  more at proposal ("Attachment limit reached (N).") with no write.
- Non-image files (PDF, video, voice note): not stored by the bot, so never offered; the agent says to add
  them on the portal.
- Photos the bot could not keep (photo reading off for the contact, or a failed read): not offered (Q1).
- A DO the dealer cannot see (outside its portal scope) or a product not on the DO: refused at proposal.
- Complaint form switched off for the contact: the two complaint tools are not offered (portal gate).
- Duplicate respond.io id on two contact rows: no tools (W1 rule).
- Required field still missing (no default, dealer did not say): the agent asks for it; no proposal.
- Stale / same-turn / older "yes": refused by `actions.confirm` (unchanged).
- Console: proposal shown, confirm writes nothing, "Test turn: nothing was sent." (W2-Q3).
- Language zh / ms / en: the agent talks in the dealer's language, the confirm block is code-built English
  (as W2), stored text verbatim.

### Decided from the repo and prior rulings (no question)

- Same portal service calls and lookup / required-field / attachment checks; no second complaint path.
- Undo = W2-Q2: 10-minute withdraw while untouched; after that the W2 sentence and the note tool.
- Console = test (W2-Q3). Router unchanged (W2-Q4): photos still go to the bot; the agent's pending proposal
  keeps the next text on the agent.
- DO must resolve under the contact's portal scope (same query as the portal DO picker), product codes must be
  on the chosen DO(s), customer name comes from the DO's debtor as the portal picker fills it.
- Known limit (W2): the team email on submit cannot be recalled by a withdraw.

### Questions (at most 5, each with a recommendation)

- **S2-Q1 Which photos a claim can carry.** (a) only photos the bot already stored (needs the contact's photo
  reading on; otherwise the agent says "add the photos on your portal" and sends the link); (b) also store
  every photo of an agent-mode contact without reading it (new store path, no AI cost). Recommendation (a):
  no new ingest path, and the fail-closed media gate stays the owner's single switch.
- **S2-Q2 AI extract of the photos.** (a) none: the agent sees the bot's per-photo reads through
  `crm_my_chat_photos` and fills only what the dealer said or the photos read; (b) one portal complaint
  extract call over all claim photos at proposal (never split, #2090) to prefill missing fields.
  Recommendation (a): the photos were already read once and paid for; (b) doubles the spend per claim.
- **S2-Q3 Fields a dealer rarely says.** (a) defaults as the portal form: date today, salesperson = the
  contact's name, lookups = binding defaults, customer name from the DO; contact person / number = the
  dealer's own name and WhatsApp number unless they give the site contact; the agent asks only for what is
  still missing; (b) ask for all 12. Recommendation (a): same defaults the portal pre-fills, and the confirm
  block shows every value before the yes.
- **S2-Q4 Photos sent after the claim is in.** (a) a fourth tool `crm_my_request_photos_add` attaches newer
  chat photos to the dealer's own complaint (the portal already allows files on a submitted complaint),
  with a confirm and an undo (remove that file); (b) not over WhatsApp, the agent sends the portal link.
  Recommendation (a): "here are more photos" right after a claim is the common shape.
- **S2-Q5 Duplicate claim.** (a) an open complaint by the same contact on the same DO and product is refused
  at proposal: "You already sent complaint CMP-.. for this on 1 Nov. I can add a note to it instead.";
  (b) allowed, the confirm block names the earlier one. Recommendation (a): a second claim doubles team SLA
  work, the note tool covers "any update?", and a genuinely new claim can still go through the portal.

### Decisions (2 Nov, crew from prior owner rulings)

- S2-Q1 (a): only photos the bot already stored, under its own access switches (W-Q3a).
- S2-Q2 (a): no extra AI read; the stored read plus the dealer's words.
- S2-Q3 (a): portal-form pre-fills; contact person / number = the dealer unless they name a site contact; ask
  only what is missing. Condition: "within warranty" must come from the dealer, never a default.
- S2-Q4 (a): a fourth tool adds newer chat photos to the dealer's own open complaint, with confirm + undo.
- S2-Q5: with the owner. Built as a switch (`portal_writes.DUPLICATE_CLAIMS`), default `"allow"` (no new
  guard): the confirm block names the earlier open claim on the same DO + product. `"refuse"` refuses at
  proposal with the note offer.

### Fixes from the crew helper review of e2f351fd (before review)

1. DO check: NOT the portal picker's partial, legal-entity-scoped search. On WhatsApp the DO must be the EXACT
   number of an order of one of the dealer's own linked customer accounts (`respond_contact_customers`).
   Anything else answers the plain not-found ("Delivery order <no> not found.") and never names another
   customer. Security-review item.
2. A photo the bot could not read is still kept when the photo switch allows it: the media worker stores the
   fetched bytes on a failed read too (job stays `failed`, ledger unchanged), so a provider outage does not
   lose claim photos.
3. The confirm block lists EACH photo it attaches: its time and what it shows (the stored read), or "could not
   be read".
