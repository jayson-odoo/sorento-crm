/**
 * Search inside the PDF viewer: the index over pdf.js text items, finding matches across
 * pages, stepping between them, and painting them on the text layer.
 */
import { describe, expect, it } from 'vitest';

import {
  buildPageIndex,
  findMatches,
  firstMatchFrom,
  foldQuery,
  hasSearchableText,
  matchSegments,
  paintHighlights,
  stepMatch,
} from './search';

const page = (...items: (string | [string, true])[]) =>
  buildPageIndex(
    items.map((item) =>
      Array.isArray(item) ? { str: item[0], hasEOL: true } : { str: item },
    ),
  );

describe('buildPageIndex', () => {
  it('joins the items, lowercases them and folds whitespace runs to one space', () => {
    const index = page('Total ', ' Amount ', ['RM 1,200', true], 'Due');
    expect(index.text).toBe('total amount rm 1,200 due');
  });

  it('remembers which item and offset each character came from', () => {
    const index = page('ab', ['cd', true], 'e');
    // "abcd e": the space is the line break, which belongs to no item.
    expect(index.text).toBe('abcd e');
    expect(Array.from(index.item)).toEqual([0, 0, 1, 1, -1, 2]);
    expect(Array.from(index.offset)).toEqual([0, 1, 0, 1, 0, 0]);
  });
});

describe('foldQuery', () => {
  it('folds a query the way page text is folded', () => {
    expect(foldQuery('  Total\t  AMOUNT ')).toBe('total amount');
    expect(foldQuery('   ')).toBe('');
  });
});

describe('findMatches', () => {
  const pages = [
    page('Sorento sofa, sorento chair'),
    page('Nothing here'),
    page('Quotation for ', ['SORENTO', true], 'Sdn Bhd'),
  ];

  it('finds every match on every page, in reading order, ignoring case', () => {
    expect(findMatches(pages, 'sorento')).toEqual([
      { page: 1, start: 0, end: 7 },
      { page: 1, start: 14, end: 21 },
      { page: 3, start: 14, end: 21 },
    ]);
  });

  it('matches across items and across a line break', () => {
    expect(findMatches(pages, 'sorento sdn')).toEqual([
      { page: 3, start: 14, end: 25 },
    ]);
    expect(findMatches(pages, 'for sorento')).toHaveLength(1);
  });

  it('finds nothing for an empty or blank query', () => {
    expect(findMatches(pages, '')).toEqual([]);
    expect(findMatches(pages, '  ')).toEqual([]);
  });

  it('does not overlap matches', () => {
    expect(findMatches([page('aaaa')], 'aa')).toEqual([
      { page: 1, start: 0, end: 2 },
      { page: 1, start: 2, end: 4 },
    ]);
  });
});

describe('matchSegments', () => {
  it('maps a match back to the slice of each item it covers', () => {
    const index = page('Quotation for ', ['SORENTO', true], 'Sdn Bhd');
    const [match] = findMatches([index], 'for sorento sdn');
    expect(matchSegments(index, match)).toEqual([
      { item: 0, from: 10, to: 14 },
      { item: 1, from: 0, to: 7 },
      { item: 2, from: 0, to: 3 },
    ]);
  });

  it('keeps a folded whitespace run inside its item', () => {
    const index = page('Total    Amount');
    const [match] = findMatches([index], 'total amount');
    expect(matchSegments(index, match)).toEqual([{ item: 0, from: 0, to: 15 }]);
  });
});

describe('stepMatch', () => {
  it('moves forward and back, wrapping at both ends', () => {
    expect(stepMatch(0, 3, 1)).toBe(1);
    expect(stepMatch(2, 3, 1)).toBe(0);
    expect(stepMatch(0, 3, -1)).toBe(2);
    expect(stepMatch(1, 3, -1)).toBe(0);
  });

  it('stays at -1 with no matches', () => {
    expect(stepMatch(-1, 0, 1)).toBe(-1);
    expect(stepMatch(-1, 0, -1)).toBe(-1);
  });
});

describe('firstMatchFrom', () => {
  const matches = [
    { page: 1, start: 0, end: 1 },
    { page: 3, start: 0, end: 1 },
    { page: 3, start: 5, end: 6 },
  ];

  it('starts from the page being read', () => {
    expect(firstMatchFrom(matches, 1)).toBe(0);
    expect(firstMatchFrom(matches, 2)).toBe(1);
    expect(firstMatchFrom(matches, 3)).toBe(1);
  });

  it('wraps to the first match when none is on or after the page', () => {
    expect(firstMatchFrom(matches, 4)).toBe(0);
  });

  it('is -1 with no matches', () => {
    expect(firstMatchFrom([], 1)).toBe(-1);
  });
});

describe('hasSearchableText', () => {
  it('is false for a scan whose pages carry no text', () => {
    expect(hasSearchableText([page(), page(' ', ['', true])])).toBe(false);
    expect(hasSearchableText([])).toBe(false);
  });

  it('is true once any page has text', () => {
    expect(hasSearchableText([page(), page('Invoice')])).toBe(true);
  });
});

describe('paintHighlights', () => {
  function spans(...strs: string[]) {
    return strs.map((s) => {
      const span = document.createElement('span');
      span.textContent = s;
      return span;
    });
  }

  it('wraps each matched slice and marks the selected one', () => {
    const strs = ['Sorento sofa, sorento chair'];
    const divs = spans(...strs);

    const selected = paintHighlights(divs, strs, [
      { item: 0, from: 0, to: 7, selected: false },
      { item: 0, from: 14, to: 21, selected: true },
    ]);

    const marks = divs[0].querySelectorAll('.highlight');
    expect(Array.from(marks).map((m) => m.textContent)).toEqual([
      'Sorento',
      'sorento',
    ]);
    expect(marks[1]).toHaveClass('selected');
    expect(selected).toBe(marks[1]);
    // The span's text is unchanged, so the layer still selects and copies the same way.
    expect(divs[0].textContent).toBe(strs[0]);
  });

  it('puts spans painted before back to plain text', () => {
    const strs = ['alpha', 'beta'];
    const divs = spans(...strs);
    paintHighlights(divs, strs, [{ item: 0, from: 0, to: 5, selected: true }]);

    const selected = paintHighlights(divs, strs, [
      { item: 1, from: 0, to: 2, selected: false },
    ]);

    expect(divs[0].querySelector('.highlight')).toBeNull();
    expect(divs[0].textContent).toBe('alpha');
    expect(divs[1].querySelector('.highlight')?.textContent).toBe('be');
    expect(selected).toBeNull();
  });
});
