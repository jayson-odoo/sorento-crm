# PLAN: Proposal / quotation detail header like Order Inquiry; lines on Header tab

Status: Plan (mock pending owner OK). Track: small fix track (FE only, no migration, no RBAC change).

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

Details, mock and acceptance criteria follow in this file and `proposal-header-layout-05nov-acceptance-criteria.md`.
