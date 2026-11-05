# PLAN: AI Assistant Prompts on the standard list + record views

Status: Build done, in review (small fix track: FE-led, no migration, no auth/RBAC change; one
new read-only list GET behind the existing `system.ai_assistant_settings.view` permission)
Lane: AI-PROMPTS-STD-VIEWS. UAC: `ai-prompts-std-views-acceptance-criteria.md`.

## Owner ask (5 Nov 2026)

"I think our AI assistnat prompt need to use the standard list and form view component of the
system la, like this list view is so non confirming"

Screen: System > AI Assistant > Prompts. Reuse-only: no new components, no mock phase (owner
rule 29 Sep).

## List

`prompts/components/PromptsList.tsx` rebuilt on the CampaignsList template:
`DataGrid` + `DataGridListToolbar` (search, Filters, Columns, Export, Refresh) +
`DataGridPagination`, `buildSelectColumn`, `rowHref` via `buildDetailSearch`,
`useListStateFromUrl`, `useResetPageOnFilterChange`.

- Columns (every one sorts server-side): Prompt, Role, Status, Runs on, Production, Latest,
  Last edited (`formatDateTimeInMalaysia`, dd/mm/yyyy), Edited by.
- Filters, multi-select: Status (Active, Dormant), Runs on (Default model + every model in use).
- Kept: the "Domain block out of date" banner above the grid.
- Dropped: the intro explanation line (DESIGN-LANGUAGE section 6) and the "Show inactive"
  checkbox (replaced by the Status filter; no default, dormant rows pilled).

Backend: `GET /api/v1/system/ai-assistant/prompts/list?page&limit&sort&dir&query&status&model`
-> `{data, empty, pagination{total,page,limit}, model_options}`; rows carry `id = name`.
`AIPromptService.list_keys_page` sorts and filters `list_keys()` in Python: the keys are
code-defined (`PROMPT_KEYS`, a few dozen), there is no table to query. Unknown sort -> 422.
Blanks sort last both ways; text sorts case-insensitively; name breaks ties.

## Detail

`prompts/components/PromptDetail.tsx` on the SalesAgentDetail record layout:

- `PageHeader` + `BackToList` (keeps list state).
- Record header card: name + status pill; `DetailActions` with `ListPager`
  (`promptsPagerQuery`, same key builder as the list), gear on the LOADED version (Publish vN,
  Stage vN, Compare versions) and the one primary, Edit. Edit session: Cancel + Save as new
  version (still a new immutable version, commit message required).
- Line tabs (`useUrlTab`): Prompt (role field + the unchanged editor: Edit / Preview /
  Architecture modes, diff, full screen, wired panel), Versions (`PanelDataGrid`; row click loads
  the version; row menu Publish / Stage), Model (`AgentModelCard`), Dry run (`DryRunBox`).

## Tests

- `sorento_crm_backend/tests/test_ai_prompt_list_grid.py`: envelope, paging, 403, every column
  sorts both ways with blanks last, Status + model multi filters, search, unknown sort 422.
- `PromptsList.test.tsx`: every header sorts through the list query, search, both multi filters,
  row open carries list state, Odoo select, banner.
- `PromptDetail.test.tsx`: existing editor suite adapted to View -> Edit, plus pager present and
  surviving Save / Publish, Back keeps list state, tab order, role field, read-only user has no
  Edit, Cancel discards, Save payload, gear Publish of the loaded version, versions grid content.
