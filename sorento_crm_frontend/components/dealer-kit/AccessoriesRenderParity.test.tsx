/**
 * PRICETAG-ACCESSORIES crew pass 3 (6 Nov): ONE tag sheet doc and ONE request row, rendered three
 * ways, must draw the same "Accessories" box:
 *   - the request designer and template canvas: `KonvaTagLayer` fed `layerDisplay(layer, row)`
 *     (`RequestTagDesigner` hosts `TagCanvasEditor`, which draws every layer through it);
 *   - the print preview: `ScaledSheet` (what `DesignViewer` shows staff and the portal);
 *   - the print page: `TagSheetRenderer` (what the PDF is rendered from).
 * Same frame size, same header text and size, same card lines in the same order at the same font
 * sizes; and a tag whose row has no list draws nothing in print (the canvas only its outline).
 */
import { act, cleanup, render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('konva/lib/Global', () => ({ Konva: { dragButtons: [0, 1] } }));
vi.mock('@/lib/dealer-kit/fonts', async (importOriginal) => ({
  ...(await importOriginal<object>()),
  ensureFontsLoaded: vi.fn(async () => ({ failed: [] })),
  ensureSeedFontsLoaded: vi.fn(async () => undefined),
}));
vi.mock('react-konva', () => {
  const passthrough = (name: string) =>
    function KonvaStandIn(props: Record<string, unknown> & { children?: React.ReactNode }) {
      return (
        <div
          data-konva={name}
          data-w={String(props.width ?? '')}
          data-h={String(props.height ?? '')}
          data-text={String(props.text ?? '')}
          data-size={String(props.fontSize ?? '')}
          data-dash={props.dash ? 'dashed' : ''}
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
  };
});

import ScaledSheet from './ScaledSheet';
import TagSheetRenderer, {
  type ResolvedLineData,
} from '@/app/(public)/c/print/tag-sheet/[downloadId]/components/TagSheetRenderer';
import { KonvaTagLayer } from '@/app/(protected)/dealer-kit/tag-templates/components/KonvaTagLayer';
import { ptToMm } from '@/lib/dealer-kit/accessory-box';
import { layerDisplay } from '@/lib/dealer-kit/product-block';
import {
  defaultAccessoriesProps,
  type LineTagData,
  type TagAccessory,
  type TagLayer,
  type TagSheetDoc,
} from '@/lib/dealer-kit/tag-template-types';
import type { TagSheetDesignPayload } from '@/lib/dealer-kit/design-payload';

class StubImage {
  width = 100;
  height = 100;
  onload: (() => void) | null = null;
  set src(_v: string) {
    Promise.resolve().then(() => this.onload?.());
  }
}
beforeEach(() => vi.stubGlobal('Image', StubImage));
afterEach(() => cleanup());

const SCALE = 4;
const LIST: TagAccessory[] = [
  { kind: 'accessory', id: 'a1', name: 'DRAINER', spec: '390x300x140, Depth: 160mm', image: null },
  { kind: 'accessory', id: 'a2', name: 'PULL OUT DRAINER', spec: null, image: null },
  {
    kind: 'product', id: 'p1', name: 'Popup Waste 80mm (w/o Overflow) Brass', spec: null, image: null,
    code: 'SRTW5000', list_price: 68,
  },
];

function row(tagId: string, accessories: TagAccessory[]): ResolvedLineData {
  return {
    tag_id: tagId, tag_label: tagId, line_id: `line-${tagId}`, code: 'SRTKS7061-BL', name: 'SRTKS7061-BL',
    dimensions: '', spec_lines: '', set_members: '', list_price: 100, sell_price: null,
    show_promo_price: false, included_accessories: '', quantity: 1, parts: [], open_groups: [],
    specs: [], images: [], accessories,
  } as unknown as ResolvedLineData;
}

function boxLayer(direction: 'vertical' | 'horizontal'): TagLayer {
  return {
    id: 'acc', type: 'accessories', x_mm: 3, y_mm: 4, width_mm: 60, height_mm: 60, rotation_deg: 0,
    z_index: 1, locked: false, visible: true, slot_binding: null, text_override: null,
    props: { ...defaultAccessoriesProps(), direction, headerText: 'ACCESSORIES INCLUDED' },
  } as unknown as TagLayer;
}

function doc(layer: TagLayer, tagIds: string[]): TagSheetDoc {
  return {
    kind: 'tag_sheet',
    imposition: { preset: 'a4_3up', page_width_mm: 210, page_height_mm: 297, bleed_mm: 0, gap_mm: 2 },
    sheets: [
      {
        id: 's1',
        tags: tagIds.map((id, i) => ({
          id: `t-${id}`, template_id: 'tpl', request_tag_id: id, x_mm: 5, y_mm: 5 + i * 110,
          width_mm: 148, height_mm: 105, layers: [layer],
        })),
      },
    ],
  } as TagSheetDoc;
}

type Drawn = { width: number; height: number; header: { text: string; pt: number }; lines: { text: string; pt: number }[] };

/** Read the box off the HTML renderers (print page and print preview), in mm and pt. */
function readHtml(container: HTMLElement): Drawn[] {
  return [...container.querySelectorAll<HTMLElement>('[data-testid="accessories-box"]')].map((box) => {
    const header = box.querySelector<HTMLElement>('[data-testid="accessories-header"]')!;
    return {
      width: parseFloat(box.style.width),
      height: parseFloat(box.style.height),
      header: { text: header.textContent ?? '', pt: parseFloat(header.style.fontSize) },
      lines: [...box.querySelectorAll<HTMLElement>('[data-testid="accessories-line"]')].map((l) => ({
        text: l.textContent ?? '',
        pt: parseFloat(l.style.fontSize),
      })),
    };
  });
}

/** Read the box off the Konva canvas, converted back from px to mm and pt. */
function readCanvas(container: HTMLElement, frameW: number): Drawn {
  const rects = [...container.querySelectorAll('[data-konva="rect"]')];
  const frame = rects.find((r) => Math.abs(Number(r.getAttribute('data-w')) / SCALE - frameW) < 1e-6)!;
  const texts = [...container.querySelectorAll('[data-konva="text"]')].map((t) => ({
    text: t.getAttribute('data-text') ?? '',
    pt: Number(t.getAttribute('data-size')) / SCALE / ptToMm(1),
  }));
  const [header, ...lines] = texts.filter((t) => t.text !== '+');
  return {
    width: Number(frame.getAttribute('data-w')) / SCALE,
    height: Number(frame.getAttribute('data-h')) / SCALE,
    header,
    lines,
  };
}

async function drawCanvas(layer: TagLayer, data: ResolvedLineData) {
  const display = layerDisplay(layer, { kind: 'line', line: data as unknown as LineTagData }, {});
  const result = render(<KonvaTagLayer layer={layer} scale={SCALE} display={display} />);
  await act(async () => {
    await Promise.resolve();
  });
  return result.container;
}

function payload(d: TagSheetDoc, rows: Record<string, ResolvedLineData>): TagSheetDesignPayload {
  return {
    page_id: 'pg', version: 1, source: 'draft', doc: d, resolvedData: rows,
    assets: {}, images: {}, fonts: [], featureIcons: [],
  };
}

const close = (a: number, b: number) => expect(a).toBeCloseTo(b, 6);

describe.each(['vertical', 'horizontal'] as const)('one doc, three renderers (%s)', (direction) => {
  it('request designer canvas = print preview = print page', async () => {
    const layer = boxLayer(direction);
    const rows = { t1: row('t1', LIST) };
    const d = doc(layer, ['t1']);

    const print = readHtml(render(<TagSheetRenderer doc={d} resolvedData={rows} assets={{}} />).container);
    cleanup();
    const preview = readHtml(render(<ScaledSheet payload={payload(d, rows)} sheetIndex={0} scale={0.5} />).container);
    cleanup();
    expect(print).toHaveLength(1);
    expect(preview).toEqual(print);

    const canvas = readCanvas(await drawCanvas(layer, rows.t1), print[0].width);
    close(canvas.width, print[0].width);
    close(canvas.height, print[0].height);
    expect(canvas.header.text).toBe(print[0].header.text);
    close(canvas.header.pt, print[0].header.pt);
    expect(canvas.lines.map((l) => l.text)).toEqual(print[0].lines.map((l) => l.text));
    canvas.lines.forEach((l, i) => close(l.pt, print[0].lines[i].pt));
    // Nothing is cut: every name and the header print whole (no ellipsis anywhere).
    expect(print[0].lines.map((l) => l.text)).toContain('PULL OUT DRAINER');
    expect(print[0].lines.every((l) => !l.text.endsWith('...'))).toBe(true);
  });
});

describe('a tag with no list', () => {
  it('print preview and print draw no box; the canvas only its dashed outline', async () => {
    const layer = boxLayer('vertical');
    const rows = { t1: row('t1', LIST), t2: row('t2', []) };
    const d = doc(layer, ['t1', 't2']);
    expect(readHtml(render(<TagSheetRenderer doc={d} resolvedData={rows} assets={{}} />).container)).toHaveLength(1);
    cleanup();
    expect(
      readHtml(render(<ScaledSheet payload={payload(d, rows)} sheetIndex={0} scale={0.5} />).container),
    ).toHaveLength(1);
    cleanup();
    const canvas = await drawCanvas(layer, rows.t2);
    expect(canvas.querySelector('[data-dash="dashed"]')).not.toBeNull();
  });
});
