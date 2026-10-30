# CARD: Send a quotation through the salesperson's own WhatsApp (QUOTE-SEND-WHATSAPP, 29 Oct)

Plan: `PLAN-quote-send-whatsapp-29oct.md`. Owner already ruled: wa.me from the salesperson's OWN WhatsApp, no
respond.io, no system-sent message (Q4, 29 Oct 22:45); number label = QUOTE-SIGN-PAGE's (its Q1 (a)).

## Rules (proposed)

1. **Where.** A new item "Send via WhatsApp" right after "Copy counter-sign link" in the quotation actions, so it is on
   both the record's gear and the list row "..." (one action set, `actions.tsx:3-9`). Same gate as the copy action:
   hidden without edit permission (`actions.tsx:154`, route needs EDIT `quotation_documents.py:616`), disabled before
   the first "Send to Customer" with the same hint "Send it to the customer first" (`actions.tsx:159-160`).
2. **What a click does.** Opens a small prompt for the LATEST revision (`actions.tsx:84-91`): "To" number (prefilled,
   editable), the message exactly as the customer will see it, and two buttons: "Copy link" and "Open WhatsApp".
   The counter-sign link is minted (or reused) when the prompt opens (`project_quotation_document_service.py:980-997`).
3. **Open WhatsApp** = a plain link to `https://wa.me/<digits>?text=<message>` in a new tab: the WhatsApp app on a
   phone, WhatsApp Web (or wa.me's own "open" page) on a desktop. The salesperson presses Send in WhatsApp themselves.
   Nothing is sent by the server.
4. **Number** (Q3): from the quotation's recipient number (`recipient_phone_snapshot`, `models/projects.py:1113`,
   copied from the customer party's phone at create, `project_quotation_document_service.py:162`; may hold several
   lines, the PDF prints each, `project_quotation_pdf_service.py:326`).
5. **Message** (Q1, Q2): fixed text, EN, built from the quotation number + revision, subject, link, sender name.
6. **After "Send to Customer R<n>"** (Q5): the same prompt opens on its own once the issue succeeds
   (`QuotationDocumentClient.tsx:406-417`).
7. **Log** (Q4): one project activity line when "Open WhatsApp" is pressed.

## Real examples (shared dev DB, masked; crew ran the read-only SQL, `crew/state/inbox/quote-send-whatsapp/`)

The dev copy has 3 quotation documents, none issued (2 with no number, 1 landline). Party phones (what a new
quotation copies): 1,801 parties, 25 with a phone: 22 MY landlines `+603..`, 1 foreign, 1 slash list, 1 other.
**No mobile number anywhere on the copy** (`mobile_60` and `mobile_local_01` = 0).

| # | Field holds (masked) | Shape | Proposed "To" in the prompt |
|---|---|---|---|
| 1 | `+60x-xxxx xx88` (22 of 25 party phones) | MY landline, intl form | blank: not WhatsApp-able |
| 2 | `03-xxxx xx58` (the one quotation with a number) | MY landline, local form | blank |
| 3 | `+91 xxxxxxxx18` | foreign, intl form | `91xxxxxxxxxx18` kept as given (could be a mobile) |
| 4 | `91-xx-xxxxxxxx/x/x/4` | several numbers in one field | blank (no clean mobile) |
| 5 | (empty) - 2 of 3 quotations, 1,776 of 1,801 parties | none | blank |
| 6 | `012-xxx xx45` (NOT on the copy, test data only) | MY mobile, local form | `6012xxxxx45` |
| 7 | `+6012-xxx xx45` (NOT on the copy, test data only) | MY mobile, intl form | `6012xxxxx45` |

Blank "To" = wa.me opens WhatsApp with the message ready and the salesperson picks the chat. On today's data that is
the normal case, so the editable "To" field is what makes the button useful.

## Edge cases

- Not yet sent to the customer: disabled with the copy action's hint. No edit permission: hidden.
- Expired link: the server rotates it on mint (`service:988-997`, TTL 30 days `:896`), so the message always carries a
  live link; an old link already sent answers "no longer valid, ask ... to resend it" (`service:1031`).
- Desktop with no WhatsApp app: wa.me's own page offers WhatsApp Web. Nothing to handle.
- Popup blockers: the link is minted when the prompt opens, and "Open WhatsApp" is a plain link pressed by the user,
  so no window is opened after a wait (which browsers block).
- Several revisions: always the latest; an older revision's link is not offered.
- Link mint fails: the prompt says so, "Open WhatsApp" stays disabled.
- Revision number label: QUOTE-SIGN-PAGE's "PRJQ-2026-0003-R1" once it merges; until then today's printed
  `our_ref_text` "PRJQ-2026-0003 (R1)" (`models/projects.py:1245`), switched at rebase.

## Questions

**Q1. Message text (customer-facing, EN only).**
(a) rec:
```
Hi <Attn>,

Here is our quotation PRJQ-2026-0003-R1 for <subject>.
You can view and accept it here:
<link>

Thank you,
<sender name>
```
(no Attn -> "Hi,"; no subject -> the " for <subject>" part is dropped); (b) (a) plus the same in Malay underneath;
(c) one line: "Quotation PRJQ-2026-0003-R1: <link>". Rec (a): short, says what the link does, EN matches the PDF.

**Q2. Whose name signs the message?** (a) the person pressing the button (it is their WhatsApp) (rec); (b) the
quotation's signatory (`signatory_name`, `models/projects.py:1122`), even if someone else sends it.

**Q3. Number.** (a) rec: take the first mobile in the field (strip spaces and dashes; MY local `01x` -> `601x`;
`+60 1x` kept; another country's `+` / `00` number kept as given); a landline, several numbers with no mobile, or an
empty field -> "To" left blank; the salesperson can type a number in the prompt, and it is NOT saved back to the
quotation; (b) as (a) but no editing in the prompt; (c) also look at the project's contact phones
(`projects.stakeholders.phone`, `models/projects.py:466`), shapes UNVERIFIED, bigger change. Rec (a): the copy holds
no mobiles at all, so the typed number is the common path; saving it back would edit a sent quotation.

**Q4. Log it?** (a) rec: one project activity line "Quotation PRJQ-2026-0003-R1 link opened in WhatsApp by <user>"
(`record_project_event`, `project_activity_service.py:107`), worded "opened" because wa.me cannot confirm a send,
and NOT counted as attention, so the Unattended badge does not clear (same as the customer's change request,
`project_quotation_document_service.py:1225-1227`); (b) as (a) but it also clears Unattended; (c) no log. (a)/(b) add
one small backend route.

**Q5. After "Send to Customer R<n>".** (a) rec: the WhatsApp prompt opens on its own once the issue succeeds (Copy
link, Open WhatsApp, Close); (b) a toast with a "Send via WhatsApp" button; (c) nothing, the gear only. Rec (a): the
salesperson is about to send it anyway, and Close costs one click when they will email instead.
