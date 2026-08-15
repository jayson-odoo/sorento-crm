# Handoff - Onboarding Slice 1 (branch `fm/onboarding-slice1`)

Written 2026-08-15 02:30 +08. Everything in the slice is built, tested and committed.
The one remaining step - interactive browser verification - is blocked by the machine,
not by the code. This file is self-contained: it is enough to resume without reading
the session transcript.

## State: what is done

| Phase | State |
|-------|-------|
| UAC + PLAN (`documentation/plans/`) | committed `59a2cbd9` |
| Models, status graph, reader, migration `360_onboarding_slice1` | committed `77d85f04` |
| Token, public routes, review/approve routes, provisioning task | committed `7734a481` |
| pytest suites (62 passing) | committed `303df1b8` |
| FE off mocks, onto the real API, + vitest (32 passing) | committed `fa1dfb37` |
| Interactive browser verification | **BLOCKED - see below** |
| `e2e/onboarding-review.spec.ts` | deliberately deferred, reasoned in the PLAN |

Re-ran on this machine just now, both green:

```
sorento_crm_backend  $ venv/bin/pytest tests/test_onboarding_reader.py \
                         tests/test_onboarding_service.py tests/test_onboarding_api.py -q
62 passed

sorento_crm_frontend $ npx vitest run components/common/onboarding \
                         "app/(auth)/onboarding" "app/(protected)/user-management/onboarding-requests"
3 files, 32 tests passed
```

`alembic heads` is a single head (`360_onboarding_slice1`); the migration merges the two
pre-existing heads via a tuple `down_revision`. Re-check this after any rebase.

## The blocker

Two independent environment faults, both machine-wide, neither inside this worktree:

1. **No DNS.** `scutil --dns` lists zero nameservers; `node`/`curl` return `ENOTFOUND`
   for every host while `ping 1.1.1.1` succeeds, so routing is fine and only resolution
   is dead. This alone stopped `next build` (`next/font/google` fetches Inter at build
   time) and stops `agent-browser install` from repairing itself
   (`Chrome for Testing CDN unreachable`).
2. **No Chromium will start.** Chrome for Testing 152 (bundled by agent-browser, present
   on disk) and `/Applications/Brave Browser.app` both die instantly with SIGABRT
   (`EXIT=134`), no stderr, no entry in `~/Library/Logs/DiagnosticReports`. Reproduced
   headless, with `--no-sandbox`, with a fresh `--user-data-dir`, and both inside and
   outside the tool sandbox. `codesign -v` on the Chrome for Testing bundle reports
   `code has no resources but signature indicates they must be present`, but Brave is a
   normally installed app and fails identically, so this is not one corrupt download - a
   machine-level policy or security agent is killing browser processes. This is
   consistent with the captain's "Chrome is UNINSTALLED" event.

So there is currently no way to drive a UI on this box: not agent-browser (its Chrome
aborts), not a CDP connection to another browser (Brave aborts too), and playwright is
out by instruction and would fail on the same binaries anyway.

## Resume: exactly what is left

1. Confirm the machine recovered: `scutil --dns | grep -c nameserver` is non-zero, and
   `npx -y agent-browser doctor` reports the Launch test as `pass`. If Chrome for
   Testing still aborts, `npx -y agent-browser install` re-downloads it (needs DNS).
2. Bring the stack up (ports chosen to avoid other lanes; nothing here is shared):
   ```bash
   cd sorento_crm_backend && venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8022 &
   cd sorento_crm_backend && ENABLE_SCHEDULER=false OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES \
       venv/bin/python worker.py &          # worker is REQUIRED: approve enqueues on `imports`
   cd sorento_crm_frontend && npx next start -p 3021 &
   ```
   The prod build is already in `.next` and already serves both routes. If it must be
   rebuilt, take the fleet build lock and, while DNS is down, pass the offline font
   stand-in (see "Offline font build" below):
   ```bash
   while ! mkdir /tmp/fm-fe-build.lockdir 2>/dev/null; do sleep 30; done
   trap 'rmdir /tmp/fm-fe-build.lockdir 2>/dev/null' EXIT INT TERM
   npm run build
   ```
3. Recreate a verification admin (the previous throwaway was deleted at the end of this
   session - see "What was left in the shared database"). It must be a real `users` row
   with a `user_sessions` row, because `require_permission` rejects both `X-API-Key` and
   a hand-minted JWT with no session.
4. Verify, **navigating by sidebar clicks only, never a deep URL**, at 1280 and at 375:
   - `/` -> User Management group -> "Onboarding Requests" leaf renders and clicks
     through (this is what catches a wrong `moduleKey` or bad permission gating).
   - Queue -> detail -> Start review -> reject a row (dialog refuses an empty reason)
     -> Approve and provision -> lanes move.
   - Public intake at `/onboarding/<token>`: upload
     `sorento_crm_backend/tests/fixtures/onboarding_phone_list.xlsx`, check the problem
     chips, submit, confirm the same link becomes a read-only status page.
   - Check the console for errors and confirm the `/api/v1/...onboarding/*` calls fire.
