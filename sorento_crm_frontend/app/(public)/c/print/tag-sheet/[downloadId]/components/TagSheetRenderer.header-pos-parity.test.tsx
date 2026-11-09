/**
 * PRICETAG-HEADER-DRAG render parity (owner rule 4 Nov: every tag prints exactly as designed). A header
 * dragged in the designer prints at the same millimetres on the print sheet / PDF as the designer canvas
 * draws it, as plain text (no border-break background), for a legacy box and a designed-card box.
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

import { KonvaTagLayer } from '@/app/(protected)/dealer-kit/tag-templates/components/KonvaTagLayer';
import { accessoryBoxLayout, accessoryLineCount } from '@/lib/dealer-kit/accessory-box';
import { cardBoxLayout } from '@/lib/dealer-kit/accessory-card';
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
const POS = { x_mm: 6.5, y_mm: 22 };
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
    props: { ...defaultAccessoriesProps(), headerText: 'FREE', headerOnBorder: true, headerPos: POS, ...extra },
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

async function canvasHeader(layer: TagLayer) {
  const { container, unmount } = render(
    <KonvaTagLayer layer={layer} scale={SCALE} display={{ accessories: LIST }} />,
  );
  await act(async () => {
    await Promise.resolve();
  });
  const text = [...container.querySelectorAll('[data-konva="text"]')].find(
    (t) => t.getAttribute('data-text') === 'FREE',
  )!;
  const out = { x: Number(text.getAttribute('data-x')), y: Number(text.getAttribute('data-y')) };
  const backgrounds = [...container.querySelectorAll('[data-konva="rect"]')].filter(
    (r) => r.getAttribute('data-fill') === '#ffffff' && Number(r.getAttribute('data-x')) === out.x,
  );
  unmount();
  return { ...out, backgrounds: backgrounds.length };
}

describe('a moved header prints where the designer draws it', () => {
  it('legacy box: canvas and print place the header at the stored mm, plain text', async () => {
    const layer = boxLayer({});
    const box = accessoryBoxLayout(1, layer.props as AccessoriesLayerProps, 45, 60, accessoryLineCount(LIST));
    expect(box.header!.x_mm).toBe(POS.x_mm);
    expect(box.header!.y_mm).toBe(POS.y_mm);

    const canvas = await canvasHeader(layer);
    expect(canvas.x).toBeCloseTo(POS.x_mm * SCALE, 6);
    expect(canvas.y).toBeCloseTo(POS.y_mm * SCALE, 6);
    expect(canvas.backgrounds).toBe(0);

    render(<TagSheetRenderer doc={doc(layer)} resolvedData={{ [TAG_ID]: row() }} assets={{}} />);
    const header = screen.getByTestId('accessories-header');
    expect(header.style.left).toBe(`${POS.x_mm}mm`);
    expect(header.style.top).toBe(`${POS.y_mm}mm`);
    expect(header.style.backgroundColor).toBe('');
    expect(header.style.width).toBe(`${box.header!.width_mm}mm`);
  });

  it('designed-card box: canvas and print place the header at the stored mm, plain text', async () => {
    const layer = boxLayer({ card: CARD });
    const box = cardBoxLayout(1, layer.props as AccessoriesLayerProps, 45, 60);
    expect(box.header!.x_mm).toBe(POS.x_mm);

    const canvas = await canvasHeader(layer);
    expect(canvas.x).toBeCloseTo(POS.x_mm * SCALE, 6);
    expect(canvas.y).toBeCloseTo(POS.y_mm * SCALE, 6);
    expect(canvas.backgrounds).toBe(0);

    render(<TagSheetRenderer doc={doc(layer)} resolvedData={{ [TAG_ID]: row() }} assets={{}} />);
    const header = screen.getByTestId('accessories-header');
    expect(header.style.left).toBe(`${POS.x_mm}mm`);
    expect(header.style.top).toBe(`${POS.y_mm}mm`);
    expect(header.style.backgroundColor).toBe('');
  });
});
