/**
 * PRICETAG-COMBO-FORMAT S3: one parser turns the stored description into blocks of runs
 * (AC-13, AC-14, AC-20). Written test-FIRST: `lib/dealer-kit/rich-text.ts` does not exist yet, so
 * every test here is red on the missing module.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';

import { isRich, parseRichText, richPlainText } from './rich-text';
import { E1_BOLD_WORDS, E1_DIMENSIONS, E1_GREY, E1_HTML, E1_PLAIN } from './rich-text.e1.fixture';

afterEach(() => vi.restoreAllMocks());

describe('parseRichText (AC-13)', () => {
  it('AC-13: E1 is 12 paragraphs; bold runs are exactly the six codes; dimension lines are grey', () => {
    const blocks = parseRichText(E1_HTML);
    expect(blocks).toHaveLength(12);
    expect(blocks.every((block) => block.kind === 'p')).toBe(true);

    const bold = blocks.flatMap((block) => block.runs).filter((run) => run.bold);
    expect(bold.map((run) => run.text)).toEqual(E1_BOLD_WORDS);

    const dimensionBlocks = blocks.filter((block) =>
      E1_DIMENSIONS.includes(block.runs.map((run) => run.text).join('')),
    );
    expect(dimensionBlocks).toHaveLength(6);
    for (const block of dimensionBlocks) {
      expect(block.runs.every((run) => run.color === E1_GREY)).toBe(true);
    }
  });

  it('AC-13: every mark becomes a run flag', () => {
    const [block] = parseRichText(
      '<p><strong>b</strong><em>i</em><u>u</u><s>s</s><code>c</code>' +
        '<mark style="background-color: #fde68a">h</mark></p>',
    );
    const byText = Object.fromEntries(block.runs.map((run) => [run.text, run]));
    expect(byText.b.bold).toBe(true);
    expect(byText.i.italic).toBe(true);
    expect(byText.u.underline).toBe(true);
    expect(byText.s.strike).toBe(true);
    expect(byText.c.code).toBe(true);
    expect(byText.h.highlight).toBe('#fde68a');
  });

  it('AC-13: h1 / h2 / h3 are bold blocks with size factors 1.4 / 1.2 / 1.1; a paragraph is 1', () => {
    const blocks = parseRichText('<h1>A</h1><h2>B</h2><h3>C</h3><p>D</p>');
    expect(blocks.map((block) => block.kind)).toEqual(['h1', 'h2', 'h3', 'p']);
    expect(blocks.map((block) => block.sizeFactor)).toEqual([1.4, 1.2, 1.1, 1]);
    expect(blocks.slice(0, 3).every((block) => block.bold === true)).toBe(true);
    expect(blocks[3].bold).toBeFalsy();
  });

  it('AC-13: list items carry a bullet or a number; numbering restarts per list', () => {
    const blocks = parseRichText(
      '<ul><li>a</li><li>b</li></ul><ol><li>c</li></ol><ol><li>d</li></ol>',
    );
    expect(blocks.every((block) => block.kind === 'li')).toBe(true);
    expect(blocks.map((block) => block.marker)).toEqual(['•', '•', '1.', '1.']);
  });

  it('AC-13: the second item of one numbered list is "2."', () => {
    const blocks = parseRichText('<ol><li>c</li><li>d</li></ol>');
    expect(blocks.map((block) => block.marker)).toEqual(['1.', '2.']);
  });

  it('AC-13: a nested list is level 2; an item the editor wraps in a paragraph is still one item', () => {
    const nested = parseRichText('<ul><li>a<ul><li>b</li></ul></li></ul>');
    expect(nested.map((block) => block.runs.map((run) => run.text).join(''))).toEqual(['a', 'b']);
    expect(nested[0].level).toBe(1);
    expect(nested[1].level).toBe(2);

    const wrapped = parseRichText('<ul><li><p>a</p></li></ul>');
    expect(wrapped).toHaveLength(1);
    expect(wrapped[0].kind).toBe('li');
    expect(wrapped[0].runs.map((run) => run.text).join('')).toBe('a');
  });

  it('AC-13: a blockquote is a quote block', () => {
    const [block] = parseRichText('<blockquote><p>q</p></blockquote>');
    expect(block.kind).toBe('quote');
    expect(block.runs.map((run) => run.text).join('')).toBe('q');
  });

  it('AC-13: alignment is per block; unset alignment is null so the layer decides', () => {
    const [centred, plain] = parseRichText('<p style="text-align: center">a</p><p>b</p>');
    expect(centred.align).toBe('center');
    expect(plain.align ?? null).toBeNull();
  });

  it('AC-13: plain text is one paragraph per line with no marks', () => {
    const blocks = parseRichText('a\nb');
    expect(blocks.map((block) => block.kind)).toEqual(['p', 'p']);
    expect(blocks.map((block) => block.runs.map((run) => run.text).join(''))).toEqual(['a', 'b']);
    for (const run of blocks.flatMap((block) => block.runs)) {
      expect(run.bold).toBeFalsy();
      expect(run.italic).toBeFalsy();
      expect(run.color ?? null).toBeNull();
    }
  });

  it('AC-13: empty and null give no blocks', () => {
    expect(parseRichText(null)).toEqual([]);
    expect(parseRichText('')).toEqual([]);
  });
});

describe('parseRichText is safe (AC-14)', () => {
  it('AC-14: an invalid colour draws in the layer colour (run colour null)', () => {
    for (const style of ['color: javascript:x', 'color: red;}', 'color: url(x)', 'color: #12345g']) {
      const [block] = parseRichText(`<p><span style="${style}">a</span></p>`);
      expect(block.runs[0].text).toBe('a');
      expect(block.runs[0].color ?? null, style).toBeNull();
    }
  });

  it('AC-14: hex and rgb colours are kept', () => {
    const [block] = parseRichText(
      '<p><span style="color: #abc">a</span><span style="color: rgb(1, 2, 3)">b</span></p>',
    );
    expect(block.runs.map((run) => run.color)).toEqual(['#abc', 'rgb(1, 2, 3)']);
  });

  it('AC-14: an <img onerror> typed as text stays literal text, and innerHTML is never written', () => {
    // KILL: parse by assigning innerHTML -> the setter spy below fires.
    const descriptor = Object.getOwnPropertyDescriptor(Element.prototype, 'innerHTML');
    expect(descriptor?.set).toBeTypeOf('function');
    const writes: unknown[] = [];
    Object.defineProperty(Element.prototype, 'innerHTML', {
      configurable: true,
      get: descriptor!.get,
      set(value) {
        writes.push(value);
        descriptor!.set!.call(this, value);
      },
    });
    try {
      const blocks = parseRichText('<p>&lt;img src=x onerror=alert(1)&gt;</p>');
      const text = blocks.flatMap((block) => block.runs).map((run) => run.text).join('');
      expect(text).toBe('<img src=x onerror=alert(1)>');
      expect(writes).toEqual([]);
    } finally {
      Object.defineProperty(Element.prototype, 'innerHTML', descriptor!);
    }
  });
});

describe('old and odd data (AC-20)', () => {
  it('AC-20: a link is its text only', () => {
    const [block] = parseRichText('<p>see <a href="javascript:alert(1)">here</a></p>');
    expect(block.runs.map((run) => run.text).join('')).toBe('see here');
  });

  it('AC-20: an unknown leftover tag is its text', () => {
    const blocks = parseRichText('<div>x</div>');
    expect(blocks.flatMap((block) => block.runs).map((run) => run.text).join('')).toBe('x');
  });
});

describe('isRich and richPlainText', () => {
  it('isRich: a value is rich iff it starts with an allowed block tag', () => {
    expect(isRich('<p>a</p>')).toBe(true);
    expect(isRich('  <h1>a</h1>')).toBe(true);
    expect(isRich('<UL><li>a</li></UL>')).toBe(true);
    expect(isRich('plain <p>a</p>')).toBe(false);
    expect(isRich('<pre>a</pre>')).toBe(false);
    expect(isRich('')).toBe(false);
    expect(isRich(null)).toBe(false);
  });

  it('richPlainText: E1 is the lines joined by newlines, no markup', () => {
    expect(richPlainText(E1_HTML)).toBe(E1_PLAIN);
  });

  it('richPlainText: bullets, numbers (restarting per list), nesting and plain input', () => {
    expect(richPlainText('<ul><li>a</li><li>b</li></ul>')).toBe('• a\n• b');
    expect(richPlainText('<ol><li>a</li><li>b</li></ol><ol><li>c</li></ol>')).toBe('1. a\n2. b\n1. c');
    expect(richPlainText('<ul><li>a<ul><li>b</li></ul></li></ul>')).toBe('• a\n  • b');
    expect(richPlainText('plain\ntext')).toBe('plain\ntext');
    expect(richPlainText(null)).toBe('');
  });
});
