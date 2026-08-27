/**
 * R18 / AC-F4 - the factory picker on a packing-list screen: server-searched, read by NAME.
 *
 * Two rules, and the second is why this file exists twice over. The code is ours, the name is
 * what the operator calls the factory, and "(400-K029)" after every entry is noise on a list
 * that is read by name; it stays in `searchText`, so typing a code still finds the supplier.
 * And the search is the SERVER's: the picker used to be handed the one page `/select` returns
 * without a query - 100 rows of 194 - and filter it in the browser, so typing JINBAICHUAN
 * answered "No supplier found." while the endpoint returned it.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

const searchSuppliers = vi.fn();
vi.mock('../../suppliers/services/supplierService', () => ({
  searchSuppliersForSelect: (...a: unknown[]) => searchSuppliers(...a),
}));

type Option = { value: string; label: string; searchText?: string };

const captured: {
  fetchOptions?: (query: string, page: number) => Promise<Option[]>;
  selectedOption?: Option;
} = {};

// The real SearchableSelect drives a cmdk popover; this test is about what the wrapper hands
// it - the fetcher and the resolved value - not about popover mechanics.
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: {
    fetchOptions?: (query: string, page: number) => Promise<Option[]>;
    selectedOption?: Option;
  }) => {
    captured.fetchOptions = props.fetchOptions;
    captured.selectedOption = props.selectedOption;
    return <div data-testid="select">{props.selectedOption?.label ?? ''}</div>;
  },
}));

import { SupplierCombobox } from './SupplierCombobox';

const SUPPLIERS = [
  { id: 'sup-a', supplier_code: '400-K029', supplier_name: 'KAILU HARDWARE FACTORY' },
  { id: 'sup-b', supplier_code: '400-C011', supplier_name: 'CAIZHOU SANITARY' },
];

beforeEach(() => {
  searchSuppliers.mockReset();
  captured.fetchOptions = undefined;
  captured.selectedOption = undefined;
});

describe('SupplierCombobox', () => {
  it('searches the server, so a factory past the first page is reachable', async () => {
    searchSuppliers.mockResolvedValue([
      { value: 'sup-z', label: 'CHAOZHOU JINBAICHUAN', searchText: '400-J001 CHAOZHOU JINBAICHUAN' },
    ]);
    render(<SupplierCombobox value="" onChange={vi.fn()} suppliers={SUPPLIERS} />);

    const found = await captured.fetchOptions!('JINBAICHUAN', 0);

    expect(searchSuppliers).toHaveBeenCalledWith('JINBAICHUAN');
    expect(found.map((o) => o.label)).toEqual(['CHAOZHOU JINBAICHUAN']);
  });

  it('shows a saved supplier straight away, without waiting for a search', async () => {
    render(<SupplierCombobox value="sup-b" onChange={vi.fn()} suppliers={SUPPLIERS} />);

    await waitFor(() => expect(screen.getByTestId('select').textContent).toBe('CAIZHOU SANITARY'));
    expect(captured.selectedOption?.value).toBe('sup-b');
  });

  it('shows a saved supplier the page only knows from the record itself', async () => {
    render(
      <SupplierCombobox
        value="sup-z"
        onChange={vi.fn()}
        suppliers={SUPPLIERS}
        supplierFallback={{
          id: 'sup-z',
          supplier_code: '400-J001',
          supplier_name: 'CHAOZHOU JINBAICHUAN',
        }}
      />,
    );

    await waitFor(() =>
      expect(screen.getByTestId('select').textContent).toBe('CHAOZHOU JINBAICHUAN'),
    );
  });

  it('labels by name alone and keeps the code searchable', () => {
    render(<SupplierCombobox value="sup-a" onChange={vi.fn()} suppliers={SUPPLIERS} />);

    expect(captured.selectedOption?.label).toBe('KAILU HARDWARE FACTORY');
    expect(captured.selectedOption?.searchText).toContain('400-K029');
    expect(captured.selectedOption?.searchText).toContain('KAILU HARDWARE FACTORY');
  });
});
