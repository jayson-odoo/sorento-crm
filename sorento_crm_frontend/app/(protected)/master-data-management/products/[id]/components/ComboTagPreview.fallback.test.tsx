/**
 * COMBO-SETTINGS-UX owner round 1 (10 Nov 18:2x): the owner must always see the description rendered
 * with THIS combo's real values. When the tag cannot draw it (no template linked, none published, or
 * the template has no field that prints the description), the panel says which in plain words and
 * still shows the description as it prints, from the combo's own tag data
 * (`GET /dealer-kit/products/{host}/tag-data?combo_id=`).
 */
import { render, screen, waitFor } from '@testing-library/react';
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
const getProductTagData = vi.hoisted(() => vi.fn());
vi.mock('@/app/(protected)/dealer-kit/services/tagDataService', async (original) => ({
  ...(await original<Record<string, unknown>>()),
  previewTags,
  getProductTagData,
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

const BF_DATA = {
  id: 'prod-1',
  code: 'SRTBF11829',
  name: 'Cabinet',
  dimensions: '',
  spec_lines: [],
  images: [],
  slots: {
    main: { product_id: 'prod-1', code: 'SRTBF11829', name: 'Cabinet', dimensions: '', dimensions_lwh: 'L780xW480xH400mm' },
    fixed: [{ product_id: 'p-basin', code: 'SRTWB2380', name: 'Basin', dimensions: '', dimensions_lwh: '' }],
    groups: [],
    upgrades: [],
  },
  combo: {
    id: 'combo-3', name: 'BF', description: 'stored', free_items: null, choices: [], upgrades: [],
    main_label: 'CABINET', parts_line: null, part_labels: { 'p-basin': 'BASIN' },
  },
};

const combo = {
  id: 'combo-3',
  host_product_id: 'prod-1',
  name: 'BF',
  sort_order: 0,
  parts: [],
  created_at: '2026-11-01T00:00:00Z',
  updated_at: '2026-11-01T00:00:00Z',
};
const link = (over: Record<string, unknown>) => ({
  id: 'tpl-sp', name: 'Bathroom furniture combo', family: 'ala_carte', published: true,
  width_mm: 85, height_mm: 58, price_type: 'selling', is_default: false, default_list: false,
  default_selling: true, ...over,
});

function draw(description: string | null) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ComboTagPreview combo={combo as never} description={description} />
    </QueryClientProvider>,
  );
}

function answerWith(layers: unknown[]) {
  previewTags.mockImplementation(async (...args: unknown[]) => {
    const key = String(sentLines(args)[0]?.key ?? 'k');
    return {
      lines: [{ line_id: key, tag_id: key, code: 'SRTBF11829', name: 'Cabinet', images: [], slots: BF_DATA.slots, combo: BF_DATA.combo }],
      templates: { [key]: { ...TEMPLATE, doc: { ...TEMPLATE.doc, layers } } },
      assets: {}, images: {}, fonts: [],
    };
  });
}

const DESCRIPTION = '<p><strong>5 IN 1</strong></p><p>{{combo.parts}}</p>';

beforeEach(() => {
  getProductTagData.mockReset();
  getProductTagData.mockResolvedValue(BF_DATA);
});

describe('the description always shows with this combo\'s real values', () => {
  it('no template linked: says so, and shows the description as it prints', async () => {
    state.links = [];
    draw(DESCRIPTION);
    expect(await screen.findByText('No price tag template linked')).toBeInTheDocument();
    expect(await screen.findByText('SRTBF11829 (CABINET)')).toBeInTheDocument();
    expect(screen.getByText('SRTWB2380 (BASIN)')).toBeInTheDocument();
    expect(screen.getByText('L780xW480xH400mm')).toBeInTheDocument();
    expect(getProductTagData).toHaveBeenCalledWith('prod-1', null, 'combo-3');
  });

  it('a template that is not published: says so, and shows the description', async () => {
    state.links = [link({ published: false })];
    draw(DESCRIPTION);
    expect(await screen.findByText('No published price tag template')).toBeInTheDocument();
    expect(await screen.findByText('SRTBF11829 (CABINET)')).toBeInTheDocument();
  });

  it('a template with no field for the description: names it, and shows the description under the tag', async () => {
    state.links = [link({})];
    answerWith([{ id: 'code', type: 'text', slot_binding: 'code', props: { kind: 'text', text: '' } }]);
    draw(DESCRIPTION);
    expect(
      await screen.findByText('"Bathroom furniture combo" has no field that prints the combo description.'),
    ).toBeInTheDocument();
    expect(await screen.findByText('SRTBF11829 (CABINET)')).toBeInTheDocument();
    expect(screen.getByTestId('design-viewer')).toBeInTheDocument();
  });

  it('a template that prints the description: the tag alone, no note', async () => {
    state.links = [link({})];
    answerWith([{ id: 'd', type: 'text', slot_binding: null, props: { kind: 'text', text: '{{combo.description}}' } }]);
    draw(DESCRIPTION);
    await waitFor(() => expect(screen.getByTestId('design-viewer')).toBeInTheDocument());
    expect(screen.queryByText(/has no field that prints/)).toBeNull();
  });

  it('unlinking the template takes the drawn tag away at once, without a reload (crew pass D1)', async () => {
    state.links = [link({})];
    answerWith([{ id: 'd', type: 'text', slot_binding: null, props: { kind: 'text', text: '{{combo.description}}' } }]);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const tree = () => (
      <QueryClientProvider client={client}>
        <ComboTagPreview combo={combo as never} description={DESCRIPTION} />
      </QueryClientProvider>
    );
    const view = render(tree());
    await waitFor(() => expect(screen.getByTestId('design-viewer')).toBeInTheDocument());
    state.links = [];
    view.rerender(tree());
    expect(await screen.findByText('No price tag template linked')).toBeInTheDocument();
    expect(screen.queryByTestId('design-viewer')).toBeNull();
  });
});
