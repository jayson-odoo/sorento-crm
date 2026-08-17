# PLAN - Onboarding intake, review and CRM-user provisioning (Slice 1)

**Status:** Phases 1 and 2 shipped (FE on the real API, backend + tests green), then
restandardized onto the repo's list/detail idiom; Phase 3 (review) in progress, with the
captain's hands-on round of 2026-08-15 applied (section 7) and the review fixes of 2026-08-16
(section 8). Section 2.6's endpoint table and 2.7's registry note describe what actually
shipped, not the original sketch.
**Contract:** `documentation/plans/UAC-onboarding-intake.md`. Read that first; it carries the
Journey and every AC this plan implements. Nothing outside the repo is required.

---

## 0. Shape of the work

Three tables, one status graph, one token, two FE surfaces (public intake, admin review), one
RQ job. (A workbook parser was built and then withdrawn - see section 7.) The parts that
already exist and are being *reused* rather than rebuilt:

| Need | Reused from |
|---|---|
| Crockford token alphabet | `app/services/portal_service.py._crockford_token` (extracted to a shared helper) |
| Token-gated public route shape | `app/api/v1/public/portal.py.get_portal_token` |
| Status graph + guarded transitions | `app/services/status_service`, migration `318_dealer_kit_edition`, `dealer_kit/edition_service.py` |
| User creation with roles/companies | `app/services/user_service.UserService.invite_user` |
| Invitation email | `app/api/v1/user_management/users.py._send_invitation_link_for_user` |
| Background job | `app/services/queue_service.enqueue_job(..., queue_name='imports')` |
| Requester email | `app/services/email_outbox_service.enqueue` + `email_event_registry` |
| Captain in-app notification | `NotificationService.create_with_channel_preferences` |
| Phone normalisation | `app/services/phone_utils.normalize_msisdn` |
| Company partitioning | `app/models/base.CompanyScopedMixin`, `company_scope(db, ...)` |

## 1. Migration

**One migration, `360_onboarding_slice1`.** The branch starts from **two** alembic heads
(`323_cs_company_backfill` and `356_human_source_boost_seed`), so this migration's
`down_revision` is the tuple of both - it merges the graph and adds the feature in one step,
leaving a single head. Numbers 324 and 357-359 are claimed by other in-flight lanes; 360 avoids
them.

Contents, all idempotent (`IF NOT EXISTS` / SELECT-then-INSERT), because the dev database is
shared across worktrees:

1. `onboarding_templates`, `onboarding_requests`, `onboarding_people` (DDL below).
2. The `onboarding_request` status graph, seeded exactly as migration 318 seeds
   `dealer_kit_edition`: statuses keyed on `(entity_type, key)` with `scope_id IS NULL`,
   `is_system = true`, then transitions keyed on `(entity_type, from, to)`.
3. `import_field_alias` rows for doc type `onboarding_person`.
4. The five permission slugs, granted to roles that already hold `user_management.users.add`
   (view/add/edit/delete) and `user_management.users.edit` (approve).

`downgrade()` drops the three tables, the graph edges then the statuses, the aliases and the
permission grants then the permissions - children before parents throughout.

**Migration `361_onboarding_role_label`** follows it: it adds `onboarding_people.role_label` and
deletes the doc-type-`onboarding_person` aliases seeded above, which existed only for the
withdrawn reader (section 7). 360's seeder is left alone because it has already run on shared
databases; 361's downgrade restores the rows. Single head after both: `361_onboarding_role_label`.

### DDL

