/**
 * PRICETAG-DESIGNER-FEEDBACK B2 in the designer (TagCanvasEditor).
 *
 * AC-3.4 right-click an accessory card -> "Change photo" opens "Choose an image"; the pick saves to
 * the main product's list row (`PUT /api/v1/master-data/products/{id}/accessories` with
 * `photo_attachment_id`). "Reset to product photo" appears only when an override is set.
 * AC-6.3 "Add Image" opens the picker with `onPickMany`; 3 picks add 3 image boxes, each below the
 * previous one.
 *
 * Harness: TagCanvasEditor.context-menu.test.tsx (Stage stand-in with getContent, KonvaTagLayer
 * renders nothing, a right-click's client px = stage px). `AssetPickerDialog` is a stand-in that
 * records its props and offers buttons that call `onPick` / `onPickMany`. HTTP goes through a mocked
 * `apiFetch`, so the save is asserted on the request, not on a service name.
 *
 * Invented (the coder must match): the previewed accessory row carries `photo_attachment_id`
 * (null = no override), which is what makes "Reset to product photo" appear.
 * Written test-FIRST.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { CANVAS_PX_PER_MM } from '@/lib/dealer-kit/canvas-geometry';
import {
  defaultAccessoriesProps,
  type TagBindingData,
  type TagLayer,
  type TagTemplateDoc,
} from '@/lib/dealer-kit/tag-template-types';

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() } }));
vi.mock('konva/lib/Global', () => ({ Konva: { dragButtons: [0, 1] } }));

vi.mock('react-konva', () => {
  const passthrough = (name: string) =>
    function KonvaStandIn({ children }: { children?: React.ReactNode }) {
      return <div data-konva={name}>{children}</div>;
    };
  return {
    Stage: ({ children, ref }: { children?: React.ReactNode; ref?: React.Ref<{ getContent: () => HTMLElement }> }) => {
      const instance = { getContent: () => document.createElement('div') };
      if (typeof ref === 'function') ref(instance);
      else if (ref && 'current' in (ref as { current: unknown })) (ref as { current: unknown }).current = instance;
      return <div data-konva="stage">{children}</div>;
    },
    Layer: passthrough('layer'),
    Group: passthrough('group'),
    Rect: passthrough('rect'),
    Circle: passthrough('circle'),
    Line: passthrough('line'),
    Transformer: passthrough('transformer'),
  };
});

vi.mock('./KonvaTagLayer', () => ({ KonvaTagLayer: () => null }));

vi.mock('@/lib/dealer-kit/fonts', () => ({
  ensureFontsLoaded: vi.fn(async () => ({ failed: [] })),
  ensureSeedFontsLoaded: vi.fn(async () => {}),
  TAG_FONT_STYLESHEET: '',
  SEED_FONT_FAMILIES: [],
}));

vi.mock('../../services/assetService', () => ({
  listAssets: vi.fn(async () => []),
  listFontAssets: vi.fn(async () => []),
  uploadAsset: vi.fn(),
}));

vi.mock('../../services/tagDataService', () => ({
  productOptions: vi.fn(async () => []),
  productSetOptions: vi.fn(async () => []),
  listSpecKeys: vi.fn(async () => []),
  comboOptions: vi.fn(async () => []),
  getProductTagData: vi.fn(async () => {
    throw new Error('not used');
  }),
  getProductSetTagData: vi.fn(async () => {
    throw new Error('not used');
  }),
}));

const http = vi.hoisted(() => ({
  calls: [] as { url: string; method: string; body: string }[],
}));
vi.mock('@/lib/api', async (importOriginal) => {
  const actual = (await importOriginal()) as Record<string, unknown>;
  return {
    ...actual,
    apiFetch: vi.fn(async (url: string, init: RequestInit = {}) => {
      const method = (init.method ?? 'GET').toUpperCase();
      http.calls.push({ url: String(url), method, body: typeof init.body === 'string' ? init.body : '' });
      const listRow = {
        kind: 'product', id: 'p-acc', name: 'ZZT DRAINER', spec: null, remark: null, image: null, images: [],
        colours: [], code: 'ZZT-DRAINER', list_price: null, product_count: 0, combo_count: 0,
        entry: { image_id: null, name: null, spec: null, remark: null, photo_attachment_id: null },
      };
      const body = String(url).includes('/accessories') ? { data: [listRow], box_style_id: null } : { data: [] };
      return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } });
    }),
  };
});

const picker = vi.hoisted(() => ({ props: [] as Record<string, unknown>[] }));
vi.mock('./AssetPickerDialog', () => ({
  AssetPickerDialog: (props: {
    open: boolean;
    title?: string;
    onPick?: (s: unknown) => void;
    onPickMany?: (s: unknown[]) => void;
  }) => {
    picker.props.push(props as Record<string, unknown>);
    if (!props.open) return null;
    return (
      <div role="dialog" aria-label={props.title ?? 'Choose an image'} data-pick-many={String(!!props.onPickMany)}>
        <button type="button" onClick={() => props.onPick?.({ type: 'product_attachment', attachmentId: 'att-side' })}>
          stand-in pick one
        </button>
        <button
          type="button"
          onClick={() =>
            props.onPickMany?.([
              { type: 'asset', assetId: 'as-1' },
              { type: 'asset', assetId: 'as-2' },
              { type: 'product_attachment', attachmentId: 'att-3' },
            ])
          }
        >
          stand-in pick three
        </button>
      </div>
    );
  },
}));

import { TagCanvasEditor } from './TagCanvasEditor';

beforeEach(() => {
  http.calls.length = 0;
  picker.props.length = 0;
});

const CARD = {
  width_mm: 30,
  height_mm: 20,
  elements: [{ id: 'pic', kind: 'picture', field: 'picture', x_mm: 0, y_mm: 0, width_mm: 30, height_mm: 20 }],
};

function accessoriesBox(): TagLayer {
  return {
    id: 'acc', type: 'accessories', x_mm: 0, y_mm: 0, width_mm: 100, height_mm: 80, rotation_deg: 0, z_index: 1,
    locked: false, visible: true, slot_binding: null, text_override: null,
    props: { ...defaultAccessoriesProps(), showHeader: false, headerText: '', showBadge: false, gap_mm: 0, columns: 1, card: CARD },
  } as unknown as TagLayer;
}

function bound(photo: string | null): TagBindingData {
  return {
    kind: 'product',
    product: {
      id: 'p-host', code: 'ZZT-HOST', name: 'ZZT-HOST', dimensions: '', spec_lines: [], specs: [], images: [],
      list_price: 100, offer_price: null, promotion_id: null, barcode: null,
      accessories: [
        {
          kind: 'product', id: 'p-acc', name: 'ZZT DRAINER', spec: null, remark: null,
          image: { attachment_id: photo ?? 'att-lead', url: 'https://cdn.test/lead.jpg' },
          images: [{ attachment_id: photo ?? 'att-lead', url: 'https://cdn.test/lead.jpg', colour_name: null, colour_hex: null }],
          colours: [], code: 'ZZT-DRAINER', list_price: null, photo_attachment_id: photo,
        },
      ],
    },
  } as unknown as TagBindingData;
}

const doc = (...layers: TagLayer[]): TagTemplateDoc => ({ width_mm: 120, height_mm: 100, layers });

/** Inside the first card (1.5 to 31.5 mm across, 1.5 to 21.5 mm down). */
const INSIDE_CARD = { clientX: 10 * CANVAS_PX_PER_MM, clientY: 10 * CANVAS_PX_PER_MM };

