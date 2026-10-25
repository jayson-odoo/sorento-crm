/**
 * Text layer layout shared by the canvas and the print page
 * (PRICETAG-BARCODE-MATCH).
 *
 * The owner saw a product title cut to "SRTWT914SS-GM-" in the request
 * preview while the canvas showed more of it: the canvas let Konva wrap the
 * text, the print page let the browser wrap it, at a different font size
 * (0.35 vs 0.3528 mm per pt), a different letter-spacing unit (0.1 mm vs
 * 1 px), a different fallback face and a different bold threshold.
 *
 * Now ONE function breaks the lines and both surfaces draw exactly those
 * lines. The rule is the one the canvas already used - Konva's own word wrap -
 * so the parity block below runs real Konva against it.
 */
import Konva from 'konva';
import { describe, expect, it } from 'vitest';

import type { TextLayerProps } from './tag-template-types';
import {
  DEFAULT_TEXT_FONT_FAMILY,
  LAYOUT_PX_PER_MM,
  LETTER_SPACING_MM_PER_UNIT,
  TEXT_MM_PER_PT,
  canvasFont,
  canvasMeasure,
  textFace,
  textLayerLines,
  wrapTextLines,
} from './text-layout';

function textProps(overrides: Partial<TextLayerProps> = {}): TextLayerProps {
  return {
    kind: 'text',
    text: '',
    fontFamily: 'DM Sans',
    fontSize: 12,
    fontWeight: 400,
    color: '#000000',
    align: 'left',
    lineHeight: 1.2,
    letterSpacing: 0,
    ...overrides,
  };
}

/** A fake monospace measure: every character is `w` wide. */
const mono =
  (w: number) =>
  (s: string): number =>
    s.length * w;

describe('units: one figure for the canvas and the print page', () => {
  it('sizes type at the canvas figure, 0.35 mm per point', () => {
    expect(TEXT_MM_PER_PT).toBe(0.35);
    expect(textFace(textProps({ fontSize: 10 })).fontSize_mm).toBeCloseTo(3.5, 10);
  });

  it('spaces letters at the canvas figure, 0.1 mm per unit', () => {
    expect(LETTER_SPACING_MM_PER_UNIT).toBe(0.1);
    expect(textFace(textProps({ letterSpacing: 2 })).letterSpacing_mm).toBeCloseTo(0.2, 10);
  });

  it('falls back to DM Sans when the layer names no face, on both surfaces', () => {
    expect(DEFAULT_TEXT_FONT_FAMILY).toBe('DM Sans, sans-serif');
    expect(textFace(textProps({ fontFamily: '' })).fontFamily).toBe('DM Sans, sans-serif');
    expect(textFace(textProps({ fontFamily: 'Jost' })).fontFamily).toBe('Jost');
  });

  it('carries the exact weight and italic, not just bold at 600+', () => {
    expect(textFace(textProps({ fontWeight: 500 })).fontStyle).toBe('500');
    expect(textFace(textProps({ fontWeight: 700, italic: true })).fontStyle).toBe('italic 700');
  });

  it('builds the canvas font string the way Konva does (families with a space quoted)', () => {
    const face = textFace(textProps({ fontFamily: 'Bebas Neue, sans-serif', fontSize: 10 }));
    expect(canvasFont(face, 4)).toBe('400 normal 14px "Bebas Neue", sans-serif');
  });
});

describe('wrapTextLines: the word-wrap rule', () => {
  const box = { maxWidth: 100, maxHeight: 1000, lineHeight: 12, letterSpacing: 0 };

  it('keeps a line that fits as it is', () => {
    expect(wrapTextLines('short', box, mono(10))).toEqual(['short']);
  });

  it('breaks after the last hyphen that fits, the way a long product code wraps', () => {
    // 10 per char, 100 wide: ten characters fit, the tenth is the hyphen.
    expect(wrapTextLines('ZZTWT9-GM-WH600', box, mono(10))).toEqual(['ZZTWT9-GM-', 'WH600']);
  });

  it('breaks at a space and drops the space', () => {
    expect(wrapTextLines('aaaa bbbb cccc', box, mono(10))).toEqual(['aaaa bbbb', 'cccc']);
  });

  it('breaks inside a word with no space or hyphen to break at', () => {
    expect(wrapTextLines('abcdefghijklmnop', box, mono(10))).toEqual(['abcdefghij', 'klmnop']);
  });

  it('keeps hard line breaks', () => {
    expect(wrapTextLines('one\ntwo', box, mono(10))).toEqual(['one', 'two']);
  });

  it('counts letter spacing per character, as Konva does', () => {
    // 9 per char + 1 spacing = 10 per char.
    expect(wrapTextLines('abcdefghijkl', { ...box, letterSpacing: 1 }, mono(9))).toEqual([
      'abcdefghij',
      'kl',
    ]);
  });

  it('draws only the lines that fit the height, and always the first one', () => {
    const text = 'aaaa bbbb cccc dddd';
    expect(wrapTextLines(text, { ...box, maxHeight: 24 }, mono(10))).toEqual(['aaaa bbbb', 'cccc dddd']);
    expect(wrapTextLines('aaaa bbbb cccc dddd eeee', { ...box, maxHeight: 24 }, mono(10))).toEqual([
      'aaaa bbbb',
      'cccc dddd',
    ]);
    expect(wrapTextLines(text, { ...box, maxHeight: 5 }, mono(10))).toEqual(['aaaa bbbb']);
  });

  it('leaves headroom when asked, so a line never sits on the very edge', () => {
    expect(wrapTextLines('aaaaaaaaaa', { ...box, headroom: 0.005 }, mono(10))).toEqual([
      'aaaaaaaaa',
      'a',
    ]);
  });
});