```
onboarding_templates
  id UUID PK, name VARCHAR(120) NOT NULL, description TEXT NULL,
  is_active BOOL NOT NULL DEFAULT true,
  role_ids JSONB NOT NULL DEFAULT '[]', company_ids JSONB NOT NULL DEFAULT '[]',
  access_agent_ids JSONB NOT NULL DEFAULT '[]',        -- written, unused until Slice 2
  default_needs_system_account BOOL NOT NULL DEFAULT true,
  default_needs_respond_contact BOOL NOT NULL DEFAULT false,
  default_needs_agent_seat BOOL NOT NULL DEFAULT false,
  captured_from_user_id UUID NULL, created_by_user_id UUID NULL,
  company_id UUID NULL FK companies, created_at, updated_at
  UNIQUE (company_id, lower(btrim(name)))              -- one label per company

onboarding_requests
  id UUID PK, company_id UUID NOT NULL FK companies,
  title VARCHAR(200) NOT NULL,
  requester_name VARCHAR(150) NOT NULL, requester_email VARCHAR(255) NOT NULL,
  requester_phone VARCHAR(32) NULL,
  token TEXT NOT NULL UNIQUE, expires_at TIMESTAMP NOT NULL, revoked_at TIMESTAMP NULL,
  status_id UUID NOT NULL FK statuses, status_key VARCHAR(64) NOT NULL,
  requester_note TEXT NULL, reviewer_note TEXT NULL,
  created_by_user_id UUID NULL, sent_at, submitted_at, reviewed_by_user_id UUID NULL,
  reviewed_at, provisioned_at,
  source_file_name VARCHAR(255) NULL, source_storage_provider VARCHAR(16) NULL,
  source_storage_key TEXT NULL,
  created_at, updated_at
  INDEX (company_id, status_key), INDEX (token)

onboarding_people
  id UUID PK, request_id UUID NOT NULL FK onboarding_requests ON DELETE CASCADE,
  company_id UUID NULL FK companies,
  row_number INT NOT NULL,
  full_name VARCHAR(200) NOT NULL, nick_name VARCHAR(100) NULL,
  role_label VARCHAR(120) NULL,                              -- migration 361, free text
  phone_raw VARCHAR(64) NULL, phone VARCHAR(32) NULL,        -- phone = normalised MSISDN
  email_raw VARCHAR(255) NULL, email VARCHAR(255) NULL,      -- email = lower(btrim())
  section_label VARCHAR(120) NULL,                           -- retained, no longer written
  template_id UUID NULL FK onboarding_templates ON DELETE SET NULL,
  requester_note TEXT NULL, reviewer_note TEXT NULL,
  needs_system_account BOOL NOT NULL DEFAULT true,
  needs_respond_contact BOOL NOT NULL DEFAULT false,
  needs_agent_seat BOOL NOT NULL DEFAULT false,
  review_status VARCHAR(20) NOT NULL DEFAULT 'proposed',     -- proposed|approved|rejected|on_hold
  rejection_reason TEXT NULL,
  user_id UUID NULL FK users ON DELETE SET NULL,
  user_step VARCHAR(20) NOT NULL DEFAULT 'pending',          -- pending|done|failed|skipped
  user_error TEXT NULL,
  respond_contact_id UUID NULL,
  contact_step VARCHAR(20) NOT NULL DEFAULT 'pending',       -- + created_local|pushed (Slice 2)
  contact_error TEXT NULL,
  linked_respond_user_id VARCHAR(64) NULL,
  agent_step VARCHAR(20) NOT NULL DEFAULT 'pending',         -- + awaiting_invite|linked (Slice 3)
  agent_error TEXT NULL,
  invite_marked_sent_at TIMESTAMP NULL, provisioned_at TIMESTAMP NULL,
  created_at, updated_at
  UNIQUE (request_id, row_number)
  INDEX (request_id, review_status)
```

Lane columns are `VARCHAR`, not a PG enum: Slices 2 and 3 add values to two of them, and
adding a value to a PG enum inside a transaction is the migration that goes wrong.

**Why the ledger lives on the person row** rather than in a saga table: three lanes with
independent state and independent error text is the `respond_synced` pattern scaled up, and it
is what makes partial state *visible*. The review page renders chips straight off these
columns, which is the captain's stated pain.

