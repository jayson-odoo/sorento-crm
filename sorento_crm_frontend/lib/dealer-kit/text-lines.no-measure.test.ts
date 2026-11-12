/**
 * MAIN-RED-TAGSHEET: a rich description laid out with NO measure (no canvas: jsdom without the
 * optional `canvas` package, or a server render) keeps the spaces between its words.
 *
 * With no measure every width is 0. `richLayerLines` used "the line has width" to mean "the line
 * has started", so it dropped the space before every word: `<img src=x>` came out `<imgsrc=x>`.
 * The plain-text path returns the hard lines as typed; the rich path must read the same.
 *
 * `measureFor = null` is the no-canvas case, explicitly, so this runs the same on every machine.
 */
import { describe, expect, it } from 'vitest';

import type { TextLayerProps } from './tag-template-types';
import { parseRichText } from './rich-text';
import { textLayerLines } from './text-layout';

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

function lineTexts(html: string): string[] {
  return textLayerLines(props, parseRichText(html), 200, 120, null).map((line) =>
    line.map((run) => run.text).join(''),
  );
}

describe('rich text layout with no measure (MAIN-RED-TAGSHEET)', () => {
  it('keeps the spaces between words in one run', () => {
    expect(lineTexts('<p>&lt;img src=x onerror=alert(1)&gt;</p>')).toEqual([
      '<img src=x onerror=alert(1)>',
    ]);
  });

  it('keeps the space where a bold run meets a plain one', () => {
    expect(lineTexts('<p><strong>SRTBF11416</strong> (CABINET) 600 x 400</p>')).toEqual([
      'SRTBF11416 (CABINET) 600 x 400',
    ]);
  });

  it('keeps each paragraph on its own line, no leading space', () => {
    expect(lineTexts('<p>first line</p><p>  second line</p>')).toEqual(['first line', 'second line']);
  });
});
