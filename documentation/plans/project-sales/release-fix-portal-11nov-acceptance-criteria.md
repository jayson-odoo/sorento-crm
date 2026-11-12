# UAC: RELEASE-FIX-PORTAL (11 Nov)

Plan: `PLAN-release-fix-portal-11nov.md`. Actor: a salesperson limited to their own projects
(`projects.projects.view_own` + `edit`, no `projects.projects.view`).

- AC-1 On their own project, the quotation form's draft, autosave, History list, History entry,
  Restore and Payment Terms select all work (200) and show that proposal's own data.
- AC-2 On another salesperson's project, every one of those routes answers 404 "Not found", the
  same as every other project route, and leaves no draft behind.
- AC-3 On their own project, another project's proposal id is 404; on their own proposal, another
  proposal's History entry id is 404 for both reading and restoring it.
- AC-4 Without a session, each route still refuses (401/403) as today.
- AC-5 The company-wide Payment Terms list and the order inquiry History tab are not refused by the
  "own records only" guard; their own permission decides, as for their sibling routes.
- AC-6 Every route a limited user can reach is pinned in `tests/portal_p2_allowed_routes.txt`.
