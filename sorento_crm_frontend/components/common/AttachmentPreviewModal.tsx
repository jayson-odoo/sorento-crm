'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Download,
  ExternalLink,
  FileQuestion,
  LoaderCircle,
  ZoomIn,
  ZoomOut,
} from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Carousel,
  CarouselContent,
  CarouselItem,
  CarouselNext,
  CarouselPrevious,
  type CarouselApi,
} from '@/components/ui/carousel';
import { Button } from '@/components/ui/button';
import { apiFetch } from '@/lib/api';

/**
 * One previewable file. `url` is the stable, cacheable CDN URL (for
 * <img>/<video>/<iframe> — no CORS/fetch needed, browser + CDN cache it).
 * `downloadUrl` is the same-origin backend `/download` route, used both for the
 * Download button and for reading Excel bytes (R2 public URLs don't send CORS
 * headers, so xlsx must be fetched same-origin).
 */
export interface AttachmentPreviewItem {
  id: string;
  name: string;
  url: string;
  downloadUrl?: string;
  sizeBytes?: number | null;
}

interface AttachmentPreviewModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  items: AttachmentPreviewItem[];
  startIndex?: number;
}

type Kind = 'image' | 'video' | 'excel' | 'pdf' | 'other';

const IMAGE_EXT = /\.(jpe?g|png|gif|webp|bmp|svg|avif)$/i;
const VIDEO_EXT = /\.(mp4|webm|mov|m4v|ogg)$/i;
const EXCEL_EXT = /\.(xlsx?|xlsm|csv)$/i;
const PDF_EXT = /\.pdf$/i;

function kindOf(name: string): Kind {
  if (IMAGE_EXT.test(name)) return 'image';
  if (VIDEO_EXT.test(name)) return 'video';
  if (EXCEL_EXT.test(name)) return 'excel';
  if (PDF_EXT.test(name)) return 'pdf';
  return 'other';
}

export default function AttachmentPreviewModal({
  open,
  onOpenChange,
  items,
  startIndex = 0,
}: AttachmentPreviewModalProps) {
  const [api, setApi] = useState<CarouselApi>();
  const [current, setCurrent] = useState(startIndex);
  const [zoom, setZoom] = useState(1);

  useEffect(() => {
    if (!api) return;
    const onSelect = () => setCurrent(api.selectedScrollSnap());
    onSelect();
    api.on('select', onSelect);
    return () => {
      api.off('select', onSelect);
    };
  }, [api]);

  // Reset zoom whenever the visible slide changes.
  useEffect(() => {
    setZoom(1);
  }, [current]);

  const zoomBy = useCallback((factor: number) => {
    setZoom((z) => Math.min(5, Math.max(0.25, +(z * factor).toFixed(2))));
  }, []);

  const onKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'ArrowRight') api?.scrollNext();
      else if (e.key === 'ArrowLeft') api?.scrollPrev();
      else if (e.key === '+' || e.key === '=') zoomBy(1.25);
      else if (e.key === '-') zoomBy(0.8);
    },
    [api, zoomBy],
  );

  // Remount on each open so opts.startIndex is honoured and heavy content is
  // freed when closed.
  if (!open || items.length === 0) return null;
  const activeItem = items[current] ?? items[0];
  const activeIsImage = kindOf(activeItem?.name ?? '') === 'image';
  // Open-in-new-tab target: the cacheable CDN url if we have one, else the
  // same-origin download route.
  const openUrl = activeItem?.url?.startsWith('http')
    ? activeItem.url
    : activeItem?.downloadUrl;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="max-w-5xl gap-0 overflow-hidden p-0"
        onKeyDown={onKeyDown}
      >
        <DialogHeader className="flex-row items-center justify-between gap-3 border-b px-4 py-3 pr-12">
          <div className="min-w-0">
            <DialogTitle className="truncate text-base" title={activeItem?.name}>
              {activeItem?.name}
            </DialogTitle>
            <p className="text-xs text-muted-foreground">
              {current + 1} / {items.length}
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            {activeIsImage && (
              <div className="flex items-center rounded-md border">
                <Button
                  variant="ghost"
                  size="sm"
                  className="px-2"
                  onClick={() => zoomBy(0.8)}
                  disabled={zoom <= 0.25}
                  aria-label="Zoom out"
                >
                  <ZoomOut className="size-4" />
                </Button>
                <span className="w-11 text-center text-xs tabular-nums text-muted-foreground">
                  {Math.round(zoom * 100)}%
                </span>
                <Button
                  variant="ghost"
                  size="sm"
                  className="px-2"
                  onClick={() => zoomBy(1.25)}
                  disabled={zoom >= 5}
                  aria-label="Zoom in"
                >
                  <ZoomIn className="size-4" />
                </Button>
              </div>
            )}
            {openUrl && (
              <Button variant="outline" size="sm" asChild>
                <a href={openUrl} target="_blank" rel="noopener noreferrer">
                  <ExternalLink className="size-4 mr-1" />
                  Open
                </a>
              </Button>
            )}
            {activeItem?.downloadUrl && (
              <Button variant="outline" size="sm" asChild>
                <a href={activeItem.downloadUrl} download={activeItem.name}>
                  <Download className="size-4 mr-1" />
                  Download
                </a>
              </Button>
            )}
          </div>
        </DialogHeader>

        <Carousel
          setApi={setApi}
          opts={{ startIndex, loop: false, watchDrag: items.length > 1 }}
          className="w-full"
        >
          <CarouselContent className="ml-0">
            {items.map((item, i) => (
              <CarouselItem key={item.id} className="basis-full pl-0">
                <div className="flex max-h-[80vh] min-h-[60vh] items-center justify-center overflow-auto bg-muted/20 p-3">
                  <PreviewSlide
                    item={item}
                    isActive={i === current}
                    zoom={i === current ? zoom : 1}
                    onWheelZoom={zoomBy}
                  />
                </div>
              </CarouselItem>
            ))}
          </CarouselContent>
          {items.length > 1 && (
            <>
              <CarouselPrevious className="left-3" />
              <CarouselNext className="right-3" />
            </>
          )}
        </Carousel>
      </DialogContent>
    </Dialog>
  );
}

