# UAC: client error report (CLIENT-ERROR-REPORT)

Plan: `PLAN-client-error-report-04nov.md`.

- AC-1 Safari without `structuredClone` (before 15.4) opens sign-in and every staff page without the
  "could not start" screen.
- AC-2 Safari with website storage blocked opens every page; settings changes work for the session.
- AC-3 A stale build (chunk load error) reloads the page once by itself; if the reloaded page works,
  the reader sees no error screen.
- AC-4 If the page still fails after that one reload, the "could not start" screen shows with the
  Reload button, and it never reloads by itself again for that build in that tab.
- AC-5 Any other error that reaches the root or a staff page boundary is recorded once, with the
  error, page path (no query string), build, browser and the signed-in user.
- AC-6 System Management > Operations > Client Errors lists those records, newest first, with user
  name (never an id), screen, error, page, browser and build; a row opens the full stack.
- AC-7 Only holders of `system_management.client_error.view` (and admins) can see the list.
- AC-8 One user can record at most 20 reports per hour; a report over 16 KB is refused.
- AC-9 Link tokens in the path, message or stack are stored redacted.
- AC-10 Records older than 30 days are deleted by the daily prune task.
