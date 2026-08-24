/**
 * Tests for the ProductNavigation wrapper (backend-driven prev/next pager).
 *
 * ProductNavigation reads the list query carried in the detail URL via
 * `parseDetailSearch`, forwards it to the thin `useProductNeighbours` wrapper,
 * and feeds the result to RecordNavigation in IDs mode. Covers:
 * - forwards the parsed list query (search/sort + product filters) to the hook
 * - renders the "index / total" counter from the hook result
 * - "… / total" while loading
 * - stepping to a neighbour preserves the list query string in the URL
 * - Prev/Next disabled when the corresponding id is null
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import ProductNavigation from './ProductNavigation';

const push = vi.fn();
// Detail URL search string the list page would have produced (search + sort +
// category/status filters), using the SAME param names as the list GET.
let searchParamsString =
  'page=1&limit=50&sort=product_name&dir=asc&query=basin&category_id=cat-1&status=active';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push }),
  useSearchParams: () => new URLSearchParams(searchParamsString),
}));

const useProductNeighbours = vi.fn();
vi.mock('../../hooks/useProducts', () => ({
  useProductNeighbours: (...args: unknown[]) => useProductNeighbours(...args),
}));

describe('ProductNavigation', () => {
  beforeEach(() => {
    push.mockClear();
    useProductNeighbours.mockReset();
    searchParamsString =
      'page=1&limit=50&sort=product_name&dir=asc&query=basin&category_id=cat-1&status=active';
    useProductNeighbours.mockReturnValue({
      prevId: 'p1',
      nextId: 'n1',
      index: 3,
      total: 23,
      isLoading: false,
    });
  });

  it('forwards the parsed list query (search/sort/filters) to useProductNeighbours', () => {
    render(<ProductNavigation productId="prod-current" />);
    expect(useProductNeighbours).toHaveBeenCalledTimes(1);
    const [productId, listParams] = useProductNeighbours.mock.calls[0];
    expect(productId).toBe('prod-current');
    expect(listParams).toMatchObject({
      pageIndex: 0,
      pageSize: 50,
      searchQuery: 'basin',
      sorting: [{ id: 'product_name', desc: false }],
      category_id: 'cat-1',
      status: 'active',
    });
  });

  it('renders the "index / total" counter from the hook result', () => {
    render(<ProductNavigation productId="prod-current" />);
    expect(screen.getByText('3 / 23')).toBeInTheDocument();
  });

  it('renders "… / total" while the neighbours query is loading', () => {
    useProductNeighbours.mockReturnValue({
      prevId: null,
      nextId: null,
      index: null,
      total: 23,
      isLoading: true,
    });
    render(<ProductNavigation productId="prod-current" />);
    expect(screen.getByText('… / 23')).toBeInTheDocument();
  });

  it('preserves the list query string when stepping to the next neighbour', () => {
    render(<ProductNavigation productId="prod-current" />);
    fireEvent.click(screen.getByLabelText('Next product'));
    expect(push).toHaveBeenCalledWith(
      '/master-data-management/products/n1?page=1&limit=50&sort=product_name&dir=asc&query=basin&category_id=cat-1&status=active',
    );
  });

  it('navigates to the previous neighbour without a query string when none is present', () => {
    searchParamsString = '';
    render(<ProductNavigation productId="prod-current" />);
    fireEvent.click(screen.getByLabelText('Previous product'));
    expect(push).toHaveBeenCalledWith('/master-data-management/products/p1');
  });

  it('disables Prev/Next when the corresponding neighbour id is null', () => {
    useProductNeighbours.mockReturnValue({
      prevId: null,
      nextId: 'n1',
      index: 1,
      total: 5,
      isLoading: false,
    });
    render(<ProductNavigation productId="prod-current" />);
    expect(screen.getByLabelText('Previous product')).toBeDisabled();
    expect(screen.getByLabelText('Next product')).not.toBeDisabled();
  });
});
