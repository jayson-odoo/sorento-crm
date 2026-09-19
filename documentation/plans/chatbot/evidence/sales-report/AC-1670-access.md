# AC-1670 browser verification - BLOCKED at login

Date: 2026-09-19
Session: agent-browser `--session csr-access` (isolated, not the shared default session)

## Goal

Contacts > a contact (Jayson, respond_contact_id 437264483 /
80560c8f-6358-4115-8b2c-e139ef31e48e) > Access tab > "Field reveals" card lists a
`Sales report` row (key `sales_orders.sales_report`); ticking/unticking persists after
reload; usable at 375px and 1280px.

## Stack confirmed reachable

- Frontend dev server: `http://localhost:3000` (next-server v15.5.9, primary checkout
  cwd `sorento_crm_frontend`), one instance machine-wide, confirmed via `lsof`.
- Lane backend: `http://localhost:8080/health` returned `{"status":"healthy"}` (checked via
  agent-browser `open` in a scratch tab, then closed that tab, no impact on the signin tab).

## Steps taken

1. `npx -y agent-browser@0.27.0 --session csr-access open http://localhost:3000` -> redirected
   to `/signin` (no session yet). Confirmed with `get url`.
2. `snapshot -i` showed the sign-in form (Email, Password, Continue).
3. Filled Email/Password from `sorento_crm_frontend/.env.local` `E2E_EMAIL` /
   `E2E_PASSWORD` (values never printed), clicked Continue.
4. Result: page stayed on `/signin`; a `network requests --filter callback/credentials` read
   showed `POST /api/auth/callback/credentials -> 401` (three times, once per retry).
5. Reloaded the sign-in page fresh (`open http://localhost:3000/signin`), re-filled the same
   two fields from the same file, clicked Continue again. Same result: page stays on
   `/signin` and the form now renders an inline alert **"Invalid credentials."**
   Screenshot of this state: `AC-1670-login-blocked.png` (this folder).
6. `console` showed only i18next/Fast-Refresh noise (the coder is actively editing the lane,
   HMR rebuilds fired several times), no errors. `errors` returned nothing.
7. Retried a third time after confirming (via the lane backend's `.env`) that
   `DATABASE_URL` was back to the expected prod-copy DB (it had briefly shown a different
   DB name mid-session, presumably the coder's own test run, then reverted on its own) -
   same "Invalid credentials." result.

Conclusion: this is a real 401 from the backend's `/api/v1/auth/login` for the
`E2E_EMAIL` / `E2E_PASSWORD` pair against whatever DB currently backs the lane backend at
:8080, not a routing or timing flake. I could not get past the sign-in screen, so none of
the Contacts > Access > Field reveals UI steps (locate the row, verify ticked, untick,
save, reload, confirm unticked, tick, save, reload, confirm ticked, 375px/1280px
screenshots) could be performed. **AC-1670 is UNVERIFIED in the browser**, not passed and
not failed - the blocker is the E2E login account, not the feature under test.

## DB baseline (read-only, sanctioned check from the brief)

Ran the one query the brief specified, against the DB currently named in the lane
backend's `.env` `DATABASE_URL`:

```
select field_key, granted from contact_field_reveals
where respond_contact_id='80560c8f-6358-4115-8b2c-e139ef31e48e'
  and field_key='sales_orders.sales_report';
```

Result:

```
         field_key         | granted
---------------------------+---------
 sales_orders.sales_report | t
(1 row)
```

The row exists and is granted = true, matching the "already ticked, captain granted it for
the console check" baseline described in the brief. This was read BEFORE any UI
interaction (since none was possible) - it reflects the starting state only, not a
post-verification end state. No tick/untick round trip was performed, so this same query
would need to be re-run after a successful login + UI pass to confirm the final state.

## Files in this run

- `AC-1670-login-blocked.png` - screenshot of the sign-in page showing the
  "Invalid credentials." alert (diagnostic evidence of the blocker, not the requested
  card screenshots).
- `AC-1670-access.md` - this note.
- `AC-1670-access-1280.png` / `AC-1670-access-375.png` - **NOT created.** The Field
  reveals card was never reached, so these were not fabricated.

## Session hygiene

Used my own named session `csr-access` throughout (never the shared default). Opened one
scratch tab to `http://localhost:8080/health` to confirm the backend was up, then closed
only that tab (`tab close t2`), leaving the sign-in tab untouched. Closed only `csr-access`
at the end of the run, never `close --all`.
