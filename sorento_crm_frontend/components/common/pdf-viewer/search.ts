/**
 * In-viewer search for `PdfViewer`: an index over every page's pdf.js text content, match
 * finding, next/previous stepping, and painting the matches onto a page's text layer.
 *
 * A page's text is its text items joined in order (an item ending a line adds one space), then
 * lowercased with whitespace runs folded to one space, so "Total  Amount" across two items or
 * two lines still matches "total amount". Every character of that folded text remembers the
 * item and offset it came from, which is how a match is painted back onto the item's span.
 */

/** One pdf.js text item, as far as search needs it. */
export interface TextItemLike {
  str: string;
  hasEOL?: boolean;
}

export interface PageIndex {
  /** Folded text: lowercase, whitespace runs as one space. */
  text: string;
  /** Per character of `text`: the item it came from, or -1 for a line-break space. */
  item: Int32Array;
  /** Per character of `text`: its offset inside that item's string. */
  offset: Int32Array;
}

export interface SearchMatch {
  /** 1-based page number. */
  page: number;
  /** Range in that page's folded text. */
  start: number;
  end: number;
}

/** A piece of a match inside one text item: `str.slice(from, to)`. */
export interface MatchSegment {
  item: number;
  from: number;
  to: number;
}

export function buildPageIndex(items: TextItemLike[]): PageIndex {
  throw new Error('not implemented');
}

/** Folds a query the same way page text is folded. Leading and trailing space is dropped. */
export function foldQuery(query: string): string {
  throw new Error('not implemented');
}

/** Every match of `query` across `pages`, in reading order. Matches never overlap. */
export function findMatches(pages: PageIndex[], query: string): SearchMatch[] {
  throw new Error('not implemented');
}

/** The item slices a match covers, merged per item. */
export function matchSegments(
  index: PageIndex,
  match: Pick<SearchMatch, 'start' | 'end'>,
): MatchSegment[] {
  throw new Error('not implemented');
}

/** The match after (`1`) or before (`-1`) `current`, wrapping at both ends. */
export function stepMatch(current: number, total: number, direction: 1 | -1): number {
  throw new Error('not implemented');
}

/** The first match on `page` or after it, wrapping to the first match; -1 when none. */
export function firstMatchFrom(matches: SearchMatch[], page: number): number {
  throw new Error('not implemented');
}

/** False for a scan with no text layer at all (every page empty or whitespace). */
export function hasSearchableText(pages: PageIndex[]): boolean {
  throw new Error('not implemented');
}

export const HIGHLIGHT_CLASS = 'highlight';
export const SELECTED_CLASS = 'selected';

/**
 * Paints `segments` onto a page's text layer: each item's span gets its matched slices
 * wrapped in `<span class="highlight">` (plus `selected` for the current match). Spans
 * painted before and not in `segments` go back to plain text. Returns the selected mark, if
 * this page holds it.
 */
export function paintHighlights(
  divs: HTMLElement[],
  strs: string[],
  segments: (MatchSegment & { selected: boolean })[],
): HTMLElement | null {
  throw new Error('not implemented');
}
