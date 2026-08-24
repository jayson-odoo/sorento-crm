# Per-Contact Portal Link Action - Design

Date: 2026-05-01
Status: Approved (brainstorm)

## Goal

Surface the existing user-submission portal as an admin-triggered action on each contact, so staff can hand a contact a working portal link without going through n8n/MCP.

The portal itself (commit `4e9082f28`) and its 7-day token model are unchanged. This design adds an internal API + UI affordances for minting/reusing tokens and presenting the link.

## Non-goals

- Manual revocation UI (deferred)
- Audit log surface for who fetched links (deferred - DB row already records mint time)
- New form types (sponsorship/etc. already supported by existing portal)

## User flow

1. Admin opens contact (detail page, SLA tracking detail, or contact list row).
2. Clicks "Portal link" action.
3. Modal opens, fires API call.
4. Modal displays: link in copyable input, expiry, "Open in new tab" link, QR code, optional "Existing valid link" badge if a live token was reused, and a "Send via Respond.io" button.
5. Admin copies / opens / scans QR / sends via Respond.io. Modal closes.

Token granularity: one generic link → `/portal?token=...`. Contact picks form type inside portal (existing dashboard already does this).

Reuse policy: if a non-revoked, non-expired `portal_tokens` row exists for `(contact_id, space_id)`, return it. Else mint a new one. Old tokens are NOT revoked.

## Backend

### New permission

Slug: `user_management.contacts.portal_link`
Label: `Get contact portal link`

Seeded (Alembic migration) and granted to roles `superadmin`, `admin` by default. No grant to other roles - admins choose to extend.

### New endpoint

`POST /api/v1/user-management/contacts/{contact_id}/portal-link`

- Auth: JWT (standard `get_current_user`).
- RBAC: gate via `require_permissions("user_management.contacts.portal_link")`.
- Path param: `contact_id` (RespondContact PK, string).
- Body: empty. Optional `{ "base_url": "..." }` to override `FRONTEND_BASE_URL` (mirrors external endpoint behavior).
- Response 200:
  ```json
  {
    "token": "…",
    "expires_at": "2026-05-08T12:00:00Z",
    "portal_url": "https://crm.example.com/portal?token=…",
    "reused": true
  }
  ```
- Errors:
  - 404 if contact not found
  - 422 if contact has no `workspace_id` (cannot resolve `space_id`)
  - Standard 401/403 on auth/permission failure

Server resolves `space_id` from `RespondContact.workspace_id → RespondWorkspace.space_id`. The client never passes `space_id` on this internal endpoint.

### New endpoint - send link via Respond.io

`POST /api/v1/user-management/contacts/{contact_id}/portal-link/send`

- Auth + RBAC: same as the link endpoint (`user_management.contacts.portal_link`).
- Body: empty (v1). Future-proofing: optional `{ "message": "...override text..." }` - out of scope for now.
- Behavior:
  1. Resolve contact + space_id (same as link endpoint).
  2. Reject 422 if `RespondContact.respond_io_id` is null/empty.
  3. Call `PortalService.get_or_mint_token` → get `(token, reused)` and `portal_url`.
  4. Build message text from a hardcoded template:
     ```
     Hi {contact_name_or_blank}, here is your secure portal link:
     {portal_url}

     The link expires on {expires_at_human}. Reply if you need help.
     ```
     `{contact_name_or_blank}` is contact's display name if present, else empty (preceding "Hi " trims trailing comma).
  5. Send via `RespondClient().send_message(respond_io_id, text)`. On `httpx.HTTPStatusError` → 502 with the upstream status message; do NOT roll back the token (link is still valid for copy/QR fallback).
- Response 200:
  ```json
  {
    "sent": true,
    "portal_url": "...",
    "expires_at": "...",
    "reused": true
  }
  ```
- Errors:
  - 404 contact not found
  - 422 contact missing workspace_id OR respond_io_id
  - 502 Respond.io API failure (message text in detail)
  - 401/403 standard

This endpoint internally reuses `get_or_mint_token`; calling it does not require having called the plain link endpoint first. Calling both for the same contact returns the same token (reuse path).

### Service layer

