/**
 * Konva draws EVERY line `textLayerLines` returns, at any zoom
 * (PRICETAG-BARCODE-MATCH review round 2).
 *
 * The canvas hands Konva the lines with its wrap off, but Konva still drops a
 * line once `current + lineHeight > height`, summed in canvas px. In a box an
 * exact number of lines tall that float sum came out a hair over at some
 * zooms (6 lines in print, 5 on the canvas), so the canvas box height carries
 * a sliver of slack (`canvasTextHeight`): the helper alone decides the count.
 */
import Konva from 'konva';
import { describe, expect, it } from 'vitest';

import type { TextLayerProps } from './tag-template-types';
import { canvasTextHeight, textFace, textLayerLines } from './text-layout';

const props: TextLayerProps = {
  kind: 'text',
  text: '',
  fontFamily: 'DM Sans',
  fontSize: 6,
  fontWeight: 400,
  color: '#000000',
  align: 'left',
  lineHeight: 1,
  letterSpacing: 0,
};

describe('canvas text height: Konva never drops a line the helper kept', () => {
  it('draws all six lines of a box exactly six lines tall, at every zoom', () => {
    const face = textFace(props);
    const text = Array.from({ length: 40 }, () => 'word').join(' ');
    const widthMm = 20;
    const heightMm = 6 * face.fontSize_mm * props.lineHeight; // 12.6mm
    const lines = textLayerLines(props, text, widthMm, heightMm);
    expect(lines).toHaveLength(6);

    for (const scale of [0.75, 1, 1.5, 2, 3, 4.5, 7.5]) {
      const node = new Konva.Text({
        text: lines.join('\n'),
        width: widthMm * scale,
        height: canvasTextHeight(heightMm * scale),
        fontSize: face.fontSize_mm * scale,
        fontFamily: face.fontFamily,
        fontStyle: face.fontStyle,
        letterSpacing: face.letterSpacing_mm * scale,
        lineHeight: props.lineHeight,
        wrap: 'none',
      });
      const drawn = (node as unknown as { textArr: { text: string }[] }).textArr.map((l) => l.text);
      expect(drawn, `scale ${scale}`).toEqual(lines);
    }
  });

  it('adds only a sliver: well under a pixel even on a tall box', () => {
    expect(canvasTextHeight(1000) - 1000).toBeGreaterThan(0);
    expect(canvasTextHeight(1000) - 1000).toBeLessThan(0.01);
  });
});
