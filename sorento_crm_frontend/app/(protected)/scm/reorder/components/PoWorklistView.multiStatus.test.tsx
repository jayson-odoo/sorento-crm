/**
 * FILTER-MULTISELECT PR5: the PO worklist Status filter (client-side) takes several values: two values
 * show either, and unticking them all brings the still-to-key queue back.
 */
import React from 'react';
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

const mockUse = vi.hoisted(() => vi.fn());
vi.mock('../hooks/usePoWorklist', () => ({
  usePoWorklist: (...args: unknown[]) => mockUse(...args),
  useSetKeyedStatus: () => ({ mutate: vi.fn(), isPending: false }),
  poWorklistKey: () => ['scm', 'reorder', 'po-worklist', null],
}));
vi.mock('next/navigation', () => ({
  usePathname: () => '/scm/reorder',
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: async () => {}, isLoading: false }),
}));
vi.mock('@/components/common/SearchableMultiSelect', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/components/common/SearchableMultiSelect')>();
  const React = await import('react');
  type Props = Parameters<typeof actual.SearchableMultiSelect>[0];
  const Stub = ({ value, onChange, options, fetchOptions, placeholder, className, triggerClassName }: Props) => {
    const [loaded, setLoaded] = React.useState(options ?? []);
    React.useEffect(() => {
      if (fetchOptions) void fetchOptions('').then(setLoaded);
    }, [fetchOptions]);
    return (
      <select multiple aria-label={placeholder ?? 'multi'} value={value}
        data-class={className ?? ''} data-trigger-class={triggerClassName ?? ''}
        onChange={(e) => onChange(Array.from(e.target.selectedOptions, (o) => o.value))}>
        {(fetchOptions ? loaded : (options ?? [])).map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
    );
  };
  return { ...actual, SearchableMultiSelect: (props: Props) => <Stub {...props} /> };
});

import { PoWorklistView } from './PoWorklistView';

const row = (code: string, keyed: string) => ({
  product_code: code, product_name: `${code} name`, uom: 'UNIT', chosen_qty: 224, suggested_qty: 224,
  chosen_supplier_code: 'FOSHAN-CF', chosen_supplier_name: 'Foshan Ceramic', decided_by: 'Mr Loo',
  decided_at: '2026-08-04T09:14:00', need_by: '2026-10-13', place_by: '2026-08-29', lead_time_days: 45, is_late: false,
  last_po_cost: 1011, last_po_currency: 'MYR', cash_committed: 226464, keyed_status: keyed, keyed_by: null, keyed_at: null,
});
const ROWS = [row('ZZT-NOTKEYED', 'not_keyed'), row('ZZT-KEYING', 'keying'), row('ZZT-KEYED', 'keyed')];

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

function renderView() {
  mockUse.mockReturnValue({
    data: { run_id: 'run-1', as_of: '2026-08-04', decision_grain: 'product', front_planning_contract_version: 1, rows: ROWS },
    isLoading: false, isPlaceholderData: false, isError: false, error: null, refetch: vi.fn(),
  });
  return render(<PoWorklistView runId="run-1" />);
}

beforeEach(() => {
  cleanup();
  mockUse.mockReset();
});
afterEach(() => cleanup());

describe('PO worklist - multi Status filter', () => {
  it('Status is a multi control', async () => {
    renderView();
    expect((await box('keyed')).hasAttribute('multiple')).toBe(true);
  });

  it('two statuses show either, and not the one left out', async () => {
    const user = userEvent.setup();
    renderView();
    await user.selectOptions(await box('keyed'), ['keyed', 'not_keyed']);
    await waitFor(() => expect(screen.getByTitle('ZZT-KEYED')).toBeInTheDocument());
    expect(screen.getByTitle('ZZT-NOTKEYED')).toBeInTheDocument();
    expect(screen.queryByTitle('ZZT-KEYING')).toBeNull();
  });

  it('unticking every status brings the still-to-key queue back', async () => {
    const user = userEvent.setup();
    renderView();
    await user.selectOptions(await box('keyed'), ['keyed', 'not_keyed']);
    await waitFor(() => expect(screen.queryByTitle('ZZT-KEYING')).toBeNull());
    await user.deselectOptions(await box('keyed'), ['keyed', 'not_keyed']);
    await waitFor(() => expect(screen.getByTitle('ZZT-KEYING')).toBeInTheDocument());
  });

  // A width on `className` sizes the popover (SearchableMultiSelect.tsx:457) and squeezes the menu
  // under its 16rem floor; the trigger takes `triggerClassName`.
  it('sizes the Status trigger, not its popover', async () => {
    renderView();
    const control = await box('keyed');
    expect(control.getAttribute('data-trigger-class')).toContain('w-44');
    expect(control.getAttribute('data-class')).not.toContain('w-44');
  });
});
