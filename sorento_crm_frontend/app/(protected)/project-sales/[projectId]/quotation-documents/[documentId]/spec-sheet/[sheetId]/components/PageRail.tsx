'use client';

import * as React from 'react';

import { Sortable, SortableItem, SortableItemHandle } from '@/components/ui/sortable';
import { cn } from '@/lib/utils';

import type { SpecSheetPage } from '../../../../../../_shared/services/specSheetService';
import { COVER } from './ReaderPage';

/**
 * The page rail: labels only. A thumbnail would mean a renderer per page, which is the cost the
 * windowed stack exists to avoid; the stack beside it is the picture.
 *
 * The pages are the Sortable's DIRECT children: its drag overlay clones the dragged child it
 * finds there, and dnd-kit measures collisions with that overlay. Wrapped in a div the overlay is
 * empty and a drop does nothing.
 */
export function PageRail({
  pages,
  numbers,
  currentKey,
  canEdit,
  onSelect,
  onReorder,
}: {
  /** Cover first. */
  pages: SpecSheetPage[];
  numbers: Map<string, number>;
  currentKey: string | null;
  canEdit: boolean;
  onSelect: (key: string) => void;
  /** The items after the cover, in their new order. */
  onReorder: (items: SpecSheetPage[]) => void;
}) {
  const cover = pages.find((p) => p.key === COVER);
  const items = pages.filter((p) => p.key !== COVER);

  const label = (page: SpecSheetPage) =>
    `${numbers.get(page.key) ?? '-'} ${page.key === COVER ? 'Cover' : page.code || page.name}`;

  const item = (page: SpecSheetPage, handle: React.ReactNode) => (
    <div
      className={cn(
        'flex min-w-0 items-center gap-1 rounded-md px-1.5 py-1 text-xs',
        currentKey === page.key ? 'bg-primary/10 ring-1 ring-primary' : 'ring-1 ring-border',
        page.hidden && 'opacity-50',
      )}
      data-testid={`spec-rail-${page.key}`}
    >
      {handle}
      <button
        type="button"
        className="min-w-0 flex-1 truncate text-left"
        title={label(page)}
        aria-current={currentKey === page.key ? 'true' : undefined}
        onClick={() => onSelect(page.key)}
      >
        {label(page)}
      </button>
      {page.edited && (
        <span className="size-2 shrink-0 rounded-full bg-amber-500" title="Edited" aria-label="Edited" />
      )}
    </div>
  );

  return (
    <div className="flex flex-col gap-1.5" data-testid="spec-sheet-rail">
      {cover && item(cover, <span className="w-4 shrink-0" aria-hidden />)}
      <Sortable
        value={items}
        onValueChange={(next) => onReorder(next as SpecSheetPage[])}
        getItemValue={(page) => page.key}
        strategy="vertical"
        className="flex flex-col gap-1.5"
      >
        {items.map((page) => (
          <SortableItem key={page.key} value={page.key} disabled={!canEdit}>
            {item(
              page,
              canEdit ? (
                <SortableItemHandle
                  aria-label={`Drag ${page.code || page.name} to reorder`}
                  // Focusable, so the shared Sortable's keyboard sensor can move a page too.
                  tabIndex={0}
                  className="w-4 shrink-0 select-none text-center text-muted-foreground"
                >
                  &#8942;
                </SortableItemHandle>
              ) : (
                <span className="w-4 shrink-0" aria-hidden />
              ),
            )}
          </SortableItem>
        ))}
      </Sortable>
    </div>
  );
}
