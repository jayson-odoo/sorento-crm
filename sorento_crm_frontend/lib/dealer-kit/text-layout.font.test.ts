/**
 * PRICETAG-DESIGNER-FEEDBACK B1, AC-1.2 and AC-1.3: a run's own font.
 *
 * AC-1.2 `runFace` uses the run's `fontFamily` and `fontSize` (pt) when set, the size as given
 * (no heading factor), else the layer's as today; measured widths use that face.
 * AC-1.3 a laid-out line is as tall as its tallest run; lines without run sizes are unchanged.
 *
 * Blocks are built by hand (not parsed), so these fail on the layout alone. Written test-FIRST.
 */
import { describe, expect, it } from 'vitest';

import type { RichBlock, RichRun } from './rich-text';
import type { TextLayerProps } from './tag-template-types';
import { LAYOUT_PX_PER_MM, TEXT_MM_PER_PT, runFace, textLayerLines } from './text-layout';

type FontRun = RichRun & { fontFamily?: string; fontSize?: number };

const props: TextLayerProps = {
  kind: 'text',
  text: '',
  fontFamily: 'DM Sans',
  fontSize: 7,
  fontWeight: 400,
  color: '#000000',
  align: 'left',
  lineHeight: 1.2,
  letterSpacing: 0,
};

const para = (runs: FontRun[], extra: Partial<RichBlock> = {}): RichBlock => ({
  kind: 'p',
  runs: runs as RichRun[],
  align: null,
  sizeFactor: 1,
  ...extra,
});

/** Every character is as wide as the font's px size, so a run's width shows its size. The
 * font strings asked for are recorded, so the family the measure saw is visible. */
function recordingMeasure() {
  const fonts: string[] = [];
  const measureFor = (font: string) => {
    fonts.push(font);
    const px = Number(/(\d+(?:\.\d+)?)px/.exec(font)?.[1] ?? '0');
    return (text: string) => Array.from(text).length * px;
  };
  return { fonts, measureFor };
}

describe('runFace: the run font (AC-1.2)', () => {
  it('uses the run family and size when set', () => {
    const face = runFace(props, { text: 'B', fontFamily: 'Montserrat', fontSize: 14 } as FontRun, 1);
    expect(face.fontFamily).toBe('Montserrat');
    expect(face.fontSize_mm).toBeCloseTo(14 * TEXT_MM_PER_PT, 10);
  });

  it('uses the run size as given, with no heading factor', () => {
    const face = runFace(props, { text: 'B', fontSize: 14 } as FontRun, 1.4, true);
    expect(face.fontSize_mm).toBeCloseTo(14 * TEXT_MM_PER_PT, 10);
    expect(face.fontFamily).toBe('DM Sans');
  });

  it('falls back to the layer face when the run sets neither', () => {
    const face = runFace(props, { text: 'B' }, 1);
    expect(face.fontFamily).toBe('DM Sans');
    expect(face.fontSize_mm).toBeCloseTo(7 * TEXT_MM_PER_PT, 10);
    const heading = runFace(props, { text: 'B' }, 1.4);
    expect(heading.fontSize_mm).toBeCloseTo(7 * 1.4 * TEXT_MM_PER_PT, 10);
  });

  it('a run family alone keeps the layer size', () => {
    const face = runFace(props, { text: 'B', fontFamily: 'Jost' } as FontRun, 1);
    expect(face.fontFamily).toBe('Jost');
    expect(face.fontSize_mm).toBeCloseTo(7 * TEXT_MM_PER_PT, 10);
  });

  it('measures a run in its own face', () => {
    const { fonts, measureFor } = recordingMeasure();
    const lines = textLayerLines(
      props,
      [para([{ text: 'aa ' }, { text: 'BB', fontFamily: 'Montserrat', fontSize: 14 }])],
      200,
      100,
      measureFor,
    );
    const runs = lines[0];
    const big = runs.find((run) => run.text === 'BB')!;
    const small = runs.find((run) => run.text.startsWith('aa'))!;
    // 2 chars, each as wide as the font size in mm.
    expect(big.width_mm).toBeCloseTo(2 * 14 * TEXT_MM_PER_PT, 6);
    expect(small.width_mm).toBeCloseTo(3 * 7 * TEXT_MM_PER_PT, 6);
    expect(fonts.some((font) => font.includes('Montserrat'))).toBe(true);
    const montserrat = fonts.find((font) => font.includes('Montserrat'))!;
    expect(montserrat).toContain(`${14 * TEXT_MM_PER_PT * LAYOUT_PX_PER_MM}px`);
  });
});

describe('rich layout: line height follows the tallest run (AC-1.3)', () => {
  it('a line holding a 14pt run in a 7pt layer is taller than a 7pt line', () => {
    const { measureFor } = recordingMeasure();
    const lines = textLayerLines(
      props,
      [para([{ text: 'a ' }, { text: 'B', fontSize: 14 }]), para([{ text: 'c' }])],
      200,
      100,
      measureFor,
    );
    expect(lines).toHaveLength(2);
    const tall = 1.2 * 14 * TEXT_MM_PER_PT;
    const plain = 1.2 * 7 * TEXT_MM_PER_PT;
    for (const run of lines[0]) expect(run.lineHeight_mm).toBeCloseTo(tall, 6);
    expect(lines[1][0].lineHeight_mm).toBeCloseTo(plain, 6);
    expect(lines[0][0].lineHeight_mm).toBeGreaterThan(lines[1][0].lineHeight_mm);
    // The next line starts below the tall one.
    expect(lines[1][0].y_mm).toBeCloseTo(tall, 6);
  });

  it('only the line holding the big run grows when a paragraph wraps', () => {
    const { measureFor } = recordingMeasure();
    // 7pt chars are 2.45 mm; a 20 mm box holds about 8 of them per line.
    const lines = textLayerLines(
      props,
      [para([{ text: 'aaaa bbbb cccc ' }, { text: 'D', fontSize: 14 }])],
      20,
      100,
      measureFor,
    );
    expect(lines.length).toBeGreaterThan(1);
    const last = lines[lines.length - 1];
    expect(last.some((run) => run.text === 'D')).toBe(true);
    expect(lines[0][0].lineHeight_mm).toBeCloseTo(1.2 * 7 * TEXT_MM_PER_PT, 6);
    expect(last[0].lineHeight_mm).toBeCloseTo(1.2 * 14 * TEXT_MM_PER_PT, 6);
  });

  it('lines without run sizes are unchanged', () => {
    const { measureFor } = recordingMeasure();
    const lines = textLayerLines(props, [para([{ text: 'a' }]), para([{ text: 'b' }])], 200, 100, measureFor);
    const plain = 1.2 * 7 * TEXT_MM_PER_PT;
    expect(lines[0][0].lineHeight_mm).toBeCloseTo(plain, 6);
    expect(lines[1][0].y_mm).toBeCloseTo(plain, 6);
  });
});