function rightClick(container: HTMLElement, point: { clientX: number; clientY: number }) {
  const stageHost = container.querySelector('[data-konva="stage"]')!.parentElement!.parentElement!;
  fireEvent.contextMenu(stageHost, point);
}

describe('AC-3.4: change an accessory photo from the canvas', () => {
  it('right-click a card offers "Change photo" and no "Reset to product photo" without an override', () => {
    const { container } = render(<TagCanvasEditor doc={doc(accessoriesBox())} onChange={vi.fn()} boundData={bound(null)} />);
    rightClick(container, INSIDE_CARD);
    // Harness check: the click lands on the box (the layer menu, not the empty-canvas one).
    expect(screen.getByRole('menuitem', { name: /Duplicate/ })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: /Change photo/ })).toBeInTheDocument();
    expect(screen.queryByRole('menuitem', { name: /Reset to product photo/ })).toBeNull();
  });

  it('"Reset to product photo" appears when the row has an override', () => {
    const { container } = render(
      <TagCanvasEditor doc={doc(accessoriesBox())} onChange={vi.fn()} boundData={bound('att-own')} />,
    );
    rightClick(container, INSIDE_CARD);
    expect(screen.getByRole('menuitem', { name: /Reset to product photo/ })).toBeInTheDocument();
  });

  it('"Change photo" opens "Choose an image"; the pick saves to the main product list row', async () => {
    const { container } = render(<TagCanvasEditor doc={doc(accessoriesBox())} onChange={vi.fn()} boundData={bound(null)} />);
    rightClick(container, INSIDE_CARD);
    fireEvent.click(screen.getByRole('menuitem', { name: /Change photo/ }));
    const dialog = await screen.findByRole('dialog', { name: 'Choose an image' });
    fireEvent.click(dialog.querySelector('button')!);

    await waitFor(() => {
      const save = http.calls.find(
        (c) => ['PUT', 'PATCH'].includes(c.method) && c.url.includes('/master-data/products/p-host/accessories'),
      );
      expect(save, JSON.stringify(http.calls)).toBeDefined();
      expect(save!.body).toContain('"photo_attachment_id":"att-side"');
    });
  });

  it('"Reset to product photo" saves a null photo for that row', async () => {
    const { container } = render(
      <TagCanvasEditor doc={doc(accessoriesBox())} onChange={vi.fn()} boundData={bound('att-own')} />,
    );
    rightClick(container, INSIDE_CARD);
    fireEvent.click(screen.getByRole('menuitem', { name: /Reset to product photo/ }));
    await waitFor(() => {
      const save = http.calls.find(
        (c) => ['PUT', 'PATCH'].includes(c.method) && c.url.includes('/master-data/products/p-host/accessories'),
      );
      expect(save, JSON.stringify(http.calls)).toBeDefined();
      expect(save!.body).toContain('"photo_attachment_id":null');
    });
  });
});

