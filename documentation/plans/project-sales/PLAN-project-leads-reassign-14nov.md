# PLAN: Project leads list + reassign back (PROJECT-LEADS-REASSIGN)

Status: Plan (behaviour card filed, waiting on answers). Track: M, LEAD pattern.

## Ask (owner, 14 Nov)

1. Access card: ONE list of every lead on the project (primary + secondary), primary marked,
   each row salesperson / date / how they found it / current owner. Reassign ownership between
   any of them, either direction, including back to the primary, through the EXISTING reassign
   dialog. Every reassignment shows in Activity. No sideways scroll.
2. Overview tab: single column (cards stacked full width), same cards and fields.

## Discovery (what exists today)

| Piece | Where | Today |
| --- | --- | --- |
| Secondary lead = takeover request `kind='dispute'` | `sorento_crm_backend/app/models/projects.py:570` | pending / approved / rejected, one decision, ever |
| Approve a secondary lead | `project_service.decide_takeover_request` `app/services/project_service.py:609` | moves owner, old owner becomes collaborator (`:671-674`), records `owner_reassigned` activity (`:680`) |
| Notify on reassign | `project_notify_service.notify_reassigned` `app/services/project_notify_service.py:222` | new + previous owner, dedup key `<request id>:reassigned` (once per request) |
| Plain owner change | `project_service.update_project` `app/services/project_service.py:1452` | manager only; NO activity event, NO collaborator, NO notification |
| Reassign dialog | `ReassignProjectDialog.tsx:37` | pending interests first; pick one = decide(approve), anyone else = PUT owner_user_id |
| Access card grid | `ProjectAccessPanel.tsx:202` | dispute requests only, wide PanelDataGrid with Status |
| Primary | none stored | project `created_by` / `created_at`, `lead_source`, `lead_created_at` (lead's raiser) |
| Overview layout | `ProjectDetailClient.tsx:517` | `grid md:grid-cols-2` |

Gap behind "can't reassign back": once a secondary lead's request is approved it is decided for
good, and the only way back to the primary is the plain owner update, which leaves no Activity
row, no notification and does not keep the outgoing owner as a collaborator.

## Direction (pending crew answers)

One backend function `reassign_project_owner(db, project, to_user_id, actor)` that both the
dispute-approve branch and the owner update call: sets owner, keeps the outgoing owner as a
collaborator, records `owner_reassigned`, notifies. The Access card list is built from the
project's primary (registrant) plus every secondary-lead request (pending and decided), with
"Current owner" derived from `project.owner_user_id`. Row right-click "Reassign to <name>" opens
the existing `ReassignProjectDialog` with that person preselected.
