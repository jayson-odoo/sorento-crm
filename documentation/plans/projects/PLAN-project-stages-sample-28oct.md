# PLAN: project pipeline stages incl. Sample Submission, via the status graph

Status: Build - owner answered the card 28 Oct ~19:45 (Q1 mirror Spec In -> form on click, Q2 strict, Q3 a,
Q4 sponsorship form on click, Q5 no dials). Track: size M, NOT the small fix
track (carries a migration). UAC: `project-stages-sample-acceptance-criteria.md`.

## Owner ask (28 Oct, verbatim)

"i think need to have 1 state is sample request, maybe can use our status graph right, cause I want to move
progressively to sample request like mentioned in this document"

Document stages ("2. Pipeline Stages (Overview)"): 1 Project Registration, 2 Spec-in / Quotation,
3 Sample Submission, 4 Final Negotiation, 5 Sponsorship, 6 Purchase Order (PO).

## Measured today

Status graph rows, entity `project`, default scope (crew dev DB sorento_prod_1020; dev copy sorento_cagent_stack
has the same 9 keys and 16 edges, 0 template-scoped rows):

| key | label | sort | flags | win % | stale days |
| --- | --- | --- | --- | --- | --- |
| identified | Identified | 0 | | 10 | 21 |
| registered | Registered | 1 | initial, default | 25 | 30 |
| specified | Spec In | 2 | | 40 | 21 |
| sample_submission | Sample Submission | 4 | (seed's tendering, re-keyed by admin) | 75 | 7 |
| final_negotiation | Final Negotiation | 5 | created 15 Oct, no edges | - | - |
| sponsorship_form | Sponsorship Form | 6 | created 15 Oct, no edges | - | - |
| po_received | PO Received | 7 | terminal | 100 | - |
| lost | Lost | 8 | terminal | 0 | - |
| dormant | Dormant | 9 | terminal | 0 | - |

16 edges, all `trigger_mode = manual`. No edge INTO `sample_submission`, `final_negotiation` or
`sponsorship_form`. The code seed (`app/services/project_seed_service.py:51-127`) still describes
quoted / tendering and is skipped once any project status exists (`:334-340`), so prod's graph is admin-owned.

## Code map (origin/main 9e41d84fc2)

- Storage: `projects.status_id` FK to `statuses.id` (`app/models/projects.py:279`); serializer adds
  `status_key`, `status_label` (`app/services/project_service.py:845-847`).
- Manual move: `POST /api/v1/project-sales/projects/{id}/status` (`app/api/v1/projects/projects.py:458`,
  `projects.projects.edit`) -> `project_service.change_status` (`project_service.py:1366-1420`), edge check
  `status_service.assert_transition_allowed` (`app/services/status_service.py:169-219`), `stage_changed`
  activity (`project_service.py:1411-1419`).
- Automatic move precedent: first PO -> `_advance_to_po_received` (`app/services/project_po_service.py:209-271`),
  legal edge only, silent no-op otherwise, no activity row.
- Sample request submit: `sample_request_service.submit` (`app/services/sample_request_service.py:477-488`);
  staff route `app/api/v1/projects/sample_requests.py:213-225`, portal `app/api/v1/public/portal_sample_request.py:193`.
- Header: `ProjectDetailClient.tsx:235-359`; moves from the whole graph in the browser,
  `availableStatusMoves` / `splitStatusMoves` (`[projectId]/components/ProjectStatusAction.tsx:43-111`);
  primary = first non-terminal forward edge. Pill colours `_shared/components/ProjectStatusPill.tsx:19-28`.
- Sample request mutations refresh only sample-request queries (`sample-requests/hooks/useSampleRequests.ts:96-99`).
- Stale descriptions listing quoted / tendering: `sorento_crm_mcp/sorento_crm_mcp/catalog.py:1726-1729`,
  `app/services/analytics_connector/reused_tools.py:795-798`, `app/api/v1/projects/projects.py:166-167`.
- Readers that need no change (read win % / stale days / labels from the graph): forecast
  (`app/services/project_forecast_service.py:207-223`), staleness sweep (`project_staleness_service.py:63-79`),
  pipeline board columns (`pipeline/components/PipelineClient.tsx:186-192`), grid Stage column
  (`_shared/components/ProjectsGrid.tsx:150-165`).

## Architecture

- Layer: graph edges are DATA (status graph rows, one idempotent migration). The stage action's "open the form"
  is FE only, in the one place that already does it for Spec In (`ProjectDetailClient.tsx:200-219` `moveTo`).
  No backend hook, no `trigger_mode = auto` evaluator (owner Q1: the move happens on click, like Spec In).
- Shared mechanism: `moveTo`'s single `if specified` becomes one key -> route map
  (`specified` -> quotation new, `sample_submission` -> sample request new, `sponsorship_form` -> sponsorship
  form new), still forward-only and still only after the move lands. Matched on the rung KEY so a relabel
  cannot break it.
- Fixed classes: every rung reachable along the ladder; every forward move into a rung that has a form opens it
  with this project filled in; back moves never open a form.

## Slices

1. Migration `stg_0001_project_ladder_edges` (revision id <= 32 chars): INSERT the 12 manual edges where both
   rungs exist in the default project graph and the edge does not. No dial fill (Q5). Downgrade removes only
   those exact edges. Same idempotent SQL to `crew/state/migrations/PROJECT-STAGES-SAMPLE.sql`.
2. FE stage action: `moveTo` key -> route map (Spec In unchanged; Sample Submission; Sponsorship Form).
   Pill colours for the three rungs (`_shared/components/ProjectStatusPill.tsx:19-28`).
3. FE sponsorship prefill: `procurement-management/sponsorship-forms/new/page.tsx` reads `?project_id=` like
   `sample-requests/new/page.tsx:13-31` and passes it to `PurchaseRequestForm`, which fills the project link
   (id + title). Staged LAST because #1953 rewrites both files (see Dependency).
4. Text: route / MCP / connector `status_key` descriptions name the live rungs, not quoted / tendering.

## Dependency on PORTAL-P4-REQUESTS #1953

#1953 (open, Build, itself stacked on #1944) keeps `/procurement-management/sponsorship-forms/new` and edits
`new/page.tsx` (Suspense wrapper) and `PurchaseRequestForm.tsx` (+197 lines). Not stacked on it (a stacked PR
gets no CI until retargeted, and #1953 is stacked on #1944 already). Slices 1, 2 and 4 are independent. Slice 3
touches the two shared files minimally (one search param, one prop, one prefill) and the PR asks merge order
#1953 first, then this lane rebases onto main and resolves; if the owner wants this lane first, #1953's worker
gets a crew-note naming the exact lines.

## Tests (tester writes red first, from the UAC)

- pytest `tests/test_project_stages_ladder.py` (new): migration adds the 12 edges on a prod-shaped graph, runs
  twice without duplicates, keeps an admin-made edge's label, is a no-op on the seed graph, leaves the 16 old
  edges; manual move refusals for skips (422); first PO from Final Negotiation / Sponsorship Form moves to
  PO Received.
- vitest `ProjectStatusAction.test.tsx` (+ detail test for `moveTo` routes): primary per rung; forward move into
  sample_submission / sponsorship_form pushes the form route with project_id; back moves push nothing; refused
  move pushes nothing; Spec In unchanged. Pill colours. Sponsorship new page prefill from `?project_id=`.
- Direct suites to re-run: `tests/test_project_samples_pos_routes.py`, `tests/test_status_engine.py`,
  `tests/test_project_mcp_surface.py`, `tests/test_project_seed.py`.

## Out of scope (named triggers)

- Realigning the code seed to the document ladder: 14 test files pin quoted / tendering; trigger = a second
  install that seeds a fresh graph.
- Final Negotiation <-> critical flag coupling (Q3 a: independent).
- Opening the form from a kanban drag: the board never opened the quotation either (`PipelineClient.tsx:430-434`).
