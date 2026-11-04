import { QueryClient } from '@tanstack/react-query';

/**
 * The cache behind the designer's artwork library, brand fonts and spec vocabulary
 * (`useKitLibrary`). It has no provider to mount, so every editor shares one read: the spec sheet
 * reader mounts a live canvas per visible page, and each used to read all three again.
 *
 * Its own file so the company switch can refresh it without pulling the designer into every page.
 *
 * - `staleTime` stays under the library's signed URL lifetime (3600 s, `asset_service.urls_for`),
 *   so an editor opened after 30 min reads fresh links instead of drawing expired ones.
 * - A company switch calls `invalidateKitLibrary()`: open editors read the new company's library
 *   at once, closed ones on their next open.
 */
export const KIT_LIBRARY_STALE_MS = 30 * 60 * 1000;

export const kitLibraryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: KIT_LIBRARY_STALE_MS,
      gcTime: KIT_LIBRARY_STALE_MS,
      retry: false,
    },
  },
});

/** The active company changed: everything read so far belongs to the old one. */
export function invalidateKitLibrary(): Promise<void> {
  return kitLibraryClient.invalidateQueries();
}

/** Forget what was read (tests): the next open reads the library again. */
export function resetKitLibraryCache(): void {
  kitLibraryClient.clear();
}
