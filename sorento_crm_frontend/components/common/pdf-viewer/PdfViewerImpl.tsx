'use client';

import * as React from 'react';
import type { CSSProperties } from 'react';
import type {
  PDFDocumentLoadingTask,
  PDFDocumentProxy,
  PDFPageProxy,
  RenderTask,
  TextLayer,
} from 'pdfjs-dist';
import {
  ChevronLeft,
  ChevronRight,
  Download,
  ExternalLink,
  FileWarning,
  MoveHorizontal,
  ZoomIn,
  ZoomOut,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import { toast } from '@/lib/toast';

import { loadPdfJs, type PdfJs } from './pdfjs';
import './pdf-viewer.css';
import type { PdfViewerProps } from './types';

const ZOOM_MIN = 0.25;
const ZOOM_MAX = 5;
const ZOOM_STEP = 1.25;
/** The scroller's own padding (`p-2`), kept out of the fit-width sum. */
const SCROLLER_PADDING = 8;
/** Pages either side of the visible ones that keep a live canvas. The rest are sized
 *  placeholders: a 100-page scan with a canvas per page would hold gigabytes. */
const RENDER_AHEAD = 1;

type Status = 'idle' | 'loading' | 'ready' | 'error';
type Zoom = 'fit' | number;

interface LoadedDocument {
  doc: PDFDocumentProxy;
  pages: PDFPageProxy[];
  /** Widest page at scale 1, for fit-width. */
  baseWidth: number;
}

const clampZoom = (value: number) =>
  Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, Math.round(value * 100) / 100));

/**
 * The themed PDF viewer: pages drawn by pdf.js onto canvases under our own single toolbar,
 * instead of the browser's built-in viewer (its own dark toolbar inside our light UI).
 *
 * Every page sits in one continuous vertical scroll. A page is only drawn while it is near
 * the viewport; the rest hold their size so the scrollbar and page jumps stay true.
 */
