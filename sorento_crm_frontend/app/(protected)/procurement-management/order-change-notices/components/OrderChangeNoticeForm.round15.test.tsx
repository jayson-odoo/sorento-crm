/**
 * OCN-ORDER-CHANGE-NOTICE round 15 (hand test step 12): a NEW notice offers the drop zone; files
 * picked before the first save are held and go up right after the notice is created (the NPA and
 * price tag portal forms' rule), then show on the detail. Same harness as the round 4 suite.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';

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

const rows = () =>
  Array.from(document.querySelectorAll<HTMLElement>('[data-testid="order-change-notice-line"]'));
const clickAddRow = () => fireEvent.click(screen.getByRole('button', { name: /^\+?\s*add row$/i }));
const ensureRow = (): HTMLElement => {
  if (rows().length === 0) clickAddRow();
  return rows()[0];
};
const labelNode = (re: RegExp): HTMLElement => screen.getAllByText(re)[0];
const waitForForm = () => screen.findByRole('heading', { name: 'Order Change Notice' });

/** The smallest box holding this control and only its own label: where its message must sit. */
function fieldBox(control: HTMLElement): HTMLElement {
  let el: HTMLElement = control;
  while (el.parentElement && el.parentElement !== document.body) {
    if (el.parentElement.querySelectorAll('label').length > 1) break;
    el = el.parentElement;
  }
  return el;
}
const messageIn = (box: HTMLElement) =>
  Array.from(box.querySelectorAll<HTMLElement>('.text-destructive, [role="alert"]')).find(
    (n) => (n.textContent ?? '').trim().length > 0,
  );

async function typeCustomer(name: string) {
  const customer = screen.getByLabelText(/^Customer Name/) as HTMLInputElement;
  fireEvent.focus(customer);
  fireEvent.change(customer, { target: { value: name } });
  await waitFor(() => expect(lookupCustomersForRequest).toHaveBeenCalled());
  fireEvent.blur(customer);
  await new Promise((r) => setTimeout(r, 250));
  return customer;
}

async function pickProduct(row: HTMLElement, text = 'abc123') {
  const box = within(row).getByRole('combobox', { name: /item code/i });
  fireEvent.focus(box);
  fireEvent.change(box, { target: { value: text } });
  fireEvent.click(await screen.findByRole('option', { name: /ABC123-RL/ }));
}

/** A header and one picked line that pass every submit rule. */
async function fillValid() {
  await typeCustomer('Customer A');
  fireEvent.change(screen.getByLabelText(/^Customer PO No/), { target: { value: PO } });
  fireEvent.click(await screen.findByText('Delay'));
  const row = ensureRow();
  await pickProduct(row);
  fireEvent.change(within(row).getByLabelText('Qty before'), { target: { value: '100' } });
  fireEvent.change(within(row).getByLabelText('Qty after'), { target: { value: '100' } });
}

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  asMock(lookupCustomersForRequest).mockResolvedValue([]);
  svc.types.mockResolvedValue(CHANGE_TYPES);
  svc.products.mockResolvedValue(PRODUCT_HITS);
  svc.switches.mockResolvedValue({ requireProject: false });
  svc.create.mockImplementation(async () => ocnDetail({ id: 'ocn-new', revision_no: 0 }));
  svc.update.mockImplementation(async (id: string) => ocnDetail({ id, revision_no: 0 }));
  svc.submit.mockImplementation(async (id: string) => ocnDetail({ id, status: 'submitted' }));
  svc.get.mockResolvedValue(ocnDetail({ id: 'ocn-edit' }));
});


describe('round 15: files on a new notice (hand test step 12)', () => {
  it('shows the drop zone before the notice is saved', async () => {
    renderForm();
    await waitForForm();
    expect(screen.getByRole('button', { name: /choose file/i })).toBeTruthy();
  });

  it('holds a file picked before the first save and uploads it once the notice exists', async () => {
    svc.upload.mockResolvedValue({});
    renderForm();
    await waitForForm();
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(['%PDF-1.4'], 'revised-po.pdf', { type: 'application/pdf' });
    fireEvent.change(input, { target: { files: [file] } });
    expect(await screen.findByText('revised-po.pdf')).toBeTruthy();
    expect(svc.upload).not.toHaveBeenCalled(); // nothing to attach it to yet
    await fillValid();
    fireEvent.click(screen.getByRole('button', { name: /^submit$/i }));
    await waitFor(() => expect(svc.create).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(svc.upload).toHaveBeenCalledWith('ocn-new', file));
    expect(svc.upload.mock.invocationCallOrder[0]).toBeGreaterThan(svc.create.mock.invocationCallOrder[0]);
    await waitFor(() => expect(nav.push).toHaveBeenCalledWith('/procurement-management/order-change-notices/ocn-new'));
  });
});
