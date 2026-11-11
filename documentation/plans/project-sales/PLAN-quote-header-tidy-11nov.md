# PLAN: QUOTE-HEADER-TIDY (one Issued by, short name in the record card, title in Header, view folds)

Status: built, in review (small fix track: FE only, no migration, no auth/RBAC change, no new ingest).
UAC: `quote-header-tidy-acceptance-criteria.md` alongside. Lane: QUOTE-HEADER-TIDY.

## Owner feedback (11 Nov 2026 ~15:10 MYT), verbatim

"don't need to be by unit here, and can show the project title in the Header section, again even in view the header
and line should be collapsible, then here just show project name so it doesn't clutter"

## Build

1. Header meta block (`QuotationDocumentHeader.tsx` `HeaderDetails`): ONE "Issued by" + "Opened" pair for the
   document, no per-area groups. Picked from the areas' current versions: issued ones win over unissued ones, and
   among those the most recently opened. Our Ref / Your Ref / Date / Total unchanged.
2. Record card subtitle (view `QuotationDocumentClient.tsx`, edit `QuotationFormClient.tsx`): the project short
   name through `projectDisplayName` (`_shared/lib/projectName.ts`, PROJECT-NAME 10 Nov: `projects.name`, title
   when no name yet), not the document's full title.
3. Header read gains a "Project" row: the document's full title (`subject_title`), clamped to two lines with the
   existing `TruncatedTextCell` expand dialog. In an edit session the existing "Project title" textarea stays.
4. View mode: the Header tab wraps the letterhead and the lines each in `components/common/FormSection.tsx`, the
   same fold the edit form uses, open on arrival, no persistence, same folded summaries (shared helpers).

5. Owner addition (11 Nov ~16:30): the primary CTA "Send to Customer A" read as a customer called A. It now
   names the revision and the To party (`recipient_name_snapshot`): "Send rev A to <party>" on a proposal,
   "Send R1 to <party>" on a quotation (R1 already says revision), "the customer" when there is no To party.
   Its menu items read "<same> by email" / "<same> via WhatsApp" and the WhatsApp prompt's title matches.
   One helper, `sendRevisionLabel` (`_shared/services/quotationDocumentService.ts`). The success toast keeps
   "Sent to the customer as <our ref> (R1)": it names the full ref, so it does not read as a name.

Proposals and quotations share these components, so both get it.

## Tests

vitest (red first): one Issued by pair for a multi-area document (latest issued wins); record card subtitle is the
project name; Header shows a Project row with the full title; view Header and Lines fold and unfold.
