# AUDIT-TRAIL-RESUBMITTED browser pass (agent-browser, headless, sandbox)

Sandbox DB `sorento_browse` (copy of the bootstrapped CI schema), seeded by `harness/seed_browse.py`
(all names invented). It writes complaint `ZZT26-0219` through three reject / resubmit cycles with the
audit listeners on and the real actor stamped: the first two resubmits in the pre-#1925 shape
(status rejected -> submitted), the third through today's `PortalService.submit_draft` (-> resubmitted).
Backend uvicorn :8000, frontend `npm run dev` :3000. Navigated by sidebar: Complaints > Complaints, then
the row. No console errors.

| Check | Screenshot | Result |
|---|---|---|
| Trail headings, oldest first: Create, Update, Rejected, Update, Resubmitted, Update, Rejected, Resubmitted, Update, Rejected, Resubmitted | 01-trail-1280.png | PASS |
| Past resubmits read "status: rejected → resubmitted" with the field diff (product code, defect description) and "by Portal: Customer A" | 01-trail-1280.png | PASS |
| New resubmit (#1925 path) reads the same | 01-trail-1280.png | PASS |
| 375px: same rows, no horizontal page overflow (scrollWidth 360 = clientWidth 360) | 02-trail-375.png | PASS |

Harness note: the sandbox tenant has no module rows, so the frontend module route guard redirects every
page home; the seed installs the `complaints` module for the default tenant.
