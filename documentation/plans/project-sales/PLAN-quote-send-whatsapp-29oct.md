# PLAN: Send a quotation through the salesperson's own WhatsApp (QUOTE-SEND-WHATSAPP)

**Status:** Build (mock v2 approved 30 Oct 09:50). Size M (card + mock before code), lead pattern (tester -> coder -> reviewer). No migration, no
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

## Architecture

Layer: FE does the send (a link; no server send). BE gains one small write route for the activity line. No schema.
Shared mechanisms reused: the sign-link mutation, `waMeUrl`, `record_project_event`, `components/ui` Dialog / Button /
Input / Textarea / DropdownMenu, `useCopyToClipboard`. Classes of input fixed: every recipient-field shape seen in the
data (MY landline local/intl, foreign intl, slash lists, empty) plus MY mobiles local/intl, by rule, not by example.

FE (paths under `sorento_crm_frontend/`):
1. `lib/wa-me.ts`: `waMeUrl(phone, text)` moved out of `app/(auth)/portal/lib/portal-paths.ts:108-111` unchanged
   (empty digits give `https://wa.me/?text=...`); its two portal importers and its test cases move with it.
2. `app/(protected)/project-sales/_shared/lib/quotationWhatsApp.ts`, pure:
   - `toWaDigits(raw)`: one number to wa.me digits: drop everything but digits, a leading `00` is dropped, a single
     leading `0` becomes `60` (MY local). Used for a typed "To".
   - `pickMobile(field)`: split the recipient field on newline, `/`, `,`, `;`, `&`, " or "; return the first part
     that is a MY mobile (`toWaDigits` matches `^601\d{8,9}$`) or a non-MY international number (written with `+`
     or `00`, digits not starting `60`); else `''`. Landlines and bare foreign-looking digits without `+`/`00` give `''`.
   - `quotationNumberLabel(document, issue)`: `issue.our_ref_text ?? `${document.document_no} (R${issue.issue_no})``
     (switches to QUOTE-SIGN-PAGE's label at rebase if it has merged).
   - `whatsAppMessage({ attn, numberLabel, subject, link, signatory })`: UAC AC-D1/AC-D2 exactly (blank = missing).
3. Service `logQuotationWhatsAppOpened(projectId, documentId, issueId)` in `_shared/services/quotationDocumentService.ts`
   + mutation `whatsAppOpened` in `_shared/hooks/useQuotationDocuments.ts` with NO error toast (AC-F3).
4. `[documentId]/components/QuotationWhatsAppDialog.tsx`: open while it holds an issue. On open: mints via `signLink`,
   link = `window.location.origin + path`; "To" prefilled `pickMobile(recipient_phone_snapshot)`; Textarea prefilled
   `whatsAppMessage(..., signatory: signatory_name)` once the link arrives. "Open WhatsApp" = an anchor
   (`target=_blank rel=noopener noreferrer`) to `waMeUrl(toWaDigits(to), message)`, inert until the link is ready;
   its click fires `whatsAppOpened` and forgets it. "Copy link", "Close".
5. `quotation-documents/actions.tsx`: action `quotation_document.whatsapp` "Send via WhatsApp" right after
   `quotation_document.sign_link`, inside `canEdit`, disabled until issued with the copy action's hint; run resolves
   the latest issue (`issueToExport`) and opens the dialog. The action set also returns `openWhatsApp(issue)`.
6. `[documentId]/components/QuotationDocumentClient.tsx:406-417`: the Send to Customer button becomes a DropdownMenu
   trigger with items Email (`mutations.issue.mutate(documentId)`, as today) and WhatsApp (same call, `onSuccess`
   -> `openWhatsApp(issue)`).

BE (`sorento_crm_backend/`):
7. `POST /projects/{project_id}/quotation-documents/{document_id}/issues/{issue_id}/whatsapp-opened` beside the
   sign-link route (`app/api/v1/projects/quotation_documents.py:610`), same guards (`require_permission(EDIT)`,
   `_editable_project`, `get_document_or_404`, `_issue_or_404`). Service `record_whatsapp_opened` in
   `project_quotation_document_service.py` calls `record_project_event(template="quotation_whatsapp_opened",
   payload={document_id, issue_id, issue_no, our_ref}, actor_id, body_text="Quotation <ref> link opened in WhatsApp by
   <user name>")`; the template is NOT added to `MEANINGFUL_TEMPLATES`. `ProjectActivityPanel.tsx:42` renders
   body_text for it as is.

## Slices

1. Tester: red vitest + pytest for everything below, committed alone (`test(red):`).
2. Coder: 1-7 until green; kill test after.
3. Reviewer + browser pass 1280/375 on the crew test copy (fake numbers only; check the wa.me href, never WhatsApp).

## Test list

- `toWaDigits`: `012-000 0001` -> `60120000001`; `+60 12-000 0001` -> `60120000001`; `0065 0000 0001` ->
  `6500000001`; `+65 0000 0001` -> `6500000001`.
- `pickMobile`: the above; `03-0000 0001` -> ``; `+603-0000 0001` -> ``; `03-0000 0001\n012-000 0001` -> mobile;
  `012-000 0001 / 013-000 0002` -> first; `91-00-00000001/2/3/4` -> ``; `''`, null, spaces -> ``.
- `whatsAppMessage`: full text byte-exact; no attn -> "Hi,"; no subject -> no " for"; no signatory -> ends "Thank you,".
- `waMeUrl`: spaces, newlines, `&`, `#`, `+` encoded; empty digits -> `https://wa.me/?text=`.
- Dialog: mints on open; title "Send R2 via WhatsApp"; To + message prefilled; href exact; edited message and typed
  `012...` change the href; buttons inert while minting and after a mint failure (with a message); click logs once;
  a failed log shows no toast.
- Actions: item right after "Copy counter-sign link"; disabled + hint before issue; absent without edit.
- Client: Send to Customer opens Email / WhatsApp; Email issues and opens nothing; WhatsApp issues then opens the
  dialog for the returned revision; failed issue opens nothing; closing the menu issues nothing.
- BE: route writes one `activity_events` row (template, body_text with ref + user); project last-activity clock
  unchanged; non-editor refused; another document's issue 404; malformed ids answered not crashed.
