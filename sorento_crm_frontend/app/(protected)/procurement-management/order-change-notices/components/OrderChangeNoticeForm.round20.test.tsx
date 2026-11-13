/**
 * OCN-ORDER-CHANGE-NOTICE round 20, I7 + I8 (form): ONE "Requested by" field, the shared
 * RequestorContactSelect, replaces "Sales Person" (read-only creator) and "Sales Incharge"
 * (user picker). Same harness as the round 15 suite; the picker is stubbed at its module.
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
  upload: vi.fn(),
}));
vi.mock('../services/orderChangeNoticeService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../services/orderChangeNoticeService')>();
  return {
    ...actual,
    lookupOrderChangeNoticeCustomers: async () => [],
    createOrderChangeNotice: (...a: unknown[]) => svc.create(...a),
    updateOrderChangeNotice: (...a: unknown[]) => svc.update(...a),
    submitOrderChangeNotice: (...a: unknown[]) => svc.submit(...a),
    getOrderChangeNotice: (...a: unknown[]) => svc.get(...a),
    listChangeTypes: (...a: unknown[]) => svc.types(...a),
    searchOrderChangeNoticeProducts: (...a: unknown[]) => svc.products(...a),
    getOrderChangeNoticeSwitches: (...a: unknown[]) => svc.switches(...a),
    uploadOrderChangeNoticeAttachment: (...a: unknown[]) => svc.upload(...a),
  };
});
vi.mock(
  '@/app/(protected)/procurement-management/purchase-requests/services/customerLookupService',
  () => ({ lookupCustomersForRequest: vi.fn(async () => []) }),
);
vi.mock('@/app/(protected)/complaint-management/complaints/services/complaintService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/app/(protected)/complaint-management/complaints/services/complaintService')>();
  return { ...actual, searchProjectsForLink: vi.fn(async () => []) };
});
vi.mock('@/services/userSelectService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/userSelectService')>();
  const users = [{ id: 'u-cs', name: 'CS Person A' }];
  return { ...actual, getUserLookup: vi.fn(async () => users), getUsersSelect: vi.fn(async () => users) };
});

// The shared picker, observed at its module: what the form hands it, and a button that picks.
const picker = vi.hoisted(() => ({ props: [] as Array<Record<string, unknown>> }));
vi.mock(
  '@/app/(protected)/master-data-management/shared/components/RequestorContactSelect',
  () => ({
    RequestorContactSelect: (props: Record<string, unknown>) => {
      picker.props.push(props);
      return (
        <div data-testid="requestor-contact-select" data-value={String(props.value ?? '')}>
          <span>{String(props.savedContactName ?? '')}</span>
          <button type="button" onClick={() => (props.onChange as (v: string | null) => void)('contact-picked')}>
            pick requestor
          </button>
        </div>
      );
    },
  }),
);

import OrderChangeNoticeForm from './OrderChangeNoticeForm';
import { CHANGE_TYPES, PRODUCT_HITS, ocnDetail } from './ocnTestData';

function renderForm(props: { ocnId?: string; projectId?: string } = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <OrderChangeNoticeForm {...props} />
    </QueryClientProvider>,
  );
}

const withRequestor = (over: Record<string, unknown> = {}) =>
  ocnDetail({
    id: 'ocn-edit',
    sales_in_charge_user_id: undefined,
    sales_in_charge_name: undefined,
    requested_by_contact_id: 'contact-saved',
    requested_by: 'Requestor A',
    ...over,
  });

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  picker.props.length = 0;
  svc.types.mockResolvedValue(CHANGE_TYPES);
  svc.products.mockResolvedValue(PRODUCT_HITS);
  svc.switches.mockResolvedValue({ requireProject: false });
  svc.create.mockImplementation(async () => withRequestor({ id: 'ocn-new' }));
  svc.update.mockImplementation(async (id: string) => withRequestor({ id }));
  svc.submit.mockImplementation(async (id: string) => withRequestor({ id, status: 'submitted' }));
  svc.get.mockResolvedValue(withRequestor());
});

describe('round 20: one Requested by field (I7)', () => {
  it('renders "Requested by" with the shared picker and no Sales Person / Sales Incharge label', async () => {
    renderForm();
    await screen.findByRole('heading', { name: 'Order Change Notice' });
    expect(screen.getAllByText(/^Requested by/).length).toBeGreaterThan(0);
    expect(screen.getByTestId('requestor-contact-select')).toBeTruthy();
    expect(screen.queryByText(/Sales Person/i)).toBeNull();
    expect(screen.queryByText(/Sales Incharge/i)).toBeNull();
    expect(screen.queryByText(/Sales in charge/i)).toBeNull();
  });

  it('an edit shows the saved requestor by name, handing the picker the saved id and name', async () => {
    renderForm({ ocnId: 'ocn-edit' });
    await waitFor(() =>
      expect(screen.getByTestId('requestor-contact-select').getAttribute('data-value')).toBe('contact-saved'),
    );
    expect(screen.getByText('Requestor A')).toBeTruthy();
    const last = picker.props.at(-1) as Record<string, unknown>;
    expect(last.savedContactId).toBe('contact-saved');
    expect(last.savedContactName).toBe('Requestor A');
  });

  it('saves the picked contact as requested_by_contact_id, and never sends sales_in_charge_user_id', async () => {
    renderForm({ ocnId: 'ocn-edit' });
    await waitFor(() => expect(screen.getByTestId('requestor-contact-select')).toBeTruthy());
    fireEvent.click(screen.getByRole('button', { name: 'pick requestor' }));
    fireEvent.click(screen.getByRole('button', { name: /^save as draft$/i }));
    await waitFor(() => expect(svc.update).toHaveBeenCalled());
    const body = svc.update.mock.calls[0][1] as Record<string, unknown>;
    expect(body.requested_by_contact_id).toBe('contact-picked');
    expect('sales_in_charge_user_id' in body).toBe(false);
  });

  it('a new notice opens with the default the server sent (I8), empty when it sent none', async () => {
    renderForm();
    await screen.findByRole('heading', { name: 'Order Change Notice' });
    expect(screen.getByTestId('requestor-contact-select').getAttribute('data-value')).toBe('');
  });
});
