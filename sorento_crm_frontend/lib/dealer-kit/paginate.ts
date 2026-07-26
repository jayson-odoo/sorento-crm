/**
 * Paper-mode pagination for the Dealer Kit page builder (AC-H3 / AC-H5 / AC-H7).
 *
 * Deliberately split in two:
 *
 *   measured  - how tall is each section once rendered? Needs a real browser.
 *   pure      - given those heights, which page does each section land on?
 *
 * This file is the pure half. Print Preview and the PDF worker BOTH read it, and
 * that shared reading is the only reason a break line drawn on the canvas can be
 * trusted. Fork this logic and the preview starts lying about where page 2
 * begins.
 *
 * A break line is only drawn when the canvas is at true paper width. On the
 * 1280px desktop canvas it would sit somewhere else entirely, so the editor
 * draws none (AC-H6).
 */

import { PAPER_SIZES_MM, type PrintProfile, type SectionPrintMode } from './types';

export interface PaginationSection {
  id: string;
  /** Rendered height at paper width, in millimetres. */
  heightMm: number;
  printMode: SectionPrintMode;
}

export interface PaginationInput {
  sections: PaginationSection[];
  profile: PrintProfile;
  /** Reserve page 1 for a cover. */
  includeCover?: boolean;
}

export interface SectionPlacement {
  sectionId: string;
  offsetMm: number;
  heightMm: number;
}

export interface PaginatedPage {
  pageNumber: number;
  isCover: boolean;
  sectionIds: string[];
  placements: SectionPlacement[];
  usedMm: number;
  /** A single section taller than one page. It cannot be split, so it spills. */
  overflows: boolean;
}

/** Printable height once margins are removed, honouring orientation. */
export function usablePageHeightMm(profile: PrintProfile): number {
  const { width, height } = PAPER_SIZES_MM[profile.pageSize];
  const paperHeight = profile.orientation === 'landscape' ? width : height;

  return paperHeight - profile.margins.top - profile.margins.bottom;
}

/** Printable width once margins are removed, honouring orientation. */
export function usablePageWidthMm(profile: PrintProfile): number {
  const { width, height } = PAPER_SIZES_MM[profile.pageSize];
  const paperWidth = profile.orientation === 'landscape' ? height : width;

  return paperWidth - profile.margins.left - profile.margins.right;
}

/**
 * Assign sections to pages.
 *
 * Sections are atomic: a section never splits across a fold, which is the
 * pagination-side counterpart of `break-inside: avoid` on a tile (AC-H7). A
 * section taller than a whole page gets its own page and is flagged
 * `overflows`, so the editor can warn rather than silently clipping content.
 */
export function paginate(input: PaginationInput): PaginatedPage[] {
  const { sections, profile, includeCover = false } = input;

  const printable = sections.filter((section) => section.printMode !== 'exclude');
  if (printable.length === 0) return [];

  const limit = usablePageHeightMm(profile);
  const pages: PaginatedPage[] = [];

  let pageNumber = 0;

  const startPage = (isCover: boolean): PaginatedPage => {
    pageNumber += 1;
    const page: PaginatedPage = {
      pageNumber,
      isCover,
      sectionIds: [],
      placements: [],
      usedMm: 0,
      overflows: false,
    };
    pages.push(page);
    return page;
  };

  if (includeCover) startPage(true);

  let current = startPage(false);

  for (const section of printable) {
    const isFirstOnPage = current.sectionIds.length === 0;
    const wantsBreak = section.printMode === 'breakBefore';
    const doesNotFit = current.usedMm + section.heightMm > limit;

    // A break before the very first section would emit a blank leading page.
    if (!isFirstOnPage && (wantsBreak || doesNotFit)) {
      current = startPage(false);
    }

    current.placements.push({
      sectionId: section.id,
      offsetMm: current.usedMm,
      heightMm: section.heightMm,
    });
    current.sectionIds.push(section.id);
    current.usedMm += section.heightMm;

    if (section.heightMm > limit) current.overflows = true;
  }

  return pages;
}