/**
 * Images always render (cheap; native `loading="lazy"` defers off-screen slides
 * so only the visible one hits the network). Heavy kinds (video/pdf/excel) mount
 * ONLY when their slide is active — at most one heavy element alive at a time.
 */
function PreviewSlide({
  item,
  isActive,
  zoom,
  onWheelZoom,
}: {
  item: AttachmentPreviewItem;
  isActive: boolean;
  zoom: number;
  onWheelZoom: (factor: number) => void;
}) {
  const kind = kindOf(item.name);
  // <img>/<video>/<iframe> can't send an auth header, so they can only render a
  // public CDN url. Without one (e.g. an attachment missing its stored CDN
  // path), fall back to download rather than a broken element. Excel is exempt —
  // it reads bytes via the authenticated same-origin /download route.
  const hasCdn = item.url.startsWith('http');

  if (kind === 'image') {
    return hasCdn ? (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={item.url}
        alt={item.name}
        loading="lazy"
        decoding="async"
        onWheel={(e) => {
          // Ctrl/Cmd + wheel zooms; plain wheel pans via the overflow container.
          if (e.ctrlKey || e.metaKey) {
            e.preventDefault();
            onWheelZoom(e.deltaY < 0 ? 1.1 : 0.9);
          }
        }}
        style={{ transform: `scale(${zoom})`, transformOrigin: 'center' }}
        className="max-h-[78vh] w-auto max-w-full object-contain transition-transform"
      />
    ) : (
      <PreviewFallback item={item} reason="This attachment has no previewable URL." />
    );
  }

  if (!isActive) return <SlideSpinner />;

  if (kind === 'video') {
    return hasCdn ? (
      <video
        src={item.url}
        controls
        preload="metadata"
        className="max-h-[78vh] w-auto"
      />
    ) : (
      <PreviewFallback item={item} reason="This attachment has no previewable URL." />
    );
  }

  if (kind === 'pdf') {
    return hasCdn ? (
      <iframe
        src={item.url}
        title={item.name}
        className="h-[78vh] w-full rounded border bg-white"
      />
    ) : (
      <PreviewFallback item={item} reason="This attachment has no previewable URL." />
    );
  }

  if (kind === 'excel') {
    return <ExcelSlide item={item} />;
  }

  return (
    <PreviewFallback item={item} reason="No inline preview for this file type." />
  );
}

