/**
 * SR-CORE staff New / Edit form, restructured by SAMPLE-REQUEST-V2 (owner 11 Nov): four guided
 * sections (Customer & project / Ship to / Items / Delivery), ship to = a party of the project,
 * the customer an AutoCount debtor only, "For" and the free contact phone / note gone, Preview the
 * page's one main button and Submit inside its popup, every exit back to where the person came
 * from (`?from=`). Card: documentation/plans/project-sales/CARD-sample-request-v2-11nov.md.
 * Line table, product search and number-field rules (AC-SR-11, 12, 80, round 9) are unchanged.
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';

const nav = vi.hoisted(() => ({ push: vi.fn(), search: '' }));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: nav.push, replace: vi.fn(), back: vi.fn() }),
  useSearchParams: () => new URLSearchParams(nav.search),
}));

vi.mock('@/lib/toast', () => ({
  toast: { error: vi.fn(), success: vi.fn(), info: vi.fn() },
}));

const mut = vi.hoisted(() => ({
  createAsync: vi.fn(),
  updateAsync: vi.fn(),
  submitAsync: vi.fn(),
  existing: undefined as unknown,
}));

vi.mock('../hooks/useSampleRequests', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../hooks/useSampleRequests')>();
  return {
    ...actual,
    useSampleRequestMutations: () => ({
      create: { mutateAsync: mut.createAsync, isPending: false },
      update: { mutateAsync: mut.updateAsync, isPending: false },
      submit: { mutateAsync: mut.submitAsync, isPending: false },
    }),
    useSampleRequestQuery: () => ({ data: mut.existing, isLoading: false }),
    useSampleRequestSwitches: () => ({ data: { requireProject: false } }),
  };
});

vi.mock('../services/sampleRequestService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../services/sampleRequestService')>();
  return { ...actual, searchSampleRequestProducts: vi.fn() };
});

vi.mock('../../_shared/services/projectService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../_shared/services/projectService')>();
  return {
    ...actual,
    getProject: vi.fn(async () => ({})),
    listPartyRoles: vi.fn(async () => []),
    getPartiesOnProject: vi.fn(async () => []),
    listParties: vi.fn(async () => ({ data: [] })),
    listPartyContacts: vi.fn(async () => []),
    listProjects: vi.fn(async () => ({ data: [] })),
    listQuotations: vi.fn(async () => []),
  };
});

vi.mock(
  '@/app/(protected)/procurement-management/purchase-requests/services/customerLookupService',
  () => ({ lookupCustomersForRequest: vi.fn(async () => []) }),
);

import { searchSampleRequestProducts } from '../services/sampleRequestService';
import { lookupCustomersForRequest } from '@/app/(protected)/procurement-management/purchase-requests/services/customerLookupService';
import { typeBadInput } from '@/test-utils/badInput';
import SampleRequestForm from './SampleRequestForm';

const asMock = (fn: unknown) => fn as ReturnType<typeof vi.fn>;
const TPE = { id: 'p-1', product_code: 'TPE-9101', product_name: 'ZZT Tape', brand_name: 'ZZT' };

function renderForm(props: { requestId?: string; projectId?: string } = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SampleRequestForm {...props} />
    </QueryClientProvider>,
  );
}

const rows = () =>
  Array.from(document.querySelectorAll<HTMLElement>('[data-testid="sample-request-line"]'));
const clickAddRow = () => fireEvent.click(screen.getByRole('button', { name: /^\+?\s*add row$/i }));
const ensureRow = (): HTMLElement => {
  if (rows().length === 0) clickAddRow();
  return rows()[0];
};
const labelNode = (re: RegExp): HTMLElement => screen.getAllByText(re)[0];

/** Types into a row's product search, whether it is a text input or a select trigger. */
function searchProduct(row: HTMLElement, text: string) {
  const box = within(row).getByRole('combobox', { name: /item code/i });
  if (box.tagName === 'INPUT') {
    fireEvent.focus(box);
    fireEvent.change(box, { target: { value: text } });
  } else {
    fireEvent.click(box);
    fireEvent.change(screen.getByPlaceholderText('Search...'), { target: { value: text } });
  }
  return box;
}

