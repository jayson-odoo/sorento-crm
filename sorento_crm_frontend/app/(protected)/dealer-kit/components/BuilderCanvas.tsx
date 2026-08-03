'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  GridLayout,
  useContainerWidth,
  verticalCompactor,
  type Layout,
} from 'react-grid-layout';

import { cn } from '@/lib/utils';
import {
  BREAKPOINT_COLUMNS,
  type BlockPlacementMap,
  type Breakpoint,
} from '@/lib/dealer-kit/deriveLayout';
import type { Block, SectionStyle } from '@/lib/dealer-kit/types';
import { ROW_HEIGHT_PX, rowsForHeight } from '@/lib/dealer-kit/gridMetrics';
import { hasArtwork, sectionSurface } from '@/lib/dealer-kit/sectionSurface';

import { BlockChrome } from './BlockChrome';
import type { ResolvedBinding } from './BlockPreview';

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
 *
 * This targets react-grid-layout v2, which differs from v1 in two ways that
 * matter: `WidthProvider` is gone (measure with the `useContainerWidth` hook),
 * and the flat props became config objects (`gridConfig` / `dragConfig` /
 * `resizeConfig`). v1 examples do not port over, and v1's `@types` package is
 * wrong here because v2 ships its own.
 */

/**
 * The row unit comes from ONE module shared with the published renderer.
 *
 * They lay the same blocks out with different engines, and while each kept its
 * own constant they disagreed: 24px here, 28px there, so a layout that looked
 * right in the builder overlapped once published.
 */
const ROW_HEIGHT = ROW_HEIGHT_PX;

export interface BuilderCanvasProps {
  blocks: Block[];
  placements: BlockPlacementMap;
  breakpoint: Breakpoint;
  selectedBlockId: string | null;
  /**
   * The section's own surface, painted here through the SAME function the
   * published catalogue and the PDF use.
   *
   * Without it a designer reviewing a seeded draft was the only person who
   * could not see the flyer artwork behind the headings they were being asked
   * to correct - and they were reviewing against a blank canvas that did not
   * match what a customer would receive.
   */
  sectionStyle?: SectionStyle;
  /**
   * assetId -> signed URL, exactly as the reader's payload carries it.
   *
   * Resolved by the server, never here: the document binds an id, and an editor
   * that signed its own URLs would be a second signer with a second opinion
   * about what is unsignable.
   */
  assets?: Record<string, string>;
  /** Locked while a breakpoint is still following desktop, so an accidental drag cannot silently pin it. */
  locked?: boolean;
  onSelectBlock: (blockId: string) => void;
  /**
   * `silent` marks a reflow the grid performed on its own (compaction, a
   * neighbour growing to fit its content) rather than something the user did.
   * Only a real drag or resize should be able to make the document dirty.
   */
  onPlacementsChange: (next: BlockPlacementMap, options?: { silent?: boolean }) => void;
  /**
   * Grow one block to `rowSpan` rows. Separate from `onPlacementsChange` because
   * it must apply against the LATEST placements, not the ones this render closed
   * over: two blocks measuring in the same tick would otherwise each spread a
   * stale map and the second would silently wipe the first.
   */
  onGrowBlock: (blockId: string, rowSpan: number) => void;
  /**
   * Resolved bindings for a block, if it has any. The canvas does not resolve
   * anything itself - resolution depends on who is viewing, which is the
   * editor's business, not the grid's.
   */
  resolveBlock?: (block: Block) => ResolvedBinding | undefined;
  onDeleteBlock: (blockId: string) => void;
}

