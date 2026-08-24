/**
 * Paper-mode pagination for the Dealer Kit page builder (AC-H3 / AC-H5 / AC-H7).
 *
 * Deliberately split in two:
 *
 *   measured - how tall is each section once rendered? Needs a real browser.
 *   pure    - given those heights, which page does each section land on?
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

import {
  BREAKPOINT_MIN_WIDTH,
  BREAKPOINT_ORDER,
  type Breakpoint,
} from './deriveLayout';
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
  /**
   * A single section taller than one page.
   *
   * This is the one case the model cannot describe. `break-inside: avoid`
   * keeps a section whole only while a whole one fits; past that Chromium
   * fragments it, and where the fold lands depends on measured content heights
   * this half of the paginator does not have. So the page count and the break
   * line stop being true from here on, and the flag exists to say so rather
   * than to let the canvas draw a break it cannot place. The renderer's own
   * `break-inside: avoid` on a tile keeps the unplaceable fold out of the
   * middle of a product; it cannot put it back where the preview drew it.
   */
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

/** CSS reckons 1in as 96px and 1in as 25.4mm, so a millimetre is a fixed count of px. */
const CSS_PX_PER_MM = 96 / 25.4;

/**
 * The width the document is laid out at when it is printed, in CSS pixels.
 *
 * The FULL paper, not the usable width: the worker prints with Chromium's own
 * margins set to zero (the document's margins are padding inside the page), so
 * the page box IS the sheet. This is therefore the width a `@media` query
 * resolves against during a print render, which is the only reason the number
 * matters at all.
 */
export function paperWidthPx(profile: PrintProfile): number {
  const { width, height } = PAPER_SIZES_MM[profile.pageSize];
  const widthMm = profile.orientation === 'landscape' ? height : width;

  return widthMm * CSS_PX_PER_MM;
}

/**
 * Which breakpoint a sheet of this paper IS.
 *
 * Paper has a width, and a width is what a breakpoint is chosen by, so this is
 * derived rather than configured. Hardcoding one would be wrong for half the
 * profiles the editor offers: A4 portrait is 794px and A4 landscape 1123px,
 * which are both tablet, but A3 landscape is 1587px, which is a desktop sheet.
 * A brochure printed on A3 landscape should look like the brochure on a
 * desktop screen, because that is the width it is.
 */
export function paperBreakpoint(profile: PrintProfile): Breakpoint {
  const px = paperWidthPx(profile);

  // BREAKPOINT_ORDER runs widest first, so the first match is the widest one
  // the paper satisfies. Mobile's minimum is 0, so there is always a match.
  return BREAKPOINT_ORDER.find((breakpoint) => px >= BREAKPOINT_MIN_WIDTH[breakpoint]) ?? 'mobile';
}

/**
 * Assign sections to pages.
 *
 * Sections are atomic: a section never splits across a fold, which is the
 * pagination-side counterpart of `break-inside: avoid` on `[data-dk-section-id]`
 * in the print page's stylesheet (AC-H7). Those two statements have to be kept
 * in step by hand, and they are the whole reason a break line drawn on the
 * canvas can be trusted.
 *
 * A section taller than a whole page gets its own page and is flagged
 * `overflows`, because that is the case where the two stop agreeing and no
 * model here can make them agree again: see `PaginatedPage.overflows`.
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
