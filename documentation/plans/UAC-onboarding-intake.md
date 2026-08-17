# UAC - Onboarding intake, review and provisioning (Slice 1)

**Status:** Approved decisions (captain, 2026-08-14), amended by the hands-on
review of 2026-08-15: the workbook upload is withdrawn (AC-4 below), the three
needs are renamed, and each row carries a free-text role.
**Spec origin:** onboarding-flow design report + captain decisions D1-D7, 2026-08-14. This
document is the self-contained contract; nothing outside the repo needs to be read to build it.
**Binding context:** `PRINCIPLES.md` (step 0 journey-first), `docs/ADR-PRODUCT-STANDARDS.md`,
`docs/ARCHITECTURE-RULES.md`, the Dealer-Kit Edition approval precedent
(`app/services/dealer_kit/edition_service.py` + migration `318_dealer_kit_edition`).

---

## Journey

**Who.** Three actors.

- The **requester** (a department head at a client company - call her Esther). She has no CRM
  account and will never get one. She already holds the list of people, usually as a
  spreadsheet somebody else wrote - she reads it and types it in.
- The **captain** (an admin holding `user_management.onboarding.approve`). Today he retypes
  Esther's list into the user form one person at a time, guesses each person's access by
  copying "someone similar", and creates the same people again by hand in respond.io.
- The **onboarded person** (staff or dealer contact). They receive an invitation and set a
  password. They are never asked to fill anything in.

**What the system already knows** and therefore never asks for: which company the batch lands
in, who asked for it, when the link expires, what access each named template grants, and which
of the submitted people already exist as a user or a contact.

### Requester side

**Step 1 - open the link.** Esther receives a link by email or WhatsApp
(`/onboarding/{token}`). It opens a branded page in the `(auth)` group - no account, no
password, no OTP. The page names her company and who asked her, and shows when the link
expires. **One decision at this step: none.** She only reads.

**Step 2 - give us the people.** She types rows into the grid, one row per person: name,
nickname, **role** in her own words ("Sales admin, KL"), phone, email. Nothing is uploaded;
there is no file to prepare and no file to get wrong. The single decision here is who is on
the list.