function toRglLayout(blocks: Block[], placements: BlockPlacementMap): Layout {
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

function fromRglLayout(layout: Layout): BlockPlacementMap {
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

/** True when two placement maps describe the same grid, so no-op callbacks do not loop. */
function samePlacements(a: BlockPlacementMap, b: BlockPlacementMap): boolean {
  const keysA = Object.keys(a);
  if (keysA.length !== Object.keys(b).length) return false;

  return keysA.every((key) => {
    const left = a[key];
    const right = b[key];
    return (
      Boolean(right) &&
      left.colStart === right.colStart &&
      left.colSpan === right.colSpan &&
      left.rowStart === right.rowStart &&
      left.rowSpan === right.rowSpan
    );
  });
}

export function BuilderCanvas({
  blocks,
  placements,
  breakpoint,
  selectedBlockId,
  sectionStyle,
  assets,
  locked = false,
  onSelectBlock,
  onPlacementsChange,
  onGrowBlock,
  resolveBlock,
  onDeleteBlock,
}: BuilderCanvasProps) {
  const columns = BREAKPOINT_COLUMNS[breakpoint];
  const layout = useMemo(() => toRglLayout(blocks, placements), [blocks, placements]);
  const { containerRef, mounted } = useContainerWidth();

  /**
   * Measure the canvas ourselves rather than trusting the hook's width.
   *
   * The hook reported 646px for a container that is really 518px, and a window
   * resize did not correct it - so every block was laid out ~100px too wide and
   * the selected one overlapped the inspector panel beside it, covering its
   * controls.
   *
   * A CALLBACK ref, not an effect: the canvas is not rendered while the section
   * is empty, so an effect keyed on mount measures nothing and never runs again
   * once the first block arrives. A callback ref fires exactly when the node
   * appears, which is the moment there is something to measure.
   */
  const [measuredWidth, setMeasuredWidth] = useState(0);
  const observerRef = useRef<ResizeObserver | null>(null);

  const attachCanvas = useCallback(
    (node: HTMLDivElement | null) => {
      containerRef.current = node;
      observerRef.current?.disconnect();
      observerRef.current = null;
      if (!node) return;

      const measure = () => setMeasuredWidth(node.getBoundingClientRect().width);
      measure();
      const observer = new ResizeObserver(measure);
      observer.observe(node);
      observerRef.current = observer;
    },
    [containerRef],
  );

  useEffect(() => () => observerRef.current?.disconnect(), []);

  // Latest measured content height per block, so a re-measure can be compared
  // against what the grid currently allots without re-rendering on every frame.
  const measured = useRef<Record<string, number>>({});
  /** True only between a drag/resize start and its stop - the window in which a layout change is a real edit. */
  const gesture = useRef(false);

  /**
   * Grow a block when its content needs more rows than it has (AC-C4).
   *
   * Grow-only, deliberately. Shrinking here would fight the Designer: a block
   * they dragged taller on purpose would spring back to hug its text the moment
   * it re-measured.
   */
  const handleMeasure = useCallback(
    (blockId: string, contentHeightPx: number) => {
      if (locked) return;

      measured.current[blockId] = contentHeightPx;

      const placement = placements[blockId];
      if (!placement) return;

      // Compare against the CURRENT row span, not the previous measurement.
      // Keying this on "has the height changed?" meant that if a grow ever
      // failed to stick, the height stayed the same forever and the block was
      // never given another chance to grow.
      const needed = rowsForHeight(contentHeightPx);
      if (needed <= placement.rowSpan) return;

      onGrowBlock(blockId, needed);
    },
    [locked, placements, onGrowBlock],
  );

  const surface = sectionSurface(sectionStyle, assets);
  // Resolved, not merely bound: an asset the server could not sign is absent
  // from the map, and the section is then a plain one.
  const overArtwork = hasArtwork(sectionStyle, assets);

  if (blocks.length === 0) {
    return (
      // Painted here too. An empty section is not a blank slate - it already
      // carries a background a reader would see, and hiding it would mean the
      // first block is placed against a surface nobody has been shown. No
      // measuring ref: there is no grid to size yet, and the callback ref is
      // deliberately attached at the moment the real canvas appears.
      <div
        data-testid="dk-builder-canvas"
        className="rounded-lg border border-dashed border-border p-10 text-center"
        style={surface}
      >
        <p className="text-sm font-medium text-foreground">This section is empty</p>
        <p className="mt-1 text-sm text-muted-foreground">
          Add a block from the palette on the left to start laying it out.
        </p>
      </div>
    );
  }

  return (
    <div
      ref={attachCanvas}
      data-testid="dk-builder-canvas"
      // No `bg-background` any more: the section's own surface decides, exactly
      // as it does for a reader. A section whose background is "transparent"
      // shows the card it sits in, which is what transparent means; a class
      // underneath would have been a fourth opinion about the colour.
      className={cn(
        'relative rounded-lg border border-border',
        locked && 'pointer-events-none opacity-70',
      )}
      style={surface}
    >
      {/* The column guides ARE the grid, not decoration - they are what makes
          "snapped to a cell" visible rather than something you have to infer. */}
      <div className="pointer-events-none absolute inset-0 px-3" aria-hidden>
        <div
          className="grid h-full w-full"
          style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}
        >
          {Array.from({ length: columns }).map((_, index) => (
            <div key={index} className="border-r border-dashed border-border/40 last:border-r-0" />
          ))}
        </div>
      </div>

      {mounted && measuredWidth > 0 && (
        <GridLayout
          className="relative"
          width={measuredWidth}
          layout={layout}
          compactor={verticalCompactor}
          gridConfig={{
            cols: columns,
            rowHeight: ROW_HEIGHT,
            margin: [12, 12],
            containerPadding: [12, 12],
          }}
          dragConfig={{ enabled: !locked, handle: '[data-dk-drag-handle]' }}
          resizeConfig={{ enabled: !locked, handles: ['se', 'e', 's'] }}
          onDragStart={() => {
            gesture.current = true;
          }}
          onResizeStart={() => {
            gesture.current = true;
          }}
          // RGL fires the stop callback BEFORE the layout change it caused, so
          // clearing the flag synchronously here would make the user's own drag
          // look like a silent reflow. Clear it a tick later, once that trailing
          // layout change has been handled.
          onDragStop={() => {
            setTimeout(() => {
              gesture.current = false;
            }, 0);
          }}
          onResizeStop={() => {
            setTimeout(() => {
              gesture.current = false;
            }, 0);
          }}
          onLayoutChange={(next: Layout) => {
            const mapped = fromRglLayout(next);
            // RGL emits on mount and after its own compaction. Without this
            // guard the editor would mark itself dirty before anyone touched it.
            if (samePlacements(mapped, placements)) return;
            onPlacementsChange(mapped, { silent: !gesture.current });
          }}
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
                  onMeasure={handleMeasure}
                  rowSpan={placements[block.id]?.rowSpan}
                  resolved={resolveBlock?.(block)}
                  breakpoint={breakpoint}
                  overArtwork={overArtwork}
                />
              </div>
            ))}
        </GridLayout>
      )}
    </div>
  );
}
