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

/** Lowercases one character, keeping it one character (so offsets stay one to one). */
function lowerChar(char: string): string {
  const lower = char.toLowerCase();
  return lower.length === 1 ? lower : char;
}

export function buildPageIndex(items: TextItemLike[]): PageIndex {
  let text = '';
  const item: number[] = [];
  const offset: number[] = [];
  let lastWasSpace = false;
  const push = (char: string, from: number, at: number) => {
    const space = /\s/.test(char);
    if (space && lastWasSpace) return;
    lastWasSpace = space;
    text += space ? ' ' : lowerChar(char);
    item.push(from);
    offset.push(at);
  };
  items.forEach(({ str, hasEOL }, i) => {
    for (let at = 0; at < str.length; at += 1) push(str[at], i, at);
    if (hasEOL) push(' ', -1, 0);
  });
  return { text, item: Int32Array.from(item), offset: Int32Array.from(offset) };
}

/** Folds a query the same way page text is folded. Leading and trailing space is dropped. */
export function foldQuery(query: string): string {
  let folded = '';
  for (const char of query.trim()) folded += /\s/.test(char) ? ' ' : lowerChar(char);
  return folded.replace(/ {2,}/g, ' ');
}

/** Every match of `query` across `pages`, in reading order. Matches never overlap. */
export function findMatches(pages: PageIndex[], query: string): SearchMatch[] {
  const needle = foldQuery(query);
  const matches: SearchMatch[] = [];
  if (!needle) return matches;
  pages.forEach(({ text }, i) => {
    let from = text.indexOf(needle);
    while (from !== -1) {
      matches.push({ page: i + 1, start: from, end: from + needle.length });
      from = text.indexOf(needle, from + needle.length);
    }
  });
  return matches;
}

/** The item slices a match covers, merged per item. */
export function matchSegments(
  index: PageIndex,
  match: Pick<SearchMatch, 'start' | 'end'>,
): MatchSegment[] {
  const segments: MatchSegment[] = [];
  for (let at = match.start; at < match.end; at += 1) {
    const item = index.item[at];
    if (item < 0) continue;
    const offset = index.offset[at];
    const last = segments[segments.length - 1];
    if (last && last.item === item) last.to = offset + 1;
    else segments.push({ item, from: offset, to: offset + 1 });
  }
  return segments;
}

/** The match after (`1`) or before (`-1`) `current`, wrapping at both ends. */
export function stepMatch(current: number, total: number, direction: 1 | -1): number {
  if (total <= 0) return -1;
  return (((current + direction) % total) + total) % total;
}

/** The first match on `page` or after it, wrapping to the first match; -1 when none. */
export function firstMatchFrom(matches: SearchMatch[], page: number): number {
  if (matches.length === 0) return -1;
  const found = matches.findIndex((match) => match.page >= page);
  return found === -1 ? 0 : found;
}

/** False for a scan with no text layer at all (every page empty or whitespace). */
export function hasSearchableText(pages: PageIndex[]): boolean {
  return pages.some(({ text }) => text.trim().length > 0);
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
  const byItem = new Map<number, (MatchSegment & { selected: boolean })[]>();
  for (const segment of segments) {
    const list = byItem.get(segment.item) ?? [];
    list.push(segment);
    byItem.set(segment.item, list);
  }
  let selectedMark: HTMLElement | null = null;
  divs.forEach((div, i) => {
    const painted = div.dataset.painted === 'true';
    const list = byItem.get(i);
    if (!list) {
      if (painted) {
        div.textContent = strs[i] ?? '';
        delete div.dataset.painted;
      }
      return;
    }
    const str = strs[i] ?? '';
    list.sort((a, b) => a.from - b.from);
    const nodes: Node[] = [];
    let at = 0;
    for (const { from, to, selected } of list) {
      if (from > at) nodes.push(document.createTextNode(str.slice(at, from)));
      const mark = document.createElement('span');
      mark.className = selected ? `${HIGHLIGHT_CLASS} ${SELECTED_CLASS}` : HIGHLIGHT_CLASS;
      mark.textContent = str.slice(Math.max(from, at), to);
      nodes.push(mark);
      if (selected && !selectedMark) selectedMark = mark;
      at = Math.max(at, to);
    }
    if (at < str.length) nodes.push(document.createTextNode(str.slice(at)));
    div.replaceChildren(...nodes);
    div.dataset.painted = 'true';
  });
  return selectedMark;
}
