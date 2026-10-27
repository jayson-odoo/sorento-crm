/**
 * FILTER-MULTISELECT PR4: the Stock ledger's Transaction type filter takes several types (OR within the
 * filter), comma-joined to the data hook. Product ID and Warehouse ID stay text boxes. Harness mirrors
 * StockLedgerList.test.tsx (hook mocked).
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
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
const hookCalls = vi.hoisted(() => [] as Array<Record<string, unknown>>);
vi.mock('../hooks/useStockLedger', () => ({
  useStockLedger: (params: Record<string, unknown>) => {
    hookCalls.push(params);
    return {
      data: {
        data: [{
          id: '1', product_id: 'p-1', warehouse_id: 'w-1', transaction_type: 'BULK_IMPORT', quantity_change: 4,
          previous_quantity: 5, new_quantity: 9, reference_type: null, reference_id: null, notes: null,
          created_by: 'u1', created_by_name: 'ZZT User', created_at: new Date('2026-09-26T08:00:00Z'),
          product: { id: 'p-1', product_code: 'ZZT-LEDGER', product_name: 'Tile' }, warehouse: { id: 'w-1', warehouse_name: 'MBS' },
        }],
        pagination: { page: 1, limit: 50, total: 1 },
      },
      isLoading: false, isPlaceholderData: false, isFetching: false, refetch: vi.fn(),
    };
  },
}));
vi.mock('@/components/common/SearchableMultiSelect', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/components/common/SearchableMultiSelect')>();
  type Props = Parameters<typeof actual.SearchableMultiSelect>[0];
  const Stub = ({ value, onChange, options, placeholder }: Props) => (
    <select multiple aria-label={placeholder ?? 'multi'} value={value}
      onChange={(e) => onChange(Array.from(e.target.selectedOptions, (o) => o.value))}>
      {(options ?? []).map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  );
  return { ...actual, SearchableMultiSelect: (props: Props) => <Stub {...props} /> };
});

import StockLedgerList from './StockLedgerList';

const setOf = (v: unknown): string[] =>
  (Array.isArray(v) ? v.map(String) : String(v ?? '').split(',')).map((s) => s.trim()).filter(Boolean).sort();
const lastParams = () => hookCalls[hookCalls.length - 1];
const boxesWith = (value: string) =>
  screen.queryAllByRole('listbox').filter(
    (el) => el.hasAttribute('multiple') && el.querySelector(`option[value="${value}"]`),
  ) as HTMLSelectElement[];
async function box(value: string) {
  await waitFor(() => {
    if (!boxesWith(value).length) throw new Error(`no multi control offering option "${value}"`);
  });
  return boxesWith(value)[0];
}
const filtersButton = () => screen.getByRole('button', { name: /^filters/i });

async function openFilters(user: ReturnType<typeof userEvent.setup>) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  render(
    <QueryClientProvider client={client}>
      <StockLedgerList />
    </QueryClientProvider>,
  );
  await screen.findByText('ZZT-LEDGER');
  await user.click(filtersButton());
}

beforeEach(() => {
  hookCalls.length = 0;
  Element.prototype.scrollIntoView = vi.fn();
});
afterEach(() => cleanup());

describe('Stock ledger - multi Transaction type filter', () => {
  it('Transaction type is a multi control', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    expect((await box('BULK_IMPORT')).hasAttribute('multiple')).toBe(true);
  });

  it('two types reach the hook as a set of two and the badge counts one filter', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    await user.selectOptions(await box('BULK_IMPORT'), ['BULK_IMPORT', 'AUTOCOUNT_PUSH']);
    await waitFor(() => expect(setOf(lastParams().transaction_type)).toEqual(['AUTOCOUNT_PUSH', 'BULK_IMPORT']));
    await user.keyboard('{Escape}');
    await waitFor(() => expect(within(filtersButton()).getByText('1')).toBeInTheDocument());
  });

  it('types AND with the warehouse box', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    await user.selectOptions(await box('BULK_IMPORT'), ['SYSTEM_ADJUSTMENT', 'AUTOCOUNT_PUSH']);
    await user.type(screen.getByPlaceholderText('Warehouse ID'), 'wh-9');
    await waitFor(() => {
      expect(setOf(lastParams().transaction_type)).toEqual(['AUTOCOUNT_PUSH', 'SYSTEM_ADJUSTMENT']);
      expect(lastParams().warehouse_id).toBe('wh-9');
    });
  });

  it('Clear filters drops the type filter', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    await user.selectOptions(await box('BULK_IMPORT'), ['BULK_IMPORT', 'AUTOCOUNT_PUSH']);
    await waitFor(() => expect(setOf(lastParams().transaction_type)).toEqual(['AUTOCOUNT_PUSH', 'BULK_IMPORT']));
    await user.click(screen.getByRole('button', { name: /clear filters/i }));
    await waitFor(() => expect(setOf(lastParams().transaction_type)).toEqual([]));
  });
});
