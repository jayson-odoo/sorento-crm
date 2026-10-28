# CARD: project stages follow the document, Sample Submission included (PROJECT-STAGES-SAMPLE, size M)

Paths: BE = `sorento_crm_backend/app`, FE = `sorento_crm_frontend/app/(protected)/project-sales`. Code read on
origin/main 9e41d84fc2. Data: status graph rows on the crew dev DB (sorento_prod_1020, `statuses` /
`status_transitions` only) and project rows on the dev copy sorento_cagent_stack (read-only).

## Why PPF2610003 jumps Spec In -> PO received

- The status graph already has the document's rungs: `sample_submission` "Sample Submission" (sort 4, 75%,
  stale 7 d), `final_negotiation` "Final Negotiation" (sort 5) and `sponsorship_form` "Sponsorship Form"
  (sort 6). They were made in the admin editor (Final Negotiation and Sponsorship Form created 15 Oct); no
  code seeds them (seed `BE/services/project_seed_service.py:51-63` still says quoted / tendering).
- But no edge leads INTO any of the three. From Spec In the only edges are PO received, Back to registered,
  Mark lost, Mark dormant (16 edges, all manual).
- The header picks the first non-terminal forward edge, else the first forward edge even if terminal
  (`FE/[projectId]/components/ProjectStatusAction.tsx:43-63`). Spec In has no non-terminal forward edge, so
  the single button is "PO received".
- Final Negotiation and Sponsorship Form have no edges at all, out or in: a project there could never reach
  PO received, and the automatic first-PO move would silently do nothing (`BE/services/project_po_service.py:262-272`).

## Proposed stage ladder (document stage -> rung)

| Doc stage | Rung (key) | Header button there | Gear menu |
| --- | --- | --- | --- |
| 1 Project Registration | Registered (`registered`) | Spec In | Back to identified, PO received, Mark lost, Mark dormant (unchanged) |
| 2 Spec-in / Quotation | Spec In (`specified`) | **Sample submitted** (new) | PO received, Back to registered, Mark lost, Mark dormant |
| 3 Sample Submission | Sample Submission (`sample_submission`) | **Final negotiation** (new) | PO received, **Back to Spec In** (new), Mark lost, Mark dormant |
| 4 Final Negotiation | Final Negotiation (`final_negotiation`) | **Sponsorship** (new) | **PO received**, **Back to sample submission**, **Mark lost**, **Mark dormant** (all new) |
| 5 Sponsorship | Sponsorship Form (`sponsorship_form`) | **PO received** (new) | **Back to final negotiation**, **Mark lost**, **Mark dormant** (all new) |
| 6 Purchase Order | PO Received (`po_received`) | none (terminal) | none |

12 new edges, all manual: 4 forward, 3 back, PO received from Final Negotiation, Lost + Dormant from the two rungs
that have none. Header layout unchanged (one button + gear menu), so no mock.

## Rules

1. Manual moves: one step forward, one step back, plus PO received / Mark lost / Mark dormant from every live
   rung (the PO-from-anywhere edges already exist for the first three rungs and Sample Submission).
2. Automatic move (code): when a sample request linked to a project is SUBMITTED (staff form or portal, both go
   through `BE/services/sample_request_service.py:477` `submit`; portal at `BE/api/v1/public/portal_sample_request.py:193`),
   the project moves to Sample Submission, built like the first-PO move (`project_po_service.py:209-271`):
   only along a legal edge from where the project is, only forward, never on an unapproved project, never an
   error that blocks the sample request. It writes a `stage_changed` activity naming the request (the PO move
   writes none today), so the history shows why it moved and the stale clock restarts.
3. First PO -> PO Received stays as it is; it now works from every rung because the edges exist.
4. Edges land by migration: additive INSERTs, idempotent, only where both rungs exist in the default graph and
   the edge does not. On a fresh DB (CI, seed with quoted / tendering) it adds nothing. The sales manager can
   still rename or re-wire in System > Status graphs (`sorento_crm_frontend/app/(protected)/system-management/status-graphs/page.tsx`, `system.statuses.edit`).
