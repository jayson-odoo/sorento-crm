/** F2 / F6: the list's empty state, load error and a row. The service is mocked; the grid is real. */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render as rtlRender, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import DealerAccessView from './DealerAccessView';

function render(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return rtlRender(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => '/sales/dealer-access',
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));
vi.mock('@/components/common/container', () => ({
  Container: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));
vi.mock('@/components/common/PageHeader', () => ({
  PageHeader: ({ title }: { title: string }) => <h1>{title}</h1>,
}));
vi.mock('@/hooks/useDeferredRowAction', () => ({
  useDeferredRowAction: () => ({ run: vi.fn(), targetId: null, isPending: false, countdown: null }),
}));
vi.mock('../hooks/useMyDealerCompanies', () => ({
  useMyDealerCompanies: () => ({ options: [{ value: 'SRT', label: 'Sorento' }], isLoading: false }),
}));

const svc = vi.hoisted(() => ({ getPeople: vi.fn(), getAccounts: vi.fn() }));
vi.mock('@/services/dealerAccessService', async (orig) => ({
  ...(await orig<typeof import('@/services/dealerAccessService')>()),
  getPeople: svc.getPeople,
  getAccounts: svc.getAccounts,
}));

beforeEach(() => {
  vi.clearAllMocks();
  svc.getAccounts.mockResolvedValue([]);
});

describe('DealerAccessView', () => {
  it('renders the empty state with a heading and hint and the one Add people button', async () => {
    svc.getPeople.mockResolvedValue({ data: [], pagination: { page: 1, limit: 50, total: 0 } });
    render(<DealerAccessView />);
    await waitFor(() => expect(screen.getByText('No people have access yet')).toBeTruthy());
    expect(screen.getByText('Add people to give them access to your accounts.')).toBeTruthy();
    expect(screen.getAllByRole('button', { name: /add people/i })).toHaveLength(1);
  });

  it('renders the load error with Retry', async () => {
    svc.getPeople.mockRejectedValue(new Error('boom'));
    render(<DealerAccessView />);
    await waitFor(() => expect(screen.getByText('Could not load people')).toBeTruthy());
    expect(screen.getByRole('button', { name: /retry/i })).toBeTruthy();
  });

  it('renders a person with the owner tag and the other-account hint', async () => {
    svc.getPeople.mockResolvedValue({
      data: [
        {
          contact_id: 'c1',
          name: 'Person A',
          phone: '+60 12-000 0001',
          company: 'SRT',
          company_name: 'Sorento',
          accounts: [{ id: 'a1', code: '300-N034', name: 'CHO***', link_id: 'l1' }],
          access: 'owner',
          owner_tag: 'Sorento Business Owner',
          other_account: true,
        },
      ],
      pagination: { page: 1, limit: 50, total: 1 },
    });
    render(<DealerAccessView />);
    await waitFor(() => expect(screen.getByText('Person A')).toBeTruthy());
    expect(screen.getByText('Sorento Business Owner')).toBeTruthy();
    expect(screen.getByText('also another account')).toBeTruthy();
  });
});
