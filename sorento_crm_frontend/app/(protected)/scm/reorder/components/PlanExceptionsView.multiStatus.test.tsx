/**
 * FILTER-MULTISELECT PR5: the Reorder plan exceptions Status filter (client-side) takes several values:
 * two values show either, and unticking them all brings the open queue back.
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
vi.mock('../hooks/usePlanExceptions', () => ({
  usePlanExceptions: (...args: unknown[]) => mockUse(...args),
  useDecidePlanException: () => ({ mutate: vi.fn(), isPending: false }),
  planExceptionsKey: () => ['scm', 'reorder', 'plan-exceptions', null, null],
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

import { PlanExceptionsView } from './PlanExceptionsView';

const reading = { lifecycle: { value: 'Active', source: 'x' }, velocity: { value: 'A / X', source: 'x' }, business: { value: 'Retail', source: 'x' }, last_po: { value: '2026-03-02', source: 'x' } };
const timeline = { before_points: [{ date: '2026-08-04', net: 60, label: null }], after_points: [{ date: '2026-08-04', net: 60, label: null }], before_shortfall_at: null, after_shortfall_at: null, before_shortfall_qty: null, after_shortfall_qty: null };
const exc = (id: string, code: string, status: string) => ({
  exception_id: id, exception_type: 'supply_surplus', product_code: code, product_name: `${code} name`, uom: 'PCS',
  warehouse_code: 'MWH', pool_code: 'MWH', po_number: `PO-${id}`, po_expected_date: '2026-09-18', quantity: 240, timeline, reading,
  actions: [], status, decided_by: null, decided_at: null, decided_action: null, decision_reason: null,
});
const ROWS = [exc('1', 'ZZT-OPEN', 'open'), exc('2', 'ZZT-APPR', 'approved'), exc('3', 'ZZT-REJ', 'rejected')];

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
    data: {
      run_id: 'run-1', as_of: '2026-08-04', generated_at: '2026-08-04T17:58:00', last_upload_at: '2026-08-04T17:55:00',
      counts: { delta_count: 10, exception_count: 3, open_count: 1, approved_count: 1, rejected_count: 1 }, rows: ROWS,
    },
    isLoading: false, isError: false, error: null, refetch: vi.fn(),
  });
  return render(<PlanExceptionsView />);
}

beforeEach(() => {
  cleanup();
  mockUse.mockReset();
});
afterEach(() => cleanup());

describe('Plan exceptions - multi Status filter', () => {
  it('Status is a multi control', async () => {
    renderView();
    expect((await box('approved')).hasAttribute('multiple')).toBe(true);
  });

  it('two statuses show either, and not the one left out', async () => {
    const user = userEvent.setup();
    renderView();
    await user.selectOptions(await box('approved'), ['approved', 'rejected']);
    await waitFor(() => expect(screen.getByText('ZZT-APPR')).toBeInTheDocument());
    expect(screen.getByText('ZZT-REJ')).toBeInTheDocument();
    expect(screen.queryByText('ZZT-OPEN')).toBeNull();
  });

  it('unticking every status brings the open queue back', async () => {
    const user = userEvent.setup();
    renderView();
    await user.selectOptions(await box('approved'), ['approved', 'rejected']);
    await waitFor(() => expect(screen.queryByText('ZZT-OPEN')).toBeNull());
    await user.deselectOptions(await box('approved'), ['approved', 'rejected']);
    await waitFor(() => expect(screen.getByText('ZZT-OPEN')).toBeInTheDocument());
  });
});
