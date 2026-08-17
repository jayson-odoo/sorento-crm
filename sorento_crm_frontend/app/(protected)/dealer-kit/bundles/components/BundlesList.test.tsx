/**
 * The bundle grid's search box.
 *
 * The grid stays a deliberate card layout - a table would hide the price and
 * the parts underneath, which is the whole point of a bundle - but every
 * sibling list has a search input, and until now this one did not.
 */
import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const { listBundles, deleteBundle } = vi.hoisted(() => ({
  listBundles: vi.fn(),
  deleteBundle: vi.fn(),
}));

vi.mock('../../services/catalogueService', () => ({
  listBundles,
  deleteBundle,
}));

vi.mock('./BundleDialog', () => ({
  BundleDialog: () => null,
}));

import type { ResolvedBundle } from '@/lib/dealer-kit/types';
import { BundlesList } from './BundlesList';

function bundle(id: string, name: string, productName: string): ResolvedBundle {
  return {
    id,
    name,
    price: 'RM 199.00',
    available: true,
    unavailableReason: null,
    components: [
      {
        productId: `${id}-p1`,
        productCode: `CODE-${id}`,
        productName,
        quantity: 1,
        allocated: 'RM 199.00',
        available: true,
      },
    ],
  };
}

const BUNDLES: ResolvedBundle[] = [
  bundle('bd-1', 'Master Bath Set', 'Rain Shower Head'),
  bundle('bd-2', 'Kitchen Starter Kit', 'Pull-out Tap'),
];

function renderList() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(
    <QueryClientProvider client={client}>
      <BundlesList />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('BundlesList search', () => {
  it('narrows the cards by name as you type and restores them when cleared', async () => {
    listBundles.mockResolvedValue(BUNDLES);

    renderList();

    await screen.findByText('Master Bath Set');
    expect(screen.getByText('Kitchen Starter Kit')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Search bundles'), { target: { value: 'kitchen' } });

    expect(screen.queryByText('Master Bath Set')).toBeNull();
    expect(screen.getByText('Kitchen Starter Kit')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Search bundles'), { target: { value: '' } });

    expect(await screen.findByText('Master Bath Set')).toBeInTheDocument();
    expect(screen.getByText('Kitchen Starter Kit')).toBeInTheDocument();
  });

  it('also matches on a component inside the bundle', async () => {
    listBundles.mockResolvedValue(BUNDLES);

    renderList();

    await screen.findByText('Master Bath Set');
    fireEvent.change(screen.getByLabelText('Search bundles'), {
      target: { value: 'pull-out tap' },
    });

    expect(screen.queryByText('Master Bath Set')).toBeNull();
    expect(screen.getByText('Kitchen Starter Kit')).toBeInTheDocument();
  });

  it('says a search matched nothing rather than reading as no bundles at all', async () => {
    listBundles.mockResolvedValue(BUNDLES);

    renderList();

    await screen.findByText('Master Bath Set');
    fireEvent.change(screen.getByLabelText('Search bundles'), { target: { value: 'zzzz' } });

    expect(await screen.findByText(/no bundles match that search/i)).toBeInTheDocument();
  });

  it('a whitespace-only search on a genuinely empty list shows the plain empty state', async () => {
    listBundles.mockResolvedValue([]);

    renderList();

    await screen.findByText('No bundles yet');
    fireEvent.change(screen.getByLabelText('Search bundles'), { target: { value: '   ' } });

    expect(screen.getByText('No bundles yet')).toBeInTheDocument();
    expect(screen.queryByText(/no bundles match that search/i)).toBeNull();
  });
});
