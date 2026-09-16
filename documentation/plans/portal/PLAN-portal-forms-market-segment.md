# PLAN - Portal forms: grant by market segment, every kind gated, per-contact override for all five

Status: r4, 16 Sep 2026: PR #963 ready for review (reviewer + security closed, browser pass green), awaiting owner test on :3082 then merge
UAC: `documentation/plans/portal/portal-forms-market-segment-acceptance-criteria.md`
Branch: `feat/portal-forms-market-segment`, worktree `.claude/worktrees/portal-forms-market-segment`
Lane stack: FE :3080, BE :8080, DB `sorento_pfms` (clone of the dev DB, see Lane setup)

All line refs are `origin/main` at 81bc9e132.

## Why

The owner wants to show the price tag request to one contact and hide any of the four
legacy kinds (complaint, stock inquiry, purchase request, sponsorship form) per contact.
Today only `price_tag_request` is gated; the four legacy kinds are hardcoded always-on in
`PortalLanding.tsx:95-111` and never checked on the backend. The grant config lives on
contact access types, and the owner ruled the group source should be market segment instead.

## What exists (measured on the prod copy, 16 Sep)

- Resolver `app/services/portal_form_visibility_service.py:26-65`: union of
  `ContactAccessType.portal_form_types` over the contact's access types, then
  `contact_portal_form_overrides` rows win (`app/models/price_tag.py:45-77`, unique on
  `(contact_id, form_type)`, no FK to any group table).
- Admin override route `app/api/v1/user_management/contact_portal_forms.py`
  (`GATED_FORM_TYPES = ("price_tag_request",)` line 38, view builder `_build_view` line 55).
- Public gate: `_require_price_tag_request_visible` `portal.py:766-779`, `_assert_visible`
  `portal_price_tag.py:67`. Legacy kinds pass through three membership checkers only:
  `_check_kind` `portal.py:701` (6 routes), `_check_revisable_kind` `:716` (5 routes),
  `_check_attachment_kind` `:759` (2 routes); attachment download `:1328` and delete `:1476`
  derive the kind from the `EntityAttachmentLink` row and bypass all three.
- `SUPPORTED_TYPES` / `GRANTABLE_PORTAL_FORM_TYPES` `app/services/portal_service.py:77-83`.
- Market segment: model `app/models/access.py:130-155` (2 rows: retail, project, both active),
  m2m `respond_contact_market_segments` `:160-178`, schemas `app/schemas/market_segment.py`
  (`is_requestor_selectable` at 16 and 28), service `market_segment_service.py:123-168`,
  route `market_segments.py:42-78`. Pattern migration `alembic/versions/308_requestor_uploader_attr.py`.
- Access type field: model `access.py:83`, schemas `user.py:459-514`, service
  `contact_access_type_service.py:64,219,241`, FE admin
  `contact-access-types/components/ContactAccessTypesAdmin.tsx:27,44-47,108,119,138,167,184,238-261,418-428`,
  service `contactAccessTypeService.ts:21,65`, test `ContactAccessTypesAdmin.portalForms.test.tsx`.
- FE landing `PortalLanding.tsx`: `TYPES` `:95-98`, `landingKindsFor` `:106-111`, `EMPTY_LISTS`
  `:113-119`, `initialTabFromUrl` default `:219`, fallback `setActiveTab('stock_inquiry')` `:268`,
  loader `:328-410` (`wantsPriceTags` `:345`, `legs` `:352-355`, `setSubmissions` `:373-379`),
  totals `:424-434`, picker `:515-558`, list `:586-598`, New button `:655-676`, per-tab empty
  card `:678-703`. No zero-kind empty state exists. Kind constants `lib/portal-form-kinds.ts`.
- Contact page grid `contacts/[id]/page.tsx:97,176-178` (Market segment, Attachment types,
  Portal forms cells in that order). Section `ContactPortalFormsSection.tsx`, hook
  `useContactPortalForms.ts`, service `contactPortalFormsService.ts` (rows
  `{form_type, inherited, override, effective}`).
