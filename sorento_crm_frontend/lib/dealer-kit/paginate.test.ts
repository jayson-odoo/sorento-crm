import { describe, it, expect } from 'vitest';

import {
  paginate,
  paperBreakpoint,
  paperWidthPx,
  usablePageHeightMm,
  type PaginationInput,
} from './paginate';
import { DEFAULT_PRINT_PROFILE, type PaperOrientation, type PaperSize } from './types';

/**
 * Golden set for paper-mode pagination (AC-H3 / AC-H5 / AC-H7).
 *
 * Pagination splits into a measured half and a pure half. Measuring section
 * heights needs a real browser; ASSIGNING measured sections to pages does not.
 * This is the pure half, and it is the half that decides where a page break
 * line is drawn - so it is the half that has to be right, because Print Preview
 * and the PDF worker both read it. If they disagree, break lines lie.
 */

const s = (
  id: string,
  heightMm: number,
  printMode: PaginationInput['sections'][number]['printMode'] = 'include',
): PaginationInput['sections'][number] => ({ id, heightMm, printMode });

const A4_USABLE = 297 - 15 - 15; // 267mm

describe('usablePageHeightMm', () => {
  it('subtracts both margins from the paper height', () => {
    expect(usablePageHeightMm(DEFAULT_PRINT_PROFILE)).toBe(A4_USABLE);
  });

  it('swaps width and height in landscape', () => {
    expect(
      usablePageHeightMm({ ...DEFAULT_PRINT_PROFILE, orientation: 'landscape' }),
    ).toBe(210 - 15 - 15);
  });
});

/**
 * Which breakpoint a sheet of paper IS.
 *
 * The print page renders the catalogue at exactly one breakpoint, for both the
 * block placements and the tile density, and this is where that one is chosen.
 * It has to be read off the paper rather than fixed, because the editor offers
 * papers on both sides of the desktop threshold: every A4 and Letter sheet is
 * a tablet, and A3 landscape is a desktop.
 */
describe('paperBreakpoint', () => {
  const profile = (pageSize: PaperSize, orientation: PaperOrientation) => ({
    ...DEFAULT_PRINT_PROFILE,
    pageSize,
    orientation,
  });

  it.each<[PaperSize, PaperOrientation, number, string]>([
    ['A4', 'portrait', 794, 'tablet'],
    ['A4', 'landscape', 1123, 'tablet'],
    ['A3', 'portrait', 1123, 'tablet'],
    // The one that stops the answer being hardcoded.
    ['A3', 'landscape', 1587, 'desktop'],
    ['Letter', 'portrait', 816, 'tablet'],
    ['Letter', 'landscape', 1056, 'tablet'],
  ])('%s %s is %ipx, which is a %s sheet', (pageSize, orientation, px, breakpoint) => {
    expect(Math.round(paperWidthPx(profile(pageSize, orientation)))).toBe(px);
    expect(paperBreakpoint(profile(pageSize, orientation))).toBe(breakpoint);
  });

  it('measures the whole sheet, not the area inside the margins', () => {
    // The worker prints with Chromium's own margins at zero, so the page box is
    // the paper and that is what a media query would resolve against. Deducting
    // the document's margins here would pick the wrong breakpoint for any sheet
    // sitting near a threshold.
    const wide = profile('A3', 'landscape');
    const narrowMargins = { ...wide, margins: { top: 40, right: 40, bottom: 40, left: 40 } };

    expect(paperWidthPx(narrowMargins)).toBe(paperWidthPx(wide));
    expect(paperBreakpoint(narrowMargins)).toBe('desktop');
  });
});

