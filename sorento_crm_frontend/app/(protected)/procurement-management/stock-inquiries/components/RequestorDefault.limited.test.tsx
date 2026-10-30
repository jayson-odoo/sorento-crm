/**
 * PORTAL-P4-REQUESTS review fix: a staff New Purchase Request starts with no requestor (control). A salesperson's
 * own contact as the default requestor is the portal form's `defaultFromContact: 'contact_id'`, which their CRM
 * form is since R1 (Stock Inquiry) and R2 (Purchase Request, Sponsorship Form: *.portalForm.test.tsx).
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => '/x/new',
  useSearchParams: () => new URLSearchParams(''),
}));
vi.mock('next-auth/react', () => ({
  useSession: () => ({ data: { user: { name: 'Sam' } }, status: 'authenticated' }),
  SessionProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));
vi.mock('@/lib/toast', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));
vi.mock('@/hooks/usePublicViewLinksEnabled', () => ({ usePublicViewLinksEnabled: () => false }));
vi.mock('@/lib/listing-column-preferences/useListingColumnPreferences', () => ({
  useListingColumnPreferences: () => ({ resetToDefaults: vi.fn(), isLoading: false }),
}));
vi.mock('./StockInquiryAttachmentsSection', () => ({ __esModule: true, default: () => null }));
vi.mock('@/app/(protected)/procurement-management/purchase-requests/components/PurchaseRequestAttachmentsSection', () => ({ __esModule: true, default: () => null }));
vi.mock('@/components/common/LookupBoundField', () => ({ __esModule: true, default: () => null }));

let held = new Set<string>();
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: (slug: string) => held.has(slug),
  useHasAnyPermission: (slugs: string[]) => slugs.some((s) => held.has(s)),
  usePermissions: () => ({ permissionSet: held, permissions: [...held], isLoading: false, isError: false }),
}));
vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (p: { fetchOptions?: (q: string) => Promise<unknown>; value?: string }) => {
    React.useEffect(() => {
      void p.fetchOptions?.('');
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);
    return p.fetchOptions ? <div data-testid="requestor-picker">{p.value ? `picked ${p.value}` : 'empty'}</div> : <div />;
  },
}));

const calls: string[] = [];
const apiFetch = vi.fn(async (url: string) => {
  calls.push(url);
  const ok = (b: unknown) => new Response(JSON.stringify(b), { status: 200, headers: { 'content-type': 'application/json' } });
  if (url.includes('/account/') || url.endsWith('/users/me')) {
    return ok({ name: 'Sam Sales', salesperson: { portal_kinds: ['stock_inquiry'], portal_slug: 'SLUG', contact_id: 'c-own' } });
  }
  if (url.includes('requestor')) return ok({ items: [{ id: 'c-own', name: 'Sam Sales' }, { id: 'c2', name: 'Ann' }], has_more: false });
  return ok({});
});
vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  apiFetch: (...a: [string]) => apiFetch(...a),
}));

import PurchaseRequestForm from '@/app/(protected)/procurement-management/purchase-requests/components/PurchaseRequestForm';

const CASES: Array<[string, string, string, () => React.ReactElement]> = [
  // stock inquiry: R1 moved a salesperson's form to the portal's own (defaultFromContact 'contact_id').
  ['purchase request', 'procurement.purchase_requests', 'my-requests', () => <PurchaseRequestForm />],
];

function mount(el: React.ReactElement) {
  return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{el}</QueryClientProvider>);
}

beforeEach(() => {
  cleanup();
  calls.length = 0;
  vi.clearAllMocks();
});

describe.each(CASES)('%s New form', (_n, base, _x, build) => {
  it('staff: requestor starts empty', async () => {
    held = new Set([`${base}.view`, `${base}.add`]);
    mount(build());
    await screen.findAllByTestId('requestor-picker');
    await new Promise((r) => setTimeout(r, 100));
    expect(screen.getAllByTestId('requestor-picker').map((e) => e.textContent)).not.toContain('picked c-own');
  });
});
