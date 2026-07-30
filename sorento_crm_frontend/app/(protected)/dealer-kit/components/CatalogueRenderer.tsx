'use client';

import { BREAKPOINT_MIN_WIDTH } from '@/lib/dealer-kit/deriveLayout';
import { cn } from '@/lib/utils';
import { ROW_GAP_PX, ROW_HEIGHT_PX } from '@/lib/dealer-kit/gridMetrics';
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
 * **Why the layout is CSS variables plus three media queries, not Tailwind
 * classes.** A block's column and row come from the document, so they are data,
 * not design tokens. Emitting `col-start-[7]` per block would need a class for
 * every value at every breakpoint, which Tailwind cannot generate ahead of time
 * from runtime data. Custom properties carry the numbers; one stylesheet reads
 * them at each breakpoint. That also means resizing the window re-lays-out with
 * no JavaScript at all, which is what makes it safe to print.
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

/** The stylesheet the custom properties feed. Emitted once per rendered page. */
const LAYOUT_CSS = `
.dk-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
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
.dk-block {
  grid-column: var(--dk-m-col) / span var(--dk-m-span);
  grid-row: var(--dk-m-row) / span var(--dk-m-rows);
  min-width: 0;
}
@media (min-width: ${BREAKPOINT_MIN_WIDTH.tablet}px) {
  .dk-grid { grid-template-columns: repeat(8, minmax(0, 1fr)); }
  .dk-block {
    grid-column: var(--dk-t-col) / span var(--dk-t-span);
    grid-row: var(--dk-t-row) / span var(--dk-t-rows);
  }
}
@media (min-width: ${BREAKPOINT_MIN_WIDTH.desktop}px) {
  .dk-grid { grid-template-columns: repeat(12, minmax(0, 1fr)); }
  .dk-block {
    grid-column: var(--dk-d-col) / span var(--dk-d-span);
    grid-row: var(--dk-d-row) / span var(--dk-d-rows);
  }
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
}

function bindingFor(block: Block, data: RenderedCatalogueData) {
  const props = block.props;
  if (props.kind !== 'collection' || !props.collectionId) return undefined;

  const tiles = data.collections?.[props.collectionId];
  if (tiles === undefined) return undefined;

  return {
    tiles,
    tileFields: props.tileTemplateId
      ? data.tileTemplates?.[props.tileTemplateId]
      : undefined,
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
  breakpoint: 'desktop' | 'tablet' | 'mobile';
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
  breakpoint: 'desktop' | 'tablet' | 'mobile';
}) {
  // `exclude` is a print instruction, not a visibility one: the section is part
  // of the digital catalogue and simply does not go on paper. Only the PDF path
  // acts on it.
  const padding = PADDING_Y[section.style.paddingY ?? 'md'] ?? PADDING_Y.md;

  return (
    <section
      className={cn('w-full', padding)}
      style={section.style.background ? { background: section.style.background } : undefined}
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
  /**
   * Which breakpoint's tile density to use. The LAYOUT is responsive via CSS at
   * every width, but tile count per row is data, so print has to pick one -
   * paper has a fixed width and no media query will fire for it.
   */
  breakpoint = 'desktop',
}: {
  name: string;
  sections: Section[];
  className?: string;
  resolvedCollections?: Record<string, ResolvedTile[]>;
  tileTemplates?: Record<string, TileField[]>;
  breakpoint?: 'desktop' | 'tablet' | 'mobile';
}) {
  const data: RenderedCatalogueData = {
    collections: resolvedCollections,
    tileTemplates,
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
      <style dangerouslySetInnerHTML={{ __html: LAYOUT_CSS }} />
      {sections.map((section) => (
        <RenderedSection
          key={section.id}
          section={section}
          data={data}
          breakpoint={breakpoint}
        />
      ))}
    </div>
  );
}
