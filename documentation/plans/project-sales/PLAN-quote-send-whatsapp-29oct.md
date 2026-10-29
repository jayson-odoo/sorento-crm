# PLAN: Send a quotation through the salesperson's own WhatsApp (QUOTE-SEND-WHATSAPP)

**Status:** Plan. Size M (card + mock before code), lead pattern (tester -> coder -> reviewer). No migration, no
auth/RBAC change, no new external ingest. Behaviour card: `CARD-quote-send-whatsapp-29oct.md` (Waiting:owner).

**Source:** owner team meeting 29 Oct 15:40 (Project Sales module); owner answers 29 Oct 22:45: Q4 a wa.me link from
the salesperson's OWN WhatsApp first (no respond.io, no templates, no system-sent message); Q3 the quotation number
label is the one QUOTE-SIGN-PAGE settles (its Q1 (a), "Quotation No. PRJQ-2026-0003-R1").

## Journey

A salesperson has pressed "Send to Customer R<n>" on a quotation. Today that only issues the revision
(`QuotationDocumentClient.tsx:406-417`); the counter-sign link is copied by hand from the gear
(`actions.tsx:155-172`) and pasted into their own WhatsApp or mail. After this lane: the gear (and the list row "...")
offers "Send via WhatsApp", and the same prompt opens on its own right after "Send to Customer R<n>". The prompt shows
who it goes to and the exact message; one press opens WhatsApp (app on phone, WhatsApp Web on desktop) with the chat
and the text already filled in. The salesperson presses Send in WhatsApp themselves.

## What exists (verified on origin/main ec29a81c3b)

- Action set, one definition for gear + row: `quotation-documents/actions.tsx:30-218`; copy link :155-185, gated by
  `canEdit` and `is_issued`, hint "Send it to the customer first".
- Link mint: `useQuotationDocumentMutations().signLink` (`_shared/hooks/useQuotationDocuments.ts:257`) -> POST
  `.../issues/{issue_id}/sign-link` (`app/api/v1/projects/quotation_documents.py:610-635`, needs EDIT) ->
  `issue_sign_link` (`app/services/project_quotation_document_service.py:980-997`): reuses a valid token, rotates an
  expired one, TTL 30 days (:896). So an expired link is never handed out.
- Clipboard fallback dialog: `[documentId]/components/QuotationSignLinkDialog.tsx`.
- wa.me helper: `app/(auth)/portal/lib/portal-paths.ts:108-111` (`waMeUrl`, strips non-digits only).
- Recipient number: `quotation_documents.recipient_phone_snapshot` String(200) (`app/models/projects.py:1113`),
  copied from `parties.phone` at create (`project_quotation_document_service.py:162`), editable, may hold several
  lines (the PDF prints each line, `project_quotation_pdf_service.py:326`).
- Project activity feed: `record_project_event` (`app/services/project_activity_service.py:107`); the Unattended
  clock only moves for `MEANINGFUL_TEMPLATES` (:38-45).

## Architecture (filled in after the card is answered)

- Layer: FE only for the send (a link, no server send). One pure helper builds the number + message + URL; one dialog
  renders it; the action set and the issue button both open that dialog. Logging (if approved) = one small BE route
  writing one `record_project_event` row.
- Shared mechanism reused: `waMeUrl` moves from the portal into a shared lib (or is imported), the sign-link mutation,
  `Dialog`/`Button`/`Input` from `components/ui`.

## Slices (after approval)

1. Pure helper `buildQuotationWhatsApp(...)` (number normalising + message + URL) - vitest red first.
2. `QuotationWhatsAppDialog` + action item + post-issue prompt - vitest red first.
3. (If Q3 = log) BE route + `record_project_event` - pytest red first.

## Test list (draft, finalised in the UAC)

- URL digits: MY local `01x` -> `601x`; `+60 1x` kept; several lines -> first mobile; landline only -> no number;
  empty -> no number; foreign `+65` kept.
- Text is URL-encoded (spaces, newlines, `&`, `#`), link included verbatim, number label right.
- Action disabled before issue with the same hint as the copy action; hidden without edit permission.
- Post-issue: the prompt opens after "Send to Customer R<n>" succeeds, not after a failure.
