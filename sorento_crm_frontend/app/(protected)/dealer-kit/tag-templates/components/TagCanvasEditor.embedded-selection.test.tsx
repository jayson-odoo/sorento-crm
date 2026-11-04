/**
 * SPEC-SHEET-V2 F4 crash (crew browser pass r6): the reader restarts a page's canvas after "Apply
 * to every page". A canvas that mounted with an EMPTY selection told the host "nothing selected",
 * the host cleared its selection, the canvas re-selected from the host's old value and reported it
 * back: a ping-pong that ended in "Maximum update depth exceeded". The canvas must start from the
 * host's selection and report only a selection the USER made.
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

function textLayer(id: string): TagLayer {
  return {
    id,
    type: 'text',
    x_mm: 0,
    y_mm: 0,
    width_mm: 30,
    height_mm: 8,
    rotation_deg: 0,
    z_index: 1,
    locked: false,
    visible: true,
    slot_binding: null,
    text_override: null,
    props: { ...defaultTextProps(), text: id },
  } as TagLayer;
}

const doc = {
  width_mm: 100,
  height_mm: 60,
  layers: [
    textLayer('title'),
    textLayer('area'),
    { ...textLayer('area-field'), props: { ...defaultTextProps(), text: 'AREA : {{line.area}}' } },
    { ...textLayer('spec'), props: { ...defaultTextProps(), text: '{{product.spec_lines}}' } },
  ],
} satisfies TagTemplateDoc;

function embedded(selectedLayerId: string | null, onSelect: (id: string | null) => void) {
  return {
    pxPerMm: 2,
    selectedLayerId,
    onSelect,
    controllerRef: { current: null },
  };
}

describe('TagCanvasEditor embedded selection', () => {
  it('a canvas that mounts while the host has a layer selected does not report "nothing selected"', async () => {
    const onSelect = vi.fn();
    render(
      <TagCanvasEditor doc={doc} onChange={vi.fn()} embedded={embedded('title', onSelect)} />,
    );
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 20));
    });
    expect(onSelect).not.toHaveBeenCalledWith(null);
  });

  it('a host that restarts the canvas (new key) with a selection settles, no update loop', async () => {
    const errors: unknown[] = [];
    const spy = vi.spyOn(console, 'error').mockImplementation((...args) => {
      errors.push(args[0]);
    });
    function Host() {
      const [selected, setSelected] = React.useState<string | null>('title');
      const [epoch, setEpoch] = React.useState(0);
      return (
        <>
          <button type="button" onClick={() => setEpoch((n) => n + 1)}>
            restart
          </button>
          <span data-testid="host-selection">{selected ?? 'none'}</span>
          <TagCanvasEditor
            key={epoch}
            doc={doc}
            onChange={vi.fn()}
            embedded={embedded(selected, setSelected)}
          />
        </>
      );
    }
    render(<Host />);
    await act(async () => {
      fireEvent.click(screen.getByText('restart'));
      await new Promise((resolve) => setTimeout(resolve, 30));
    });
    spy.mockRestore();
    expect(errors.some((e) => String(e).includes('Maximum update depth'))).toBe(false);
    expect(screen.getByTestId('host-selection')).toHaveTextContent('title');
  });

  it('a click on another layer is still reported to the host', async () => {
    const onSelect = vi.fn();
    render(
      <TagCanvasEditor doc={doc} onChange={vi.fn()} embedded={embedded('title', onSelect)} />,
    );
    await act(async () => {
      fireEvent.click(screen.getByTestId('layer-area'));
    });
    expect(onSelect).toHaveBeenCalledWith('area');
  });

  it('a double-click on a data-bound text (AREA) asks the host for its field box, not inline edit', async () => {
    const onEditField = vi.fn(() => true);
    render(
      <TagCanvasEditor
        doc={doc}
        onChange={vi.fn()}
        embedded={{ ...embedded(null, vi.fn()), onEditField }}
      />,
    );
    await act(async () => {
      fireEvent.click(screen.getByTestId('layer-area-field'));
      fireEvent.doubleClick(screen.getByTestId('layer-area-field'));
    });
    expect(onEditField).toHaveBeenCalledWith('area-field');
  });

  it('a read-only canvas does not open the field box', async () => {
    const onEditField = vi.fn();
    render(
      <TagCanvasEditor
        doc={doc}
        onChange={vi.fn()}
        embedded={{ ...embedded(null, vi.fn()), onEditField, readOnly: true }}
      />,
    );
    await act(async () => {
      fireEvent.doubleClick(screen.getByTestId('layer-area-field'));
    });
    expect(onEditField).not.toHaveBeenCalled();
  });

  it('a double-click on any other text, a data-bound one included, opens in-place typing on the page', async () => {
    const onEditField = vi.fn(() => false);
    render(
      <TagCanvasEditor
        doc={doc}
        onChange={vi.fn()}
        embedded={{ ...embedded(null, vi.fn()), onEditField }}
      />,
    );
    await act(async () => {
      fireEvent.click(screen.getByTestId('layer-spec'));
      fireEvent.doubleClick(screen.getByTestId('layer-spec'));
    });
    const box = await screen.findByTestId('inline-text-editor');
    expect(box).not.toHaveAttribute('readonly');
    expect(box).not.toHaveAttribute('aria-readonly', 'true');
  });

  it('the field box (AREA) opens instead of in-place typing when the host takes the double-click', async () => {
    const onEditField = vi.fn(() => true);
    render(
      <TagCanvasEditor
        doc={doc}
        onChange={vi.fn()}
        embedded={{ ...embedded(null, vi.fn()), onEditField }}
      />,
    );
    await act(async () => {
      fireEvent.doubleClick(screen.getByTestId('layer-area-field'));
    });
    expect(screen.queryByTestId('inline-text-editor')).toBeNull();
  });

  it('text typed in place is kept when the page unloads before the click outside', async () => {
    const onLayersChange = vi.fn();
    const view = render(
      <TagCanvasEditor
        doc={doc}
        onChange={vi.fn()}
        onLayersChange={onLayersChange}
        embedded={{ ...embedded(null, vi.fn()), onEditField: () => false }}
      />,
    );
    await act(async () => {
      fireEvent.doubleClick(screen.getByTestId('layer-title'));
    });
    const box = await screen.findByTestId('inline-text-editor');
    fireEvent.change(box, { target: { value: 'Custom note' } });
    onLayersChange.mockClear();
    // The reader scrolls far away and unloads the page: no blur, no click outside.
    view.unmount();
    const last = onLayersChange.mock.calls.at(-1)?.[0] as TagLayer[] | undefined;
    expect(last?.find((l) => l.id === 'title')?.props).toMatchObject({ text: 'Custom note' });
  });

  it('an in-place edit opened and left unchanged reports nothing on unload', async () => {
    const onLayersChange = vi.fn();
    const view = render(
      <TagCanvasEditor
        doc={doc}
        onChange={vi.fn()}
        onLayersChange={onLayersChange}
        embedded={{ ...embedded(null, vi.fn()), onEditField: () => false }}
      />,
    );
    await act(async () => {
      fireEvent.doubleClick(screen.getByTestId('layer-title'));
    });
    await screen.findByTestId('inline-text-editor');
    onLayersChange.mockClear();
    view.unmount();
    expect(onLayersChange).not.toHaveBeenCalled();
  });
});
