# PLAN: Contacts list Companies column matches the contact detail (CONTACT-COMPANIES-COL)

Status: Review (fix 9673c44c on PR #2410). Track: small fix (no migration, no auth change: the superadmin read gate is kept).

Owner 14 Nov (side bug from the #2256 hand test): "the company here does not tally with the company here".
List column "Companies" showed one company; the same contact's detail page showed two.

## Cause (two different definitions under one label)

| Screen | Source | Meaning |
| --- | --- | --- |
| Contacts list, column "Companies" + Company filter | `contact_customer_service.customer_companies_by_contact` (sorento_crm_backend/app/services/contact_customer_service.py:274), called at contact_service.py:186, sent as `customer_companies` (contact_service.py:214), rendered at ContactsList.tsx:484 | Companies of the contact's LINKED CUSTOMERS (`respond_contact_customers` -> `customers.company_id`), PR #1930 |
| Contact detail, Profile, "Companies" chips | `ContactService.list_contact_companies` (contact_service.py:626) via `GET /contacts/{id}/companies` (contacts.py:658, superadmin-only), rendered at contacts/[id]/page.tsx:41 and :165 | The contact's COMPANY GRANT (`respond_contact_companies`), edited in ContactEditDialog and by tags; decides which company's rows the chatbot may tell the contact about |

The owner's case: three linked customers, all in one company, but a grant of two companies. Both
screens are "correct" for their own definition; the label is the same, so they disagree.

## Options (ruling asked on the PR)

(a) Companies = the grant everywhere: list column, its sort and the Company filter read
`respond_contact_companies` through ONE shared batched function that the detail endpoint also uses.
(b) Companies = linked customers' companies everywhere: detail chips read
`customer_companies_by_contact`; the grant moves to its own label ("Company access").
(c) Keep both, rename one so they no longer share a label.

## Rulings

- Owner 14 Nov ~13:40: "it should follow the detail page" = (a): Companies = company access everywhere.
- Crew 14 Nov 13:45: company access stays superadmin-only to read (read-gates plan :138, tests
  test_user_management_read_gates.py :845 / :860 unchanged). For superadmins the list column, sort and
  Company filter show company access; for everyone else the column and filter are hidden (not "-").

## Fix

- ONE shared function `company_access_by_contact` (contact_service.py) backs the detail endpoint
  (`ContactService.list_contact_companies`) and the list's column (`companies` field, was
  `customer_companies`), sort and Company filter. `customer_companies_by_contact` is removed.
- Gate `can_read_company_access(redact_sections)`: the list already carries the superadmin verdict as
  the redacted `companies` tag-settings section. Not readable: values withheld, filter matches nothing,
  sort falls back to the default order.
- FE: `isSuperadminUser` hides the column, the filter (and drops a `company` URL value) and the detail
  page's Companies field; the detail page reads through the shared `getContactCompanies` service.
- Tests: tests/test_contacts_company_filter.py (rewritten to the new definition),
  ContactsList.companies.test.tsx, contacts/[id]/page.companies.test.tsx.
- Guide: documentation/user-guides/user-management/contact-companies.md.
