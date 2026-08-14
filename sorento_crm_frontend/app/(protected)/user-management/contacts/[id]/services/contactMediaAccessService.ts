/**
 * Per-contact chatbot media access (PLAN-chatbot-media-endpoint, slice S1, UAC S1-01..S1-03).
 *
 * ---------------------------------------------------------------------------
 * EXPECTED API CONTRACT - written in Phase 1, built to in Phase 2
 * ---------------------------------------------------------------------------
 *
 * GET /api/v1/user-management/contacts/{contact_id}/media-access
 *   Permission: the existing contact-edit/view permission. No new admin role (UAC S1-06).
 *   200 ->
 *     {
 *       "period_key": "2026-08",           // YYYY-MM, computed in Asia/Kuala_Lumpur
 *       "resets_on": "1 September",        // ALREADY RENDERED. No caller does date maths.
 *       "items": [
 *         {
 *           "modality": "image",           // "image" | "voice"
 *           "is_allowed": false,           // the gate
 *           "has_row": false,              // false = no contact_media_limit row exists
 *           "monthly_limit": null,         // null = inherit the system default
 *           "effective_monthly_limit": 50, // inheritance already resolved
 *           "max_clip_seconds": null,      // voice only; null = inherit
 *           "effective_max_clip_seconds": null,   // null for image
 *           "used": 0,                     // ledger rows counted against this period
 *           "remaining": 50,
 *           "updated_at": null,            // naive UTC
 *           "updated_by_name": null        // resolved name, never a UUID
 *         },
 *         { "modality": "voice", ... }
 *       ]
 *     }
 *
 *   BOTH modalities are always present, in the order image, voice, whether or not a
 *   `contact_media_limit` row exists. Absence of a row means denied (fail closed), and
 *   `has_row: false` is what lets the surface say "never configured" rather than
 *   "somebody turned this off". The frontend never invents a missing item.
 *
 * PUT /api/v1/user-management/contacts/{contact_id}/media-access/{modality}
 *   body: { "is_allowed": true, "monthly_limit": 200, "max_clip_seconds": null }
 *     monthly_limit    null = clear the override and inherit the system default (UAC S1-07)
 *     max_clip_seconds voice only; ignored for image
 *   200 -> the updated item, in the identical shape as one `items[]` entry above, with
 *          `used` / `remaining` / `effective_*` recomputed.
 *   Upserts: a PUT against a contact with no row creates one.
 *   403 when the caller lacks the contact-edit permission (UAC S1-06).
 *
 * ---------------------------------------------------------------------------
 * PHASE 1: both functions below resolve against `../__mocks__/contactMediaAccess`.
 * Phase 2 swaps each body for the `apiFetch` call sketched in its comment and deletes
 * the mock module. Nothing above the service boundary changes.
 */

import type {
  ContactMediaAccess,
  ContactMediaAccessInput,
  ContactMediaAccessItem,
  MediaModality,
} from '../__mocks__/contactMediaAccess';
import {
  mockGetContactMediaAccess,
  mockUpdateContactMediaAccess,
} from '../__mocks__/contactMediaAccess';

export type {
  ContactMediaAccess,
  ContactMediaAccessInput,
  ContactMediaAccessItem,
  MediaModality,
};

export const MEDIA_MODALITY_LABELS: Record<MediaModality, string> = {
  image: 'Photos',
  voice: 'Voice notes',
};

export async function getContactMediaAccess(
  contactId: string,
): Promise<ContactMediaAccess> {
  // Phase 2:
  //   const response = await apiFetch(`/api/user-management/contacts/${contactId}/media-access`);
  //   if (!response.ok) throw new Error(await extractApiError(response, 'Failed to load media access'));
  //   return response.json();
  return mockGetContactMediaAccess(contactId);
}

export async function updateContactMediaAccess(
  contactId: string,
  modality: MediaModality,
  input: ContactMediaAccessInput,
): Promise<ContactMediaAccessItem> {
  // Phase 2:
  //   const response = await apiFetch(
  //     `/api/user-management/contacts/${contactId}/media-access/${modality}`,
  //     { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input) },
  //   );
  //   if (!response.ok) throw new Error(await extractApiError(response, 'Failed to save media access'));
  //   return response.json();
  return mockUpdateContactMediaAccess(contactId, modality, input);
}
