/**
 * TAG-TEMPLATE-DUPLICATE item 4 (owner 6 Nov): the combo's Tag preview switches between its
 * LINKED templates (e.g. BF_LP and BF_SP). Order: Default LP, then Default SP, then the rest;
 * the preview opens on the first. Picking another redraws with that template, and Open (the
 * viewer's own button) opens whatever is drawn. Fixtures follow `ComboTagPreview.service.test.tsx`.
 */
import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const viewer = vi.hoisted(() => ({ payloads: [] as unknown[] }));
vi.mock('@/components/dealer-kit/DesignViewer', () => ({
  default: (props: { payload: unknown; headerActions?: React.ReactNode; docNumber: string }) => {
    viewer.payloads.push(props.payload);
    return (
      <div data-testid="design-viewer">
        {props.headerActions}
        <button type="button">Open {props.docNumber}</button>
        {props.payload ? 'drawn' : 'empty'}
      </div>
    );
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

const lp = link({ id: 'tpl-lp', name: 'BF_LP', price_type: 'list', default_list: true });
const sp = link({ id: 'tpl-sp', name: 'BF_SP', price_type: 'selling', default_selling: true });
const extra = link({ id: 'tpl-x', name: 'BF_EXTRA', price_type: 'selling' });

describe('ComboTagPreview linked-template switcher (item 4)', () => {
  it('lists the linked templates Default LP first, then Default SP, then the rest', async () => {
    state.links = [extra, sp, lp];
    draw(null);
    const group = await screen.findByRole('group', { name: 'Template to preview' });
    const names = Array.from(group.querySelectorAll('[role="radio"]')).map((b) => b.textContent);
    expect(names).toEqual(['BF_LP', 'BF_SP', 'BF_EXTRA']);
  });

  it('opens on the Default LP, drawn as list', async () => {
    state.links = [sp, lp];
    draw(null);
    await waitFor(() => expect(previewTags).toHaveBeenCalled());
    expect(sentLines(previewTags.mock.calls[0])[0]).toMatchObject({
      tag_template_id: 'tpl-lp',
      price_type: 'list',
    });
    expect(await screen.findByRole('radio', { name: /BF_LP/ })).toHaveAttribute('aria-checked', 'true');
  });

  it('opens on the first linked when there is no Default LP', async () => {
    state.links = [extra, sp];
    draw(null);
    await waitFor(() => expect(previewTags).toHaveBeenCalled());
    expect(sentLines(previewTags.mock.calls[0])[0]).toMatchObject({ tag_template_id: 'tpl-sp' });
  });

  it('picking BF_SP redraws with it as selling, and Open opens the selected one', async () => {
    state.links = [lp, sp];
    draw(null);
    await waitFor(() => expect(previewTags).toHaveBeenCalled());
    fireEvent.click(await screen.findByRole('radio', { name: /BF_SP/ }));

    await waitFor(() =>
      expect(sentLines(previewTags.mock.calls.at(-1)!)[0]).toMatchObject({
        tag_template_id: 'tpl-sp',
        price_type: 'selling',
      }),
    );
    expect(await screen.findByRole('button', { name: 'Open 3 in 1 - BF_SP' })).toBeInTheDocument();
  });

  it('shows no switcher with a single linked template', async () => {
    state.links = [lp];
    draw(null);
    await waitFor(() => expect(previewTags).toHaveBeenCalled());
    expect(screen.queryByRole('group', { name: 'Template to preview' })).toBeNull();
  });
});
