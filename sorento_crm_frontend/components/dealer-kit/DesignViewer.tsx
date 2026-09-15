'use client';

/**
 * The design, wherever it is read (r9 S1/D2).
 *
 * ONE viewer for the salesperson's portal page and marketing's detail page: the
 * same `TagSheetRenderer` the PDF export draws with, fed the same media maps,
 * so a proof, a preview and a print can no longer disagree about what a tag
 * looks like. The card itself is deliberately plain - fit to width, a sheet
 * pager when there is more than one, and Open - because everything that needs
 * room (zoom, pan, download) belongs in the lightbox and not in a section a
 * reader scrolls past.
 */

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { ChevronLeft, ChevronRight, Maximize2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { SectionSkeleton } from '@/components/common/SectionSkeleton';
import ScaledSheet, { sheetPixelSize } from './ScaledSheet';
import DesignLightbox, { type DesignDownload } from './DesignLightbox';
import type { DesignReview } from './DesignPinLayer';
import type { TagSheetDesignPayload } from '@/lib/dealer-kit/design-payload';

interface DesignViewerProps {
  /** Section title. `Design` on both surfaces today. */
  title?: string;
  /** The document number, shown as the lightbox title. Never an id. */
  docNumber: string;
  payload: TagSheetDesignPayload | null;
  loading?: boolean;
  /** Why there is nothing to draw, and what happens next. */
  emptyMessage?: string;
  emptyHint?: string;
  download?: DesignDownload;
  /** Actions that belong to the design itself, right of the title. */
  headerActions?: ReactNode;
  /** Pinned change requests, drawn over the sheet here and in the lightbox. */
  review?: DesignReview;
  /**
   * The change-request rail: the pins placed so far, a general note and Send
   * (D5). Rendered under the sheet in the card AND in the lightbox, so a
   * reader who zoomed in to place a pin can send from where they are.
   */
  footer?: ReactNode;
}

export default function DesignViewer({
  title = 'Design',
  docNumber,
  payload,
  loading = false,
  emptyMessage = 'No design yet',
  emptyHint,
  download,
  headerActions,
  review,
  footer,
}: DesignViewerProps) {
  const [sheetIndex, setSheetIndex] = useState(0);
  const [lightboxOpen, setLightboxOpen] = useState(false);
  const [containerWidth, setContainerWidth] = useState(0);
  const containerRef = useRef<HTMLDivElement | null>(null);

  const sheetCount = payload?.doc?.sheets.length ?? 0;

  useEffect(() => {
    // A shorter document must not leave the pager pointing past its end.
    setSheetIndex((index) => (index < sheetCount ? index : 0));
  }, [sheetCount]);

  useEffect(() => {
    const node = containerRef.current;
    if (!node) return;
    const observer = new ResizeObserver((entries) => {
      const width = entries[0]?.contentRect.width;
      if (width) setContainerWidth(width);
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, [payload]);

  const natural = useMemo(
    () => sheetPixelSize(payload?.doc ?? null),
    [payload?.doc],
  );

  // Fit to WIDTH in the card: a reader scrolling a page wants to see the whole
  // width of the sheet at a glance, and the lightbox is where the whole page
  // gets its own screen.
  const fitScale = useMemo(() => {
    if (!containerWidth || !natural.width) return 1;
    return Math.max(0.05, containerWidth / natural.width);
  }, [containerWidth, natural.width]);

  // Before the ResizeObserver's first callback the width is still 0 and the
  // fit falls back to 1 - a visible flash of an oversized sheet for one frame.
  const measuring = containerWidth === 0;

  const openLightbox = useCallback(() => setLightboxOpen(true), []);

  const body = () => {
    if (loading) return <SectionSkeleton rows={6} />;
    if (!payload?.doc || sheetCount === 0) {
      return (
        <div className="py-8 text-center">
          <p className="text-sm text-muted-foreground">{emptyMessage}</p>
          {emptyHint && (
            <p className="mt-1 text-xs text-muted-foreground">{emptyHint}</p>
          )}
        </div>
      );
    }
    return (
      <div ref={containerRef} className="rounded-lg bg-muted/30 p-2">
        {measuring ? (
          <SectionSkeleton rows={6} />
        ) : (
          <ScaledSheet
            payload={payload}
            sheetIndex={sheetIndex}
            scale={fitScale}
            review={review}
          />
        )}
      </div>
    );
  };

  return (
    <>
      <Card>
        <CardHeader className="px-4 py-3">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <CardTitle className="text-base">{title}</CardTitle>
            <div className="flex flex-wrap items-center gap-2">
              {sheetCount > 1 && (
                <div className="flex items-center gap-1">
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-7 w-7 p-0"
                    aria-label="Previous sheet"
                    disabled={sheetIndex === 0}
                    onClick={() => setSheetIndex((index) => index - 1)}
                  >
                    <ChevronLeft className="size-3.5" />
                  </Button>
                  <span className="text-xs text-muted-foreground">
                    Sheet {sheetIndex + 1} / {sheetCount}
                  </span>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-7 w-7 p-0"
                    aria-label="Next sheet"
                    disabled={sheetIndex >= sheetCount - 1}
                    onClick={() => setSheetIndex((index) => index + 1)}
                  >
                    <ChevronRight className="size-3.5" />
                  </Button>
                </div>
              )}
              {headerActions}
              {sheetCount > 0 && (
                <Button variant="outline" size="sm" onClick={openLightbox}>
                  <Maximize2 className="size-4 mr-1" />
                  Open
                </Button>
              )}
            </div>
          </div>
        </CardHeader>
        <CardContent className="px-4 pb-4">
          {body()}
          {footer}
        </CardContent>
      </Card>

      {payload && (
        <DesignLightbox
          open={lightboxOpen}
          onOpenChange={setLightboxOpen}
          title={docNumber}
          payload={payload}
          initialSheetIndex={sheetIndex}
          download={download}
          review={review}
          footer={footer}
        />
      )}
    </>
  );
}
