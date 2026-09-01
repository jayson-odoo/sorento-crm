# UAC - Per-contact portal form visibility override

**Companion to:** `PLAN-contact-portal-form-override.md`
**Status:** Built 1 Sep 2026.
**Legend:** `[BE]` backend/pytest · `[FE]` frontend/vitest

Convention: **Given / When / Then**. An AC passes only when the Then is observed against the
real stack for the side marked.

---

## Journey

**Actor:** an admin with `user_management.contacts.edit`, on a contact's detail page.

1. They open a contact whose access type does not carry `price_tag_request`, and see a
   **Portal forms** section with one row: Price Tag Request, badged Hidden, a control reading
   Inherit from access types.
2. They switch the control to Always show. The badge flips to Visible immediately - no
   confirmation, no save button elsewhere on the page to remember.
3. On a different contact, whose access type DOES carry `price_tag_request`, they switch the
   control to Always hide. The badge flips to Hidden even though the access type grants it.
4. Switching either control back to Inherit removes the override; the badge reflects whatever
   the access type union says on its own.

---

## Acceptance criteria

- **AC-1 [BE]** Given a contact, when `GET /api/v1/user-management/contacts/{id}/portal-forms`
  is called, then the response is `{"forms": [...]}` with exactly one row per
  `GATED_FORM_TYPES` entry (today: `price_tag_request` only), each carrying `form_type`,
  `inherited` (bool), `override` (bool or null), `effective` (bool). The four legacy
  submission kinds never appear in this list.

- **AC-2 [BE]** Given a contact, when `PUT .../portal-forms` is called with
  `{"overrides": [{"form_type": "price_tag_request", "is_enabled": true}]}`, then a
  `contact_portal_form_overrides` row is created (or the existing one updated) with
  `is_enabled=true`, and the response is the same shape as GET, recomputed. The same PUT with
  `is_enabled: false` sets it false. `is_enabled: null` deletes the row.

- **AC-3 [BE]** Given a PUT body naming a `form_type` outside `GATED_FORM_TYPES`, when the
  route runs, then it responds 422 and writes nothing. Given an unknown `contact_id`, when
  either GET or PUT is called, then it responds 404. Both routes require
  `user_management.contacts.edit` for PUT; GET accepts `user_management.contacts.view`.

- **AC-4 [BE]** Given a contact with an assigned access type carrying `price_tag_request` AND
  an override row with `is_enabled=false`, when GET is called, then `effective` is `false`
  (override wins). Given the same contact with the override row deleted, then `effective` is
  `true` (falls back to inherited). Given a contact with no assigned access type and an
  override row `is_enabled=true`, then `effective` is `true` (override adds a type inheritance
  never granted).

- **AC-5 [FE]** Given the contact detail page, when it renders, then a **Portal forms**
  section appears with one row per gated kind: a human label, a Badge showing the current
  `effective` state, and a `SearchableSelect` with exactly three options (Inherit from access
  types / Always show / Always hide) reflecting `override` (null/true/false). Changing the
  selection issues the PUT immediately and the row's badge updates from the response - no
  separate save action.

- **AC-6 [BE]** Given a PUT that sets `is_enabled=true` for a contact with no other grant of
  `price_tag_request`, when `resolve_visible_form_types(db, contact_id)` is called afterward in
  the same test, then the returned set contains `price_tag_request` - the override the route
  wrote is the one the resolver reads, with nothing re-derived in between.

- **AC-7 [FE]** No UUID (contact id, override row id) is rendered anywhere in the section's
  text content. The section and its control are usable without clipping or overflow at 375px
  and at 1280px viewport widths.
