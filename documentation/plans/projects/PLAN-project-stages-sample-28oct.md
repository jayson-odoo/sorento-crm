# PLAN: project pipeline stages incl. Sample Submission, via the status graph

Status: Plan - behaviour card filed (`CARD-project-stages-sample-28oct.md`, 28 Oct), waiting on the owner's
answers to Q1-Q5. Drafted on the recommended answers; revised when they land. Track: size M, NOT the small fix
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

- Layer: graph edges are DATA (status graph rows); the one automatic rule is a service hook beside the
  existing first-PO hook, not an evaluator for `trigger_mode = auto` edges (`derived.py` ships no evaluator;
  one rule does not earn one - trigger to build it: a third automatic stage rule).
- Shared mechanism: the body of `_advance_to_po_received` becomes one helper
  `advance_project_to(db, project, key, *, reason)` (status lookup with template-scope fallback, forward-only
  by sort_order, legal-edge check), used by both the PO hook and the new sample-request hook. The PO hook keeps
  its return value and route contract (`status_moved_to_po_received`).
- Fixed classes: every rung reachable along the ladder; every automatic move legal per the graph; every
  automatic move leaves a `stage_changed` activity row.

## Slices

1. Migration `stg_0001_project_ladder_edges` (revision id <= 32 chars): INSERT the 12 manual edges where both
   rungs exist in the default project graph and the edge does not; NULL-only fill of win % / stale days for
   `final_negotiation` (85 / 7) and `sponsorship_form` (90 / 7) [Q5]. Downgrade removes only those exact
   edges. Same SQL, idempotent, to `crew/state/migrations/PROJECT-STAGES-SAMPLE.sql`.
2. BE: shared advance helper; `sample_request_service.submit` calls it for the linked project with key
   `sample_submission` [Q1]; never raises into the submit; writes `stage_changed` with the request number.
3. FE: pill colours for the three rungs; submit invalidates the project detail + list queries.
4. Text: MCP / connector / route descriptions name the live rungs (read from the graph where cheap, else text).

## Tests (tester writes red first, from the UAC)

- pytest `tests/test_project_stages_ladder.py` (new): migration edges + idempotence + fresh-DB no-op;
  sample-request submit moves Spec In -> Sample Submission; no move from Registered / beyond / unapproved /
  no project / second request; activity row; first PO from Final Negotiation and Sponsorship Form moves to
  PO Received.
- vitest `ProjectStatusAction.test.tsx`: from Spec In the primary is "Sample submitted" and PO received sits
  in the overflow; pill test for the three keys.
- Direct suites to re-run: `tests/test_project_samples_pos_routes.py`, `tests/test_sample_requests_core.py`,
  `tests/test_status_engine.py`, `tests/test_project_mcp_surface.py`.

## Out of scope (named triggers)

- Realigning the code seed to the document ladder: 14 test files pin quoted / tendering; trigger = a second
  install that seeds a fresh graph.
- Automatic Sponsorship move [Q4] and Final Negotiation <-> critical flag coupling [Q3].
