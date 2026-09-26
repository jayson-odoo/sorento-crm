/**
 * Stock Ledger list - the Type column and filter know the AutoCount push (#1257, round 2).
 *
 * Pinned: an AUTOCOUNT_PUSH row reads "AutoCount push" (not the raw code), the known types
 * read as words, an unknown type still shows its raw code, and the Type filter offers the
 * push type. `useListingColumnPreferences` is mocked because the DataGrid renders no rows in
 * jsdom without it.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  STOCK_LEDGER_TRANSACTION_TYPE_OPTIONS,
  stockLedgerTypeLabel,
  type StockLedgerEntry,
} from '../types/stockLedger.types';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
  });
}

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }),
  usePathname: () => '/inventory-management/stock-ledger',
  useSearchParams: () => new URLSearchParams(''),
}));

vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

function entry(id: string, code: string, transaction_type: string): StockLedgerEntry {
  return {
    id,
    product_id: `p-${id}`,
    warehouse_id: `w-${id}`,
    transaction_type,
    quantity_change: 4,
    previous_quantity: 5,
    new_quantity: 9,
    reference_type: null,
    reference_id: null,
    notes: null,
    created_by: 'u1',
    created_by_name: 'AutoCount ESB',
    created_at: new Date('2026-09-26T08:00:00Z'),
    product: { id: `p-${id}`, product_code: code, product_name: 'Tile' },
    warehouse: { id: `w-${id}`, warehouse_name: 'MBS' },
  };
}

const rows: StockLedgerEntry[] = [
  entry('1', 'SKU-PUSH', 'AUTOCOUNT_PUSH'),
  entry('2', 'SKU-BULK', 'BULK_IMPORT'),
  entry('3', 'SKU-ODD', 'LEGACY_THING'),
];

const hookCalls: Array<{ transaction_type?: string }> = [];

vi.mock('../hooks/useStockLedger', () => ({
  useStockLedger: (params: { transaction_type?: string }) => {
    hookCalls.push(params);
    return {
      data: { data: rows, pagination: { page: 1, limit: 50, total: rows.length } },
      isLoading: false,
      isPlaceholderData: false,
      isFetching: false,
      refetch: vi.fn(),
    };
  },
}));

import StockLedgerList from './StockLedgerList';

function renderList() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return render(
    <QueryClientProvider client={client}>
      <StockLedgerList />
    </QueryClientProvider>,
  );
}

function rowFor(code: string): HTMLElement {
  return screen.getByText(code).closest('tr') as HTMLElement;
}

beforeEach(() => {
  hookCalls.length = 0;
});

describe('StockLedgerList - Type column', () => {
  it('labels an AutoCount push row in words', () => {
    renderList();
    expect(within(rowFor('SKU-PUSH')).getByText('AutoCount push')).toBeInTheDocument();
    expect(within(rowFor('SKU-PUSH')).queryByText('AUTOCOUNT_PUSH')).toBeNull();
  });

  it('labels a bulk import row in words', () => {
    renderList();
    expect(within(rowFor('SKU-BULK')).getByText('Bulk import')).toBeInTheDocument();
  });

  it('shows an unknown type as its raw code', () => {
    renderList();
    expect(within(rowFor('SKU-ODD')).getByText('LEGACY_THING')).toBeInTheDocument();
  });

  it('asks the server for every type until a filter is picked', () => {
    renderList();
    expect(hookCalls.at(-1)?.transaction_type).toBeUndefined();
  });
});

describe('Stock ledger transaction types', () => {
  it('offers the AutoCount push in the Type filter', () => {
    expect(STOCK_LEDGER_TRANSACTION_TYPE_OPTIONS).toContainEqual({
      value: 'AUTOCOUNT_PUSH',
      label: 'AutoCount push',
    });
    expect(STOCK_LEDGER_TRANSACTION_TYPE_OPTIONS.map((o) => o.value)).toEqual(
      expect.arrayContaining(['BULK_IMPORT', 'SYSTEM_ADJUSTMENT', 'AUTOCOUNT_PUSH']),
    );
  });

  it('maps codes to labels with a raw fallback', () => {
    expect(stockLedgerTypeLabel('AUTOCOUNT_PUSH')).toBe('AutoCount push');
    expect(stockLedgerTypeLabel('SYSTEM_ADJUSTMENT')).toBe('System adjustment');
    expect(stockLedgerTypeLabel('LEGACY_THING')).toBe('LEGACY_THING');
  });
});