`PortalService.get_or_mint_token(contact_id, space_id) -> tuple[PortalToken, bool]`

`PortalService.send_link_via_respond_io(contact_id, space_id, base_url=None) -> dict`
- Calls `get_or_mint_token`, builds the templated message, calls `RespondClient().send_message`. Returns `{ token, expires_at, portal_url, reused, sent: True }`.
- Lets `httpx.HTTPStatusError` propagate; route handler maps to 502.

Logic:
1. Validate inputs (existing validation).
2. Query `PortalToken` where `contact_id = ? AND space_id = ? AND revoked_at IS NULL AND expires_at > now()` ordered by `expires_at DESC` limit 1.
3. If row found → return `(row, True)`.
4. Else call existing `mint_token(contact_id, space_id)` → return `(row, False)`.

Existing `mint_token` is unchanged; external endpoint `POST /external/portal-tokens/` (used by n8n) is unchanged. The new endpoint uses `get_or_mint_token` so it can also be the basis for an MCP-side change later if desired, but no MCP changes in this spec.

### Files touched (backend)

- `sorento_crm_backend/alembic/versions/<n>_contact_portal_link_permission.py` - new permission row + role grants
- `sorento_crm_backend/app/api/v1/user_management/contacts.py` - two new route handlers (link + send)
- `sorento_crm_backend/app/services/portal_service.py` - add `get_or_mint_token` and `send_link_via_respond_io`
- `sorento_crm_backend/tests/` - unit tests for service reuse logic + endpoint RBAC + 422 missing workspace + 422 missing respond_io_id + 502 mocked Respond.io failure

## Frontend

### Dependency

Add `qrcode.react` (small, MIT, peer-deps clean against React 19) to `sorento_crm_frontend/package.json`.

### Service + hooks

- `sorento_crm_frontend/services/contactPortalLinkService.ts`
  - `getContactPortalLink(contactId): Promise<PortalLinkResponse>` → `POST /user-management/contacts/{id}/portal-link`
  - `sendContactPortalLink(contactId): Promise<PortalLinkSendResponse>` → `POST /user-management/contacts/{id}/portal-link/send`
  - Both use shared `apiFetch` + `extractApiError`.
- `sorento_crm_frontend/hooks/useContactPortalLinkMutation.ts` - two react-query `useMutation` hooks: `useContactPortalLinkMutation` and `useSendContactPortalLinkMutation`. Both toast on error.

Types:
```ts
export interface PortalLinkResponse {
  token: string;
  expires_at: string;       // ISO
  portal_url: string;
  reused: boolean;
}

export interface PortalLinkSendResponse {
  sent: true;
  portal_url: string;
  expires_at: string;
  reused: boolean;
}
```

### Shared UI components

`sorento_crm_frontend/components/contacts/PortalLinkButton.tsx`

Props:
```ts
{
  contactId: string;
  contactLabel?: string;             // for dialog header
  canSendViaRespondIo?: boolean;     // gates "Send via Respond.io" button
  variant?: 'button' | 'menu-item' | 'icon';
  disabled?: boolean;
}
```

Each call site passes `canSendViaRespondIo` based on whether the contact's `respond_io_id` is populated. When unknown (e.g. SLA tracking page may not have it), pass `true` and let the backend return 422 - UI shows the toast.

Renders the appropriate trigger element (Button / DropdownMenuItem / icon Button). Opening the trigger launches the dialog.

Permission gate: component reads current user permissions (existing hook/store) and returns `null` when `user_management.contacts.portal_link` is missing.

`sorento_crm_frontend/components/contacts/PortalLinkDialog.tsx`

State:
- On open: fire mutation. While pending → spinner.
- On error → inline error text + retry button. Dialog stays open.
- On success → render content.