export default function PdfViewerImpl({
  url,
  loadData,
  documentKey,
  fileName,
  title,
  page,
  onPageChange,
  pageCountHint,
  fileActions = true,
  unavailable,
  className,
}: PdfViewerProps) {
  const hasSource = Boolean(url || loadData);
  // With bytes but no url and no key, the one document this mount was given.
  const identity =
    documentKey ?? (url ? url.split('?')[0] : hasSource ? 'bytes' : null);

  // The loader reads the latest source through a ref, so a re-signed URL for the same
  // document (same identity) does not throw away the rendered pages.
  const sourceRef = React.useRef({ url, loadData });
  sourceRef.current = { url, loadData };
  const onPageChangeRef = React.useRef(onPageChange);
  onPageChangeRef.current = onPageChange;

  const [status, setStatus] = React.useState<Status>(
    hasSource ? 'loading' : 'idle',
  );
  const [loaded, setLoaded] = React.useState<LoadedDocument | null>(null);
  const [pdfjs, setPdfjs] = React.useState<PdfJs | null>(null);
  const [current, setCurrent] = React.useState(Math.max(1, page ?? 1));
  const [zoom, setZoom] = React.useState<Zoom>('fit');
  const [containerWidth, setContainerWidth] = React.useState(0);
  const [range, setRange] = React.useState<[number, number]>([
    1,
    1 + 2 * RENDER_AHEAD,
  ]);

  const scrollerRef = React.useRef<HTMLDivElement>(null);
  const pageRefs = React.useRef<(HTMLDivElement | null)[]>([]);
  // The last page this viewer and its caller agreed on. A `page` prop equal to it is the
  // echo of our own report, not a jump request.
  const agreedPageRef = React.useRef(Math.max(1, page ?? 1));

  React.useEffect(() => {
    if (!identity || !hasSource) {
      setStatus('idle');
      setLoaded(null);
      return;
    }
    let cancelled = false;
    let task: PDFDocumentLoadingTask | null = null;
    setStatus('loading');
    setLoaded(null);
    (async () => {
      try {
        const lib = await loadPdfJs();
        const { url: sourceUrl, loadData: read } = sourceRef.current;
        const source = read
          ? { data: new Uint8Array(await read()) }
          : { url: sourceUrl as string };
        if (cancelled) return;
        task = lib.getDocument({ ...source, isEvalSupported: false });
        const doc = await task.promise;
        const pages = await Promise.all(
          Array.from({ length: doc.numPages }, (_, i) => doc.getPage(i + 1)),
        );
        if (cancelled) return;
        const baseWidth = Math.max(
          ...pages.map((p) => p.getViewport({ scale: 1 }).width),
        );
        setPdfjs(() => lib);
        setLoaded({ doc, pages, baseWidth });
        setStatus('ready');
      } catch (error) {
        if (!cancelled) {
          // A trace for whoever hits the error state next - see the dev-only pdfjs
          // failure mode noted in LESSONS-LEARNT.md (webpack `next dev` without
          // --turbopack) that this would otherwise hide completely.
          console.warn('PdfViewer failed to load the document', error);
          setStatus('error');
        }
      }
    })();
    return () => {
      cancelled = true;
      void task?.destroy();
    };
  }, [identity, hasSource]);

  const numPages =
    loaded?.pages.length ??
    (pageCountHint && pageCountHint > 0 ? pageCountHint : 0);
  const shownPage = numPages
    ? Math.min(Math.max(current, 1), numPages)
    : current;

  const fitScale =
    loaded && containerWidth > 0
      ? clampZoom((containerWidth - 2 * SCROLLER_PADDING) / loaded.baseWidth)
      : 1;
  const scale = zoom === 'fit' ? fitScale : zoom;
  const scaleRef = React.useRef(scale);
  scaleRef.current = scale;

  React.useLayoutEffect(() => {
    const el = scrollerRef.current;
    if (!el) return;
    setContainerWidth(el.clientWidth);
    const observer = new ResizeObserver(() =>
      setContainerWidth(el.clientWidth),
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, [status]);

  const scrollToPage = React.useCallback((target: number) => {
    const el = scrollerRef.current;
    const node = pageRefs.current[target - 1];
    // Instant, never smooth: a page jump is a keyboard or click action, and a smooth scroll
    // would report every page it passes on the way.
    if (el && node)
      el.scrollTop = Math.max(0, node.offsetTop - SCROLLER_PADDING);
  }, []);

  const report = React.useCallback((next: number) => {
    setCurrent(next);
    if (next !== agreedPageRef.current) {
      agreedPageRef.current = next;
      onPageChangeRef.current?.(next);
    }
  }, []);

  const goTo = React.useCallback(
    (target: number) => {
      const bounded = numPages
        ? Math.min(Math.max(target, 1), numPages)
        : Math.max(target, 1);
      scrollToPage(bounded);
      report(bounded);
    },
    [numPages, report, scrollToPage],
  );

  // A caller-driven jump (a line's note opening its page).
  React.useEffect(() => {
    if (page == null || page === agreedPageRef.current) return;
    agreedPageRef.current = page;
    setCurrent(page);
    scrollToPage(page);
  }, [page, scrollToPage]);

  const syncFromScroll = React.useCallback(() => {
    const el = scrollerRef.current;
    if (!el) return;
    const top = el.scrollTop;
    const bottom = top + el.clientHeight;
    // The page under the top third of the view is the one being read.
    const probe = top + el.clientHeight / 3;
    let first = 0;
    let last = 0;
    let reading = 0;
    pageRefs.current.forEach((node, i) => {
      if (!node) return;
      const nodeTop = node.offsetTop;
      const nodeBottom = nodeTop + node.offsetHeight;
      if (nodeBottom > top && nodeTop < bottom) {
        if (!first) first = i + 1;
        last = i + 1;
      }
      if (!reading && nodeBottom > probe) reading = i + 1;
    });
    if (first) {
      const next: [number, number] = [
        first - RENDER_AHEAD,
        last + RENDER_AHEAD,
      ];
      setRange((prev) =>
        prev[0] === next[0] && prev[1] === next[1] ? prev : next,
      );
    }
    if (reading) report(reading);
  }, [report]);

  const frame = React.useRef(0);
  const onScroll = React.useCallback(() => {
    cancelAnimationFrame(frame.current);
    frame.current = requestAnimationFrame(syncFromScroll);
  }, [syncFromScroll]);
  React.useEffect(() => () => cancelAnimationFrame(frame.current), []);

  // Land on the requested page once the pages exist, and keep the page being read in place
  // across a zoom or a resize.
  React.useLayoutEffect(() => {
    if (status !== 'ready') return;
    scrollToPage(agreedPageRef.current);
    syncFromScroll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status, scale]);

  const zoomBy = React.useCallback((factor: number) => {
    setZoom(clampZoom(scaleRef.current * factor));
  }, []);

  const onKeyDown = (event: React.KeyboardEvent) => {
    if (event.altKey || event.ctrlKey || event.metaKey) return;
    const target = event.target as HTMLElement;
    if (target.closest('input, textarea, select, [contenteditable="true"]'))
      return;
    let handled = true;
    if (event.key === 'PageDown') goTo(shownPage + 1);
    else if (event.key === 'PageUp') goTo(shownPage - 1);
    else if (event.key === '+' || event.key === '=') zoomBy(ZOOM_STEP);
    else if (event.key === '-') zoomBy(1 / ZOOM_STEP);
    else handled = false;
    if (handled) {
      // Kept here: a surrounding dialog binds + and - to its own image zoom.
      event.preventDefault();
      event.stopPropagation();
    }
  };

  const download = async () => {
    if (!loaded) return;
    try {
      const bytes = await loaded.doc.getData();
      const href = URL.createObjectURL(
        new Blob([bytes as BlobPart], { type: 'application/pdf' }),
      );
      const a = document.createElement('a');
      a.href = href;
      a.download = fileName || `${title}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(href);
    } catch {
      toast.error(`Could not download ${fileName || title}`);
    }
  };

  const openUrl = url && /^https?:/i.test(url) ? url : null;
  const openLoaded = async () => {
    // Opened inside the click, before the await, or a popup blocker drops it.
    const tab = window.open('', '_blank');
    if (!tab || !loaded) return;
    tab.opener = null;
    const bytes = await loaded.doc.getData();
    const href = URL.createObjectURL(
      new Blob([bytes as BlobPart], { type: 'application/pdf' }),
    );
    tab.location.href = href;
    setTimeout(() => URL.revokeObjectURL(href), 60_000);
  };

  const pageLabel = numPages ? `Page ${shownPage} of ${numPages}` : null;

  return (
    <div
      className={cn(
        'flex min-h-0 min-w-0 flex-col overflow-hidden bg-background',
        className,
      )}
      role="group"
      aria-label={`${title} viewer`}
      onKeyDown={onKeyDown}
      data-slot="pdf-viewer"
    >
      <div className="flex flex-wrap items-center justify-between gap-x-2 gap-y-1 border-b border-border px-2 py-1.5">
        <div className="flex items-center gap-1">
          <Button
            type="button"
            mode="icon"
            variant="ghost"
            size="sm"
            aria-label="Previous page"
            disabled={shownPage <= 1}
            onClick={() => goTo(shownPage - 1)}
          >
            <ChevronLeft className="size-4" />
          </Button>
          {pageLabel && (
            <span className="min-w-[5.5rem] text-center text-xs tabular-nums text-muted-foreground">
              {pageLabel}
            </span>
          )}
          <Button
            type="button"
            mode="icon"
            variant="ghost"
            size="sm"
            aria-label="Next page"
            disabled={!numPages || shownPage >= numPages}
            onClick={() => goTo(shownPage + 1)}
          >
            <ChevronRight className="size-4" />
          </Button>
        </div>

        <div className="flex items-center gap-1">
          <Button
            type="button"
            mode="icon"
            variant="ghost"
            size="sm"
            aria-label="Zoom out"
            disabled={status !== 'ready' || scale <= ZOOM_MIN}
            onClick={() => zoomBy(1 / ZOOM_STEP)}
          >
            <ZoomOut className="size-4" />
          </Button>
          <span
            className="w-10 text-center text-xs tabular-nums text-muted-foreground"
            aria-live="polite"
          >
            {status === 'ready' ? `${Math.round(scale * 100)}%` : ''}
          </span>
          <Button
            type="button"
            mode="icon"
            variant="ghost"
            size="sm"
            aria-label="Zoom in"
            disabled={status !== 'ready' || scale >= ZOOM_MAX}
            onClick={() => zoomBy(ZOOM_STEP)}
          >
            <ZoomIn className="size-4" />
          </Button>
          <Button
            type="button"
            mode="icon"
            variant="ghost"
            size="sm"
            aria-label="Fit width"
            aria-pressed={zoom === 'fit'}
            disabled={status !== 'ready'}
            onClick={() => setZoom('fit')}
          >
            <MoveHorizontal className="size-4" />
          </Button>
        </div>

        {/* Three groups that wrap as whole groups, so a narrow column (375px, a side
            panel) stacks them instead of clipping the last button. */}
        {fileActions && hasSource && (
          <div className="flex items-center gap-1">
            <Button
              type="button"
              mode="icon"
              variant="ghost"
              size="sm"
              aria-label="Download"
              disabled={status !== 'ready'}
              onClick={download}
            >
              <Download className="size-4" />
            </Button>
            {openUrl ? (
              <Button
                type="button"
                mode="icon"
                variant="ghost"
                size="sm"
                asChild
              >
                <a
                  href={openUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  aria-label="Open in new tab"
                >
                  <ExternalLink className="size-4" />
                </a>
              </Button>
            ) : (
              <Button
                type="button"
                mode="icon"
                variant="ghost"
                size="sm"
                aria-label="Open in new tab"
                disabled={status !== 'ready'}
                onClick={openLoaded}
              >
                <ExternalLink className="size-4" />
              </Button>
            )}
          </div>
        )}
      </div>

      <div
        ref={scrollerRef}
        onScroll={onScroll}
        tabIndex={0}
        role="region"
        aria-label={title}
        className="relative min-h-0 flex-1 overflow-auto bg-muted/40 p-2 outline-none focus-visible:ring-2 focus-visible:ring-ring/40 focus-visible:ring-inset"
      >
        {status === 'idle' ? (
          (unavailable ?? (
            <PdfNotice title="The file is not available to preview" />
          ))
        ) : status === 'error' ? (
          <PdfNotice title="This PDF could not be shown here">
            {openUrl && (
              <Button type="button" variant="outline" size="sm" asChild>
                <a href={openUrl} target="_blank" rel="noopener noreferrer">
                  <ExternalLink className="size-3.5" aria-hidden />
                  Open the file
                </a>
              </Button>
            )}
          </PdfNotice>
        ) : status === 'loading' || !loaded || !pdfjs ? (
          <div
            role="status"
            aria-busy="true"
            aria-label="Loading"
            className="mx-auto w-full max-w-[640px]"
          >
            <Skeleton className="aspect-[1/1.414] w-full rounded-sm" />
          </div>
        ) : (
          <div className="flex w-max min-w-full flex-col items-center gap-2">
            {loaded.pages.map((pdfPage, index) => (
              <PdfPage
                key={index}
                pdfjs={pdfjs}
                pdfPage={pdfPage}
                scale={scale}
                label={`${title} page ${index + 1}`}
                draw={index + 1 >= range[0] && index + 1 <= range[1]}
                nodeRef={(node) => {
                  pageRefs.current[index] = node;
                }}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function PdfNotice({
  title,
  children,
}: {
  title: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="flex h-full min-h-40 flex-col items-center justify-center gap-2 rounded border border-dashed border-border px-6 text-center">
      <FileWarning className="size-5 text-muted-foreground" aria-hidden />
      <p className="text-sm font-medium">{title}</p>
      {children}
    </div>
  );
}

function PdfPage({
  pdfjs,
  pdfPage,
  scale,
  label,
  draw,
  nodeRef,
}: {
  pdfjs: PdfJs;
  pdfPage: PDFPageProxy;
  scale: number;
  label: string;
  draw: boolean;
  nodeRef: (node: HTMLDivElement | null) => void;
}) {
  const viewport = React.useMemo(
    () => pdfPage.getViewport({ scale }),
    [pdfPage, scale],
  );
  const canvasRef = React.useRef<HTMLCanvasElement>(null);
  const textRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    const canvas = canvasRef.current;
    const text = textRef.current;
    if (!draw || !canvas || !text) return;
    let cancelled = false;
    let renderTask: RenderTask | null = null;
    let textLayer: TextLayer | null = null;
    const ratio = window.devicePixelRatio || 1;
    canvas.width = Math.floor(viewport.width * ratio);
    canvas.height = Math.floor(viewport.height * ratio);
    try {
      renderTask = pdfPage.render({
        canvas,
        viewport,
        transform: ratio !== 1 ? [ratio, 0, 0, ratio, 0, 0] : undefined,
      });
    } catch {
      return;
    }
    renderTask.promise
      .then(() => {
        if (cancelled) return;
        text.replaceChildren();
        textLayer = new pdfjs.TextLayer({
          textContentSource: pdfPage.streamTextContent(),
          container: text,
          viewport,
        });
        return textLayer.render();
      })
      // A cancelled render rejects by design; a page that fails to draw stays a blank sheet.
      .catch(() => {});
    return () => {
      cancelled = true;
      renderTask?.cancel();
      textLayer?.cancel();
    };
  }, [draw, pdfjs, pdfPage, viewport]);

  const style = {
    width: Math.floor(viewport.width),
    height: Math.floor(viewport.height),
    '--scale-factor': scale,
    '--user-unit': pdfPage.userUnit,
    '--total-scale-factor': scale * pdfPage.userUnit,
    '--scale-round-x': '1px',
    '--scale-round-y': '1px',
  } as CSSProperties;

  return (
    <div
      ref={nodeRef}
      role="group"
      aria-label={label}
      data-page-number={pdfPage.pageNumber}
      className="relative shrink-0 bg-white shadow-xs ring-1 ring-border/60"
      style={style}
    >
      {draw && (
        <>
          <canvas
            ref={canvasRef}
            aria-hidden
            className="absolute inset-0 block size-full"
          />
          <div ref={textRef} className="textLayer" />
        </>
      )}
    </div>
  );
}
