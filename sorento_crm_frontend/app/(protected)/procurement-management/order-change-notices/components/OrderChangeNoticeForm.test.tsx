/**
 * OCN-ORDER-CHANGE-NOTICE UAC G3 (red-first): the raise / edit form, drawn in the sample request
 * document shell (owner: "make sure the form obey with our design principle in sample request").
 * Component: ./OrderChangeNoticeForm.tsx (default export, props { ocnId?: string; projectId?: string }).
 * Line table: components/common/OrderChangeNoticeLines.tsx (shared, rendered inside the form).
 *
 * UI hooks this file fixes for the coder (the mock names no markup), all copied from
 * SampleRequestForm.test.tsx:
 *  - the card carries the visible heading "Order Change Notice" and a secondary badge with the same
 *    words, plus the status pill (the record's status word, "Draft" on a new one);
 *  - every header field has a visible label (trailing " *" / "(optional)" allowed, prefix match) and
 *    the control is reachable with getByLabelText(<label>): Customer Name, Customer PO No., SO No.,
 *    Registered project, C.S. Incharge, Requested by (round 20); Type of change is a choice of the four
 *    types (click the type's name), the risk and the guide text of the picked type are read-only text;
 *  - Customer Name = AsyncCombobox + lookupCustomersForRequest (free text kept as customer_name);
 *  - the line table: columnheaders No., Item Code, Qty before, Qty after, Date before, Date after,
 *    Delivered, Remark; the outline "Add row" button appends a row; each row is exactly one element
 *    with data-testid="order-change-notice-line"; inside it the product search is role="combobox"
 *    named "Item code", the others carry aria-label "Qty before", "Qty after", "Date before",
 *    "Date after", "Delivered", "Remark" (the two dates are the shared DatePickerField);
 *  - a validation message is an element with class text-destructive (or role="alert") INSIDE the same
 *    field box as its control, never only in a banner at the top or bottom;
 *  - service calls (module ../services/orderChangeNoticeService): createOrderChangeNotice(body),
 *    updateOrderChangeNotice(id, body), submitOrderChangeNotice(id, revisionNo),
 *    getOrderChangeNotice(id), listChangeTypes(), searchOrderChangeNoticeProducts(q) -> hits
 *    {id, product_code, product_name, brand_name}; body keys as the backend payload (change_type_id,
 *    customer_id, customer_name, customer_po_no, so_no_text, project_id, requested_by_contact_id,
 *    cs_in_charge_user_id, description, lines[{product_id, qty_before, qty_after, date_before,
 *    date_after, delivered_qty, remark}]), dates as YYYY-MM-DD.
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

const nav = vi.hoisted(() => ({ push: vi.fn(), back: vi.fn() }));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: nav.push, replace: vi.fn(), back: nav.back }),
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
  svc.create.mockImplementation(async () => ocnDetail({ id: 'ocn-new', revision_no: 0 }));
  svc.update.mockImplementation(async (id: string) => ocnDetail({ id, revision_no: 0 }));
  svc.submit.mockImplementation(async (id: string) => ocnDetail({ id, status: 'submitted' }));
  svc.get.mockResolvedValue(ocnDetail({ id: 'ocn-edit' }));
});

describe('G3 the sample request document shell', () => {
  it('shows one card: the kind badge, the status pill and the centred title', async () => {
    renderForm();
    expect(await waitForForm()).toBeTruthy();
    const badge = screen
      .getAllByText('Order Change Notice')
      .find((n) => !/^H[1-6]$/.test(n.tagName));
    expect(badge, 'a badge carrying the kind').toBeDefined();
    expect(screen.getByText('Draft')).toBeTruthy();
  });

  it('prints the header labels in the card order', async () => {
    renderForm();
    await waitForForm();
    const order = [
      /^Date\b/,
      /^Customer Name/,
      /^Customer PO No/,
      /^SO No/,
      /^Registered project/,
      /^C\.S\. Incharge/,
      /^Requested by/,
      /^Type of change/,
    ];
    const nodes = order.map(labelNode);
    for (let i = 0; i < nodes.length - 1; i += 1) {
      expect(
        nodes[i].compareDocumentPosition(nodes[i + 1]) & Node.DOCUMENT_POSITION_FOLLOWING,
        `${order[i]} should come before ${order[i + 1]}`,
      ).toBeTruthy();
    }
  });

  it('marks Customer Name and Customer PO No. required, the project optional', async () => {
    renderForm();
    await waitForForm();
    expect(labelNode(/^Customer Name/).textContent).toMatch(/\*/);
    expect(labelNode(/^Customer PO No/).textContent).toMatch(/\*/);
    expect(labelNode(/^Registered project/).textContent).toMatch(/\(optional\)/i);
    expect(labelNode(/^SO No/).textContent).not.toMatch(/\*/);
  });

  it('shows Sales Person and Date as read-only values, the date as dd/mm/yyyy', async () => {
    renderForm();
    await waitForForm();
    expect(screen.queryByLabelText(/^Sales Person/)).toBeNull();
    expect(document.body.textContent).toMatch(/\b\d{2}\/\d{2}\/\d{4}\b/);
    expect(document.querySelector('input[type="date"]')).toBeNull();
  });

  it('has Cancel, Save as draft (outline) and Submit (the one main button)', async () => {
    renderForm();
    await waitForForm();
    expect(screen.getAllByRole('button', { name: /^cancel$/i }).length).toBeGreaterThan(0);
    const draft = screen.getByRole('button', { name: /^save as draft$/i });
    const submit = screen.getByRole('button', { name: /^submit$/i });
    expect(draft.className).toMatch(/border/);
    expect(draft.className).not.toMatch(/(^|\s)bg-primary(\s|$)/);
    expect(submit.className).toMatch(/(^|\s)bg-primary(\s|$)/);
  });

  it('Cancel goes back to the list on a new notice', async () => {
    renderForm();
    await waitForForm();
    fireEvent.click(screen.getByRole('button', { name: /^cancel$/i }));
    expect(nav.push).toHaveBeenCalledWith('/procurement-management/order-change-notices');
  });

  it('has a Description box and no UUID text anywhere', async () => {
    renderForm();
    await waitForForm();
    expect(screen.getByLabelText(/^Description/)).toBeTruthy();
    expect(document.body.textContent).not.toMatch(UUID_RE);
  });
});

