/**
 * CollectionsList - search box behaviour.
 *
 * This is the list `TileDesignsList` and `BundlesList` copied their search
 * pattern from. Keep the same two guards pinned here: a whitespace-only
 * search on a genuinely empty list reads as "no collections yet" (not "no
 * matches"), and typing a term while on page 2 does not strand the grid on
 * an empty slice.
 */
import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

// Saved column widths are a per-user preference fetched over the network. Left
// real, the grid sits in its loading state forever under jsdom.
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

const { listCollections, deleteCollection } = vi.hoisted(() => ({
  listCollections: vi.fn(),
  deleteCollection: vi.fn(),
}));

vi.mock('../../services/catalogueService', () => ({
  listCollections,
  deleteCollection,
}));

vi.mock('./CollectionDialog', () => ({
  CollectionDialog: () => null,
}));

import type { CollectionSummary } from '@/lib/dealer-kit/types';
import { CollectionsList } from './CollectionsList';

function collection(id: string, name: string): CollectionSummary {
  return {
    id,
    name,
    scope: 'library',
    memberCount: 3,
    updatedAt: '2026-08-01T02:00:00',
  };
}

function renderList() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(
    <QueryClientProvider client={client}>
      <CollectionsList />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('CollectionsList search', () => {
  it('a whitespace-only search on a genuinely empty list shows the plain empty state', async () => {
    listCollections.mockResolvedValue([]);

    renderList();

    await screen.findByText('No reusable collections yet');
    fireEvent.change(screen.getByLabelText('Search collections'), {
      target: { value: '   ' },
    });

    expect(screen.getByText('No reusable collections yet')).toBeInTheDocument();
    expect(screen.queryByText(/no collections match that search/i)).toBeNull();
  });

  it('resets to page 1 when a search term is typed while on page 2', async () => {
    const manyRows: CollectionSummary[] = [
      collection('m1', 'Kitchen Sink A'),
      collection('m2', 'Kitchen Sink B'),
      collection('m3', 'Kitchen Sink C'),
      ...Array.from({ length: 10 }, (_, i) => collection(`nm${i}`, `Bath Rack ${i}`)),
    ];
    listCollections.mockResolvedValue(manyRows);

    renderList();

    await screen.findByText('Kitchen Sink A');
    expect(screen.queryByText('Bath Rack 8')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: /go to next page/i }));
    await screen.findByText('Bath Rack 8');
    expect(screen.queryByText('Kitchen Sink A')).toBeNull();

    fireEvent.change(screen.getByLabelText('Search collections'), {
      target: { value: 'kitchen' },
    });

    expect(await screen.findByText('Kitchen Sink A')).toBeInTheDocument();
    expect(screen.getByText('Kitchen Sink B')).toBeInTheDocument();
    expect(screen.getByText('Kitchen Sink C')).toBeInTheDocument();
    expect(screen.queryByText(/no collections match that search/i)).toBeNull();
  });
});
