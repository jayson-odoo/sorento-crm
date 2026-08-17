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

export function saveBlobAs(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  // Revoked a tick later, not on this one: the click starts the save asynchronously, and
  // some browsers have not read the object url by the time the synchronous line after the
  // click runs - the download then fails with nothing on the console to say why.
  setTimeout(() => URL.revokeObjectURL(url), 0);
}