5. Run `/code-review` (Phase 3), then open the PR. Never push to the default branch.

## Live handles

**Nothing is running.** A machine-wide event killed every background process of this
lane (backend, worker, FE server) right after the blocker was recorded. Restart them
with the commands in "Resume" step 2; the built `.next` is still on disk, so the FE
needs `npx next start -p 3021` only, no rebuild.

- Backend `:8022`, FE prod `:3021`, both configured in `sorento_crm_frontend/.env.local`
  (`NEXT_PUBLIC_API_URL=http://localhost:8022`, `NEXTAUTH_URL=http://localhost:3021`).
  `.env.local` is gitignored.
- Demo request already provisioned end to end (proves the whole path):
  `fad9d51d-f4c8-48c3-839c-d86a4b6de4e8`. Final ledger, read from the database:
  `status=completed`, `provisioned_at` set, both people `user_step=skipped` with the
  pre-existing `user_id` captured, `contact_step`/`agent_step` still `pending` (Slice 2
  and 3). The RQ job returned `{'created': 0, 'skipped': 2, 'failed': 0, 'people': 2}`.
- Second request left in `sent` state for the browser pass, with no people on it yet:
  `d0c4c68e-fc64-41fe-a218-9866c0a608b5`, intake token
  `TSNSNN3539BXXTJ3P1NRXYV0KXT5PESRTCVRGHA86ANTPAQY`
  (the `intake_url` it reports says `:3000`; that is
  `FRONTEND_BASE_URL`, so browse it on `:3021` instead).

## What was verified without a browser

Against the live stack, with curl, before the browser step was reached:

- Public `/me` returns exactly the six allowed template keys - the privacy boundary
  (labels only, never roles or user ids) holds on the wire, not just in the schema.
- `/parse` on the fixture workbook: 18 people, 4 sections, `Ahmad Zulkifli` carries
  `['no email']`, `Rajesh Kumar Nair` carries `['phone not recognised']`.
- `/submit` flips the request to `submitted`, `editable=false`, and the requester note
  persists (this is the bug fixed in `303df1b8` - `_move`'s
  `db.refresh(..., with_for_update=True)` was discarding it).
- Admin detail shows the collision chip `Already a user: Test User`.
- Approve with nobody kept -> 422. Approve -> `{"status":"processing","job_id":...,
  "queued_people":2}`. A second approve -> 422, by construction of the status graph.

The prod build serves both routes (`/onboarding/<token>` 200, the protected queue 200
with the client-side auth redirect). That is a smoke test, not UI verification - both
screens render client-side, so their content is not in the served HTML. **No claim is
made that the UI was visually verified.**

## Offline font build (why the build works with no DNS)

`app/layout.tsx` uses `next/font/google`'s `Inter`, which is fetched at build time, so
`next build` fails outright without DNS. Next ships an env hook for this
(`NEXT_FONT_GOOGLE_MOCKED_RESPONSES`, see
`node_modules/next/dist/compiled/@next/font/dist/google/fetch-css-from-google-fonts.js`).
The stand-in used for the current build lives in the session scratchpad, not the repo:

```
NEXT_FONT_GOOGLE_MOCKED_RESPONSES=<scratchpad>/google-font-mock.js npm run build
```

It maps `https://fonts.googleapis.com/css2?family=Inter:wght@100..900&display=swap` to a
single `@font-face` block. Consequence, and it is why this is a stopgap: the emitted
`.woff2` is not a real font, so pages render in the fallback face. Everything else about
the build is real. **Rebuild without it once DNS is back**, and do not carry this into
any build anyone will look at for visual fidelity.

## What was left in the shared database

The dev database is a production copy. This slice wrote only:

- its own three tables (`onboarding_requests`, `onboarding_people`,
  `onboarding_templates`) plus the two demo requests above;
- the seeded rows its migration owns: 9 `statuses` + 11 `status_transitions` for
  `onboarding_request`, 19 `import_field_alias` rows for `onboarding_person`,
  5 permissions and 28 role grants.

No `users` row was created by provisioning - the demo people were chosen so their emails
already belonged to existing users, which is exactly the `skipped` lane the ledger shows.
The migration was applied with a small `MigrationContext`/`Operations` script rather than
`alembic upgrade head`, because the database is stamped at `353_project_order_inquiry_rename`
from another lane's branch and alembic cannot walk from there to `360`.

The throwaway verification admin created for the API checks was deleted before this
handoff. The RQ worker must be started with `ENABLE_SCHEDULER=false`: with the scheduler
on it drains the *shared* `email_outbox` every 5 seconds, which is other lanes' rows. It
was a no-op here (no SMTP configured, all rows stayed `pending`, none sent), but do not
rely on that.
