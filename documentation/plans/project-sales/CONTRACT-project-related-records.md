# CONTRACT: project related records (PROJECT-RELATED-RECORDS)

The shared spec the tester writes red tests against and the coder implements. UAC:
`project-related-records-12nov-acceptance-criteria.md`. Owner rule (13 Nov): reuse the EXISTING
components and functions; no look-alikes.

## 1. Migration

`sorento_crm_backend/alembic/versions/prr_0001_si_npa_project_link.py`, revision `prr_0001_si_npa_project`,
down_revision = current single head (`acqs_0001_project_ac_write` on 13 Nov; re-check with `alembic heads`).
Same idempotent shape as `318_complaint_project_link.py`:

- `stock_inquiries.project_id UUID NULL`, FK `fk_stock_inquiries_project_id` -> `projects.projects(id)` ON DELETE SET NULL,
  partial index `ix_stock_inquiries_project` ON (project_id) WHERE project_id IS NOT NULL.
- `new_product_applications.project_id` likewise (`fk_new_product_applications_project_id`, `ix_new_product_applications_project`).
- Downgrade drops index, FK, column. No data written.

## 2. Models and schemas

- `StockInquiry.project_id`, `NewProductApplication.project_id`: `Column(UUID(as_uuid=False), ForeignKey("projects.projects.id", ondelete="SET NULL"), nullable=True)`.
- SI and NPA create/update schemas accept `project_id: Optional[str]`. Responses carry `project_id`, `project_code`, `project_title`
  (same names the complaint response uses, `app/schemas/complaints.py:211-230`). Both manual dict builders, if any, carry them.
- `project_name` (free text) unchanged and never used to fill `project_id`.
- On create and on a CHANGED link: `project_service.assert_linkable_project(db, project_id, current, code="<type>_project_not_approved")` -> 422.
- NPA created with `stock_inquiry_id` and no `project_id` key in the payload: starts with that SI's `project_id`. An explicit `project_id: null` stays null.

## 3. Set the project on any record at any time (D2)

One shared function `project_related_records.set_record_project(db, *, kind, record_id, project_id, actor)`:
validates with `assert_linkable_project`, writes only `project_id`, never touches status or approval, works in any status
(closed, approved, rejected), audited through the existing audit listeners (History shows old -> new).

Routes (each guarded by that type's EXISTING edit permission/scope, no new slug):
- `PATCH /api/v1/procurement/stock-inquiries/{id}/project`
- `PATCH /api/v1/procurement/new-product-applications/{id}/project`
- `PATCH /api/v1/procurement/purchase-requests/{id}/project` (purchase requests and sponsorship forms)
- `PATCH /api/v1/complaints/{id}/project`
Body `{"project_id": "<uuid>" | null}`; response = that type's normal detail response. (Exact prefixes: use each router's real
prefix; the tester reads them from `app/api/v1/__init__.py`.)

## 4. Portal pickers (AC-C3)