**Slice-1 honesty about the two dormant lanes.** `contact_step` and `agent_step` stay `pending`
on people who need them. They are not `skipped` (nothing decided to skip them) and not `failed`
(nothing tried). The request's terminal status is computed over the **user lane alone**
(AC-7.6) and the FE labels the other two "not yet automated" rather than implying failure.
When Slice 2 lands, `contact_step = 'pending'` is exactly its backlog query.

## 2. Backend

### 2.1 Models - `app/models/onboarding.py`

`OnboardingTemplate`, `OnboardingRequest`, `OnboardingPerson`. All three carry
`CompanyScopedMixin` (the new-table guard requires it of anything with a `company_id`).
`OnboardingRequest.people` is a `relationship` with `cascade="all, delete-orphan"` ordered by
`row_number`. Registered in `app/models/__init__.py`.

### 2.2 Shared token helper - `app/services/crockford.py`

`crockford_token(length: int = 48) -> str` plus the alphabet constant, extracted so the
onboarding token and the portal token cannot drift onto different alphabets.
`portal_service._crockford_token` becomes a one-line delegate; its behaviour is unchanged and
its existing tests must stay green.

### 2.3 Parser - REMOVED

`app/services/onboarding_reader.py`, `tests/test_onboarding_reader.py` and the fixture workbook
are deleted; **upload dropped by captain decision 2026-08-15; requesters type rows in the
system.** What the sketch below described no longer exists, and is kept only so a reader of the
git history knows what was withdrawn rather than lost.

<details>
<summary>The parser as built (withdrawn)</summary>

### 2.3 Parser - `app/services/onboarding_reader.py` (deleted)

Public surface: `read_workbook(file_data, resolver=None, *, db=None) -> OnboardingReadResult`
with `rows: list[OnboardingPersonRow]`, `problems: list[RowProblem]`, `unmapped_headers`,
`missing_columns`, `total_rows`, `sections: list[str]`, and `ok` = no missing columns. Same
shape as `CustomerReadResult` so the two readers stay comparable.

Doc type `onboarding_person`; readable fields `full_name`, `nick_name`, `phone`, `email`.
Only `full_name` is header-required (AC-4.8): a sheet with names and no emails is still a
usable list of people.

Algorithm, in order:

1. `sheet_rows(file_data)` into a list. Any exception -> one `RowProblem(0, ...)` plus
   `missing_columns`, per the customer reader.
2. Find the header row: the first row whose cells resolve a `full_name` column. Record the
   column map and the unmapped headers.
3. Walk the rows after it. For each:
   - **Repeated header** - the row re-resolves `full_name` *and* at least one other mapped
     field to the same positions. Skip, count nothing. (AC-4.3)
   - **Section label** - exactly one non-empty cell, in a column that is either unmapped or
     the name column, whose text resolves to no field and does not look like a person (no `@`,
     no digit run of 7+). Set `current_section`, append to `sections`, count nothing. (AC-4.4)
   - **Furniture** - `_is_report_furniture` over every non-empty cell (imported from
     `customer_import_reader`, not re-implemented). Skip. (AC-4.5)
   - Otherwise a **data row**: `total_rows += 1`. No name -> `RowProblem(row, "no staff
     name")` and skip. Otherwise emit a row carrying raw + normalised email and phone, plus
     `section_label = current_section`, and append a non-fatal `RowProblem` for a missing
     email or a phone `normalize_msisdn` could not read.

The parser never touches the database beyond building the `AliasResolver`, so it is testable
against a file alone.

</details>

`_plausible_msisdn` was the one piece worth keeping - it is a property of a stored phone
number, not of a parser - and now lives in `onboarding_service`.

### 2.4 Service - `app/services/onboarding_service.py`

