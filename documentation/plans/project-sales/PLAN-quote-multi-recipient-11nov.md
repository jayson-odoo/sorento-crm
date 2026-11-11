# PLAN: quotation with several To parties, one approval, per-recipient PDFs + sent log (lane QUOTE-MULTI-RECIPIENT)

Status: Plan, card v1 + mock v1 posted, waiting on the owner (Q1-Q4). No code until approved. Track: full
(additive migration + external-facing PDF + send surface).

Card: `CARD-quote-multi-recipient-11nov.md`. Mock: `mockups/quote-multi-recipient-11nov.html`. UAC: `quote-multi-recipient-11nov-acceptance-criteria.md`
(to follow, after the card is approved).

## Owner ask (11 Nov 2026)

One proposal/quotation can be addressed to several of the project's parties, each with its own Attn contacts,
with one set of lines/prices/revision and one approval. Send goes to the listed recipients (all or a subset),
each gets its own PDF addressed to it, and every send is logged per recipient per revision.

## Today (read in this lane)

- One recipient per document, snapshotted on the document row:
  `sorento_crm_backend/app/models/projects.py:1195-1203` (`recipient_party_id`, `recipient_*_snapshot`, `attn_name`).
- Issue (revision) row: `app/models/projects.py:1480-1585`, one PDF per issue (`pdf_attachment_id`).

## Build outline (detailed once the card is approved)

Backend
1. Additive migration (id <= 32 chars, down_revision = main's single head at build time):
   - `projects.quotation_document_recipients` (document_id CASCADE, party_id SET NULL, sort_order, name / address /
     phone / fax / email snapshots, attn_name, attn_contact_ids JSONB, company_id), unique (document_id, party_id);
     backfill one row per document that has a recipient today.
   - `projects.quotation_sends` (document_id, issue_id CASCADE, recipient_id SET NULL, party_id, name / attn
     snapshots, channel NULL|email|whatsapp|download, sent_by, sent_at, company_id; + sign_token if Q1 a);
     backfill one row per existing issue, channel NULL ("Not recorded").
   - The document's `recipient_*` / `attn_name` columns stay, mirrored from recipient 1 (no reader changes).
2. Recipient endpoints (list / add / update / remove / reorder) outside `assert_unlocked` (rule 3), History entry
   per change; `apply_recipient_pick`'s post-issue lock is dropped for adding recipients.
3. `POST .../issue` takes `recipient_ids` + `channel`; `POST .../issues/{id}/send` re-sends a revision (rule 7). Both
   refuse an unlisted recipient (422) and write `quotation_sends` rows.
4. PDF / cover / Excel render take an optional send row and print its To / Attn; queued export per recipient.
5. `GET .../sends` for the document, `sent_to` summary on the project's document list.

Frontend
6. `QuotationDocumentHeader.tsx` TO block as a list (read + edit), `QuotationRecipientPicker` per recipient,
   Attn via `PartyContactsDialog` (#2335).
7. Send popup (new `QuotationSendDialog.tsx`), CTA label helper in `quotationDecision.ts` (shared with #2334's wording).
8. Sent section on the Header tab; "Sent to" column in `QuotationsPanel.tsx`.

## Tests (red first, after approval)

Backend: migration backfill (recipients + legacy sends); add / remove / duplicate / last-recipient rules; header
edit while approved allowed for recipients only; send refuses unlisted recipient; sends rows per recipient per
channel; re-send without new issue; PDF prints the send row's To / Attn. Vitest: CTA label (1 / 2 / 3+), Send popup
ticks and refuses empty, TO list read / edit, Sent section, project "Sent to" column.