describe('AC-6.3: one image box per picked image', () => {
  it('"Add Image" opens the picker in pick-many mode', async () => {
    render(<TagCanvasEditor doc={doc()} onChange={vi.fn()} />);
    fireEvent.click(screen.getAllByRole('button', { name: 'Add Image' })[0]);
    const dialog = await screen.findByRole('dialog', { name: 'Choose an image' });
    expect(dialog).toHaveAttribute('data-pick-many', 'true');
  });

  it('picking 3 images adds 3 image boxes, in order, each below the previous one', async () => {
    const onChange = vi.fn();
    render(<TagCanvasEditor doc={doc()} onChange={vi.fn()} onLayersChange={onChange} />);
    fireEvent.click(screen.getAllByRole('button', { name: 'Add Image' })[0]);
    fireEvent.click(await screen.findByRole('button', { name: 'stand-in pick three' }));

    await waitFor(() => {
      const last = { layers: (onChange.mock.calls.at(-1)?.[0] ?? []) as TagLayer[] };
      expect(last.layers.filter((l) => l.type === 'image')).toHaveLength(3);
    });
    const last = { layers: onChange.mock.calls.at(-1)![0] as TagLayer[] };
    const images = last.layers.filter((l) => l.type === 'image');
    expect(images.map((l) => (l.props as { source?: unknown }).source)).toEqual([
      { type: 'asset', assetId: 'as-1' },
      { type: 'asset', assetId: 'as-2' },
      { type: 'product_attachment', attachmentId: 'att-3' },
    ]);
    for (let i = 1; i < images.length; i += 1) {
      expect(images[i].y_mm).toBeGreaterThanOrEqual(images[i - 1].y_mm + images[i - 1].height_mm - 1e-6);
    }
  });
});

