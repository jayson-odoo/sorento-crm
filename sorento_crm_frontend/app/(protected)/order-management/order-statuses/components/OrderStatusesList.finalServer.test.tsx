/**
 * FILTER-MULTISELECT PR4b (owner Q1 (a)): the Order statuses "Final" filter stays a single yes / no
 * control, but it is answered by the server: the choice reaches the list request (a param naming
 * "final"; the backend route reads `is_final_status`) and the page is no longer filtered client-side,
 * so a final status on page 2 is reachable and the pagination total reflects the filter.
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

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/order-management/order-statuses',
  useSearchParams: () => new URLSearchParams(''),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: ({ value, onChange, options, placeholder }: {
    value: string; onChange: (v: string) => void; options: { value: string; label: string }[]; placeholder?: string;
  }) => (
    <select aria-label={placeholder ?? 'select'} value={value} onChange={(e) => onChange(e.target.value)}>
      {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  ),
}));
const useStatuses = vi.hoisted(() => vi.fn());
vi.mock('../hooks/useOrderStatuses', () => ({ useOrderStatuses: (params: unknown) => useStatuses(params) }));

import OrderStatusesList from './OrderStatusesList';

// The server answered with BOTH kinds regardless of the choice: whatever the screen shows is then
// exactly what it did not filter itself.
const ROWS = [
  { id: 'os-1', status_code: 'ZZT-FINAL', status_name: 'ZZT Final', sequence: 1, is_final_status: true, created_at: '2026-01-01T00:00:00' },
  { id: 'os-2', status_code: 'ZZT-OPEN', status_name: 'ZZT Open', sequence: 2, is_final_status: false, created_at: '2026-01-01T00:00:00' },
];
const lastParams = () => useStatuses.mock.calls[useStatuses.mock.calls.length - 1][0] as Record<string, unknown>;
const finalValue = (): unknown => {
  const entry = Object.entries(lastParams()).find(([k]) => /final/i.test(k));
  return entry ? entry[1] : undefined;
};
const isYes = (v: unknown) => v === true || v === 'true' || v === 'yes' || v === '1';
const isNo = (v: unknown) => v === false || v === 'false' || v === 'no' || v === '0';
const filtersButton = () => screen.getByRole('button', { name: /^filters/i });

async function openFilters(user: ReturnType<typeof userEvent.setup>) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <OrderStatusesList />
    </QueryClientProvider>,
  );
  await screen.findByText('ZZT-FINAL');
  await user.click(filtersButton());
}

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  useStatuses.mockReturnValue({
    data: { data: ROWS, pagination: { total: 2, page: 1, limit: 50 } },
    isLoading: false, isPlaceholderData: false, isFetching: false, error: null, refetch: vi.fn(),
  });
});
afterEach(() => cleanup());

describe('Order statuses - Final filter is answered by the server', () => {
  it('no final param is sent until a choice is made', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    expect(finalValue()).toBeUndefined();
  });

  it('choosing Final statuses sends a yes value in the list request', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    await user.selectOptions(screen.getByLabelText('All'), 'Final statuses');
    await waitFor(() => expect(isYes(finalValue())).toBe(true));
  });

  it('choosing Non-final statuses sends a no value in the list request', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    await user.selectOptions(screen.getByLabelText('All'), 'Non-final statuses');
    await waitFor(() => expect(isNo(finalValue())).toBe(true));
  });

  it('the page is not filtered client-side: both kinds the server returned stay visible', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    await user.selectOptions(screen.getByLabelText('All'), 'Final statuses');
    await waitFor(() => expect(isYes(finalValue())).toBe(true));
    expect(screen.getByText('ZZT-FINAL')).toBeInTheDocument();
    expect(screen.getByText('ZZT-OPEN')).toBeInTheDocument();
  });

  it('the filter drops back to no param when All is chosen again', async () => {
    const user = userEvent.setup();
    await openFilters(user);
    const select = screen.getByLabelText('All');
    await user.selectOptions(select, 'Final statuses');
    await waitFor(() => expect(isYes(finalValue())).toBe(true));
    await user.selectOptions(select, 'All');
    await waitFor(() => expect(finalValue()).toBeUndefined());
  });
});
