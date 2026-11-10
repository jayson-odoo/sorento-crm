# PLAN: Quotation cover page: source-field rows and the sales cover sheet layout (QUOTE-COVER-FIELDS)

**Status:** Plan. Behaviour card + mock v1 (`documentation/mockups/QUOTE-COVER-FIELDS/index.html`) filed as crew-ask on PR #2307; build waits for owner approval.
Track: M (expected migration for the missing sources, see card Q2). Follow-up to QUOTE-COVER-DESIGN
(`documentation/plans/projects/PLAN-quote-cover-design-02nov.md`).

## Journey

Owner, 10 Nov ~14:55 MYT: the cover page designer (Project Sales > Configuration > Quotation Templates > Cover page)
needs more fields, laid out like the sales team's real cover sheet: a "Propose to:" band with two columns, a
"Project Title:" band, a "Term & Condition:" band, a "Prepared by," signature block and a company footer.

Owner ruling, 10 Nov ~15:00 MYT:
1. Reference No. = the document number ONLY. The project title gets its own Project Title band.
2. Every designer row has a SOURCE FIELD the admin picks from a list, plus the editable label and
   show/hide/drag as today. Adding a row = pick a source + label. Defaults reproduce today minus the
   project title in Reference No.

## Today (origin/main a4af6565)

- Rows are a fixed tuple of 12 keys: `sorento_crm_backend/app/services/quotation_cover_service.py:24-37`,
  refused when unknown `:99-100`, all 12 required `:109-110`.
- Reference No. appends the project title: `quotation_cover_service.py:133-138`.
- Values per key: `issue_values` `quotation_cover_service.py:242-270`.
- Designer: `sorento_crm_frontend/app/(protected)/project-sales/quotation-templates/components/QuotationCoverDesigner.tsx:216-342`.
- One active design per company: partial unique index `sorento_crm_backend/app/models/projects.py:1340-1346`.

## Source field registry (draft, see the behaviour card)

One dict in `quotation_cover_service.py`: source key -> caption, default label, resolver. Rows become
`{source, label, shown}` (plus a section once Q1 is answered). Validation accepts any known source.

Open questions and the full source list with file:line live in the lane PR's behaviour card.
