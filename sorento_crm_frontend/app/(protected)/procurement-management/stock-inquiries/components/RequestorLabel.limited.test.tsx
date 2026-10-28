/**
 * PORTAL-P4-REQUESTS browser-pass fix (red): the preselected own requestor must SHOW its name on load, not the
 * placeholder until the dropdown opens. Real SearchableSelect (not mocked). Original header follows.
 * PORTAL-P4-REQUESTS review fix (red): the portal form preselects the signed-in salesperson's OWN contact as
 * the requestor (SubmissionForm `defaultFromContact: 'contact_id'`). The CRM limited New Stock Inquiry / Purchase
 * Request / Sponsorship Form must start the same way (own contact from the account profile's salesperson.contact_id),
 * and still list options from /api/v1/my-requests/requestor-options. Staff forms start empty (control).
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
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
const calls: string[] = [];
const apiFetch = vi.fn(async (url: string) => {
  calls.push(url);
  const ok = (b: unknown) => new Response(JSON.stringify(b), { status: 200, headers: { 'content-type': 'application/json' } });
  if (url.includes('/account/') || url.endsWith('/users/me')) {
    return ok({ name: 'Test Salesperson A', salesperson: { portal_kinds: ['stock_inquiry'], portal_slug: 'SLUG', contact_id: 'c-own' } });
  }
  if (url.includes('requestor')) return ok({ items: [{ id: 'c-own', name: 'Test Salesperson A' }, { id: 'c2', name: 'Ann' }], has_more: false });
  return ok({});
});
vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  apiFetch: (...a: [string]) => apiFetch(...a),
}));

import StockInquiryForm from './StockInquiryForm';
import PurchaseRequestForm from '@/app/(protected)/procurement-management/purchase-requests/components/PurchaseRequestForm';



const CASES: Array<[string, string, string, () => React.ReactElement]> = [
  ['stock inquiry', 'procurement.stock_inquiries', 'Select sales person', () => <StockInquiryForm />],
  ['purchase request', 'procurement.purchase_requests', 'Select requestor', () => <PurchaseRequestForm />],
  ['sponsorship form', 'procurement.sponsorship_forms', 'Select requestor', () => <PurchaseRequestForm defaultRequestType="sponsorship_form" />],
];

function mount(el: React.ReactElement) {
  return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{el}</QueryClientProvider>);
}

beforeEach(() => {
  cleanup();
  calls.length = 0;
  vi.clearAllMocks();
});

describe.each(CASES)('%s New form, requestor label', (_n, base, placeholder, build) => {
  it('limited: the combobox shows the own name on load without opening the dropdown', async () => {
    held = new Set([`${base}.view_own`, `${base}.add`]);
    mount(build());
    const box = () => screen.getAllByRole('combobox').find((c) => /Test Salesperson A|Select (sales person|requestor)/.test(c.textContent ?? ''));
    await waitFor(() => expect(box()?.textContent).toContain('Test Salesperson A'));
    expect(box()?.textContent).not.toContain(placeholder);
  });
});
