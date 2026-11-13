# PLAN: WhatsApp issue reports via the ideation path (typed submissions)

Status: Build (card v2 posted 13 Nov ~19:30, Q1-Q3 pending; answer-independent parts in build). Track: L (lead pattern).
Lane: WA-COMPLAINT-INTAKE. Owner ask 13 Nov 2026, demo Mon 16 Nov 09:30.
UAC: `wa-complaint-intake-acceptance-criteria.md`.

## Re-scope (owner 13 Nov ~19:10, verbatim)

"when i say file complaint menas complaint to the system or a feature request not a sorento complaint like DO
all those". So a "complaint" is an ISSUE with the CRM or the AI, filed on the ideation path with a type:
idea (today) | issue (new). Card v1 below (product/DO complaints, revive #2095) is SUPERSEDED; the #2095 merge
was reverted on this branch (81f26d30, 0c19cf80).

## Design (card v2)

- One type table `app/services/submission_types.py` (core): per type its label, the one required field, the
  ask-back, the reply copy keys. `idea` and `issue` today; a new type is a row, not a path. Justification for the
  table (PRINCIPLES "simplest thing"): the owner asked for it explicitly ("we should be able to scale from
  there") and two types exist on day one.
- The type travels through the ONE existing create builder `ideation_capture_service.build_create_payload`
  (shared by the bot lane and `crm_idea_create`), via ONE mapping function type -> ss fields (Q1).
- The extractor (`ideation_extractor`) reads the type by meaning (schema enum); `crm_idea_create` takes a
  `type` argument. No keywords.
- Chat photos/screenshots sent in the 30 min before filing (and after the contact's previous submission) are
  uploaded to the new item as the submitting user through the existing embed upload (`api/v1/ideation/ideas.py:148`
  -> `call_ss`).
- /ideas: Type column + multi-select Type filter + Type on the detail page, all read through one FE helper.
- Parser rule: a problem with the CRM / the assistant is `ideate`; a complaint about a product or an order
  stays `portal_link` (`chatbot/head/parser_template.py:239-240`).

## Reuse map (card v2)

| Need | Existing function | Use |
|---|---|---|
| Create item in ss | `ideation_capture_service.build_create_payload` :208, `call_create_idea` :113 | extend (type) |
| Bot-lane turn | `handle_capture_turn` :244 | extend (type, photos, reply per type) |
| Agent tool | `agent/writes.py` `crm_idea_create` :2108, `_idea_create_execute` | extend (type arg, photos) |
| Meaning -> fields | `ideation_extractor.extract_ideate_turn` :354 | extend (type in schema) |
| Reply words en/ms/zh | `ideation_capture_replies.render_reply`, `chatbot_reply_copy` | reuse, new copy rows |
| Upload to ss as the user | `api/v1/ideation/ideas.py:148` body, `ideation_gateway_service.call_ss` | extract the upload body into one function both call |
| Chat photos | `tasks/media_tasks.py:118` `_store_media_bytes` (attachments linked to `chatbot_turn`) | read |
| /ideas list | `components/ideas/IdeasListView.tsx` | extend (column + filter) |

## Superseded: card v1 (product/DO complaints)

## Discovery (what exists, file:line)

The ideation path on WhatsApp has two halves today:

| Piece | Where | Who can use it |
|---|---|---|
| Bot lane `ideate` -> MCP `crm_ideation_turn` -> `/external/ideation/turn` -> `handle_capture_turn` | `lanes/ideate.py:224`, `api/v1/external/ideation.py:33`, `ideation_capture_service.py:244` | only a contact LINKED to an active CRM user holding `ideation.board.view` (`ideation_capture_service.py:186`) |
| Agent write `crm_idea_create`: propose -> confirm summary -> "yes" -> create | `agent/writes.py:2108`, `:2262`, confirm block `agent/loop.py:866` | linked CRM users |
| Agent dealer writes (contact principal): `crm_stock_inquiry_create`, notes, withdraw | `agent/portal_writes.py:30`, `_si_execute :390` | dealers (contacts with AI access) whose portal form is switched on (`portal_form_visibility_service`) |

Dealers cannot use the ideate lane (no linked user). The dealer-capable half of the path is the agent's
propose -> confirm -> write seam, which already runs the PORTAL's own service as the contact. The earlier
plan named the complaint claim as its slice 2 (`documentation/plans/resources/PLAN-agentic-wa-w2-01nov.md`
lines 57, 98).

Where a complaint lands and who is told:

| Function | file:line | Reuse |
|---|---|---|
| Portal draft + submit as the contact (creates the `complaints` row, assigns the number, sets `respond_inbox_url` = link back to the WhatsApp conversation) | `portal_service.py:1106` draft, `:1153` submit, `:1523` `_instantiate`, `:1414` number | reuse as is (dealer) |
| Required fields on submit (12, incl. DO number and product lines) | `portal_required_fields.py:19` | reuse as is |
| CS notification on submit (Tier 1 complaint team: in-app + one email) | `portal_service.py:2051` -> `complaints_service.py:1326` `notify_team_complaint_external_created` | reuse as is |
| Staff create (CRM form) | `api/v1/complaints/complaints.py:1074` -> `complaints_service.py:1865` `create_complaint` | reuse for the staff variant only (Q2) |
| Dealer's DO lookup (DO number, debtor, product lines) | `api/v1/public/portal.py:646` | extract the query into one shared function, called by the portal route and the bot |
| Option lists: complaint type, defects discovered, within warranty, customer type | lookup sets `complaints_*` (`public/portal.py:474`) | reuse as is |
| Photos onto the complaint | `entity_attachment_service.py:255` `create_attachment_and_link`; WhatsApp media rows `models/media.py:179` `MediaExtractionJob.media_url`; byte fetch `media_extract/service.py:201` | reuse as is |
| Stock inquiry draft+submit+cleanup | `portal_writes.py:390-434` | turn into ONE shared "submit a portal form as the contact" function; stock inquiry and complaint both call it |
| Router: a turn with media always goes to the bot | `router.py:78` | extend (Q4) |

## Behaviour card

Card v1, posted as crew-ask on PR #2400 (13 Nov). Answers pending.

## 0. What already exists (searched: main, open + closed PRs, #163, repo docs)

| What | Where | On prod today? |
|---|---|---|
| **WhatsApp complaint filing by a dealer, with chat photos, confirm, number, 10-min undo, add-photos-later** | PR #2095 AGENTIC-WA-S2 (branch `claude/whatsapp-warranty-complaints-6u1gk1` head 05562ce7; final work on side branch `...-g526m6` fa4159f7). 5 dealer tools in `agent/portal_writes.py`: `crm_my_chat_photos`, `crm_complaint_create`, `crm_complaint_withdraw`, `crm_complaint_photos_add`, `crm_complaint_photo_remove`; portal upload body shared as `store_portal_upload` (`api/v1/public/portal.py`); 45 tests `tests/chatbot/agent/test_agent_wa_s2_complaint.py`; crew console + WhatsApp-path passes green 3 Nov. Plan `PLAN-agentic-wa-s2-02nov.md` (on that branch). | **No.** Owner PARKED it 3 Nov 17:10 before the hand test finished ("Do not merge ... no more pushes"), closed on owner instruction 7 Nov. Never merged. This is almost certainly what the owner remembers. |
| What a WhatsApp "I want to complain" gets today | parser routes a complaint to `portal_link` (`chatbot/head/parser_template.py:239-240`); bot sends the complaint form link (`lanes/business/fetch.py:1693`, copy `chatbot_reply_copy.py:431`) | Yes: a link, the dealer fills the portal form. |
| Dealer adds a note to their own complaint on WhatsApp | `agent/portal_writes.py:620` `crm_my_request_note_add` (#2072 W2) | Yes. |
| Portal complaint create (the record CS works) | `portal_service.py:1106` draft, `:1153` submit, `:1523` row (sets `respond_inbox_url` = link back to the WhatsApp conversation), `:1414` number, `:2051` -> `complaints_service.py:1326` CS notice (Tier 1 complaint team, in-app + email) | Yes (portal form). |
| Older LLM/n8n-shaped complaint create with DO-first lookup + `user_confirmed` | `api/v1/complaints/complaints.py:1074` (integration payload) and `:1204` `/complaints/integration` | Route is on main; no in-repo caller (n8n only, if any). Not reused: it bypasses the contact's portal checks and has no undo. |
| Consumer (retail) WhatsApp intake `/external/complaint-intake/submit` | PR #163 after-sales S1-S7b (open, never merged, 96 commits, branch left main 1 Aug) | No. Consumer/warranty-engine journey, not dealer complaints; 82k lines, not a reuse candidate for Monday. |
| Ideation on WhatsApp (the "same path") | bot lane `lanes/ideate.py:224` -> `/external/ideation/turn` (`ideation_capture_service.py:244`); agent write `crm_idea_create` (`agent/writes.py:2108`) with the same propose -> confirm -> yes seam #2095 uses | Yes, but only for a contact LINKED to an active CRM user (`ideation_capture_service.py:186`); dealers cannot use the ideate lane. |
| Shared Service repo (ideation / tickets) | not reachable from this sandbox (GitHub scope is this repo only) | Ideas land there via `/ideation/intake/ideas`; nothing complaint-shaped is called from the CRM. |

**Gap:** nothing on prod files a complaint from WhatsApp. #2095 did it end to end on the agent's typed-write seam (the same propose -> confirm -> create seam as ideas and stock inquiries). Probe today: fa4159f7 merges onto main 3dfd3730 with 2 conflicting files (`agent/loop.py` 8 hunks, `agent/writes.py` 1 hunk), both in code main also changed since 7 Nov.

## 1. Rules (proposed: revive #2095 on this lane, plus what this lane adds)

- Who: a dealer contact with AI access whose Complaint portal form is on (`portal_form_visibility_service`). One respond.io id on two contact rows = no tools (W1 rule).
- Same record, same function: the portal's own draft + submit as the contact (actor = contact, `auth_method=agent`). Same number series, same required fields (`portal_required_fields.py:19`), same lookup lists, same CS notice, same conversation link. No second complaint path.
- The bot gathers: DO number (must be an exact DO of one of the dealer's own linked customers, else "Delivery order <no> not found."), product(s) on that DO + qty, what is wrong (dealer's words, kept verbatim in their language), within warranty (always asked, never defaulted), complaint type / when found (one short question with the real list options when the dealer did not say). Pre-filled like the portal form: date today, customer from the DO, contact person + number = the dealer, salesperson, lookup defaults.
- Photos: the dealer's own chat photos the bot stored in the last 24 h, newest 10, each listed on the confirm with its time and what it shows; copied from our storage (never the respond.io link). Photos sent after filing: "add these" attaches them to the open complaint (confirm + undo).
- Confirm first, nothing written before "yes". Undo: "undo" within 10 min withdraws an untouched complaint (W2-Q2), after that "It is with the team now... I can add a note".
- "Typed submissions": one shared submit seam, each type a definition on it. Today's types on the seam: idea (linked users), stock inquiry, complaint (dealers). Next types (purchase request, sponsorship, sample) add a definition, not a path.
- Console turn = test: proposal shown, "yes" writes nothing.

## 2. Examples (masked shapes; sandbox has no dev data, data request below)

1. EN, photos first: 3 photos of a cracked basin, then "Boss ELP37xx cracked when unboxed, DO 26xxxx-xxxx, still under warranty" -> confirm card -> "yes" -> "Complaint CMP-xxxx is with the team. Reply undo within 10 minutes to withdraw it."
2. Malay, no DO: "Sinki KS12xx bocor lepas 2 minggu pasang" -> bot: which delivery order (lists the dealer's own DOs that carry KS12xx: number + date, up to 5, real options) -> "1" -> "Masih dalam waranti?" -> confirm card.
3. Photo only, nothing else: today's bot reads the photo (unchanged). If the dealer then says "this one, want to complain", the photo is offered on the claim.
4. Unknown product / not on the DO: "Couldn't find ABC123 on delivery order 26xxxx-xxxx." with that DO's product codes as options.
5. Form off for this dealer: complaint tools not offered; the bot answers as today (portal link / refer to salesman per the contact's switch).

Confirm card (EN, one fact per line):
```
I will file this complaint when you confirm:
Delivery order: 26xxxx-xxxx
Product:
ELP37xx
Quantity: 1
Problem: "cracked when unboxed"
Complaint type: Broken
Found: On delivery
Within warranty: Yes
Photos: 3 (10:02 am - 10:05 am)
Reply yes to go ahead, or tell me what to change.
```
Malay (Q5 a): "Saya akan failkan aduan ini selepas anda sahkan: ... Balas ya untuk teruskan, atau beritahu apa yang perlu diubah." / after: "Aduan CMP-xxxx telah dihantar kepada pasukan. Balas undo dalam 10 minit untuk menariknya balik."

Lands: CRM Complaints list + detail (same record staff and portal create), status Submitted, the WhatsApp conversation link on the record; the audit actor is the dealer contact (auth_method agent), as #2095 recorded it. Notified: the Tier 1 complaint team, in-app + email, exactly as a portal complaint. No CRM screen changes, so no mock.

## 3. Questions (at most 5)

- **Q1 Reuse #2095?** (a) revive #2095's work onto this lane: merge fa4159f7 + main (2 conflicting files), keep its tests, add what this card adds (typed seam, Malay card, staff if Q2); (b) build fresh on the bot's ideate lane with a `type` field. Recommendation **(a)**: it is the same seam ideas use, it was green on crew's console + WhatsApp passes, and Monday leaves no room for a rebuild; (b) cannot serve dealers (the lane needs a linked CRM user) and duplicates confirm/undo.
- **Q2 Why was #2095 parked, and does it still apply?** (a) parked only for timing/priorities: lift it, ship it here; (b) a behaviour the owner did not want (please name it, I fix it first). Recommendation **(a)** unless the owner names (b).
- **Q3 Sales staff filing for a dealer** (the Monday meeting is with Sales). (a) also a linked staff user: "file a complaint for <customer>, DO ..." uses the same type definition and creates through the staff create (`complaints_service.py:1865`) + the same CS notice, staff permission `complaints.add` checked; (b) dealers only in this lane, staff next. Recommendation **(a)**: the demo audience is Sales, same seam, one extra runner.
- **Q4 Photo-first and photo-caption turns.** Today a turn with a photo always goes to the bot (`router.py:78`), so a caption "ELP37xx cracked, want to claim" is answered by the bot, not filed. (a) keep #2095's rule (photos stored by the bot, offered on the next text) and add: a photo caption that reads as a complaint goes through the same router classification as text; (b) leave the router as is (dealer must send a text after the photos). Recommendation **(a)**: WhatsApp users caption photos; requires the contact's photo-reading switch on, as #2095.
- **Q5 Confirm card language.** (a) the card and the after-filing line in the dealer's language (EN / Malay / Chinese), labels translated, the dealer's own words kept verbatim; (b) English card as every other agent write today (`agent/loop.py:866`). Recommendation **(a)** for complaints (dealers write Malay), the rest of the writes unchanged.

Data request (crew, masked): the 4 lookup sets `complaints_complaint_type`, `_defects_discovered`, `_within_warranty`, `_customer_type` (values + labels + binding default); 3 recent portal complaints (DO number shape, product lines, description) and 1 dealer test contact with AI access + Complaint form on + photo reading on.

Next while waiting: merging fa4159f7 + main on a scratch branch to size the conflicts and run #2095's 45 tests on today's main (no push to this PR until answers).

