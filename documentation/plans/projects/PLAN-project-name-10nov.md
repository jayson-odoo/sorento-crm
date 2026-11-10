# PLAN: PROJECT-NAME (short project name in the header, lean registration page 1)

Status: Build in progress (card v1.1 answered Q1 a, Q2 a, Q3 a, Q4 a, Q5 b; mock v1 approved 10 Nov). Track: normal (additive migration `pname_0001_project_lead_name`). Card:
`CARD-project-name-10nov.md`. Mock: `mockups/project-name-10nov.html` (after the card).

## Journey

Owner ruling, 10 Nov: a project gets a short NAME so the long legal title stops bloating the header. The header
shows the name; the full title moves into the Overview "The development" card. Registration page 1 holds only the
project title and the developer; the name sits on page 2, prefilled by the existing AI extract and editable by hand.

Build waits for the owner's approval of the card and the mock.

## Slices (one lane, one PR)

1. BE: migration (projects.name, leads.name), schemas, register / edit / salesperson draft / portal save /
   approve / qualify, extract `name` field + proposal, search (projects, leads, portal lookup, assistant
   resolver), notifications via `project_display_name`, clash candidates, task rows, MCP text, backfill script.
2. FE core (mock): page 2 Project name, extract row, edit field under the title, header name, Details title,
   grid column, pipeline search placeholder.
3. FE peripheral: pipeline cards, pickers, in-project headers, lead form + lead page, my tasks, portal form.
4. Review, security review, browser pass, hand-test script.

## Contract

- `POST /projects/`, `PUT /projects/{id}`, `POST /projects/{id}/approve`: optional `name` (max 80; whitespace
  collapsed; blank = null). Responses add `name`.
- `POST|PUT /leads`: optional `name`; `POST /leads/{id}/qualify` optional `name` (defaults to the lead's).
- `POST /projects/ai-extract` adds `name` (plain string or null, at most 80).
- `POST /projects/clash-preview` candidates add `name`.
- Portal `project_registration` fields add `name`; `/lookups/projects` rows add `name`.
- Task rows add `project_name`.

## Triggers deliberately not built

- SCM / order-inquiry worklist / fulfilment / allocation columns stay on the title (Q1 a). Build when the owner
  asks; the OI worklist Project filter matches exact title text (`order_inquiry_worklist_service.py:1524`).
