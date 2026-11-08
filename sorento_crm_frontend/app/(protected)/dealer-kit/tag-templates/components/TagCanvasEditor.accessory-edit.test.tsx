/**
 * PRICETAG-ACCESSORY-DESIGNER S3: card / footer editing mode of an accessories box in the tag template
 * designer.
 *
 * Plan: PLAN-pricetag-accessory-designer-07nov.md "S3 Designer", card rules V1 and V3, mock v2.
 *  - double-click (or Enter) on a SELECTED accessories box, or the inspector's "Edit card" / "Edit footer",
 *    enters editing mode; the toolbar then reads `Editing card:` with Picture, Text, Colour dots, Shape, Done
 *    (footer: no Picture).
 *  - entering a box with no `card` builds one with `cardFromLegacy` first.
 *  - clicking a tool adds an element to `layer.props.card.elements` (footer: `footer.elements`).
 *  - Done and Escape leave the mode.
 *
 * Mount idiom: `TagCanvasEditor.nudge.test.tsx` (KonvaTagLayer stood in by a div; here it also forwards a
 * double-click). InspectorPanel and CanvasToolbar are NOT mocked. The saved-template hooks and service are
 * mocked (modules assumed by this lane).
 *
 * Written test-FIRST.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { TagLayer, TagTemplateDoc } from '@/lib/dealer-kit/tag-template-types';
import { defaultAccessoriesProps } from '@/lib/dealer-kit/tag-template-types';

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
    Circle: passthrough('circle'),
    Line: passthrough('line'),
    Transformer: passthrough('transformer'),
  };
});

vi.mock('./KonvaTagLayer', () => ({
  KonvaTagLayer: ({
    layer,
    onSelect,
    onDoubleClick,
  }: {
    layer: TagLayer;
    onSelect?: (id: string, additive: boolean) => void;
    onDoubleClick?: (id: string) => void;
  }) => (
    <div
      data-testid={`layer-${layer.id}`}
      onClick={() => onSelect?.(layer.id, false)}
      onDoubleClick={() => onDoubleClick?.(layer.id)}
    />
  ),
}));

vi.mock('@/lib/dealer-kit/fonts', () => ({
  ensureFontsLoaded: vi.fn(async () => ({ failed: [] })),
  ensureSeedFontsLoaded: vi.fn(async () => {}),
  TAG_FONT_STYLESHEET: '',
  SEED_FONT_FAMILIES: [],
}));

vi.mock('../../services/assetService', () => ({
  listAssets: vi.fn(async () => []),
  listFontAssets: vi.fn(async () => []),
}));

vi.mock('../../services/tagDataService', () => ({
  productOptions: vi.fn(async () => []),
  productSetOptions: vi.fn(async () => []),
  listSpecKeys: vi.fn(async () => []),
  getProductTagData: vi.fn(async () => {
    throw new Error('not used');
  }),
  getProductSetTagData: vi.fn(async () => {
    throw new Error('not used');
  }),
}));

vi.mock('../../services/accessoryTemplateService', () => ({
  listAccessoryTemplates: vi.fn(async () => []),
  getAccessoryTemplate: vi.fn(async () => null),
  createAccessoryTemplate: vi.fn(),
  updateAccessoryTemplate: vi.fn(),
  getAccessoryTemplateUsage: vi.fn(async () => ({ templates: [] })),
}));

const hookStub = () => ({ data: undefined, isLoading: false, mutate: vi.fn(), mutateAsync: vi.fn(), run: vi.fn() });
vi.mock('../../accessory-templates/hooks/useAccessoryTemplates', () => ({
  useAccessoryTemplatesQuery: () => ({ ...hookStub(), data: [] }),
  useAccessoryTemplateQuery: hookStub,
  useAccessoryTemplateUsage: hookStub,
  useCreateAccessoryTemplate: hookStub,
  useUpdateAccessoryTemplate: hookStub,
  useDeleteAccessoryTemplate: hookStub,
}));

import { TagCanvasEditor } from './TagCanvasEditor';

function accessoriesLayer(id: string, props: Record<string, unknown> = {}): TagLayer {
  return {
    id,
    type: 'accessories',
    x_mm: 5,
    y_mm: 5,
    width_mm: 60,
    height_mm: 80,
    rotation_deg: 0,
    z_index: 1,
    locked: false,
    visible: true,
    slot_binding: null,
    text_override: null,
    props: { ...defaultAccessoriesProps(), ...props },
  } as TagLayer;
}

function docWith(...layers: TagLayer[]): TagTemplateDoc {
  return { width_mm: 148, height_mm: 105, layers };
}

function mount(layer: TagLayer = accessoriesLayer('acc1')) {
  const state = { layers: [] as TagLayer[] };
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <TagCanvasEditor
        doc={docWith(layer)}
        onChange={vi.fn()}
        onLayersChange={(layers) => {
          state.layers = layers;
        }}
      />
    </QueryClientProvider>,
  );
  return state;
}

const cardOf = (state: { layers: TagLayer[] }) =>
  (state.layers[0].props as unknown as { card?: { elements: { kind: string; field?: string | null }[] } }).card;

function select() {
  fireEvent.click(screen.getByTestId('layer-acc1'));
}

describe('accessories box: entering card editing mode', () => {
  it('a plain selected box is not in editing mode', () => {
    mount();
    select();
    expect(screen.queryByText(/Editing card:/)).toBeNull();
  });

  it('double-click on the box enters card editing mode with the four tools and Done', () => {
    mount();
    select();
    fireEvent.doubleClick(screen.getByTestId('layer-acc1'));
    expect(screen.getByText(/Editing card:/)).toBeInTheDocument();
    for (const name of ['Picture', 'Text', 'Colour dots', 'Shape', 'Done']) {
      expect(screen.getByRole('button', { name })).toBeInTheDocument();
    }
  });

  it('Enter on a selected box enters card editing mode', () => {
    mount();
    select();
    fireEvent.keyDown(window, { key: 'Enter' });
    expect(screen.getByText(/Editing card:/)).toBeInTheDocument();
  });

  it('the inspector Edit card button enters card editing mode', () => {
    mount();
    select();
    fireEvent.click(screen.getByRole('button', { name: 'Edit card' }));
    expect(screen.getByText(/Editing card:/)).toBeInTheDocument();
  });

  it('entering a box with no card builds one from its legacy settings (picture, name, spec)', () => {
    const state = mount();
    select();
    fireEvent.doubleClick(screen.getByTestId('layer-acc1'));
    const card = cardOf(state);
    expect(card).toBeDefined();
    const fields = card!.elements.map((e) => e.field);
    expect(fields).toEqual(expect.arrayContaining(['picture', 'name', 'spec']));
  });

  it('entering a box that already has a card leaves that card alone', () => {
    const own = {
      width_mm: 40,
      height_mm: 30,
      elements: [{ id: 'only', kind: 'text', field: 'name', x_mm: 1, y_mm: 1, width_mm: 20, height_mm: 5 }],
    };
    const state = mount(accessoriesLayer('acc1', { card: own }));
    select();
    fireEvent.doubleClick(screen.getByTestId('layer-acc1'));
    expect(screen.getByText(/Editing card:/)).toBeInTheDocument();
    const live = cardOf(state) ?? own;
    expect(live.elements).toHaveLength(1);
  });
});

describe('accessories box: tools and leaving', () => {
  it('Colour dots adds a colour_dots element to the card', () => {
    const state = mount();
    select();
    fireEvent.doubleClick(screen.getByTestId('layer-acc1'));
    const before = cardOf(state)!.elements.length;
    fireEvent.click(screen.getByRole('button', { name: 'Colour dots' }));
    const elements = cardOf(state)!.elements;
    expect(elements).toHaveLength(before + 1);
    expect(elements.some((e) => e.kind === 'colour_dots')).toBe(true);
  });

  it('Text, Shape and Picture add their own element kinds', () => {
    const state = mount(
      accessoriesLayer('acc1', { card: { width_mm: 40, height_mm: 30, elements: [] } }),
    );
    select();
    fireEvent.doubleClick(screen.getByTestId('layer-acc1'));
    fireEvent.click(screen.getByRole('button', { name: 'Text' }));
    fireEvent.click(screen.getByRole('button', { name: 'Shape' }));
    fireEvent.click(screen.getByRole('button', { name: 'Picture' }));
    expect(cardOf(state)!.elements.map((e) => e.kind).sort()).toEqual(['picture', 'shape', 'text']);
  });

  it('Done leaves editing mode and brings the normal toolbar back', () => {
    mount();
    select();
    fireEvent.doubleClick(screen.getByTestId('layer-acc1'));
    fireEvent.click(screen.getByRole('button', { name: 'Done' }));
    expect(screen.queryByText(/Editing card:/)).toBeNull();
    expect(screen.queryByRole('button', { name: 'Colour dots' })).toBeNull();
  });

  it('Escape leaves editing mode', () => {
    mount();
    select();
    fireEvent.doubleClick(screen.getByTestId('layer-acc1'));
    expect(screen.getByText(/Editing card:/)).toBeInTheDocument();
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.queryByText(/Editing card:/)).toBeNull();
  });
});

describe('accessories box: footer editing mode', () => {
  it('Edit footer enters footer mode without a Picture tool', () => {
    mount();
    select();
    fireEvent.click(screen.getByRole('button', { name: 'Edit footer' }));
    expect(screen.getByText(/Editing footer:/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Picture' })).toBeNull();
    for (const name of ['Text', 'Colour dots', 'Shape', 'Done']) {
      expect(screen.getByRole('button', { name })).toBeInTheDocument();
    }
  });

  it('Colour dots in footer mode lands in footer.elements and shows the footer', () => {
    const state = mount();
    select();
    fireEvent.click(screen.getByRole('button', { name: 'Edit footer' }));
    fireEvent.click(screen.getByRole('button', { name: 'Colour dots' }));
    const footer = (state.layers[0].props as unknown as {
      footer?: { show: boolean; elements: { kind: string }[] };
    }).footer;
    expect(footer?.show).toBe(true);
    expect(footer?.elements.some((e) => e.kind === 'colour_dots')).toBe(true);
  });
});