5. Small code: pill colours for the three rungs (`FE/_shared/components/ProjectStatusPill.tsx:19-28` only knows
   the old keys, so they render grey today); the project header refreshes after a sample request is submitted
   (`FE/sample-requests/hooks/useSampleRequests.ts:96-99` invalidates only sample-request data); the MCP /
   chatbot descriptions that still list quoted / tendering (`sorento_crm_mcp/sorento_crm_mcp/catalog.py:1726-1730`,
   `BE/services/analytics_connector/reused_tools.py:795-798`, `BE/api/v1/projects/projects.py:166-167`) name the
   live rungs.

## Real examples (dev copy sorento_cagent_stack)

| Project | Today | After |
| --- | --- | --- |
| PPF2610003 (owner screenshot) | Spec In, button "PO received" | Spec In, button "Sample submitted"; PO received in the gear menu |
| PRJ-000002 "100 UNITS DSTH & 8 UNITS DS SE..." | Spec In, 1 quotation, sample request SR-000001 already delivered | stays Spec In (no backfill, Q5); next submitted request or one click moves it |
| PRJ-000003 "Restroom Refurb" | Spec In, 1 quotation, no sample request | button "Sample submitted" |
| PRJ-000004 "TRX Zus Coffee" | Spec In, nothing linked | button "Sample submitted"; if a PO arrives first it still jumps to PO Received |
| PRJ-000001 "Setia Alam" | PO Received, 1 PO, 3 sales orders | unchanged (terminal) |

## Edge cases

- Second sample request, or a re-sample while in Final Negotiation / Sponsorship: no move (forward only).
- Sample request cancelled after submit: project stays at Sample Submission (no automatic step back).
- Sample request with no project, or project still Registered / Identified (no legal edge to Sample Submission):
  no move. UNVERIFIED how many prod projects sit at Registered with samples (prod reads are off limits).
- Project awaiting registration approval: no move (manual moves and sample requests wait for approval too, `BE/services/project_service.py:459-465` assert_can_write_project).
- Template-forked graphs: none exist (0 scoped project rows); the move uses the template graph if one appears, like the PO move.

## Questions (each with a recommendation)

1. Automatic move trigger. (a) first sample request SUBMITTED moves Spec In -> Sample Submission; (b) on draft
   create; (c) no automatic move, the button only. **Recommend (a)**: a draft can be abandoned, submit is the
   committed act, and it covers the portal too.
2. Skips. (a) strict ladder as above (one forward, one back, PO / Lost / Dormant anywhere; Sponsorship skippable
   only because PO received is allowed from Final Negotiation); (b) also allow Spec In -> Final Negotiation for
   projects that need no sample. **Recommend (a)**: the owner wants projects to move progressively; (b) is one
   editor click later if real projects need it.
3. Final Negotiation vs the "critical" flag. The code models the document's Final Negotiation as a FLAG
   (`is_critical`, "Final Negotiation" in `BE/models/projects.py:295-297` and MCP `catalog.py:1730`) so a
   re-quote does not drag the card backwards; the admin also made a Final Negotiation rung. (a) keep both,
   independent: the rung is the stage, the flag stays "management involved" (no code); (b) entering the rung
   switches the flag on; (c) drop the rung, keep the flag (then the ladder is Sample Submission -> Sponsorship).
   **Recommend (a)**: smallest change, nothing existing breaks, and (b) can follow if management asks.
4. Sponsorship. (a) manual button only; (b) first sponsorship form linked to the project moves it to
   Sponsorship Form automatically. **Recommend (a)** for this lane: the owner asked for sample request; the
   sponsorship form lives in procurement (`purchase_requests`), a second hook is its own small lane.
5. Existing projects and forecast dials. Final Negotiation and Sponsorship Form have no win % (left out of the
   Weighted forecast, `BE/services/project_forecast_service.py:217`) and no stale days (never go stale).
   (a) no backfill of stages; the sales manager sets win % / stale days in the editor (no UPDATE on prod);
   (b) no backfill, migration fills only the empty dials (suggest 85% / 7 d and 90% / 7 d); (c) also move Spec In
   projects that already have a submitted sample request (owner-run UPDATE). **Recommend (b)**: forecast stays
   whole on deploy, values stay editable; no stage backfill because a delivered sample on an old project may
   be from an earlier round.
