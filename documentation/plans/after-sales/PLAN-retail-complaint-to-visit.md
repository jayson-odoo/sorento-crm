# PLAN - From a lodged retail complaint to a technician at the door

**Status:** Phase A (S7a) IMPLEMENTED 2026-08-08, migration 330. **Phase B (S7b) BUILT 2026-08-15
(commits `5a2d15da8`, `a1bb28454`), in Phase 3 review.** Phases C (S8) and D (S9) pre-code.
**UAC (the contract this fulfils):** `retail-complaint-to-visit-acceptance-criteria.md` - every
section below cites the ACs it satisfies.
**Parent:** `PLAN-after-sales-warranty.md` (S1 to S6 built). This plan covers what happens AFTER a
retail complaint lands, up to a technician being sent.
**Decisions:** `adr/0009` Service Job is requester-agnostic - `adr/0010` Warranty Terms scope to
Kind - `adr/0001` status engine is core.
**Branch:** `worktree-after-sales-warranty`. **Ports:** BE 8050; FE 3051 (3050 was taken by another
session's dev server, and taking a port someone else is serving on is not a thing to do quietly).

> **Written late, and that is the finding.** S7a shipped against the UAC alone, with no companion
> plan, because the UAC's rulings were complete enough to build from. The repo requires a plan
> before implementation starts and this file closes that gap retrospectively for Phase A and
> properly for Phase B. Recorded rather than backdated.

---

## Phase A - The resolution decides whether a visit is needed (S7a) - BUILT

`complaint_resolutions.requires_service_job` (migration 330, defaults false, existing rows false).
Setting a requiring resolution raises a Service Job through the same `raise_job_for_source` the
manual button uses, copying the complaint's site, idempotent against any LIVE job (`cancelled`
excluded), post-commit and best-effort. Clearing a resolution never deletes a job.

Phase 1 was deliberately skipped: the FE surface is one boolean on an existing master-data form.
Two bugs found while verifying (`list_resolutions` hand-built its response dict and dropped the new
column; the complaint update never invalidated the service-jobs query) and one test that passed for
the wrong reason (monkeypatched at the definition site, not the use site). Satisfies AC-V1 to AC-V8.

---

## Phase B - Warranty policy configuration (S7b) - THIS SLICE

### Why it exists, in one measurement

The entitlement engine is built, correct and writes assessments. On the dev database it reads
**31 Kinds, 41 Terms and 2 Kind Rules**, and **29 of the 31 Kinds have no rule that can reach
them**. A product whose code matches no rule resolves to no Kind, and no Kind means no verdict. The
feature is not broken; it is unconfigurable, and nothing on any screen says so. This slice is the
editor plus the two counts that make the hole visible.

### Rulings

Thirteen open questions were ruled before the gate and live in the UAC as **AC-P0a to AC-P13**.
They are not restated here; the ones that shape the architecture are:

- **AC-P0a** - the area is `/warranty-management`, module key `warranty`, slugs `warranty.*`. NOT
  `/master-data-management`, which `route-module-map.ts` gates on the *product* module.
- **AC-P2a** - a Supersede action, because AC-P2's refusal alone makes publishing version N+1 a
  two-step performed in the correct order.
- **AC-P2c** - no `EXCLUDE` constraint: `btree_gist` is not installed and prod's permission to
  create it is unverified. Measured, revisitable.
- **AC-P6a** - `resolve_kind` is refactored so the tester and production share ONE ranking.
- **AC-P9 / AC-P12** - the two FK hazards: unscoped nested Terms, and a Kind delete that cascades
  warranty promises out of every policy.

### API contract (pinned here; the FE prototype and the BE gate both build to it)

Mounted in `app/api/v1/__init__.py` under
`Depends(require_module_enabled_with_api_key("warranty"))`, prefix `/warranty-management`. Reads
take `require_permission_with_api_key`, writes take `require_permission`.

Status codes (AC-P15): `POST` 201 with the row, `PATCH` 200 with the row, `DELETE` 200.
Envelope (AC-P14): policies are `ListResponse[T]` = `{data, pagination:{total,page,limit},
empty}`; everything else is a bare array.

