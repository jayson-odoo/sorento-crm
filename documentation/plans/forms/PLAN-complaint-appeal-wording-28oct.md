# PLAN: complaint appeal wording (COMPLAINT-APPEAL-WORDING)

Status: in progress (small fix track: wording only, no migration, no auth change)

## Ask

Owner, 28 Oct 2026, after #1942 went live (a complaint's audit trail reads Rejected /
Resubmitted): "can we change to Appealed and the button to Appeal instead of Resubmitted and
Resubmit".

## Decision

- Complaints only. A complaint shows **Appealed** where it showed "Resubmitted" (status pill,
  list filter, portal landing, audit trail heading and summary) and **Appeal** where it showed
  "Resubmit" (portal send button, confirm dialog, toast).
- Display only. The stored status value stays `resubmitted`: the backend, the status engine,
  the chatbot parser, n8n and every other form share that value
  (`app/services/submission_status.py`), so renaming it is not trivial and would need a
  migration. The label layer maps it.
- Other forms (stock inquiry, purchase request, sponsorship, NPA, ...) keep "Resubmitted" /
  "Resubmit" until the owner decides; the PR lists where they show it.

## Acceptance

1. A complaint with status `resubmitted` reads "Appealed" on the staff list, staff detail, the
   linked-complaints panel and the portal landing; the staff list status filter offers
   "Appealed".
2. A complaint's audit trail heads a rejected -> submitted / resubmitted move "Appealed" and its
   summary reads "Rejected → Appealed".
3. A rejected complaint on the portal shows an "Appeal complaint" button, an "Appeal this
   complaint?" confirm, "Appealing..." while sending and an "Appealed." toast.
4. Every non-complaint form still reads "Resubmitted" / "Resubmit".
