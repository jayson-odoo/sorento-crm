# PS-SAMPLE-TRACKING browser evidence (cloud sandbox, 2 Nov 2026)

agent-browser 0.27.0, headless, against `next dev` + uvicorn on a throwaway sandbox database
(bootstrapped with `scripts.bootstrap_env`; fake rows only: SR-000001/2, CG-SBX-0001/2, one Overall
Tracking `orders` row CG-SBX-0002 delivered 24 Nov 2026).

| File | What it shows |
| --- | --- |
| 01-start-processing-dialog-1280.png | Change to processing opens the date answer; the button is disabled until answered |
| 02-past-date-refused-1280.png | No + a past date: "The proposed date cannot be in the past." |
| 03-detail-proposed-date-1280.png | Sample team: Proposes 09/12/2026 + New date + the note |
| 04-link-consignment-picker-1280.png | Link consignment: live CGs of the company, CG number + debtor + date |
| 05-delivered-by-consignment-1280.png | Delivered 24/11/2026 (Order Tracking), Consignment No CG-SBX-0002 - 21/11/2026, no Mark delivered |
| 06-list-new-date-badge-1280.png | List Delivery column: 15/12/2026 + New date |
| 07-stage-filter-delivery-1280.png | Filters > Stage = Delivery lists the delivered request |
| 08-list-stage-delivery-375.png, 09-detail-delivered-375.png | 375px: no horizontal page scroll (scrollWidth 375) |

Notes:
- Navigation was by sidebar clicks from `/` (Project Sales > Sample Requests). On the blank sandbox
  DB the Project Sales module had to be installed for the tenant first (`install_modules`), or the
  sidebar hides it.
- The headless date input ignores typed keys, so the proposed date was set with the native value
  setter plus an `input` event (what React receives from a real pick).
- The audit trail prints `date_answered_by` as the raw user id, the same as every other user FK on
  this audit trail (existing behaviour, not changed here).
