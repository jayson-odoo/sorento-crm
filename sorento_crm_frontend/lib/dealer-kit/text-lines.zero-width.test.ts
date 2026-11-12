/**
 * MAIN-RED-TAGSHEET review round: "the line has started" is ONE test in `richLayerLines`.
 *
 * A measured word can be 0 wide (a zero-width space, U+200B, is not whitespace to the tokenizer).
 * If the space after it joins the line (the line holds a piece) but its width and the overflow
 * check still read `lineWidth > 0`, the next word lands on the same line uncounted and the line
 * runs past the box. Every line must fit its box.
 */
import { describe, expect, it } from 'vitest';

import type { TextLayerProps } from './tag-template-types';
import { parseRichText } from './rich-text';
import { LAYOUT_PX_PER_MM, textLayerLines } from './text-layout';

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

/** 10 px per character, a zero-width space 0 px. */
const measureFor = () => (text: string) => Array.from(text).filter((ch) => ch !== '​').length * 10;

describe('rich text layout: a zero-width first word (MAIN-RED-TAGSHEET)', () => {
  it('the next word wraps instead of running past the box', () => {
    // Box 12 mm = ~45 px: "​" (0) + " " (10) + "bbbb" (40) = 50 px does not fit.
    const widthMm = 12;
    const lines = textLayerLines(props, parseRichText('<p>​ bbbb</p>'), widthMm, 120, measureFor);
    for (const line of lines) {
      const used = line.reduce((sum, run) => sum + run.width_mm, 0);
      expect(used * LAYOUT_PX_PER_MM, line.map((run) => run.text).join('')).toBeLessThanOrEqual(
        widthMm * LAYOUT_PX_PER_MM,
      );
    }
    expect(lines.map((line) => line.map((run) => run.text).join(''))).toEqual(['​', 'bbbb']);
  });
});
