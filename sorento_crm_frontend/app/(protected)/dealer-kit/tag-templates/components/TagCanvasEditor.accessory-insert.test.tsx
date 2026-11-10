/**
 * PRICETAG-ACCESSORY-DESIGNER fix round: in the request designer (`linkedAccessoryBoxes="detach"`) a linked
 * box is detached before it is edited, in the same undo step as the card conversion; the template editor
 * keeps the link.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { TagLayer, TagTemplateDoc } from '@/lib/dealer-kit/tag-template-types';
import { accessoryDesign, designKey } from '@/lib/dealer-kit/accessory-card';
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

const FRESH = {
  id: 'p1',
  name: 'FREE',
  used_in: 1,
  updated_at: 'U2',
  design: { direction: 'vertical', headerText: 'SERVER', card: { width_mm: 40, height_mm: 30, elements: [] } },
};
const hookStub = () => ({ data: undefined, isLoading: false, mutate: vi.fn(), mutateAsync: vi.fn(), run: vi.fn() });
vi.mock('../../accessory-templates/hooks/useAccessoryTemplates', () => ({
  // The menu list is STALE (U1); a fresh read (refetch) answers U2.
  useAccessoryTemplatesQuery: () => ({
    data: [{ ...FRESH, updated_at: 'U1', design: { ...FRESH.design, headerText: 'STALE' } }],
    refetch: async () => ({ data: [FRESH] }),
  }),
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


function mount(layers: TagLayer[], inserted: (...args: unknown[]) => void) {
  const state = { layers: [] as TagLayer[] };
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <TagCanvasEditor
        doc={docWith(...layers)}
        onChange={vi.fn()}
        onAccessoryTemplateInserted={inserted as never}
        onLayersChange={(next) => {
          state.layers = next;
        }}
      />
    </QueryClientProvider>,
  );
  return state;
}

describe('inserting a saved template', () => {
  it('uses the fresh design, makes an older box of the same template follow it, and reports the version', async () => {
    const inserted = vi.fn();
    const older = accessoriesLayer('old1', {
      presetId: 'p1',
      headerText: 'OLDER',
      card: { width_mm: 40, height_mm: 30, elements: [] },
    });
    const state = mount([older], inserted);
    fireEvent.click(await screen.findByRole('button', { name: /Add Accessories/ }));
    fireEvent.click(await screen.findByText('FREE'));
    await waitFor(() => expect(inserted).toHaveBeenCalled());
    expect(inserted).toHaveBeenCalledWith('p1', expect.objectContaining({ headerText: 'SERVER' }), 'U2');
    const headers = state.layers.map((l) => (l.props as unknown as { headerText: string }).headerText);
    expect(headers).toEqual(['SERVER', 'SERVER']);
  });
});