describe('paginate', () => {
  it('returns no pages for no sections', () => {
    expect(paginate({ sections: [], profile: DEFAULT_PRINT_PROFILE })).toEqual([]);
  });

  it('keeps sections that fit on one page together', () => {
    const pages = paginate({
      sections: [s('a', 100), s('b', 100)],
      profile: DEFAULT_PRINT_PROFILE,
    });

    expect(pages).toHaveLength(1);
    expect(pages[0].sectionIds).toEqual(['a', 'b']);
  });

  it('moves a section that does not fit onto the next page', () => {
    const pages = paginate({
      sections: [s('a', 200), s('b', 100)],
      profile: DEFAULT_PRINT_PROFILE,
    });

    expect(pages).toHaveLength(2);
    expect(pages[0].sectionIds).toEqual(['a']);
    expect(pages[1].sectionIds).toEqual(['b']);
  });

  it('drops excluded sections entirely', () => {
    const pages = paginate({
      sections: [s('a', 50), s('skip', 50, 'exclude'), s('b', 50)],
      profile: DEFAULT_PRINT_PROFILE,
    });

    expect(pages).toHaveLength(1);
    expect(pages[0].sectionIds).toEqual(['a', 'b']);
  });

  it('an excluded section does not consume vertical space', () => {
    const pages = paginate({
      sections: [s('a', 200), s('huge', 500, 'exclude'), s('b', 60)],
      profile: DEFAULT_PRINT_PROFILE,
    });

    expect(pages).toHaveLength(1);
    expect(pages[0].sectionIds).toEqual(['a', 'b']);
  });

  it('forces a new page for breakBefore even when the section would fit', () => {
    const pages = paginate({
      sections: [s('a', 50), s('b', 50, 'breakBefore')],
      profile: DEFAULT_PRINT_PROFILE,
    });

    expect(pages).toHaveLength(2);
    expect(pages[0].sectionIds).toEqual(['a']);
    expect(pages[1].sectionIds).toEqual(['b']);
  });

  it('does not emit a leading blank page when the first section is breakBefore', () => {
    const pages = paginate({
      sections: [s('a', 50, 'breakBefore'), s('b', 50)],
      profile: DEFAULT_PRINT_PROFILE,
    });

    expect(pages).toHaveLength(1);
    expect(pages[0].sectionIds).toEqual(['a', 'b']);
  });

  it('gives a section taller than a whole page its own page and flags the overflow', () => {
    const pages = paginate({
      sections: [s('tall', A4_USABLE + 120)],
      profile: DEFAULT_PRINT_PROFILE,
    });

    expect(pages).toHaveLength(1);
    expect(pages[0].sectionIds).toEqual(['tall']);
    expect(pages[0].overflows).toBe(true);
  });

  it('starts an oversized section on a fresh page rather than orphaning it', () => {
    const pages = paginate({
      sections: [s('a', 100), s('tall', A4_USABLE + 50)],
      profile: DEFAULT_PRINT_PROFILE,
    });

    expect(pages[0].sectionIds).toEqual(['a']);
    expect(pages[1].sectionIds).toEqual(['tall']);
    expect(pages[1].overflows).toBe(true);
  });

  it('reserves page 1 for the cover when the profile asks for one', () => {
    const pages = paginate({
      sections: [s('a', 50)],
      profile: { ...DEFAULT_PRINT_PROFILE, cover: true },
      includeCover: true,
    });

    expect(pages[0].isCover).toBe(true);
    expect(pages[0].sectionIds).toEqual([]);
    expect(pages[1].sectionIds).toEqual(['a']);
    expect(pages[1].pageNumber).toBe(2);
  });

  it('numbers pages from 1 and records the offset of each section', () => {
    const pages = paginate({
      sections: [s('a', 100), s('b', 100), s('c', 100)],
      profile: DEFAULT_PRINT_PROFILE,
    });

    expect(pages[0].pageNumber).toBe(1);
    expect(pages[1].pageNumber).toBe(2);
    expect(pages[0].placements).toEqual([
      { sectionId: 'a', offsetMm: 0, heightMm: 100 },
      { sectionId: 'b', offsetMm: 100, heightMm: 100 },
    ]);
    expect(pages[1].placements).toEqual([{ sectionId: 'c', offsetMm: 0, heightMm: 100 }]);
  });

  it('reports where each page break falls, which is what the canvas draws', () => {
    const pages = paginate({
      sections: [s('a', 200), s('b', 200), s('c', 200)],
      profile: DEFAULT_PRINT_PROFILE,
    });

    expect(pages.map((p) => p.sectionIds)).toEqual([['a'], ['b'], ['c']]);
  });

  it('is pure - it does not mutate its input', () => {
    const input: PaginationInput = {
      sections: [s('a', 200), s('b', 200)],
      profile: DEFAULT_PRINT_PROFILE,
    };
    const snapshot = structuredClone(input);

    paginate(input);

    expect(input).toEqual(snapshot);
  });

  it('handles a page whose sections exactly fill it without spilling', () => {
    const pages = paginate({
      sections: [s('a', A4_USABLE), s('b', 10)],
      profile: DEFAULT_PRINT_PROFILE,
    });

    expect(pages[0].sectionIds).toEqual(['a']);
    expect(pages[0].overflows).toBe(false);
    expect(pages[1].sectionIds).toEqual(['b']);
  });
});
