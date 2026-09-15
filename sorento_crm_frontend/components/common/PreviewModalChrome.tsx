'use client';

/**
 * The header every full-screen preview shares: title, position counter, zoom
 * cluster, actions (r9 S1/D2).
 *
 * Lifted out of `AttachmentPreviewModal` when the tag sheet lightbox needed the
 * same bar. Two surfaces drawing their own header is how a Download button ends
 * up in a different place on each of them, so the bar is one component and the
 * only thing a caller supplies is what goes in it. The close button belongs to
 * `DialogContent` (`showCloseButton`), not here.
 *
 * The zoom cluster covers both middles the app needs: an editable percentage
 * (an image, where any value is meaningful) and a preset menu (a tag sheet,
 * where Fit plus a handful of steps is what a reader actually wants).
 */

import { useCallback, useEffect, useState, type ReactNode } from 'react';
import { ChevronDown, ZoomIn, ZoomOut } from 'lucide-react';

import { Button } from '@/components/ui/button';
import {
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';

export const PREVIEW_ZOOM_MIN = 0.25;
export const PREVIEW_ZOOM_MAX = 5;

export interface PreviewZoomPreset {
  label: string;
  onSelect: () => void;
}

export interface PreviewZoomProps {
  /** Current scale, 1 = 100%. */
  value: number;
  min?: number;
  max?: number;
  /** Multiply the current scale (the buttons and the keyboard both use this). */
  onZoomBy: (factor: number) => void;
  /** Set an absolute scale (the editable percentage commits through this). */
  onSetZoom: (value: number) => void;
  /**
   * When given, the middle is a menu of these presets instead of an editable
   * percentage - `Fit` has no number to type, so a sheet offers steps.
   */
  presets?: PreviewZoomPreset[];
  /** What the middle reads when it is a menu (e.g. `Fit`). Defaults to the %. */
  valueLabel?: string;
}

export function PreviewZoomCluster({
  value,
  min = PREVIEW_ZOOM_MIN,
  max = PREVIEW_ZOOM_MAX,
  onZoomBy,
  onSetZoom,
  presets,
  valueLabel,
}: PreviewZoomProps) {
  // A text draft so the user can type freely; committed (clamped) on
  // Enter/blur.
  const [zoomText, setZoomText] = useState(String(Math.round(value * 100)));
  useEffect(() => {
    setZoomText(String(Math.round(value * 100)));
  }, [value]);

  const commitZoomText = useCallback(() => {
    const pct = parseInt(zoomText, 10);
    if (!Number.isNaN(pct)) {
      onSetZoom(Math.min(max, Math.max(min, pct / 100)));
    } else {
      setZoomText(String(Math.round(value * 100)));
    }
  }, [zoomText, value, min, max, onSetZoom]);

  return (
    <div className="flex items-center rounded-md border">
      <Button
        variant="ghost"
        size="sm"
        className="px-2"
        onClick={() => onZoomBy(0.8)}
        disabled={value <= min}
        aria-label="Zoom out"
      >
        <ZoomOut className="size-4" />
      </Button>
      {presets && presets.length > 0 ? (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant="ghost"
              size="sm"
              className="gap-1 px-2 text-xs tabular-nums text-muted-foreground"
              aria-label="Zoom level"
            >
              {valueLabel ?? `${Math.round(value * 100)}%`}
              <ChevronDown className="size-3.5" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            {presets.map((preset) => (
              <DropdownMenuItem key={preset.label} onSelect={preset.onSelect}>
                {preset.label}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      ) : (
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
            className="w-8 bg-transparent text-right text-xs tabular-nums text-muted-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-sm"
          />
          <span className="pr-1 text-xs text-muted-foreground">%</span>
        </div>
      )}
      <Button
        variant="ghost"
        size="sm"
        className="px-2"
        onClick={() => onZoomBy(1.25)}
        disabled={value >= max}
        aria-label="Zoom in"
      >
        <ZoomIn className="size-4" />
      </Button>
    </div>
  );
}

interface PreviewModalChromeProps {
  /** The document number or the file name - never an id. */
  title: string;
  /** The position counter, e.g. `2 / 5`. Rendered as the dialog description. */
  counter?: ReactNode;
  /** Omit (or pass null) on a surface that cannot zoom - a video, a PDF. */
  zoom?: PreviewZoomProps | null;
  /** Open / Download / Delete and friends, right of the zoom cluster. */
  actions?: ReactNode;
}

export function PreviewModalChrome({
  title,
  counter,
  zoom,
  actions,
}: PreviewModalChromeProps) {
  return (
    // Stacks at phone width: title + zoom + actions cannot fit on one 375px
    // row, and a plain flex-row overflows the dialog instead of wrapping.
    <DialogHeader className="flex-col items-stretch gap-2 border-b px-4 py-3 pr-12 text-start sm:flex-row sm:items-center sm:justify-between sm:gap-3">
      <div className="min-w-0">
        <DialogTitle className="truncate text-base" title={title}>
          {title}
        </DialogTitle>
        {/* DialogDescription, not a bare <p>: Radix warns (and screen readers
            get nothing) when DialogContent has no aria-describedby, and the
            position counter is the description these dialogs already had. */}
        <DialogDescription className="text-xs text-muted-foreground">
          {counter}
        </DialogDescription>
      </div>
      <div className="flex flex-wrap items-center gap-2 sm:shrink-0 sm:justify-end">
        {zoom && <PreviewZoomCluster {...zoom} />}
        {actions}
      </div>
    </DialogHeader>
  );
}

export default PreviewModalChrome;