Functions (module-level, matching `edition_service`'s shape):

- `create_request(db, *, company_id, title, requester_*, expiry_days=14, user_id)` - mints the
  token, seats the request at `draft`.
- `get_request` / `list_requests(db, *, status_key=None, ...)`.
- `send_request(db, id, *, user_id)` - `draft -> sent`, stamps `sent_at`, enqueues the intake
  email to the requester.
- `resolve_token(db, raw) -> OnboardingRequest` - raises `OnboardingAuthError` on unknown,
  expired or revoked. Read under `company_scope(db, None)`; the caller then narrows scope to
  the request's company, exactly as `public/catalogue.py` does.
- `revoke(db, id)` / `regenerate_token(db, id)`.
- `replace_people(db, request, rows)` - the requester's draft save. Whole-list replace keyed on
  `row_number`; refused unless the request is `sent`.
- `submit(db, request)` - `sent -> submitted`, stamps `submitted_at`, notifies (best-effort).
- `start_review(db, id, *, user_id)` - `submitted -> in_review`.
- `update_person(db, person_id, patch)` / `reject_person(db, person_id, *, reason)` (422 on a
  blank reason) / `approve_person`.
- `collisions_for(db, request) -> dict[person_id, list[Collision]]` - three live queries, no
  storage (AC-6.4).
- `approve(db, id, *, user_id)` - `in_review -> processing` through `_move` (row locked and
  re-read, `assert_transition_allowed`), then enqueues the job **after** the commit.
- `finalise(db, request)` - called by the job: `processing -> completed | partially_completed`.

`_move` is copied in spirit from `edition_service._move`: refresh with `with_for_update`,
resolve the target status by key, `assert_transition_allowed`, apply the stamp callback only
after legality, commit, translate `IntegrityError` to a 409.

### 2.5 Provisioning task - `app/tasks/onboarding_tasks.py`

`provision_onboarding_request(request_id: str)`, enqueued on `imports`.

Own session, own `company_scope(db, frozenset({company_id}))`. Walks approved people in
`row_number` order. Per person:

- Lane `user`, only when `needs_system_account` and the lane is `pending` or `failed`
  (AC-7.5).
- Existing user by folded email -> `user_step = 'skipped'`, `user_id` captured,
  `user_error = None` and the reason carried in the response as a chip, not as an error.
- Otherwise `UserService(db).invite_user(UserCreate(...), invited_by_user_id=...)` with the
  template's `role_ids` / `company_ids`, then the invitation email.
- Any exception -> `user_step = 'failed'`, `user_error = str(exc)`, commit that row, continue
  (AC-7.4). The loop's try/except is **per person per lane**, never around the batch.

Then `finalise`, then the requester completion email - best-effort, caught and warned
(AC-7.7). Because this file lives under `app/tasks/`, the Worker session must be restarted
after editing it.

### 2.6 Routes

**Public** - `app/api/v1/public/onboarding.py`, mounted in
`app/api/v1/public/__init__.py` at prefix `/onboarding`:

| Method + path | Behaviour |
|---|---|
| `GET /me` | Request context: company name, requester name, expiry, status, template labels, current rows. Read-only after submit. |
| `GET /templates` | `id`, `name`, `description`, three default flags. **Nothing else** (AC-5.4). |
| `PUT /rows` | Save the draft rows. 409 unless status is `sent`. |
| `POST /submit` | `sent -> submitted`, notifies. |

`get_onboarding_token` mirrors `get_portal_token`: header `X-Onboarding-Token` or `?token=`,
401 with a plain message on anything unresolvable.

**Admin** - `app/api/v1/user_management/onboarding.py`, mounted under the existing
`user_management` router (so it inherits `require_module_enabled_with_api_key('base')`):

| Method + path | Behaviour |
|---|---|
| `GET /requests` | One page of the review queue. Takes `page`, `limit`, `query`, `status_key`, `sort`, `dir` and answers the standard `ListResponse` envelope (`data` + `pagination`). Sortable on `title`, `company_name`, `requester_name`, `status`, `submitted_at`, `expires_at`, `created_at`; an unknown column falls back to `created_at desc` rather than erroring. Ordering ends on `id`, so a row cannot land on two pages, and nulls sort last, so drafts do not outrank fresh submissions. |
| `GET /requests/neighbours` | `{total, index, prev_id, next_id}` for the detail page's prev/next pager, taking the same filter and sort params as the list. Declared BEFORE `/requests/{id}`: FastAPI matches in declaration order, so the other way round "neighbours" is read as an id. |
| `POST /requests` | Create. `company_id` is required - it decides what approval actually grants. |
| `GET\|DELETE /requests/{id}` | Detail (collisions computed on read), and hard delete (people cascade). |
| `POST /requests/{id}/send` | Mint and email the intake link. |
| `POST /requests/{id}/revoke` | Kill the link immediately. |
| `POST /requests/{id}/regenerate-token` | Issue a new link; the old one stops working. |
| `POST /requests/{id}/start-review` | `submitted -> in_review`. |
| `PUT /requests/{id}/people/{person_id}` | Edit one person. |
| `POST /requests/{id}/people/{person_id}/keep\|hold\|reject` | Per-person verdict. `reject` requires a reason, checked here and not only in the dialog. |
| `POST /requests/{id}/approve` | `in_review -> processing`, and queues provisioning. |
| `GET\|POST /templates`, `PUT\|DELETE /templates/{id}`, `POST /templates/capture-from-user/{user_id}` | Template administration. |

Every per-person route resolves the person through the request named in the path and 404s on a
mismatch. Both ids are caller-supplied, and without that check a write addressed to request A
but naming request B's person landed on B while answering with A's detail - the caller saw
their own batch unchanged and never learnt that somebody else's had been edited.

Permission per route: `.view` on reads, `.add` on create/send, `.edit` on writes and templates,
`.delete` on delete, `.approve` on approve. `DELETE` is a hard delete (people cascade).

### 2.7 Registry additions

- `app/rbac/permission_registry.py`: the five slugs.
- `app/services/email_event_registry.py`: `onboarding_intake_link` (priority 0 - it is the
  link she is waiting for), `onboarding_submitted`, `onboarding_completed`.

**Not** `app/services/list_query_registry.py`. That registry serves the saved-filter and
server-side-export path, and the queue needs neither: it pages through its own endpoint and
lets column preferences key on the DataGrid default (the route pathname). The embedded people
grid opts out of preferences altogether with `listingKey=""`, or it would store a separate
column layout per request id and per intake token.

## 3. Frontend

### Phase 1 - mock first (no backend calls)

Built and browser-verified before any of section 2 is written, per the repo's methodology.

**Public intake** - `app/(auth)/onboarding/[token]/page.tsx` plus
`app/(auth)/onboarding/components/`:

- `IntakeHeader` - company, requester, expiry, status.
- `PeopleGrid` - the editable grid; template picker, needs multi-select, role, note. One
  component serving intake and review, with a `mode: 'intake' | 'review' | 'readonly'` prop, so
  the two screens cannot drift.
- `SubmitBar` + `SubmittedStatusView`.

The dropzone that used to sit above the grid is gone with the upload path (section 7).

**Admin** - `app/(protected)/user-management/onboarding-requests/page.tsx` (DataGrid queue) and
`[id]/page.tsx` (detail: header meta strip, the same `PeopleGrid` in `review` mode, collision
chips, per-row reject dialog, approve button, three-lane ledger chips). Sidebar entry added to
**both** menu blocks in `config/menu.config.tsx` under User Management, gated on
`user_management.onboarding.view`.

Verification: navigate from `/`, expand the User Management sidebar group, click the entry -
never a direct deep URL - snapshot at 1280 and 375, check the console, screenshot golden path
plus empty/error states.

### Phase 2 - real wiring

`services/onboardingService.ts` (admin) and `app/(auth)/onboarding/lib/onboarding-client.ts`
(public, token header) carrying the documented contract at the top of the file. Hooks
`useOnboardingRequests` / `useOnboardingRequest` / `useOnboardingMutations` built on the shared
`useCreateMutation` / `useUpdateMutation` / `useDeleteMutation`. `extractApiError` and
`buildDataGridParams` used, never hand-rolled. Mocks deleted except where a test uses them.

## 4. Tests (Phase 2, not deferred)

- **pytest** - `tests/test_onboarding_service.py` (token, transitions, collisions, the role
  round trip, provisioning lanes) and `tests/test_onboarding_api.py` (both HTTP surfaces).
  Postgres only, via `tests/_pg_fixture.blank_session()`; every test seeds its own
  company/role/template/request chain with a marker prefix and cleans children first. No
  `LIMIT 1` off a live table. The reader's own suite and its fixture workbook were deleted with
  the reader (section 7).
- **vitest** - `PeopleGrid` across loading/empty/error/data/submitted, the template picker's
  label-only contract, the needs multi-select and its read-only rendering, the role cell, the
  collision chips, the reject dialog's required reason. `DataGrid` listings mock
  `useListingColumnPreferences` so rows actually mount.
- **playwright** - `e2e/onboarding-review.spec.ts`: sidebar -> queue -> detail -> approve,
  asserting the `/api/v1/user-management/onboarding/*` calls the flow makes.

  **Deferred, deliberately.** Playwright drives a system Chrome that is not installed on the
  machine this slice was built on, so the spec could only be committed unrun - an e2e test
  nobody has ever seen pass is worse than an absent one, because the first person to run it
  cannot tell a real regression from a spec that never worked. The same flow IS verified,
  end to end against the live stack, in the browser log below; the spec goes in as soon as a
  runnable Chrome exists. Tracked as the one open item against AC-10.

## 5. Order of work

1. UAC + this plan. *(done)*
2. Phase 1 FE mock, browser-verified at 375 and 1280.
3. Migration + models.
4. Token + public routes + tests.
5. Admin routes + service + status transitions + tests.
6. Provisioning task + tests.
7. FE off mocks; vitest + playwright.
8. Prod build, `/code-review`, PR.

## 6. Risks

- **Two alembic heads at branch point.** Handled by the tuple `down_revision`; re-check
  `alembic heads` after any rebase and keep it at one. After migration 361 the single head is
  `361_onboarding_role_label`.
- **The shared dev database is a production copy.** Every write this feature makes is to its
  own new tables plus the seeded graph/permission rows. Nothing else is touched.

## 7. Captain's review round, 2026-08-15

Six changes off a hands-on session on the running stack. Internal field names are unchanged
throughout - `needs_respond_contact`, `needs_agent_seat`, `contact_step`, `agent_step` still
say what they always said, because this was a vocabulary decision and renaming a column is a
migration.

1. **Labels.** "WhatsApp contact" is now **Access to chatbot AI**; "Chat-agent seat" is now
   **Respond.io account**; "System account" is unchanged. Applied to the needs options, the
   lane ledger, the reviewer's counts strip ("Respond.io accounts N"), the contact collision
   chip, and this contract's prose. `NEED_LABELS` in `PeopleGrid.tsx` is the one place the
   three words live.
2. **Needs is a multi-select.** The checkbox stack is replaced by the shared
   `SearchableMultiSelect` - the component every other picker in the app uses. The patch it
   raises carries all three flags, not only the one that moved: the selection IS the answer, so
   an unticked option has to arrive as `false` rather than as an absent key. Locked and
   read-only modes render the chosen labels as plain text.
3. **Dropdowns fit their options and wrap.** `SearchableSelect` and `SearchableMultiSelect`
   gained an opt-in `wrapOptions`: the menu grows to the widest option (capped at the viewport,
   never narrower than the trigger) and a long label wraps instead of truncating. Fixed in the
   shared components rather than forked, and set on the template picker, the needs
   multi-select, the queue's status filter and the create dialog's company select.
   `SearchableMultiSelect` also gained `id`, for parity with `SearchableSelect`, so a
   `<label htmlFor>` can point at its trigger.
4. **Delete affordance.** The row's text "Remove" button is a ghost trash-can icon button
   (`Trash2`, `mode="icon"`), still behind `ConfirmDeleteDialog` with the standard copy.
5. **Role.** `onboarding_people.role_label` (VARCHAR(120), nullable, migration
   `361_onboarding_role_label`), on `DraftRowIn` / `PersonPatchIn` / `PersonOut` with
   `max_length=120`, in `EDITABLE_PERSON_FIELDS`, and a Role column in the grid on both
   screens (`BufferedInput`, commit on blur). Free text on purpose: a role picker would expose
   the role list AC-5.4 hides.
6. **Upload dropped by captain decision 2026-08-15; requesters type rows in the system.**
   Deleted: `app/services/onboarding_reader.py`, `tests/test_onboarding_reader.py`,
   `tests/fixtures/onboarding_phone_list.xlsx` and its generator,
   `POST /api/v1/public/onboarding/parse` with its rate-limit settings, the parse schemas, the
   FE dropzone and `parseSheet`, the Issues and Section columns, `ProblemChips`, and the
   "Source file" meta item. Migration 361 also deletes the `import_field_alias` rows for doc
   type `onboarding_person`, which existed only for that reader; the deletion lives in 361
   rather than in 360, whose seeder has already run on shared databases, and 361's downgrade
   puts the rows back.

   Two things are deliberately kept. `onboarding_people.section_label` stays as a nullable
   column - nothing reads or writes it, and dropping a populated column is destructive for no
   gain. `_plausible_msisdn` moved into `onboarding_service`: it judges a stored phone number,
   not a spreadsheet.

### Open items (recorded, not built)

- **Access templates have no admin UI.** The CRUD endpoints exist
  (`GET|POST /user-management/onboarding/templates`, `PUT|DELETE .../templates/{id}`,
  `POST .../templates/capture-from-user/{user_id}`), and the pickers read them, but there is no
  page to create or edit one - so today a template is created through the API. The captain
  asked where he configures them; the honest answer is "not built yet".
- **Intake-link expiry has no UI control.** `expiry_days` is only settable at creation
  (default 14) and "Issue a new link" resets to 14 days. Nothing on the create dialog or the
  detail page lets the captain choose a different window or extend a live link.
- **The `cancelled` state has no route.** Migration 360 seeds it and its four incoming edges,
  and the dead `cancel()` service function has been deleted rather than exposed; nothing moves
  a request there today. The seeded edges stay - removing them is a destructive migration for
  no gain.
- **The batch note is not part of a saved draft.** "Save draft" persists the people rows
  (`PUT /public/onboarding/rows`); the batch-level `requester_note` is stamped by `submit`
  alone, so a note typed and left unsent does not survive a reload.

## 8. Fixes after the review round, 2026-08-16

1. **"Save draft" on the intake page.** AC-3.2 promises a link the requester edits over several
   days and the intake email says so, but the only call to `saveRows` was the one `submit` made
   on its way out: her rows lived in component state and closing the tab lost them. The button
   calls the endpoint that already persists rows while the request is `sent`, and `GET /me`
   already rehydrates them, so no server change was needed. Deliberately not autosave, not
   local storage, not dirty tracking, and not a `beforeunload` handler.
2. **A bad `template_id` is a 422 on both writers.** It is a UUID foreign key taken straight
   from client input: `"nope"` reached Postgres as `invalid input syntax for type uuid` and a
   well-formed unknown id as a foreign-key violation, so a token holder saw a 500 where every
   other bad field answers 422. Checked in `_apply_person_values`, which is the one path both
   the public save and the reviewer's patch go through.
3. **A bad `company_id` is a 422 on create.** Title, email and expiry were validated and the
   company was not, though it decides what approving the batch grants. An unknown id escaped
   `db.commit()` as a foreign-key violation; an out-of-scope one committed and then vanished
   behind the caller's own scope filter, 404ing them on the request they had just created.
