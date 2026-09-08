'use client';

/**
 * Portal design viewer: renders each tag sheet at print-accurate size (D11)
 * for the salesperson to review before approving or requesting changes.
 *
 * Uses TagSheetRenderer in preview mode (DOM/CSS, not Konva) over the SAME
 * doc + resolved line data the CRM designer and the PDF export read, so what
 * is shown here is what gets printed.
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import { ChevronDown, ChevronLeft, ChevronRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import TagSheetRenderer, {
  type ResolvedLineData,
} from '@/app/(public)/c/print/tag-sheet/[downloadId]/components/TagSheetRenderer';
import type { TagSheetDoc } from '@/lib/dealer-kit/tag-template-types';

interface PriceTagProofViewerProps {
  doc: TagSheetDoc | null;
  resolvedData: Record<string, ResolvedLineData>;
}

/** Discrete zoom presets (D11/AC-S4-2), plus "Fit" - the scroll container's
 *  own measured width divided by the sheet's natural (1mm = 1mm) width. */
const ZOOM_LEVELS = [0.25, 0.5, 0.75, 1, 1.5, 2] as const;
type ZoomValue = 'fit' | (typeof ZOOM_LEVELS)[number];

// CSS `mm` resolves to 96px/inch by spec regardless of the screen's actual
// DPI - the same constant the print route relies on for physical accuracy -
// so Fit is computed arithmetically from the measured container width rather
// than needing a hidden render pass to measure the sheet itself.
const PX_PER_MM = 96 / 25.4;

function zoomLabel(value: ZoomValue): string {
  return value === 'fit' ? 'Fit' : `${Math.round(value * 100)}%`;
}

export default function PriceTagProofViewer({
  doc,
  resolvedData,
}: PriceTagProofViewerProps) {
  const [activeSheetIndex, setActiveSheetIndex] = useState(0);
  const [zoom, setZoom] = useState<ZoomValue>('fit');
  const [containerWidth, setContainerWidth] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const node = containerRef.current;
    if (!node) return;
    const observer = new ResizeObserver((entries) => {
      const width = entries[0]?.contentRect.width;
      if (width) setContainerWidth(width);
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  const sheetCount = doc?.sheets.length ?? 0;
  const pageWidthMm = doc?.imposition.page_width_mm ?? 0;

  // A little padding subtracted so the sheet's edge is not flush against the
  // scroll container's own border.
  const fitScale = useMemo(() => {
    if (!containerWidth || !pageWidthMm) return 1;
    const naturalWidthPx = pageWidthMm * PX_PER_MM;
    return Math.max(0.05, (containerWidth - 16) / naturalWidthPx);
  }, [containerWidth, pageWidthMm]);

  const scale = zoom === 'fit' ? fitScale : zoom;
  // Before the ResizeObserver's first callback, containerWidth is still 0
  // and fitScale falls back to 1 (real size) - a visible flash of an
  // oversized sheet for one frame. Wait for a real measurement instead.
  const isMeasuringFit = zoom === 'fit' && containerWidth === 0;

  // Build a single-sheet doc for the active sheet.
  const activeSheetDoc = useMemo(() => {
    if (!doc || !doc.sheets[activeSheetIndex]) return null;
    return {
      ...doc,
      sheets: [doc.sheets[activeSheetIndex]],
    } as TagSheetDoc;
  }, [doc, activeSheetIndex]);

  if (!doc || sheetCount === 0) {
    return (
      <Card>
        <CardHeader className="py-3 px-4">
          <CardTitle className="text-base">Design Preview</CardTitle>
        </CardHeader>
        <CardContent className="px-4 pb-4">
          <p className="text-sm text-muted-foreground text-center py-6">
            No tag sheets designed yet.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="py-3 px-4">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <CardTitle className="text-base">Design Preview</CardTitle>
          <div className="flex items-center gap-2">
            {/* Zoom: Fit plus six discrete presets (AC-S4-2). */}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="outline"
                  size="sm"
                  className="h-7 gap-1 px-2 text-xs"
                  aria-label="Zoom level"
                >
                  {zoomLabel(zoom)}
                  <ChevronDown className="size-3.5" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onSelect={() => setZoom('fit')}>
                  Fit
                </DropdownMenuItem>
                {ZOOM_LEVELS.map((level) => (
                  <DropdownMenuItem key={level} onSelect={() => setZoom(level)}>
                    {zoomLabel(level)}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>

            {/* Sheet navigation */}
            {sheetCount > 1 && (
              <>
                <div className="w-px h-4 bg-border mx-1" />
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 w-7 p-0"
                  disabled={activeSheetIndex === 0}
                  onClick={() => setActiveSheetIndex((i) => i - 1)}
                >
                  <ChevronLeft className="size-3.5" />
                </Button>
                <span className="text-xs text-muted-foreground">
                  Sheet {activeSheetIndex + 1} / {sheetCount}
                </span>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-7 w-7 p-0"
                  disabled={activeSheetIndex === sheetCount - 1}
                  onClick={() => setActiveSheetIndex((i) => i + 1)}
                >
                  <ChevronRight className="size-3.5" />
                </Button>
              </>
            )}
          </div>
        </div>
      </CardHeader>
      <CardContent className="px-4 pb-4">
        {/* No `flex justify-center` here on purpose: centered content that
            overflows a flex container makes the overflowing start (left)
            edge unreachable by scroll in some browsers, and 200% needs the
            full sheet reachable (AC-S4-2). */}
        <div
          ref={containerRef}
          className="overflow-auto bg-muted/30 rounded-lg p-4 max-h-[70vh]"
        >
          {isMeasuringFit ? (
            <Skeleton className="h-64 w-full" />
          ) : (
            activeSheetDoc && (
              <TagSheetRenderer
                doc={activeSheetDoc}
                resolvedData={resolvedData}
                preview
                previewScale={scale}
              />
            )
          )}
        </div>
      </CardContent>
    </Card>
  );
}
