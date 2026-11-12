/**
 * PRICETAG-HEADER-DRAG round 2 render parity: a RESIZED, FILLED, rounded, padded header prints on the
 * print sheet / PDF exactly as the designer canvas draws it (owner rule 4 Nov: render accuracy), on a
 * legacy box and a designed-card box.
 */

import { act, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('konva/lib/Global', () => ({ Konva: { dragButtons: [0, 1] } }));
vi.mock('react-konva', () => {
  const passthrough = (name: string) =>
    function KonvaStandIn(props: Record<string, unknown> & { children?: React.ReactNode }) {
      return (
        <div
          data-konva={name}
          data-x={String(props.x ?? 0)}
          data-y={String(props.y ?? 0)}
          data-w={String(props.width ?? '')}
          data-text={String(props.text ?? '')}
          data-fill={String(props.fill ?? '')}
          data-align={String(props.align ?? '')}
          data-h={String(props.height ?? '')}
          data-wrap={String(props.wrap ?? '')}
          data-corner={String(props.cornerRadius ?? '')}
        >
          {props.children}
        </div>
      );
    };
  return {
    Group: passthrough('group'),
    Rect: passthrough('rect'),
    Text: passthrough('text'),
    Path: passthrough('path'),
    Image: passthrough('image'),
    Ellipse: passthrough('ellipse'),
    Line: passthrough('line'),
    Circle: passthrough('circle'),
  };
});

import { accessoryChrome, headerLineCap } from '@/lib/dealer-kit/accessory-box';
import { KonvaTagLayer } from '@/app/(protected)/dealer-kit/tag-templates/components/KonvaTagLayer';
import {
  defaultAccessoriesProps,
  type AccessoriesLayerProps,
  type TagAccessory,
  type TagLayer,
  type TagSheetDoc,
} from '@/lib/dealer-kit/tag-template-types';
import TagSheetRenderer, { type ResolvedLineData } from './TagSheetRenderer';

class StubImage {
  width = 100;
  height = 100;
  onload: (() => void) | null = null;
  set src(_v: string) {
    Promise.resolve().then(() => this.onload?.());
  }
}
beforeEach(() => {
  vi.stubGlobal('Image', StubImage);
});

const TAG_ID = 'tag-1';
const SCALE = 4;
const LIST: TagAccessory[] = [
  {
    kind: 'product',
    id: 'p1',
    name: 'Popup Waste 80mm (w/o Overflow) Brass',
    spec: null,
    image: null,
    code: 'SRTW5000',
    list_price: 68,
  },
];
// Inside the closed-up box of one card (designed card 16 mm tall), so the spot is not pulled in.
const POS = { x_mm: 6.5, y_mm: 14 };
const CARD = {
  width_mm: 38,
  height_mm: 16,
  elements: [{ id: 'n', kind: 'text', field: 'name', x_mm: 1, y_mm: 1, width_mm: 30, height_mm: 4 }],
} as unknown as NonNullable<AccessoriesLayerProps['card']>;

function boxLayer(extra: Partial<AccessoriesLayerProps>): TagLayer {
  return {
    id: 'acc',
    type: 'accessories',
    x_mm: 3,
    y_mm: 4,
    width_mm: 45,
    height_mm: 60,
    rotation_deg: 0,
    z_index: 1,
    locked: false,
    visible: true,
    slot_binding: null,
    text_override: null,
    // Left-aligned header style: a moved header must still centre in its own text-wide band on BOTH
    // canvas and print, or the two would sit a padding apart.
    props: {
      ...defaultAccessoriesProps(),
      headerText: 'FREE',
      headerOnBorder: true,
      headerStyle: { align: 'left' },
      headerPos: POS,
      ...extra,
    },
  } as unknown as TagLayer;
}

function row(): ResolvedLineData {
  return {
    tag_id: TAG_ID, tag_label: '1a', line_id: 'line-1', code: 'SRTWB7065', name: 'SRTWB7065',
    dimensions: '', spec_lines: '', set_members: '', list_price: 100, sell_price: null,
    show_promo_price: false, included_accessories: '', quantity: 1, parts: [], open_groups: [],
    specs: [], images: [], accessories: LIST,
  } as unknown as ResolvedLineData;
}

function doc(layer: TagLayer): TagSheetDoc {
  return {
    kind: 'tag_sheet',
    imposition: { preset: 'a4_3up', page_width_mm: 210, page_height_mm: 297, bleed_mm: 0, gap_mm: 2 },
    sheets: [
      {
        id: 's1',
        tags: [
          { id: 't1', template_id: 'tpl', request_tag_id: TAG_ID, x_mm: 5, y_mm: 5, width_mm: 148, height_mm: 105, layers: [layer] },
        ],
      },
    ],
  } as TagSheetDoc;
}

const STYLED = {
  headerPos: { x_mm: 5, y_mm: 6 },
  headerSize: { width_mm: 24, height_mm: 10 },
  headerFill: '#1f4d36',
  headerRadius_mm: 2,
  headerPadding: { top: 1, right: 1.5, bottom: 1, left: 2 },
  headerColor: '#ffffff',
};

async function canvas(layer: TagLayer) {
  const { container, unmount } = render(
    <KonvaTagLayer layer={layer} scale={SCALE} display={{ accessories: LIST }} />,
  );
  await act(async () => {
    await Promise.resolve();
  });
  const text = [...container.querySelectorAll('[data-konva="text"]')].find((t) => t.getAttribute('data-text') === (layer.props as AccessoriesLayerProps).headerText)!;
  const fill = [...container.querySelectorAll('[data-konva="rect"]')].find((r) => r.getAttribute('data-fill') === '#1f4d36')!;
  const n = (el: Element, k: string) => Number(el.getAttribute(`data-${k}`));
  const out = {
    text: { x: n(text, 'x'), y: n(text, 'y'), w: n(text, 'w'), h: n(text, 'h'), wrap: text.getAttribute('data-wrap') },
    fill: fill ? { x: n(fill, 'x'), y: n(fill, 'y'), w: n(fill, 'w'), h: n(fill, 'h'), corner: n(fill, 'corner') } : null,
  };
  unmount();
  return out;
}

describe('a resized, filled header prints where and how the designer draws it', () => {
  for (const kind of ['legacy', 'designed-card'] as const) {
    it(`${kind} box`, async () => {
      const layer = boxLayer(kind === 'legacy' ? STYLED : { ...STYLED, card: CARD });
      const c = await canvas(layer);
      // Canvas: the fill rect is the band; the text sits inside the padding and wraps.
      expect(c.fill).toEqual({ x: 5 * SCALE, y: 6 * SCALE, w: 24 * SCALE, h: 10 * SCALE, corner: 2 * SCALE });
      expect(c.text.x).toBeCloseTo((5 + 2) * SCALE, 6);
      expect(c.text.y).toBeCloseTo((6 + 1) * SCALE, 6);
      expect(c.text.w).toBeCloseTo((24 - 2 - 1.5) * SCALE, 6);
      expect(c.text.h).toBeCloseTo((10 - 1 - 1) * SCALE, 6);
      expect(c.text.wrap).toBe('word');

      render(<TagSheetRenderer doc={doc(layer)} resolvedData={{ [TAG_ID]: row() }} assets={{}} />);
      const header = screen.getByTestId('accessories-header');
      expect(header.style.left).toBe('5mm');
      expect(header.style.top).toBe('6mm');
      expect(header.style.width).toBe('24mm');
      expect(header.style.height).toBe('10mm');
      expect(header.style.backgroundColor).toBe('rgb(31, 77, 54)');
      expect(header.style.borderRadius).toBe('2mm');
      expect(header.style.padding).toBe('1mm 1.5mm 1mm 2mm');
      expect(header.style.boxSizing).toBe('border-box');
      expect(header.style.whiteSpace).toBe('normal');
      expect(header.style.color).toBe('rgb(255, 255, 255)');
    });
  }

  it('text too tall for a narrowed band spills like the canvas (centred, never clipped)', async () => {
    // Narrowed to 14 mm at today's 4.81 mm height: "ACCESSORIES INCLUDED" wraps to two 9 pt lines.
    const layer = boxLayer({
      headerText: 'ACCESSORIES INCLUDED',
      headerPos: { x_mm: 2, y_mm: 2 },
      headerSize: { width_mm: 14, height_mm: 4.81 },
    });
    const c = await canvas(layer);
    // Konva keeps the band as the text box and wraps inside it (it does not drop wrapped lines).
    expect(c.text.h).toBeCloseTo(4.81 * SCALE, 6);
    expect(c.text.wrap).toBe('word');
    render(<TagSheetRenderer doc={doc(layer)} resolvedData={{ [TAG_ID]: row() }} assets={{}} />);
    const header = screen.getByTestId('accessories-header');
    expect(header.style.whiteSpace).toBe('normal');
    expect(header.style.justifyContent).toBe('center');
    // The band itself never clips (a line taller than it spills, centred, as on the canvas) ...
    expect(header.style.overflow).toBe('');
    // ... and the text is cut to the lines Konva keeps: one 9 pt line in a 4.81 mm band.
    const cap = headerLineCap(accessoryChrome(layer.props as AccessoriesLayerProps, 45, 60).header!, 1);
    expect(cap.lines).toBe(1);
    const lines = screen.getByTestId('accessories-header-lines');
    expect(lines.style.maxHeight).toBe(`${cap.lineHeight_mm}mm`);
    expect(lines.style.overflow).toBe('hidden');
    expect(lines.style.overflowWrap).toBe('anywhere');
  });

  it('the line cap is Konva\'s rule: keep a line while the next still fits, the first always', () => {
    const h = (height_mm: number) => ({ height_mm, fontSize_pt: 9, padding: { top: 0, bottom: 0 } });
    const line = headerLineCap(h(1), 1).lineHeight_mm;
    expect(headerLineCap(h(line * 0.5)).lines).toBe(1);
    expect(headerLineCap(h(line * 1.99)).lines).toBe(1);
    expect(headerLineCap(h(line * 2)).lines).toBe(2);
    expect(headerLineCap(h(line * 3.2)).lines).toBe(3);
    expect(headerLineCap({ height_mm: line * 3.2, fontSize_pt: 9, padding: { top: line, bottom: 0 } }).lines).toBe(2);
    expect(headerLineCap(h(line * 3), 1.5).lines).toBe(2);
  });

  it('no stored style: the print header keeps today\'s single-line, unpadded, square look', () => {
    const layer = boxLayer({ headerPos: undefined });
    render(<TagSheetRenderer doc={doc(layer)} resolvedData={{ [TAG_ID]: row() }} assets={{}} />);
    const header = screen.getByTestId('accessories-header');
    expect(header.style.whiteSpace).toBe('nowrap');
    expect(header.style.borderRadius).toBe('');
    expect(header.style.padding).toBe('');
  });
});
