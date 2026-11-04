/**
 * PRICETAG-COMBO: the template editor's Preview combo picker (AC-5.1).
 *
 * Written test-FIRST (PRINCIPLES.md Phase 2). The editor has no Preview combo control
 * yet, so every case is red on a missing element. Harness copied from
 * `TagCanvasEditor.preview.test.tsx` (Konva stood in for by a div per layer).
 *
 * Assumed shapes, for the captain to tighten with the coder: the control is a
 * SearchableSelect labelled "Preview combo", clearable, fed by
 * `tagDataService.comboOptions(query)` (option value = combo id), and a pick loads the
 * host with `getProductTagData(hostId, promotionId, comboId)`.
 */

import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
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
  combo: {
    id: 'combo-1',
    name: '3 in 1',
    description: 'Cabinet, mirror and basin',
    free_items: 'Tap, waste',
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

describe('TagCanvasEditor Preview combo (AC-5.1)', () => {
  it('shows a clearable Preview combo select', () => {
    render(<TagCanvasEditor doc={doc()} onChange={vi.fn()} />);
    const select = screen.getByLabelText(/Preview combo/i);
    expect(select).toHaveAttribute('data-clearable', 'true');
  });

  it('searches combos through the combo options service', async () => {
    render(<TagCanvasEditor doc={doc()} onChange={vi.fn()} />);
    const mine = selects.props.find(
      (props) => String(props['aria-label'] ?? props.placeholder ?? '').match(/Preview combo/i),
    ) as { fetchOptions?: (q: string, page: number) => Promise<unknown> } | undefined;
    expect(mine?.fetchOptions, 'the picker must search on the server').toBeTypeOf('function');
    await act(async () => {
      await mine!.fetchOptions!('3 in', 0);
    });
    expect(tagData.comboOptions).toHaveBeenCalledWith('3 in');
  });

  it('previews the picked combo: its name and description reach the canvas', async () => {
    render(<TagCanvasEditor doc={doc()} onChange={vi.fn()} />);
    fireEvent.change(screen.getByLabelText(/Preview combo/i), { target: { value: 'combo-1' } });

    await waitFor(() => expect(screen.getByTestId('layer-title')).toHaveTextContent('3 in 1'));
    expect(screen.getByTestId('layer-desc')).toHaveTextContent('Cabinet, mirror and basin');
    const calls = tagData.getProductTagData.mock.calls;
    expect(calls.some((args) => args.includes('combo-1'))).toBe(true);
  });

  it('clearing the pick goes back to what the template shows', async () => {
    render(<TagCanvasEditor doc={doc()} onChange={vi.fn()} />);
    const select = screen.getByLabelText(/Preview combo/i);
    fireEvent.change(select, { target: { value: 'combo-1' } });
    await waitFor(() => expect(screen.getByTestId('layer-title')).toHaveTextContent('3 in 1'));

    fireEvent.change(screen.getByLabelText(/Preview combo/i), { target: { value: '' } });
    await waitFor(() => expect(screen.getByTestId('layer-title')).not.toHaveTextContent('3 in 1'));
  });

  it('writes nothing it previewed into the document Save sends', async () => {
    const onChange = vi.fn();
    render(<TagCanvasEditor doc={doc()} onChange={onChange} />);
    fireEvent.change(screen.getByLabelText(/Preview combo/i), { target: { value: 'combo-1' } });
    await waitFor(() => expect(screen.getByTestId('layer-title')).toHaveTextContent('3 in 1'));

    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    const saved = onChange.mock.calls[0][0] as TagTemplateDoc;
    for (const saveLayer of saved.layers) {
      expect(saveLayer.text_override).toBeNull();
      expect(JSON.stringify(saveLayer)).not.toContain('3 in 1');
    }
  });
});
