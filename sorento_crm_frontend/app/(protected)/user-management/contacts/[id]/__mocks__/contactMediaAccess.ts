/**
 * PHASE 1 MOCK - delete in Phase 2 (PLAN-chatbot-media-endpoint, slice S1).
 *
 * Stands in for `GET|PUT /api/v1/user-management/contacts/{id}/media-access`
 * until the backend lands. The contract this mock honours is documented in
 * `../services/contactMediaAccessService.ts`; that file is the source of truth
 * and this one only produces plausible bodies for it.
 *
 * Two things the mock deliberately reproduces, because the surface has to be
 * tuned against them:
 *
 * 1. Both modalities are ALWAYS returned, whether or not a `contact_media_limit`
 *    row exists. Absence of a row means denied, and `has_row: false` is how the
 *    operator is told the contact is on the untouched default rather than on an
 *    explicit "off" someone set.
 * 2. `resets_on` arrives already rendered ("1 September"). The CRM computes the
 *    period in Asia/Kuala_Lumpur; no caller does date arithmetic.
 *
 * Which state a contact lands in is derived from its id, so a given contact is
 * stable across reloads and the operator surface can be exercised against every
 * state by walking the contact list:
 *
 *   bucket 0 - nothing configured at all (the empty state, and the ship default)
 *   bucket 1 - photos on, inherited limit, usage past the 80 percent mark
 *   bucket 2 - photos on with an override, voice on and fully spent
 *
 * Writes persist in module memory for the life of the tab, so turning a modality
 * on and reloading the section shows the change the way the real endpoint will.
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

/** Mirrors the plan's `system_settings` defaults, so inheritance reads truthfully. */
const DEFAULT_IMAGE_LIMIT = 50;
const DEFAULT_VOICE_LIMIT = 100;
const DEFAULT_VOICE_MAX_SECONDS = 120;

const MOCK_LATENCY_MS = 260;

function sleep(ms: number) {
  return new Promise<void>((resolve) => setTimeout(resolve, ms));
}

function bucketFor(contactId: string): 0 | 1 | 2 {
  let sum = 0;
  for (const ch of contactId) sum += ch.charCodeAt(0);
  return (sum % 3) as 0 | 1 | 2;
}

function blankItem(modality: MediaModality): ContactMediaAccessItem {
  const limit = modality === 'image' ? DEFAULT_IMAGE_LIMIT : DEFAULT_VOICE_LIMIT;
  return {
    modality,
    is_allowed: false,
    has_row: false,
    monthly_limit: null,
    effective_monthly_limit: limit,
    max_clip_seconds: null,
    effective_max_clip_seconds: modality === 'voice' ? DEFAULT_VOICE_MAX_SECONDS : null,
    used: 0,
    remaining: limit,
    updated_at: null,
    updated_by_name: null,
  };
}

function seed(contactId: string): ContactMediaAccessItem[] {
  const bucket = bucketFor(contactId);
  const image = blankItem('image');
  const voice = blankItem('voice');

  if (bucket === 1) {
    Object.assign(image, {
      is_allowed: true,
      has_row: true,
      used: 43,
      remaining: DEFAULT_IMAGE_LIMIT - 43,
      updated_at: '2026-08-04T02:11:00',
      updated_by_name: 'Nurul Aziz',
    });
    Object.assign(voice, { has_row: true, updated_at: '2026-08-04T02:11:00', updated_by_name: 'Nurul Aziz' });
  }

  if (bucket === 2) {
    Object.assign(image, {
      is_allowed: true,
      has_row: true,
      monthly_limit: 200,
      effective_monthly_limit: 200,
      used: 118,
      remaining: 82,
      updated_at: '2026-07-29T09:40:00',
      updated_by_name: 'Lim Wei Sheng',
    });
    Object.assign(voice, {
      is_allowed: true,
      has_row: true,
      used: DEFAULT_VOICE_LIMIT,
      remaining: 0,
      updated_at: '2026-07-29T09:40:00',
      updated_by_name: 'Lim Wei Sheng',
    });
  }

  return [image, voice];
}

const store = new Map<string, ContactMediaAccessItem[]>();

function itemsFor(contactId: string): ContactMediaAccessItem[] {
  const existing = store.get(contactId);
  if (existing) return existing;
  const fresh = seed(contactId);
  store.set(contactId, fresh);
  return fresh;
}

/** The current period and its reset label, rendered the way the backend will. */
function currentPeriod(): { period_key: string; resets_on: string } {
  const now = new Date();
  const nextMonth = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth() + 1, 1));
  return {
    period_key: `${now.getUTCFullYear()}-${String(now.getUTCMonth() + 1).padStart(2, '0')}`,
    resets_on: `1 ${nextMonth.toLocaleString('en-GB', { month: 'long', timeZone: 'UTC' })}`,
  };
}

export async function mockGetContactMediaAccess(
  contactId: string,
): Promise<ContactMediaAccess> {
  await sleep(MOCK_LATENCY_MS);
  return { ...currentPeriod(), items: itemsFor(contactId).map((item) => ({ ...item })) };
}

export async function mockUpdateContactMediaAccess(
  contactId: string,
  modality: MediaModality,
  input: ContactMediaAccessInput,
): Promise<ContactMediaAccessItem> {
  await sleep(MOCK_LATENCY_MS);
  const items = itemsFor(contactId);
  const index = items.findIndex((item) => item.modality === modality);
  const current = items[index];
  const defaultLimit = modality === 'image' ? DEFAULT_IMAGE_LIMIT : DEFAULT_VOICE_LIMIT;
  const effectiveLimit = input.monthly_limit ?? defaultLimit;
  const next: ContactMediaAccessItem = {
    ...current,
    is_allowed: input.is_allowed,
    has_row: true,
    monthly_limit: input.monthly_limit,
    effective_monthly_limit: effectiveLimit,
    max_clip_seconds: modality === 'voice' ? input.max_clip_seconds : null,
    effective_max_clip_seconds:
      modality === 'voice' ? input.max_clip_seconds ?? DEFAULT_VOICE_MAX_SECONDS : null,
    remaining: Math.max(0, effectiveLimit - current.used),
    updated_at: new Date().toISOString().slice(0, 19),
    updated_by_name: 'You',
  };
  items[index] = next;
  return { ...next };
}