```
GET    /api/v1/warranty-management/policies                      DataGrid params -> ListResponse[PolicyResponse]
POST   /api/v1/warranty-management/policies                      PolicyCreate
GET    /api/v1/warranty-management/policies/{id}                 PolicyResponse (same schema as the list row)
PATCH  /api/v1/warranty-management/policies/{id}                 PolicyUpdate; overlap-guarded (AC-P22)
DELETE /api/v1/warranty-management/policies/{id}                 hard; cascades terms (AC-P13)
POST   /api/v1/warranty-management/policies/{id}/supersede       PolicyCreate -> {closed, created} (AC-P2a, P21)

GET    /api/v1/warranty-management/policies/{pid}/terms          ?group_by=kind -> terms grouped (AC-P4)
POST   /api/v1/warranty-management/policies/{pid}/terms          TermCreate
PATCH  /api/v1/warranty-management/policies/{pid}/terms/{tid}    TermUpdate
DELETE /api/v1/warranty-management/policies/{pid}/terms/{tid}    hard; assessments survive (AC-P8a)

GET    /api/v1/warranty-management/kinds                         KindResponse[]
POST   /api/v1/warranty-management/kinds                         KindCreate
PATCH  /api/v1/warranty-management/kinds/{id}                    KindUpdate
DELETE /api/v1/warranty-management/kinds/{id}                    refused while referenced (AC-P12)
GET    /api/v1/warranty-management/kinds/select                  {id, code, name}[] for dropdowns

GET    /api/v1/warranty-management/kind-rules                    ?kind_id=
POST   /api/v1/warranty-management/kind-rules                    RuleCreate
PATCH  /api/v1/warranty-management/kind-rules/{id}               RuleUpdate
DELETE /api/v1/warranty-management/kind-rules/{id}
POST   /api/v1/warranty-management/kind-rules/test               the tester (AC-P6, P6a, P6b, P6c)

GET    /api/v1/warranty-management/defect-types                  {id, label}[] (AC-P18)
```

`PolicyResponse` carries `term_count` on the LIST row, `TermResponse` carries
`assessment_count`, and `KindResponse` carries `rule_count`, `term_count`, `has_no_rules`
and `has_no_terms` (AC-P16, AC-P17). `defect-types` exists because
`covered_defect_type_ids` holds `lookup_options.id` values and the existing lookup endpoint
returns `value` + `label` and never the id.

Every id-bearing relation is ALSO returned resolved, because the repo forbids a UUID on
screen: `PolicyResponse.source_attachment_name`, `TermResponse.kind_code` / `kind_name` /
`covered_defect_type_labels`, `RuleResponse.kind_code` / `kind_name`. Two shapes the
original block left open and Phase 1 pinned: `?group_by=kind` answers
`{groups: [{kind: {id,code,name}, terms: TermResponse[]}], total}`, and
`deciding_rule.id` is NULLABLE - an unsaved candidate rule (AC-P6b) has no id yet.

**Tester request / response**, the one shape worth writing out:

```jsonc
// request
{ "product_code": "SRTWC8152", "category_code": null, "product_name": null,
  "candidate_rule": { "kind_id": "...", "match_type": "model_prefix",
                      "match_value": "SRTWC", "priority": 0 } }   // optional, unsaved (AC-P6b)

// response
{ "resolved_kind": { "id": "...", "code": "water_closet", "name": "Water Closet" },   // or null
  "deciding_rule": { "id": "...", "kind_id": "...", "match_type": "model_prefix",
                     "match_value": "SRTWC", "priority": 0, "is_candidate": false },  // or null
  "matches": [ { "rank": 1, "rule": {...}, "kind": {...}, "matched_length": 5,
                 "is_candidate": false }, ... ] }                                     // AC-P6c
}
```

`matches` is the full ranked list, produced by the SAME `_RuleMatch.sort_key` production uses.
`deciding_rule` is `matches[0]` or null. A tester that answers from its own ranking is worse than
no tester.

### Backend shape