The portal SI, NPA, complaint and purchase request submissions accept `project_id` exactly as the portal sponsorship form does
today: offered from `sponsorship_link_service.projects_for_contact`, checked by the ownership half of
`sponsorship_link_service.assert_project_requirement` (a project outside the contact's companies -> 422). Optional (D3): no
`requires_registered_project` enforcement for these four kinds.

## 5. Related-records endpoint

`GET /api/v1/project-sales/projects/{project_id}/related-records`

Query: `type` (repeatable: `stock_inquiry`, `complaint`, `purchase_request`, `sponsorship_form`, `new_product_application`),
`status` (repeatable, raw status values), `query` (search number, subject, raised_by; case-insensitive contains),
`sort` in `type|number|status|approval|date|raised_by|subject|value` (default `date`), `dir` `asc|desc` (default `desc`),
`page` (1-based), `limit` (default 25, capped like other lists, see `tests/test_list_pagination_limit.py`).

Guard: `require_any_permission(READ)` + the project own-scope router guard; project not visible -> 404. Add the route to
`tests/portal_p2_allowed_routes.txt`.

Response `RelatedRecordsResponse` = `ListResponse[RelatedRecordRow]` plus:
- `type_counts: Dict[kind, int]`: rows per visible type with no type/status/query filter (the tab badge = sum);
- `types: List[{"kind", "label"}]`: types the viewer may see, in registry order.
- `statuses: List[str]`: the raw statuses of the visible linked rows with no filter, sorted (the Status filter's
  options; added by the coder so the filter offers every status, not only the loaded page's).

`RelatedRecordRow`: `kind`, `id`, `number`, `status`, `approval_status` (PR/SF only, else null), `date` (date),
`raised_by` (a name, never an id), `subject`, `value` (Decimal or null).

Per type (registry entry). Timestamps are naive UTC; "MYT day" = the Asia/Kuala_Lumpur calendar day (`project_related_records._malaysia_date`):
| kind | label | table | number | status | approval | date | raised_by | subject | value |
|---|---|---|---|---|---|---|---|---|---|
| stock_inquiry | Stock Inquiry | stock_inquiries | inquiry_number | status | - | MYT day of created_at | salesperson | item_description | - |
| complaint | Complaint | complaints | complaint_number | status | - | complaint_date | salesperson | defect_description | - |
| purchase_request | Purchase request | purchase_requests (request_type='purchase_request') | request_number | status | approval_status | coalesce(request_date, MYT day of submitted_at, MYT day of created_at) | requested_by | project_title | total_project_value |
| sponsorship_form | Sponsorship form | purchase_requests (request_type='sponsorship_form') | request_number | status | approval_status | coalesce(request_date, MYT day of submitted_at, MYT day of created_at) | requested_by | purpose | total_project_value |
| new_product_application | New product application | new_product_applications | application_no | status | - | MYT day of coalesce(submitted_at, created_at) | applicant user name | remark | cost_price |

Visibility per type: `own_scope.request_access(perms, access_kind)` (`access_kind` = kind). `None` -> type absent from rows,
`type_counts` and `types`. `"own"` -> `own_scope.request_clause(model, me)` (NPA: `own_scope.npa_clause(me)`). `"all"` -> no
extra clause. Rows only where `project_id = :project_id`. One `UNION ALL` of the visible types' selects, filtered, sorted
(ties broken by `number`, then `id`) and paged in SQL.

## 6. Registry (OCN plug-in)

`sorento_crm_backend/app/services/project_related_records.py`:

```python
@dataclass(frozen=True)
class RelatedType:
    kind: str
    label: str
    access_kind: str            # key for own_scope.request_access
    model: Any                  # SQLAlchemy model with project_id
    select: Callable[[Me, str], Select]   # (me, access) -> select of the 8 labelled columns + kind, id
RELATED_TYPES: "OrderedDict[str, RelatedType]"
def register_related_type(rt: RelatedType) -> None
def list_related_records(db, *, project_id, perms, me, types=None, statuses=None, query=None,
                         sort="date", direction="desc", page=1, limit=25) -> dict
```

FE: `sorento_crm_frontend/app/(protected)/project-sales/[projectId]/components/relatedRecordTypes.ts`:
`RELATED_RECORD_TYPES: Record<kind, { label: string; href: (id: string) => string }>` and
`registerRelatedRecordType(kind, def)`. `RelatedRecordsPanel.tsx` reads only the registry + the API `types`; an unknown kind with a
registry entry renders without editing the panel.

FE hrefs: SI `/procurement-management/stock-inquiries/{id}`, complaint `/complaint-management/complaints/{id}`, PR
`/procurement-management/purchase-requests/{id}`, SF `/procurement-management/sponsorship-forms/{id}`, NPA
`/procurement-management/new-product-applications/{id}`.

## 7. FE

- `ProjectDetailClient.tsx` `TABS`: `{ id: 'related', label: 'Related' }` replaces `sponsorships` in the same position;
  `resolveProjectTab('sponsorships')` -> `'related'` and the panel opens with type filter `['sponsorship_form']`.
  Tab badge = sum of `type_counts`.
- `RelatedRecordsPanel.tsx` = `components/common/PanelDataGrid.tsx` with server sort/search/paging (extend PanelDataGrid ONLY if
  it lacks server paging, never a copy), sponsorship rollup line on top (existing `useSponsorshipRollup`), filters Type + Status via
  `SearchableMultiSelect`, dates `formatDate` (`lib/helpers.ts`), money `formatMyr`, pills `lib/status-pill.ts`, empty state
  "No related records" + hint, no Create button, row click -> href. `SponsorshipsPanel.tsx` is retired (its tests move).
- Hook `useProjectRelatedRecords(projectId, params)` in `_shared/hooks/useProjects.ts`, service fn in `projectService.ts` using
  `buildDataGridParams(params, { type, status })`.
- SI and NPA forms (staff + portal `SubmissionForm.tsx`) and portal complaint/PR: the SAME picker as `PurchaseRequestForm.tsx:779-800`
  (`SearchableSelect` + `searchProjectsForLink`, label "Registered project (optional)", clearable); detail pages show
  code + title linking to the project and let an editor change it via the PATCH route.

## 8. Assistant

Register the related-records route in `app/services/assistant_registry/<projects module>.py` (`routes`), plus two eval prompts in
`scripts/chatbot_eval/gold/assistant_<module>.jsonl`. `python3 scripts/ci_ai_coverage.py` green.

## 9. D1 review sheet (crew-run)

`sorento_crm_backend/scripts/project_link_review.py`:
- `--export out.xlsx`: read-only. Lists SI (`project_name`), complaints (`project_title`), PR/SF (`project_title`) with
  `project_id IS NULL` whose trimmed, case-insensitive typed name equals the title of EXACTLY ONE approved project
  (`approved_projects`) of the same company (records with no company: matched across all companies, still exactly one).
  Columns: Link? (blank), Type, Number, Date (dd/mm/yyyy), Typed project name, Proposed project code, Proposed project title, record id, project id.
  Shared Excel style.
- `--apply ticked.xlsx`: links only rows whose Link? cell is ticked (`y`/`yes`/`x`/`1`), through `set_record_project`, skipping a
  row whose record already has a project; prints counts. Never run by the lane against a shared DB.

## 10. Fix round 2 (security + review, 13 Nov)

- **One portal project check.** `sponsorship_link_service.assert_contact_may_link(db, contact, project_id, current, code)`:
  ownership first (a project outside the contact's companies -> 422 `sponsorship_project_not_permitted`), then
  `assert_linkable_project` (`<kind>_project_not_approved`). `PortalService._assert_own_project` runs it inside
  `_apply_payload` before `project_id` is written, so portal create, draft save, submit and revise
  (`portal_revision_service.revise` -> `_apply_payload`) all refuse a foreign project and save nothing; submit
  re-checks the stored value. The portal NPA write and `POST /external/stock-inquiries` (with `project_id`; the
  contact is the payload's `contact_id`) call the same function. The sponsorship form's own gate
  (`assert_project_requirement`) reuses the ownership half.
- **NPA cost.** `RelatedType.value_is_cost` (NPA): the row's `value` is null, for sort and cell, unless
  `cost_access.can_view_cost` (`products.cost.view`); the assistant's `project_related_record` rows follow it.
- **PATCH rules.** NPA: the NPA edit rule, the applicant (or an admin), plus `.create`. PR/SF: an edit right on
  either kind is checked before the row is read (no 404/403 oracle), then the row's own kind.
- **PR/SF response** carries `project_name` (the linked title; `project_title` stays the typed text).
- **FE.** Complaint, PR and SF detail pages get the shared `RecordProjectField` (kind's own edit right, any
  status). Related grid: Type and Status in the toolbar's Filters popover (always present); complaint status
  label and pill from `lib/complaint-status.ts` through the registry entry (`statusLabel`, `statusPillClass`);
  page, sort, search and filters in the address bar as `rel_page`, `rel_limit`, `rel_sort`, `rel_dir`,
  `rel_query`, `rel_type`, `rel_status` (prefixed: the project page's own `page`/`sort`/`query` belong to the
  projects list's prev/next); a sort change goes back to page 1.
- `scripts/project_link_review.py --apply` needs `--actor`.


## 11. Fix round 3 (browser pass 1, 13 Nov)

- `GET /projects/{id}/sponsorships/rollup` follows `own_scope.request_access(perms, "sponsorship_form")`: none -> 403,
  `own` -> `sponsorship_link_service.sponsorship_rollup(..., clause=request_clause(...))` (their own forms), `all` ->
  every form. The Related panel asks for the spend line only when the API's `types` include `sponsorship_form`.
- The shared `RegisteredProjectSelect`: one line per option (truncate, full label on hover), the closed control cut
  to one line inside its cell (`contain: inline-size`), clearable on every form.
- `useSetRecordProject` refreshes `['audit-logs']` and the Related tabs, so History shows the change at once.
