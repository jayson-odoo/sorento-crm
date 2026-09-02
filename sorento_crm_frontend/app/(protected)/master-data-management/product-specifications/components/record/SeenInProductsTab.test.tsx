/**
 * AC-B.5, D17 - Seen in products.
 *
 * The Value column and the Value filter option read the same value_labels the
 * record's own Values and words tab does (readableValue). The facets are toolbar
 * filters (Value/Class/Source `SearchableSelect`s, "{name} (count)"), not a pill
 * strip. A row opens the product via `rowHref` (a real link carrying `back=`)
 * rather than a click handler with no href underneath it.
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

let queryData: SpecKeyProducts;
let lastParams: SpecKeyProductsParams | undefined;
// `mock.calls` records what reached the hook. `lastParams` is the same thing read
// back plainly, so assertions below do not have to dig into vitest's call-argument
// typing.
const mockUseSpecKeyProductsQuery = vi.fn((specKey: string, params: SpecKeyProductsParams) => {
  lastParams = params;
  return { data: queryData, isLoading: false, isFetching: false };
});
vi.mock('../../hooks/useSpecKeyProductsQuery', () => ({
  useSpecKeyProductsQuery: (specKey: string, params: SpecKeyProductsParams) =>
    mockUseSpecKeyProductsQuery(specKey, params),
}));

import { SeenInProductsTab } from './SeenInProductsTab';
import type { SpecKeyProducts } from '../../services/productSpecService';
import type { SpecKeyProductsParams } from '../../hooks/useSpecKeyProductsQuery';

function renderTab(props: Partial<React.ComponentProps<typeof SeenInProductsTab>> = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SeenInProductsTab specKey="finish" label="Finish" {...props} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  mockUseSpecKeyProductsQuery.mockClear();
  lastParams = undefined;
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

// The three filter triggers carry no accessible name (role=combobox takes its
// name from `aria-label`/`aria-labelledby` only, never content) - so tests reach
// them by JSX order: Value, Class, Source (the same order the filter panel lists
// them in).
function openFilters() {
  fireEvent.pointerDown(screen.getByRole('button', { name: /Filters/i }), { button: 0 });
  const [valueCombobox, classCombobox, sourceCombobox] = screen.getAllByRole('combobox');
  return { valueCombobox, classCombobox, sourceCombobox };
}

describe('SeenInProductsTab - value labels (D17)', () => {
  it('the Value column reads the label, not the slug', () => {
    renderTab({ valueLabels: { pp: 'PP' } });

    expect(screen.getByTitle('PP')).toBeInTheDocument();
    expect(screen.queryByText('pp')).not.toBeInTheDocument();
  });

  it('the Value filter option reads the label too', () => {
    renderTab({ valueLabels: { pp: 'PP' } });

    const { valueCombobox } = openFilters();
    fireEvent.click(valueCombobox);

    expect(screen.getByText('PP (3)')).toBeInTheDocument();
  });

  it('falls back to the automatic wording with no label', () => {
    renderTab();

    const { valueCombobox } = openFilters();
    fireEvent.click(valueCombobox);

    expect(screen.getByText('Pp (3)')).toBeInTheDocument();
  });
});

describe('SeenInProductsTab - toolbar filters, not a pill strip (D17)', () => {
  it('offers Value, Class and Source as clearable filter selects', () => {
    queryData = {
      ...queryData,
      by_class: [{ class: 'Sinks', count: 2 }],
      by_source: [{ source: 'derived', count: 3 }],
    };
    renderTab();

    const { valueCombobox, classCombobox, sourceCombobox } = openFilters();
    expect(valueCombobox).toBeInTheDocument();
    expect(classCombobox).toBeInTheDocument();
    expect(sourceCombobox).toBeInTheDocument();

    fireEvent.click(classCombobox);
    expect(screen.getByText('Sinks (2)')).toBeInTheDocument();
  });

  it('choosing a Value option selects it on the combobox', () => {
    renderTab();

    const { valueCombobox } = openFilters();
    fireEvent.click(valueCombobox);
    fireEvent.click(screen.getByText('Pp (3)'));

    expect(screen.getByText('Pp (3)', { selector: '[data-slot="searchable-select-trigger"] span' })).toBeInTheDocument();
  });
});

describe('SeenInProductsTab - Class and Source narrow the query, not the page (D17)', () => {
  it('choosing a Class option reaches the query hook as classLabel, not a client-side filter', () => {
    queryData = { ...queryData, by_class: [{ class: 'Sinks', count: 2 }] };
    renderTab();

    const { classCombobox } = openFilters();
    fireEvent.click(classCombobox);
    fireEvent.click(screen.getByText('Sinks (2)'));

    expect(lastParams).toMatchObject({ classLabel: 'Sinks' });
  });

  it('choosing a Source option reaches the query hook as source, not a client-side filter', () => {
    queryData = { ...queryData, by_source: [{ source: 'human', count: 4 }] };
    renderTab();

    const { sourceCombobox } = openFilters();
    fireEvent.click(sourceCombobox);
    fireEvent.click(screen.getByText('Set by hand (4)'));

    expect(lastParams).toMatchObject({ source: 'human' });
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

  it('a real middle-click opens the same target in a new tab (F3)', () => {
    // DataGridTable's rowHref row is a <tr> with no <a> underneath it - a <tr>
    // cannot be an anchor's child per the HTML table model - so it earns
    // "opens in a new tab" the same way an anchor's target=_blank would: an
    // `auxclick` listener that checks `button === 1` and calls `window.open`.
    // A real middle-click delivers exactly that event, which this asserts
    // rather than looking for an `href` attribute that will never exist here.
    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null);
    renderTab();

    const row = screen
      .getAllByRole('row')
      .find((el) => el.getAttribute('tabindex') === '0') as HTMLElement;
    expect(row).toBeTruthy();

    fireEvent(row, new MouseEvent('auxclick', { bubbles: true, cancelable: true, button: 1 }));

    expect(openSpy).toHaveBeenCalledTimes(1);
    const [url] = openSpy.mock.calls[0];
    expect(String(url)).toContain('/products/prod-1');
    expect(String(url)).toContain('tab=specifications');
    expect(String(url)).toContain('back=');
    expect(push).not.toHaveBeenCalled();

    openSpy.mockRestore();
  });
});
