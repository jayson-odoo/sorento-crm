/** Staged (not-yet-uploaded) files the preview modal can render from a blob: url. The
 *  owning component creates the url and revokes it, so it cannot leak. */
export function canPreviewLocally(file: File): boolean {
  return (
    file.type.startsWith('image/') ||
    file.type.startsWith('video/') ||
    file.type === 'application/pdf'
  );
}
