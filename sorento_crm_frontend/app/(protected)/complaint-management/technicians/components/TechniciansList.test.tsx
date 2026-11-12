/** AFTER-SALES-P1 fix round 1 (S-10): rows carry no icon button; the right-click menu holds the actions. */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, fireEvent, within } from '@testing-library/react';

if (!window.matchMedia) {
  (window as unknown as { matchMedia: unknown }).matchMedia = () => ({
    matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {},
  });
}
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/complaint-management/technicians',
  useSearchParams: () => new URLSearchParams(''),
}));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));
vi.mock('@/hooks/usePermissions', () => ({ useHasPermission: () => true }));
vi.mock('@/hooks/useDeferredRowAction', () => ({
  useDeferredRowAction: () => ({ run: vi.fn(), targetId: null, isPending: false, countdown: null }),
}));
const mutate = { mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false };
vi.mock('../hooks/useTechnicians', () => ({
  useTechnicians: () => ({
    data: {
      data: [
        { id: 't-1', name: 'Ali', phone: '+6012', employment_type: 'employee', is_active: true, in_use: true },
      ],
      pagination: { total: 1, page: 1, limit: 50 },
    },
    isLoading: false, isFetching: false, isPlaceholderData: false, refetch: vi.fn(),
  }),
  useTechnicianMutations: () => ({ create: mutate, update: mutate, remove: mutate }),
}));

import TechniciansList from './TechniciansList';

function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><TechniciansList /></QueryClientProvider>);
}

describe('TechniciansList (S-10)', () => {
  it('has no icon button on a row', async () => {
    setup();
    const row = (await screen.findByText('Ali')).closest('tr')!;
    expect(within(row).queryAllByRole('button')).toHaveLength(0);
  });

  it('right-click offers Edit and Archive, and no Delete for a technician on a job', async () => {
    setup();
    fireEvent.contextMenu(await screen.findByText('Ali'));
    const menu = await screen.findByRole('menu');
    const labels = within(menu).getAllByRole('menuitem').map((i) => (i.textContent || '').trim());
    expect(labels).toEqual(['Edit', 'Archive']);
  });

  it('has the Filters control in the toolbar (R4-2)', async () => {
    setup();
    await screen.findByText('Ali');
    expect(screen.getByRole('button', { name: /Filters/ })).toBeInTheDocument();
  });
});
