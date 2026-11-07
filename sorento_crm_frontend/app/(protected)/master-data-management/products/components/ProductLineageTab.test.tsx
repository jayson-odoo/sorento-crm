/**
 * NPA-FROM-SI: the product Lineage tab. Real hook and service; only the network edge (`apiFetch`)
 * is stubbed so the HTTP status decides the screen: a 500 is an error message, a 403 (refusal)
 * still reads as the empty state, and an empty answer is the empty state.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const net = vi.hoisted(() => ({ fetch: vi.fn() }));
vi.mock('@/lib/api', async (importOriginal) => {
  const original = await importOriginal<typeof import('@/lib/api')>();
  return { ...original, apiFetch: (...a: unknown[]) => net.fetch(...a) };
});

import ProductLineageTab from './ProductLineageTab';

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });

const row = (over: Record<string, unknown> = {}) => ({
  application_no: 'NPA-000123',
  product_id: 'p-69',
  product_code: 'SRTWB893',
  product_name: 'Wall hung basin',
  is_active: true,
  current_products: [{ id: 'p-1', product_code: 'SRTWB888' }],
  description: 'no tap hole & overflow',
  expected_qty: '270',
  created_at: '2026-11-03T02:00:00',
  ...over,
});

function renderTab() {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <ProductLineageTab productId="p-69" />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('Lineage tab states', () => {
  it('shows the error message, not the empty state, when the request fails with 500', async () => {
    net.fetch.mockResolvedValue(json(500, { detail: 'boom' }));
    renderTab();
    expect(await screen.findByText('Could not load the lineage.')).toBeInTheDocument();
    expect(screen.queryByText('No lineage')).toBeNull();
  });

  it('still shows the empty state when the read is refused with 403', async () => {
    net.fetch.mockResolvedValue(json(403, { detail: 'Forbidden' }));
    renderTab();
    expect(await screen.findByText('No lineage')).toBeInTheDocument();
    expect(screen.queryByText('Could not load the lineage.')).toBeNull();
  });

  it('shows the empty state heading and hint when there is no lineage', async () => {
    net.fetch.mockResolvedValue(json(200, { created_from: [], made_from_this: [] }));
    renderTab();
    expect(await screen.findByText('No lineage')).toBeInTheDocument();
    expect(
      screen.getByText('Codes created through a New Product Application show here.'),
    ).toBeInTheDocument();
    expect(screen.queryByText('Could not load the lineage.')).toBeNull();
  });

  it('keeps both tables with their column headers', async () => {
    net.fetch.mockResolvedValue(
      json(200, {
        created_from: [row({ application_id: 'a-1', customer_name: 'EXAMPLE DEVELOPER', project_name: 'TOWER B' })],
        made_from_this: [row({ application_no: 'NPA-000200', product_id: 'p-70', product_code: 'SRTWB894', application_id: 'a-2' })],
      }),
    );
    renderTab();
    expect(await screen.findByText('Created from')).toBeInTheDocument();
    expect(screen.getByText('New codes made from this product')).toBeInTheDocument();
    const heads = screen.getAllByRole('columnheader').map((h) => (h.textContent ?? '').trim());
    for (const h of ['New code', 'From product codes', 'Why', 'Application', 'Customer / project', 'Qty', 'Created']) {
      expect(heads, h).toContain(h);
    }
  });

  it('says None for the table that has no rows', async () => {
    net.fetch.mockResolvedValue(
      json(200, { created_from: [row()], made_from_this: [] }),
    );
    renderTab();
    expect(await screen.findByText('Created from')).toBeInTheDocument();
    expect(screen.getByText('None')).toBeInTheDocument();
  });
});
