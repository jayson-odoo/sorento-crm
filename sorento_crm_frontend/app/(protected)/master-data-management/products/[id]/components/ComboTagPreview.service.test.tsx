/**
 * PRICETAG-COMBO-FORMAT R18: the combo live preview is drawn from the SAME pipeline as the request
 * preview and the PDF. It asks a staff service (`POST /api/v1/dealer-kit/tag-preview`) for ONE line
 * and draws the response's line, template and images through `DesignViewer`, overriding only
 * `combo.description` with the editor's unsaved draft. A hand-built line (no slots, parts, images)
 * resolved nothing for position-bound layers or the price badge.
 *
 * Written test-FIRST. Contract read literally, flagged: the service function is `previewTags` in
 * `app/(protected)/dealer-kit/services/tagDataService.ts` (the ruling gives that as an example). Its
 * argument shape is not fixed, so the sent line is found anywhere in the call arguments.
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
vi.mock('@/app/(protected)/dealer-kit/services/tagDataService', async (original) => ({
  ...(await original<Record<string, unknown>>()),
  previewTags,
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

const combo = {
  id: 'combo-3',
  host_product_id: 'prod-1',
  name: '3 in 1',
  sort_order: 0,
  parts: [],
  created_at: '2026-11-01T00:00:00Z',
  updated_at: '2026-11-01T00:00:00Z',
};
const link = (over: Record<string, unknown>) => ({
  id: 'tpl-sp',
  name: 'Bathroom Furniture SP',
  family: 'ala_carte',
  published: true,
  width_mm: 85,
  height_mm: 58,
  price_type: 'both',
  is_default: false,
  default_list: false,
  default_selling: false,
  ...over,
});

function draw(description: string | null) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const tree = (text: string | null) => (
    <QueryClientProvider client={client}>
      <ComboTagPreview combo={combo as never} description={text} />
    </QueryClientProvider>
  );
  const view = render(tree(description));
  return { rerender: (text: string | null) => view.rerender(tree(text)) };
}

const drawn = () => viewer.payloads.filter(Boolean).at(-1) as {
  resolvedData: Record<string, Record<string, unknown>>;
  images: Record<string, string>;
};
const resolvedLine = () => Object.values(drawn().resolvedData)[0];

describe('ComboTagPreview asks the staff preview service (R18)', () => {
  it('R18: sends ONE product line for the host and combo, on the SP default as selling', async () => {
    // TAG-TEMPLATE-DUPLICATE item 4: a link that is BOTH defaults now opens as the LP default
    // (owner 6 Nov: Default LP first); the SP-only default is still drawn as selling.
    state.links = [link({ default_selling: true })];
    draw('<p>draft</p>');
    await waitFor(() => expect(previewTags).toHaveBeenCalled());

    const lines = sentLines(previewTags.mock.calls[0]);
    expect(lines).toHaveLength(1);
    expect(lines[0]).toMatchObject({
      line_type: 'product',
      product_id: 'prod-1',
      combo_id: 'combo-3',
      tag_template_id: 'tpl-sp',
      price_type: 'selling',
    });
  });

  it('R18: a default that is only the LP default is sent as list', async () => {
    state.links = [link({ default_list: true })];
    draw('<p>draft</p>');
    await waitFor(() => expect(previewTags).toHaveBeenCalled());

    expect(sentLines(previewTags.mock.calls[0])[0]).toMatchObject({ tag_template_id: 'tpl-sp', price_type: 'list' });
  });

  it('R18: draws the response line (slots, images, prices) with only the description replaced by the draft', async () => {
    state.links = [link({ default_selling: true })];
    draw('<p>the draft</p>');
    await waitFor(() => expect(drawn()).toBeTruthy());

    const line = resolvedLine();
    expect(line.slots).toEqual(SLOTS);
    expect(line.list_price).toBe(730);
    expect(line.sell_price).toBe(459);
    expect(line.images).toEqual([{ attachment_id: 'img-1', url: 'https://cdn.example.test/cabinet.jpg' }]);
    expect(drawn().images['img-1']).toBe('https://cdn.example.test/cabinet.jpg');
    const shownCombo = line.combo as Record<string, unknown>;
    expect(shownCombo.description).toBe('<p>the draft</p>');
    expect(shownCombo.free_items).toBe('Free tap');
    expect(shownCombo.name).toBe('3 in 1');
  });

  it('R18: typing changes the drawn description without losing the response data', async () => {
    state.links = [link({ default_selling: true })];
    const view = draw('<p>first</p>');
    await waitFor(() => expect(drawn()).toBeTruthy());

    view.rerender('<p>second</p>');

    await waitFor(() => expect((resolvedLine().combo as Record<string, unknown>).description).toBe('<p>second</p>'));
    expect(resolvedLine().slots).toEqual(SLOTS);
  });
});

describe('ComboTagPreview draws the feature icons (SPEC-ICON-COMBINED follow-up F4)', () => {
  it('FU-F4: hands the response feature_icons (with conditions) to the viewer', async () => {
    const icons = [
      { id: 'ic-s', name: 'S trap', spec_key: 'trap_type', values: ['s_trap'], conditions: [] },
      {
        id: 'ic-s150',
        name: 'S trap 150mm',
        spec_key: 'trap_length',
        values: ['150'],
        conditions: [{ spec_key: 'trap_type', value: 's_trap' }],
      },
    ];
    const base = previewTags.getMockImplementation()!;
    previewTags.mockImplementation(async (...args: unknown[]) => ({ ...(await base(...args)), feature_icons: icons }));
    state.links = [link({ default_selling: true })];
    draw('<p>x</p>');
    await waitFor(() => expect(drawn()).toBeTruthy());

    expect((drawn() as unknown as { featureIcons: unknown[] }).featureIcons).toEqual(icons);
  });
});

describe('ComboTagPreview empty states (R18 keeps them)', () => {
  it('R18: no link at all says "No price tag template linked" and does not call the service', async () => {
    state.links = [];
    draw('<p>x</p>');
    expect(await screen.findByText('No price tag template linked')).toBeInTheDocument();
    expect(previewTags).not.toHaveBeenCalled();
  });

  it('R18: a default that is not published says "No published price tag template"', async () => {
    state.links = [link({ default_selling: true, published: false })];
    previewTags.mockResolvedValue({ lines: [], templates: {}, assets: {}, images: {}, fonts: [] });
    draw('<p>x</p>');
    expect(await screen.findByText('No published price tag template')).toBeInTheDocument();
    expect(screen.queryByText('No price tag template linked')).toBeNull();
  });

  it('reviewer should-fix: a failed preview says it could not load, never that a template is missing', async () => {
    state.links = [link({ default_selling: true })];
    previewTags.mockRejectedValue(new Error('500'));
    draw('<p>x</p>');
    expect(await screen.findByText('Could not load the tag preview')).toBeInTheDocument();
    expect(screen.queryByText('No published price tag template')).toBeNull();
    expect(screen.queryByText('No price tag template linked')).toBeNull();
  });
});
