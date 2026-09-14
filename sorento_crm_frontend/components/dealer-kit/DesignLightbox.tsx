'use client';

/**
 * The tag sheet lightbox (r9 S1/D2).
 *
 * The attachment viewer's chrome (`PreviewModalChrome`) over a sheet instead of
 * an `<img>`: doc number, sheet counter, zoom cluster, Download PDF, close.
 * What a salesperson does here is look closely at a tag, so the zoom has to
 * behave the way every image viewer they use behaves - Ctrl/Cmd + wheel zooms
 * AROUND THE CURSOR, a plain wheel scrolls, and a drag pans once the sheet is
 * bigger than the window (C1).
 */

import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { ChevronLeft, ChevronRight, Download, Loader2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Dialog, DialogContent } from '@/components/ui/dialog';
import {
  PREVIEW_ZOOM_MAX,
  PREVIEW_ZOOM_MIN,
  PreviewModalChrome,
  type PreviewZoomPreset,
} from '@/components/common/PreviewModalChrome';
import ScaledSheet, { sheetPixelSize } from './ScaledSheet';
import type { TagSheetDesignPayload } from '@/lib/dealer-kit/design-payload';

/** What the % menu offers beside Fit. */
const ZOOM_PRESETS = [0.25, 0.5, 0.75, 1, 1.5, 2, 4] as const;

export interface DesignDownload {
  /** False while no completed export exists - the button says so. */
  available: boolean;
  pending?: boolean;
  onDownload: () => void;
}

interface DesignLightboxProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The document number. Never an id. */
  title: string;
  payload: TagSheetDesignPayload;
  /** Which sheet the card was showing when Open was pressed. */
  initialSheetIndex?: number;
  download?: DesignDownload;
}

function clampScale(value: number): number {
  return Math.min(PREVIEW_ZOOM_MAX, Math.max(PREVIEW_ZOOM_MIN, +value.toFixed(3)));
}

