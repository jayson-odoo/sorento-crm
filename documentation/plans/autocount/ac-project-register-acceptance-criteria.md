# UAC: Register a CRM project in AutoCount (AC-PROJECT-REGISTER)

Plan: `PLAN-ac-project-register-13nov.md`. Answers to the behaviour card (crew, 13 Nov, from owner
rules): Q1 (a), Q2 (a), Q3 (a), Q4 (a), Q5 (a).

## Switch and access

- **R1** A new admin switch `project_autocount_register_enabled` ("AutoCount project registration")
  on System Settings. It defaults to OFF on a new settings row and after the migration. It is
  readable and writable through the admin settings GET/PUT, and readable by any signed-in user
  through `GET /user-management/settings/app-config`. A `null` on PUT stores false.
- **R2** Switch OFF: `GET` and `POST /project-sales/{project_id}/autocount-register` answer 403
  `ac_register_switched_off`. The fake Shared Service sees ZERO requests, not even the
  capability read. The project page shows no menu item, no badge and no dialog.
- **R3** Without `projects.autocount.write`, both routes answer 403 and the project page shows
  nothing new. A user without write access to the project (`assert_can_write_project`) is
  answered 403 on POST.
- **R4** An unknown project id answers 404, and a malformed id answers 422 or 404. A
  project in another company answers 404.

## Eligibility

- **R5** Only a project that is approved (`is_approved`: approval_state NULL or `approved`) and
  whose outcome is not `lost` can be registered. Any other project gets POST 409
  `ac_not_eligible` with the message "Only an approved project that is not lost can be
  registered in AutoCount." A project still awaiting approval is refused one step earlier by
  the shared project write check (409 `project_not_approved`, its own plain sentence); either
  way the SS is not called. On the page the menu item is not shown
  for such a project.

## Status read (GET)

- **R6** With the switch ON, `GET /project-sales/{project_id}/autocount-register` answers
  `{registered, project_no, registered_at, eligible, can_register, reason}`.
  - `registered`: the project holds an AutoCount key.
  - `can_register`: true only when eligible, not registered, the SS lists `projects / create_doc`
    as enabled, and the SS names a book.
  - `reason`: otherwise the plain reason: "Waiting for AutoCount" when the SS does not list the
    capability or names no book, "Could not reach AutoCount" when the SS is unreachable, and
    null when registered or ineligible.
- **R7** Before the endpoint exists, the SS's capability feed has no `projects` entry. GET
  answers `can_register=false` with reason "Waiting for AutoCount", and the page shows the
  menu item greyed with that reason. This is the UAT state.

## Register (POST)

- **R8** POST builds the body with `build_project_body`:
  `{companyCode, project: {projNo: project_code, description: title (first 100 chars),
  desc2: sales profile location or address (first 100 chars, omitted when empty),
  isActive: true}}`. The company code comes from the project's company, never from the
  request, and the route takes no body. It sends with `client.write("documents/projects",
  body, idempotency_key=...)`. The idempotency key starts `crm-proj-<project id>-create`. The
  write carries the press's X-Request-ID and the actor headers.
- **R9** When the capability is not enabled or no book is named, POST answers 200 with an
  outcome other than `done` and the plain reason ("Waiting for AutoCount" /
  "Could not reach AutoCount"). No write is sent.
- **R10** A `done` answer stores `autocount_doc_no` (the SS answer's `docNo`, else the
  document's `ProjNo`, else the sent `projNo`), `autocount_doc_key` (the answer's key, else
  that number), `autocount_book` (the book named), and `autocount_registered_at`. It answers
  `outcome=done` with message "<number> registered in AutoCount" and `doc_no` = the number.
  Project detail then carries `autocount_project_no` and `autocount_registered_at`.
- **R11** A refusal (`refused` / VENDOR_REFUSED / a 4xx gateway error) answers the plain reason
  and releases the key: `autocount_pending_create` is cleared and nothing is stored. The next
  press sends the CURRENT body under a NEW key.
- **R12** An unknown outcome (timeout, 5xx, `pending_verification`) keeps the key and body in
  `autocount_pending_create`. The next press re-sends that SAME key and body first. If that
  answers done, the project is linked and nothing is created twice.
- **R13** A press on a project already registered answers `done`, "<number> is already in
  AutoCount.", and sends nothing.
- **R14** Every write is logged with the person who pressed (audit row `autocount_write`, as
  the quotation and sales order writes). Every press that reached the SS also adds one row
  to the project's Activity feed:
  - done: "Registered in AutoCount as <number>";
  - otherwise: "AutoCount registration not completed: <plain reason>".
- **R15** Nothing else about the project changes. Editing a project later sends nothing to
  AutoCount (Q5).

## Screen

- **R16** Switch ON + permission: an approved, not lost, not registered project has a gear menu
  item "Register in AutoCount". When `can_register` is false it is disabled and shows the
  reason. Pressing it opens the shared AutoCount result dialog with the answer, and
  "Try again" is available from the menu after a failure.
- **R17** A registered project shows a Badge with the AutoCount number in the header (title
  "AutoCount number"), and the menu item is gone. The badge shows whatever the switch is set
  to, because it is a stored fact.
- **R18** Switch OFF or no permission: the project page DOM is the same as before this lane, with
  no extra request to the register route.
