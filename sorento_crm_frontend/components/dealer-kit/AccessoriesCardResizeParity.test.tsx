/**
 * TAG-ACC-CARD-RESIZE: the template canvas (`KonvaTagLayer`) and the print page (`TagSheetRenderer`)
 * draw the same designed accessories box when (1) the box is too small for one card at 70% - both
 * draw the shrunk cards, never the "Accessories" placeholder / nothing - and (2) a card Text element
 * carries the owner's header-like style (background, padding, corner radius) and `{{product.*}}`
 * fields, on a Free items box and on an Upgrades box.
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
          data-y={String(props.y ?? 0)}
          data-x={String(props.x ?? 0)}
          data-name={String(props.name ?? '')}
          data-clipw={String(props.clipWidth ?? '')}
          data-align={String(props.align ?? '')}
          data-style={String(props.fontStyle ?? '')}
          data-family={String(props.fontFamily ?? '')}
          data-fill={String(props.fill ?? '')}
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

import TagSheetRenderer, {
  type ResolvedLineData,
} from '@/app/(public)/c/print/tag-sheet/[downloadId]/components/TagSheetRenderer';
import { KonvaTagLayer } from '@/app/(protected)/dealer-kit/tag-templates/components/KonvaTagLayer';
import { layerDisplay } from '@/lib/dealer-kit/product-block';
import {
  defaultAccessoriesProps,
  type LineTagData,
  type TagAccessory,
  type TagLayer,
  type TagSheetDoc,
} from '@/lib/dealer-kit/tag-template-types';

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
const CARD_FILL = '#fefefe';
const LIST: TagAccessory[] = [
  {
    kind: 'product', id: 'p1', name: 'Popup Waste 80mm', spec: 'Brass', image: null,
    code: 'SRTW5000', list_price: 68, price_tag_description: 'Waste copy',
  },
  { kind: 'accessory', id: 'a1', name: 'DRAINER', spec: '390x300x140', image: null },
];

function row(accessories: TagAccessory[]): ResolvedLineData {
  return {
    tag_id: 't1', tag_label: 't1', line_id: 'line-t1', code: 'HOST', name: 'HOST',
    dimensions: '', spec_lines: '', set_members: '', list_price: 100, sell_price: null,
    show_promo_price: false, included_accessories: '', quantity: 1, parts: [], open_groups: [],
    specs: [], images: [], accessories,
  } as unknown as ResolvedLineData;
}

function boxLayer(width_mm: number, height_mm: number, text: Record<string, unknown> = {}): TagLayer {
  return {
    id: 'acc', type: 'accessories', x_mm: 3, y_mm: 4, width_mm, height_mm, rotation_deg: 0,
    z_index: 1, locked: false, visible: true, slot_binding: null, text_override: null,
    props: {
      ...defaultAccessoriesProps(),
      showHeader: false,
      showBadge: false,
      cardFill: CARD_FILL,
      card: {
        width_mm: 40,
        height_mm: 30,
        elements: [
          { id: 't', kind: 'text', field: null, text: '{{product.code}}', x_mm: 1, y_mm: 1, width_mm: 30, height_mm: 8, ...text },
        ],
      },
    },
  } as unknown as TagLayer;
}

function doc(layer: TagLayer): TagSheetDoc {
  return {
    kind: 'tag_sheet',
    imposition: { preset: 'a4_3up', page_width_mm: 210, page_height_mm: 297, bleed_mm: 0, gap_mm: 2 },
    sheets: [{ id: 's1', tags: [{ id: 't-t1', template_id: 'tpl', request_tag_id: 't1', x_mm: 5, y_mm: 5, width_mm: 148, height_mm: 105, layers: [layer] }] }],
  } as TagSheetDoc;
}

function printCards(layer: TagLayer, data: ResolvedLineData) {
  const { container } = render(<TagSheetRenderer doc={doc(layer)} resolvedData={{ t1: data }} assets={{}} />);
  const cards = [...container.querySelectorAll<HTMLElement>('[data-testid="accessories-card"]')].map((card) => ({
    width: parseFloat(card.style.width),
    texts: [...card.querySelectorAll<HTMLElement>('[data-testid="accessories-element-text"]')].map((t) => ({
      text: t.textContent ?? '',
      background: t.style.backgroundColor,
      width: parseFloat(t.style.width),
      padding: t.style.padding,
    })),
  }));
  cleanup();
  return cards;
}

async function canvas(layer: TagLayer, data: ResolvedLineData) {
  const display = layerDisplay(layer, { kind: 'line', line: data as unknown as LineTagData }, {});
  const result = render(<KonvaTagLayer layer={layer} scale={SCALE} display={display} />);
  await act(async () => {
    await Promise.resolve();
  });
  return result.container;
}

const rects = (c: HTMLElement, fill: string) =>
  [...c.querySelectorAll('[data-konva="rect"]')].filter((r) => r.getAttribute('data-fill') === fill);
const texts = (c: HTMLElement) => [...c.querySelectorAll('[data-konva="text"]')].map((t) => t.getAttribute('data-text'));

describe('a box too small for one card at 70% (Q1)', () => {
  it('print draws the shrunk card(s) and the canvas the same, never the placeholder', async () => {
    const layer = boxLayer(20, 14);
    const data = row(LIST);
    const print = printCards(layer, data);
    expect(print.length).toBeGreaterThan(0);
    const c = await canvas(layer, data);
    expect(texts(c)).not.toContain('Accessories');
    const cards = rects(c, CARD_FILL);
    expect(cards).toHaveLength(print.length);
    cards.forEach((card, i) => expect(Number(card.getAttribute('data-w')) / SCALE).toBeCloseTo(print[i].width, 6));
    expect(texts(c)).toContain('SRTW5000');
    expect(print[0].texts[0].text).toBe('SRTW5000');
  });
});

describe('card Text style and fields (owner 22:30 / 22:35)', () => {
  const style = { fill: '#dc2626', cornerRadius_mm: 1, padding: { top: 1, right: 2, bottom: 1, left: 2 } };

  it('Free items: background behind the element, text inset by the padding, on both surfaces', async () => {
    const layer = boxLayer(60, 80, style);
    const data = row(LIST);
    const print = printCards(layer, data);
    expect(print[0].texts[0]).toMatchObject({ text: 'SRTW5000', background: 'rgb(220, 38, 38)', width: 30 });
    expect(print[0].texts[0].padding).toBe('1mm 2mm');
    const c = await canvas(layer, data);
    const [bg] = rects(c, '#dc2626');
    expect(Number(bg.getAttribute('data-w')) / SCALE).toBeCloseTo(30, 6);
    expect(texts(c)).toContain('SRTW5000');
    // The canvas insets the text by the same padding print uses: left 2 mm, top 1 mm, 30 - 4 mm wide.
    const node = [...c.querySelectorAll('[data-konva="text"]')].find((t) => t.getAttribute('data-text') === 'SRTW5000')!;
    const inset = node.closest('[data-konva="group"][data-x="8"][data-y="4"]');
    expect(inset).not.toBeNull();
    expect(Number(node.getAttribute('data-w')) / SCALE).toBeCloseTo(26, 6);
    // The library accessory has no code: its text prints nothing on either surface.
    expect(print[1]?.texts ?? []).toHaveLength(0);
  });

  it('padding wider than the element: print keeps a valid padding (each side clamped at 0)', () => {
    const layer = boxLayer(60, 80, { padding: { top: 0, right: 0, bottom: 0, left: 40 } });
    const print = printCards(layer, row(LIST));
    // A negative side would make CSS drop the whole declaration (empty string).
    expect(print[0].texts[0].padding).toBe('0mm 0mm 0mm 40mm');
  });

  it('no stored style: no background on either surface (existing cards unchanged)', async () => {
    const layer = boxLayer(60, 80);
    const data = row(LIST);
    const print = printCards(layer, data);
    expect(print[0].texts[0]).toMatchObject({ background: '', padding: '' });
    const c = await canvas(layer, data);
    expect(rects(c, '#dc2626')).toHaveLength(0);
  });

  it('Upgrades box: the price tag description resolves per upgrade item on both surfaces', async () => {
    const layer = boxLayer(60, 80, { text: '{{product.price_tag_description}}' });
    (layer.props as { list?: string }).list = 'upgrades';
    const data = {
      ...row([]),
      combo: {
        id: 'c', name: 'C', description: null, free_items: null, choices: [],
        upgrades: [{ product_id: 'u1', code: 'SRTKT71SS', description: 'Tap', topup_amount: 150, picked: false }],
      },
      slots: {
        fixed: [], groups: [],
        upgrades: [{ product_id: 'u1', code: 'SRTKT71SS', name: 'Tap', dimensions: '', list_price: 440, price_tag_description: 'Tap copy' }],
      },
    } as unknown as ResolvedLineData;
    const print = printCards(layer, data);
    expect(print.map((card) => card.texts[0]?.text)).toEqual(['Tap copy']);
    const c = await canvas(layer, data);
    expect(texts(c)).toContain('Tap copy');
  });
});

describe('below the readable floor, and the "+N" chip (review should-fix 3, 4)', () => {
  it('both surfaces clip the floor-sized card to the box', async () => {
    const layer = boxLayer(8, 8);
    const data = row(LIST);
    const { container } = render(<TagSheetRenderer doc={doc(layer)} resolvedData={{ t1: data }} assets={{}} />);
    const box = container.querySelector<HTMLElement>('[data-testid="accessories-box"]')!;
    expect(box.style.overflow).toBe('hidden');
    cleanup();
    const c = await canvas(layer, data);
    expect(c.querySelector(`[data-konva="group"][data-clipw="${8 * SCALE}"]`)).not.toBeNull();
  });

  it('a box that fits draws no clip on either surface', async () => {
    const layer = boxLayer(60, 80);
    const data = row(LIST);
    const { container } = render(<TagSheetRenderer doc={doc(layer)} resolvedData={{ t1: data }} assets={{}} />);
    expect(container.querySelector<HTMLElement>('[data-testid="accessories-box"]')!.style.overflow).toBe('');
    cleanup();
    const c = await canvas(layer, data);
    expect([...c.querySelectorAll('[data-konva="group"]')].some((g) => g.getAttribute('data-clipw'))).toBe(false);
  });

  it('the editor canvas marks dropped cards with "+N"; print never does', async () => {
    const layer = boxLayer(60, 20);
    const data = row(LIST);
    const display = { ...layerDisplay(layer, { kind: 'line', line: data as unknown as LineTagData }, {}), accessoryDropMarker: true };
    const { container: c } = render(<KonvaTagLayer layer={layer} scale={SCALE} display={display} />);
    await act(async () => {
      await Promise.resolve();
    });
    expect(c.querySelector('[data-name="accessory-drop-marker"]')).not.toBeNull();
    expect(texts(c)).toContain('+1');
    cleanup();
    // Without the editor flag (request preview), no chip.
    expect((await canvas(layer, data)).querySelector('[data-name="accessory-drop-marker"]')).toBeNull();
    cleanup();
    const { container: print } = render(<TagSheetRenderer doc={doc(layer)} resolvedData={{ t1: data }} assets={{}} />);
    expect(print.textContent).not.toContain('+1');
  });
});

describe('a field that resolves to nothing prints NOTHING (crew check A, owner rule: missing = no space)', () => {
  const tag = '{{product.price_tag_description}}';

  function withUnder(layer: TagLayer): TagLayer {
    const card = (layer.props as { card: { elements: unknown[] } }).card;
    card.elements.push({ id: 'under', kind: 'text', field: null, text: 'UNDER', x_mm: 1, y_mm: 10, width_mm: 30, height_mm: 5 });
    return layer;
  }

  it('Free items: an item with no description prints no text and no raw tag; the element under moves up', async () => {
    const layer = withUnder(boxLayer(60, 80, { text: tag }));
    const noDescription: TagAccessory[] = [
      { kind: 'product', id: 'p2', name: 'Bare', spec: null, image: null, code: 'BARE1', list_price: 10, price_tag_description: null },
    ];
    const data = row(noDescription);
    const { container } = render(<TagSheetRenderer doc={doc(layer)} resolvedData={{ t1: data }} assets={{}} />);
    const texts = [...container.querySelectorAll<HTMLElement>('[data-testid="accessories-element-text"]')];
    expect(texts.map((t) => t.textContent)).toEqual(['UNDER']);
    expect(container.textContent).not.toContain('{{');
    // The element below moves up into the freed space (no gap).
    expect(parseFloat(texts[0].style.top)).toBeCloseTo(1, 6);
    cleanup();
    const c = await canvas(layer, data);
    expect(c.textContent ?? '').not.toContain('{{');
    expect([...c.querySelectorAll('[data-konva="text"]')].map((t) => t.getAttribute('data-text'))).not.toContain(tag);
  });

  it('Upgrades: an upgrade with no description prints no text and no raw tag', async () => {
    const layer = withUnder(boxLayer(60, 80, { text: tag }));
    (layer.props as { list?: string }).list = 'upgrades';
    const data = {
      ...row([]),
      combo: {
        id: 'c', name: 'C', description: null, free_items: null, choices: [],
        upgrades: [{ product_id: 'u2', code: 'NODESC', description: 'No desc', topup_amount: 50, picked: false }],
      },
      slots: { fixed: [], groups: [], upgrades: [{ product_id: 'u2', code: 'NODESC', name: 'No desc', dimensions: '', list_price: 90 }] },
    } as unknown as ResolvedLineData;
    const { container } = render(<TagSheetRenderer doc={doc(layer)} resolvedData={{ t1: data }} assets={{}} />);
    const texts = [...container.querySelectorAll<HTMLElement>('[data-testid="accessories-element-text"]')];
    expect(texts.map((t) => t.textContent)).toEqual(['UNDER']);
    expect(container.textContent).not.toContain('{{');
    cleanup();
    const c = await canvas(layer, data);
    expect([...c.querySelectorAll('[data-konva="text"]')].map((t) => t.getAttribute('data-text'))).not.toContain(tag);
  });
});
