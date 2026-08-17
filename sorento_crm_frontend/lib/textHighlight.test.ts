import { describe, expect, it } from 'vitest';

import { escapeRegExp, splitHighlightSegments } from './textHighlight';

describe('escapeRegExp', () => {
  it('neutralises every regex metacharacter', () => {
    expect(escapeRegExp('a.b*c+d?e^f$g{h}i(j)k|l[m]n\\o')).toBe(
      'a\\.b\\*c\\+d\\?e\\^f\\$g\\{h\\}i\\(j\\)k\\|l\\[m\\]n\\\\o',
    );
  });
});

describe('splitHighlightSegments', () => {
  it('marks every case-insensitive occurrence', () => {
    expect(splitHighlightSegments('Order the order', 'ORDER')).toEqual([
      { text: 'Order', match: true },
      { text: ' the ', match: false },
      { text: 'order', match: true },
    ]);
  });

  it('returns the text untouched when the term is empty', () => {
    expect(splitHighlightSegments('hello', '   ')).toEqual([{ text: 'hello', match: false }]);
  });

  it('returns nothing for empty text', () => {
    expect(splitHighlightSegments('', 'x')).toEqual([]);
  });

  it('treats a regex metacharacter as a literal instead of throwing', () => {
    expect(() => splitHighlightSegments('cost is 5 (five)', '(')).not.toThrow();
    expect(splitHighlightSegments('cost is 5 (five)', '(')).toEqual([
      { text: 'cost is 5 ', match: false },
      { text: '(', match: true },
      { text: 'five)', match: false },
    ]);
  });

  it('does not let "." match every character', () => {
    expect(splitHighlightSegments('abc.def', '.')).toEqual([
      { text: 'abc', match: false },
      { text: '.', match: true },
      { text: 'def', match: false },
    ]);
  });

  it('keeps a trailing match at the end of the string', () => {
    expect(splitHighlightSegments('find me', 'me')).toEqual([
      { text: 'find ', match: false },
      { text: 'me', match: true },
    ]);
  });
});
