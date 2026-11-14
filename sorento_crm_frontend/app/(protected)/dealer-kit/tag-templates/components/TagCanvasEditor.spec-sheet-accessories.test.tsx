/**
 * SPEC-SHEET-DESIGNER-PARITY B2: the Accessories tool is offered on a spec sheet template
 * (today hidden: `onAddAccessories={specSheet ? undefined : ...}`). Written test-FIRST.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { TagLayer, TagTemplateDoc } from '@/lib/dealer-kit/tag-template-types';

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

function docWith(): TagTemplateDoc {
  return { width_mm: 338.7, height_mm: 190.5, layers: [] };
}

function mount(specSheet: boolean) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <TagCanvasEditor doc={docWith()} onChange={vi.fn()} specSheet={specSheet} />
    </QueryClientProvider>,
  );
}

describe('the Accessories tool on a spec sheet template (B2)', () => {
  it('is offered when editing a spec sheet template', async () => {
    mount(true);
    expect(await screen.findByRole('button', { name: /Add Accessories/ })).toBeTruthy();
  });

  it('is still offered on a price tag template', async () => {
    mount(false);
    expect(await screen.findByRole('button', { name: /Add Accessories/ })).toBeTruthy();
  });
});