const shows = (row: HTMLElement, text: string) =>
  row.textContent?.includes(text) ||
  Array.from(row.querySelectorAll('input')).some((i) => (i as HTMLInputElement).value.includes(text));

const fold = (q: string) => q.toLowerCase().replace(/[^a-z0-9]/g, '');

beforeEach(() => {
  vi.clearAllMocks();
  nav.search = '';
  mut.existing = undefined;
  mut.createAsync.mockResolvedValue({ id: 'sr-new' });
  mut.updateAsync.mockResolvedValue({ id: 'sr-new' });
  mut.submitAsync.mockResolvedValue({ id: 'sr-new', request_no: 'SR-000231' });
  asMock(searchSampleRequestProducts).mockImplementation(async (q: string) =>
    fold(q) === 'tpe9101' ? [TPE] : [],
  );
  asMock(lookupCustomersForRequest).mockResolvedValue([]);
});

describe('SAMPLE-REQUEST-V2 the guided form', () => {
  it('has the four sections in order, not the paper card', async () => {
    renderForm();
    const order = ['Customer & project', 'Ship to', 'Items', 'Delivery'].map(
      (t) => screen.getAllByText(t, { selector: 'span' })[0],
    );
    await screen.findByText('Customer & project');
    for (let i = 0; i < order.length - 1; i += 1) {
      expect(order[i].compareDocumentPosition(order[i + 1]) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    }
    expect(screen.queryByText('Consignment Requisition Form')).toBeNull();
  });

  it('drops For, the free contact phone / note, and the empty Consignment / PO numbers', async () => {
    renderForm();
    await screen.findByText('Customer & project');
    expect(screen.queryByLabelText(/^For\b/)).toBeNull();
    expect(screen.queryByText(/^Contact Phone/)).toBeNull();
    expect(screen.queryByLabelText(/note/i)).toBeNull();
    expect(screen.queryByText(/^Consignment No/)).toBeNull();
    expect(screen.queryByText(/^PO No/)).toBeNull();
  });

  it('has no Quotation, Or (alternative) or Immediate arrangement anywhere', async () => {
    renderForm();
    await screen.findByText('Customer & project');
    clickAddRow();
    const text = document.body.textContent ?? '';
    expect(text).not.toMatch(/quotation/i);
    expect(text).not.toMatch(/or \(alternative\)/i);
    expect(text).not.toMatch(/immediate/i);
  });

  it('has the footer fields, Save as draft, and Preview as the only main button', async () => {
    renderForm();
    await screen.findByText('Customer & project');
    for (const name of ['Deliver-Van', 'Self-Deliver', 'Self-Collection']) {
      expect(screen.getByRole('radio', { name })).toBeTruthy();
    }
    expect(labelNode(/^Loan Period/)).toBeTruthy();
    expect(labelNode(/^Goods Taken From/)).toBeTruthy();
    expect(labelNode(/^Purpose/)).toBeTruthy();
    expect(screen.getByRole('button', { name: /^save as draft$/i })).toBeTruthy();
    expect(screen.getByRole('button', { name: /^preview$/i })).toBeTruthy();
    // Submit lives in the preview popup only (one main button per screen).
    expect(screen.queryByRole('button', { name: /^submit$/i })).toBeNull();
  });

  it('the delivery date is the dd/mm/yyyy picker, not a native date input', async () => {
    renderForm();
    await screen.findByText('Customer & project');
    expect(document.querySelector('input[type="date"]')).toBeNull();
    expect(screen.getByPlaceholderText('DD/MM/YYYY')).toBeTruthy();
  });
});

describe('AC-SR-80 the line table', () => {
  it('has the Item Code, Qty and Remark headers and Add row appends a product row', async () => {
    renderForm();
    await screen.findByText('Customer & project');
    clickAddRow();
    expect(screen.getAllByText(/^Item Code/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/^Qty$/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/^Remark$/).length).toBeGreaterThan(0);
    const before = rows().length;
    expect(before).toBeGreaterThan(0);
    clickAddRow();
    expect(rows().length).toBe(before + 1);
  });

  it('keeps the board in row 1 as a checkbox with a label, never as a product row', async () => {
    renderForm();
    await screen.findByText('Customer & project');
    const board = screen.getByRole('checkbox', { name: /mount & label sample board/i });
    expect(board.closest('[data-testid="sample-request-line"]')).toBeNull();
    const before = rows().length;
    fireEvent.click(board);
    expect(await screen.findByRole('textbox', { name: /board label/i })).toBeTruthy();
    expect(rows().length).toBe(before);
  });
});

describe('AC-SR-11 product search lists and never picks', () => {
  it('"tpe9101" lists TPE-9101 and leaves the row empty until it is clicked', async () => {
    renderForm();
    await screen.findByText('Customer & project');
    const row = ensureRow();
    searchProduct(row, 'tpe9101');

    const option = await screen.findByRole('option', { name: /TPE-9101/ });
    expect(asMock(searchSampleRequestProducts)).toHaveBeenCalledWith('tpe9101');
    expect(shows(row, 'TPE-9101')).toBeFalsy();

    fireEvent.click(option);
    await waitFor(() => expect(shows(row, 'TPE-9101')).toBeTruthy());
  });
});

describe('AC-SR-12 product not in the list', () => {
  it('shows the card sentence and adds nothing', async () => {
    renderForm();
    await screen.findByText('Customer & project');
    const row = ensureRow();
    const before = rows().length;
    searchProduct(row, 'B2155-BLUE-NL');

    expect(
      await screen.findByText(
        'B2155-BLUE-NL is not in the product list. Pick the product you mean, or ask purchasing to add it as a new product before you request it.',
      ),
    ).toBeTruthy();
    expect(rows().length).toBe(before);
    expect(shows(row, 'TPE-9101')).toBeFalsy();
  });
});

describe('AC-SR-02 / AC-SR-03 Preview names the missing field', () => {
  it('without a Request Delivery Date shows an error naming it and does not save', async () => {
    renderForm();
    await screen.findByText('Customer & project');
    fireEvent.click(screen.getByRole('button', { name: /^preview$/i }));

    const messages = await screen.findAllByText(
      (content, el) =>
        el?.tagName !== 'LABEL' &&
        /request delivery date/i.test(content) &&
        content.trim().length > 'Request Delivery Date'.length + 2,
    );
    expect(messages.length).toBeGreaterThan(0);
    expect(mut.createAsync).not.toHaveBeenCalled();
    expect(mut.submitAsync).not.toHaveBeenCalled();
    expect(screen.queryByText('Preview sample request')).toBeNull();
  });

  it('without a delivery mode shows "Choose a delivery mode"', async () => {
    renderForm();
    await screen.findByText('Customer & project');
    fireEvent.click(screen.getByRole('button', { name: /^preview$/i }));
    expect(await screen.findByText(/choose a delivery mode/i)).toBeTruthy();
    expect(mut.createAsync).not.toHaveBeenCalled();
  });

  it('without a ship-to party says who the samples go to (rule 2)', async () => {
    renderForm();
    await screen.findByText('Customer & project');
    fireEvent.click(screen.getByRole('button', { name: /^preview$/i }));
    expect(await screen.findByText('Pick who the samples go to')).toBeTruthy();
  });
});

describe('rule 1: the customer is an AutoCount debtor', () => {
  it('a typed name that matches no debtor is not kept', async () => {
    renderForm();
    await screen.findByText('Customer & project');
    const customer = screen.getByLabelText(/^Customer/) as HTMLInputElement;
    fireEvent.focus(customer);
    fireEvent.change(customer, { target: { value: 'Walk-in Trading' } });
    await waitFor(() => expect(lookupCustomersForRequest).toHaveBeenCalled());
    fireEvent.blur(customer);
    await new Promise((r) => setTimeout(r, 250));

    fireEvent.click(screen.getByRole('button', { name: /^save as draft$/i }));
    await waitFor(() => expect(mut.createAsync).toHaveBeenCalled());
    expect(mut.createAsync.mock.calls[0][0]).toMatchObject({ customer_id: null, customer_name: null });
    fireEvent.click(screen.getByRole('button', { name: /^preview$/i }));
    expect(await screen.findByText('Pick the customer')).toBeTruthy();
  });

  it('lists a debtor with its code and links the pick', async () => {
    asMock(lookupCustomersForRequest).mockResolvedValue([
      {
        customer_id: 'c-1',
        debtor_name: 'JV PERKASA SDN BHD',
        customer_code: '300-J099',
        debtor_type: null,
        sales_type: null,
      },
    ]);
    renderForm();
    await screen.findByText('Customer & project');
    const customer = screen.getByLabelText(/^Customer/);
    fireEvent.focus(customer);
    fireEvent.change(customer, { target: { value: 'perkasa' } });
    expect(await screen.findByText('300-J099')).toBeTruthy();
    fireEvent.click(await screen.findByRole('option', { name: /JV PERKASA SDN BHD/ }));

    fireEvent.click(screen.getByRole('button', { name: /^save as draft$/i }));
    await waitFor(() => expect(mut.createAsync).toHaveBeenCalled());
    expect(mut.createAsync.mock.calls[0][0]).toMatchObject({ customer_id: 'c-1' });
  });
});

/** A draft that passes every staff rule, as the server returns it. */
const READY_DRAFT = {
  id: 'sr-1',
  request_no: 'SR-000231',
  status: 'draft',
  status_label: 'Draft',
  customer_id: 'c-1',
  customer_name: 'NUSANTARA BUILDERS SDN BHD',
  project_id: null,
  project_title: 'Residensi Taman Seri Murni',
  ship_to_party_id: 'party-1',
  ship_to_role: null,
  ship_to_name: 'Bintang Trading Sdn Bhd',
  ship_to_address: 'No. 12, Jalan Perindustrian 3, Klang',
  site_contact_name: 'Mei Ling Tan',
  site_contact_phone: '012-345 6789',
  scope_note: 'show unit',
  site_contact_note: 'call first',
  delivery_date: '2026-11-18',
  delivery_mode: 'driver',
  loan_value: 2,
  loan_unit: 'months',
  goods_from: 'either',
  board_mounting: false,
  lines: [
    { id: 'l1', line_no: 1, product_id: 'p-1', product_code: 'TPE-9101', product_name: 'ZZT Tape', qty: 1, remark: null },
  ],
};

describe('Preview, then Submit in the popup', () => {
  it('opens the preview with the request as the sample team reads it, and Submit sends it', async () => {
    mut.existing = READY_DRAFT;
    mut.updateAsync.mockResolvedValue({ id: 'sr-1', request_no: 'SR-000231' });
    renderForm({ requestId: 'sr-1' });
    await screen.findByText('Customer & project');
    fireEvent.click(screen.getByRole('button', { name: /^preview$/i }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText('Preview sample request')).toBeTruthy();
    expect(within(dialog).getByText(/Bintang Trading Sdn Bhd/)).toBeTruthy();
    expect(within(dialog).getByText(/Mei Ling Tan, 012-345 6789/)).toBeTruthy();
    expect(mut.updateAsync).not.toHaveBeenCalled();

    fireEvent.click(within(dialog).getByRole('button', { name: /^submit$/i }));
    await waitFor(() => expect(mut.submitAsync).toHaveBeenCalledWith('sr-1'));
    const body = mut.updateAsync.mock.calls[0][0].data;
    expect(body).toMatchObject({
      customer_id: 'c-1',
      ship_to_party_id: 'party-1',
      delivery_date: '2026-11-18',
      delivery_mode: 'driver',
    });
    // Rules 3-4: the staff form never writes For or the contact note; the server prints the
    // party name and the contact from the party.
    expect(body).not.toHaveProperty('scope_note');
    expect(body).not.toHaveProperty('site_contact_note');
    expect(body).not.toHaveProperty('ship_to_name');
    expect(body).not.toHaveProperty('quotation_version_id');
  });
});

describe('owner 16:30: every exit returns to where the person started', () => {
  it('Submit from a project tab goes back to that tab', async () => {
    nav.search = `from=${encodeURIComponent('/project-sales/pr-1?tab=sample-requests')}`;
    mut.existing = READY_DRAFT;
    mut.updateAsync.mockResolvedValue({ id: 'sr-1', request_no: 'SR-000231' });
    renderForm({ requestId: 'sr-1' });
    await screen.findByText('Customer & project');
    fireEvent.click(screen.getByRole('button', { name: /^preview$/i }));
    fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: /^submit$/i }));
    await waitFor(() => expect(nav.push).toHaveBeenCalledWith('/project-sales/pr-1?tab=sample-requests'));
  });

  it('Save as draft without an origin goes to the Sample Requests list', async () => {
    renderForm();
    await screen.findByText('Customer & project');
    fireEvent.click(screen.getByRole('button', { name: /^save as draft$/i }));
    await waitFor(() => expect(nav.push).toHaveBeenCalledWith('/project-sales/sample-requests'));
  });

  it('an origin that is not a same-app path is ignored', async () => {
    nav.search = `from=${encodeURIComponent('https://evil.example/x')}`;
    renderForm();
    await screen.findByText('Customer & project');
    fireEvent.click(screen.getByRole('button', { name: /^save as draft$/i }));
    await waitFor(() => expect(nav.push).toHaveBeenCalledWith('/project-sales/sample-requests'));
  });
});

