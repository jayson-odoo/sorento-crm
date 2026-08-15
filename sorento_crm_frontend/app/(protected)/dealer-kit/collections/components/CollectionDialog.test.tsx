/**
 * A collection, as a record you can open.
 *
 * The complaint was "collection is what purpose already ah", and the honest
 * reading of it is that a collection did not behave like a record: the list
 * could show them and delete them, but there was no way to create one and no
 * way to open one. The only route in was picking products inside a page editor
 * and promoting the result.
 *
 * The other half of the answer - what a collection is FOR - belongs in the user
 * guide, not on the screen, so what this file pins is that the form states what
 * the collection resolves to RIGHT NOW. A rule earns its keep by picking up
 * products added after it was written, so that is the only honest answer and
 * only the server can give it.
 */
import React from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

vi.mock('../../services/catalogueService', () => ({
  createCollection: vi.fn(),
  updateCollection: vi.fn(),
  resolveCollection: vi.fn(),
}));

// The picker has its own file of tests, and it fetches products and photos.
vi.mock('../../components/ProductPickerDialog', () => ({
  EMPTY_SELECTION: { conditions: null, pinnedProductIds: [], excludedProductIds: [] },
  ProductPickerDialog: ({ open }: { open: boolean }) =>
    open ? <div data-testid="picker" /> : null,
}));

import {
  createCollection,
  resolveCollection,
  updateCollection,
} from '../../services/catalogueService';
import { CollectionDialog } from './CollectionDialog';

const mockCreate = vi.mocked(createCollection);
const mockUpdate = vi.mocked(updateCollection);
const mockResolve = vi.mocked(resolveCollection);

const EXISTING = {
  id: 'c-1',
  name: 'Bathroom best sellers',
  scope: 'library' as const,
  memberCount: 2,
  updatedAt: '2026-08-04T00:00:00',
};

function renderDialog(collection: typeof EXISTING | null = null) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <CollectionDialog open onOpenChange={vi.fn()} collection={collection} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockCreate.mockResolvedValue({} as never);
  mockUpdate.mockResolvedValue({} as never);
  mockResolve.mockResolvedValue({
    collectionId: 'c-1',
    tiles: [
      { productId: 'p-1', productCode: 'SRTWB3401', productName: 'Wall Basin' },
      { productId: 'p-2', productCode: 'SRTBT1855', productName: 'Freestanding Bath' },
    ],
  } as never);
});

describe('CollectionDialog', () => {
  it('creates a named library collection', async () => {
    renderDialog(null);

    await act(async () => {
      fireEvent.change(screen.getByLabelText(/name/i), { target: { value: 'Best sellers' } });
    });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /^save$/i }));
    });

    await waitFor(() =>
      expect(mockCreate).toHaveBeenCalledWith(
        expect.objectContaining({ scope: 'library', name: 'Best sellers' }),
      ),
    );
  });

  it('will not save a collection with no name', () => {
    renderDialog(null);

    expect(screen.getByRole('button', { name: /^save$/i })).toBeDisabled();
  });

  it('opens an existing collection with its name filled in', () => {
    renderDialog(EXISTING);

    expect(screen.getByLabelText(/name/i)).toHaveValue('Bathroom best sellers');
    expect(screen.getByText(/edit collection/i)).toBeInTheDocument();
  });

  it('says what the collection holds RIGHT NOW, resolved by the server', async () => {
    // Not the pins. A rule picks up products added after it was written, so
    // "what is in it" changes without anybody editing this record.
    renderDialog(EXISTING);

    await waitFor(() => expect(screen.getByText(/2 products right now/i)).toBeInTheDocument());
    expect(screen.getByText('SRTWB3401')).toBeInTheDocument();
    expect(screen.getByText('Freestanding Bath')).toBeInTheDocument();
  });

  it('says so when a collection currently matches nothing', async () => {
    mockResolve.mockResolvedValue({ collectionId: 'c-1', tiles: [] } as never);

    renderDialog(EXISTING);

    await waitFor(() =>
      expect(screen.getByText(/nothing matches yet/i)).toBeInTheDocument(),
    );
  });

  it('updates rather than creating when a collection is open', async () => {
    renderDialog(EXISTING);

    await act(async () => {
      fireEvent.change(screen.getByLabelText(/name/i), { target: { value: 'Renamed' } });
    });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /^save$/i }));
    });

    await waitFor(() =>
      expect(mockUpdate).toHaveBeenCalledWith('c-1', expect.objectContaining({ name: 'Renamed' })),
    );
    expect(mockCreate).not.toHaveBeenCalled();
  });

  it('opens the same product picker the page editor uses', async () => {
    // A second way to choose products would be a second idea of what choosing
    // means.
    renderDialog(null);

    expect(screen.queryByTestId('picker')).toBeNull();
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /choose products/i }));
    });
    expect(screen.getByTestId('picker')).toBeInTheDocument();
  });

  it('does not explain what a collection is for on the screen', () => {
    // That belongs in the user guide. The dialog says what this control does,
    // not how the feature works.
    renderDialog(null);

    expect(screen.queryByText(/resolved at read time/i)).toBeNull();
    expect(screen.queryByText(/rule engine/i)).toBeNull();
  });
});
