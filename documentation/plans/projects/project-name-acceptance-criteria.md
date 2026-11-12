# UAC: PROJECT-NAME (10 Nov 2026)

Plan: `PLAN-project-name-10nov.md`. Card: `CARD-project-name-10nov.md` v1.1. Tests:
`sorento_crm_backend/tests/test_project_name.py`, `ProjectForm.projectName.test.tsx`,
`ProjectDetailClient.test.tsx` (PROJECT-NAME block), `ProjectsGrid.approval.test.tsx` (PROJECT-NAME block),
`_shared/lib/projectName.test.ts`.

## A. Data
- A1 A project and a lead each have an optional name, at most 80 characters; whitespace is collapsed and a
  blank name is stored as empty (null).
- A2 Two projects may share a name, under the same developer too; the registration lock and the Check use
  title + developer only.

## B. Register (create wizard)
- B1 Page 1 (Check) holds Project title, Developer, AI extract and Check only.
- B2 Page 2 "Who and what" opens with Project name (optional, 80 max, counter), then type and template.
- B3 The AI extract review lists a Project name row; confirming fills the page 2 field; a typed name is
  never overwritten.
- B4 Register sends `name` (trimmed, or null).

## C. Edit
- C1 Project title stays the first field; Project name sits directly under it.
- C2 Setting, changing or clearing the name never changes the title or reruns the clash check.

## D. Project page
- D1 The header shows the name; with no name, the title clamped to 2 lines as before.
- D2 "The development" opens with Project title (full width, 3 lines, full text on demand).

## E. Elsewhere (Q1 a)
- E1 Projects grid, pipeline, pickers, in-project headers, lead page project tables, My tasks show the name
  (title when none); the grid shows the title on hover.
- E2 Search on the projects list, the leads list, the portal project lookup and the assistant resolver
  matches the name too.
- E3 Notifications (secondary lead, reassigned, price floor, stale ladder, registration decisions) name the
  project by its name, the title when none.
- E4 Quotation subject / cover / PDF / Excel, AutoCount `our_ref_no`, spec sheet, purchase request and
  SCM / OI / fulfilment columns keep the full title.

## F. Leads and portal (Q5 b)
- F1 The lead form has Project name under the title; the lead header shows it; Qualify carries it onto the
  project unless the confirm step sends another.
- F2 The dealer portal registration form has Project name after the title, filled by its AI extract; the
  value is stored on the registration and kept through Approve (the approver may change it).

## G. Backfill (Q2 a)
- G1 Dry run lists code, title and AI proposed name for every coded project without a name, writing
  nothing to the database.
- G2 Apply writes only rows of the reviewed CSV whose project still has no name; a blank proposal is skipped.
