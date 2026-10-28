# COMPLAINT-APPEAL-WORDING browser pass (agent-browser 0.27.0, headless, cloud sandbox)

Round 1 (complaints) below; round 2 (every form, owner 28 Oct) after it.

Sandbox DB `sorento_browse` (bootstrapped CI schema), seeded by
`documentation/plans/audit/evidence/audit-trail-resubmitted/harness/seed_browse.py` (complaint `ZZT26-0219`,
three reject / resubmit cycles, now `resubmitted`) plus `harness/seed_rejected.py` (complaint `ZZT26-0220`,
left `rejected`, same portal contact). All names invented. Backend uvicorn :8000, frontend `npm run dev` :3000.
Staff side reached by sidebar: Complaints > Complaints, then the row.

| Check | Screenshot | Result |
|---|---|---|
| Staff list: ZZT26-0219 status cell reads "Appealed", ZZT26-0220 "Rejected" | 01-list-1280.png | PASS |
| Staff list Status filter offers "Appealed" (no "Resubmitted") | 02-filter-1280.png | PASS |
| Staff detail header reads "Appealed"; no "resubmit" anywhere in the page text | 03-detail-1280.png | PASS |
| Audit trail: every appeal row is headed "Appealed", summary "status: rejected → appealed", field diff kept | 04-trail-1280.png | PASS |
| 375px: same trail, no horizontal overflow (scrollWidth 360 = clientWidth 360) | 05-trail-375.png | PASS |
| Portal landing (Complaint tab): ZZT26-0219 "Appealed", ZZT26-0220 "Rejected" | 06-portal-landing-1280.png | PASS |
| Portal rejected complaint: button "Appeal complaint", no "resubmit" in page text | 07-portal-appeal-button-1280.png | PASS |
| Confirm dialog: "Appeal this complaint?" with "Appeal complaint" action | 08-portal-confirm-1280.png | PASS |
| 375px portal form: "Appeal complaint" button fits, no overflow (375 = 375) | 09-portal-appeal-button-375.png | PASS |
| Public complaint view link (`/view/complaint?token=`): Status reads "Appealed" | 10-public-view-1280.png | PASS |

Not driven end to end: the send itself. The synthetic complaint lacks required fields whose lookup sets do not
exist in an empty schema, so client validation stops it before the request. The "Appealing..." / "Appealed."
strings are the same `VERB_DOING` / `VERB_DONE` map the button and confirm read from.

Harness notes: the portal token needs `verified_at` set (OTP gate); the public view needs the
`public_view_links` module installed for the default tenant.

## Round 2: every form

Extra seed `harness/seed_every_form.py` (one `resubmitted` stock inquiry, purchase request, sponsorship form,
new product application, project registration and quotation; one rejected stock inquiry on the portal contact).
Migration `appeal_0001_appeal_labels` was run with `alembic upgrade head` on the sandbox DB, whose quotation graph
still held the old seeded "Resubmitted" / "Resubmit for approval" labels; afterwards it read "Appealed" / "Appeal".
Staff pages reached by sidebar (Procurement, Project Sales Admin, Project Sales); the two 375px staff shots reopen
pages already reached that way.

| Check | Screenshot | Result |
|---|---|---|
| Stock inquiries list: ZZT-SI-0001 reads "Appealed" | 11-stock-inquiries-1280.png | PASS |
| Stock inquiry detail: header "Appealed"; audit create row "status: ∅ → appealed" (was "resubmitted", fixed in this round) | 12-stock-inquiry-detail-1280.png | PASS |
| New product applications list: "Appealed" | 13-npa-list-1280.png | PASS |
| Purchase requests list: "Appealed" | 14-purchase-requests-1280.png | PASS |
| Sponsorship forms list: "Appealed" | 15-sponsorship-forms-1280.png | PASS |
| Purchase request detail: pill "Appealed" (it read "Submitted" before this round), no "resubmit" in page text | 16-purchase-request-detail-1280.png | PASS |
| Projects board: the registration card reads "Appealed" | 17-projects-1280.png | PASS |
| Project detail: "Appealed" where the code would be | 18-project-detail-1280.png | PASS |
| Project Quotations tab: ZZT-Q-0001 status "Appealed" (label from the migrated DB row) | 19-project-quotations-1280.png | PASS |
| Quotation detail: "Appealed" | 20-quotation-detail-1280.png | PASS |
| Portal Stock Inquiry list: "Appealed" | 21-portal-stock-inquiries-1280.png | PASS |
| Portal rejected stock inquiry: button "Appeal stock inquiry" | 22-portal-si-appeal-button-1280.png | PASS |
| Confirm: "Appeal this stock inquiry?" / "Appeal stock inquiry" | 23-portal-si-confirm-1280.png | PASS |
| 375px: portal button fits, no overflow (375 = 375) | 24-portal-si-appeal-button-375.png | PASS |
| 375px: purchase request detail, no overflow (360 = 360) | 25-purchase-request-detail-375.png | PASS |
| 375px: projects board, no overflow (375 = 375) | 26-projects-375.png | PASS |

Not driven in the browser: the quotation "Appeal" button (a quotation with no priced lines needs no approval, so it
offers Sign) and the dealer-kit edition "Appeal" button (no dealer-kit page chain in an empty schema). Both are
covered by `QuotationDocumentClient.test.tsx` C3 and `EditionDetail.test.tsx`; the quotation button's label comes
from the migrated edge row checked above.
