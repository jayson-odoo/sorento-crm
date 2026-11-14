/**
 * OCN-ORDER-CHANGE-NOTICE round 4 (review and security fixes, lead rulings): the form's new
 * behaviour. Same harness as OrderChangeNoticeForm.test.tsx (the service mocked at its boundary).
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

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
}));
vi.mock('../services/orderChangeNoticeService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../services/orderChangeNoticeService')>();
  return {
    ...actual,
    // Round 17: the form searches customers through the notice's own route; the suite's customer
    // lookup mock stands for it, so its assertions read as before.
    lookupOrderChangeNoticeCustomers: async (q: string) =>
      (await import('@/app/(protected)/procurement-management/purchase-requests/services/customerLookupService')).lookupCustomersForRequest(q),
    createOrderChangeNotice: (...a: unknown[]) => svc.create(...a),
    updateOrderChangeNotice: (...a: unknown[]) => svc.update(...a),
    submitOrderChangeNotice: (...a: unknown[]) => svc.submit(...a),
    getOrderChangeNotice: (...a: unknown[]) => svc.get(...a),
    listChangeTypes: (...a: unknown[]) => svc.types(...a),
    searchOrderChangeNoticeProducts: (...a: unknown[]) => svc.products(...a),
    getOrderChangeNoticeSwitches: (...a: unknown[]) => svc.switches(...a),
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
import { CHANGE_TYPES, PRODUCT_HITS, UUID_RE, ocnDetail } from './ocnTestData';

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

describe('round 4: a refused Submit never numbers a second notice (review M4)', () => {
  it('keeps the created id: create once across two Submits, the second one updates', async () => {
    svc.submit.mockRejectedValueOnce(new Error('Choose the project before you submit.'));
    renderForm();
    await waitForForm();
    await fillValid();
    fireEvent.click(screen.getByRole('button', { name: /^submit$/i }));
    expect(await screen.findByText(/Choose the project before you submit/)).toBeTruthy();
    await waitFor(() => expect(nav.replace).toHaveBeenCalledWith('/procurement-management/order-change-notices/ocn-new/edit'));
    fireEvent.click(screen.getByRole('button', { name: /^submit$/i }));
    await waitFor(() => expect(svc.submit).toHaveBeenCalledTimes(2));
    expect(svc.create).toHaveBeenCalledTimes(1);
    expect(svc.update).toHaveBeenCalledTimes(1);
    expect(svc.update.mock.calls[0][0]).toBe('ocn-new');
  });
});

describe('round 4: the System Settings switch and the fenced edit', () => {
  it('marks the project required when the switch is on, and refuses Submit without one', async () => {
    svc.switches.mockResolvedValue({ requireProject: true });
    renderForm();
    await waitForForm();
    await waitFor(() => expect(labelNode(/^Registered project/).textContent).toMatch(/\*/));
    expect(labelNode(/^Registered project/).textContent).not.toMatch(/optional/i);
    await fillValid();
    fireEvent.click(screen.getByRole('button', { name: /^submit$/i }));
    await waitFor(() => expect(messageIn(fieldBox(screen.getByLabelText(/^Registered project/)))).toBeDefined());
    expect(svc.create).not.toHaveBeenCalled();
  });

  it('an edit is sent at the revision on screen', async () => {
    svc.get.mockResolvedValue(ocnDetail({ id: 'ocn-edit', revision_no: 2 }));
    renderForm({ ocnId: 'ocn-edit' });
    await waitFor(() => expect((screen.getByLabelText(/^Customer PO No/) as HTMLInputElement).value).toBe(PO));
    fireEvent.click(screen.getByRole('button', { name: /^save as draft$/i }));
    await waitFor(() => expect(svc.update).toHaveBeenCalled());
    expect(svc.update.mock.calls[0][2]).toBe(2);
  });

  it('draws the type of change as the shared toggle group', async () => {
    renderForm();
    await waitForForm();
    const item = (await screen.findByText('Delay')).closest('[data-slot="toggle-group-item"]');
    expect(item).not.toBeNull();
  });
});

describe('round 4: an amendment-born notice (review m1, m2)', () => {
  const amendmentBorn = () =>
    ocnDetail({
      id: 'ocn-edit',
      source: 'amendment',
      customer_name: null,
      customer_po_no: null,
      lines: [],
      amendment_id: 'am-1',
      change_table_json: { rows: [{ verb: 'DELAY' }], verb_summary: { DELAY: 1 } },
    });

  it('shows its project read-only and submits with no typed customer, PO or line', async () => {
    svc.get.mockResolvedValue(amendmentBorn());
    renderForm({ ocnId: 'ocn-edit' });
    await waitForForm();
    await waitFor(() => expect(screen.getAllByText('Project Alpha Tower').length).toBeGreaterThan(0));
    expect(screen.queryByLabelText(/^Registered project/)).toBeNull();
    expect(rows()).toHaveLength(0);
    fireEvent.click(screen.getByRole('button', { name: /^submit$/i }));
    await waitFor(() => expect(svc.submit).toHaveBeenCalledWith('ocn-edit', 0));
  });
});

describe('round 4: attachments on a saved notice (review B2)', () => {
  it('lists its files with Link Attachment while it is a draft', async () => {
    renderForm({ ocnId: 'ocn-edit' });
    await waitFor(() => expect((screen.getByLabelText(/^Customer PO No/) as HTMLInputElement).value).toBe(PO));
    expect(screen.getByText('Linked Attachments')).toBeTruthy();
    expect(screen.getByRole('button', { name: /link attachment/i })).toBeTruthy();
  });

  it('has no files section on a new notice (there is nothing to link to yet)', async () => {
    renderForm();
    await waitForForm();
    expect(screen.queryByText('Linked Attachments')).toBeNull();
  });
});
