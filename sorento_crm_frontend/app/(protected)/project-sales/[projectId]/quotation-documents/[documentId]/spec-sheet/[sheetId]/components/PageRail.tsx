'use client';

import * as React from 'react';

import ScaledSheet, { PX_PER_MM } from '@/components/dealer-kit/ScaledSheet';
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
}) {
  const scroller = React.useRef<HTMLDivElement>(null);
  const [inView, setInView] = React.useState<ReadonlySet<string>>(new Set());
  const seen = React.useRef(new Set<string>());

  const cover = pages.find((p) => p.key === COVER);
  const items = pages.filter((p) => p.key !== COVER);
  const width = strip ? STRIP_WIDTH : THUMB_WIDTH;
  const naturalW = pageMm.width_mm * PX_PER_MM;
  const scale = naturalW > 0 ? width / naturalW : 0;
  const height = Math.round(pageMm.height_mm * PX_PER_MM * scale);

  const pageKeys = pages.map((p) => p.key).join('|');
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
          page.hidden && 'opacity-50',
        )}
        style={{ width: width + 8 }}
        data-testid={`spec-rail-${page.key}`}
        data-rail-key={page.key}
      >
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
        </div>
      </div>
    );
  };

  const body = (
    <>
      {cover && thumb(cover, <span className="w-3 shrink-0" aria-hidden />)}
      <Sortable
        value={items}
        onValueChange={(next) => onReorder(next as SpecSheetPage[])}
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

  return (
    <div
      ref={scroller}
      data-testid="spec-sheet-rail"
      className={cn(
        strip
          ? 'flex w-full gap-1.5 overflow-x-auto pb-1'
          : 'flex max-h-[calc(100dvh-16rem)] min-h-[20rem] w-44 shrink-0 flex-col gap-1.5 overflow-y-auto',
      )}
    >
      {body}
    </div>
  );
}
