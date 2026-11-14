/**
 * PRICETAG-DESIGNER-FEEDBACK B1, AC-1.1: `parseRichText` reads a span's `font-family` and
 * `font-size` (pt) into the run as `fontFamily` / `fontSize`, and never merges runs whose font
 * fields differ. Written test-FIRST.
 */
import { describe, expect, it } from 'vitest';

import { parseRichText, type RichRun } from './rich-text';

type FontRun = RichRun & { fontFamily?: string | null; fontSize?: number | null };

const runsOf = (html: string) => parseRichText(html)[0].runs as FontRun[];

describe('parseRichText: font per word (AC-1.1)', () => {
  it('reads font-family and font-size (pt) from a span into the run', () => {
    const runs = runsOf('<p>A <span style="font-family: Montserrat; font-size: 14pt">B</span></p>');
    expect(runs.map((run) => run.text)).toEqual(['A ', 'B']);
    expect(runs[0].fontFamily ?? null).toBeNull();
    expect(runs[0].fontSize ?? null).toBeNull();
    expect(runs[1].fontFamily).toBe('Montserrat');
    expect(runs[1].fontSize).toBe(14);
  });

  it('reads either property alone', () => {
    const family = runsOf('<p><span style="font-family: Jost">B</span></p>');
    expect(family[0].fontFamily).toBe('Jost');
    expect(family[0].fontSize ?? null).toBeNull();

    const size = runsOf('<p><span style="font-size: 9pt">B</span></p>');
    expect(size[0].fontSize).toBe(9);
    expect(size[0].fontFamily ?? null).toBeNull();
  });

  it('keeps colour beside the font fields', () => {
    const runs = runsOf('<p><span style="color: #ff0000; font-family: Montserrat; font-size: 14pt">B</span></p>');
    expect(runs[0]).toMatchObject({ text: 'B', color: '#ff0000', fontFamily: 'Montserrat', fontSize: 14 });
  });

  it('never merges runs with different families', () => {
    const runs = runsOf(
      '<p><span style="font-family: Montserrat">A</span><span style="font-family: Jost">B</span></p>',
    );
    expect(runs.map((run) => [run.text, run.fontFamily])).toEqual([
      ['A', 'Montserrat'],
      ['B', 'Jost'],
    ]);
  });

  it('never merges runs with different sizes, or a sized run with plain text', () => {
    const runs = runsOf('<p><span style="font-size: 14pt">A</span><span style="font-size: 10pt">B</span>C</p>');
    expect(runs.map((run) => [run.text, run.fontSize ?? null])).toEqual([
      ['A', 14],
      ['B', 10],
      ['C', null],
    ]);
  });
});
