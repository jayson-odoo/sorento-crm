'use client';

/**
 * Portal proof viewer: renders a scaled-down preview of each tag sheet for the
 * salesperson to review before approving or requesting changes.
 *
 * Uses TagSheetRenderer in preview mode (DOM/CSS, not Konva) with mock data
 * resolved from the request lines. Phase 2 fetches the real print payload.
 */

import { useMemo, useState } from 'react';
import { ChevronLeft, ChevronRight, ZoomIn, ZoomOut } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import TagSheetRenderer, {
  type ResolvedLineData,
} from '@/app/(public)/c/print/tag-sheet/[downloadId]/components/TagSheetRenderer';
import type { TagSheetDoc } from '@/lib/dealer-kit/tag-template-types';

interface PriceTagProofViewerProps {
  doc: TagSheetDoc | null;
  resolvedData: Record<string, ResolvedLineData>;
}

const ZOOM_LEVELS = [0.2, 0.3, 0.4, 0.5, 0.6];

export default function PriceTagProofViewer({
  doc,
  resolvedData,
}: PriceTagProofViewerProps) {
  const [activeSheetIndex, setActiveSheetIndex] = useState(0);
  const [zoomIndex, setZoomIndex] = useState(1); // default 0.3

  const zoom = ZOOM_LEVELS[zoomIndex] ?? 0.3;
  const sheetCount = doc?.sheets.length ?? 0;

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
          <CardTitle className="text-base">Proof Preview</CardTitle>
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
          <CardTitle className="text-base">Proof Preview</CardTitle>
          <div className="flex items-center gap-2">
            {/* Zoom controls */}
            <Button
              variant="ghost"
              size="sm"
              className="h-7 w-7 p-0"
              disabled={zoomIndex === 0}
              onClick={() => setZoomIndex((i) => Math.max(0, i - 1))}
            >
              <ZoomOut className="size-3.5" />
            </Button>
            <span className="text-xs text-muted-foreground w-10 text-center">
              {Math.round(zoom * 100)}%
            </span>
            <Button
              variant="ghost"
              size="sm"
              className="h-7 w-7 p-0"
              disabled={zoomIndex === ZOOM_LEVELS.length - 1}
              onClick={() =>
                setZoomIndex((i) => Math.min(ZOOM_LEVELS.length - 1, i + 1))
              }
            >
              <ZoomIn className="size-3.5" />
            </Button>

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
        <div className="overflow-auto bg-muted/30 rounded-lg p-4 flex justify-center">
          {activeSheetDoc && (
            <TagSheetRenderer
              doc={activeSheetDoc}
              resolvedData={resolvedData}
              preview
              previewScale={zoom}
            />
          )}
        </div>
      </CardContent>
    </Card>
  );
}
