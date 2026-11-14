'use client';

import * as React from 'react';

import { MoreHorizontal } from 'lucide-react';

import ScaledSheet, { PX_PER_MM } from '@/components/dealer-kit/ScaledSheet';
import { Button } from '@/components/ui/button';
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuTrigger,
} from '@/components/ui/context-menu';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Sortable,
  SortableItem,
  SortableItemHandle,
} from '@/components/ui/sortable';
import type { TagSheetDesignPayload } from '@/lib/dealer-kit/design-payload';
import { cn } from '@/lib/utils';

import type { SpecSheetPage } from '../../../../../../_shared/services/specSheetService';
import { COVER } from './ReaderPage';

/** A thumbnail's width, px. The page is drawn small, like a slide. */
const THUMB_WIDTH = 148;
/** On a phone the rail is a strip: smaller thumbnails side by side. */
const STRIP_WIDTH = 112;

export interface RailPicture {
  payload: TagSheetDesignPayload;
  index: number;
}

/**
 * The page rail: real mini pages, like slides. Each thumbnail is a `ScaledSheet` drawn from the
 * preview chunk payloads the stack already loads; a thumbnail whose chunk is not loaded is a
 * placeholder. The rail scrolls on its own and reports which thumbnails it is showing, so the
 * reader asks for those chunks through the SAME cached chunk queries: one request per chunk,
 * never one per thumbnail. Only the thumbnails in the rail's own view mount a renderer.
 *
 * The pages are the Sortable's DIRECT children: its drag overlay clones the dragged child it
 * finds there, and dnd-kit measures collisions with that overlay.
 *
 * SPEC-SHEET-PARITY-B2 v3 (AC-C2.1-C2.5): the rail is the page navigation. "Page N of M" reads
 * under the thumbnails; each page after the cover has a "..." menu and a right-click (long-press
 * on a phone) menu with Remove page, which sets the page's existing left-out flag (`onRemove`).
 * Removed pages leave the thumbnails and are listed under "Removed pages (N)" with Put back.
 */