describe('G3 type of change', () => {
  it('offers the four types and nothing is picked at first', async () => {
    renderForm();
    await waitForForm();
    for (const name of ['Advance', 'Exchange', 'Cancellation', 'Delay']) {
      expect(await screen.findByText(name)).toBeTruthy();
    }
    expect(screen.queryByText(CHANGE_TYPES[1].guide_text)).toBeNull();
  });

  it('picking a type shows its risk level and its guide text, read-only', async () => {
    renderForm();
    await waitForForm();
    fireEvent.click(await screen.findByText('Exchange'));
    expect(await screen.findByText(CHANGE_TYPES[1].guide_text)).toBeTruthy();
    expect(screen.getByText('High')).toBeTruthy();
    expect(screen.queryByDisplayValue('High')).toBeNull();
  });

  it('picking another type swaps the risk and the guide', async () => {
    renderForm();
    await waitForForm();
    fireEvent.click(await screen.findByText('Exchange'));
    await screen.findByText(CHANGE_TYPES[1].guide_text);
    fireEvent.click(screen.getByText('Cancellation'));
    expect(await screen.findByText(CHANGE_TYPES[2].guide_text)).toBeTruthy();
    expect(screen.getByText('Highest')).toBeTruthy();
    expect(screen.queryByText(CHANGE_TYPES[1].guide_text)).toBeNull();
  });
});

