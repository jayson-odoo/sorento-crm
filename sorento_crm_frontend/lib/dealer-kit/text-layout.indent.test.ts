/**
 * PRICETAG-DESIGNER-FEEDBACK AC-2.1 to AC-2.4: a description line that starts with spaces keeps
 * them on the tag (owner, 14 Nov: "   L580xW450xH450mm" under "Basin size:" lost its indent).
 *
 * Written test-FIRST. One rule for a hard line start (a new paragraph, a `<br>`, a "\n"): its
 * leading spaces are drawn, so the first word starts right of the indent. A soft wrap (a line
 * that breaks on its own) still drops the space it broke at.
 *
 * The measure is a fake monospace one (every character 5 px in every face), handed in as
 * `measureFor`, so the test runs the same on every machine.
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

const CHAR_PX = 5;
const mono = (s: string) => s.length * CHAR_PX;
const measureFor = () => mono;
const mm = (chars: number) => (chars * CHAR_PX) / LAYOUT_PX_PER_MM;

type Run = { text: string; x_mm: number; width_mm: number; bold?: boolean };
const textOf = (line: Run[]) => line.map((run) => run.text).join('');
const widthOf = (line: Run[]) => line.reduce((sum, run) => sum + run.width_mm, 0);

function rich(html: string, width_mm = 200, height_mm = 120): Run[][] {
  return textLayerLines(props, parseRichText(html), width_mm, height_mm, measureFor) as unknown as Run[][];
}

describe('AC-2.1: a paragraph that starts with spaces keeps them (measured)', () => {
  it('AC-2.1: "   L580xW450xH450mm" in its own paragraph keeps its 3 leading spaces', () => {
    const lines = rich('<p>Basin size:</p><p>   L580xW450xH450mm</p>');
    expect(lines.map(textOf)).toEqual(['Basin size:', '   L580xW450xH450mm']);
    // The 3 spaces take their width: the line is 3 + 16 characters wide.
    expect(widthOf(lines[1])).toBeCloseTo(mm(3 + 16), 6);
  });

  it('AC-2.1: the first word after the indent starts right of x=0, by 3 spaces', () => {
    const lines = rich('<p>Basin size:</p><p>   <strong>L580xW450xH450mm</strong></p>');
    const word = lines[1].find((run) => run.text.includes('L580'));
    expect(word).toBeDefined();
    expect(word!.bold).toBe(true);
    expect(word!.x_mm).toBeCloseTo(mm(3), 6);
  });

  it('AC-2.1: an indent written as &nbsp; is kept the same way', () => {
    const lines = rich('<p>Basin size:</p><p>&nbsp;&nbsp;&nbsp;L580xW450xH450mm</p>');
    expect(lines).toHaveLength(2);
    expect(textOf(lines[1]).replace(/ /g, ' ')).toBe('   L580xW450xH450mm');
    expect(widthOf(lines[1])).toBeCloseTo(mm(3 + 16), 6);
  });
});

describe('AC-2.1: no measure (no canvas)', () => {
  it('AC-2.1: the indented paragraph text begins with "   "', () => {
    const lines = textLayerLines(
      props,
      parseRichText('<p>Basin size:</p><p>   L580xW450xH450mm</p>'),
      200,
      120,
      null,
    ) as unknown as Run[][];
    expect(lines.map(textOf)).toEqual(['Basin size:', '   L580xW450xH450mm']);
  });
});

describe('AC-2.2: spaces right after a hard break are kept', () => {
  it('AC-2.2: after a <br>, measured', () => {
    const lines = rich('<p>Basin size:<br>   L580xW450xH450mm</p>');
    expect(lines.map(textOf)).toEqual(['Basin size:', '   L580xW450xH450mm']);
    expect(widthOf(lines[1])).toBeCloseTo(mm(3 + 16), 6);
  });

  it('AC-2.2: after a <br>, no measure', () => {
    const lines = textLayerLines(
      props,
      parseRichText('<p>Basin size:<br>   L580xW450xH450mm</p>'),
      200,
      120,
      null,
    ) as unknown as Run[][];
    expect(lines.map(textOf)).toEqual(['Basin size:', '   L580xW450xH450mm']);
  });
});

describe('AC-2.3: a soft wrap still drops its space; spaces between words are unchanged', () => {
  // 16 mm is 60.5 px: "aaaa  bbbb" (50 px) fits, "aaaa  bbbb cccc" (75 px) does not.
  it('AC-2.3: the wrapped line starts with its word, not a space', () => {
    const lines = rich('<p>aaaa  bbbb cccc</p>', 16, 40);
    expect(lines.map(textOf)).toEqual(['aaaa  bbbb', 'cccc']);
    expect(lines[1][0].x_mm).toBeCloseTo(0, 6);
  });

  it('AC-2.3: an indented paragraph keeps its indent on line 1 only, the wrap drops the space', () => {
    // "  aaaa bbbb" is 55 px and fits; "cccc" wraps.
    const lines = rich('<p>  aaaa bbbb cccc</p>', 16, 40);
    expect(lines.map(textOf)).toEqual(['  aaaa bbbb', 'cccc']);
  });
});

describe('AC-2.4: plain (non-rich) text keeps leading spaces after "\\n"', () => {
  it('AC-2.4: measured', () => {
    expect(textLayerLines(props, 'Basin size:\n   L580xW450xH450mm', 200, 120, mono)).toEqual([
      'Basin size:',
      '   L580xW450xH450mm',
    ]);
  });

  it('AC-2.4: no measure', () => {
    expect(textLayerLines(props, 'Basin size:\n   L580xW450xH450mm', 200, 120, null)).toEqual([
      'Basin size:',
      '   L580xW450xH450mm',
    ]);
  });

  it('AC-2.3 (plain): a soft wrap drops its space', () => {
    expect(textLayerLines(props, 'aaaa  bbbb cccc', 16, 40, mono)).toEqual(['aaaa  bbbb', 'cccc']);
  });
});
