/**
 * The topbar must name the company the BACKEND will scope to.
 *
 * The browser authenticates FastAPI with an opaque session token, not the NextAuth
 * JWT, so the backend scope resolver never sees the `active_company_id` claim - it
 * falls back to the persisted `users.last_active_company_id`. Anything that moves
 * that value without re-minting this tab's JWT (a switch in another tab, another
 * device, an API client) leaves the claim stale while every scoped read follows the
 * persisted value.
 *
 * Observed live: the switcher read "Sorento SRT" while the backend answered
 * `active_company_id: <Mocha>`. Escalating a Sorento SLA stage then 422'd with "No
 * higher-tier team configured" - Mocha has no ladder - on a page that claimed to be
 * Sorento. A wrong label here is not cosmetic: it is the user's only signal about
 * which company their writes land in.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { CompanyProvider, useCompany } from './CompanyProvider';

const getMyCompanyContextMock = vi.fn();
const useSessionMock = vi.fn();

vi.mock('next-auth/react', () => ({
  useSession: () => useSessionMock(),
}));

vi.mock('@/app/(protected)/system-management/companies/services/companyService', () => ({
  getMyCompanyContext: () => getMyCompanyContextMock(),
  switchCompany: vi.fn(async () => undefined),
}));

const invalidateKitLibraryMock = vi.fn(async () => undefined);
vi.mock('@/lib/dealer-kit/kit-library-cache', () => ({
  invalidateKitLibrary: () => invalidateKitLibraryMock(),
}));

const SORENTO = {
  id: 'c-sorento',
  name: 'Sorento',
  code: 'SRT',
  is_active: true,
};
const MOCHA = { id: 'c-mocha', name: 'Mocha', code: 'MOCHA', is_active: true };

function ActiveCompanyProbe() {
  const { activeCompany, isLoading } = useCompany();
  if (isLoading) return <span>loading</span>;
  return <span data-testid="active">{activeCompany?.code ?? 'none'}</span>;
}

function renderProvider() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <CompanyProvider>
        <ActiveCompanyProbe />
      </CompanyProvider>
    </QueryClientProvider>,
  );
}

describe('CompanyProvider active company', () => {
  beforeEach(() => {
    getMyCompanyContextMock.mockReset();
    useSessionMock.mockReset();
  });

  it('follows the backend when the session claim has gone stale', async () => {
    useSessionMock.mockReturnValue({
      data: { user: { active_company_id: SORENTO.id } },
      status: 'authenticated',
      update: vi.fn(),
    });
    getMyCompanyContextMock.mockResolvedValue({
      companies: [MOCHA, SORENTO],
      active_company_id: MOCHA.id,
      last_active_company_id: MOCHA.id,
    });

    renderProvider();

    await waitFor(() => expect(screen.getByTestId('active')).toHaveTextContent('MOCHA'));
  });

  it('uses the session claim when the backend does not resolve one', async () => {
    useSessionMock.mockReturnValue({
      data: { user: { active_company_id: SORENTO.id } },
      status: 'authenticated',
      update: vi.fn(),
    });
    getMyCompanyContextMock.mockResolvedValue({
      companies: [MOCHA, SORENTO],
      active_company_id: null,
      last_active_company_id: null,
    });

    renderProvider();

    await waitFor(() => expect(screen.getByTestId('active')).toHaveTextContent('SRT'));
  });

  it('a switch also refreshes the designer library cache (its own client, old company data)', async () => {
    const update = vi.fn(async () => undefined);
    useSessionMock.mockReturnValue({
      data: { user: { active_company_id: SORENTO.id } },
      status: 'authenticated',
      update,
    });
    getMyCompanyContextMock.mockResolvedValue({
      companies: [MOCHA, SORENTO],
      active_company_id: SORENTO.id,
      last_active_company_id: SORENTO.id,
    });
    invalidateKitLibraryMock.mockClear();
    let switchTo: ((id: string) => void) | null = null;
    function Switcher() {
      const { setActiveCompany } = useCompany();
      switchTo = setActiveCompany;
      return null;
    }
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <CompanyProvider>
          <ActiveCompanyProbe />
          <Switcher />
        </CompanyProvider>
      </QueryClientProvider>,
    );
    await waitFor(() => expect(screen.getByTestId('active')).toHaveTextContent('SRT'));
    switchTo!(MOCHA.id);
    await waitFor(() => expect(invalidateKitLibraryMock).toHaveBeenCalledTimes(1));
    expect(update).toHaveBeenCalledWith({ active_company_id: MOCHA.id });
  });
});
