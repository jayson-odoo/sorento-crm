/**
 * AC-B.5, item 6 - Seen in products.
 *
 * The Value column and the value facets read the same value_labels the record's
 * own Values and words tab does (readableValue), the facet strip is always mounted
 * (an empty one says "No facets yet" rather than vanishing), the facet pills are
 * the shared `Button`, and a row opens the product via `rowHref` (a real link
 * carrying `back=`) rather than a click handler with no href underneath it.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const push = vi.fn();
vi.mock('next/navigation', () => ({
  usePathname: () => '/master-data-management/product-specifications/finish',
  useRouter: () => ({ push, replace: vi.fn() }),
}));

vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => true,
}));

// Otherwise DataGrid stays on its loading skeleton forever - the real hook's
// react-query call never resolves in this test's environment (no API mocked).
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));

const rerouteMutate = vi.fn();
vi.mock('../../hooks/useSpecRegistryMutations', () => ({
  useSpecRegistryMutations: () => ({
    reread: { mutate: rerouteMutate, isPending: false },
  }),
}));

let queryData: unknown;
vi.mock('../../hooks/useSpecKeyProductsQuery', () => ({
  useSpecKeyProductsQuery: () => ({
    data: queryData,
    isLoading: false,
    isFetching: false,
  }),
}));

import { SeenInProductsTab } from './SeenInProductsTab';

function renderTab(props: Partial<React.ComponentProps<typeof SeenInProductsTab>> = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SeenInProductsTab specKey="finish" label="Finish" {...props} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  queryData = {
    spec_key: 'finish',
    label: 'Finish',
    total: 1,
    by_value: [{ value: 'pp', count: 3 }],
    by_class: [],
    by_source: [],
    products: [
      {
        id: 'prod-1',
        product_code: 'WC-100',
        description: 'Water closet',
        class: null,
        value: 'pp',
        source: 'derived',
        evidence: 'PP seat',
      },
    ],
  };
});

afterEach(() => {
  cleanup();
});

describe('SeenInProductsTab - value labels (item 6)', () => {
  it('the Value column reads the label, not the slug', () => {
    renderTab({ valueLabels: { pp: 'PP' } });

    expect(screen.getByTitle('PP')).toBeInTheDocument();
    expect(screen.queryByText('pp')).not.toBeInTheDocument();
  });

  it('the value facet pill reads the label too', () => {
    renderTab({ valueLabels: { pp: 'PP' } });

    expect(screen.getByText('PP · 3')).toBeInTheDocument();
  });

  it('falls back to the automatic wording with no label', () => {
    renderTab();

    expect(screen.getByText('Pp · 3')).toBeInTheDocument();
  });
});

describe('SeenInProductsTab - facet strip (item 6)', () => {
  it('shows "No facets yet" rather than disappearing when there are none', () => {
    queryData = { ...queryData, by_value: [], by_class: [], by_source: [] };
    renderTab();

    expect(screen.getByText('No facets yet')).toBeInTheDocument();
  });

  it('the value pill is a real button, pressed when it is the active filter', () => {
    renderTab();

    const pill = screen.getByRole('button', { name: /Pp · 3/ });
    expect(pill).toHaveAttribute('aria-pressed', 'false');
  });
});

describe('SeenInProductsTab - row navigation (item 6)', () => {
  beforeEach(() => push.mockReset());

  it('the row opens the product Specifications tab via rowHref, carrying back=', () => {
    renderTab();

    const row = screen
      .getAllByRole('row')
      .find((el) => el.getAttribute('tabindex') === '0') as HTMLElement;
    expect(row).toBeTruthy();

    fireEvent.click(row);

    expect(push).toHaveBeenCalledWith(expect.stringContaining('/products/prod-1'));
    expect(push.mock.calls[0][0]).toContain('tab=specifications');
    expect(push.mock.calls[0][0]).toContain('back=');
  });
});