| Thing | File |
|---|---|
| Schemas | `app/schemas/warranty_config.py` (Create/Update/Response per entity, `ListResponse[T]` envelope) |
| Service | `app/services/warranty_config_service.py` - all validation lives here, routes stay thin |
| Ranking refactor | `app/services/warranty_service.py` - add `resolve_kind_match()`, `_RuleMatch.rule`; `resolve_kind` delegates |
| Routes | `app/api/v1/warranty/{__init__,policies,terms,kinds,kind_rules}.py` |
| Slugs | `app/rbac/permission_registry.py` via `_crud("warranty", "policies", ...)` and `_crud("warranty", "kinds", ...)` |
| Migration | `331_warranty_config.py` - `ck_warranty_terms_duration_xor_lifetime`, `sync_permissions`, role grants |
| Manifest | `app/modules/warranty/manifest.py` - set `ROUTER_PREFIX`, extend `EXPORT_FILES_*` |

The migration must do more than call `sync_permissions`: that seeds the slug and grants nobody
(AC-X4, AC-P11). Follow `236_seed_sla_kpi_view_perm.py` for the role-grant half.

### Frontend shape

`/warranty-management` with three tabs. One area, not three sidebar entries, because AC-P7's
zero-rule flag is the whole point and burying it three clicks deep in a separate list is how it
stays invisible.

- **Policies** - DataGrid, create/edit modal, Supersede action, row click opens the policy with its
  Terms **grouped by Kind** (AC-P4: a Water Closet carries three Terms that disagree on all four
  dimensions, so one-at-a-time cannot be checked against the document). Names the active company
  (AC-P10).
- **Kinds** - DataGrid with `rule_count` and `term_count`, zero visibly flagged on both (AC-P7,
  AC-P7a). States that Kinds are shared across companies (AC-P10).
- **Rules** - DataGrid filterable by Kind, plus the tester card (AC-P6, P6b, P6c).

Shared components only: `DataGrid` with `tableLayout: {width:'fixed', columnsResizable:true}`,
`DataGridListToolbar`, `FormDialogScaffold`, `ConfirmDeleteDialog`, `SearchableSelect`. Follow
`master-data-management/lookup-sets/` - the closest existing parent/child modal CRUD, which also
already has a `TestResolveCard` worth reading before writing the tester.

Sidebar: `config/menu.config.tsx` (**the tree is duplicated - edit both copies**) plus a
`{ prefix: '/warranty-management', moduleKey: 'warranty' }` entry in `lib/route-module-map.ts`.

### Phases

1. **Phase 1** - FE on mock fixtures. Every state: loading, empty, error, zero-rule Kind, a Kind
   with three disagreeing Terms, a tester hit and a tester miss.
2. **Phase 2** - red suite authored by a different agent than the implementer, then implementation
   to green, then FE off mocks. Vitest for the new components, pytest for every route (happy path,
   auth denial, validation), Playwright for the config-to-verdict round trip.
3. **Phase 3** - `/code-review`, then the DoD gate.

### Risks

- **The refactor of `resolve_kind` touches the live engine.** `tests/test_warranty_engine.py` (79
  tests) is the regression net and must stay green unchanged - not adjusted to fit.
- **29 unreachable Kinds is a data problem this slice only makes visible.** Seeding the missing
  rules is Sorento's call (open item #27), not this slice's.
- **There is a SECOND hole upstream of a verdict, and S7b does not close it.** Measured
  2026-08-09: all **23** `warranty_assessments` rows are verdict `unknown`, every one with the
  same reason - *"No purchase is linked to this complaint line yet, so there is no purchase date
  to compute cover from."* Not one of them failed for want of a Kind rule. So configuring the
  rules is necessary and NOT sufficient: a complaint line with no `consumer_purchase_line_id`
  has no purchase date, and the engine cannot pick a policy without one. The linkage is the
  consumer lodge journey's job (S3, which now writes it - there are 7 `consumer_purchases`
  against 1 `consumer_profile`, all from S3 testing); the 23 legacy rows predate it. Recorded so
  that "we configured the rules and still get no verdicts" is a known state rather than a
  surprise, and so nobody widens S7b to chase it. Verifying S7b's effect therefore needs a
  complaint lodged THROUGH the consumer journey, not one of the 23.
