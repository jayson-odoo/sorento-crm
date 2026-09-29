import type { ReactNode } from 'react';

export interface PdfViewerProps {
  /**
   * Where the file lives. Feeds Open in a new tab and, when `loadData` is absent, is also
   * where the bytes are read from, so it must then be same-origin (or send CORS headers):
   * a presigned storage URL does not, and needs `loadData` instead.
   */
  url: string | null;
  /**
   * Reads the bytes through a route this page is allowed to call (the authenticated
   * `/download` route, the portal token route). Wins over `url` for loading.
   */
  loadData?: () => Promise<ArrayBuffer>;
  /**
   * Changes only when the document changes. A re-signed URL for the same file keeps the
   * rendered pages and the reader's place. Defaults to `url` without its query string;
   * pass it when loading from `loadData` alone.
   */
  documentKey?: string | null;
  /** Saved file name for Download. */
  fileName?: string | null;
  /** Accessible name of the viewer region, and the page label prefix. */
  title: string;
  /**
   * The page to show. When it changes the viewer jumps to it (a line's note opening its
   * page); scrolling reports the page in view back through `onPageChange`.
   */
  page?: number;
  onPageChange?: (page: number) => void;
  /** Page count to show in the toolbar before the document has loaded. */
  pageCountHint?: number | null;
  /**
   * Download and Open in the toolbar. Off where the surrounding chrome already carries
   * them (the attachment preview header), so the two never sit side by side.
   */
  fileActions?: boolean;
  /** Shown instead of pages when there is neither a `url` nor `loadData`. */
  unavailable?: ReactNode;
  className?: string;
}
