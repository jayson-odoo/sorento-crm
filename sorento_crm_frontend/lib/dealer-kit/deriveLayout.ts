/**
 * Responsive layout derivation for the Dealer Kit page builder (AC-C5 - AC-C8).
 *
 * A page stores one placement map per breakpoint. Only `desktop` is authored
 * directly; `tablet` and `mobile` are derived from it until a Designer edits
 * them, at which point that breakpoint is pinned (`isDerived: false`) and stops
 * following desktop.
 *
 * Derivation places BLOCKS. It deliberately does not touch what is inside a
 * block: a collection block's tile density per breakpoint lives on the block's
 * own `columns` prop, so a 4-across product grid stays 4-across on desktop and
 * 2-across on tablet without derivation knowing anything about tiles.
 */

export type Breakpoint = 'desktop' | 'tablet' | 'mobile';

export const BREAKPOINT_COLUMNS: Record<Breakpoint, number> = {
  desktop: 12,
  tablet: 8,
  mobile: 4,
};

/** Minimum viewport width at which each breakpoint applies. */
export const BREAKPOINT_MIN_WIDTH: Record<Breakpoint, number> = {
  desktop: 1280,
  tablet: 768,
  mobile: 0,
};

export const BREAKPOINT_ORDER: Breakpoint[] = ['desktop', 'tablet', 'mobile'];

/**
 * One block's placement. 1-indexed to match CSS Grid line numbers, so a
 * placement maps to `grid-column: colStart / span colSpan` with no arithmetic
 * at render time.
 */
export interface BlockLayout {
  colStart: number;
  colSpan: number;
  rowStart: number;
  rowSpan: number;
}

/** Block id -> placement. */
export type BlockPlacementMap = Record<string, BlockLayout>;

export interface BreakpointLayout {
  blocks: BlockPlacementMap;
  /** False once a Designer has edited this breakpoint by hand. */
  isDerived: boolean;
}

export type PageLayouts = Record<Breakpoint, BreakpointLayout>;

/**
 * Reading order: top to bottom, then left to right, ties broken on block id.
 *
 * The id tie-break is what makes derivation deterministic. Without it two
 * blocks sharing a cell would come out in whatever order `Object.keys` happened
 * to yield, and the same document would derive differently across saves.
 */
function readingOrder(entries: [string, BlockLayout][]): [string, BlockLayout][] {
  return [...entries].sort(([idA, a], [idB, b]) => {
    if (a.rowStart !== b.rowStart) return a.rowStart - b.rowStart;
    if (a.colStart !== b.colStart) return a.colStart - b.colStart;
    return idA < idB ? -1 : idA > idB ? 1 : 0;
  });
}

/**
 * Derive a placement map for a narrower grid.
 *
 * Every block becomes full width and stacks in reading order. That is the right
 * default here rather than a crude one, because the composition that matters at
 * small widths is inside the blocks, not between them.
 *
 * Pure: the source map is never mutated.
 */
export function deriveLayout(
  source: BlockPlacementMap,
  targetColumns: number,
): BlockPlacementMap {
  const derived: BlockPlacementMap = {};
  let nextRow = 1;

  for (const [id, placement] of readingOrder(Object.entries(source))) {
    const rowSpan = Math.max(1, Math.round(placement.rowSpan));

    derived[id] = {
      colStart: 1,
      colSpan: targetColumns,
      rowStart: nextRow,
      rowSpan,
    };

    nextRow += rowSpan;
  }

  return derived;
}

/**
 * Re-derive every breakpoint still following desktop, leaving pinned ones alone.
 * Called after any desktop edit (AC-C7).
 */
export function reflowDerivedBreakpoints(layouts: PageLayouts): PageLayouts {
  const next: PageLayouts = { ...layouts };

  for (const breakpoint of BREAKPOINT_ORDER) {
    if (breakpoint === 'desktop') continue;
    if (!layouts[breakpoint]?.isDerived) continue;

    next[breakpoint] = {
      isDerived: true,
      blocks: deriveLayout(layouts.desktop.blocks, BREAKPOINT_COLUMNS[breakpoint]),
    };
  }

  return next;
}

/** Pin a breakpoint to a hand-authored layout - it stops following desktop (AC-C7). */
export function pinBreakpoint(
  layouts: PageLayouts,
  breakpoint: Breakpoint,
  blocks: BlockPlacementMap,
): PageLayouts {
  return {
    ...layouts,
    [breakpoint]: { blocks, isDerived: false },
  };
}

/** Hand a breakpoint back to derivation, discarding its manual layout (AC-C8). */
export function rederiveBreakpoint(
  layouts: PageLayouts,
  breakpoint: Exclude<Breakpoint, 'desktop'>,
): PageLayouts {
  return {
    ...layouts,
    [breakpoint]: {
      isDerived: true,
      blocks: deriveLayout(layouts.desktop.blocks, BREAKPOINT_COLUMNS[breakpoint]),
    },
  };
}

/** A fresh set of layouts for a page whose desktop placement is `blocks`. */
export function createLayouts(blocks: BlockPlacementMap = {}): PageLayouts {
  return {
    desktop: { blocks, isDerived: false },
    tablet: { blocks: deriveLayout(blocks, BREAKPOINT_COLUMNS.tablet), isDerived: true },
    mobile: { blocks: deriveLayout(blocks, BREAKPOINT_COLUMNS.mobile), isDerived: true },
  };
}
