/**
 * A text layer breaks into the SAME lines on the canvas and on the print page
 * (PRICETAG-BARCODE-MATCH).
 *
 * Owner, PT-202610-0001: a product title showed cut to "SRTWT914SS-GM-" in
 * the request preview. The canvas let Konva wrap the text and the print page
 * let the browser wrap it, at different font-size and letter-spacing units,
 * so the two broke the same title at different places and the print page's
 * fixed-height box clipped what the canvas still showed.
 *
 * Both now draw the lines `textLayerLines` returns: the canvas hands them to
 * Konva with wrapping off, the print page prints them with wrapping off.
 * `react-konva` is stood in for by a div carrying the props that matter, as
 * in `KonvaTagLayer.barcode.test.tsx`.
 */
import { render } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('konva/lib/Global', () => ({ Konva: { dragButtons: [0, 1] } }));

vi.mock('react-konva', () => {
  const passthrough = (name: string) =>
    function KonvaStandIn(props: Record<string, unknown> & { children?: React.ReactNode }) {
      return (
        <div
          data-konva={name}
          data-text={String(props.text ?? '')}
          data-wrap={String(props.wrap ?? '')}
          data-font-size={String(props.fontSize ?? '')}
          data-font-style={String(props.fontStyle ?? '')}
          data-font-family={String(props.fontFamily ?? '')}
          data-letter-spacing={String(props.letterSpacing ?? '')}
          data-source-text={String(props.sourceText ?? '')}
          data-height={String(props.height ?? '')}
        >
          {props.children}
        </div>
      );
    };
  return {
    Group: passthrough('group'),
    Rect: passthrough('rect'),
    Text: passthrough('text'),
    Image: passthrough('image'),
    Ellipse: passthrough('ellipse'),
    Line: passthrough('line'),
    Path: passthrough('path'),
  };
});

import TagSheetRenderer from '@/app/(public)/c/print/tag-sheet/[downloadId]/components/TagSheetRenderer';
import type { TagLayer, TagSheetDoc, TextLayerProps } from '@/lib/dealer-kit/tag-template-types';
import { canvasTextHeight, textFace, textLayerLines } from '@/lib/dealer-kit/text-layout';
import { KonvaTagLayer } from './KonvaTagLayer';

// Synthetic code with the owner's shape: letters, digits and hyphens.
const TITLE = 'ZZTWT914SS-GM-WH600 TOWEL RAIL';

function textLayer(props: Partial<TextLayerProps>, width_mm = 30, height_mm = 5): TagLayer {
  return {
    id: 'title',
    type: 'text',
    x_mm: 0,
    y_mm: 0,
    width_mm,
    height_mm,
    rotation_deg: 0,
    z_index: 1,
    locked: false,
    visible: true,
    slot_binding: null,
    text_override: null,
    props: {
      kind: 'text',
      text: TITLE,
      fontFamily: 'DM Sans',
      fontSize: 10,
      fontWeight: 700,
      color: '#000000',
      align: 'left',
      lineHeight: 1.2,
      letterSpacing: 1,
      ...props,
    },
  } as TagLayer;
}

function docWith(layer: TagLayer): TagSheetDoc {
  return {
    kind: 'tag_sheet',
    imposition: {
      preset: 'a4_3up',
      page_width_mm: 210,
      page_height_mm: 297,
      bleed_mm: 0,
      gap_mm: 2,
    },
    sheets: [
      {
        id: 's1',
        tags: [
          {
            id: 't1',
            template_id: 'tpl-1',
            request_tag_id: null,
            x_mm: 5,
            y_mm: 5,
            width_mm: 95,
            height_mm: 130,
            layers: [layer],
          },
        ],
      },
    ],
  } as unknown as TagSheetDoc;
}

function canvasText(layer: TagLayer, scale: number): HTMLElement {
  const { container } = render(<KonvaTagLayer layer={layer} scale={scale} />);
  const node = container.querySelector('[data-konva="text"]') as HTMLElement | null;
  expect(node).not.toBeNull();
  return node!;
}

function printText(layer: TagLayer): HTMLElement {
  const { container } = render(
    <TagSheetRenderer doc={docWith(layer)} resolvedData={{}} assets={{}} images={{}} />,
  );
  const node = Array.from(container.querySelectorAll('div')).find(
    (d) => d.childElementCount === 0 && (d.textContent ?? '').startsWith('ZZT'),
  ) as HTMLElement | undefined;
  expect(node).toBeDefined();
  return node!;
}

describe('text layer: canvas and print draw the same lines', () => {
  for (const [label, layer] of [
    ['one line tall (the owner case: the title is cut on BOTH, at the same place)', textLayer({}, 30, 5)],
    ['two lines tall', textLayer({}, 30, 10)],
    ['wide enough for one line', textLayer({}, 90, 5)],
    ['padded, light weight, no letter spacing', textLayer({ fontWeight: 300, letterSpacing: 0, padding: { top: 1, right: 2, bottom: 1, left: 2 } }, 34, 12)],
  ] as const) {
    it(label, () => {
      const expected = textLayerLines(
        layer.props as TextLayerProps,
        TITLE,
        layer.width_mm,
        layer.height_mm,
      ).join('\n');

      // The canvas, at two zooms: same lines, Konva's own wrap off.
      for (const scale of [3, 7.5]) {
        const node = canvasText(layer, scale);
        expect(node.getAttribute('data-text')).toBe(expected);
        expect(node.getAttribute('data-wrap')).toBe('none');
        // The unbroken text rides on the node, for a live resize to re-break.
        expect(node.getAttribute('data-source-text')).toBe(TITLE);
        // Konva's own height cut never undoes the helper's line count.
        if (!layer.props.kind || !('padding' in layer.props) || !layer.props.padding) {
          expect(parseFloat(node.getAttribute('data-height')!)).toBeCloseTo(
            canvasTextHeight(layer.height_mm * scale),
            9,
          );
        }
      }

      // The print page: same lines, the browser's own wrap off.
      const printed = printText(layer);
      expect(printed.textContent).toBe(expected);
      expect(printed.style.whiteSpace).toBe('pre');
    });
  }

  it('sets the same type on both: 0.35 mm per pt, 0.1 mm letter spacing, exact weight, DM Sans fallback', () => {
    const layer = textLayer({ fontFamily: '', fontWeight: 500, italic: true, letterSpacing: 2 }, 60, 20);
    const face = textFace(layer.props as TextLayerProps);

    const node = canvasText(layer, 3);
    expect(parseFloat(node.getAttribute('data-font-size')!)).toBeCloseTo(10 * 0.35 * 3, 6);
    expect(parseFloat(node.getAttribute('data-letter-spacing')!)).toBeCloseTo(2 * 0.1 * 3, 6);
    expect(node.getAttribute('data-font-style')).toBe('italic 500');
    expect(node.getAttribute('data-font-family')).toBe('DM Sans, sans-serif');

    const printed = printText(layer);
    expect(printed.style.fontSize).toBe(`${face.fontSize_mm}mm`);
    expect(printed.style.letterSpacing).toBe(`${face.letterSpacing_mm}mm`);
    expect(printed.style.fontWeight).toBe('500');
    expect(printed.style.fontStyle).toBe('italic');
    // jsdom quotes a family name with a space.
    expect(printed.style.fontFamily.replace(/"/g, '')).toBe('DM Sans, sans-serif');
  });
});
