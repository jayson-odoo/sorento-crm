import { vi } from 'vitest';

/**
 * `useUrlTab` writes the tab with `window.history.replaceState` (Next syncs it into
 * `useSearchParams`). A test puts jsdom at the record's URL and reads back the last URL written.
 */
export function watchTabWrites(path: string, search: URLSearchParams | string = ''): () => string | undefined {
  const qs = search.toString();
  window.history.replaceState(null, '', `${path}${qs ? `?${qs}` : ''}`);
  const spy = vi.spyOn(window.history, 'replaceState');
  return () => spy.mock.calls.at(-1)?.[2] as string | undefined;
}