describe('number fields round 9: Save as draft refuses a bad quantity or loan period like Submit', () => {
  const SENTENCE = 'Enter a whole number of at least 1.';
  async function pickProduct() {
    const row = ensureRow();
    searchProduct(row, 'tpe9101');
    fireEvent.click(await screen.findByRole('option', { name: /TPE-9101/ }));
    return row;
  }
  const draft = () => fireEvent.click(screen.getByRole('button', { name: /^save as draft$/i }));
  const nothingSent = () => {
    expect(mut.createAsync).not.toHaveBeenCalled();
    expect(mut.updateAsync).not.toHaveBeenCalled();
  };

  it('a blank Quantity sends nothing and shows the sentence', async () => {
    renderForm();
    await screen.findByText('Customer & project');
    const row = await pickProduct();
    fireEvent.change(within(row).getByLabelText('Quantity'), { target: { value: '' } });
    draft();
    expect(await screen.findByText(SENTENCE)).toBeTruthy();
    nothingSent();
  });

  it('a Quantity of 0 sends nothing and shows the sentence', async () => {
    renderForm();
    await screen.findByText('Customer & project');
    const row = await pickProduct();
    fireEvent.change(within(row).getByLabelText('Quantity'), { target: { value: '0' } });
    draft();
    expect(await screen.findByText(SENTENCE)).toBeTruthy();
    nothingSent();
  });

  it('a bad-input Quantity sends nothing and shows the sentence', async () => {
    renderForm();
    await screen.findByText('Customer & project');
    const row = await pickProduct();
    typeBadInput(within(row).getByLabelText('Quantity'));
    draft();
    expect(await screen.findByText(SENTENCE)).toBeTruthy();
    nothingSent();
  });

  it('a blank Loan Period sends nothing and shows the sentence', async () => {
    renderForm();
    await screen.findByText('Customer & project');
    await pickProduct();
    fireEvent.change(screen.getByLabelText('Loan Period'), { target: { value: '' } });
    draft();
    expect(await screen.findByText(SENTENCE)).toBeTruthy();
    nothingSent();
  });

  it('a bad-input Loan Period sends nothing and shows the sentence', async () => {
    renderForm();
    await screen.findByText('Customer & project');
    await pickProduct();
    typeBadInput(screen.getByLabelText('Loan Period'));
    draft();
    expect(await screen.findByText(SENTENCE)).toBeTruthy();
    nothingSent();
  });

  it('S1 guard: a refused Preview with a blank Loan Period shows the sentence under the box', async () => {
    renderForm();
    await screen.findByText('Customer & project');
    fireEvent.change(screen.getByLabelText('Loan Period'), { target: { value: '' } });
    fireEvent.click(screen.getByRole('button', { name: /^preview$/i }));
    expect(await screen.findByText(SENTENCE)).toBeTruthy();
    nothingSent();
  });
});
