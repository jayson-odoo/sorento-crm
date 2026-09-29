/**
 * Saving a file the browser fetched rather than followed.
 *
 * Every generated document in this module (the AutoCount import file, the corrective import
 * file) lives behind an authenticated backend route, so it is fetched through the api client
 * and handed to the user as bytes. An `<a href download>` cannot do it: the path is the
 * BACKEND's, it would resolve against the frontend origin, and it carries no bearer token.
 */

/** `attachment; filename="PSO-000101.csv"` to `PSO-000101.csv`, or null when absent. */
export function filenameFromContentDisposition(header: string | null): string | null {
  if (!header) return null;
  const quoted = /filename\*?=(?:UTF-8'')?"([^"]+)"/i.exec(header);
  if (quoted?.[1]) return decodeURIComponent(quoted[1]);
  const bare = /filename\*?=(?:UTF-8'')?([^;]+)/i.exec(header);
  return bare?.[1] ? decodeURIComponent(bare[1].trim()) : null;
}

// Lifted to `lib/save-blob.ts` (PLAN-excel-preview-26sep S1, the second domain to need it);
// re-exported here so this module's callers are unchanged.
export { saveBlobAs } from '@/lib/save-blob';