- **`covered_defect_type_ids` is a `uuid[]` with no FK** (AC-D18). The Term editor can offer a
  defect-type picker but cannot stop a later delete narrowing a Term's scope silently.

### Phase 2c contract audit - decided 2026-08-15

The FE prototype pinned its expected contract in a header comment during Phase 1; the backend was
built afterwards by a different agent. Before flipping the FE off its mocks, both sides were read
against each other. All 21 routes, every envelope, every request-body key and all six load-bearing
response fields (`term_count`, `source_attachment_name`, `assessment_count`, `has_no_rules` /
`has_no_terms`, the `?group_by=kind` envelope, nullable `deciding_rule.id`) match. Thirteen
disagreements were found; the rulings:

**The AC wins, so the FE doc was wrong and is corrected (no behaviour change):**

- The house error envelope is a top-level `{message, detail, code}`, not a string `detail`.
  `extractApiError` already recovers it through its `error.message` branch. The pinned comment
  claiming a string `detail` was wrong and would have misled the next reader.
- The overlap message tells the user to **delete the successor first**, not to supersede - which is
  what **AC-P26** actually ruled. The FE comment quoted the pre-AC-P26 wording.
- `POST /kind-rules/test` is a **200**, not a 201. It creates nothing; AC-P15's "POST 201" governs
  creating POSTs only.
- Unknown `match_type` values render a readable fallback rather than `undefined`, per **AC-P24**
  ("strict at write, tolerant at read"). Latent today: all live rules are `model_list` or `series`.

**Real defects, fixed in this phase:**

- **The policies grid's sort was dead.** `usePolicies` left `sorting` out of its react-query key, so
  no column header ever refetched. Every header, including the three the backend does support.
