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
  DialogDescription,
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
import { toast } from 'sonner';

/**
 * Fetch attachment bytes for the Download button and the Excel inline preview.
 * Default: the authenticated same-origin `/download` route via `apiFetch` (JWT
 * cookie/session) - matches the existing (protected) callers exactly. Token
 * surfaces (the contact portal) have no JWT session, so `apiFetch` 401s there;
 * they should pass their own `fetchBytes` via {@link AttachmentPreviewModalProps},
 * or simply omit `downloadUrl` on their items so the Download button (and this
 * fetch) never runs at all.
 */
type FetchBytes = (item: AttachmentPreviewItem) => Promise<Response>;

async function defaultFetchBytes(item: AttachmentPreviewItem): Promise<Response> {
  return apiFetch(item.downloadUrl as string);
}

/**
 * A plain `<a href download>` to /download sends no auth header → 401 ("File
 * wasn't available on site"), so fetch the bytes via `fetchBytes` and save the
 * resulting blob instead.
 */
async function downloadItem(item: AttachmentPreviewItem, fetchBytes: FetchBytes) {
  if (!item.downloadUrl) return;
  try {
    const resp = await fetchBytes(item);
    if (!resp.ok) throw new Error('Download failed');
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = item.name;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  } catch {
    toast.error(`Could not download ${item.name}`);
  }
}

/**
 * One previewable file. `url` is the stable, cacheable CDN URL (for
 * <img>/<video>/<iframe> - no CORS/fetch needed, browser + CDN cache it).
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
  /**
   * Override for fetching attachment bytes (Download button + Excel inline
   * preview). Defaults to `apiFetch(item.downloadUrl)` - unchanged for every
   * existing (protected) caller. Pass this on a token-authenticated surface
   * (no NextAuth JWT session) that has its own way to read the bytes; if no
   * such path exists, leave `downloadUrl` unset on the item instead - the
   * Download button then stays hidden rather than shipping one that 401s.
   */
  fetchBytes?: FetchBytes;
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
  fetchBytes,
}: AttachmentPreviewModalProps) {
  const resolvedFetchBytes = fetchBytes ?? defaultFetchBytes;
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

  // Editable zoom percentage. Keep a text draft so the user can type freely,
  // committing (clamped 25 - 500%) on Enter/blur.
  const [zoomText, setZoomText] = useState('100');
  useEffect(() => {
    setZoomText(String(Math.round(zoom * 100)));
  }, [zoom]);
  const commitZoomText = useCallback(() => {
    const pct = parseInt(zoomText, 10);
    if (!Number.isNaN(pct)) {
      setZoom(Math.min(5, Math.max(0.25, pct / 100)));
    } else {
      setZoomText(String(Math.round(zoom * 100)));
    }
  }, [zoomText, zoom]);

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
            {/* DialogDescription, not a bare <p>: Radix warns (and screen readers
                get nothing) when DialogContent has no aria-describedby, and the
                position counter is the description this dialog already had. */}
            <DialogDescription className="text-xs text-muted-foreground">
              {current + 1} / {items.length}
            </DialogDescription>
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
                <div className="flex items-center">
                  <input
                    type="text"
                    inputMode="numeric"
                    value={zoomText}
                    onChange={(e) =>
                      setZoomText(e.target.value.replace(/[^0-9]/g, '').slice(0, 3))
                    }
                    onBlur={commitZoomText}
                    onKeyDown={(e) => {
                      // Don't let the modal's arrow/+/- shortcuts fire while typing.
                      e.stopPropagation();
                      if (e.key === 'Enter') {
                        commitZoomText();
                        (e.target as HTMLInputElement).blur();
                      }
                    }}
                    aria-label="Zoom percentage"
                    className="w-8 bg-transparent text-right text-xs tabular-nums text-muted-foreground outline-none"
                  />
                  <span className="pr-1 text-xs text-muted-foreground">%</span>
                </div>
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
              <Button
                variant="outline"
                size="sm"
                onClick={() => downloadItem(activeItem, resolvedFetchBytes)}
              >
                <Download className="size-4 mr-1" />
                Download
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
                <div className="flex max-h-[80vh] min-h-[60vh] items-start justify-center overflow-auto bg-muted/20 p-3">
                  <PreviewSlide
                    item={item}
                    isActive={i === current}
                    zoom={i === current ? zoom : 1}
                    onWheelZoom={zoomBy}
                    fetchBytes={resolvedFetchBytes}
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
 * ONLY when their slide is active - at most one heavy element alive at a time.
 */
function PreviewSlide({
  item,
  isActive,
  zoom,
  onWheelZoom,
  fetchBytes,
}: {
  item: AttachmentPreviewItem;
  isActive: boolean;
  zoom: number;
  onWheelZoom: (factor: number) => void;
  fetchBytes: FetchBytes;
}) {
  const kind = kindOf(item.name);
  // <img>/<video>/<iframe> can't send an auth header, so they can only render a
  // public CDN url. Without one (e.g. an attachment missing its stored CDN
  // path), fall back to download rather than a broken element. Excel is exempt
  // it reads bytes via fetchBytes.
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
        className="my-auto max-h-[78vh] w-auto max-w-full object-contain transition-transform"
      />
    ) : (
      <PreviewFallback item={item} reason="This attachment has no previewable URL." fetchBytes={fetchBytes} />
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
      <PreviewFallback item={item} reason="This attachment has no previewable URL." fetchBytes={fetchBytes} />
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
      <PreviewFallback item={item} reason="This attachment has no previewable URL." fetchBytes={fetchBytes} />
    );
  }

  if (kind === 'excel') {
    return <ExcelSlide item={item} fetchBytes={fetchBytes} />;
  }

  return (
    <PreviewFallback item={item} reason="No inline preview for this file type." fetchBytes={fetchBytes} />
  );
}

