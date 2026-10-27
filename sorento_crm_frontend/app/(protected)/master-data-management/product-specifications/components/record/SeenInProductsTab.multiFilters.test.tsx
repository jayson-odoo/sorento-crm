/**
 * FILTER-MULTISELECT PR4: the "Seen in products" tab's Value, Class and Source filters take several
 * values (OR within a filter, AND across), comma-joined to the data hook. Harness mirrors
 * SeenInProductsTab.test.tsx (hook mocked). The tab keeps its filters in component state, not the URL.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('next/navigation', () => ({
  usePathname: () => '/master-data-management/product-specifications/finish',
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));
vi.mock('@/hooks/usePermissions', () => ({ useHasPermission: () => true }));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));
vi.mock('../../hooks/useSpecRegistryMutations', () => ({
  useSpecRegistryMutations: () => ({ reread: { mutate: vi.fn(), isPending: false } }),
}));
const useQ = vi.hoisted(() => vi.fn());
vi.mock('../../hooks/useSpecKeyProductsQuery', () => ({
  useSpecKeyProductsQuery: (specKey: string, params: unknown) => useQ(specKey, params),
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

import { SeenInProductsTab } from './SeenInProductsTab';

const DATA = {
  spec_key: 'finish', label: 'Finish', total: 1,
  by_value: [{ value: 'matte', count: 3 }, { value: 'gloss', count: 2 }, { value: 'satin', count: 1 }],
  by_class: [{ class: 'ZZT Sink', count: 3 }, { class: 'ZZT Tap', count: 2 }],
  by_source: [{ source: 'derived', count: 4 }, { source: 'human', count: 2 }],
  products: [{ id: 'prod-1', product_code: 'ZZT-100', description: 'ZZT item', class: 'ZZT Sink', value: 'matte', source: 'derived', evidence: 'matte' }],
};

const setOf = (v: unknown): string[] =>
  (Array.isArray(v) ? v.map(String) : String(v ?? '').split(',')).map((s) => s.trim()).filter(Boolean).sort();
const lastParams = () => {
  const calls = useQ.mock.calls;
  return calls[calls.length - 1][1] as Record<string, unknown>;
};
const boxesWith = (value: string) =>
  screen.queryAllByRole('listbox').filter(
    (el) => el.hasAttribute('multiple') && el.querySelector(`option[value="${value}"]`),
  ) as HTMLSelectElement[];
function openFilters() {
  if (screen.queryAllByRole('listbox').length) return;
  fireEvent.pointerDown(screen.getByRole('button', { name: /Filters/i }), { button: 0 });
}
async function box(value: string) {
  openFilters();
  await waitFor(() => {
    if (!boxesWith(value).length) throw new Error(`no multi control offering option "${value}"`);
  });
  return boxesWith(value)[0];
}

function renderTab() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SeenInProductsTab specKey="finish" label="Finish" />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  useQ.mockReset();
  useQ.mockReturnValue({ data: DATA, isLoading: false, isFetching: false });
  Element.prototype.scrollIntoView = vi.fn();
});
afterEach(() => cleanup());

describe('Seen in products - multi Value, Class and Source filters', () => {
  it('Value, Class and Source are multi controls', async () => {
    renderTab();
    expect((await box('matte')).hasAttribute('multiple')).toBe(true);
    expect((await box('ZZT Tap')).hasAttribute('multiple')).toBe(true);
    expect((await box('human')).hasAttribute('multiple')).toBe(true);
  });

  it('two values reach the hook as a set of two and the badge counts one filter', async () => {
    const user = userEvent.setup();
    renderTab();
    await user.selectOptions(await box('matte'), ['matte', 'gloss']);
    await waitFor(() => expect(setOf(lastParams().value)).toEqual(['gloss', 'matte']));
    expect(within(screen.getByRole('button', { name: /Filters/i })).getByText('1')).toBeInTheDocument();
  });

  it('two classes and two sources reach the hook as sets of two', async () => {
    const user = userEvent.setup();
    renderTab();
    await user.selectOptions(await box('ZZT Tap'), ['ZZT Sink', 'ZZT Tap']);
    await user.selectOptions(await box('human'), ['derived', 'human']);
    await waitFor(() => {
      expect(setOf(lastParams().classLabel)).toEqual(['ZZT Sink', 'ZZT Tap']);
      expect(setOf(lastParams().source)).toEqual(['derived', 'human']);
    });
  });

  it('filters AND across: two values with one source', async () => {
    const user = userEvent.setup();
    renderTab();
    await user.selectOptions(await box('matte'), ['gloss', 'satin']);
    await user.selectOptions(await box('human'), ['human']);
    await waitFor(() => {
      expect(setOf(lastParams().value)).toEqual(['gloss', 'satin']);
      expect(setOf(lastParams().source)).toEqual(['human']);
    });
  });

  it('unticking every value drops the filter from the request', async () => {
    const user = userEvent.setup();
    renderTab();
    await user.selectOptions(await box('matte'), ['matte', 'gloss']);
    await waitFor(() => expect(setOf(lastParams().value)).toEqual(['gloss', 'matte']));
    await user.deselectOptions(await box('matte'), ['matte', 'gloss']);
    await waitFor(() => expect(setOf(lastParams().value)).toEqual([]));
  });
});