export default function DesignLightbox({
  open,
  onOpenChange,
  title,
  payload,
  initialSheetIndex = 0,
  download,
}: DesignLightboxProps) {
  const sheetCount = payload.doc?.sheets.length ?? 0;
  const [sheetIndex, setSheetIndex] = useState(initialSheetIndex);
  const [zoomMode, setZoomMode] = useState<'fit' | number>('fit');
  const [viewport, setViewport] = useState({ width: 0, height: 0 });
  const scrollRef = useRef<HTMLDivElement | null>(null);
  // A callback ref, not `useEffect` + `useRef`: the dialog's content mounts one
  // commit AFTER `open` flips (the shared `DialogContent` mirrors Radix's open
  // state into React state to gate its exit animation), so an effect keyed on
  // `open` reads a null ref, never measures, and the sheet opens at 100%
  // wearing a `Fit` label. Measured on the lane, 14 Sep.
  const [scroller, setScroller] = useState<HTMLDivElement | null>(null);
  const attachScroller = useCallback((node: HTMLDivElement | null) => {
    scrollRef.current = node;
    setScroller(node);
  }, []);

  // Reopening starts where the card was, at Fit.
  useEffect(() => {
    if (!open) return;
    setSheetIndex(initialSheetIndex);
    setZoomMode('fit');
  }, [open, initialSheetIndex]);

  useEffect(() => {
    if (!scroller) return;
    setViewport({ width: scroller.clientWidth, height: scroller.clientHeight });
    const observer = new ResizeObserver((entries) => {
      const box = entries[0]?.contentRect;
      if (box) setViewport({ width: box.width, height: box.height });
    });
    observer.observe(scroller);
    return () => observer.disconnect();
  }, [scroller]);

  const natural = useMemo(() => sheetPixelSize(payload.doc), [payload.doc]);

  // Fit means the WHOLE sheet, both axes - a lightbox that fits only the width
  // still hides the bottom half of an A4 page.
  const fitScale = useMemo(() => {
    if (!viewport.width || !viewport.height || !natural.width || !natural.height) {
      return 1;
    }
    return Math.max(
      PREVIEW_ZOOM_MIN,
      Math.min(
        (viewport.width - 24) / natural.width,
        (viewport.height - 24) / natural.height,
      ),
    );
  }, [viewport, natural]);

  const scale = zoomMode === 'fit' ? fitScale : zoomMode;

  // Zoom around a point: remember where the cursor sat in CONTENT coordinates,
  // then put that same content point back under the cursor once the new scale
  // has laid out. Without this, zooming in walks the page towards its top-left
  // corner and the reader loses the tag they were looking at.
  const anchorRef = useRef<{
    contentX: number;
    contentY: number;
    cursorX: number;
    cursorY: number;
    fromScale: number;
  } | null>(null);

  useLayoutEffect(() => {
    const node = scrollRef.current;
    const anchor = anchorRef.current;
    if (!node || !anchor) return;
    anchorRef.current = null;
    const ratio = scale / anchor.fromScale;
    node.scrollLeft = anchor.contentX * ratio - anchor.cursorX;
    node.scrollTop = anchor.contentY * ratio - anchor.cursorY;
  }, [scale]);

  const zoomBy = useCallback(
    (factor: number) => {
      setZoomMode((current) => {
        const from = current === 'fit' ? fitScale : current;
        return clampScale(from * factor);
      });
    },
    [fitScale],
  );

  // Ctrl/Cmd + wheel. A native listener rather than React's `onWheel`: React
  // registers wheel handlers passively at the root, so `preventDefault` there
  // is ignored and the browser page-zooms instead of the sheet.
  useEffect(() => {
    if (!scroller) return;
    const onWheel = (event: WheelEvent) => {
      if (!event.ctrlKey && !event.metaKey) return; // plain wheel scrolls
      event.preventDefault();
      const rect = scroller.getBoundingClientRect();
      const cursorX = event.clientX - rect.left;
      const cursorY = event.clientY - rect.top;
      anchorRef.current = {
        contentX: scroller.scrollLeft + cursorX,
        contentY: scroller.scrollTop + cursorY,
        cursorX,
        cursorY,
        fromScale: scale,
      };
      zoomBy(event.deltaY < 0 ? 1.1 : 1 / 1.1);
    };
    scroller.addEventListener('wheel', onWheel, { passive: false });
    return () => scroller.removeEventListener('wheel', onWheel);
  }, [scale, zoomBy, scroller]);

  // Drag to pan, once there is something to pan to.
  const dragRef = useRef<{ x: number; y: number } | null>(null);
  const [dragging, setDragging] = useState(false);
  const pannable =
    natural.width * scale > viewport.width ||
    natural.height * scale > viewport.height;

  const onPointerDown = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      if (!pannable || event.button !== 0) return;
      dragRef.current = { x: event.clientX, y: event.clientY };
      setDragging(true);
      // A pointer id that is not actually down (jsdom, a synthetic event)
      // rejects capture; the drag still works off the move events.
      try {
        event.currentTarget.setPointerCapture(event.pointerId);
      } catch {
        // Nothing to release later either - `endDrag` checks first.
      }
    },
    [pannable],
  );

  const onPointerMove = useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    const node = scrollRef.current;
    const from = dragRef.current;
    if (!node || !from) return;
    node.scrollLeft -= event.clientX - from.x;
    node.scrollTop -= event.clientY - from.y;
    dragRef.current = { x: event.clientX, y: event.clientY };
  }, []);

  const endDrag = useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    if (!dragRef.current) return;
    dragRef.current = null;
    setDragging(false);
    try {
      if (event.currentTarget.hasPointerCapture(event.pointerId)) {
        event.currentTarget.releasePointerCapture(event.pointerId);
      }
    } catch {
      // See `onPointerDown`: capture may never have been granted.
    }
  }, []);

  const onKeyDown = useCallback(
    (event: React.KeyboardEvent) => {
      if (event.key === '+' || event.key === '=') zoomBy(1.25);
      else if (event.key === '-') zoomBy(0.8);
      else if (event.key === '0') setZoomMode('fit');
      else if (event.key === 'ArrowRight' && sheetIndex < sheetCount - 1) {
        setSheetIndex((index) => index + 1);
      } else if (event.key === 'ArrowLeft' && sheetIndex > 0) {
        setSheetIndex((index) => index - 1);
      } else return;
      event.preventDefault();
    },
    [zoomBy, sheetIndex, sheetCount],
  );

  const presets: PreviewZoomPreset[] = useMemo(
    () => [
      { label: 'Fit', onSelect: () => setZoomMode('fit') },
      ...ZOOM_PRESETS.map((level) => ({
        label: `${Math.round(level * 100)}%`,
        onSelect: () => setZoomMode(level),
      })),
    ],
    [],
  );

  if (!open || !payload.doc || sheetCount === 0) return null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="max-w-[95vw] gap-0 overflow-hidden p-0 sm:max-w-5xl"
        onKeyDown={onKeyDown}
      >
        <PreviewModalChrome
          title={title}
          counter={`${sheetIndex + 1} / ${sheetCount}`}
          zoom={{
            value: scale,
            onZoomBy: zoomBy,
            onSetZoom: (next) => setZoomMode(clampScale(next)),
            presets,
            valueLabel:
              zoomMode === 'fit' ? 'Fit' : `${Math.round(scale * 100)}%`,
          }}
          actions={
            <>
              {sheetCount > 1 && (
                <div className="flex items-center rounded-md border">
                  <Button
                    variant="ghost"
                    size="sm"
                    className="px-2"
                    aria-label="Previous sheet"
                    disabled={sheetIndex === 0}
                    onClick={() => setSheetIndex((index) => index - 1)}
                  >
                    <ChevronLeft className="size-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="px-2"
                    aria-label="Next sheet"
                    disabled={sheetIndex >= sheetCount - 1}
                    onClick={() => setSheetIndex((index) => index + 1)}
                  >
                    <ChevronRight className="size-4" />
                  </Button>
                </div>
              )}
              {download && (
                <Button
                  variant="outline"
                  size="sm"
                  disabled={!download.available || download.pending}
                  onClick={download.onDownload}
                >
                  {download.pending ? (
                    <Loader2 className="size-4 mr-1 animate-spin" />
                  ) : (
                    <Download className="size-4 mr-1" />
                  )}
                  {download.available
                    ? 'Download PDF'
                    : 'PDF is being generated'}
                </Button>
              )}
            </>
          }
        />

        <div
          ref={attachScroller}
          data-testid="design-lightbox-viewport"
          className="flex h-[78dvh] overflow-auto bg-muted/30 p-3"
          style={{
            // Auto margins centre the sheet without making its start edge
            // unreachable the way `justify-content: center` does when the
            // content overflows. Pinch on a touch screen stays the browser's.
            touchAction: 'pan-x pan-y pinch-zoom',
            cursor: pannable ? (dragging ? 'grabbing' : 'grab') : 'default',
          }}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={endDrag}
          onPointerCancel={endDrag}
        >
          <div style={{ margin: 'auto' }}>
            <ScaledSheet
              payload={payload}
              sheetIndex={sheetIndex}
              scale={scale}
            />
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
