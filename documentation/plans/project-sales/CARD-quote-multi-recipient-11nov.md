# CARD: one proposal / quotation, several To parties, one approval, per-recipient PDFs + Sent log (lane QUOTE-MULTI-RECIPIENT)

Status: behaviour card v1, waiting on the owner (Q1-Q4 + mock). No code yet.
Mock: `mockups/quote-multi-recipient-11nov.html`. Plan: `PLAN-quote-multi-recipient-11nov.md`.

## Owner ask (11 Nov 2026 ~16:45 MYT)

"our quotation now only can have 1 to party, if same quotation for diff party how eh, then the user need to create
quotation multiple times and get approval many times?" ... "if we only select the To when click Send to, isn't it
weird? cause in the proposal is PGB group but I can send to like XYZ group? ... very hard to trace back".

## What is true today (origin/main 12153bdf, read in this lane)

- One recipient per document, snapshotted on the document row: `recipient_party_id`, `recipient_*_snapshot`,
  `attn_name` (`sorento_crm_backend/app/models/projects.py:1195-1203`). It is picked in the header
  (`QuotationRecipientPicker.tsx`, `apply_recipient_pick` `project_quotation_document_service.py:263-370`) and
  is **locked once revision A is issued** (`:285-290`, code `quotation_recipient_locked`, PROJECT-PARTY-ROLES Q5 a:
  "a different party gets its own proposal"). This lane replaces that rule.
- Sending = issuing a new revision. The header CTA "Send to Customer A" (`QuotationDocumentClient.tsx:614-640`) has
  Email and WhatsApp. **Email only issues the revision**: the CRM sends no email, the salesperson downloads the PDF
  and mails it. WhatsApp issues, then opens a wa.me link (`QuotationWhatsAppDialog.tsx`); only "link opened" is
  logged, on the project feed (`record_whatsapp_opened` `:1743-1778`).
- Re-sending an existing revision is in the gear: Download PDF / Excel (queued to My Downloads), Copy counter-sign
  link, Send via WhatsApp (`quotation-documents/actions.tsx:168-245`).
- The PDF reads the recipient LIVE off the document, not off the revision (`project_quotation_pdf_service.py:491-498`,
  cover page `quotation_cover_service.py:388-389, :502-507`). So nothing records who a revision was addressed to.
- One counter-sign link per revision (`quotation_issues.sign_token`), the views count per revision
  (`quotation_issue_views`), and the sign page shows the document's one recipient
  (`project_quotation_document_service.py:2419-2421`).
- The cover letter's `{{recipient_name}}` / `{{attn_name}}` are filled in ONCE when the document is created, into
  `cover_letter_html` (`_render_templates_onto` `:412-450`, context `project_quotation_template_service.py:283-284`).
- Approval sits on the document (`approval_status_id`). While it is with a manager or approved, every header save
  is refused (`assert_unlocked`, `project_quotation_approval_service.py:552-565`, called from
  `project_quotation_document_service.py:496`). Sending spends the approval (`mark_issued` `:538-550`).

## Rules after this lane