describe('G3 line items', () => {
  it('has the heading, an outline Add row button and the seven line columns', async () => {
    renderForm();
    await waitForForm();
    expect(screen.getByRole('heading', { name: 'Line items' })).toBeTruthy();
    const add = screen.getByRole('button', { name: /^\+?\s*add row$/i });
    expect(add.className).toMatch(/border/);
    ensureRow();
    for (const name of ['No.', 'Item Code', 'Qty before', 'Qty after', 'Date before', 'Date after', 'Delivered', 'Remark']) {
      expect(
        screen.getByRole('columnheader', { name: new RegExp(`^${name.replace('.', '\\.')}$`) }),
        name,
      ).toBeTruthy();
    }
  });

  it('Add row appends a row', async () => {
    renderForm();
    await waitForForm();
    const before = ensureRow() && rows().length;
    clickAddRow();
    expect(rows().length).toBe(before + 1);
  });

  it('every row has the product search and the six value boxes', async () => {
    renderForm();
    await waitForForm();
    const row = ensureRow();
    expect(within(row).getByRole('combobox', { name: /item code/i })).toBeTruthy();
    for (const name of ['Qty before', 'Qty after', 'Date before', 'Date after', 'Delivered', 'Remark']) {
      expect(within(row).getByLabelText(name), name).toBeTruthy();
    }
  });

  it('product search lists a catalogue product and picks only on a click', async () => {
    renderForm();
    await waitForForm();
    const row = ensureRow();
    const box = within(row).getByRole('combobox', { name: /item code/i }) as HTMLInputElement;
    fireEvent.focus(box);
    fireEvent.change(box, { target: { value: 'abc123' } });
    const option = await screen.findByRole('option', { name: /ABC123-RL/ });
    expect(svc.products).toHaveBeenCalledWith('abc123');
    expect(row.textContent).not.toMatch(/ABC123-RL/);
    fireEvent.click(option);
    await waitFor(() => expect((within(row).getByRole('combobox', { name: /item code/i }) as HTMLInputElement).value).toMatch(/ABC123-RL/));
  });

  it('a typed date is accepted as dd/mm/yyyy and saved as YYYY-MM-DD', async () => {
    renderForm();
    await waitForForm();
    await fillValid();
    const row = rows()[0];
    const after = within(row).getByLabelText('Date after') as HTMLInputElement;
    fireEvent.change(after, { target: { value: '05/01/2027' } });
    fireEvent.blur(after);
    fireEvent.click(screen.getByRole('button', { name: /^save as draft$/i }));
    await waitFor(() => expect(svc.create).toHaveBeenCalled());
    expect(svc.create.mock.calls[0][0].lines[0].date_after).toBe('2027-01-05');
  });

  it('a quantity can be cleared and retyped: the box stays empty while typing and never snaps back', async () => {
    const user = userEvent.setup();
    renderForm();
    await waitForForm();
    const row = ensureRow();
    const qty = within(row).getByLabelText('Qty before') as HTMLInputElement;
    await user.type(qty, '842');
    expect(qty.value).toBe('842');
    await user.clear(qty);
    expect(qty.value).toBe('');
    expect(messageIn(fieldBox(qty))).toBeUndefined();
    await user.type(qty, '2');
    expect(qty.value).toBe('2');
  });

  it('never caps a quantity by stock', async () => {
    const user = userEvent.setup();
    renderForm();
    await waitForForm();
    const qty = within(ensureRow()).getByLabelText('Qty after') as HTMLInputElement;
    await user.type(qty, '999999');
    expect(qty.value).toBe('999999');
  });
});

