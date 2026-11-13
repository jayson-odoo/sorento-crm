# UAC: AGENTIC-WA-S2 - warranty / complaint claim with photos on WhatsApp

Plan: `PLAN-agentic-wa-s2-02nov.md`. Scope: a CONTACT principal (Agent switch on, no linked active CRM user) whose
Complaint form is visible. Linked staff contacts are unchanged.

## Exposure

- C-1 With the Complaint form visible the contact is also offered `crm_my_chat_photos`, `crm_complaint_create`,
  `crm_complaint_withdraw`, `crm_complaint_photos_add`, `crm_complaint_photo_remove`. With the Complaint form
  switched off for the contact none of the five is offered; the W2 tools are unchanged.
- C-2 Every new tool has a router label, listed only when offered.

## Chat photos (read)

- C-3 `crm_my_chat_photos` returns the contact's OWN photos stored from this WhatsApp chat (`chatbot_turn`
  attachments, image mime only) of the last 24 hours, newest first, at most 10; each with its id, the time it was
  sent and what it shows (the bot's stored read), or "could not be read". Voice notes, other contacts' photos,
  older photos, and photos sent before the contact's newest live claim write (filed, withdrawn, photos added)
  never appear.

## Claim (propose)

- C-4 Needs at least one DO number, at least one product code, the defect description and within warranty.
  Within warranty is never defaulted, even when its lookup has a default.
- C-5 Each DO must be the EXACT number of an order of one of the contact's own linked customer accounts. Any other
  number (another dealer's DO, a partial number) answers "Delivery order <no> not found." and the reply never
  names another customer. No row is written.
- C-6 Each product code must be on one of the named DOs.
- C-7 Lookup fields (within warranty, complaint type, defects discovered, customer type) take an active option of
  the SAME set the portal form shows (value or label); a wrong value is refused with the options listed. A value
  the model passes must also be something the customer said in this chat (the option's value, label or an admin
  keyword; for within warranty, the customer speaking about the warranty): otherwise nothing is proposed and the
  refusal carries the real options to ask for (`data.ask_customer`). An omitted optional one takes the set's
  binding default; with no default it is asked for the same way. No confirm block while any is missing.
- C-8 Pre-fills as the portal form: complaint date today, salesperson = the contact's name, customer name = the
  DO's debtor, contact person / number = the contact's own name and WhatsApp number unless given.
- C-9 `photo_ids` come from `crm_my_chat_photos` this turn, must be the contact's own stored chat images of the
  last 24 hours, and pass the portal attachment type (extension, size, count).
- C-10 The confirm line lists every value and EACH photo with its time and what it shows (or "could not be
  read"). Nothing is written before the yes.
- C-11 Duplicate (S2-Q5, owner 2 Nov: deferred): a second claim on the same DO and product goes through as on the
  portal, with no extra line and no refusal.

## Claim (confirm)

- C-12 The contact's next-turn yes creates the complaint through the portal service: draft, the photos through
  the portal upload body (bytes copied from our own storage into `portal/<contact>/`, linked as portal files,
  uploader = the contact), submit (number, status, one history row, team notice, SLA submit event). The reply
  carries, by code: "Complaint <no> is with the team. Reply undo within 10 minutes to withdraw it."
- C-13 A refusal at submit leaves no draft and no uploaded file behind.
- C-14 A console confirm writes nothing ("Test turn: nothing was sent.").

## Undo and later photos

- C-15 `crm_complaint_withdraw` hard-deletes the contact's own complaint under the W2-Q2 rule (first submission,
  10 minutes, untouched: no team response, no responder, not resolved or voided, no root cause / resolution, no
  comment by anyone else, no form action, no file from anyone else, untouched SLA stage), with its lines,
  history, notifications, own notes, its own files, stages and view link. Otherwise the W2 sentence.
- C-16 `crm_complaint_photos_add` attaches newer chat photos (C-9 rules) to the contact's own open complaint
  (not resolved, voided or closed); a photo already on it is refused. Another contact's complaint is not found.
- C-17 `crm_complaint_photo_remove` removes a file the contact itself added (the portal's own remove rule); a
  staff file is refused.

## Photos kept on a failed read (helper fix 2)

- C-18 When the media read fails after the photo was fetched (provider error, unparseable answer), the job is
  still `failed` and metered as today, but the fetched image is stored as the turn's `chatbot_media` attachment,
  so the claim can carry it ("could not be read").

## Reply text (crew pass, 3 Nov)

- C-19 A write's own "not found" refusal backs the agent's not-found: no "I could not confirm that nothing exists"
  line.
- C-20 The confirm block and a confirm note ("Complaint <no> is with the team ...") appear exactly once in a reply,
  even when the model copies them into its own text.
