/**
 * Copy/cut clipboard, module-level rather than component `useState` (S3).
 *
 * The request designer remounts `TagCanvasEditor` with `key={selectedTag.id}`
 * on every line switch, so a `useState` clipboard emptied on the very next
 * click: copy on line A, click line B, paste did nothing. A module-level
 * store survives that remount (and a route change within the SPA) because it
 * lives outside React's tree entirely; `useSyncExternalStore` is how a
 * component reads it without going stale.
 *
 * `sourceDocId` is the template or placed-tag id the copy came FROM, so a
 * paste can tell a same-doc paste (offset by `CLONE_OFFSET_MM`, as before)
 * from a cross-doc paste (land at the original x/y, so a layout copied from
 * one line lands in the same place on another).
 *
 * Per user by construction: this is JavaScript memory in the user's own
 * browser tab. Nothing here is written to the server, `localStorage` or any
 * shared place, so user A's copy can never reach user B's paste, and two tabs
 * of the same user do not share it either. A page reload clears it - that is
 * the tradeoff of living only in memory, and it is acceptable (documented in
 * the UAC) rather than solved with a persistence layer nothing else needs.
 */

import type { TagLayer } from './tag-template-types';

export interface TagClipboardValue {
  layers: TagLayer[];
  roots: string[];
  sourceDocId: string | null;
}

let value: TagClipboardValue | null = null;
const listeners = new Set<() => void>();

export function getTagClipboard(): TagClipboardValue | null {
  return value;
}

export function setTagClipboard(next: TagClipboardValue | null): void {
  value = next;
  for (const listener of listeners) listener();
}

export function subscribeTagClipboard(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