describe('G3 Save as draft and Submit', () => {
  it('Save as draft creates the notice and does not submit it', async () => {
    renderForm();
    await waitForForm();
    await fillValid();
    fireEvent.click(screen.getByRole('button', { name: /^save as draft$/i }));
    await waitFor(() => expect(svc.create).toHaveBeenCalledTimes(1));
    expect(svc.submit).not.toHaveBeenCalled();
    const body = svc.create.mock.calls[0][0];
    expect(body).toMatchObject({
      customer_name: 'Customer A',
      customer_po_no: PO,
      change_type_id: CHANGE_TYPES[3].id,
    });
    expect(body.lines).toHaveLength(1);
    expect(body.lines[0]).toMatchObject({ product_id: PRODUCT_HITS[0].id });
    expect(Number(body.lines[0].qty_before)).toBe(100);
    expect(Number(body.lines[0].qty_after)).toBe(100);
    await waitFor(() =>
      expect(nav.push).toHaveBeenCalledWith('/procurement-management/order-change-notices/ocn-new'),
    );
  });

  it('Submit creates the notice, then submits it at the revision the create answered', async () => {
    renderForm();
    await waitForForm();
    await fillValid();
    fireEvent.click(screen.getByRole('button', { name: /^submit$/i }));
    await waitFor(() => expect(svc.submit).toHaveBeenCalledTimes(1));
    expect(svc.create).toHaveBeenCalledTimes(1);
    expect(svc.create.mock.invocationCallOrder[0]).toBeLessThan(svc.submit.mock.invocationCallOrder[0]);
    expect(svc.submit).toHaveBeenCalledWith('ocn-new', 0);
    await waitFor(() =>
      expect(nav.push).toHaveBeenCalledWith('/procurement-management/order-change-notices/ocn-new'),
    );
  });

  it('a picked debtor is linked by id, and a typed name keeps customer_id empty', async () => {
    asMock(lookupCustomersForRequest).mockResolvedValue([
      { customer_id: 'c-1', debtor_name: 'Customer A', customer_code: '300-A001', debtor_type: null, sales_type: null },
    ]);
    renderForm();
    await waitForForm();
    const customer = screen.getByLabelText(/^Customer Name/);
    fireEvent.focus(customer);
    fireEvent.change(customer, { target: { value: 'custo' } });
    expect(await screen.findByText('300-A001')).toBeTruthy();
    fireEvent.click(await screen.findByRole('option', { name: /Customer A/ }));
    fireEvent.click(screen.getByRole('button', { name: /^save as draft$/i }));
    await waitFor(() => expect(svc.create).toHaveBeenCalled());
    expect(svc.create.mock.calls[0][0]).toMatchObject({ customer_id: 'c-1' });
  });

  it('a typed name that matches no debtor is kept as customer_name with no customer_id', async () => {
    renderForm();
    await waitForForm();
    await typeCustomer('Walk-in Trading');
    fireEvent.click(screen.getByRole('button', { name: /^save as draft$/i }));
    await waitFor(() => expect(svc.create).toHaveBeenCalled());
    const body = svc.create.mock.calls[0][0];
    expect(body.customer_name).toBe('Walk-in Trading');
    expect(body.customer_id ?? null).toBeNull();
  });

  it('SO No. and the description travel as plain text', async () => {
    renderForm();
    await waitForForm();
    await fillValid();
    fireEvent.change(screen.getByLabelText(/^SO No/), { target: { value: 'SO-ZZT-0001' } });
    fireEvent.change(screen.getByLabelText(/^Description/), { target: { value: 'Site not ready.' } });
    fireEvent.click(screen.getByRole('button', { name: /^save as draft$/i }));
    await waitFor(() => expect(svc.create).toHaveBeenCalled());
    expect(svc.create.mock.calls[0][0]).toMatchObject({ so_no_text: 'SO-ZZT-0001', description: 'Site not ready.' });
  });

  it('a person picked as C.S. Incharge is sent by id', async () => {
    renderForm();
    await waitForForm();
    await fillValid();
    fireEvent.click(screen.getByLabelText(/^C\.S\. Incharge/));
    fireEvent.click(await screen.findByRole('option', { name: /CS Person A/ }));
    fireEvent.click(screen.getByRole('button', { name: /^save as draft$/i }));
    await waitFor(() => expect(svc.create).toHaveBeenCalled());
    expect(svc.create.mock.calls[0][0]).toMatchObject({ cs_in_charge_user_id: 'u-cs' });
  });

  it('a server refusal is shown and the form stays', async () => {
    svc.create.mockRejectedValue(new Error('Customer PO No. is already used on another notice'));
    renderForm();
    await waitForForm();
    await fillValid();
    fireEvent.click(screen.getByRole('button', { name: /^save as draft$/i }));
    expect(await screen.findByText(/already used on another notice/)).toBeTruthy();
    expect(nav.push).not.toHaveBeenCalledWith(expect.stringMatching(/ocn-new/));
  });
});

describe('G3 validation sits next to the field and nothing is sent', () => {
  it('Submit on an empty form names Customer Name, Customer PO No., Type of change and the lines', async () => {
    renderForm();
    await waitForForm();
    fireEvent.click(screen.getByRole('button', { name: /^submit$/i }));
    await waitFor(() => expect(messageIn(fieldBox(screen.getByLabelText(/^Customer Name/)))).toBeDefined());
    expect(messageIn(fieldBox(screen.getByLabelText(/^Customer PO No/)))).toBeDefined();
    const typeBox = fieldBox(await screen.findByText('Delay'));
    expect(messageIn(typeBox), 'a message beside Type of change').toBeDefined();
    const lineMessage = Array.from(document.querySelectorAll<HTMLElement>('.text-destructive, [role="alert"]')).find(
      (n) => /line|item|product/i.test(n.textContent ?? '') && !n.closest('label'),
    );
    expect(lineMessage, 'a message about the lines').toBeDefined();
    expect(svc.create).not.toHaveBeenCalled();
    expect(svc.submit).not.toHaveBeenCalled();
  });

  it('a line without a product is refused on Submit, beside the table', async () => {
    renderForm();
    await waitForForm();
    await typeCustomer('Customer A');
    fireEvent.change(screen.getByLabelText(/^Customer PO No/), { target: { value: PO } });
    fireEvent.click(await screen.findByText('Delay'));
    ensureRow();
    fireEvent.click(screen.getByRole('button', { name: /^submit$/i }));
    await waitFor(() => {
      const found = Array.from(document.querySelectorAll<HTMLElement>('.text-destructive, [role="alert"]')).some(
        (n) => /item|product/i.test(n.textContent ?? ''),
      );
      expect(found).toBe(true);
    });
    expect(svc.create).not.toHaveBeenCalled();
  });

  it('a message goes away once the field is fixed and Submit is pressed again', async () => {
    renderForm();
    await waitForForm();
    fireEvent.click(screen.getByRole('button', { name: /^submit$/i }));
    await waitFor(() => expect(messageIn(fieldBox(screen.getByLabelText(/^Customer PO No/)))).toBeDefined());
    await fillValid();
    fireEvent.click(screen.getByRole('button', { name: /^submit$/i }));
    await waitFor(() => expect(svc.submit).toHaveBeenCalled());
    expect(messageIn(fieldBox(screen.getByLabelText(/^Customer PO No/)))).toBeUndefined();
  });
});

