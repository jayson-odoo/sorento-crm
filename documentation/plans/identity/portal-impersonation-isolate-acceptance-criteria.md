# UAC: Portal impersonation isolated from the admin's staff session

Plan: `PLAN-portal-impersonation-isolate-05nov.md`.

- PII-1: An admin who impersonates a salesperson contact in tab A sees the salesperson's view in
  tab A only. A tab B opened before or after, in the same browser or another one, shows the admin
  with full access (Products list loads).
- PII-2: Reloading tab A keeps the view-as in tab A.
- PII-3: Exit Impersonation in tab A returns tab A to the admin with no sign-in prompt; tab B is
  unchanged and stays signed in.
- PII-4: Starting impersonation never signs the admin out of any tab.
- PII-5: A non-admin cannot start impersonation (403), and a view-as header sent by a non-admin is
  ignored.
- PII-6: A request made as the impersonated salesperson cannot reach a staff-only API (403).
- PII-7: Audit is unchanged: actions in tab A are the target as actor with the admin as real user;
  start and end rows are written as today.