1. **To is a list, on the header.** The TO block holds one or more recipients. Each recipient = one party (the
   project's parties first; any company party can still be picked and is linked to the project, as today) with
   its own address / phone / fax / email snapshot and its own Attn (the QUOTE-ATTN-PICKER popup, #2335). The first
   recipient is the one the document's existing fields keep mirroring, so every screen and merge field that reads
   "the recipient" keeps working.
2. **Add / remove = header edit, in History.** "+ Add recipient" under the last one; a remove (x) on each. Each change
   is a History entry ("Added XYZ GROUP to To", "Removed XYZ GROUP from To"). The same party cannot be listed twice.
3. **One approval for all.** Lines, prices and revision are shared. A party that needs other prices gets its own
   quotation. Adding or removing a recipient, or changing its Attn, **does not touch the approval** and is allowed
   while the quotation is with a manager or approved (it is not a price). Everything else on the header stays
   locked as today.
4. **Send names the recipients and the revision.** Main CTA: "Send rev B to PGB GROUP" (one), "Send rev B to PGB
   GROUP & XYZ GROUP" (two), "Send rev B to PGB GROUP +2" (three or more). Pressing it opens the Send popup:
   every listed recipient ticked, untick to send to fewer, channel Email / WhatsApp / Download. **Only listed
   recipients can be picked**; to send to another party, add it to the header first.
5. **Each recipient gets its own PDF.** Same pages, same lines, same revision; only the To block, Attn and the cover
   page's To / Attn fields differ. Email and Download queue one PDF per ticked recipient to My Downloads, named with
   the party ("proposal-Q-2026-0141-B-PGB-GROUP.pdf"). WhatsApp opens one chat per ticked recipient, one after the
   other, each with its own PDF link.
6. **Sent log, per recipient per revision.** Every send writes one row per recipient: revision, party (snapshot of
   its name and Attn as sent), channel, who sent, when. Shown:
   - on the document: a "Sent" section on the Header tab under the TO block, newest first
     ("rev B, PGB GROUP, Attn MS. LINDA TAN, WhatsApp, Hafiz Kamal, 11 Nov 16:50");
   - on each recipient in the TO block: "rev B sent 11 Nov" or "Not sent yet" (amber when it holds an older
     revision than the latest: "has rev A, latest is B");
   - on the project's Proposals list: a "Sent to" column ("PGB GROUP (B), XYZ GROUP (A)").
7. **Re-send a revision without a new one.** The gear's "Send rev B again" opens the same popup for the CURRENT
   revision: no new revision, no approval, one Sent row per recipient picked. This is how a recipient added after
   rev B was sent gets rev B (see Q3).
8. **Outcome stays per project** (5 Nov rule "Outcome per project only"). Won / lost is not per recipient. A customer
   feedback note can name which listed recipient it came from (see Q4).
9. **Existing documents.** Their one To becomes a one-item list (migration); every existing revision gets one Sent
   row to that recipient, channel "Not recorded", at its issue time and by its issuer, so the Sent section is
   never empty for something that went out. A one-recipient document looks exactly as today apart from the CTA
   wording and the Sent section.
10. **The PDF of a sent revision is frozen per recipient.** It prints the To / Attn from its Sent row, so editing a
    party's address next month does not rewrite a PDF already sent. A revision with no Sent row (legacy) prints as
    today.

## Real examples

Dev DB is not reachable from this cloud lane. Company names below are the owner's own samples already used by
PROJECT-PARTY-ROLES (card `CARD-project-party-roles-10nov.md:79-83`); every PERSON name is fake-but-stable (public
repo). The read-only counts query is
`quote-multi-recipient-dev-examples.sql` (crew-data-request) and v2 of this card swaps in its numbers.

1. **One recipient, as today.** PPF2611004, its proposal, To PARAGON VIEW SDN BHD (developer), no Attn.
   After migration: one-item To list, CTA "Send rev A to PARAGON VIEW SDN BHD", Sent section empty ("Not sent yet").
2. **Two recipients, one approval.** PGB GROUP proposal with a below-floor line: To PGB GROUP (Attn MS. LINDA TAN &
   MS. NUR AINA) + AHMAD ZAKI RESOURCES BERHAD (main contractor, Attn placeholder until the dev rows come back). Manager approves once. "Send rev A to
   PGB GROUP & AHMAD ZAKI RESOURCES BERHAD", Email: two PDFs in My Downloads, two Sent rows.
3. **Added after the send.** Same proposal, rev A already sent to both. Sales adds VERITAS ARCHITECTS (architect)
   while the approval is spent; the header save is allowed (rule 3). Gear "Send rev A again", only VERITAS ARCHITECTS
   ticked: one Sent row, no rev B, no approval.
4. **New revision, only to some.** Prices change, rev B is approved, sent to PGB GROUP only. TO block: PGB GROUP "rev B
   sent", AHMAD ZAKI "has rev A, latest is B" (amber), VERITAS ARCHITECTS "has rev A, latest is B".
5. **Legacy.** A proposal issued R1 and R2 before this lane to PARAGON VIEW SDN BHD: two Sent rows "Not recorded",
   at the issue times, by the issuers.

## Edge cases

- **Party removed after a send.** Its Sent rows stay (they are the record) and read "(no longer on To)". It is not
  offered in the Send popup until re-added. Unlinking the party from the PROJECT does not touch the document: the
  snapshot stays and it can still be sent to (snapshot doctrine, AC-A3).
- **Recipient with no contact.** Allowed; Attn is empty, and the PDF leaves the Attn line out as today
  (`project_quotation_pdf_service.py:498`). WhatsApp to it asks for a number in the chat step, as today.
- **Removing the last recipient.** Refused once anything has been sent ("A sent proposal keeps at least one To").
  Before the first send it is allowed (two dev proposals have no To today) but Send is disabled with "Add who this
  goes to".
- **Approval reset when lines change.** Unchanged: lines are locked while pending / approved; Revise returns the
  document to draft and a below-floor line needs approval again before the next revision. Recipients never reset
  it (rule 3).
- **Same party twice.** Refused ("PGB GROUP is already in To").
- **Recipient edited after it was sent rev A** (e.g. Attn changed). Its Sent row keeps the Attn as sent; the next
  send prints the new Attn.
- **Counter-sign / views with several recipients.** Depends on Q1.
- **Cover letter that names the first recipient** ("Dear PGB GROUP" typed or filled by `{{recipient_name}}`).
  Depends on Q2.
- **Make quotation from a proposal** (`make-quotation`): the quotation copies the whole To list.
- **Agent / MCP readers** that quote "the recipient" keep reading the document's mirrored first recipient; a
  `recipients` list is added beside it, nothing is removed.

## Questions (owner)

**Q1. Counter-sign link and view count with several recipients.**
(a) One link per recipient per revision: the sign page shows THAT recipient's To, and views / sign-back / "changes
requested" name the party. (b) One link per revision for everyone, the page lists all recipients, views are not split.
**Recommendation: (a)**, because it is the traceability you asked for: "XYZ GROUP opened rev B twice" instead of "someone
opened rev B".

**Q2. The cover letter text when it names a recipient.** The letter is one text for the document; its
`{{recipient_name}}` is filled once.
(a) Keep one letter; when a quotation has 2+ recipients and the letter contains a recipient's name or Attn, the Send
popup warns "The letter names PGB GROUP; XYZ GROUP will see that" so sales rewords it neutrally. (b) Re-fill the
letter per recipient at print time from the template, replacing what sales typed.
**Recommendation: (a)**, because (b) silently overwrites typed wording, and the To block + cover page fields are
already per recipient.

**Q3. A recipient added after the current revision went out.**
(a) It can be sent the current revision as is (gear "Send rev B again"), no new revision. (b) A new recipient always
needs a new revision.
**Recommendation: (a)**, because the content is identical and a new revision would make the other recipients' copy
look outdated for nothing.

**Q4. Customer feedback naming the party.**
(a) The feedback note gets an optional "From" picker over the listed recipients (and with Q1 a, sign-page feedback
fills it automatically). (b) Free text only, as today.
**Recommendation: (a)**, because it is one optional field and makes "who said what" readable on the project.
