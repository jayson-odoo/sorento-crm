# UAC: AGENT-QUOTE-COMPARE

Status: final (crew answers 10 Nov: Q1 a, Q2 a, Q3 a, Q4 a, Q5 fix both candidates, crew has no prod access).

Journey: a staff user opens a project page, opens the AI agent and asks "compare the two quotation for this
project". The agent reads both documents' lines and answers with one compact table (items, qty, prices, discounts,
totals), in a few rounds, under the user's own access. If anything fails after it has read data, it still says what
it read; it never ends on a bare "could not answer".

## A. Page context (cause a)

- AC-A1 A panel turn whose open page path holds a UUID (`/project-sales/<uuid>`) may pass that UUID as an id
  argument in round 1: `crm_project_quotations_list(project_id=<uuid>)` is not refused.
- AC-A2 A UUID that is neither in the page path nor in a tool result this turn is still refused "Unknown id".
- AC-A3 Seeding grants nothing: a page UUID for a project the user cannot read still gets the route's own refusal.

## B. Refusals that teach the right call (cause b)

- AC-B1 "Unknown id in `project_id`" names where a project id comes from (the open page, `crm_projects_find`); it
  does not send the model to `crm_resolve` for a kind `crm_resolve` cannot search.
- AC-B2 `crm_resolve`'s description says which kinds it resolves and that projects and complaints are found with
  their own find tools.
- AC-B3 `crm_resolve({"term": "PPF2611004"})` and `crm_resolve({"kind": "project", "text": "PPF2611004"})` are
  refused with a message that states the accepted shape: `terms` (list of text) and `kinds` (list, naming the
  kinds).
- AC-B4 An unknown argument on any catalogue tool is refused with the tool's accepted argument names (guards and
  `view` never listed).

## C. Clean ids, no 500 (cause c)

- AC-C1 `project_id=" <uuid> "` (padded) is forwarded as the bare UUID and the call answers ok.
- AC-C2 A list (`["<uuid>"]` or a JSON-array string) sent to a single-id argument is refused "one id" before any
  call; a `*_ids` argument still takes a list.
- AC-C3 Backend `GET /api/v1/project-sales/projects/{padded uuid}/quotations` answers 200 with the project's
  quotations, not 500.

## D. Never a bare failure (cause d)

- AC-D1 Round or token limit hit, then the final answer call fails (provider error or timeout): status `limited`,
  reply says it could not finish, why in plain words (did not respond in time / provider error), and lists the
  labels of what it read. Never "The agent could not answer: the model provider failed."
- AC-D2 A failed round after tool results, then a failed final call: same as D1.
- AC-D3 A provider failure before any tool result is unchanged (`failed`, fixed text).
- AC-D4 The trace records the provider failure's exception class (no key, no prompt text).

## E. Compare quotations (cause e)

- AC-E1 New panel read `crm_project_quotation_lines`, offered on staff panel turns only, gated by the quotation
  routes' READ slugs (`projects.projects.view` or `projects.projects.view_own`); a user with neither is denied.
- AC-E2 `{project_id}` alone returns every document of the project with each scope's CURRENT version: ref
  (document number), scope, version number, total, and lines (product code, description, qty, uom, list price,
  unit price, discount %, line total).
- AC-E3 `refs` narrows to documents (`PRJQ-2026-0006`) and to issued revisions (`PRJQ-2026-0007-B` returns the
  versions that revision pinned, with their lines and the revision's totals). A ref that matches nothing comes back
  under `not_found`, never an error.
- AC-E4 A document with no lines says so (empty `lines`, total 0), e.g. PRJQ-2026-0011 on PPF2611006.
- AC-E5 A project of another company, or an unknown project id, is refused like the quotations route (404),
  never an error.
- AC-E6 Output stays under the result cap; when it would not, rows are capped and the count of the rest is given.

## F. Live (owner rule)

- AC-F1 The owner's question, on the panel of a dev project with 2+ documents (PPF2611008: PRJQ-2026-0013 and
  QT-2026-0003), answers LIVE in at most 4 rounds with one compact comparison table, x3 runs; rounds, tokens and the
  answer recorded in crew-done.