describe('AC-5.3: a card that crosses the tag edge is named on the canvas', () => {
  function manyBound(count: number): TagBindingData {
    const accessories = Array.from({ length: count }, (_, i) => ({
      kind: 'product', id: `p-acc-${i + 1}`, name: `ZZT ITEM ${i + 1}`, spec: null, remark: null, image: null,
      images: [], colours: [], code: `ZZTACC${i + 1}`, list_price: null, photo_attachment_id: null,
    }));
    const base = bound(null) as unknown as { product: Record<string, unknown> };
    return { kind: 'product', product: { ...base.product, accessories } } as unknown as TagBindingData;
  }

  function lowBox(): TagLayer {
    // 8 mm tall box sitting 2 mm above the bottom of a 100 mm tag: six 20 mm cards stacked can
    // never fit, whatever the readable minimum is, so the last ones grow past the tag edge.
    return { ...accessoriesBox(), y_mm: 90, height_mm: 8 } as TagLayer;
  }

  it('shows a visible warning naming the card that crosses the tag edge', async () => {
    render(<TagCanvasEditor doc={doc(lowBox())} onChange={vi.fn()} boundData={manyBound(6)} />);
    await waitFor(() => expect(screen.getByText(/ZZTACC6/)).toBeInTheDocument());
  });

  it('says nothing when every card stays inside the tag', async () => {
    render(<TagCanvasEditor doc={doc(accessoriesBox())} onChange={vi.fn()} boundData={manyBound(2)} />);
    // Let effects settle, then expect no warning naming a card.
    await waitFor(() => expect(screen.getAllByRole('button', { name: 'Add Image' }).length).toBeGreaterThan(0));
    expect(screen.queryByText(/ZZTACC1|ZZTACC2/)).toBeNull();
  });
});

describe('AC-6.3: the new boxes are selected; replacing an image stays single pick', () => {
  it('after picking 3 images all 3 new boxes are selected (one nudge moves all three)', async () => {
    const onChange = vi.fn();
    render(<TagCanvasEditor doc={doc()} onChange={vi.fn()} onLayersChange={onChange} />);
    fireEvent.click(screen.getAllByRole('button', { name: 'Add Image' })[0]);
    fireEvent.click(await screen.findByRole('button', { name: 'stand-in pick three' }));
    await waitFor(() => {
      const last = { layers: (onChange.mock.calls.at(-1)?.[0] ?? []) as TagLayer[] };
      expect(last.layers.filter((l) => l.type === 'image')).toHaveLength(3);
    });
    const before = (onChange.mock.calls.at(-1)![0] as TagLayer[]).filter((l) => l.type === 'image');

    fireEvent.keyDown(window, { key: 'ArrowRight', shiftKey: true });
    await waitFor(() => {
      const after = (onChange.mock.calls.at(-1)![0] as TagLayer[]).filter((l) => l.type === 'image');
      after.forEach((layer, i) => expect(layer.x_mm).toBeCloseTo(before[i].x_mm + 1, 6));
    });
  });

  it('Choose image on an existing image box opens a single-pick dialog that applies and closes', async () => {
    const onChange = vi.fn();
    const existing = {
      id: 'img1', type: 'image', x_mm: 5, y_mm: 5, width_mm: 20, height_mm: 10, rotation_deg: 0, z_index: 1,
      locked: false, visible: true, slot_binding: null, text_override: null,
      props: { kind: 'image', source: null, fit: 'contain', maskShape: 'none' },
    } as TagLayer;
    const { container } = render(<TagCanvasEditor doc={doc(existing)} onChange={vi.fn()} onLayersChange={onChange} />);
    // A right-click selects the clicked layer (TagCanvasEditor.context-menu.test.tsx).
    rightClick(container, { clientX: 10 * CANVAS_PX_PER_MM, clientY: 10 * CANVAS_PX_PER_MM });
    // Close the menu without Escape (Escape also clears the selection): a harmless item.
    fireEvent.click(screen.getByRole('menuitem', { name: /Bring to Front/ }));
    await waitFor(() => expect(screen.queryByRole('menu')).toBeNull());
    fireEvent.click(await screen.findByRole('button', { name: 'Choose image' }));

    const dialog = await screen.findByRole('dialog', { name: 'Choose an image' });
    expect(dialog).toHaveAttribute('data-pick-many', 'false');
    fireEvent.click(screen.getByRole('button', { name: 'stand-in pick one' }));

    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Choose an image' })).toBeNull());
    await waitFor(() => {
      const last = { layers: (onChange.mock.calls.at(-1)?.[0] ?? []) as TagLayer[] };
      expect(last.layers.filter((l) => l.type === 'image')).toHaveLength(1);
      expect((last!.layers[0].props as { source?: unknown }).source).toEqual({
        type: 'product_attachment',
        attachmentId: 'att-side',
      });
    });
  });
});
