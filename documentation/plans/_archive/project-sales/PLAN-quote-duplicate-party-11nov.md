# PLAN: Duplicate for another party (lane QUOTE-DUPLICATE-PARTY, PR #2340)

Status: Built; crew pass READY on 5af70b35 (reviewer READY, security review ready, user guide updated). Owner "yeah duplicate", 11 Nov ~16:00 MYT. Track: full (additive migration, size M).
Supersedes the multi-recipient design of this lane (dropped by the owner; its card and mock are deleted).
UAC: `quote-duplicate-party-11nov-acceptance-criteria.md`.

## Owner rules (crew proposal, owner "yeah")

1. One action "Duplicate for another party" on a proposal / quotation (gear + the list row's "..."), one small
   lightbox: the To party picker + its Attn picker (the header's own pickers). Nothing else.
2. The copy is the document as it stands: every area scope, lines, prices, terms, cover letter and closing, spec
   sheet settings, certificate choices. New number; To / Attn = the picked party; Prepared By = the creator.
3. Approval carries over when the copy's lines and prices equal the approved source revision: the copy is approved
   with no new request, and its History says "Approval carried from <ref>". Any later line / price change on the copy
   goes through the normal flow.
4. The copy's header shows "Copied from <source ref>" (link); the source's History says "Duplicated for <party> as
   <new ref>". The project's Proposals list already shows each document's own To (`QuotationsPanel.tsx:174`).
5. One sign-back link per document per revision (owner Q1): already true, the token lives on each issue.
6. Later revisions of each copy are independent.
7. The "Send rev X to <party>" label belongs to QUOTE-HEADER-TIDY (#2334); this lane does not touch it.

## What is reused (read in this lane)

- Copy body: `make_quotation` (`app/services/project_quotation_document_service.py:1059-1201`) copies header fields,
  scopes, one version per scope and its lines (`copy_line`, `app/services/project_quotation_service.py:424`).
  Duplicate copies from each scope's CURRENT version (the document as it stands), not from an issue.
- To / Attn: `apply_recipient_pick` (`project_quotation_document_service.py:263-370`) on the new document, so the
  picked party, its role link and Attn contacts behave exactly as in the header.
- Prepared By: `created_by` = the person duplicating (#2335 prints the creator).
- Approval: a status on the document only (`approval_status_id`, `app/models/projects.py:1240-1265`), keys in
  `project_quotation_approval_service.py:40-63`. Approved documents are locked (`assert_unlocked` :552).
- History: `projects.quotation_document_snapshots` (the History sheet). Restorable form snapshots plus a `note`.

## Design

Backend
1. Migration `qdp_0001_duplicate_party` (additive, down_revision = main's single head):
   - `quotation_documents.copied_from_document_id` UUID NULL, FK `quotation_documents.id` ON DELETE SET NULL.
     Not `source_issue_id`: that one means "quotation made from this proposal" and drives the below-proposal check
     (`project_quotation_approval_service.py:154`) and the proposal's "Quotation" link (`:1293-1325`).
   - `quotation_document_snapshots.kind` CHECK widened with `event`: a History line with a note and no restorable
     state (`doc` stays NOT NULL, written as `{}`). The History sheet shows it without View / Restore.
2. `duplicate_document(db, source, actor, payload)` in `project_quotation_document_service.py`:
   - refuses while the source has a pending autosave draft (`assert_no_pending_draft`, same as Send);
   - kind: a proposal copies as a proposal. The project's quotation copies as a PROPOSAL too (one quotation per
     project, `uq_quotation_documents_one_quotation`); see the card question if the owner wants otherwise;
   - header fields + letter / closing / terms + payment term + validity + spec_sheet copied; doc_date today;
     `your_ref` cleared (it is the other party's reference); signature not copied (each document is signed by whoever
     sends it); `source_issue_id` not copied;
   - each scope: new scope, version 1, lines copied from the source's current version (`copy_line`);
   - certificate rows (`quotation_document_certificates`) copied;
   - To / Attn via `apply_recipient_pick` with the lightbox payload (party required);
   - approval: if the copy needs approval (`requires_approval`) and the source's lines are approved as they stand
     (source key `approved`, or `issued` with every scope's current version equal to its latest issue's version),
     the copy is set `approved` with the source's approver, and an `event` History entry "Approval carried from
     <source ref>" is written. Otherwise the copy is a draft that follows the normal flow.
   - History: copy gets "Copied from <source ref>"; source gets "Duplicated for <party> as <new no>"; project feed
     `quotation_duplicated` event.
3. `POST /projects/{project_id}/quotation-documents/{document_id}/duplicate`, permission EDIT (same as create),
   body = recipient pick fields; response = the new document (201).
4. Serializer: `copied_from_document_id` + `copied_from_label` (source number, latest revision).

Frontend
5. `actions.tsx`: "Duplicate for another party" (Copy icon) for `canEdit`; opens `DuplicateForPartyDialog`
   (new, `components/ui/dialog` + `QuotationRecipientPicker` + `QuotationAttnChooser`), Duplicate disabled until a
   party is picked; on success go to the copy.
6. `QuotationDocumentHeader.tsx`: "Copied from" Field with a link, next to "From".
7. `QuotationHistorySheet.tsx`: `event` entries show the note, who and when, no View / Restore.

## Tests (red first)

Backend `tests/test_quote_duplicate_party.py`: copy has a new number, the picked To / Attn, created_by = actor,
copied_from link, every scope + line + price, terms / letter / spec sheet / certificates; source untouched; refused
without a party, with a pending draft, cross-project party not linked without a role; approval carried when source is
approved; carried when issued and unchanged since; NOT carried when source lines changed after the approved send;
no approval state when none is needed; History entries on both; quotation source copies as a proposal.
Vitest: action present for editors only, dialog disables Duplicate until a party is picked, posts the pick, header
shows Copied from, History sheet renders an event entry without Restore.

## Decisions made in build (review round 1)

- Letter, closing and terms are stored with their merge fields filled in, so the copy swaps the source's
  recipient name, Attn, number and date for its own (`_swap_letter_facts`). Known limit: when the source was
  addressed to the developer, a letter that ALSO names the developer elsewhere gets that mention swapped too.
- Not copied: Your Ref, the signature, `source_issue_id`, and the SAVED spec sheets (SS1, SS2: frozen outputs of
  the source); the spec sheet settings column is copied, so a new sheet is one click. The signatory name and phone
  are copied (they prefill the Sign dialog).
- History "Version N" counts restorable entries only; event lines carry no number.
- The source row is locked (`SELECT ... FOR UPDATE`) before the approval is read, so a Revise cannot slip between
  the line copy and the carry (security review S1). A carried approval writes `quotation_approval_carried` on the
  project feed (N1).

## Assistant coverage (DoD 6-8)

No new list screen (6: n/a). No `ActionDef` (7): the repo has no ActionDef registry, and a duplicate needs a party
and Attn picked on screen. Trigger to add one: the first quotation write the assistant gets. No gold eval file for
project-sales actions exists to extend (8: n/a).

## Owner questions (crew-ask on #2340), answered

Answered by the owner 11 Nov ~19:20: Q1 (a) "duplicate is actually proposal yeah", a quotation source copies as a
proposal for the new party; Q2 (a) "signature is not copied yeah", the copy is signed again. Both match the build.
