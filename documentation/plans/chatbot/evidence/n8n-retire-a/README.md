# N8N-RETIRE-A browser pass (cloud sandbox, 12 Nov 2026)

Stack: throwaway DB `sorento_browse` (copy of the seeded CI DB) with one invented superadmin
(`documentation/plans/chatbot/evidence/console-synth-envelope/harness/seed_browse.py`) and one
default `system_settings` row (the empty seed has none, so Save answered 404 until it existed; prod
has the row). No respond.io key, no SMTP: nothing can leave the sandbox. Backend uvicorn :8000,
frontend `next dev` :3000. Head 955d28d85c. Reached by sidebar from `/`: Users & Access > Settings >
Chatbot tab.

| Step | Width | Result |
| --- | --- | --- |
| 01 page opens | 1280 | PASS. "Bot replies sent by" sits under "Direct ingress", reads **n8n** (default). |
| 02 options | 1280 | PASS. n8n / CRM for listed contacts / CRM for all. |
| 03 listed contacts | 1280 | PASS. "Reply sender contacts" box appears only for this option; saved, reload keeps it; DB `contacts` + the id. |
| 04 CRM for all | 1280 | PASS. Box hidden; saved; DB `all`. |
| 05 CRM for all | 375 | PASS. Nothing clipped, no sideways scroll (page width 360). |
| 06 back to n8n | 375 | PASS. Saved; reload reads n8n; DB `n8n` (rollback is one change). |
