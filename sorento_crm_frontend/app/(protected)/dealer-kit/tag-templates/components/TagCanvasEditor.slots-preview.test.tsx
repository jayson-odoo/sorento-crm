/**
 * PRICETAG-COMBO-RENDER fix round 1 (F1): the template editor names positions from the PREVIEWED combo.
 * Harness copied from `TagCanvasEditor.combo-preview.test.tsx`.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { TagLayer, TagTemplateDoc } from '@/lib/dealer-kit/tag-template-types';
import { defaultTextProps } from '@/lib/dealer-kit/tag-template-types';

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

function layer(id: string, slot: TagLayer['slot_binding'], text: string): TagLayer {
  return {
    id,
    type: 'text',
    x_mm: 0,
    y_mm: 0,
    width_mm: 40,
    height_mm: 8,
    rotation_deg: 0,
    z_index: 1,
    locked: false,
    visible: true,
    slot_binding: slot,
    text_override: null,
    props: { ...defaultTextProps(), text },
  };
}

function doc(): TagTemplateDoc {
  return {
    width_mm: 100,
    height_mm: 80,
    layers: [
      layer('title', 'combo_name' as TagLayer['slot_binding'], 'Combo title'),
      layer('desc', 'combo_description' as TagLayer['slot_binding'], 'Combo description'),
    ],
  };
}

const part = (code: string) => ({ product_id: `id-${code}`, code, name: code, dimensions: '' });
const COMBO_PRODUCT = {
  id: 'p-host',
  code: 'ZZHOST1',
  name: 'ZZHOST1',
  dimensions: '',
  spec_lines: [],
  specs: [],
  images: [],
  list_price: 1000,
  offer_price: null,
  promotion_id: null,
  barcode: null,
  combo: { id: 'combo-1', name: '3 in 1', description: null, free_items: null, choices: [], upgrades: [] },
  slots: {
    fixed: [],
    groups: [{ role: 'Kitchen tap', size: 2, picks: [part('SRTKT1862SS'), part('SRTKT1863SS')] }],
    upgrades: [],
  },
};

function slotDoc(): TagTemplateDoc {
  const l = layer('tap2', 'code', 'Code');
  (l.props as unknown as Record<string, unknown>).subjectSlot = { kind: 'pick', group: 0, index: 1 };
  return { width_mm: 100, height_mm: 80, layers: [l] };
}

beforeEach(() => {
  vi.clearAllMocks();
  selects.props.length = 0;
  tagData.comboOptions.mockResolvedValue([COMBO_OPTION]);
  tagData.getProductTagData.mockResolvedValue(COMBO_PRODUCT);
});

describe('TagCanvasEditor reads positions from the previewed combo (AC-A5, AC-A7)', () => {
  it('names the Layers suffix generically with nothing previewed', async () => {
    render(<TagCanvasEditor doc={slotDoc()} onChange={vi.fn()} />);
    expect(await screen.findByText(/Choice group 1, pick 2/)).toBeInTheDocument();
  });

  it('names it from the previewed combo once one is picked', async () => {
    render(<TagCanvasEditor doc={slotDoc()} onChange={vi.fn()} />);
    fireEvent.change(screen.getByLabelText(/Preview combo/i), { target: { value: 'combo-1' } });
    await waitFor(() => expect(screen.getAllByText(/Kitchen tap, pick 2/).length).toBeGreaterThan(0));
    expect(screen.queryByText(/Choice group 1, pick 2/)).toBeNull();
  });
});
