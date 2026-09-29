'use client';

import { lazy, Suspense } from 'react';

import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';

import type { PdfViewerProps } from './pdf-viewer/types';

export type { PdfViewerProps } from './pdf-viewer/types';

/**
 * Every in-app PDF renders through this: our own toolbar, our tokens, one continuous scroll
 * of pages, instead of the browser's PDF viewer in an iframe.
 *
 * Lazy twice over: the viewer's code is its own chunk, fetched on first mount, and pdf.js
 * (plus its worker) is a further chunk the viewer only asks for when it has a document to
 * open. A page that never shows a PDF pays for neither.
 */
const PdfViewerImpl = lazy(() => import('./pdf-viewer/PdfViewerImpl'));

export function PdfViewer(props: PdfViewerProps) {
  return (
    <Suspense
      fallback={
        <div
          className={cn('flex min-h-0 flex-col bg-background', props.className)}
          role="status"
          aria-busy="true"
          aria-label="Loading"
        >
          <div className="h-10 border-b border-border" />
          <div className="min-h-0 flex-1 bg-muted/40 p-2">
            <Skeleton className="mx-auto aspect-[1/1.414] w-full max-w-[640px] rounded-sm" />
          </div>
        </div>
      }
    >
      <PdfViewerImpl {...props} />
    </Suspense>
  );
}