function PreviewFallback({
  item,
  reason,
}: {
  item: AttachmentPreviewItem;
  reason: string;
}) {
  return (
    <div className="flex flex-col items-center gap-3 py-12 text-center">
      <FileQuestion className="size-10 text-muted-foreground/50" />
      <p className="text-sm text-muted-foreground">{reason}</p>
      {item.downloadUrl && (
        <Button variant="outline" size="sm" asChild>
          <a href={item.downloadUrl} download={item.name}>
            <Download className="size-4 mr-1" />
            Download to view
          </a>
        </Button>
      )}
    </div>
  );
}

function SlideSpinner() {
  return (
    <div className="flex h-[60vh] items-center justify-center">
      <LoaderCircle className="size-6 animate-spin text-muted-foreground/40" />
    </div>
  );
}

const MAX_ROWS = 200;
const MAX_COLS = 40;

function ExcelSlide({ item }: { item: AttachmentPreviewItem }) {
  const wbRef = useRef<import('xlsx').WorkBook | null>(null);
  const xlsxRef = useRef<typeof import('xlsx') | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sheets, setSheets] = useState<string[]>([]);
  const [active, setActive] = useState('');
  const [rows, setRows] = useState<string[][]>([]);
  const [truncated, setTruncated] = useState(false);

  const showSheet = useCallback((name: string) => {
    const wb = wbRef.current;
    const XLSX = xlsxRef.current;
    if (!wb || !XLSX) return;
    const ws = wb.Sheets[name];
    const aoa = XLSX.utils.sheet_to_json<unknown[]>(ws, {
      header: 1,
      blankrows: false,
      defval: '',
    });
    const trimmed = aoa
      .slice(0, MAX_ROWS)
      .map((r) => r.slice(0, MAX_COLS).map((c) => (c == null ? '' : String(c))));
    setTruncated(aoa.length > MAX_ROWS || aoa.some((r) => r.length > MAX_COLS));
    setRows(trimmed);
    setActive(name);
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        setLoading(true);
        setError(null);
        if (!item.downloadUrl) throw new Error('No source available to load this file.');
        // R2 public URLs send no CORS headers → read bytes same-origin.
        const resp = await apiFetch(item.downloadUrl);
        if (!resp.ok) throw new Error('Failed to load spreadsheet.');
        const buf = await resp.arrayBuffer();
        const XLSX = await import('xlsx');
        const wb = XLSX.read(new Uint8Array(buf), { type: 'array' });
        if (cancelled) return;
        xlsxRef.current = XLSX;
        wbRef.current = wb;
        setSheets(wb.SheetNames);
        const first = wb.SheetNames[0] ?? '';
        setLoading(false);
        showSheet(first);
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : 'Preview failed.');
          setLoading(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [item.downloadUrl]);

  if (loading) return <SlideSpinner />;
  if (error) {
    return (
      <div className="flex flex-col items-center gap-3 py-12 text-center">
        <FileQuestion className="size-10 text-muted-foreground/50" />
        <p className="text-sm text-muted-foreground">{error}</p>
        {item.downloadUrl && (
          <Button variant="outline" size="sm" asChild>
            <a href={item.downloadUrl} download={item.name}>
              <Download className="size-4 mr-1" />
              Download instead
            </a>
          </Button>
        )}
      </div>
    );
  }

  return (
    <div className="flex h-full w-full flex-col gap-2">
      {sheets.length > 1 && (
        <div className="flex flex-wrap gap-1">
          {sheets.map((name) => (
            <button
              key={name}
              type="button"
              onClick={() => showSheet(name)}
              className={`rounded px-2 py-1 text-xs ${
                name === active
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-muted text-muted-foreground hover:bg-muted/70'
              }`}
            >
              {name}
            </button>
          ))}
        </div>
      )}
      <div className="w-full overflow-auto rounded border bg-white">
        <table className="w-max border-collapse text-xs">
          <tbody>
            {rows.map((r, ri) => (
              <tr key={ri} className={ri === 0 ? 'bg-muted/50 font-medium' : ''}>
                {r.map((c, ci) => (
                  <td
                    key={ci}
                    className="max-w-[240px] truncate border px-2 py-1"
                    title={c}
                  >
                    {c}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {truncated && (
        <p className="text-xs text-muted-foreground">
          Showing first {MAX_ROWS} rows × {MAX_COLS} columns. Download for the full
          sheet.
        </p>
      )}
    </div>
  );
}
