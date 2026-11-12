/**
 * COMBO-SETTINGS-UX rule 2 (owner 10 Nov: Q1 (a), Q5 yes): the combo preview lets the reader pick an
 * option per pick-one group, and an upgrade, and draws the tag the way a request line with those picks
 * prints, without saving anything. The line goes out as a real request line does
 * (`product_tag_template_service.preview`): a fixed part `{product_id, role: null}`, a picked option
 * `{product_id, role}`, an open group `{role, candidates}`, an upgrade under the role `Upgrade`.
 * Nothing picked = every option open (Q1 (a)).
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const viewer = vi.hoisted(() => ({ payloads: [] as unknown[] }));
vi.mock('@/components/dealer-kit/DesignViewer', () => ({
  default: (props: { payload: unknown }) => {
    viewer.payloads.push(props.payload);
    return <div data-testid="design-viewer">{props.payload ? 'drawn' : 'empty'}</div>;
  },
}));

const state = vi.hoisted(() => ({ links: [] as unknown[] }));
vi.mock('@/app/(protected)/dealer-kit/hooks/useProductTagTemplates', () => ({
  useComboTagTemplates: () => ({ data: state.links, isLoading: false, isError: false }),
}));
vi.mock('@/app/(protected)/dealer-kit/hooks/usePublishedTagTemplates', () => ({
  usePublishedTagTemplates: () => ({ data: [], isLoading: false, isError: false }),
}));

const TEMPLATE = {
  id: 'tpl-sp',
  name: 'Bathroom Furniture SP',
  family: 'ala_carte',
  doc: { layers: [], width_mm: 85, height_mm: 58 },
  print_size: { width_mm: 85, height_mm: 58 },
};
const SLOTS = {
  main: { product_id: 'prod-1', code: 'SRTBF11416', name: 'Cabinet', images: [] },
  fixed: [{ product_id: 'p-mirror', code: 'MIRROR', name: 'Mirror', images: [] }],
  groups: [],
  upgrades: [],
};

const previewTags = vi.hoisted(() => vi.fn());
vi.mock('@/app/(protected)/dealer-kit/services/tagDataService', async (original) => ({
  ...(await original<Record<string, unknown>>()),
  previewTags,
}));

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: {
    value: string;
    onChange: (v: string) => void;
    options?: { value: string; label: string }[];
    'aria-label'?: string;
    placeholder?: string;
  }) => (
    <select aria-label={props['aria-label']} value={props.value} onChange={(e) => props.onChange(e.target.value)}>
      <option value="">{props.placeholder}</option>
      {(props.options ?? []).map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  ),
}));

import { ComboTagPreview } from './ComboTagPreview';

/** The sent line, wherever the service puts its lines. */
function sentLines(args: unknown[]): Array<Record<string, unknown>> {
  const found: Array<Record<string, unknown>> = [];
  const walk = (value: unknown) => {
    if (Array.isArray(value)) value.forEach(walk);
    else if (value && typeof value === 'object') {
      const record = value as Record<string, unknown>;
      if ('product_id' in record && 'line_type' in record) found.push(record);
      else Object.values(record).forEach(walk);
    }
  };
  args.forEach(walk);
  return found;
}

beforeEach(() => {
  viewer.payloads = [];
  state.links = [];
  previewTags.mockReset();
  previewTags.mockImplementation(async (...args: unknown[]) => {
    const key = String(sentLines(args)[0]?.key ?? 'k');
    return {
      lines: [
        {
          line_id: key,
          tag_id: key,
          code: 'SRTBF11416',
          name: 'Cabinet',
          list_price: 730,
          sell_price: 459,
          images: [{ attachment_id: 'img-1', url: 'https://cdn.example.test/cabinet.jpg' }],
          slots: SLOTS,
          combo: { id: 'combo-3', name: '3 in 1', description: '<p>stored</p>', free_items: 'Free tap', choices: [], upgrades: [] },
        },
      ],
      templates: { [key]: TEMPLATE },
      assets: {},
      images: {},
      fonts: [],
    };
  });
});

const part = (id: string, product_id: string, code: string, over: Record<string, unknown> = {}) => ({
  id,
  combo_id: 'combo-k',
  product_id,
  code,
  product_name: code,
  dimensions: null,
  choice_group: null,
  sort_order: 0,
  ...over,
});
const SINK_COMBO = {
  id: 'combo-k',
  host_product_id: 'prod-1',
  name: 'SRTKS7061-BL',
  sort_order: 0,
  parts: [
    part('pt-drainer', 'p-drainer', 'BK002'),
    part('pt-t1', 'p-t1', 'SRTKT1633SS-BL', { choice_group: 'TAP', sell_price: '899.00' }),
    part('pt-t2', 'p-t2', 'SRTKT1634SS-BL', { choice_group: 'TAP', sell_price: '899.00' }),
    part('pt-t3', 'p-t3', 'SRTKT71SS-BL', { choice_group: 'TAP', sell_price: '1099.00' }),
    part('pt-up', 'p-up', 'SRTKT1690-BL', { is_upgrade: true, topup_amount: '150.00' }),
  ],
  created_at: '2026-11-01T00:00:00Z',
  updated_at: '2026-11-01T00:00:00Z',
};
const LINK = {
  id: 'tpl-sp', name: 'KS_2TAP_SP', family: 'ala_carte', published: true, width_mm: 85, height_mm: 58,
  price_type: 'selling', is_default: false, default_list: false, default_selling: true,
};

