import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';

/**
 * Per-contact chatbot media access (PLAN-chatbot-media-endpoint, slice S1, UAC S1-01..S1-03).
 *
 * ---------------------------------------------------------------------------
 * API CONTRACT - written in Phase 1, built to in Phase 2
 * ---------------------------------------------------------------------------
 *
 * GET /api/v1/user-management/contacts/{contact_id}/media-access
 *   Permission: `user_management.contacts.edit` - the contact-edit permission, granted
 *   to every existing role by migration 357 so nobody who could edit a contact before
 *   loses the ability now. No new admin role (UAC S1-06).
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
 */

export type MediaModality = 'image' | 'voice';

export interface ContactMediaAccessItem {
  modality: MediaModality;
  /** The gate. False (or no row at all) means the bot ignores that media type. */
  is_allowed: boolean;
  /** False when no `contact_media_limit` row exists - never configured, not "turned off". */
  has_row: boolean;
  /** null = inherit the system default. */
  monthly_limit: number | null;
  /** The limit actually in force once inheritance is resolved. */
  effective_monthly_limit: number;
  /** Voice only. null = inherit the system default. */
  max_clip_seconds: number | null;
  /** Voice only; null for image. */
  effective_max_clip_seconds: number | null;
  /** Items counted against this period. Refusals do not count. */
  used: number;
  remaining: number;
  updated_at: string | null;
  updated_by_name: string | null;
}

export interface ContactMediaAccess {
  /** YYYY-MM, computed in Asia/Kuala_Lumpur by the CRM. */
  period_key: string;
  /** Already rendered for display, for example "1 September". */
  resets_on: string;
  items: ContactMediaAccessItem[];
}

export interface ContactMediaAccessInput {
  is_allowed: boolean;
  monthly_limit: number | null;
  /** Voice only; ignored for image. */
  max_clip_seconds: number | null;
}

export const MEDIA_MODALITY_LABELS: Record<MediaModality, string> = {
  image: 'Photos',
  voice: 'Voice notes',
};

export async function getContactMediaAccess(
  contactId: string,
): Promise<ContactMediaAccess> {
  const response = await apiFetch(
    `/api/user-management/contacts/${contactId}/media-access`,
  );
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to load media access'));
  }
  return response.json();
}

export async function updateContactMediaAccess(
  contactId: string,
  modality: MediaModality,
  input: ContactMediaAccessInput,
): Promise<ContactMediaAccessItem> {
  const response = await apiFetch(
    `/api/user-management/contacts/${contactId}/media-access/${modality}`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(input),
    },
  );
  if (!response.ok) {
    throw new Error(await extractApiError(response, 'Failed to save media access'));
  }
  return response.json();
}