- **`term_count` was sortable but the backend's whitelist is `{version, effective_from,
  effective_to, created_at}`**, so that click silently did nothing. The column is no longer sortable;
  a control that does nothing is worse than an absent one.
- **AC-P26's prevention clause was never built.** The AC requires the Supersede dialog to state the
  resulting window for BOTH policies before the user confirms ("Version 15 closes 2026-08-31;
  Version 16 runs from 2026-09-01"). The dialog said only "Replacing v15". Since AC-P26 also rules
  out an undo, the confirmation IS the safety mechanism, so this was the one finding that mattered
  most.
- **The create path and the update path rejected the same input with different bodies.** Inverted
  window, blank version and blank part name are Pydantic validators on create (surfacing as
  `"Value error, ..."` in the modal) but `AppException`s on update (clean). Moved to the service so
  one rule produces one message. The same move covers every other caller-facing rule that lived on
  a schema - an unknown `match_type`, an empty `match_value`, and the rule tester's "nothing to
  test" - because leaving half of them behind would have the SAME route answer two adjacent field
  errors with two different envelopes. `warranty_config_service` now owns them all in one
  `_required_text` / `_assert_window_not_inverted` / `_validated_match_*` set that create, update,
  supersede and the tester all call. The schemas keep SHAPE only, so `min_length=1` came off
  `version` and `part_name` too - it would have answered `""` with Pydantic's stock message while
  `"   "` fell through to the service's sentence. `max_length` stays: that is the column's width,
  a different fact.
- **`PolicyResponse.created_at` was declared `Optional[datetime] = None`** while the column is
  `nullable=False, server_default=now()`. The declaration lied to every consumer of the schema. Now
  a required `datetime`, matching the FE's `WarrantyPolicyRow.created_at: string`.
- **`PolicyResponse.source_attachment_id` put a raw UUID on the wire that nothing consumed.**
  Removed. `source_attachment_name` (resolved from the attachment's `original_filename`, `null`
  when nothing is linked) is what the screen renders and stays. `PolicyCreate` / `PolicyUpdate`
  keep `source_attachment_id` as a WRITE field - linking a document is what a write does - so the
  deferred item below stays reachable the day a writer is built for it.

**Deferred, recorded so it is not mistaken for an oversight:**

- **A policy's source document has no writer.** The detail page renders a "Source document" card
  whose empty state offers an "Edit policy" CTA, but `WarrantyPolicyWrite` has no
  `source_attachment_id` field and the form never sends one, so the CTA could not lead anywhere.
  (`PolicyCreate` / `PolicyUpdate` DO accept the id - it is only the form that cannot supply it.) The AC does not ask for
  the warranty PDF to be attached at all - `policy_text` already holds the terms - so rather than
  widen the slice, the false CTA is removed and the card keeps an honest empty state. Attaching the
  source PDF is a later slice if Sorento wants it.

---

## Phase C - Propose a date, and let the consumer answer (S8) - PRE-CODE

Gated on `[CFG]`: Voice Calls enabled on the Sorento Respond.io workspace and the `Call Ended`
webhook pointed here. Respond.io publishes the webhook but **no call-history API**, so calls arrive
as events and cannot be backfilled - a call that ends while the webhook is misconfigured is simply
not on the record. Satisfies AC-C1 to AC-C11.

## Phase D - Calendar dispatch board (S9) - PRE-CODE

Month view by default, day view on click, jobs with no date kept reachable beside the calendar
(AC-D4 - the calendar's blind spot is exactly the job most likely to be forgotten). Satisfies
AC-D1 to AC-D6.

## Next step

Phase 3 - code review, then the DoD gate, then the PR.

### Phase 2c - what shipped, and how it was verified (2026-08-15)

Commits `5a2d15da8` (backend) and `a1bb28454` (frontend). The FE runs on the live backend;
`lib/warrantyConfigMock.ts` and its flag are deleted. 74 vitest across 13 files, 311 pytest across
every warranty suite, the 79-test engine regression net unedited. Every gate was written by a
different agent than the one that implemented it, which is what surfaced most of the findings below.

Verified in a browser against the real backend on a prod build, reached by clicking through the
sidebar rather than deep-linking:

- the policies list reads its 41 terms from the database, and `GET /policies` answers 200
- the Version header now issues `sort=version&dir=asc` and refetches - **that sort had never worked
  once**, because `usePolicies` left `sorting` out of its react-query key
- the Terms header issues no request at all, the backend having no such sort to give
- Kinds shows **"29 of 31 have no rule"** - the measurement this whole slice exists to surface
- the tester resolves `SRTMCB8071-BL` to Mirror Cabinet and names the deciding rule
- `?group_by=kind` answers **200, not the 500** the audit flagged as possible: the route's
  `Union[TermsGroupedResponse, List[TermResponse]]` response_model does resolve deterministically
- the supersede dialog states **"v15 closes 1999-12-31; v16 runs from 2000-01-01."** and recomputes
  live as the date is edited - AC-P26's prevention clause, which had never been built
- a refused create renders the house envelope cleanly: *"Effective range overlaps policy v15
  (2000-01-01 onwards). A complaint is judged against the version in force on its purchase date, so
  two candidates make that answer arbitrary."* - no `"Value error, "` prefix reaching the admin

Nothing was written during verification: the supersede dialog was cancelled rather than published,
and the only two writes attempted were refusals. The database still holds exactly one policy.

**Deviation from this plan's Phase 2 wording, recorded rather than left to disagree.** The plan says
"Playwright for the config-to-verdict round trip". The standing instruction for this repo is
agent-browser for UI verification, with the existing `e2e/` specs kept but no new ones authored. The
round trip above was therefore exercised with agent-browser in an isolated session (so a browser
another session owned was never disturbed), not a new Playwright spec.

### Still open after Phase 2c

- **A `null` in a CREATE body is still a raw Pydantic envelope** while the same null on PATCH is now
  the house envelope. It is a type refusal, which this module assigns to the schemas as shape, so
  closing it means making the create schemas' scalars Optional and letting the service answer - a
  contract change, deliberately not taken unilaterally. `max_length` overflow is the same story,
  though at least consistent across both verbs.
- **`components/ui/data-grid-table-dnd.tsx` never sets `data-group-label`** on its divider row,
  unlike the non-DnD variant - and the DnD one is what renders, since `columnsDraggable` defaults to
  true. So a test asserting on that attribute silently tests nothing. Shared infrastructure, not this
  slice's code; flagged, not fixed.
- **The FE types still declare `created_at?: string`** on the term and rule types, now that the
  backend declares it required. Harmless in that direction, worth tightening next time.
