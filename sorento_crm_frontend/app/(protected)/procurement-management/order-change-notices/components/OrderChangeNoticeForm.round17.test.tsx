/**
 * OCN-ORDER-CHANGE-NOTICE round 17 (crew re-pass, owner rule "every picker searchable"): the
 * Customer Name picker searches through the notice's own lookup, which a `.view_own` salesperson
 * may call, never the purchase request's (its own-scope guard refuses them). Same harness as the
 * round 4 suite.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';

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

const nav = vi.hoisted(() => ({ push: vi.fn(), back: vi.fn(), replace: vi.fn() }));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: nav.push, replace: nav.replace, back: nav.back }),
  useSearchParams: () => new URLSearchParams(''),
  usePathname: () => '/procurement-management/order-change-notices/new',
}));
vi.mock('@/lib/toast', () => ({ toast: { error: vi.fn(), success: vi.fn(), info: vi.fn() } }));
// Round 20b: the form reads the signed-in salesperson's linked contact (UAC I8 prefill); none here.
vi.mock('@/hooks/useAccountProfileForHeader', () => ({ useAccountProfileForHeader: () => ({ salesperson: null }) }));
vi.mock('@/hooks/usePermissions', () => ({
  useHasPermission: () => true,
  usePermissions: () => ({ permissions: [], permissionSet: new Set(), isLoading: false }),
}));

const svc = vi.hoisted(() => ({
  create: vi.fn(),
  update: vi.fn(),
  submit: vi.fn(),
  get: vi.fn(),
  types: vi.fn(),
  products: vi.fn(),
  switches: vi.fn(),
  customers: vi.fn(),
}));
vi.mock('../services/orderChangeNoticeService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../services/orderChangeNoticeService')>();
  return {
    ...actual,
    createOrderChangeNotice: (...a: unknown[]) => svc.create(...a),
    updateOrderChangeNotice: (...a: unknown[]) => svc.update(...a),
    submitOrderChangeNotice: (...a: unknown[]) => svc.submit(...a),
    getOrderChangeNotice: (...a: unknown[]) => svc.get(...a),
    listChangeTypes: (...a: unknown[]) => svc.types(...a),
    searchOrderChangeNoticeProducts: (...a: unknown[]) => svc.products(...a),
    getOrderChangeNoticeSwitches: (...a: unknown[]) => svc.switches(...a),
    lookupOrderChangeNoticeCustomers: (...a: unknown[]) => svc.customers(...a),
  };
});

vi.mock(
  '@/app/(protected)/procurement-management/purchase-requests/services/customerLookupService',
  () => ({ lookupCustomersForRequest: vi.fn(async () => []) }),
);
vi.mock('@/app/(protected)/complaint-management/complaints/services/complaintService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/app/(protected)/complaint-management/complaints/services/complaintService')>();
  return {
    ...actual,
    searchProjectsForLink: vi.fn(async () => [
      { value: 'proj-alpha', label: 'PRJ-001 - Project Alpha Tower' },
    ]),
  };
});
vi.mock('@/services/userSelectService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/userSelectService')>();
  const users = [
    { id: 'u-sales', name: 'Sales Person A' },
    { id: 'u-cs', name: 'CS Person A' },
  ];
  return {
    ...actual,
    getUserLookup: vi.fn(async () => users),
    getUsersSelect: vi.fn(async () => users),
  };
});

import { lookupCustomersForRequest } from '@/app/(protected)/procurement-management/purchase-requests/services/customerLookupService';
import OrderChangeNoticeForm from './OrderChangeNoticeForm';
import { CHANGE_TYPES, PRODUCT_HITS } from './ocnTestData';

const asMock = (fn: unknown) => fn as ReturnType<typeof vi.fn>;

function renderForm(props: { ocnId?: string; projectId?: string } = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <OrderChangeNoticeForm {...props} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  asMock(lookupCustomersForRequest).mockResolvedValue([]);
  svc.types.mockResolvedValue(CHANGE_TYPES);
  svc.products.mockResolvedValue(PRODUCT_HITS);
  svc.switches.mockResolvedValue({ requireProject: false });
  svc.customers.mockResolvedValue([
    { customer_id: 'c-1', debtor_name: 'ZZT Builders', customer_code: '300-Z001', debtor_type: null, sales_type: null },
  ]);
});

describe('round 17: the Customer Name picker searches through the notice', () => {
  it("calls the notice's own customer lookup, never the purchase request's", async () => {
    renderForm();
    await screen.findByRole('heading', { name: 'Order Change Notice' });
    const box = screen.getByLabelText(/^Customer Name/) as HTMLInputElement;
    fireEvent.focus(box);
    fireEvent.change(box, { target: { value: 'ZZT' } });
    await waitFor(() => expect(svc.customers).toHaveBeenCalledWith('ZZT'));
    expect(await screen.findByText(/ZZT Builders/)).toBeTruthy();
    expect(lookupCustomersForRequest).not.toHaveBeenCalled();
  });
});
