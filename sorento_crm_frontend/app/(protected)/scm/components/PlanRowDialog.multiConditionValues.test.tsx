/**
 * FILTER-MULTISELECT PR5: a picker's advanced-filter CONDITION takes several values (OR within the
 * condition). Today conditions AND and a condition holds one value, so two POs can never be shown at
 * once (two conditions on one field read as nothing). The shared condition editor serves the PO and
 * the Sales order pickers, so the PO picker stands for both here.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
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

vi.mock('next/navigation', () => ({ usePathname: () => '/scm/loading-plan' }));
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({ value, onChange, options, placeholder, clearable }: {
    value: string; onChange: (v: string) => void; options?: { value: string; label: string }[]; placeholder?: string; clearable?: boolean;
  }) => (
    <select aria-label={placeholder ? 'Filter value' : 'Filter field'} value={value} onChange={(e) => onChange(e.target.value)}>
      {clearable ? <option value="">{placeholder ?? ''}</option> : null}
      {(options ?? []).map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  ),
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

import { PoTakesPicker } from './PlanRowDialog';

const take = (id: string, po: string, supplier: string) => ({
  po_line_id: id, po_number: po, supplier_name: supplier, po_date: '2026-04-28', expected_date: '2026-09-15', qty: 40,
  open_qty: 150, taken_qty: 0, taken_by: [] as string[],
});
const TAKES = [take('l1', 'PO-24118', 'JINBAICHUAN'), take('l2', 'PO-24090', 'JINBAICHUAN'), take('l3', 'PO-9000', 'Kailu')];

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

function renderPicker() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <PoTakesPicker takes={TAKES} tickedIds={[]} onChange={() => {}} coveredQty={0} packedQty={60} />
    </QueryClientProvider>,
  );
  fireEvent.pointerDown(screen.getByRole('button', { name: /filters/i }), { button: 0 });
  fireEvent.click(screen.getByRole('button', { name: /add condition/i }));
}

beforeEach(() => cleanup());
afterEach(() => cleanup());

describe('PO / SO picker conditions - several values per condition', () => {
  it('the value of a condition is a multi control', async () => {
    renderPicker();
    expect((await box('PO-24118')).hasAttribute('multiple')).toBe(true);
  });

  it('two POs in one condition show both rows and hide the third', async () => {
    const user = userEvent.setup();
    renderPicker();
    await user.selectOptions(await box('PO-24118'), ['PO-24118', 'PO-9000']);
    fireEvent.click(screen.getByRole('button', { name: /^apply$/i }));
    await waitFor(() => expect(screen.getByText('PO-9000')).toBeTruthy());
    expect(screen.getByText('PO-24118')).toBeTruthy();
    expect(screen.queryByText('PO-24090')).toBeNull();
  });

  it('two suppliers in one condition show every PO of either', async () => {
    const user = userEvent.setup();
    renderPicker();
    fireEvent.change(screen.getByLabelText('Filter field'), { target: { value: 'supplier_name' } });
    await user.selectOptions(await box('JINBAICHUAN'), ['JINBAICHUAN', 'Kailu']);
    fireEvent.click(screen.getByRole('button', { name: /^apply$/i }));
    await waitFor(() => expect(screen.getByText('PO-9000')).toBeTruthy());
    expect(screen.getByText('PO-24118')).toBeTruthy();
    expect(screen.getByText('PO-24090')).toBeTruthy();
  });

  it('Clear filters restores every row', async () => {
    const user = userEvent.setup();
    renderPicker();
    await user.selectOptions(await box('PO-24118'), ['PO-24118', 'PO-9000']);
    fireEvent.click(screen.getByRole('button', { name: /^apply$/i }));
    await waitFor(() => expect(screen.queryByText('PO-24090')).toBeNull());
    fireEvent.click(screen.getByRole('button', { name: /clear filters/i }));
    await waitFor(() => expect(screen.getByText('PO-24090')).toBeTruthy());
  });
});
