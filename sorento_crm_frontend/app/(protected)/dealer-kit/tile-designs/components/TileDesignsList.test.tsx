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
});
