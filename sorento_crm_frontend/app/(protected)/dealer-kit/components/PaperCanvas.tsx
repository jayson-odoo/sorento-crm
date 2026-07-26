'use client';

import { useMemo } from 'react';
import { AlertTriangle } from 'lucide-react';

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { cn } from '@/lib/utils';
import { paginate, usablePageHeightMm, usablePageWidthMm } from '@/lib/dealer-kit/paginate';
import type { PrintProfile, Section } from '@/lib/dealer-kit/types';

import { BlockPreview } from './BlockPreview';

/**
 * Paper mode: the page at true paper geometry, with the page breaks drawn.
 *
 * This is the ONLY surface allowed to draw break lines. On the 1280px desktop
 * canvas the same lines would sit somewhere else entirely, so drawing them there
 * would be a confident lie (AC-H6). Paper mode is what makes it honest: the
 * canvas is at paper width, so the break is where the break is.
 *
 * Section heights are estimated here from block placement. Phase 2 replaces the
 * estimate with a measured height from the print route - the same route the PDF
 * worker renders, which is what keeps preview and PDF agreeing (AC-H5).
 */

/** Rough mm per grid row, used only until Phase 2 measures for real. */
const MM_PER_ROW = 7;
const SECTION_PADDING_MM: Record<string, number> = {
  none: 0,
  sm: 6,
  md: 12,
  lg: 20,
  xl: 32,
};

function estimateSectionHeightMm(section: Section): number {
  const placements = Object.values(section.layouts.desktop.blocks);
  const rows = placements.reduce(
    (lowest, placement) => Math.max(lowest, placement.rowStart + placement.rowSpan - 1),
    0,
  );
  const padding = SECTION_PADDING_MM[section.style.paddingY ?? 'md'] ?? 12;

  return rows * MM_PER_ROW + padding * 2;
}

export function PaperCanvas({
  sections,
  profile,
}: {
  sections: Section[];
  profile: PrintProfile;
}) {
  const pages = useMemo(
    () =>
      paginate({
        sections: sections.map((section) => ({
          id: section.id,
          heightMm: estimateSectionHeightMm(section),
          printMode: section.printMode,
        })),
        profile,
        includeCover: profile.cover,
      }),
    [sections, profile],
  );

  const sectionById = useMemo(
    () => new Map(sections.map((section) => [section.id, section])),
    [sections],
  );

  const pageWidthMm = usablePageWidthMm(profile) + profile.margins.left + profile.margins.right;
  const pageHeightMm = usablePageHeightMm(profile) + profile.margins.top + profile.margins.bottom;
  const overflowing = pages.filter((page) => page.overflows);

  if (pages.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-border p-10 text-center">
        <p className="text-sm font-medium text-foreground">Nothing to print</p>
        <p className="mt-1 text-sm text-muted-foreground">
          Every section is set to exclude from print, so this page would export blank.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center gap-6">
      {overflowing.length > 0 && (
        <Alert variant="destructive" className="w-full max-w-2xl">
          <AlertTriangle className="size-4" />
          <AlertTitle>
            {overflowing.length === 1
              ? '1 section is taller than a page'
              : `${overflowing.length} sections are taller than a page`}
          </AlertTitle>
          <AlertDescription>
            A section never splits across a fold, so this one will spill past the printable
            area. Shorten it or set it to start a new page.
          </AlertDescription>
        </Alert>
      )}

      {pages.map((page) => (
        <div key={page.pageNumber} className="flex flex-col items-center gap-2">
          <div
            className="relative bg-white shadow-md ring-1 ring-border"
            style={{
              width: `${pageWidthMm}mm`,
              height: `${pageHeightMm}mm`,
              maxWidth: '100%',
            }}
          >
            <div
              className="absolute border border-dashed border-sky-400/50"
              style={{
                top: `${profile.margins.top}mm`,
                right: `${profile.margins.right}mm`,
                bottom: `${profile.margins.bottom}mm`,
                left: `${profile.margins.left}mm`,
              }}
              aria-hidden
            />

            {page.isCover ? (
              <div className="flex h-full items-center justify-center">
                <span className="text-xs uppercase tracking-widest text-zinc-400">Cover</span>
              </div>
            ) : (
              <div
                className="absolute overflow-hidden"
                style={{
                  top: `${profile.margins.top}mm`,
                  right: `${profile.margins.right}mm`,
                  bottom: `${profile.margins.bottom}mm`,
                  left: `${profile.margins.left}mm`,
                }}
              >
                {page.placements.map((placement) => {
                  const section = sectionById.get(placement.sectionId);
                  if (!section) return null;

                  return (
                    <div
                      key={placement.sectionId}
                      className="absolute inset-x-0"
                      style={{
                        top: `${placement.offsetMm}mm`,
                        height: `${placement.heightMm}mm`,
                      }}
                    >
                      <div
                        className="grid h-full gap-2"
                        style={{ gridTemplateColumns: 'repeat(12, minmax(0, 1fr))' }}
                      >
                        {section.blocks.map((block) => {
                          const spot = section.layouts.desktop.blocks[block.id];
                          if (!spot || block.hideInPrint) return null;

                          return (
                            <div
                              key={block.id}
                              className="min-w-0 overflow-hidden"
                              style={{
                                gridColumn: `${spot.colStart} / span ${spot.colSpan}`,
                                gridRow: `${spot.rowStart} / span ${spot.rowSpan}`,
                              }}
                            >
                              <BlockPreview block={block} />
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}

            {profile.headerFooter.pageNumbers && !page.isCover && (
              <span
                className="absolute text-[8pt] text-zinc-500"
                style={{ bottom: '5mm', right: `${profile.margins.right}mm` }}
              >
                {page.pageNumber}
              </span>
            )}
          </div>

          <span
            className={cn(
              'text-xs font-medium',
              page.overflows ? 'text-destructive' : 'text-muted-foreground',
            )}
          >
            {page.isCover ? 'Cover' : `Page ${page.pageNumber}`}
            {page.overflows && ' · content overflows'}
          </span>
        </div>
      ))}
    </div>
  );
}
