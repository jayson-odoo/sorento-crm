/**
 * PRICETAG-ACC-LABELS (owner 7 Nov): the template designer shows the SAME standing warning the
 * request preview shows ("1 accessory does not fit its box", `FeatureIconDropWarning`) while a
 * previewed product or combo has more accessories than the box can draw. Before this lane the
 * designer only toasted once on an increase and warned inside the inspector of a SELECTED box.
 *
 * Written red-first. Harness copied from `TagCanvasEditor.combo-preview.test.tsx`.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { TagLayer, TagTemplateDoc } from '@/lib/dealer-kit/tag-template-types';
import { defaultAccessoriesProps } from '@/lib/dealer-kit/tag-template-types';
import { accessoryBoxLayout, accessoryLineCount } from '@/lib/dealer-kit/accessory-box';

vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() } }));

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
  }: {
    layer: TagLayer;
    display?: { text?: string; imageUrl?: string | null };
  }) => (
    <div data-testid={`layer-${layer.id}`} data-image={display?.imageUrl ?? ''}>
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
  listAssets: vi.fn(async () => []),
  listFontAssets: vi.fn(async () => []),
}));

const COMBO_OPTION = { value: 'combo-1', label: '3 in 1', description: 'ZZHOST1' };

const tagData = vi.hoisted(() => ({
  getProductTagData: vi.fn(),
  comboOptions: vi.fn(),
}));

vi.mock('../../services/tagDataService', () => ({
  productOptions: vi.fn(async () => []),
  productSetOptions: vi.fn(async () => []),
  listSpecKeys: vi.fn(async () => []),
  comboOptions: tagData.comboOptions,
  getProductTagData: tagData.getProductTagData,
  getProductSetTagData: vi.fn(async () => {
    throw new Error('not used');
  }),
}));

/** Records every SearchableSelect so a test can reach the Preview combo one. */
const selects = vi.hoisted(() => ({ props: [] as Record<string, unknown>[] }));
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: {
    value: string;
    onChange: (v: string) => void;
    options?: { value: string; label: string }[];
    fetchOptions?: (q: string, page: number) => Promise<{ value: string; label: string }[]>;
    placeholder?: string;
    clearable?: boolean;
    'aria-label'?: string;
  }) => {
    selects.props.push(props as unknown as Record<string, unknown>);
    const label = props['aria-label'] ?? props.placeholder ?? '';
    return (
      <select
        aria-label={label}
        data-clearable={String(!!props.clearable)}
        value={props.value ?? ''}
        onChange={(event) => props.onChange(event.target.value)}
      >
        <option value="">-</option>
        <option value={COMBO_OPTION.value}>{COMBO_OPTION.label}</option>
      </select>
    );
  },
}));

import { TagCanvasEditor } from './TagCanvasEditor';

const ACCESSORIES = [
  { id: 'a1', name: 'SRTW5000', spec: 'Waste', image: null },
  { id: 'a2', name: 'COLANDER', spec: 'Colander', image: null },
  { id: 'a3', name: 'DRAINER', spec: 'Drainer', image: null },
];

function box(width_mm: number, height_mm: number): TagLayer {
  return {
    id: 'acc',
    type: 'accessories',
    x_mm: 0,
    y_mm: 0,
    width_mm,
    height_mm,
    rotation_deg: 0,
    z_index: 1,
    locked: false,
    visible: true,
    slot_binding: null,
    text_override: null,
    props: defaultAccessoriesProps(),
  } as TagLayer;
}

const doc = (layer: TagLayer): TagTemplateDoc => ({ width_mm: 200, height_mm: 200, layers: [layer] });

const dropsFor = (layer: TagLayer) =>
  accessoryBoxLayout(
    ACCESSORIES.length,
    layer.props as ReturnType<typeof defaultAccessoriesProps>,
    layer.width_mm,
    layer.height_mm,
    accessoryLineCount(ACCESSORIES),
  ).dropped;

const COMBO_PRODUCT = {
  id: 'p-host',
  code: 'SRTWB7065',
  name: 'SRTWB7065',
  dimensions: '',
  spec_lines: [],
  specs: [],
  images: [],
  list_price: 1000,
  offer_price: null,
  promotion_id: null,
  barcode: null,
  accessories: [],
  combo: {
    id: 'combo-1',
    name: 'Basin with tap',
    description: '',
    free_items: null,
    accessories: ACCESSORIES,
    choices: [],
    upgrades: [],
  },
};

beforeEach(() => {
  vi.clearAllMocks();
  selects.props.length = 0;
  tagData.comboOptions.mockResolvedValue([COMBO_OPTION]);
  tagData.getProductTagData.mockResolvedValue(COMBO_PRODUCT);
});

async function previewCombo() {
  fireEvent.change(screen.getByLabelText(/Preview combo/i), { target: { value: 'combo-1' } });
  await waitFor(() => expect(tagData.getProductTagData).toHaveBeenCalled());
}

describe('Template designer: accessories drop warning', () => {
  it('shows "N accessory does not fit its box" when the previewed list overflows the box', async () => {
    const small = box(30, 20);
    const dropped = dropsFor(small);
    expect(dropped, 'fixture: the box must be too small').toBeGreaterThan(0);
    render(<TagCanvasEditor doc={doc(small)} onChange={vi.fn()} />);
    await previewCombo();
    const text =
      dropped === 1 ? '1 accessory does not fit its box' : `${dropped} accessories do not fit their box`;
    expect(await screen.findByText(text)).toBeInTheDocument();
  });

  it('says nothing when every accessory fits', async () => {
    const big = box(190, 190);
    expect(dropsFor(big), 'fixture: the box must fit all three').toBe(0);
    render(<TagCanvasEditor doc={doc(big)} onChange={vi.fn()} />);
    await previewCombo();
    await waitFor(() => expect(tagData.getProductTagData).toHaveBeenCalled());
    expect(screen.queryByText(/does not fit its box|do not fit their box/)).toBeNull();
  });

  it('says nothing for the sample cards of a box with nothing previewed', () => {
    render(<TagCanvasEditor doc={doc(box(30, 20))} onChange={vi.fn()} />);
    expect(screen.queryByText(/does not fit its box|do not fit their box/)).toBeNull();
  });
});
