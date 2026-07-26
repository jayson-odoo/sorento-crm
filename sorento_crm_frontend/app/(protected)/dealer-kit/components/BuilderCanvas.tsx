'use client';

import { useMemo } from 'react';
import GridLayout, { WidthProvider, type Layout } from 'react-grid-layout';

import { cn } from '@/lib/utils';
import {
  BREAKPOINT_COLUMNS,
  type BlockPlacementMap,
  type Breakpoint,
} from '@/lib/dealer-kit/deriveLayout';
import type { Block } from '@/lib/dealer-kit/types';

import { BlockChrome } from './BlockChrome';

import 'react-grid-layout/css/styles.css';
import 'react-resizable/css/styles.css';

/**
 * Edit-time grid surface.
 *
 * react-grid-layout lives HERE and only here. The public renderer emits plain
 * CSS Grid from the same placement map, so nothing about RGL reaches a reader's
 * bundle (AC-C9). RGL's `{x, y, w, h}` maps 1:1 onto our 1-indexed
 * `{colStart, colSpan, rowStart, rowSpan}`, which is the whole reason it was
 * chosen over hand-rolling drag and resize maths on top of dnd-kit.
 */

const ResponsiveGrid = WidthProvider(GridLayout);

/** Grid row unit in px. Small, so content-driven heights land close to their true size. */
const ROW_HEIGHT = 24;

export interface BuilderCanvasProps {
  blocks: Block[];
  placements: BlockPlacementMap;
  breakpoint: Breakpoint;
  selectedBlockId: string | null;
  /** Locked while a breakpoint is still following desktop, so an accidental drag cannot silently pin it. */
  locked?: boolean;
  onSelectBlock: (blockId: string) => void;
  onPlacementsChange: (next: BlockPlacementMap) => void;
  onDeleteBlock: (blockId: string) => void;
}

function toRglLayout(blocks: Block[], placements: BlockPlacementMap): Layout[] {
  return blocks
    .filter((block) => placements[block.id])
    .map((block) => {
      const placement = placements[block.id];
      return {
        i: block.id,
        x: placement.colStart - 1,
        y: placement.rowStart - 1,
        w: placement.colSpan,
        h: placement.rowSpan,
        minW: 1,
        minH: 1,
      };
    });
}

function fromRglLayout(layout: Layout[]): BlockPlacementMap {
  const next: BlockPlacementMap = {};

  for (const item of layout) {
    next[item.i] = {
      colStart: item.x + 1,
      colSpan: item.w,
      rowStart: item.y + 1,
      rowSpan: item.h,
    };
  }

  return next;
}

export function BuilderCanvas({
  blocks,
  placements,
  breakpoint,
  selectedBlockId,
  locked = false,
  onSelectBlock,
  onPlacementsChange,
  onDeleteBlock,
}: BuilderCanvasProps) {
  const columns = BREAKPOINT_COLUMNS[breakpoint];
  const layout = useMemo(() => toRglLayout(blocks, placements), [blocks, placements]);

  if (blocks.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-border p-10 text-center">
        <p className="text-sm font-medium text-foreground">This section is empty</p>
        <p className="mt-1 text-sm text-muted-foreground">
          Add a block from the palette on the left to start laying it out.
        </p>
      </div>
    );
  }

  return (
    <div
      className={cn(
        'dk-canvas relative rounded-lg border border-border bg-background',
        locked && 'pointer-events-none opacity-70',
      )}
      style={
        {
          // The column guides are the grid itself, not decoration - they are what
          // makes "snapped to a cell" visible rather than something you infer.
          '--dk-columns': columns,
        } as React.CSSProperties
      }
    >
      <div className="pointer-events-none absolute inset-0 grid gap-0 px-0" aria-hidden>
        <div
          className="grid h-full w-full"
          style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}
        >
          {Array.from({ length: columns }).map((_, index) => (
            <div key={index} className="border-r border-dashed border-border/40 last:border-r-0" />
          ))}
        </div>
      </div>

      <ResponsiveGrid
        className="relative"
        layout={layout}
        cols={columns}
        rowHeight={ROW_HEIGHT}
        margin={[12, 12]}
        containerPadding={[12, 12]}
        compactType="vertical"
        preventCollision={false}
        isDraggable={!locked}
        isResizable={!locked}
        draggableHandle="[data-dk-drag-handle]"
        onLayoutChange={(next: Layout[]) => onPlacementsChange(fromRglLayout(next))}
      >
        {blocks
          .filter((block) => placements[block.id])
          .map((block) => (
            <div key={block.id}>
              <BlockChrome
                block={block}
                isSelected={block.id === selectedBlockId}
                onSelect={() => onSelectBlock(block.id)}
                onDelete={() => onDeleteBlock(block.id)}
              />
            </div>
          ))}
      </ResponsiveGrid>
    </div>
  );
}
