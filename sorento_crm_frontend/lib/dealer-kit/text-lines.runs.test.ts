/**
 * PRICETAG-COMBO-FORMAT AC-15: `textLayerLines` takes the parsed blocks and breaks a line that
 * mixes bold and normal text at the word measured in each run's OWN face. One function serves the
 * canvas and the print page.
 *
 * Written test-FIRST. Contract read literally: "`textLayerLines` accepts blocks and returns lines
 * of runs measured per run face". So the second argument is the `RichBlock[]` from
 * `parseRichText`, and each returned line is an array of runs carrying `text` (and `bold`).
 *
 * The face is observed through the canvas context's `font` string (a stand-in `getContext` makes
 * a bold glyph twice as wide as a regular one), so the test does not depend on how the
 * implementation hands a face to its measure.
 *
 * KILL: measure every run with the regular face -> the break test goes red.
 */
import { beforeAll, describe, expect, it } from 'vitest';

import type { TextLayerProps } from './tag-template-types';
import { textLayerLines } from './text-layout';
import { parseRichText } from './rich-text';

const props: TextLayerProps = {
  kind: 'text',
  text: '',
  fontFamily: 'DM Sans',
  fontSize: 10,
  fontWeight: 400,
  color: '#000000',
  align: 'left',
  lineHeight: 1.2,
  letterSpacing: 0,
};

const REGULAR_EM = 5;
const BOLD_EM = 10;

beforeAll(() => {
  const context = {
    font: '',
    measureText(text: string) {
      const bold = /(^|\s)(bold|[6-9]00)(\s|$)/.test(this.font);
      return { width: text.length * (bold ? BOLD_EM : REGULAR_EM) };
    },
  };
  HTMLCanvasElement.prototype.getContext = (() => context) as never;
});

// px width of the box: the bold word (10 chars x 10) fits at 120, the whole line (100 + 50) does not.
// LAYOUT_PX_PER_MM = 96 / 25.4, so 32 mm is 120.9 px.
const WIDTH_MM = 32;
const HEIGHT_MM = 40;

type Line = Array<{ text: string; bold?: boolean }>;
const textOf = (line: Line) => line.map((run) => run.text).join('');

function lines(html: string): Line[] {
  return textLayerLines(props, parseRichText(html) as never, WIDTH_MM, HEIGHT_MM) as unknown as Line[];
}

describe('textLayerLines with runs (AC-15)', () => {
  it('AC-15: "**SRTBF11416** (CABINET)" breaks after the bold word, because the bold face is wider', () => {
    // Measured all-regular the line is 20 chars x 5 = 100 px and stays on ONE line.
    const result = lines('<p><strong>SRTBF11416</strong> (CABINET)</p>');
    expect(result.map((line) => textOf(line).trim())).toEqual(['SRTBF11416', '(CABINET)']);
    expect(result[0].some((run) => run.bold)).toBe(true);
    expect(result[1].some((run) => run.bold)).toBeFalsy();
  });

  it('AC-15: the same text with no bold stays on one line', () => {
    const result = lines('<p>SRTBF11416 (CABINET)</p>');
    expect(result).toHaveLength(1);
    expect(textOf(result[0])).toBe('SRTBF11416 (CABINET)');
  });

  it('AC-15: the canvas caller and the print caller get equal line lists', () => {
    // Both call the one function with the same arguments; asserting equality of two calls pins
    // that the result is deterministic and carries no caller-specific state.
    const html = '<p><strong>SRTBF11416</strong> (CABINET)</p><p>L400xW345xH390mm</p>';
    const canvasLines = textLayerLines(props, parseRichText(html) as never, WIDTH_MM, HEIGHT_MM);
    const printLines = textLayerLines(props, parseRichText(html) as never, WIDTH_MM, HEIGHT_MM);
    expect(printLines).toEqual(canvasLines);
    expect((canvasLines as unknown[]).length).toBeGreaterThanOrEqual(3);
  });
});