- Data: 99 contacts, 44 hold a portal token. Of those 44: 28 in both segments, 2 in one,
  14 in none. Access types: 21 of the 44 have none. (Why D3 is a base default: any
  group-derived rule would blank a third of the portal's contacts.) No access type grants
  `price_tag_request` (stripped by `ptag_0003`). One override row exists (the owner's own
  contact, price tag Always show).
- Alembic single head `ptag_0011_line_promo`.

## Decisions (owner rulings 16 Sep in bold)

- **D1 Group source is market segment.** `portal_form_types` JSONB moves to `market_segments`;
  the access type column, schema fields, service handling, admin column + modal field and its
  test are removed. One source of truth. Owner accepted the measured weakness (segments barely
  discriminate today) as their call.
- **D2 All five kinds are gated**, on the landing and on every public route. Hidden means 403
  `FORM_TYPE_NOT_VISIBLE` on list and detail too, mirroring price tag. No read-only history.
- **D3 Base default, not fail-closed (owner, lavish 16 Sep).** Every contact sees the four
  legacy kinds unless a per-contact override hides one. `price_tag_request` (and any future
  kind) is opt-in: a segment grant or an override. Resolver:
  `visible = set(SUPPORTED_TYPES) | union(segment.portal_form_types) ; apply overrides`.
  No "no segment" special case, no seed, nobody loses a form at deploy. The base list is the
  existing `SUPPORTED_TYPES` constant; it becomes a System Settings field only when the owner
  asks to change the default itself (named trigger, Out of scope).
- **D4 Migration is expand only (r4, security review).** Add `market_segments.portal_form_types`
  (default `[]`). Do NOT drop `contact_access_types.portal_form_types` in this release: the
  blue/green deploy runs `alembic upgrade head` in the new container while the old image still
  serves traffic and still selects that column (old resolver + every ORM load of
  `ContactAccessType`), so dropping it 500s the portal and the Respond.io ingest path for the
  whole swap window. The model stops mapping the column now; the drop lands as its own
  migration in a later release (issue filed). No seed rows, no override backfill. Segment
  grants are additive, so the segment admin field offers only the kinds beyond the base
  (today: Price Tag Request) under the label "Additional portal forms".
- D5 One gate helper. `_require_price_tag_request_visible` becomes
  `_require_form_visible(db, contact_id, kind)` and is called from the three `_check_*_kind`
  helpers (which gain `db` and `token` parameters) and from the two row-derived attachment
  paths. `portal_price_tag.py._assert_visible` stays as is (already the same rule). No new
  dependency, no registry.
- D6 FE constants: `GATED_LANDING_KINDS` / `isGatedLandingKind` / `PortalGatedKind` are deleted;
  `LANDING_KINDS` is the one list and every entry is gated. `SUBMISSION_KINDS` stays for the
  shared `[type]` route shape guards. `GATED_FORM_TYPES` on the BE admin route becomes
  `GRANTABLE_PORTAL_FORM_TYPES`.
- D7 No new fetch for a grant guard. A detail/edit page renders the server 403 inline (AC-L4).
  A `/new` page makes no submission request on load, so it reads `visible_form_types` from
  one `/me` read (`SubmissionForm` reuses the fetch it already made; `PriceTagRequestForm` adds
  the one `/me` call it never had) and renders the same inline message when the kind is absent
  (r3, coder finding 16 Sep; wording r4). The server remains the enforcement; the page check only
  avoids an empty form.
- D8 Tests: a shared helper `tests/_portal_grant.py` with `grant_portal_forms(db, contact_id,
  kinds)` writing override rows, and `seed_segment(db, kinds)` + `link_contact_segment` for
  inheritance tests. `_ptag_r9_seed.seed_portal_contact` switches from an access type to a
  segment grant. Legacy portal suites get `grant_portal_forms(..., SUPPORTED_TYPES)` in their
  contact fixture.

## Design brief (DESIGN-LANGUAGE frequency gate)

- Market Segments admin and Contact Access Types admin: admin surfaces, hit rarely. Copy the
  existing chip column and `SearchableMultiSelect` field verbatim from the access types admin.
- Contact page Portal forms block: admin, occasional. Five rows in the existing bordered-row
  layout; no new component.
- Portal landing empty state: dealer, first open only when misconfigured. One `Card`, centred,
  title + WhatsApp `Button`. Must NOT animate: the empty state, the chip lists, the row selects.
  No motion in this lane.

## Slices (one lane, one PR, commit per slice)

- **S0** docs: this plan + UAC (main session).
- **S1 Phase 1 FE against mocks** (coder, worktree): AC-M1..M3, AC-C1..C3, AC-L1..L5.
  r2: the segment field offers only kinds beyond the base four (D4); landing unchanged.
  Contract doc at the top of `marketSegmentService.ts` (new `portal_form_types: string[]` on
  read/create/update) and `contactPortalFormsService.ts` (five rows). Mocks: the market segment
  service returns `portal_form_types` from a local fixture until S2; the contact portal-forms
  service returns five rows. Landing uses the real `visible_form_types` already on `/me`.
  Vitest: update `ContactPortalFormsSection.test.tsx` (five rows, label), delete
  `ContactAccessTypesAdmin.portalForms.test.tsx`, add `MarketSegmentsAdmin.portalForms.test.tsx`
  (copy of the deleted one, re-pointed), add landing tests for L1..L3.
- **S2 Phase 2 BE, tester first** (tester writes red, same coder makes green): AC-D1..D4,
  AC-R1..R5, AC-G1..G5. Order: migration -> model -> schema -> service -> routes -> fixtures
  (D8) -> swap S1 mocks for real calls.
- **S3 Phase 3**: reviewer + security-reviewer (public portal routes, RBAC of the admin route)
  + tester browser run (AC-E1..E4) in parallel; guide-writer; DoD gate.

## Migration (`alembic/versions/ptag_0012_segment_portal_forms.py`, id `ptag_0012_seg_forms`, down `ptag_0011_line_promo`)

1. `market_segments.portal_form_types` JSONB NOT NULL server_default `'[]'` (idempotent via
   `_columns`).
Downgrade: drop that column. No data statements (D3), no access-type drop (D4 r4).
Follow-up migration next release: `DROP COLUMN contact_access_types.portal_form_types`.

## Test list (captain's, one line per AC the tester writes)

- AC-D1 `test_migration_adds_segment_column_and_keeps_access_type_column` - the test first
  rewinds the create_all schema (drops the segment column) so upgrade has work to do; after
  upgrade the segment column exists with default `[]`, the access type column still exists;
  second run no error.
- AC-D2 `test_migration_writes_no_data_rows` - segment lists stay `[]`, override row count
  unchanged, existing override row unchanged.
- AC-D3 `test_contact_with_no_segment_and_no_override_sees_exactly_the_four_legacy_kinds`.
- AC-D4 `test_migration_downgrade_drops_segment_column_only`.
- AC-R1 `test_resolver_is_base_four_plus_segment_union_and_ignores_access_types`.
- AC-R2 `test_resolver_override_false_hides_a_base_kind_and_true_shows_price_tag`.
- AC-R3 `test_segment_routes_carry_and_validate_portal_form_types` (create, update, omit, list,
  unknown 422).
- AC-R4 `test_access_type_routes_ignore_portal_form_types`.
- AC-R5 `test_contact_portal_forms_lists_five_rows_inherited_from_segments`.
- AC-G1 `test_hidden_kind_is_403_on_every_legacy_route` parametrised over kind x route (13
  routes).
- AC-G2 `test_hidden_kind_attachment_download_and_delete_403`.
- AC-G3 covered by existing suites once fixtures grant visibility (tester lists the files
  touched in the commit message).
- AC-G4 `test_me_visible_form_types_covers_all_five`.
- AC-G5 `test_price_tag_routes_still_403_without_grant`.
- FE (vitest): AC-M1/M2 `MarketSegmentsAdmin.portalForms.test.tsx`; AC-M3 assertion added to
  the existing access types admin test that the column and field are absent; AC-C1/C2/C3 in
  `ContactPortalFormsSection.test.tsx`; AC-L1/L2/L3 in a new `PortalLanding.visibility.test.tsx`.

## Lane setup (coder brief)

- Worktree off `origin/main`; branch `feat/portal-forms-market-segment`.
- Running-stack DB: `createdb -U sorento_crm -O sorento_crm sorento_pfms` then
  `pg_dump -U sorento_crm sorento_ai_automation_0915_1900 | psql -U sorento_crm sorento_pfms`
  (never `-T`: the dev DB has live connections and the shared dev DB must NOT receive this
  migration, it drops a column other stacks still read). Lane `.env` points at `sorento_pfms`,
  redis db index of its own (flush it first).
- Test DB: `sorento_pfms_ci`, built with the create_all recipe (`tests/_pg_fixture.py`), owned
  by `sorento_crm`. Exclusive to this lane.
- Stack: BE :8080, FE :3080 (`npm run dev`), `.env.local` per the CLAUDE.md remote-testing block.
  Worker not needed. `ENABLE_SCHEDULER=false`.

## Out of scope (named triggers)

- A per-segment default for the Respond.io or chatbot surfaces: only when a second consumer of
  `portal_form_types` appears.
- `DROP COLUMN contact_access_types.portal_form_types`: own migration in the release after
  this one ships (expand-contract, D4 r4).
- Editable base default (today the constant `SUPPORTED_TYPES`): a System Settings field only
  when the owner asks to change what every contact gets by default.
- Removing a base kind for a whole segment (tri-state segment grants): only when the owner
  asks to hide a legacy form from a whole segment rather than per contact.
- Read-only history for a hidden kind: owner ruled no; revisit only on a dealer complaint.
- Notification when a contact's visible set changes: none today; trigger is an owner ask.
