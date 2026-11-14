/**
 * OCN-ORDER-CHANGE-NOTICE round 20b, I8 prefill (review): a NEW notice shows "Requested by" already
 * set to the signed-in salesperson's linked contact, by name, before any save, and the create body
 * carries that contact id. With no linked contact the field is empty.
 *
 * Contract this test pins: the form reads `useAccountProfileForHeader()` (hooks/) and its
 * `salesperson.contactId` (already there) plus `salesperson.contactName` (the hook must add it:
 * the account profile's salesperson block carries the contact's name).
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


const profile = vi.hoisted(() => ({
  salesperson: null as null | { portalKinds: string[]; portalSlug: string; contactId: string | null; contactName: string | null },
}));
vi.mock('@/hooks/useAccountProfileForHeader', () => ({
  useAccountProfileForHeader: () => ({
    salesperson: profile.salesperson,
    isLoading: false,
    isError: false,
    avatarSrc: undefined,
    displayName: 'Test Salesperson A',
    displayEmail: 'sp@zzt.test',
  }),
}));

import OrderChangeNoticeForm from './OrderChangeNoticeForm';
import { CHANGE_TYPES, PRODUCT_HITS, ocnDetail } from './ocnTestData';

function renderForm() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <OrderChangeNoticeForm />
    </QueryClientProvider>,
  );
}

const lastProps = () => picker.props.at(-1) as Record<string, unknown>;

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  picker.props.length = 0;
  profile.salesperson = {
    portalKinds: ['order_change_notice'],
    portalSlug: 'sp-slug',
    contactId: 'contact-me',
    contactName: 'Requestor Me',
  };
  svc.types.mockResolvedValue(CHANGE_TYPES);
  svc.products.mockResolvedValue(PRODUCT_HITS);
  svc.switches.mockResolvedValue({ requireProject: false });
  svc.create.mockImplementation(async () => ocnDetail({ id: 'ocn-new', requested_by_contact_id: 'contact-me', requested_by: 'Requestor Me' }));
  svc.update.mockImplementation(async (id: string) => ocnDetail({ id }));
  svc.submit.mockImplementation(async (id: string) => ocnDetail({ id, status: 'submitted' }));
  svc.get.mockResolvedValue(ocnDetail({ id: 'ocn-edit' }));
});

describe('round 20b: a new notice prefills Requested by (I8)', () => {
  it('shows the signed-in salesperson\'s linked contact by name before any save', async () => {
    renderForm();
    await screen.findByRole('heading', { name: 'Order Change Notice' });
    await waitFor(() =>
      expect(screen.getByTestId('requestor-contact-select').getAttribute('data-value')).toBe('contact-me'),
    );
    expect(screen.getByText('Requestor Me')).toBeTruthy();
    expect(lastProps().savedContactName).toBe('Requestor Me');
    expect(svc.create).not.toHaveBeenCalled();
  });

  it('the first save carries requested_by_contact_id = that contact', async () => {
    renderForm();
    await screen.findByRole('heading', { name: 'Order Change Notice' });
    await waitFor(() =>
      expect(screen.getByTestId('requestor-contact-select').getAttribute('data-value')).toBe('contact-me'),
    );
    fireEvent.click(screen.getByRole('button', { name: /^save as draft$/i }));
    await waitFor(() => expect(svc.create).toHaveBeenCalled());
    const body = svc.create.mock.calls[0][0] as Record<string, unknown>;
    expect(body.requested_by_contact_id).toBe('contact-me');
  });

  it('a pick still wins over the prefill', async () => {
    renderForm();
    await screen.findByRole('heading', { name: 'Order Change Notice' });
    await waitFor(() =>
      expect(screen.getByTestId('requestor-contact-select').getAttribute('data-value')).toBe('contact-me'),
    );
    fireEvent.click(screen.getByRole('button', { name: 'pick requestor' }));
    fireEvent.click(screen.getByRole('button', { name: /^save as draft$/i }));
    await waitFor(() => expect(svc.create).toHaveBeenCalled());
    expect((svc.create.mock.calls[0][0] as Record<string, unknown>).requested_by_contact_id).toBe('contact-picked');
  });

  it('with no linked contact the field is empty and the body leaves it out', async () => {
    profile.salesperson = { portalKinds: [], portalSlug: 'sp-slug', contactId: null, contactName: null };
    renderForm();
    await screen.findByRole('heading', { name: 'Order Change Notice' });
    expect(screen.getByTestId('requestor-contact-select').getAttribute('data-value')).toBe('');
    fireEvent.click(screen.getByRole('button', { name: /^save as draft$/i }));
    await waitFor(() => expect(svc.create).toHaveBeenCalled());
    const body = svc.create.mock.calls[0][0] as Record<string, unknown>;
    expect(body.requested_by_contact_id ?? null).toBeNull();
  });
});
