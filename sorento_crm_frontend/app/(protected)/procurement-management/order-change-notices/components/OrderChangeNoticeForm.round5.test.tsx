/**
 * OCN-ORDER-CHANGE-NOTICE round 5 (lead ruling N3): a saved draft takes a file straight onto the
 * notice from the form. Same harness as OrderChangeNoticeForm.round4.test.tsx.
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
import { CHANGE_TYPES, PRODUCT_HITS, ocnDetail } from './ocnTestData';

const asMock = (fn: unknown) => fn as ReturnType<typeof vi.fn>;
const PO = 'XT04/3871 (R1)';

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
  svc.get.mockResolvedValue(ocnDetail({ id: 'ocn-edit' }));
  svc.upload.mockResolvedValue({});
});

describe('round 5: a file uploaded straight onto a saved draft (N3)', () => {
  it('offers the drop zone beside Link Attachment and sends a chosen file through the service', async () => {
    renderForm({ ocnId: 'ocn-edit' });
    await waitFor(() => expect((screen.getByLabelText(/^Customer PO No/) as HTMLInputElement).value).toBe(PO));
    expect(screen.getByRole('button', { name: /link attachment/i })).toBeTruthy();
    expect(screen.getByRole('button', { name: /choose file/i })).toBeTruthy();
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(['%PDF-1.4'], 'revised-po.pdf', { type: 'application/pdf' });
    fireEvent.change(input, { target: { files: [file] } });
    await waitFor(() => expect(svc.upload).toHaveBeenCalledWith('ocn-edit', file));
  });

  it('has no drop zone on a new notice (nothing to upload onto yet)', async () => {
    renderForm();
    await screen.findByRole('heading', { name: 'Order Change Notice' });
    expect(screen.queryByRole('button', { name: /choose file/i })).toBeNull();
  });
});