describe('wrapTextLines matches Konva word wrap (the canvas rule before this change)', () => {
  const texts = [
    'ZZTWT914SS-GM-WH 600MM TOWEL RAIL',
    'One two three four five six seven eight nine ten eleven twelve',
    'Line one\nLine two is a lot longer than the box is wide, by far',
    'NOBREAKSATALLINTHISVERYLONGWORDTHATKEEPSONGOING',
    'A-B-C-D-E-F-G-H-I-J-K-L-M-N-O-P-Q-R-S-T',
    '  leading and trailing spaces  ',
  ];
  const boxes = [
    { width: 60, height: 200 },
    { width: 110, height: 30 },
    { width: 200, height: 10 },
    { width: 140, height: 200 },
  ];
  const faces = [
    { fontStyle: '400', letterSpacing: 0 },
    { fontStyle: 'italic 700', letterSpacing: 1.5 },
  ];

  for (const text of texts) {
    for (const b of boxes) {
      for (const f of faces) {
        it(`${JSON.stringify(text).slice(0, 28)} in ${b.width}x${b.height}, ${f.fontStyle}/${f.letterSpacing}`, () => {
          const fontSize = 12;
          const lineHeight = 1.2;
          const node = new Konva.Text({
            text,
            width: b.width,
            height: b.height,
            fontSize,
            fontFamily: 'DM Sans, sans-serif',
            fontStyle: f.fontStyle,
            letterSpacing: f.letterSpacing,
            lineHeight,
            wrap: 'word',
          });
          const konvaLines = (node as unknown as { textArr: { text: string }[] }).textArr.map(
            (l) => l.text,
          );
          const face = {
            fontFamily: 'DM Sans, sans-serif',
            fontStyle: f.fontStyle,
            fontSize_mm: fontSize,
            letterSpacing_mm: f.letterSpacing,
          };
          const measure = canvasMeasure(canvasFont(face, 1));
          expect(measure).not.toBeNull();
          expect(
            wrapTextLines(
              text,
              {
                maxWidth: b.width,
                maxHeight: b.height,
                lineHeight: lineHeight * fontSize,
                letterSpacing: f.letterSpacing,
              },
              measure!,
            ),
          ).toEqual(konvaLines);
        });
      }
    }
  }
});

describe('textLayerLines: one answer for a layer, whatever the zoom', () => {
  it('breaks a layer in mm of its box, inside its padding, at the print scale', () => {
    const props = textProps({
      fontSize: 10,
      padding: { top: 1, right: 2, bottom: 1, left: 2 },
    });
    const measure = mono(10);
    const lines = textLayerLines(props, 'aaaa bbbb cccc', 30, 20, measure);
    const px = LAYOUT_PX_PER_MM;
    expect(lines).toEqual(
      wrapTextLines(
        'aaaa bbbb cccc',
        {
          maxWidth: (30 - 4) * px,
          maxHeight: (20 - 2) * px,
          lineHeight: 1.2 * 10 * TEXT_MM_PER_PT * px,
          letterSpacing: 0,
          headroom: 0.005,
        },
        measure,
      ),
    );
  });

  it('cuts a long hyphenated code the same way on every surface: only the lines that fit', () => {
    // One line tall: the canvas and the print page both show the first line
    // only - never one of them the whole code and the other a stub.
    const props = textProps({ fontSize: 10, lineHeight: 1.2 });
    const oneLine = 1.2 * 10 * TEXT_MM_PER_PT + 0.5;
    const lines = textLayerLines(props, 'ZZTWT914SS-GM-WH600', 30, oneLine);
    expect(lines.length).toBe(1);
    const twoLines = textLayerLines(props, 'ZZTWT914SS-GM-WH600', 30, oneLine * 2);
    expect(twoLines.join('')).toBe('ZZTWT914SS-GM-WH600');
  });
});
