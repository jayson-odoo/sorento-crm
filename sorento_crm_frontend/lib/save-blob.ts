/**
 * Hand the user bytes the browser fetched, as a saved file.
 *
 * Lifted out of `project-sales/_shared/services/fileDownload.ts` once a second domain needed
 * it (PLAN-excel-preview-26sep S1: the low stock report saves its file on its own once the
 * worker has built it). A blob anchor, not `window.open`: a save that fires seconds after the
 * click is not a user gesture any more, and a popup blocker would stop a new window.
 */
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