function PreviewFallback({
  item,
  reason,
  fetchBytes,
}: {
  item: AttachmentPreviewItem;
  reason: string;
  fetchBytes: FetchBytes;
}) {
  return (
    <div className="my-auto flex flex-col items-center gap-3 py-12 text-center">
      <FileQuestion className="size-10 text-muted-foreground/50" />
      <p className="text-sm text-muted-foreground">{reason}</p>
      {item.downloadUrl && (
        <Button variant="outline" size="sm" onClick={() => downloadItem(item, fetchBytes)}>
          <Download className="size-4 mr-1" />
          Download to view
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

function ExcelSlide({ item, fetchBytes }: { item: AttachmentPreviewItem; fetchBytes: FetchBytes }) {
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
    // raw:false → return each cell's FORMATTED text (the `.w` value), so date
    // cells show as "21/04/2026" instead of their serial number (e.g. 46133),
    // and numbers keep their display format.
    const aoa = XLSX.utils.sheet_to_json<unknown[]>(ws, {
      header: 1,
      blankrows: false,
      defval: '',
      raw: false,
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
        // R2 public URLs send no CORS headers → callers read bytes via fetchBytes
        // (same-origin /download by default, or a caller-supplied override).
        const resp = await fetchBytes(item);
        if (!resp.ok) throw new Error('Failed to load spreadsheet.');
        const buf = await resp.arrayBuffer();
        const XLSX = await import('xlsx');
        const wb = XLSX.read(new Uint8Array(buf), { type: 'array', cellDates: true });
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
      <div className="my-auto flex flex-col items-center gap-3 py-12 text-center">
        <FileQuestion className="size-10 text-muted-foreground/50" />
        <p className="text-sm text-muted-foreground">{error}</p>
        {item.downloadUrl && (
          <Button variant="outline" size="sm" onClick={() => downloadItem(item, fetchBytes)}>
            <Download className="size-4 mr-1" />
            Download instead
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
