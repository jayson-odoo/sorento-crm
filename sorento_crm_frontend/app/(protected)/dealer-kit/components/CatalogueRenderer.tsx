'use client';

import {
  BREAKPOINT_COLUMNS,
  BREAKPOINT_MIN_WIDTH,
  type Breakpoint,
} from '@/lib/dealer-kit/deriveLayout';
import { cn } from '@/lib/utils';
import { ROW_GAP_PX, ROW_HEIGHT_PX } from '@/lib/dealer-kit/gridMetrics';
// The one implementation of "what a SectionStyle looks like", shared with the
// builder canvas so the editor cannot drift from what it publishes.
import { sectionSurface } from '@/lib/dealer-kit/sectionSurface';
import type {
  Block,
  BlockLayout,
  ResolvedTile,
  Section,
  TileField,
} from '@/lib/dealer-kit/types';

import { BlockPreview } from './BlockPreview';

/**
 * The published document, rendered read-only.
 *
 * This is what a dealer or a consumer actually sees, and in S3 it is also what
 * the PDF worker prints through headless Chromium. One renderer, so "the PDF
 * matches the screen" is structural rather than a promise someone has to keep.
 *
 * **Why the layout is CSS variables plus a generated stylesheet, not Tailwind
 * classes.** A block's column and row come from the document, so they are data,
 * not design tokens. Emitting `col-start-[7]` per block would need a class for
 * every value at every breakpoint, which Tailwind cannot generate ahead of time
 * from runtime data. Custom properties carry the numbers; one stylesheet reads
 * them. Every block carries all three breakpoints' numbers at once, which is
 * what lets the stylesheet switch between them with no JavaScript - by media
 * query on screen, and by naming one outright on paper (see `breakpoint`).
 */

// Shared with the builder canvas: see lib/dealer-kit/gridMetrics. These two
// numbers ARE the contract between what a designer arranges and what a reader
// receives.

const PADDING_Y: Record<string, string> = {
  none: 'py-0',
  sm: 'py-3',
  md: 'py-6',
  lg: 'py-10',
  xl: 'py-16',
};

/** Which custom-property family carries a breakpoint's placement. */
const VAR_PREFIX: Record<Breakpoint, 'd' | 't' | 'm'> = {
  desktop: 'd',
  tablet: 't',
  mobile: 'm',
};

/** Everything that is true of the grid at every width. */
const GRID_BASE_CSS = `
.dk-grid {
  display: grid;
  /*
    Rows GROW to their content. A block's row count was measured in the builder
    at the builder's width; the published page is a different width, so a tile
    with a square image is a different height - and with fixed rows the extra
    height spilled out of the block and ran into the one below it. Growing the
    row moves what follows down instead, which is the difference between a
    catalogue that reads and one that overlaps.
  */
  grid-auto-rows: minmax(${ROW_HEIGHT_PX}px, auto);
  gap: ${ROW_GAP_PX}px;
}
.dk-block { min-width: 0; }
`;

/** The column count and the placement variables for one breakpoint. */
function placementRules(breakpoint: Breakpoint): string {
  const prefix = VAR_PREFIX[breakpoint];

  return `.dk-grid { grid-template-columns: repeat(${BREAKPOINT_COLUMNS[breakpoint]}, minmax(0, 1fr)); }
.dk-block {
  grid-column: var(--dk-${prefix}-col) / span var(--dk-${prefix}-span);
  grid-row: var(--dk-${prefix}-row) / span var(--dk-${prefix}-rows);
}`;
}

/**
 * The stylesheet the custom properties feed. Emitted once per rendered page.
 *
 * `responsive` is the screen: mobile-first, with the wider layouts behind media
 * queries, so resizing the window re-lays-out with no JavaScript.
 *
 * A PINNED breakpoint emits the same rules with the media queries removed, and
 * that is the print path. Paper cannot resize, so a query is a decision made by
 * something that is not the document - and it is a DIFFERENT decision from the
 * one that picks tile density, which is data and cannot be a query at all. That
 * is precisely how the two came apart: see the note on `breakpoint` below.
 */
