# COMPLAINT-APPEAL-WORDING browser pass (agent-browser 0.27.0, headless, cloud sandbox)

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
