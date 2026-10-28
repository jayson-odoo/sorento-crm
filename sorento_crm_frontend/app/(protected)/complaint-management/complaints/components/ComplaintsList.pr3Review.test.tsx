/**
 * FILTER-MULTISELECT PR3 review: an assignee id the options do not hold (an old link, or before the Respond
 * user lookup answers) is never shown as its own label. Uses the real SearchableMultiSelect.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import ComplaintsList from './ComplaintsList';

const url = vi.hoisted(() => ({ search: '' }));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/complaint-management/complaints',
  useSearchParams: () => new URLSearchParams(url.search),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));
const useComplaints = vi.fn();
vi.mock('../hooks/useComplaints', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../hooks/useComplaints')>();
  return {
    ...actual,
    useComplaints: (...a: unknown[]) => useComplaints(...a),
    useExportComplaintPdf: () => ({ mutate: vi.fn(), isPending: false }),
  };
});
vi.mock('../../complaint-root-causes/hooks/useComplaintRootCauses', () => ({
  useComplaintRootCausesSelect: () => ({ data: [{ id: 'rc-1', name: 'ZZT Cause One' }], error: null, refetch: vi.fn() }),
}));
vi.mock('../../complaint-resolutions/hooks/useComplaintResolutions', () => ({
  useComplaintResolutionsSelect: () => ({ data: [{ id: 'rs-1', name: 'ZZT Fix One' }], error: null, refetch: vi.fn() }),
}));
vi.mock('@/services/userSelectService', () => ({
  getUserLookup: vi.fn(async () => [
    { id: 'u-ann', respond_user_id: 'resp-ann', name: 'ZZT Ann', email: 'a@e.com' },
    { id: 'u-ben', respond_user_id: 'resp-ben', name: 'ZZT Ben', email: 'b@e.com' },
  ]),
}));
beforeEach(() => {
  if (!window.matchMedia) {
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: false, media: query, onchange: null, addListener: vi.fn(), removeListener: vi.fn(),
      addEventListener: vi.fn(), removeEventListener: vi.fn(), dispatchEvent: vi.fn(),
    })) as unknown as typeof window.matchMedia;
  }
  if (!('ResizeObserver' in window)) {
    (window as unknown as { ResizeObserver: unknown }).ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
  }
  Element.prototype.scrollIntoView = vi.fn();
  Element.prototype.hasPointerCapture = vi.fn();
  url.search = '';
  useComplaints.mockReset();
  useComplaints.mockReturnValue({
    data: { data: [], pagination: { total: 0, page: 1, limit: 50 } },
    isLoading: false, isPlaceholderData: false, isFetching: false, error: null, refetch: vi.fn(),
  });
});
afterEach(() => cleanup());

function renderIt() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ComplaintsList />
    </QueryClientProvider>,
  );
}
async function openFilters(user: ReturnType<typeof userEvent.setup>) {
  renderIt();
  await user.click(await screen.findByRole('button', { name: /^filters/i }));
  await screen.findByText('Assigned to');
}

const ORPHAN = 'resp-orphan-77123';
describe('Complaints - an assignee id the options do not hold', () => {
  it('shows no raw Respond id in the Assigned to trigger or a chip', async () => {
    url.search = `assigned_to=${ORPHAN}`;
    const user = userEvent.setup();
    await openFilters(user);
    expect(document.body.textContent ?? '').not.toContain(ORPHAN);
  });

  it('shows no raw id beside a known assignee either', async () => {
    url.search = `assigned_to=resp-ann%2C${ORPHAN}`;
    const user = userEvent.setup();
    await openFilters(user);
    await waitFor(() => expect(document.body.textContent ?? '').toContain('ZZT Ann'));
    expect(document.body.textContent ?? '').not.toContain(ORPHAN);
  });
});
