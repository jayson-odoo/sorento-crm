/**
 * PRICETAG-ACC-LABELS (owner 7 Nov): the combo editor's tag preview warns when an accessories box
 * is too small for its list. `DesignViewer` draws `FeatureIconDropWarning` from
 * `accessoryDrops(payload.doc, payload.resolvedData)` (covered in its own tests), so this pins the
 * other half: the payload `ComboTagPreview` hands it carries the tag label and the lists the box
 * reads, for the default box (the combo's list) and a Main-pinned box (the main product's own).
 */
import { render, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { accessoryDrops } from '@/lib/dealer-kit/accessory-drops';
import { accessoryBoxLayout, accessoryLineCount } from '@/lib/dealer-kit/accessory-box';
import { defaultAccessoriesProps, type TagSheetDoc } from '@/lib/dealer-kit/tag-template-types';

const viewer = vi.hoisted(() => ({ payloads: [] as unknown[] }));
vi.mock('@/components/dealer-kit/DesignViewer', () => ({
  default: (props: { payload: unknown }) => {
    viewer.payloads.push(props.payload);
    return <div data-testid="design-viewer" />;
  },
}));

vi.mock('@/app/(protected)/dealer-kit/hooks/useProductTagTemplates', () => ({
  useComboTagTemplates: () => ({
    data: [
      {
        id: 'tpl-1',
        name: 'Basin LP',
        family: 'ala_carte',
        published: true,
        width_mm: 85,
        height_mm: 58,
        price_type: 'list',
        is_default: true,
        default_list: true,
        default_selling: false,
      },
    ],
    isLoading: false,
    isError: false,
  }),
}));

const ITEMS = [
  { id: 'a1', name: 'SRTW5000', spec: 'Waste', image: null },
  { id: 'a2', name: 'COLANDER', spec: 'Colander', image: null },
];
const box = { props: defaultAccessoriesProps(), width_mm: 20, height_mm: 15 };
const pinned = { kind: 'main' } as const;

const layer = (subjectSlot?: { kind: 'main' }) => ({
  id: 'acc',
  type: 'accessories',
  x_mm: 0,
  y_mm: 0,
  width_mm: box.width_mm,
  height_mm: box.height_mm,
  rotation_deg: 0,
  z_index: 1,
  locked: false,
  visible: true,
  slot_binding: null,
  text_override: null,
  props: { ...box.props, ...(subjectSlot ? { subjectSlot } : {}) },
});

const state = vi.hoisted(() => ({ pinned: false, mainItems: [] as unknown[], comboItems: [] as unknown[] }));
const previewTags = vi.hoisted(() => vi.fn());
vi.mock('@/app/(protected)/dealer-kit/services/tagDataService', async (original) => ({
  ...(await original<Record<string, unknown>>()),
  previewTags,
}));

import { ComboTagPreview } from './ComboTagPreview';

beforeEach(() => {
  viewer.payloads = [];
  previewTags.mockReset();
  previewTags.mockImplementation(async () => ({
    lines: [
      {
        line_id: 'combo-preview',
        tag_id: 'combo-preview',
        tag_label: '1a',
        code: 'SRTWB7065',
        name: 'Basin',
        list_price: 500,
        sell_price: 400,
        images: [],
        parts: [],
        specs: [],
        open_groups: [],
        // The tag's list on a combo line is the combo's; the main product keeps its own. The two
        // lists differ per case, so a box that ignored its pin would report the wrong one.
        accessories: state.comboItems,
        slots: {
          main: { product_id: 'p-basin', code: 'SRTWB7065', name: 'Basin', images: [], accessories: state.mainItems },
          fixed: [{ product_id: 'p-tap', code: 'SRTWT7202', name: 'Tap', images: [] }],
          groups: [],
          upgrades: [],
        },
        combo: { id: 'combo-1', name: 'Basin with tap', description: '', free_items: null, accessories: state.comboItems, choices: [], upgrades: [] },
      },
    ],
    templates: {
      'combo-preview': {
        id: 'tpl-1',
        name: 'Basin LP',
        family: 'ala_carte',
        doc: { width_mm: 85, height_mm: 58, layers: [layer(state.pinned ? pinned : undefined)] },
        print_size: { width_mm: 85, height_mm: 58 },
      },
    },
    assets: {},
    images: {},
    fonts: [],
  }));
});

const combo = {
  id: 'combo-1',
  host_product_id: 'p-basin',
  name: 'Basin with tap',
  sort_order: 0,
  parts: [],
  created_at: '2026-11-01T00:00:00Z',
  updated_at: '2026-11-01T00:00:00Z',
};

async function dropsDrawn() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <ComboTagPreview combo={combo as never} description={null} />
    </QueryClientProvider>,
  );
  await waitFor(() => expect(viewer.payloads.filter(Boolean).length).toBeGreaterThan(0));
  const payload = viewer.payloads.filter(Boolean).at(-1) as {
    doc: TagSheetDoc;
    resolvedData: Record<string, never>;
  };
  return accessoryDrops(payload.doc, (tagId) => payload.resolvedData[tagId] ?? null);
}

const expected = accessoryBoxLayout(ITEMS.length, box.props, box.width_mm, box.height_mm, accessoryLineCount(ITEMS))
  .dropped;

describe('Combo tag preview: accessories drop warning', () => {
  it('fixture: the box is too small for the list', () => {
    expect(expected).toBeGreaterThan(0);
  });

  it('a default box on the combo tag reports the combo list\'s drops under the tag label', async () => {
    Object.assign(state, { pinned: false, comboItems: ITEMS, mainItems: [] });
    expect(await dropsDrawn()).toEqual([{ tagLabel: '1a', dropped: expected }]);
  });

  it('a default box ignores the main product\'s own list', async () => {
    Object.assign(state, { pinned: false, comboItems: [], mainItems: ITEMS });
    expect(await dropsDrawn()).toEqual([]);
  });

  it('a Main-pinned box reports drops from the main product\'s own list', async () => {
    Object.assign(state, { pinned: true, comboItems: [], mainItems: ITEMS });
    expect(await dropsDrawn()).toEqual([{ tagLabel: '1a', dropped: expected }]);
  });

  it('a Main-pinned box never reports the combo list\'s drops (lists stay independent)', async () => {
    Object.assign(state, { pinned: true, comboItems: ITEMS, mainItems: [] });
    expect(await dropsDrawn()).toEqual([]);
  });
});
