/**
 * PRICETAG-ACCESSORY-DESIGNER fix round: in the request designer (`linkedAccessoryBoxes="detach"`) a linked
 * box is detached before it is edited, in the same undo step as the card conversion; the template editor
 * keeps the link.
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

function mount(layer: TagLayer, mode?: 'live' | 'detach') {
  const state = { layers: [] as TagLayer[] };
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <TagCanvasEditor
        doc={docWith(layer)}
        onChange={vi.fn()}
        linkedAccessoryBoxes={mode}
        onLayersChange={(layers) => {
          state.layers = layers;
        }}
      />
    </QueryClientProvider>,
  );
  return state;
}

const presetOf = (state: { layers: TagLayer[] }) =>
  (state.layers[0].props as unknown as { presetId?: string | null }).presetId;

const card = { width_mm: 40, height_mm: 30, elements: [] };

describe('linked accessories box in the request designer', () => {
  it('detaches on entering the card editor', () => {
    const state = mount(accessoriesLayer('acc1', { presetId: 'p1', card }), 'detach');
    fireEvent.click(screen.getByTestId('layer-acc1'));
    fireEvent.click(screen.getByRole('button', { name: 'Edit card' }));
    expect(screen.getByText(/Editing card:/)).toBeInTheDocument();
    expect(presetOf(state) ?? null).toBeNull();
    expect(screen.queryByText(/Linked to/)).toBeNull();
  });

  it('detaches in the same step as converting a box with no card', () => {
    const state = mount(accessoriesLayer('acc1', { presetId: 'p1' }), 'detach');
    fireEvent.click(screen.getByTestId('layer-acc1'));
    fireEvent.doubleClick(screen.getByTestId('layer-acc1'));
    expect(presetOf(state) ?? null).toBeNull();
    expect((state.layers[0].props as unknown as { card?: unknown }).card).toBeDefined();
  });

  it('detaches when the box design is changed from the inspector', () => {
    const state = mount(accessoriesLayer('acc1', { presetId: 'p1', card }), 'detach');
    fireEvent.click(screen.getByTestId('layer-acc1'));
    fireEvent.click(screen.getByRole('checkbox', { name: 'Footer note' }));
    expect(presetOf(state) ?? null).toBeNull();
  });

  it('the template editor keeps the link', () => {
    const state = mount(accessoriesLayer('acc1', { presetId: 'p1', card }));
    fireEvent.click(screen.getByTestId('layer-acc1'));
    fireEvent.click(screen.getByRole('button', { name: 'Edit card' }));
    fireEvent.click(screen.getByRole('button', { name: 'Done' }));
    expect(presetOf(state)).toBe('p1');
  });
});

describe('box keys while a card is edited', () => {
  it('Delete with no element selected does not delete the box; arrows and duplicate do nothing to it', () => {
    const state = mount(accessoriesLayer('acc1', { card }));
    fireEvent.click(screen.getByTestId('layer-acc1'));
    fireEvent.doubleClick(screen.getByTestId('layer-acc1'));
    fireEvent.keyDown(window, { key: 'Delete' });
    fireEvent.keyDown(window, { key: 'ArrowRight' });
    fireEvent.keyDown(window, { key: 'd', ctrlKey: true });
    expect(state.layers).toHaveLength(1);
    expect(state.layers[0].x_mm).toBe(5);
    expect(screen.getByText(/Editing card:/)).toBeInTheDocument();
  });

  it('a leaving undo: the editor closes when the box no longer has a card', () => {
    mount(accessoriesLayer('acc1'));
    fireEvent.click(screen.getByTestId('layer-acc1'));
    fireEvent.doubleClick(screen.getByTestId('layer-acc1'));
    expect(screen.getByText(/Editing card:/)).toBeInTheDocument();
    fireEvent.keyDown(window, { key: 'z', ctrlKey: true });
    expect(screen.queryByText(/Editing card:/)).toBeNull();
  });
});