export function PageRail({
  pages,
  numbers,
  currentKey,
  canEdit,
  strip,
  pageMm,
  pictureOf,
  onSelect,
  onReorder,
  onVisibleChange,
  onRemove,
  className,
}: {
  /** Cover first. */
  pages: SpecSheetPage[];
  numbers: Map<string, number>;
  currentKey: string | null;
  canEdit: boolean;
  /** A horizontal strip (a phone) instead of a column. */
  strip: boolean;
  pageMm: { width_mm: number; height_mm: number };
  /** The loaded payload that holds a page, or null while its chunk is not here. */
  pictureOf: (key: string) => RailPicture | null;
  onSelect: (key: string) => void;
  /** The items after the cover, in their new order. */
  onReorder: (items: SpecSheetPage[]) => void;
  /** The thumbnails in the rail's own view. */
  onVisibleChange: (keys: ReadonlySet<string>) => void;
  /** Remove page (true) / Put back (false): the page's left-out flag. Absent: no menus. */
  onRemove?: (key: string, removed: boolean) => void;
  /** Extra classes for the column (the host sets its height, e.g. taller in full screen). */
  className?: string;
}) {
  const scroller = React.useRef<HTMLDivElement>(null);
  const [inView, setInView] = React.useState<ReadonlySet<string>>(new Set());
  const seen = React.useRef(new Set<string>());

  const cover = pages.find((p) => p.key === COVER);
  const items = pages.filter((p) => p.key !== COVER && !p.hidden);
  const removed = pages.filter((p) => p.key !== COVER && p.hidden);
  const shownCount = pages.filter((p) => p.key === COVER || !p.hidden).length;
  const currentNumber = currentKey ? numbers.get(currentKey) : undefined;
  const width = strip ? STRIP_WIDTH : THUMB_WIDTH;
  const naturalW = pageMm.width_mm * PX_PER_MM;
  const scale = naturalW > 0 ? width / naturalW : 0;
  const height = Math.round(pageMm.height_mm * PX_PER_MM * scale);

  const pageKeys = pages.map((p) => `${p.key}:${p.hidden ? 1 : 0}`).join('|');
  React.useEffect(() => {
    const root = scroller.current;
    if (!root || typeof IntersectionObserver === 'undefined') return;
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          const key = entry.target.getAttribute('data-rail-key');
          if (!key) continue;
          if (entry.isIntersecting) seen.current.add(key);
          else seen.current.delete(key);
        }
        const next = new Set(seen.current);
        setInView((prev) =>
          prev.size === next.size && [...next].every((k) => prev.has(k))
            ? prev
            : next,
        );
      },
      { root, rootMargin: strip ? '0px 50%' : '50% 0px' },
    );
    root
      .querySelectorAll('[data-rail-key]')
      .forEach((el) => observer.observe(el));
    return () => observer.disconnect();
  }, [pageKeys, strip]);

  React.useEffect(() => {
    onVisibleChange(inView);
  }, [inView, onVisibleChange]);

  const label = (page: SpecSheetPage) =>
    `${numbers.get(page.key) ?? '-'} ${page.key === COVER ? 'Cover' : page.code || page.name}`;

  const removable = (page: SpecSheetPage) =>
    canEdit && Boolean(onRemove) && page.key !== COVER;

  const goTo = (page: SpecSheetPage, picture: RailPicture | null) => (
    <button
      type="button"
      className="block overflow-hidden rounded-sm bg-white"
      style={{ width, height }}
      aria-label={`Go to page ${label(page)}`}
      aria-current={currentKey === page.key ? 'true' : undefined}
      title={label(page)}
      onClick={() => onSelect(page.key)}
    >
      {picture && scale > 0 ? (
        <ScaledSheet
          payload={picture.payload}
          sheetIndex={picture.index}
          scale={scale}
        />
      ) : (
        <span className="block size-full bg-muted" />
      )}
    </button>
  );

  const thumb = (page: SpecSheetPage, handle: React.ReactNode) => {
    const picture =
      inView.has(page.key) && !page.hidden ? pictureOf(page.key) : null;
    return (
      <div
        className={cn(
          'relative flex shrink-0 flex-col gap-0.5 rounded-md p-1 ring-1',
          currentKey === page.key
            ? 'bg-primary/10 ring-2 ring-primary'
            : 'ring-border',
        )}
        style={{ width: width + 8 }}
        data-testid={`spec-rail-${page.key}`}
        data-rail-key={page.key}
      >
        {removable(page) ? (
          <ContextMenu>
            <ContextMenuTrigger asChild>{goTo(page, picture)}</ContextMenuTrigger>
            <ContextMenuContent>
              <ContextMenuItem onSelect={() => onRemove?.(page.key, true)}>
                Remove page
              </ContextMenuItem>
            </ContextMenuContent>
          </ContextMenu>
        ) : (
          goTo(page, picture)
        )}
        <div className="flex min-w-0 items-center gap-1 text-2xs text-muted-foreground">
          {handle}
          <span className="min-w-0 flex-1 truncate" title={label(page)}>
            {label(page)}
          </span>
          {page.edited && (
            <span
              className="size-2 shrink-0 rounded-full bg-amber-500"
              title="Edited"
              aria-label="Edited"
            />
          )}
          {removable(page) && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="size-5 shrink-0"
                  aria-label="Page options"
                >
                  <MoreHorizontal className="size-3.5" aria-hidden />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onSelect={() => onRemove?.(page.key, true)}>
                  Remove page
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </div>
      </div>
    );
  };

  const body = (
    <>
      {cover && thumb(cover, <span className="w-3 shrink-0" aria-hidden />)}
      <Sortable
        value={items}
        onValueChange={(next) => {
          // Removed pages keep their place among the others, so Put back returns them there.
          const moved = next as SpecSheetPage[];
          let at = 0;
          onReorder(
            pages
              .filter((p) => p.key !== COVER)
              .map((p) => (p.hidden ? p : (moved[at++] ?? p))),
          );
        }}
        getItemValue={(page) => page.key}
        strategy={strip ? 'horizontal' : 'vertical'}
        className={strip ? 'flex gap-1.5' : 'flex flex-col gap-1.5'}
      >
        {items.map((page) => (
          <SortableItem key={page.key} value={page.key} disabled={!canEdit}>
            {thumb(
              page,
              canEdit ? (
                <SortableItemHandle
                  aria-label={`Drag ${page.code || page.name} to reorder`}
                  // Focusable, so the shared Sortable's keyboard sensor can move a page too.
                  tabIndex={0}
                  className="w-3 shrink-0 select-none text-center"
                >
                  &#8942;
                </SortableItemHandle>
              ) : (
                <span className="w-3 shrink-0" aria-hidden />
              ),
            )}
          </SortableItem>
        ))}
      </Sortable>
    </>
  );

  const footer = (
    <div className="flex shrink-0 flex-col gap-1.5">
      <p
        className="text-center text-xs tabular-nums text-muted-foreground"
        data-testid="spec-rail-page-of"
      >
        Page {currentNumber ?? '-'} of {shownCount}
      </p>
      {removed.length > 0 && (
        <div
          className="flex flex-col gap-1 border-t border-border pt-1.5"
          data-testid="spec-rail-removed"
        >
          <p className="text-xs font-medium text-muted-foreground">
            Removed pages ({removed.length})
          </p>
          {removed.map((page) => (
            <div
              key={page.key}
              className="flex min-w-0 items-center gap-1 text-xs"
            >
              <span
                className="min-w-0 flex-1 truncate"
                title={page.code || page.name}
              >
                {page.code || page.name}
              </span>
              {canEdit && onRemove && (
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  className="h-6 shrink-0 px-1.5 text-xs"
                  onClick={() => onRemove(page.key, false)}
                >
                  Put back
                </Button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );

  return (
    <div
      className={cn(
        'flex min-h-0 flex-col gap-1.5',
        strip
          ? 'w-full'
          : 'max-h-[calc(100dvh-16rem)] min-h-[20rem] w-44 shrink-0',
        className,
      )}
    >
      <div
        ref={scroller}
        data-testid="spec-sheet-rail"
        className={cn(
          strip
            ? 'flex w-full gap-1.5 overflow-x-auto overscroll-contain pb-1'
            : 'flex min-h-0 flex-1 flex-col gap-1.5 overflow-y-auto overscroll-contain',
        )}
      >
        {body}
      </div>
      {footer}
    </div>
  );
}
