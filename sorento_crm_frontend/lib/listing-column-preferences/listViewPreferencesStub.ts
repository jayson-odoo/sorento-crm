/**
 * PHASE 1 MOCK - DELETE IN PHASE 2.
 *
 * TODO(phase-2): this whole file goes away. `useListingViewPreferences` swaps
 * `readListViewPreferences` / `writeListViewPreferences` for the real service calls
 * (`getUserListColumnConfig` / `upsertUserListColumnConfig`) and its react-query key
 * for `['list-column-config', key]`, so the view hook and the column hook share one
 * fetch of one row. Until the backend learns to merge (PLAN 3.2) the view hook must
 * NOT write through that endpoint: today's whole-blob replace would wipe the user's
 * saved column order.
 *
 * It stands in for `PUT/GET /api/v1/list-query/column-config/{listing_key}` and
 * reproduces the merge semantics the backend will get in Phase 2:
 *   - a key ABSENT from the body is left alone,
 *   - a key PRESENT and null is cleared,
 * so the frontend is tuned against the contract it will actually meet.
 *
 * Storage is localStorage, not module memory, purely so a browser reload behaves
 * like a returning user while there is no backend to remember anything.
 */

import type {
  UserListColumnConfigPayload,
  UserListColumnConfigResponse,
} from './listColumnPreferencesService';

const STORAGE_KEY = 'phase1-listing-view-preferences-stub';

/** Stand-in for the round trip, so the loading gate is a real state to tune. */
const STUB_LATENCY_MS = 300;

type StubStore = Record<string, UserListColumnConfigPayload>;

function readStore(): StubStore {
  if (typeof window === 'undefined') return {};
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as unknown;
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {};
    return parsed as StubStore;
  } catch {
    return {};
  }
}

function writeStore(store: StubStore): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(store));
  } catch {
    // A full or blocked localStorage just means the stub forgets. Phase 1 only.
  }
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export async function readListViewPreferences(
  listingKey: string,
): Promise<UserListColumnConfigResponse> {
  const key = (listingKey || '').trim();
  await delay(STUB_LATENCY_MS);
  const stored = readStore()[key];
  return { listing_key: key, config: stored ?? null };
}

export async function writeListViewPreferences(
  listingKey: string,
  payload: UserListColumnConfigPayload,
): Promise<UserListColumnConfigResponse> {
  const key = (listingKey || '').trim();
  await delay(STUB_LATENCY_MS);

  const store = readStore();
  // The merge the Phase 2 handler will do server-side: overlay the keys the body
  // carried, then drop the ones explicitly set to null (AC-A2 / AC-A3).
  const merged: Record<string, unknown> = { ...(store[key] ?? {}), ...payload };
  for (const [k, v] of Object.entries(merged)) {
    if (v === null) delete merged[k];
  }

  const config = merged as UserListColumnConfigPayload;
  store[key] = config;
  writeStore(store);
  return { listing_key: key, config };
}
