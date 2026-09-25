'use client';

import * as React from 'react';
import { ChevronLeft, ChevronRight, ExternalLink, FileWarning } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { PdfViewer } from '@/components/common/PdfViewer';
import { apiFetch } from '@/lib/api';

/**
 * The page the extraction came from, beside the extraction.
 *
 * A PDF renders in the shared `PdfViewer`, whose one toolbar carries the page bar; `page`
 * drives it, so a line's note still opens its page. The bytes come through the
 * authenticated download route when the version names its attachment, because the signed
 * `document_url` is cross-origin with no CORS headers and a script cannot read it.
 *
 * The source is pinned per document (see `useStableDocumentSource`), because the backend
 * signs a fresh URL every time the version is read: accepting a note would otherwise hand
 * the viewer a new source, and it would throw away a rendered 1.2 MB scan and fetch it
 * again, losing the reader's place on every action.
 */
export function POIntakeDocumentViewer({
  documentUrl,
  documentKey,
  attachmentId,
  pageCount,
  page,
  onPageChange,
  className,
}: {
  documentUrl: string | null;
  /**
   * Something that changes only when the document itself changes, such as the PO version
   * id. Falls back to the URL with its signature stripped.
   */
  documentKey?: string | null;
  /** The scan's attachment, read through the authenticated same-origin download route. */
  attachmentId?: string | null;
  pageCount: number | null;
  page: number;
  onPageChange: (page: number) => void;
  className?: string;
}) {
  const total = pageCount && pageCount > 0 ? pageCount : 1;
  const current = Math.min(Math.max(page, 1), total);
  const source = useStableDocumentSource(documentUrl, documentKey);
  const kind = kindOf(source);
  const loadData = React.useMemo(
    () =>
      attachmentId
        ? async () => {
            const response = await apiFetch(
              `/api/v1/resource-management/attachments/${attachmentId}/download`,
            );
            if (!response.ok) throw new Error('The scan could not be read');
            return response.arrayBuffer();
          }
        : undefined,
    [attachmentId],
  );

  if (source && kind === 'pdf') {
    return (
      <PdfViewer
        url={source}
        loadData={loadData}
        documentKey={documentKey ?? pathOf(source)}
        title="Purchase order"
        page={page}
        onPageChange={onPageChange}
        pageCountHint={pageCount}
        className={`h-[60vh] rounded-lg border border-border ${className ?? ''}`}
      />
    );
  }

  return (
    <div
      className={`flex min-w-0 flex-col rounded-lg border border-border ${className ?? ''}`}
    >
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-3 py-2">
        <div className="flex items-center gap-1">
          <Button
            type="button"
            mode="icon"
            variant="ghost"
            size="sm"
            aria-label="Previous page"
            disabled={current <= 1}
            onClick={() => onPageChange(current - 1)}
          >
            <ChevronLeft className="size-4" />
          </Button>
          <span className="text-xs tabular-nums text-muted-foreground">
            {`Page ${current} of ${total}`}
          </span>
          <Button
            type="button"
            mode="icon"
            variant="ghost"
            size="sm"
            aria-label="Next page"
            disabled={current >= total}
            onClick={() => onPageChange(current + 1)}
          >
            <ChevronRight className="size-4" />
          </Button>
        </div>
        {documentUrl && (
          <Button type="button" variant="ghost" size="sm" asChild>
            <a href={documentUrl} target="_blank" rel="noreferrer">
              <ExternalLink className="size-3.5" aria-hidden />
              Open the file
            </a>
          </Button>
        )}
      </div>

      <div className="min-h-0 flex-1 bg-muted/30 p-2">
        {!source ? (
          <div className="flex h-[45vh] flex-col items-center justify-center gap-2 rounded border border-dashed border-border px-6 text-center lg:h-full">
            <FileWarning className="size-5 text-muted-foreground" aria-hidden />
            <p className="text-sm font-medium">The scan is not available to preview</p>
            <p className="max-w-xs text-xs text-muted-foreground">
              Upload the document again from the POs tab if you need it beside the lines.
            </p>
          </div>
        ) : (
          <img
            src={source}
            alt={`Purchase order page ${current}`}
            className="h-[45vh] w-full rounded bg-white object-contain lg:h-full"
          />
        )}
      </div>
    </div>
  );
}

/**
 * The first URL seen for a document, kept for as long as it is the same document.
 *
 * `document_url` is presigned on the server for every read of the version, so its query
 * string differs after each accept, edit and reject even though the bytes behind it are
 * identical. Handing that new string to the viewer reloads the scan. Identity is the caller's
 * key when it has one, otherwise the URL without its signature.
 */
function useStableDocumentSource(
  documentUrl: string | null,
  documentKey?: string | null,
): string | null {
  const identity = documentKey ?? pathOf(documentUrl);
  const pinned = React.useRef<{ identity: string | null; url: string } | null>(null);

  if (documentUrl && pinned.current?.identity !== identity) {
    pinned.current = { identity, url: documentUrl };
  }

  if (!documentUrl) return null;
  return pinned.current?.url ?? documentUrl;
}

function pathOf(url: string | null): string | null {
  return url ? url.split('?')[0] : null;
}

function kindOf(url: string | null): 'pdf' | 'image' {
  if (!url) return 'pdf';
  const path = url.split('?')[0].toLowerCase();
  return /\.(png|jpe?g|webp|gif)$/.test(path) ? 'image' : 'pdf';
}
