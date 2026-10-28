/**
 * FILTER-MULTISELECT PR5: the SCM dashboard filter bar's Category, Supplier, Value (ABC) and Demand (XYZ)
 * filters take several values (OR within a filter, AND across). Warehouses is already multi: a guard.
 * The bar is controlled, so the test holds the filters in state and reads what `onChange` handed back;
 * the filter keys are found by name (category / supplier / abc / xyz), array or comma-joined.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
}
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = ResizeObserverStub;
Element.prototype.scrollIntoView = vi.fn();

vi.mock('../hooks/useScmOptions', () => ({
  useCategoryOptions: () => ({ data: [{ value: 'cat-1', label: 'ZZT Cat 1' }, { value: 'cat-2', label: 'ZZT Cat 2' }, { value: 'cat-3', label: 'ZZT Cat 3' }], error: null, refetch: vi.fn() }),
  useSupplierOptions: () => ({ data: [{ value: 'SUP1', label: 'ZZT Sup 1' }, { value: 'SUP2', label: 'ZZT Sup 2' }, { value: 'SUP3', label: 'ZZT Sup 3' }], error: null, refetch: vi.fn() }),
  useWarehouseOptions: () => ({ data: [{ value: 'WH1', label: 'ZZT WH 1' }, { value: 'WH2', label: 'ZZT WH 2' }], error: null, refetch: vi.fn() }),
}));
vi.mock('@/components/common/SearchableMultiSelect', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/components/common/SearchableMultiSelect')>();
  const React = await import('react');
  type Props = Parameters<typeof actual.SearchableMultiSelect>[0];
  const Stub = ({ value, onChange, options, fetchOptions, placeholder }: Props) => {
    const [loaded, setLoaded] = React.useState(options ?? []);
    React.useEffect(() => {
      if (fetchOptions) void fetchOptions('').then(setLoaded);
    }, [fetchOptions]);
    return (
      <select multiple aria-label={placeholder ?? 'multi'} value={value}
        onChange={(e) => onChange(Array.from(e.target.selectedOptions, (o) => o.value))}>
        {(fetchOptions ? loaded : (options ?? [])).map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
    );
  };
  return { ...actual, SearchableMultiSelect: (props: Props) => <Stub {...props} /> };
});

import { ScmFilterBar } from './ScmFilterBar';
import { EMPTY_SCM_FILTERS, type ScmFilters } from '../services/scmDashboardService';

const setOf = (v: unknown): string[] =>
  (Array.isArray(v) ? v.map(String) : String(v ?? '').split(',')).map((s) => s.trim()).filter(Boolean).sort();
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

const latest: { filters: ScmFilters } = { filters: EMPTY_SCM_FILTERS };
/** The values held by whichever filter key matches `pattern` (not the warehouses key). */
const valuesOf = (pattern: RegExp): string[] => {
  const entry = Object.entries(latest.filters as unknown as Record<string, unknown>).find(
    ([k]) => pattern.test(k) && !/warehouse/i.test(k),
  );
  return setOf(entry ? entry[1] : undefined);
};

function Harness() {
  const [filters, setFilters] = React.useState<ScmFilters>(EMPTY_SCM_FILTERS);
  latest.filters = filters;
  return <ScmFilterBar filters={filters} onChange={setFilters} />;
}

function renderBar() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <Harness />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  cleanup();
  latest.filters = EMPTY_SCM_FILTERS;
});
afterEach(() => cleanup());

describe('SCM filter bar - multi Category, Supplier, Value and Demand', () => {
  it('Category, Supplier, Value and Demand are multi controls', async () => {
    renderBar();
    expect((await box('cat-1')).hasAttribute('multiple')).toBe(true);
    expect((await box('SUP1')).hasAttribute('multiple')).toBe(true);
    expect((await box('A')).hasAttribute('multiple')).toBe(true);
    expect((await box('X')).hasAttribute('multiple')).toBe(true);
  });

  it('two categories are held as a set of two', async () => {
    const user = userEvent.setup();
    renderBar();
    await user.selectOptions(await box('cat-1'), ['cat-1', 'cat-3']);
    await waitFor(() => expect(valuesOf(/categor/i)).toEqual(['cat-1', 'cat-3']));
  });

  it('two suppliers are held as a set of two', async () => {
    const user = userEvent.setup();
    renderBar();
    await user.selectOptions(await box('SUP1'), ['SUP2', 'SUP3']);
    await waitFor(() => expect(valuesOf(/supplier/i)).toEqual(['SUP2', 'SUP3']));
  });

  it('Value and Demand classes, including the unknown pseudo-value, are held as sets', async () => {
    const user = userEvent.setup();
    renderBar();
    await user.selectOptions(await box('A'), ['A', 'unknown']);
    await user.selectOptions(await box('X'), ['X', 'Y']);
    await waitFor(() => {
      expect(valuesOf(/abc/i)).toEqual(['A', 'unknown']);
      expect(valuesOf(/xyz/i)).toEqual(['X', 'Y']);
    });
  });

  it('the filters AND across: all four held at once', async () => {
    const user = userEvent.setup();
    renderBar();
    await user.selectOptions(await box('cat-1'), ['cat-1', 'cat-2']);
    await user.selectOptions(await box('SUP1'), ['SUP1', 'SUP2']);
    await user.selectOptions(await box('A'), ['A', 'B']);
    await user.selectOptions(await box('X'), ['Y', 'Z']);
    await waitFor(() => {
      expect(valuesOf(/categor/i)).toEqual(['cat-1', 'cat-2']);
      expect(valuesOf(/supplier/i)).toEqual(['SUP1', 'SUP2']);
      expect(valuesOf(/abc/i)).toEqual(['A', 'B']);
      expect(valuesOf(/xyz/i)).toEqual(['Y', 'Z']);
    });
  });

  it('Clear drops every multi filter', async () => {
    const user = userEvent.setup();
    renderBar();
    await user.selectOptions(await box('cat-1'), ['cat-1', 'cat-2']);
    await user.selectOptions(await box('A'), ['A', 'B']);
    await waitFor(() => expect(valuesOf(/abc/i)).toEqual(['A', 'B']));
    await user.click(screen.getByRole('button', { name: /clear/i }));
    await waitFor(() => {
      expect(valuesOf(/categor/i)).toEqual([]);
      expect(valuesOf(/abc/i)).toEqual([]);
    });
  });

  it('Warehouses (already multi) still holds two warehouses', async () => {
    const user = userEvent.setup();
    renderBar();
    await user.selectOptions(await box('WH1'), ['WH1', 'WH2']);
    await waitFor(() => expect(setOf(latest.filters.warehouses)).toEqual(['WH1', 'WH2']));
  });
});
