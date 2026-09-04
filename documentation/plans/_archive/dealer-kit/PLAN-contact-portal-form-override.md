# PLAN - Per-contact portal form visibility override

**Status:** Built 1 Sep 2026 (single lane, no separate Phase 1/Phase 2 split since the storage
and resolver already existed and only the admin surface was new; tests written alongside the
route per TDD). UAC: `contact-portal-form-override-acceptance-criteria.md`.
**Branch:** `feat/contact-portal-form-overrides` (worktree lane
`.claude/worktrees/contact-portal-forms`). **Domain:** dealer-kit (shares the portal form
gating machinery `PLAN-price-tag-request.md` introduced).

## Why

`contact_portal_form_overrides` and `resolve_visible_form_types` (`PLAN-price-tag-request.md`
D61) already exist: the union of `portal_form_types` across a contact's access types, then a
per-contact row that adds or removes one form type. Nothing writes that table. An admin who
needs to show `price_tag_request` to one dealer without moving that dealer to a different
access type, or hide it from one dealer within an access type that otherwise carries it, has
no way to do either today.

## Decision log

- **Lifts the "No per-contact grant UI" deferral.** `PLAN-price-tag-request.md`, section "No
  per-contact grant UI" (D61 follow-ups), read: "nobody has asked to grant one person a form
  their access type does not carry. The access type is the unit the request was made in." The
  trigger named there has arrived: the captain asked for per-contact editing on 2026-09-01.
  This plan is that build.
- **Only gated kinds are in scope.** `price_tag_request` is the only entry in
  `GATED_LANDING_KINDS` (`sorento_crm_frontend/lib/portal-form-kinds.ts`) today. The four
  legacy submission kinds (complaint, stock_inquiry, purchase_request, sponsorship_form) are
  always on the portal landing regardless of access type or override, so this UI never lists
  them. The next gated form joins `GATED_FORM_TYPES` on the backend route and
  `GATED_LANDING_KINDS` on the frontend - one list, already the source of truth for the portal
  landing and for the access-type admin screen (D61b).
- **No new permission.** `user_management.contacts.view` for read, `.edit` for write - the
  same pair every other per-contact admin surface on this page uses
  (`contact_media_access.py`), not a new admin-only role.
- **Three-state control, not a boolean.** Inherit / Always show / Always hide, because the
  fourth possible state - "no opinion, not even implicit" - IS "Inherit"; there is no fifth
  state to add a control for. A checkbox would collapse "override to false" and "no override"
  into the same unchecked appearance, which is exactly the ambiguity `has_row` exists to avoid
  on the sibling media-access surface.

## Design

### Backend

New route file `app/api/v1/user_management/contact_portal_forms.py`, mirroring
`contact_media_access.py`'s shape (own router, mounted under the same `/contacts` prefix in
`app/api/v1/user_management/__init__.py`, `_require_contact` 404 pattern).

- `GET /{contact_id}/portal-forms` (`user_management.contacts.view`): one row per
  `GATED_FORM_TYPES` entry - `form_type`, `inherited` (in the union of the contact's assigned
  access types' `portal_form_types`), `override` (the stored row's `is_enabled`, or null if no
  row), `effective` (override if not null, else inherited).
- `PUT /{contact_id}/portal-forms` (`user_management.contacts.edit`): body
  `{"overrides": [{"form_type", "is_enabled"}]}`. `is_enabled=null` deletes the row (back to
  inherit); `true`/`false` upserts it, updating the existing row rather than inserting a
  duplicate (unique constraint on `(contact_id, form_type)`). An unknown `form_type` is 422
  via `handle_unprocessable`; an unknown contact is 404. Returns the same shape as GET.

No new storage. The union-of-access-types query the route needs for `inherited` is the same
query step 1+2 of `resolve_visible_form_types` already runs, so it was extracted to
`inherited_form_types(db, contact_id)` in `portal_form_visibility_service.py` and both callers
use it - no second copy of that join. `resolve_visible_form_types` itself is otherwise
untouched; it already applies whatever the route writes.

### Frontend

`ContactPortalFormsSection.tsx` on the contact detail page, immediately after
`ContactAttachmentTypesSection`, in the same grid-cell placement those sibling sections use.
Layered the same way `ContactMediaAccessSection` is (`contactPortalFormsService.ts` ->
`useContactPortalForms.ts` -> component), because that is the one sibling on this page that
already follows the enforced layering rather than calling `apiFetch` directly from the
component.

One row per gated kind: label (`portalFormKindLabel`), an effective `Badge` (Visible/Hidden),
and a `SearchableSelect` (single-select, not clearable - the three options already cover every
state, so there is nothing to clear to) with `inherit` / `show` / `hide`. Changing it PUTs
immediately; no confirmation dialog, because nothing here is destructive or hides data the
operator cannot see again by picking Inherit or the opposite state.

## Tests

pytest (`tests/test_contact_portal_forms.py`): inheritance with no override, override winning
over inheritance in both directions, null override deleting the row, a second PUT on the same
form_type updating in place rather than duplicating, a single PUT naming the same form_type
twice collapsing to its last entry rather than double-inserting or racing a delete against an
add, an unknown form_type refused 422, an unknown contact 404 on both routes,
`resolve_visible_form_types` picking up a route-written override (the AC-6 integration check),
and GET/PUT asking for the view/edit permission slugs respectively rather than a stub that
answers True regardless of what was asked. vitest (`ContactPortalFormsSection.test.tsx`):
renders the price-tag row from a mocked GET, selecting "Always show" issues the true PUT,
selecting "Always hide" issues the false PUT, selecting "Inherit" issues the null PUT, no UUID
in the rendered output.
