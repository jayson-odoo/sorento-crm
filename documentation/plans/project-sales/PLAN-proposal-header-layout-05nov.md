# PLAN: Proposal / quotation detail header like Order Inquiry; lines on Header tab

Status: Plan (mock v2 pending owner OK; v1 note 12:20: drop the area header row in view, Record outcome to the gear). Track: small fix track (FE only, no migration, no RBAC change).

Lane: PROPOSAL-HEADER-LAYOUT. Owner request 5 Nov 2026 12:20 MYT.

## Journey
A sales user opens a proposal (or quotation) from the project page and wants the header to read
like Order Inquiry detail: number + status badge inline, one subtitle line, actions on the right,
and the lines visible on the Header tab without switching tabs.

## Scope
- Header card: number + status badge inline, one subtitle line, right side gear, printer (count), primary send.
- Remove the customer line under the title and the "The customer holds this version..." hint text.
- Lines table moves onto the Header tab under the header card; the Lines tab is removed.
- Spec sheet tab internals untouched.

## Facts (read from the code)
- Proposal and quotation are ONE page: `quotation-documents/[documentId]`, the noun comes from
  `documentNoun` (`_shared/services/quotationDocumentService.ts:213`). Both change.
- OI's header card is inline (`order-inquiries/[id]/components/OrderInquiryDetail.tsx:767-971`), not shared.
  It is extracted as `components/common/RecordHeaderCard.tsx` and used by OI and the proposal page.
- The proposal page already has a pager (`QuotationDocumentClient.tsx:350`, project's documents).
- Header today: `QuotationDocumentClient.tsx:315-501`; tabs: `QuotationDocumentTabs.tsx:32`;
  lines panel: `QuotationScopesTab.tsx`, routed at `(view)/lines/page.tsx`.

## Mock
`mockups/proposal-header-layout-05nov.html` (1280 + 375 + behaviour card, 5 questions). Build waits for the owner's OK.