**Step 3 - say what each person needs.** Per row she picks an **access template** by its label
- "Salesperson", "Sales admin", "Dealer" - and confirms a multi-select the template pre-fills:
*System account*, *Access to chatbot AI*, *Respond.io account*. She sees **template labels
only** - never a role name, never a permission slug, never the existing user list. Her free-text
role and a *notes for the reviewer* box cover anything the templates cannot say ("like Ahmad's
access but no exports").

**Step 4 - submit.** One submit for the whole batch. She holds a confirmation - "18 people
submitted for review" - and an email saying the same. The **same link** now serves a read-only
status page: per-row approved / rejected-with-reason / provisioned. She gets one further email
when the batch finishes.

### Captain side

**Step 1 - the queue.** A new request appears at **User Management -> Onboarding Requests**
with an in-app notification. The row reads "MOCHA staff - 18 people, from Esther".

**Step 2 - review.** The detail page is *the same grid Esther saw*, plus what she could not
see: per-row **collision chips** computed live against the real unique keys (this email is
already a user; this phone is already a contact), the resolved contents of the template she
picked (roles, companies), and every field editable. He fixes a typo in place. He rejects
individual rows with a reason - the reason is required, exactly as Edition rejection requires
one. **The decisions at this step are per row: keep, edit, or reject.**

**Step 3 - approve.** One button for the batch. It transitions the request through the status
engine and queues the provisioning job. He never leaves the page to create anything by hand.

**Step 4 - watch it land.** Each person row carries a three-lane ledger - *System account /
Access to chatbot AI / Respond.io account* - and the page renders it. A lane that failed says
why, on that person's row, and no failure stops any other person or lane.

**What everyone holds at the end.** Esther holds a status page and a completion email. The
captain holds a batch of CRM users created with the right roles and companies, and a visible
record of anything that did not land. Each onboarded staff member holds the existing invitation
email with a 7-day password link.

---

## Scope of Slice 1

**In:** the three tables, the status graph, the intake token, the public intake endpoints, the
intake FE page, the review queue and detail FE, approve, the **CRM-user provisioning lane**,
collision reporting, and the requester/captain notifications.

**Out, and named so the absence is deliberate:**

- The **respond-contact lane** (create the contact, push it to respond.io, apply the template's
  agent grants) is Slice 2. In Slice 1 the contact lane on a person who needs one stays
  `pending` and the UI says so.
- The **agent-seat lane** and its `onboarding_agent_link_sync` reconciler are Slice 3. Same
  treatment: lane stays `pending`, labelled.
- The **WhatsApp welcome message** is OFF (captain decision D6 - it would spend a WhatsApp
  template on every dealer). No plumbing is added for it in this slice.
- **Team placement in templates.** At most one conversation-SLA tier-1 team per user is a hard
  cross-user invariant (`user_service._assert_single_tier1_team`-class check); a template that
  places people on teams would break it in bulk. Templates carry roles and companies only.

---

## AC-1 The three tables

- **AC-1.1** `onboarding_requests` is company-scoped (`CompanyScopedMixin`): a request belongs
  to exactly one company because everything downstream - which companies the user is granted,
  which teams could ever route to them - is company-scoped. The company is chosen at request
  creation and is **never** something the requester supplies.
- **AC-1.2** `onboarding_people` rows cascade-delete with their request and carry the
  three-lane provisioning ledger *on the person row*, not in a side saga table. Three lanes,
  each with its own step value, its own error text and its own captured artifact id.
- **AC-1.3** `onboarding_templates` carry `role_ids` and `company_ids` (JSONB), the three
  default need-flags, and an optional `captured_from_user_id` recording which user the template
  was built from. `access_agent_ids` is present on the table but unused until Slice 2.
- **AC-1.4** Storing a *template id* on the person row, not a copy of its roles, is deliberate:
  the captain resolves the template at review time and sees what it currently means. Roles are
  read from the template at **provisioning** time, so what is granted is what the review screen
  showed.
- **AC-1.4b** Each person row carries a free-text `role_label` (120 characters, nullable): what
  the requester says this person does. It is prose, never a role id - a picker here would
  expose the role list AC-5.4 exists to hide, and the reviewer is the one who turns "Sales
  admin, KL" into an access template. Editable on both screens, shown on the review detail.
- **AC-1.5** Emails are stored folded (`lower(btrim())`); phones are stored MSISDN-normalised
  via `app/services/phone_utils.normalize_msisdn`. Both are stored **normalised and raw**: the
  raw value is what Esther typed and is what the review screen shows her back, the normalised
  value is what collides.

## AC-2 Status graph (seeded, Edition precedent)

- **AC-2.1** Entity type `onboarding_request`, seeded by migration as `is_system` rows so an
  admin renaming a status in the status UI cannot brick the workflow.
- **AC-2.2** States: `draft` (initial), `sent`, `submitted`, `in_review`, `processing`,
  `completed` (terminal), `partially_completed` (terminal), `rejected` (terminal), `cancelled`
  (terminal).
- **AC-2.3** Edges: draft->sent, sent->submitted, submitted->in_review, in_review->processing,
  processing->completed, processing->partially_completed, in_review->rejected, and
  cancel edges from draft/sent/submitted/in_review.
- **AC-2.4** Every move goes through `status_service.assert_transition_allowed` against a
  row re-read under `with_for_update`, never through an `if`. A second approve is therefore a
  409 by construction, not a race.
- **AC-2.5** A request cannot be edited by the requester once it leaves `sent`. The public
  write endpoints check the status, not the token alone.

## AC-3 The intake token (captain decision D1)

- **AC-3.1** One token per request, minted at creation. Crockford base32, 48 characters, from
  the same alphabet the portal already uses (no I/L/O/U, so a token read aloud over the phone
  survives).
- **AC-3.2** **Multi-use until submitted.** Esther legitimately edits over several days and
  re-opens the link; a one-shot `ApprovalToken` shape would break that on the first reload.
- **AC-3.3** 14-day default expiry, revocable, re-sendable. Revoking is immediate and the
  public endpoints answer 401 afterwards.
- **AC-3.4** After submission the same token serves the **read-only status page**. It does not
  need re-minting and it does not grant writes.
- **AC-3.5** No OTP. The data behind the token is the batch of names, phones and emails Esther
  herself supplied; a leaked link exposes her own submission, not CRM data. This is the
  deliberate difference from the contact portal, which fronts real CRM records.
- **AC-3.6** Public endpoints live under `/api/v1/public/onboarding/*` and take the token in an
  `X-Onboarding-Token` header **or** a `token` query parameter, mirroring `get_portal_token`.
## AC-4 Sheet parse - WITHDRAWN

**Upload dropped by captain decision 2026-08-15; requesters type rows in the system.**

The whole of AC-4 (workbook reader, `import_field_alias` doc type `onboarding_person`, header
detection, repeated-header and section-label heuristics, report-furniture filtering, per-row
parse problems, `POST /public/onboarding/parse` and its per-IP rate limit) is withdrawn. The
reader, its tests, its fixture workbook and the endpoint are deleted rather than left dormant:
a parser nothing calls is a parser nobody maintains, and it carried the two review findings
(parse clobbers typed rows, an all-caps name swallowed as a section) that this decision
retires.

Consequences elsewhere in this contract:

- The **Issues** column (per-row parse problems) and the **Section** column (`section_label`)
  are gone from the grid. `onboarding_people.section_label` stays as a nullable column so the
  change needs no destructive migration; nothing reads or writes it.
- The request's `source_file_name` / `source_storage_*` are no longer surfaced. There is no
  source file.
- Phone normalisation (`normalize_msisdn`, MY region) and email folding survive - they are
  properties of a stored value, not of a parser - and live in `onboarding_service` now.
- The intake email tells the requester to type her list in, not to upload one.

## AC-5 Intake page (requester)

- **AC-5.1** Route `/onboarding/{token}` in the `(auth)` group. Branded, NextAuth-independent,
  no sidebar.
- **AC-5.2** Renders at 375px and 1280px. The grid scrolls inside its own container; the page
  body never scrolls horizontally.
- **AC-5.3** Per-row: name, nickname, free-text **role**, phone, email, a template picker
  (label + description only), a **Needs multi-select** pre-filled from the template offering
  *System account* / *Access to chatbot AI* / *Respond.io account*, and a note; plus a batch
  note. Rows are added with "Add a person" and removed with the standard trash-can button
  behind the standard confirm dialog. The multi-select is the shared
  `SearchableMultiSelect` - a stack of checkboxes was this grid's own invention. Every
  dropdown in the feature sizes its menu to the option text and wraps a long label rather than
  truncating it.
- **AC-5.4** The template picker never exposes role names, permission slugs, company ids or
  the user list. The public template endpoint serializes `id`, `name`, `description` and the
  three default flags - nothing else. This is the privacy boundary, enforced in the schema, not
  in the component.
- **AC-5.5** No UUIDs are rendered anywhere on the page (cursor rule).
- **AC-5.6** Loading, empty, error, saved and submitted states are all designed; after
  submit the page renders the read-only status view of the same grid.

## AC-6 Review queue and detail (captain)

- **AC-6.1** Queue is a shared `DataGrid` listing at
  `/user-management/onboarding-requests`, reached by a sidebar entry under **User Management**,
  gated on `user_management.onboarding.view`. Fixed layout, resizable columns, explicit sizes,
  `truncate` + `title` on long text.
- **AC-6.2** Detail page at `/user-management/onboarding-requests/{id}` renders **every**
  section including empty ones, with explicit empty states, and carries prev/next record
  navigation (`components/common/RecordNavigation`).
- **AC-6.3** Read view and edit view have the same structure: editing a person row swaps a
  value for an input **in place**. Read-only metadata (created, submitted, token expiry) lives
  in the header meta strip, never inside an editable section.
- **AC-6.4** Collision chips are computed **live** on read, never stored:
  `email -> users.email`, `phone -> users.contact_number`, `phone ->
  respond_contacts.phone_number`, all compared on the normalised value. An existing artifact is
  **not an error**: it renders as "already a user" and pre-decides that lane as `skipped`.
- **AC-6.5** Per-row reject requires a reason (422 without one, checked server-side, not only
  in the dialog).
- **AC-6.6** Approve is one action for the batch, gated on
  `user_management.onboarding.approve` - a **separate** permission from view/edit, per the
  Edition precedent.
- **AC-6.7** Delete of a request is a hard delete behind `ConfirmDeleteDialog` with the
  standard "Confirm delete" / "This action cannot be undone" copy. Never `window.confirm`.

## AC-7 Provisioning (user lane only in this slice)

- **AC-7.1** Approve enqueues ONE RQ job on the **`imports`** queue. The worker owns that
  queue; the API process must not drain it.
- **AC-7.2** The job walks `review_status == 'approved'` people in row order. For each person
  needing a system account it calls the existing `UserService.invite_user` with the template's
  `role_ids` and `company_ids`, then sends the existing invitation email.
- **AC-7.3** An email that already belongs to a user is **not a failure**: the lane is
  `skipped`, the existing `user_id` is captured on the row, and the reason is shown. Onboarding
  someone who half-exists fills in what is missing.
- **AC-7.4** A lane failure is recorded on that person's row with its error text, and the job
  continues. **Never per-batch.** One malformed email cannot stop the other seventeen people.
- **AC-7.5** The job is idempotent. Re-running it re-walks the lanes and touches only those in
  `pending` or `failed`; `done` and `skipped` are left alone. A crash mid-batch is recovered by
  re-running, not by cleanup.
- **AC-7.6** On completion the request moves to `completed` when every approved person's user
  lane is `done` or `skipped`, and to `partially_completed` when any is `failed`. Contact and
  agent lanes are **not** counted in this slice - they are `pending` by design and Slice 2/3's
  inbox. The UI labels them so, rather than implying they failed.
- **AC-7.7** Post-commit side effects (notifications) are best-effort: they catch and warn, and
  never raise, so a batch that actually provisioned cannot report a failure.

## AC-8 Notifications

- **AC-8.1** Requester, on submit: email via `email_outbox_service.enqueue`, new registry event
  `onboarding_submitted`.
- **AC-8.2** Requester, on batch completion: email, new registry event `onboarding_completed`,
  carrying the counts.
- **AC-8.3** Captain, on submission: in-app notification via
  `NotificationService.create_with_channel_preferences`, type `onboarding_submitted`, to the
  user who created the request (and, when set, its reviewer).
- **AC-8.4** Onboarded staff: the **existing** invite email. No new template, no new send path.
- **AC-8.5** Nothing is sent to contact-only people in this slice (D6).

## AC-9 Permissions

New slugs in `app/rbac/permission_registry.py`, granted by migration to whichever roles already
hold `user_management.users.add` (view/add/edit/delete) and `user_management.users.edit`
(approve) - the same authority in bulk, so the feature is not invisible on first deploy:

`user_management.onboarding.view` / `.add` / `.edit` / `.delete` / `.approve`.

Templates are administered under `.edit`; there is no separate template permission.

## AC-10 Tests

- **pytest**: token resolve/expiry/revoke/post-submit-read-only; the role round trip
  (typed on her rows, edited by the reviewer, returned on the detail); every public endpoint's happy path, 401 and
  validation error; every admin endpoint's happy path and permission denial; the status
  transitions including the double-approve 409; the provisioning job's create / pre-existing /
  failure / re-run paths; collision detection. Postgres only - **never** sqlite, and every test
  seeds its own FK chain rather than borrowing an existing row.
- **vitest**: intake grid and review grid components across loading / empty / error / data /
  submitted states; the template picker's label-only contract; the needs multi-select and its
  read-only rendering; the hooks.
- **playwright**: sidebar click -> review queue -> detail -> approve, asserting the
  `/api/v1/*` calls actually fired.
