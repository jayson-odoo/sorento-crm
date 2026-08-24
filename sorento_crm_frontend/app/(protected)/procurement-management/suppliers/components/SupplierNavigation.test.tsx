/**
 * Tests for the SupplierNavigation wrapper (backend-driven prev/next pager).
 *
 * SupplierNavigation reads the list query carried in the detail URL via
 * `parseDetailSearch`, forwards it to the thin `useSupplierNeighbours` wrapper,
 * and feeds the result to RecordNavigation in IDs mode. Covers:
 * - forwards the parsed list query (search/sort) to useSupplierNeighbours
 * - renders the "index / total" counter from the hook result
 * - "… / total" while loading
 * - stepping to a neighbour preserves the list query string in the URL
 * - Prev/Next disabled when the corresponding id is null
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import SupplierNavigation from './SupplierNavigation';

const push = vi.fn();
// Detail URL search string the list page would have produced (search + sort).
let searchParamsString = 'page=1&limit=50&sort=supplier_name&dir=asc&query=acme';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push }),
  useSearchParams: () => new URLSearchParams(searchParamsString),
}));

const useSupplierNeighbours = vi.fn();
vi.mock('../hooks/useSuppliers', () => ({
  useSupplierNeighbours: (...args: unknown[]) => useSupplierNeighbours(...args),
}));

describe('SupplierNavigation', () => {
  beforeEach(() => {
    push.mockClear();
    useSupplierNeighbours.mockReset();
    searchParamsString = 'page=1&limit=50&sort=supplier_name&dir=asc&query=acme';
    useSupplierNeighbours.mockReturnValue({
      prevId: 'p1',
      nextId: 'n1',
      index: 3,
      total: 23,
      isLoading: false,
    });
  });

  it('forwards the parsed list query (search/sort) to useSupplierNeighbours', () => {
    render(<SupplierNavigation supplierId="s-current" />);
    expect(useSupplierNeighbours).toHaveBeenCalledTimes(1);
    const [supplierId, listParams] = useSupplierNeighbours.mock.calls[0];
    expect(supplierId).toBe('s-current');
    expect(listParams).toMatchObject({
      pageIndex: 0,
      pageSize: 50,
      searchQuery: 'acme',
      sorting: [{ id: 'supplier_name', desc: false }],
    });
  });

  it('renders the "index / total" counter from the hook result', () => {
    render(<SupplierNavigation supplierId="s-current" />);
    expect(screen.getByText('3 / 23')).toBeInTheDocument();
  });

  it('renders "… / total" while the neighbours query is loading', () => {
    useSupplierNeighbours.mockReturnValue({
      prevId: null,
      nextId: null,
      index: null,
      total: 23,
      isLoading: true,
    });
    render(<SupplierNavigation supplierId="s-current" />);
    expect(screen.getByText('… / 23')).toBeInTheDocument();
  });

  it('preserves the list query string when stepping to the next neighbour', () => {
    render(<SupplierNavigation supplierId="s-current" />);
    fireEvent.click(screen.getByLabelText('Next supplier'));
    expect(push).toHaveBeenCalledWith(
      '/procurement-management/suppliers/n1?page=1&limit=50&sort=supplier_name&dir=asc&query=acme',
    );
  });

  it('navigates to the previous neighbour without a query string when none is present', () => {
    searchParamsString = '';
    render(<SupplierNavigation supplierId="s-current" />);
    fireEvent.click(screen.getByLabelText('Previous supplier'));
    expect(push).toHaveBeenCalledWith('/procurement-management/suppliers/p1');
  });

  it('disables Prev/Next when the corresponding neighbour id is null', () => {
    useSupplierNeighbours.mockReturnValue({
      prevId: null,
      nextId: 'n1',
      index: 1,
      total: 5,
      isLoading: false,
    });
    render(<SupplierNavigation supplierId="s-current" />);
    expect(screen.getByLabelText('Previous supplier')).toBeDisabled();
    expect(screen.getByLabelText('Next supplier')).not.toBeDisabled();
  });
});
