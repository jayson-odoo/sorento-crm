'use client';

/**
 * Which upload-activity sessions the user has already seen.
 *
 * The badge on the top-nav icon counts in-flight uploads plus every session the
 * backend marks `needs_action`. A failed import is `needs_action` for as long as
 * it stays in the feed's window (seven days), and nothing anywhere could clear
 * it: no dismiss endpoint, no column, no control. So one failed import pinned a
 * red "1" next to the upload icon for a week, with no way to act on it - the
 * import had already been re-run successfully, and the badge kept asking.
 *
 * This is deliberately browser-local rather than a column and an endpoint. What
 * is being remembered is "I have looked at this", which is per-person and
 * per-device and costs nothing if it is lost; the session itself stays in the
 * drawer either way, so nothing is hidden, only un-nagged. A migration and a
 * route would buy cross-device sync for a read receipt.
 *
 * Marking happens on drawer open, and ONLY for sessions that are `needs_action`
 * at that moment. That distinction matters: a session still uploading is not
 * `needs_action`, so it is not marked, and if it later fails the badge comes
 * back. Marking every visible session on open would silence exactly the failure
 * the user opened the drawer to watch for.
 */

const STORAGE_KEY = 'sorento:upload-activity:dismissed';

/** Ceiling so the entry cannot grow without bound. Newest ids are kept. */
const MAX_REMEMBERED = 200;

/** Stable empty snapshot — useSyncExternalStore compares snapshots by identity. */
const EMPTY: readonly string[] = Object.freeze([]);

let cache: readonly string[] | null = null;
const listeners = new Set<() => void>();

function readStorage(): readonly string[] {
  if (typeof window === 'undefined') return EMPTY;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return EMPTY;
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return EMPTY;
    const ids = parsed.filter((v): v is string => typeof v === 'string');
    return ids.length ? Object.freeze(ids) : EMPTY;
  } catch {
    // Private mode, quota, or a corrupt value. A nagging badge beats a crash.
    return EMPTY;
  }
}

function writeStorage(ids: readonly string[]): void {
  if (typeof window === 'undefined') return;
  try {
    if (ids.length) {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(ids));
    } else {
      window.localStorage.removeItem(STORAGE_KEY);
    }
  } catch {
    /* best effort */
  }
}

function commit(next: readonly string[]): void {
  const trimmed =
    next.length > MAX_REMEMBERED ? next.slice(next.length - MAX_REMEMBERED) : next;
  cache = trimmed.length ? Object.freeze([...trimmed]) : EMPTY;
  writeStorage(cache);
  listeners.forEach((l) => l());
}

// ---- external store ------------------------------------------------------

export function subscribeDismissed(onChange: () => void): () => void {
  listeners.add(onChange);
  return () => {
    listeners.delete(onChange);
  };
}

/** Snapshot identity is stable between mutations, as useSyncExternalStore requires. */
export function getDismissedSnapshot(): readonly string[] {
  if (cache === null) cache = readStorage();
  return cache;
}

export function getDismissedServerSnapshot(): readonly string[] {
  return EMPTY;
}

// ---- mutations -----------------------------------------------------------

/** Remember these session ids as seen. No-op when nothing is new. */
export function dismissSessions(ids: readonly string[]): void {
  if (!ids.length) return;
  const current = getDismissedSnapshot();
  const known = new Set(current);
  const fresh = ids.filter((id) => id && !known.has(id));
  if (!fresh.length) return;
  commit([...current, ...fresh]);
}

/**
 * Drop remembered ids that are no longer in the feed.
 *
 * Without this the entry grows for ever and, worse, a session id that ages out
 * of the seven-day window and somehow comes back would still read as seen.
 */
export function pruneDismissed(liveSessionIds: readonly string[]): void {
  const current = getDismissedSnapshot();
  if (!current.length) return;
  const live = new Set(liveSessionIds);
  const kept = current.filter((id) => live.has(id));
  if (kept.length === current.length) return;
  commit(kept);
}

/** Test seam — also what a "reset" control would call. */
export function clearDismissed(): void {
  commit(EMPTY);
  // Drop the memo too, so the next snapshot re-reads storage. Behaviour is the
  // same either way (storage is now empty), but it means a test can clear and
  // then exercise the real read path instead of being served the cache.
  cache = null;
}
