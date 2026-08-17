/**
 * The tile design list's search box.
 *
 * Every sibling list (collections, catalogues, editions, flyer readings) has a
 * search input above the grid; this one did not. Mirrors
 * `CollectionsList`'s client-side filter over the name.
 */
import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

// Saved column widths are a per-user preference fetched over the network. Left
// real, the grid sits in its loading state forever under jsdom and every
// assertion below passes or fails for a reason that has nothing to do with it.
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

const { listTileTemplates, deleteTileTemplate } = vi.hoisted(() => ({
  listTileTemplates: vi.fn(),
  deleteTileTemplate: vi.fn(),
}));

vi.mock('../../services/catalogueService', () => ({
  TILE_FIELDS: [
    { value: 'code', label: 'Code', hint: '' },
    { value: 'name', label: 'Name', hint: '' },
  ],
  listTileTemplates,
  deleteTileTemplate,
}));

vi.mock('./TileDesignDialog', () => ({
  TileDesignDialog: () => null,
}));

import type { TileTemplate } from '@/lib/dealer-kit/types';
import { TileDesignsList } from './TileDesignsList';

const ROWS: TileTemplate[] = [
  {
    id: 'tt-1',
    name: 'Standard bathware card',
    fields: ['code', 'name'],
    updatedAt: '2026-08-01T02:00:00',
  } as TileTemplate,
  {
    id: 'tt-2',
    name: 'Kitchen sink minimal',
    fields: ['name'],
    updatedAt: '2026-07-30T02:00:00',
  } as TileTemplate,
];

function renderList() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(
    <QueryClientProvider client={client}>
      <TileDesignsList />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('TileDesignsList search', () => {
  it('narrows the rows as you type and restores them when cleared', async () => {
    listTileTemplates.mockResolvedValue(ROWS);

    renderList();

    await screen.findByText('Standard bathware card');
    expect(screen.getByText('Kitchen sink minimal')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Search tile designs'), {
      target: { value: 'kitchen' },
    });

    expect(screen.queryByText('Standard bathware card')).toBeNull();
    expect(screen.getByText('Kitchen sink minimal')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Search tile designs'), { target: { value: '' } });

    expect(await screen.findByText('Standard bathware card')).toBeInTheDocument();
    expect(screen.getByText('Kitchen sink minimal')).toBeInTheDocument();
  });

  it('says a search matched nothing rather than reading as no designs at all', async () => {
    listTileTemplates.mockResolvedValue(ROWS);

    renderList();

    await screen.findByText('Standard bathware card');
    fireEvent.change(screen.getByLabelText('Search tile designs'), {
      target: { value: 'zzzz' },
    });

    expect(await screen.findByText(/no tile designs match that search/i)).toBeInTheDocument();
  });

  it('a whitespace-only search on a genuinely empty list shows the plain empty state', async () => {
    listTileTemplates.mockResolvedValue([]);

    renderList();

    await screen.findByText('No tile designs yet');
    fireEvent.change(screen.getByLabelText('Search tile designs'), {
      target: { value: '   ' },
    });

    expect(screen.getByText('No tile designs yet')).toBeInTheDocument();
    expect(screen.queryByText(/no tile designs match that search/i)).toBeNull();
  });

  it('resets to page 1 when a search term is typed while on page 2', async () => {
    const manyRows: TileTemplate[] = [
      { id: 'm1', name: 'Kitchen Sink A', fields: ['name'], updatedAt: '2026-08-01T02:00:00' },
      { id: 'm2', name: 'Kitchen Sink B', fields: ['name'], updatedAt: '2026-08-01T02:00:00' },
      { id: 'm3', name: 'Kitchen Sink C', fields: ['name'], updatedAt: '2026-08-01T02:00:00' },
      ...Array.from({ length: 10 }, (_, i) => ({
        id: `nm${i}`,
        name: `Bath Rack ${i}`,
        fields: ['name'],
        updatedAt: '2026-08-01T02:00:00',
      })),
    ] as TileTemplate[];
    listTileTemplates.mockResolvedValue(manyRows);

    renderList();

    await screen.findByText('Kitchen Sink A');
    // Page 1 shows the first 10 rows; "Bath Rack 8"/"9" only appear on page 2.
    expect(screen.queryByText('Bath Rack 8')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: /go to next page/i }));
    await screen.findByText('Bath Rack 8');
    expect(screen.queryByText('Kitchen Sink A')).toBeNull();

    fireEvent.change(screen.getByLabelText('Search tile designs'), {
      target: { value: 'kitchen' },
    });

    // The 3 matches were on the original page 1; if the pageIndex didn't reset,
    // the grid slices the 3-row filtered result starting at offset 10 -> empty.
    expect(await screen.findByText('Kitchen Sink A')).toBeInTheDocument();
    expect(screen.getByText('Kitchen Sink B')).toBeInTheDocument();
    expect(screen.getByText('Kitchen Sink C')).toBeInTheDocument();
    expect(screen.queryByText(/no tile designs match that search/i)).toBeNull();
  });
});
