/**
 * Products ticked in a published catalogue, on their way to the room designer.
 *
 * The catalogue is anonymous - a link a dealer forwards - so there is no
 * Selection to write to while somebody is browsing it. The picks therefore live
 * in this browser until the designer opens, and the designer turns them into
 * real lines the moment it has a Selection to put them on.
 *
 * Deliberately small and dumb: a list of product ids and a timestamp. Anything
 * richer (quantities, prices) would be a second, un-priced copy of the
 * catalogue living in localStorage, and the two would disagree.
 */

const KEY = 'dealer-kit:catalogue-picks';

/** Older than this and the picks are somebody's forgotten tab, not an intent. */
const MAX_AGE_MS = 24 * 60 * 60 * 1000;

/** Enough for a room. A cap stops a stuck loop filling storage. */
export const MAX_PICKS = 40;

interface StoredPicks {
  productIds: string[];
  savedAt: number;
}

function read(): StoredPicks | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as StoredPicks;
    if (!Array.isArray(parsed.productIds)) return null;
    return parsed;
  } catch {
    // Corrupt or foreign data in our key is not worth a crash on page load.
    return null;
  }
}

export function readPicks(now: number = Date.now()): string[] {
  const stored = read();
  if (!stored) return [];
  if (now - stored.savedAt > MAX_AGE_MS) return [];
  return stored.productIds.slice(0, MAX_PICKS);
}

export function writePicks(productIds: string[], now: number = Date.now()): void {
  if (typeof window === 'undefined') return;
  const unique = Array.from(new Set(productIds)).slice(0, MAX_PICKS);
  window.localStorage.setItem(
    KEY,
    JSON.stringify({ productIds: unique, savedAt: now } satisfies StoredPicks),
  );
}

export function clearPicks(): void {
  if (typeof window === 'undefined') return;
  window.localStorage.removeItem(KEY);
}

export function togglePick(productIds: string[], productId: string): string[] {
  return productIds.includes(productId)
    ? productIds.filter((id) => id !== productId)
    : [...productIds, productId].slice(0, MAX_PICKS);
}