function draw(combo: unknown = SINK_COMBO) {
  state.links = [LINK];
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const ui = (c: unknown) => (
    <QueryClientProvider client={client}>
      <ComboTagPreview combo={c as never} description={null} />
    </QueryClientProvider>
  );
  const view = render(ui(combo));
  return { ...view, redraw: (c: unknown) => view.rerender(ui(c)) };
}

const lastParts = () => sentLines(previewTags.mock.calls.at(-1) ?? [])[0]?.parts;

describe('ComboTagPreview, preview with choices', () => {
  it('with nothing picked sends the fixed parts and every group open (Q1 a), the upgrade open', async () => {
    draw();
    await waitFor(() => expect(previewTags).toHaveBeenCalled());
    expect(lastParts()).toEqual([
      { product_id: 'p-drainer', role: null },
      { role: 'TAP', candidates: ['p-t1', 'p-t2', 'p-t3'] },
      { role: 'Upgrade', candidates: ['p-up'] },
    ]);
  });

  it('offers a picker per pick-one group, by code, starting on No pick, named on screen (review S2)', async () => {
    draw();
    const tap = await screen.findByLabelText('Preview TAP');
    expect(screen.getByText('TAP')).toBeInTheDocument();
    expect(screen.getByText('Upgrade')).toBeInTheDocument();
    expect((tap as HTMLSelectElement).value).toBe('');
    expect([...tap.querySelectorAll('option')].map((o) => o.textContent)).toEqual([
      'No pick',
      'SRTKT1633SS-BL',
      'SRTKT1634SS-BL',
      'SRTKT71SS-BL',
    ]);
  });

  it('picking a tap redraws with that tap placed, nothing saved', async () => {
    draw();
    fireEvent.change(await screen.findByLabelText('Preview TAP'), { target: { value: 'p-t2' } });
    await waitFor(() =>
      expect(lastParts()).toEqual([
        { product_id: 'p-drainer', role: null },
        { product_id: 'p-t2', role: 'TAP' },
        { role: 'Upgrade', candidates: ['p-up'] },
      ]),
    );
  });

  it('picking the upgrade sends it under the Upgrade role (Q5)', async () => {
    draw();
    fireEvent.change(await screen.findByLabelText('Preview Upgrade'), { target: { value: 'p-up' } });
    await waitFor(() => expect(lastParts()).toContainEqual({ product_id: 'p-up', role: 'Upgrade' }));
  });

  it('a pick whose option was removed from the combo goes back to No pick', async () => {
    const { redraw } = draw();
    fireEvent.change(await screen.findByLabelText('Preview TAP'), { target: { value: 'p-t2' } });
    await waitFor(() => expect(lastParts()).toContainEqual({ product_id: 'p-t2', role: 'TAP' }));
    redraw({ ...SINK_COMBO, parts: SINK_COMBO.parts.filter((p) => p.product_id !== 'p-t2') });
    await waitFor(() => expect(lastParts()).toContainEqual({ role: 'TAP', candidates: ['p-t1', 'p-t3'] }));
    expect((screen.getByLabelText('Preview TAP') as HTMLSelectElement).value).toBe('');
  });

  it('a one-option group is placed as a fixed part (owner round 1), with no picker; a combo with nothing to pick shows none', async () => {
    draw({
      ...SINK_COMBO,
      parts: [part('pt-a', 'p-a', 'BASIN-1', { choice_group: 'BASIN' }), part('pt-f', 'p-f', 'WASTE')],
    });
    await waitFor(() =>
      expect(lastParts()).toEqual([
        { product_id: 'p-a', role: null },
        { product_id: 'p-f', role: null },
      ]),
    );
    expect(screen.queryByLabelText(/^Preview /)).toBeNull();
  });

  it('shows no pickers while there is no published template to draw (review N4)', async () => {
    state.links = [];
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <ComboTagPreview combo={SINK_COMBO as never} description={null} />
      </QueryClientProvider>,
    );
    await screen.findByText('No price tag template linked');
    expect(screen.queryByLabelText('Preview TAP')).toBeNull();
  });
});