function layoutCss(breakpoint: Breakpoint | 'responsive'): string {
  if (breakpoint !== 'responsive') {
    return `${GRID_BASE_CSS}\n${placementRules(breakpoint)}\n`;
  }

  return `${GRID_BASE_CSS}
${placementRules('mobile')}
@media (min-width: ${BREAKPOINT_MIN_WIDTH.tablet}px) {
${placementRules('tablet')}
}
@media (min-width: ${BREAKPOINT_MIN_WIDTH.desktop}px) {
${placementRules('desktop')}
}
`;
}

/**
 * Sections behave like the pages of the printed flyer they replace.
 *
 * The document this renders IS a brochure, and a reader who knows the A3 flyer
 * expects a flick to move them a page rather than leave them looking at the
 * bottom of one section and the top of the next.
 *
 * **`proximity`, never `mandatory`.** Mandatory snaps from anywhere, which on a
 * section taller than the viewport means the reader cannot stop in the middle
 * of it - they get yanked to one end or the other and can never read the part
 * between. Proximity engages only near a boundary, so a tall section scrolls
 * through normally and a short one still clicks into place (AC-R2).
 *
 * Applied to the document scroller (`html`) rather than a wrapper, because
 * making the catalogue its own scroll container costs the reader the mobile
 * browser's collapsing address bar and the page's own scroll restoration.
 *
 * Off entirely under `prefers-reduced-motion`: snapping is motion the reader
 * did not ask for, and somebody who has said so at the OS level has said so.
 */
const SNAP_CSS = `
html { scroll-snap-type: y proximity; }
.dk-section { scroll-snap-align: start; }
@media (prefers-reduced-motion: reduce) {
  html { scroll-snap-type: none; }
}
`;

/** A placement that is missing at a breakpoint falls back to a full-width row. */
function placementVars(
  prefix: 'd' | 't' | 'm',
  placement: BlockLayout | undefined,
  columns: number,
  fallbackRow: number,
): Record<string, string> {
  const colStart = placement?.colStart ?? 1;
  const colSpan = placement?.colSpan ?? columns;
  return {
    [`--dk-${prefix}-col`]: String(colStart),
    [`--dk-${prefix}-span`]: String(Math.max(1, colSpan)),
    [`--dk-${prefix}-row`]: String(placement?.rowStart ?? fallbackRow),
    [`--dk-${prefix}-rows`]: String(Math.max(1, placement?.rowSpan ?? 2)),
  };
}

export interface RenderedCatalogueData {
  /** collectionId -> tiles, already priced for whoever is reading. */
  collections?: Record<string, ResolvedTile[]>;
  /** tileTemplateId -> the fields that design binds. */
  tileTemplates?: Record<string, TileField[]>;
  /**
   * The design a collection block uses when it names none of its own.
   *
   * The page carries it, because "how do the tiles look" is one editorial
   * decision about the document. A brochure seeded from the printed flyer is
   * 341 collection blocks and the seed binds a design on NONE of them, so
   * without this fallback choosing one changed a single row and read - fairly -
   * as doing nothing at all.
   */
  defaultTileTemplateId?: string | null;
  /** assetId -> signed URL for the section backgrounds this document binds. */
  assets?: Record<string, string>;
}

function bindingFor(block: Block, data: RenderedCatalogueData) {
  const props = block.props;
  if (props.kind !== 'collection' || !props.collectionId) return undefined;

  const tiles = data.collections?.[props.collectionId];
  if (tiles === undefined) return undefined;

  // The block's own design wins - some rows really are different - and the
  // page's is the default behind it.
  const templateId = props.tileTemplateId ?? data.defaultTileTemplateId ?? null;

  return {
    tiles,
    tileFields: templateId ? data.tileTemplates?.[templateId] : undefined,
  };
}

function RenderedBlock({
  block,
  section,
  index,
  data,
  breakpoint,
}: {
  block: Block;
  section: Section;
  index: number;
  data: RenderedCatalogueData;
  breakpoint: Breakpoint;
}) {
  const fallbackRow = index * 2 + 1;
  const style = {
    ...placementVars('d', section.layouts.desktop.blocks[block.id], 12, fallbackRow),
    ...placementVars('t', section.layouts.tablet.blocks[block.id], 8, fallbackRow),
    ...placementVars('m', section.layouts.mobile.blocks[block.id], 4, fallbackRow),
  } as React.CSSProperties;

  return (
    <div className="dk-block" style={style} data-dk-block-id={block.id}>
      <BlockPreview block={block} resolved={bindingFor(block, data)} breakpoint={breakpoint} />
    </div>
  );
}