Content:
- Header: "Portal link - {contactLabel ?? contactId}"
- Sub-line: "Expires {formatted expires_at}" + small badge "Reused existing link" when `reused === true`
- Read-only `<Input>` containing `portal_url` + Copy button (uses `navigator.clipboard.writeText`, toast "Copied")
- "Open in new tab" anchor with `target="_blank" rel="noopener noreferrer"`
- QR canvas: `<QRCodeSVG value={portal_url} size={192} />`
- "Send via Respond.io" button: fires send mutation. While pending → spinner inside button, button disabled. On success → toast "Sent to {contactLabel}". On failure → toast with extracted error message (button re-enabled). Button is disabled (with tooltip "Contact has no Respond.io ID") if `contact.respond_io_id` not present - caller passes `canSendViaRespondIo: boolean` prop.
- Footer: Close button

### Wiring

Three call sites, all use `PortalLinkButton`:

1. **Contact detail page** - `app/(protected)/user-management/contacts/[id]/page.tsx`
   - Add to `ToolbarActions`: `<PortalLinkButton contactId={id} contactLabel={contact.name ?? contact.phone} variant="button" />`
   - Place between the existing Edit and Delete actions.

2. **SLA tracking detail page** - `app/(protected)/sla-management/conversation-sla-tracking/[id]/page.tsx`
   - Existing gear-menu (DropdownMenu in screenshot). Add `<PortalLinkButton contactId={tracking.contact_id} contactLabel={tracking.contact_label} variant="menu-item" />` as a new menu item near "Open conversation".
   - Show only when `tracking.contact_id` is resolved.

3. **Contact list row action** - `app/(protected)/user-management/contacts/page.tsx`
   - Add a `DropdownMenuItem` to the existing per-row action menu calling the same component (`variant="menu-item"`).

### Files touched (frontend)

- `package.json` - add `qrcode.react`
- `services/contactPortalLinkService.ts` (new)
- `hooks/useContactPortalLinkMutation.ts` (new)
- `components/contacts/PortalLinkButton.tsx` (new)
- `components/contacts/PortalLinkDialog.tsx` (new)
- `app/(protected)/user-management/contacts/[id]/page.tsx` (add toolbar action)
- `app/(protected)/user-management/contacts/page.tsx` (add row action)
- `app/(protected)/sla-management/conversation-sla-tracking/[id]/page.tsx` (add gear menu item)

## RBAC

- Backend route gated by new perm `user_management.contacts.portal_link`.
- FE button hidden when user lacks the perm (existing permission hook).
- Migration seeds the permission row and grants it to `superadmin` + `admin` only. Other roles get nothing by default; admins can add via Roles & Permissions UI.

## Error & edge cases

| Case | Behavior |
|------|----------|
| Contact has no workspace_id | 422 "Contact has no workspace; cannot mint portal link." |
| Contact has no respond_io_id (send endpoint) | 422 "Contact has no Respond.io identifier; cannot send link." |
| Respond.io API failure (send endpoint) | 502 with upstream message; token already minted is still valid for copy/QR |
| Contact id unknown | 404 |
| Latest token expires within seconds of request | Reuse if `expires_at > now()`. Acceptable; client gets near-expired link. (Optional refinement: reuse only if `expires_at > now() + 5 min`. Skip for v1.) |
| User lacks permission | 403 from backend; FE never shows button |
| FRONTEND_BASE_URL unset | Endpoint returns relative URL; FE prepends `window.location.origin` before display |
| Clipboard API blocked (insecure context) | Fallback: select input text, toast "Press Ctrl/Cmd+C to copy" |

## Testing

Backend:
- `tests/test_portal_service.py` - `get_or_mint_token` reuses live token; mints new when only expired tokens exist; mints new when all tokens revoked.
- `tests/test_user_management_contacts.py` - new endpoint: 200 with reused=true on second call; 200 reused=false when prior token expired; 404 unknown contact; 422 contact w/o workspace; 403 without perm.

Frontend:
- Vitest: `PortalLinkDialog` renders link + QR on success; renders "Reused existing link" badge when `reused=true`; copy button calls clipboard API; "Send via Respond.io" fires send mutation and shows toast on success.
- Manual: click action on contact detail, list row, SLA tracking detail. Confirm three places work and dialog identical. Send-via-Respond.io delivers a real chat message in staging.

## Rollout

Single PR, feature-flag-free.

Migration is additive (one permission row + grants). No data migration. Safe to roll back by reversing the migration; FE component renders nothing without the perm.