describe('G3 Edit opens the same form', () => {
  it('fills every field from the record, shows its status word, and names no UUID', async () => {
    renderForm({ ocnId: 'ocn-edit' });
    await waitForForm();
    await waitFor(() => expect((screen.getByLabelText(/^Customer PO No/) as HTMLInputElement).value).toBe(PO));
    expect((screen.getByLabelText(/^Customer Name/) as HTMLInputElement).value).toBe('Customer A');
    expect(screen.getByLabelText(/^Registered project/).textContent).toMatch(/Project Alpha Tower/);
    expect((screen.getByLabelText(/^Description/) as HTMLTextAreaElement).value).toMatch(/replaces ABC123-RL/);
    expect(await screen.findByText(CHANGE_TYPES[1].guide_text)).toBeTruthy();
    expect(rows()).toHaveLength(2);
    expect((within(rows()[0]).getByRole('combobox', { name: /item code/i }) as HTMLInputElement).value).toMatch(/ABC123-RL/);
    expect((within(rows()[0]).getByLabelText('Qty before') as HTMLInputElement).value).toBe('842');
    expect((within(rows()[0]).getByLabelText('Date before') as HTMLInputElement).value).toBe('15/01/2027');
    expect(document.body.textContent).not.toMatch(UUID_RE);
    expect(screen.getByText('Draft')).toBeTruthy();
  });

  it('Save as draft updates the same record and never creates a second one', async () => {
    renderForm({ ocnId: 'ocn-edit' });
    await waitFor(() => expect((screen.getByLabelText(/^Customer PO No/) as HTMLInputElement).value).toBe(PO));
    fireEvent.change(screen.getByLabelText(/^Description/), { target: { value: 'New dates' } });
    fireEvent.click(screen.getByRole('button', { name: /^save as draft$/i }));
    await waitFor(() => expect(svc.update).toHaveBeenCalledTimes(1));
    expect(svc.update.mock.calls[0][0]).toBe('ocn-edit');
    expect(svc.update.mock.calls[0][1]).toMatchObject({ description: 'New dates' });
    expect(svc.create).not.toHaveBeenCalled();
    expect(svc.submit).not.toHaveBeenCalled();
  });

  it('Submit updates then submits, and never asks for a revision reason on your own record', async () => {
    renderForm({ ocnId: 'ocn-edit' });
    await waitFor(() => expect((screen.getByLabelText(/^Customer PO No/) as HTMLInputElement).value).toBe(PO));
    expect(screen.queryByLabelText(/reason/i)).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: /^submit$/i }));
    await waitFor(() => expect(svc.submit).toHaveBeenCalledWith('ocn-edit', 0));
    expect(svc.update.mock.invocationCallOrder[0]).toBeLessThan(svc.submit.mock.invocationCallOrder[0]);
    expect(screen.queryByLabelText(/reason/i)).toBeNull();
  });

  it('the registered project can be cleared, and the save then sends no project', async () => {
    renderForm({ ocnId: 'ocn-edit' });
    await waitFor(() => expect((screen.getByLabelText(/^Customer PO No/) as HTMLInputElement).value).toBe(PO));
    const trigger = screen.getByLabelText(/^Registered project/);
    fireEvent.pointerDown(within(trigger).getByRole('button', { name: 'Clear selection' }));
    fireEvent.click(screen.getByRole('button', { name: /^save as draft$/i }));
    await waitFor(() => expect(svc.update).toHaveBeenCalled());
    expect(svc.update.mock.calls[0][1].project_id ?? null).toBeNull();
  });

  it('shows a skeleton, then ends in an error with a way back if the record cannot load', async () => {
    svc.get.mockRejectedValue(new Error('Could not load the notice'));
    renderForm({ ocnId: 'ocn-edit' });
    expect(await screen.findByText(/could not load|try again|not found/i)).toBeTruthy();
  });
});