function RenderedSection({
  section,
  data,
  breakpoint,
}: {
  section: Section;
  data: RenderedCatalogueData;
  breakpoint: Breakpoint;
}) {
  // `exclude` is a print instruction, not a visibility one: the section is part
  // of the digital catalogue and simply does not go on paper. Only the PDF path
  // acts on it.
  const padding = PADDING_Y[section.style.paddingY ?? 'md'] ?? PADDING_Y.md;

  return (
    <section
      className={cn('dk-section w-full', padding)}
      style={sectionSurface(section.style, data.assets)}
      data-dk-section-id={section.id}
      aria-label={section.name}
    >
      <div className="mx-auto w-full max-w-[1400px] px-4 sm:px-6">
        <div className="dk-grid">
          {section.blocks.map((block, index) => (
            <RenderedBlock
              key={block.id}
              block={block}
              section={section}
              index={index}
              data={data}
              breakpoint={breakpoint}
            />
          ))}
        </div>
      </div>
    </section>
  );
}

export function CatalogueRenderer({
  name,
  sections,
  className,
  resolvedCollections,
  tileTemplates,
  defaultTileTemplateId,
  assets,
  /**
   * Which breakpoint this rendering IS.
   *
   * `responsive` (the screen) lets the media queries choose the placement as
   * the window changes, and takes desktop tile density.
   *
   * Naming a breakpoint pins BOTH halves of the layout to it: the placement
   * rules are emitted without media queries, and the same breakpoint chooses
   * tile density. That is one decision, which is the point.
   *
   * Print used to name none, and got the two halves from different places. The
   * default put DESKTOP density on the page, while the media queries still ran
   * and resolved against the width of the paper (A4 portrait is 794px, so
   * `min-width: 768px` fires and `min-width: 1280px` does not), so the
   * PLACEMENTS came out of the tablet layout. Blocks the designer put side by
   * side arrived stacked, carrying a tile count that belonged to the layout
   * they did not get.
   */
  breakpoint = 'responsive',
  snapSections = false,
}: {
  name: string;
  sections: Section[];
  className?: string;
  resolvedCollections?: Record<string, ResolvedTile[]>;
  tileTemplates?: Record<string, TileField[]>;
  /** The page's design, used by every collection block that names none. */
  defaultTileTemplateId?: string | null;
  /**
   * assetId -> signed URL, resolved by the server and sent WITH the document.
   *
   * Not fetched per section on purpose: this same renderer is printed by
   * headless Chromium, which decides it has finished when the page says so, and
   * artwork that starts loading after that prints as a blank band in a PDF
   * nobody re-checks.
   */
  assets?: Record<string, string>;
  breakpoint?: Breakpoint | 'responsive';
  /**
   * Settle on a section boundary as the reader scrolls, the way a page turn
   * does.
   *
   * On for the published catalogue. OFF for the builder, where a designer is
   * positioning blocks and needs to stop exactly where they choose, and
   * pointless for print, which does not scroll.
   */
  snapSections?: boolean;
}) {
  // Responsive placement is chosen per width by CSS, but density is data and
  // cannot be; desktop keeps the screen exactly as it was.
  const density: Breakpoint = breakpoint === 'responsive' ? 'desktop' : breakpoint;
  const data: RenderedCatalogueData = {
    collections: resolvedCollections,
    tileTemplates,
    defaultTileTemplateId,
    assets,
  };
  if (sections.length === 0) {
    // Published but empty is a real state, and it says so rather than rendering
    // a blank screen a reader would read as a broken link.
    return (
      <div className={cn('mx-auto max-w-xl px-4 py-24 text-center', className)}>
        <h1 className="text-xl font-semibold text-foreground">{name}</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          This catalogue has been published but does not have any content yet.
        </p>
      </div>
    );
  }

  return (
    <div className={cn('w-full', className)} data-dk-catalogue>
      <style
        dangerouslySetInnerHTML={{
          __html: layoutCss(breakpoint) + (snapSections ? SNAP_CSS : ''),
        }}
      />
      {sections.map((section) => (
        <RenderedSection
          key={section.id}
          section={section}
          data={data}
          breakpoint={density}
        />
      ))}
    </div>
  );
}
