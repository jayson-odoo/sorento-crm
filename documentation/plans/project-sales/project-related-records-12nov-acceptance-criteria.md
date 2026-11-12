# UAC: project related records (PROJECT-RELATED-RECORDS)

Status: DRAFT. Crew answered Q1-Q4 = (a) from owner rulings (12 Nov). Open owner decisions: D1 (old-record linking), D2 (editable on closed/approved without Revise), D3 (project optional on new SI/NPA). Final when the owner approves mock v2 and D1-D3.
Card: `CARD-project-related-records-12nov.md`. Mock: `documentation/mockups/project-related/index.html`.

## A. The Related tab

- AC-A1 The project page has a tab "Related" in place of "Sponsorship Form", in the same position. Its badge equals the number of rows the grid shows with no filter.
- AC-A2 `?tab=sponsorships` (old links) opens Related with the Type filter set to Sponsorship form.
- AC-A3 The grid lists every purchase request, sponsorship form, complaint, stock inquiry and new product application whose `project_id` is this project, one line per row.
- AC-A4 Columns: Type, Number, Status, Approval (PR/SF only, else "-"), Date (dd/mm/yyyy), Raised by (a name), Subject, Value (RM, else "-"). Every column sorts on the server (asc, desc, off) and the order holds on page 2. Default sort: Date, newest first.
- AC-A5 Search matches number, subject and raised-by; it runs on the server.
- AC-A6 Filters: Type (multi-select, only types the viewer may view) and Status (multi-select). Two values in one filter = either; two filters = both.
- AC-A7 Clicking a row opens that record's own page. No Open column, no row buttons.
- AC-A8 Columns can be hidden and reordered; the choice is kept per user (listing key).
- AC-A9 No related rows: the tab shows heading "No related records" and a hint, no button.
- AC-A10 The sponsorship spend line (total and per year) shows above the grid when the project has at least one sponsorship form; its numbers equal today's rollup.
- AC-A11 Usable at 375px and 1280px; the page does not scroll sideways.

## B. Who sees what

- AC-B1 The tab needs project read (`projects.projects.view` or `view_own` on their own project). Another company's project, or someone else's project for a `view_own` user, is a 404.
- AC-B2 Per type, the viewer's request rule applies: no view and no view_own on a type -> that type's rows and Type option are absent; view_own only -> only their own rows (request forms: `contact_id` is their contact; NPA: applicant is them or their contact); view (or admin) -> all linked rows.
- AC-B3 A record linked to a project of another company never appears on this project.
- AC-B4 An API-key caller gets the act-as user's view, nothing wider.

## C. Linking SI and NPA

- AC-C1 Stock inquiries and new product applications have a nullable Project link. Existing rows are not changed by the release.
- AC-C2 The staff SI and NPA forms have a clearable, searchable Project picker (code and title), the same one the purchase request form uses. Only approved projects are offered and accepted (`assert_linkable_project`).
- AC-C3 The portal SI, NPA, complaint and purchase request forms have the same project picker the portal sponsorship form has, offering only the contact's own company projects; a project outside them is refused with a plain message. (Today only the portal sponsorship form has it, `SubmissionForm.tsx:397`.)
- AC-C3a Picker rows are one line: project code + short title clamped with "...", full title on hover, no price.
- AC-C3b (D3, recommended) Project stays optional on new SI and NPA.
- AC-C4 An NPA raised from an SI starts with that SI's project picked; the person can change or clear it.
- AC-C5 The typed "Project name" keeps working and is never used to fill the link.
- AC-C6 Linking happens on the record's own page via its Project field; every change shows in that record's History tab (shared history component: who, on behalf of, when, old -> new).
- AC-C6a (D2, pending owner) On a closed or approved record, the Project field alone stays editable without Revise.
- AC-C8 (D1, pending owner) Existing records are never linked by name automatically. If D1 = reviewed list: a one-off list of exact-name proposals; only rows the owner ticks are written.
- AC-C7 The detail pages of SI and NPA show the linked project as its code + title, linking to the project.

## D. Extensibility (OCN)

- AC-D1 Adding a record type is one backend registration and one frontend entry; a test registers a sixth fake type and it appears in the endpoint, the filter and the grid without editing either.

## E. Assistant

- AC-E1 The related-records list route is registered in `app/services/assistant_registry/` (project module) and has two eval prompts in `scripts/chatbot_eval/gold/`.
