/**
 * SPEC-SHEET-DESIGNER-PARITY B6: the embedded canvas exposes `addLayer(kind)` on its controller, so
 * the reader's shared toolbar adds elements to the page through it. Written test-FIRST.
 */
import * as React from 'react';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { ProductTagData, TagLayer, TagTemplateDoc } from '@/lib/dealer-kit/tag-template-types';
import { defaultTextProps } from '@/lib/dealer-kit/tag-template-types';

// -- Stand-ins for everything that needs a browser or a server ---------------

vi.mock('konva/lib/Global', () => ({ Konva: { dragButtons: [0, 1] } }));

vi.mock('react-konva', () => {
  const passthrough = (name: string) =>
    function KonvaStandIn({ children }: { children?: React.ReactNode }) {
      return <div data-konva={name}>{children}</div>;
    };
  return {
    Stage: passthrough('stage'),
    Layer: passthrough('layer'),
    Group: passthrough('group'),
    Rect: passthrough('rect'),
    Line: passthrough('line'),
    Transformer: passthrough('transformer'),
  };
});

vi.mock('./KonvaTagLayer', () => ({
  KonvaTagLayer: ({
    layer,
    display,
    onSelect,
    onHoverChange,
    onDoubleClick,
  }: {
    layer: TagLayer;
    display?: { text?: string; imageUrl?: string | null };
    onSelect?: (id: string, additive: boolean) => void;
    onHoverChange?: (id: string, hovering: boolean) => void;
    onDoubleClick?: (id: string) => void;
  }) => (
    <div
      data-testid={`layer-${layer.id}`}
      data-image={display?.imageUrl ?? ''}
      onClick={() => onSelect?.(layer.id, false)}
      onDoubleClick={() => onDoubleClick?.(layer.id)}
      onMouseEnter={() => onHoverChange?.(layer.id, true)}
      onMouseLeave={() => onHoverChange?.(layer.id, false)}
    >
      {display?.text ?? ''}
    </div>
  ),
}));

vi.mock('@/lib/dealer-kit/fonts', () => ({
  ensureFontsLoaded: vi.fn(async () => ({ failed: [] })),
  ensureSeedFontsLoaded: vi.fn(async () => {}),
  TAG_FONT_STYLESHEET: '',
  SEED_FONT_FAMILIES: [],
}));

vi.mock('../../services/assetService', () => ({
  listAssets: vi.fn(async () => [
    {
      id: 'asset-logo',
      name: 'Logo',
      kind: 'logo',
      url: 'https://cdn.test/library/logo-original-7mb.png',
      thumb_url: 'https://cdn.test/library/logo.thumb.jpg',
    },
  ]),
  listFontAssets: vi.fn(async () => []),
}));

const PRODUCTS: Record<string, ProductTagData> = {
  'p-sink': {
    id: 'p-sink',
    code: 'CBF3612',
    name: 'Carysil Big Bowl Sink',
    dimensions: 'L860xW500xH220mm',
    spec_lines: ['Nano grain finish'],
    specs: [{ key: 'material', label: 'Material', value: 'granite', unit: null }],
    images: [],
    list_price: 2000,
    offer_price: 1500,
    promotion_id: null,
    barcode: null,
  },
  'p-tap': {
    id: 'p-tap',
    code: 'SRT2201',
    name: 'Sorento Pillar Tap',
    dimensions: 'L200xW50xH300mm',
    spec_lines: ['Brass body'],
    specs: [],
    images: [],
    list_price: 400,
    offer_price: 320,
    promotion_id: null,
    barcode: null,
  },
};

vi.mock('../../services/tagDataService', () => ({
  productOptions: vi.fn(async () =>
    Object.values(PRODUCTS).map((product) => ({
      value: product.id,
      label: product.code,
      description: product.name,
    })),
  ),
  productSetOptions: vi.fn(async () => []),
  listSpecKeys: vi.fn(async () => []),
  getProductTagData: vi.fn(async (id: string) => PRODUCTS[id]),
  getProductSetTagData: vi.fn(async () => {
    throw new Error('not used');
  }),
}));

import { TagCanvasEditor } from './TagCanvasEditor';

function mount(layers: TagLayer[] = []) {
  const controllerRef: { current: unknown } = { current: null };
  const onSelect = vi.fn();
  const reported: TagLayer[][] = [];
  render(
    <TagCanvasEditor
      doc={{ width_mm: 100, height_mm: 60, layers }}
      onChange={vi.fn()}
      onLayersChange={(next) => reported.push(next)}
      specSheet
      embedded={{ pxPerMm: 2, selectedLayerId: null, onSelect, controllerRef: controllerRef as never }}
    />,
  );
  return { controllerRef, onSelect, reported };
}

type Adder = { addLayer: (kind: string) => void };

describe('embedded controller addLayer (B6)', () => {
  it("addLayer('text') adds one selected text layer and reports it", async () => {
    const { controllerRef, onSelect, reported } = mount();
    await act(async () => {
      (controllerRef.current as Adder).addLayer('text');
    });
    const last = reported[reported.length - 1];
    expect(last).toHaveLength(1);
    expect(last[0].type).toBe('text');
    expect(onSelect).toHaveBeenCalledWith(last[0].id);
  });

  it("addLayer('table') adds a table layer", async () => {
    const { controllerRef, reported } = mount();
    await act(async () => {
      (controllerRef.current as Adder).addLayer('table');
    });
    const last = reported[reported.length - 1];
    expect(last.map((l) => l.type as string)).toEqual(['table']);
  });

  it('keeps the layers already on the page and gives the new one a fresh id', async () => {
    const { controllerRef, reported } = mount([
      { ...({} as TagLayer), id: 'old', type: 'text', x_mm: 0, y_mm: 0, width_mm: 30, height_mm: 8, rotation_deg: 0, z_index: 1, locked: false, visible: true, slot_binding: null, text_override: null, props: { ...defaultTextProps(), text: 'old' } } as unknown as TagLayer,
    ]);
    await act(async () => {
      (controllerRef.current as Adder).addLayer('shape');
    });
    const last = reported[reported.length - 1];
    expect(last).toHaveLength(2);
    expect(last[0].id).toBe('old');
    expect(last[1].id).not.toBe('old');
    expect(last[1].type).toBe('shape');
  });
});

describe('embedded picker cancel and group (B6 fix round)', () => {
  it('cancelling the asset picker removes the empty frame addLayer(image) just added', async () => {
    const { controllerRef, reported } = mount();
    await act(async () => {
      (controllerRef.current as Adder).addLayer('image');
    });
    expect(reported[reported.length - 1].map((l) => l.type)).toEqual(['image']);
    fireEvent.click(await screen.findByRole('button', { name: 'Cancel' }));
    expect(reported[reported.length - 1]).toEqual([]);
  });

  it('exposes groupSelected / ungroupSelected on the controller', async () => {
    const { controllerRef } = mount();
    await act(async () => {
      await Promise.resolve();
    });
    const controller = controllerRef.current as { groupSelected?: unknown; ungroupSelected?: unknown };
    expect(typeof controller.groupSelected).toBe('function');
    expect(typeof controller.ungroupSelected).toBe('function');
  });
});

