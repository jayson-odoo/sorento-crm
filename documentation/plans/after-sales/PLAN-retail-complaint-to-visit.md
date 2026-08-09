# PLAN - From a lodged retail complaint to a technician at the door

**Status:** Phase A (S7a) IMPLEMENTED 2026-08-08, migration 330. **Phase B (S7b) IN BUILD from
2026-08-09.** Phases C (S8) and D (S9) pre-code.
**UAC (the contract this fulfils):** `retail-complaint-to-visit-acceptance-criteria.md` - every
section below cites the ACs it satisfies.
**Parent:** `PLAN-after-sales-warranty.md` (S1 to S6 built). This plan covers what happens AFTER a
retail complaint lands, up to a technician being sent.
**Decisions:** `adr/0009` Service Job is requester-agnostic - `adr/0010` Warranty Terms scope to
Kind - `adr/0001` status engine is core.
**Branch:** `worktree-after-sales-warranty`. **Ports:** FE 3050, BE 8050.

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
- **`covered_defect_type_ids` is a `uuid[]` with no FK** (AC-D18). The Term editor can offer a
  defect-type picker but cannot stop a later delete narrowing a Term's scope silently.

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

S7b Phase 1.
