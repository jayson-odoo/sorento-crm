/**
 * SAMPLE-REQUEST-V2, owner hand test 12 Nov ~15:45 on #2338 (red-first):
 *   F1 the sections open like the price tag request: the first one (Customer & project) open by
 *      default, the rest collapsed; a request loaded with values opens the sections that hold them.
 *   F2 a long project title is clamped (one line, the full text on demand), never a block of text.
 *   F3 filling a section opens the next one, once; a section the person collapsed by hand stays shut.
 *   F4 two contacts chosen = both phones shown (it used to keep only the first one's).
 * F1 and F3 share the price tag request's own logic (`hooks/useProgressiveSections`).
 */
import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
  useSearchParams: () => new URLSearchParams(''),
}));
vi.mock('@/hooks/useEffectiveUserId', () => ({
  useEffectiveUserId: () => 'u-1',
  useEffectiveUserName: () => 'Aiman Hakim',
}));
vi.mock('@/lib/toast', () => ({ toast: { error: vi.fn(), success: vi.fn(), info: vi.fn() } }));

const mut = vi.hoisted(() => ({ existing: undefined as unknown }));
vi.mock('../hooks/useSampleRequests', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../hooks/useSampleRequests')>();
  return {
    ...actual,
    useSampleRequestMutations: () => ({
      create: { mutateAsync: vi.fn(async () => ({ id: 'sr-new' })), isPending: false },
      update: { mutateAsync: vi.fn(async () => ({ id: 'sr-1' })), isPending: false },
      submit: { mutateAsync: vi.fn(async () => ({ id: 'sr-1', request_no: 'SR-1' })), isPending: false },
    }),
    useSampleRequestQuery: () => ({ data: mut.existing, isLoading: false }),
    useSampleRequestSwitches: () => ({ data: { requireProject: false } }),
  };
});

const TPE = { id: 'p-1', product_code: 'TPE-9101', product_name: 'ZZT Tape', brand_name: 'ZZT' };
vi.mock('../services/sampleRequestService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../services/sampleRequestService')>();
  return {
    ...actual,
    searchSampleRequestProducts: vi.fn(async () => [TPE]),
    getSampleRequestQuotationPrefill: vi.fn(async () => ({ documents: [], document_id: null, issue_id: null, lines: [], skipped: [] })),
  };
});

const LONG_TITLE =
  'Residensi Taman Seri Murni Fasa 2B, Blok A hingga D, Pembangunan Bercampur Kediaman dan Komersial di Lot 1234';
const CONTACTS = [
  { id: 'ct-1', party_id: 'party-1', name: 'Mei Ling Tan', phone: '0123456789', email: null, job_title: null, is_active: true },
  { id: 'ct-2', party_id: 'party-1', name: 'Ravi Kumar', phone: '01111111111', email: null, job_title: null, is_active: true },
];
vi.mock('../../_shared/services/projectService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../_shared/services/projectService')>();
  return {
    ...actual,
    getProject: vi.fn(async () => ({ id: 'proj-1', project_code: 'PPF2611001', title: LONG_TITLE, address: null })),
    listPartyRoles: vi.fn(async () => []),
    getPartiesOnProject: vi.fn(async () => [
      { party_id: 'party-1', party_type: 'trading_house', role: 'trading_house', name: 'Bintang Trading Sdn Bhd',
        phone: null, address: 'No. 12, Jalan Perindustrian 3, Klang', email: null, fax: null, contacts: [] },
    ]),
    listParties: vi.fn(async () => ({ data: [] })),
    listPartyContacts: vi.fn(async () => CONTACTS),
    listProjects: vi.fn(async () => ({ data: [] })),
    listQuotations: vi.fn(async () => []),
  };
});

// The proposal's contact chooser, reduced to what it hands back: Done with both contacts ticked
// gives the ids, the joined names and (as the proposal Attn does) the FIRST contact's phone only.
vi.mock('../../[projectId]/quotation-documents/components/QuotationRecipientPicker', () => ({
  QuotationAttnChooser: ({ onChange }: { onChange: (p: Record<string, unknown>) => void }) => (
    <button
      type="button"
      onClick={() =>
        onChange({
          attn_contact_ids: ['ct-1', 'ct-2'],
          attn_name: 'Mei Ling Tan & Ravi Kumar',
          recipient_phone_snapshot: '012-345 6789',
        })
      }
    >
      Choose contacts
    </button>
  ),
}));

vi.mock(
  '@/app/(protected)/procurement-management/purchase-requests/services/customerLookupService',
  () => ({
    lookupCustomersForRequest: vi.fn(async () => [
      { customer_id: 'c-1', debtor_name: 'JV PERKASA SDN BHD', customer_code: '300-J099', debtor_type: null, sales_type: null },
    ]),
  }),
);

import SampleRequestForm from './SampleRequestForm';
import { getProject, listPartyContacts } from '../../_shared/services/projectService';
import { getSampleRequestQuotationPrefill } from '../services/sampleRequestService';

const SECTIONS = ['Customer & project', 'Ship to', 'Items', 'Delivery'] as const;
const trigger = (title: string) => screen.getByRole('button', { name: new RegExp(`^${title}`) });
const expanded = (title: string) => trigger(title).getAttribute('aria-expanded');

let client: QueryClient;
function renderForm(props: { requestId?: string; projectId?: string } = {}) {
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SampleRequestForm {...props} />
    </QueryClientProvider>,
  );
}

async function pickCustomer() {
  const customer = screen.getByLabelText(/^Customer/);
  fireEvent.focus(customer);
  fireEvent.change(customer, { target: { value: 'perkasa' } });
  fireEvent.click(await screen.findByRole('option', { name: /JV PERKASA SDN BHD/ }));
}

async function pickParty() {
  fireEvent.click(document.getElementById('sr-ship-to') as HTMLElement);
  fireEvent.click(await screen.findByRole('option', { name: /Bintang Trading/ }));
}

async function pickProduct() {
  const box = screen.getAllByRole('combobox', { name: /item code/i })[0];
  if (box.tagName === 'INPUT') {
    fireEvent.focus(box);
    fireEvent.change(box, { target: { value: 'tpe' } });
  } else {
    fireEvent.click(box);
    fireEvent.change(screen.getByPlaceholderText('Search...'), { target: { value: 'tpe' } });
  }
  fireEvent.click(await screen.findByRole('option', { name: /TPE-9101/ }));
}

const READY_DRAFT = {
  id: 'sr-1', request_no: 'SR-000231', status: 'draft', status_label: 'Draft',
  customer_id: 'c-1', customer_name: 'NUSANTARA BUILDERS SDN BHD', project_id: null,
  project_title: 'Residensi', ship_to_party_id: 'party-1', ship_to_role: null,
  ship_to_name: 'Bintang Trading Sdn Bhd', ship_to_address: 'No. 12, Klang',
  site_contact_name: 'Mei Ling Tan', site_contact_phone: '012-345 6789',
  delivery_date: '2026-11-18', delivery_mode: 'driver', loan_value: 2, loan_unit: 'months',
  goods_from: 'either', board_mounting: false,
  lines: [{ id: 'l1', line_no: 1, product_id: 'p-1', product_code: 'TPE-9101', product_name: 'ZZT Tape', qty: 1, remark: null }],
};

beforeEach(() => {
  mut.existing = undefined;
  (listPartyContacts as unknown as ReturnType<typeof vi.fn>).mockImplementation(async () => CONTACTS);
  (getSampleRequestQuotationPrefill as unknown as ReturnType<typeof vi.fn>).mockImplementation(async () => ({
    documents: [], document_id: null, issue_id: null, lines: [], skipped: [],
  }));
});

describe('F1: sections open like the price tag request', () => {
  it('a new request opens the first section (Customer & project) and keeps the rest collapsed', async () => {
    renderForm();
    await screen.findByText('Customer & project');
    expect(expanded('Customer & project')).toBe('true');
    for (const t of ['Ship to', 'Items', 'Delivery']) expect(expanded(t)).toBe('false');
  });

  it('a loaded draft opens every section that already holds a value', async () => {
    mut.existing = READY_DRAFT;
    renderForm({ requestId: 'sr-1' });
    await screen.findByText('Customer & project');
    await waitFor(() => {
      for (const t of SECTIONS) expect(expanded(t)).toBe('true');
    });
  });
});

describe('F3: filling a section opens the next one', () => {
  it('a customer opens Ship to, a party opens Items, a product opens Delivery', async () => {
    renderForm({ projectId: 'proj-1' });
    await screen.findByText('Customer & project');
    await pickCustomer();
    await waitFor(() => expect(expanded('Ship to')).toBe('true'));
    expect(expanded('Items')).toBe('false');
    await pickParty();
    await waitFor(() => expect(expanded('Items')).toBe('true'));
    expect(expanded('Delivery')).toBe('false');
    await pickProduct();
    await waitFor(() => expect(expanded('Delivery')).toBe('true'));
  });

  it('a section the person collapsed by hand is not reopened by the rule', async () => {
    renderForm();
    await screen.findByText('Customer & project');
    fireEvent.click(trigger('Ship to')); // open
    fireEvent.click(trigger('Ship to')); // and shut it again, by hand
    await pickCustomer();
    await new Promise((r) => setTimeout(r, 50));
    expect(expanded('Ship to')).toBe('false');
  });
});

describe('F2: a long project title is clamped, the full text on demand', () => {
  it('the fixed Project shows one clamped line with the whole title on hover and behind the eye', async () => {
    renderForm({ projectId: 'proj-1' });
    const full = `PPF2611001 - ${LONG_TITLE}`;
    await screen.findByText('Customer & project');
    // The Project field itself, not the section header's one-line summary.
    await waitFor(() =>
      expect(screen.getAllByTitle(full).filter((el) => !el.closest('button')).length).toBe(1),
    );
    const label = screen.getAllByTitle(full).filter((el) => !el.closest('button'))[0];
    // The eye ("Show full title") appears once the browser measures the clamp; jsdom has no layout,
    // so the cloud browser pass checks it.
    expect(label.className).toMatch(/(^|\s)truncate(\s|$)/);
  });
});

describe('F4: every chosen contact keeps its phone', () => {
  it('two contacts chosen: both phones show under Contact person, not the first one only', async () => {
    renderForm({ projectId: 'proj-1' });
    await screen.findByText('Customer & project');
    fireEvent.click(trigger('Ship to'));
    await pickParty();
    // The real chooser opens its popup only once the party's contacts have answered.
    await waitFor(() => expect(listPartyContacts).toHaveBeenCalled());
    await new Promise((r) => setTimeout(r, 20));
    fireEvent.click(screen.getByRole('button', { name: 'Choose contacts' }));
    expect((screen.getByLabelText('Contact person') as HTMLInputElement).value).toBe('Mei Ling Tan & Ravi Kumar');
    await waitFor(() => expect(screen.getByText(/012-345 6789/)).toBeTruthy());
    expect(screen.getByText(/011-1111 1111/)).toBeTruthy();
  });
});

describe('review round (owner F1-F4)', () => {
  it('B1: a contact added inside the popup keeps its phone once the contact list refreshes', async () => {
    // The popup's own refetch lands after it hands back the picks: the form catches up from it.
    (listPartyContacts as unknown as ReturnType<typeof vi.fn>).mockImplementation(async () => [CONTACTS[0]]);
    renderForm({ projectId: 'proj-1' });
    await screen.findByText('Customer & project');
    fireEvent.click(trigger('Ship to'));
    await pickParty();
    await waitFor(() => expect(listPartyContacts).toHaveBeenCalled());
    await new Promise((r) => setTimeout(r, 20));
    fireEvent.click(screen.getByRole('button', { name: 'Choose contacts' }));
    (listPartyContacts as unknown as ReturnType<typeof vi.fn>).mockImplementation(async () => CONTACTS);
    await client.invalidateQueries();
    await waitFor(() => expect(screen.getByText(/011-1111 1111/)).toBeTruthy());
    expect(screen.getByText(/012-345 6789/)).toBeTruthy();
  });

  it('S1: a loaded draft with lines but no party opens Items', async () => {
    mut.existing = { ...READY_DRAFT, ship_to_party_id: null, ship_to_name: '', ship_to_address: '', delivery_date: null };
    renderForm({ requestId: 'sr-1' });
    await screen.findByText('Customer & project');
    await waitFor(() => expect(expanded('Items')).toBe('true'));
  });

  it('S2: a quotation prefill fills the lines but Delivery waits for the party', async () => {
    (getSampleRequestQuotationPrefill as unknown as ReturnType<typeof vi.fn>).mockImplementation(async () => ({
      documents: [{ id: 'q-1', label: 'Q1' }], document_id: 'q-1', issue_id: null,
      lines: [{ product_id: 'p-1', product_code: 'TPE-9101', product_name: 'ZZT Tape' }], skipped: [],
    }));
    renderForm({ projectId: 'proj-1' });
    await screen.findByText('Customer & project');
    await waitFor(() => expect(getSampleRequestQuotationPrefill).toHaveBeenCalled());
    await new Promise((r) => setTimeout(r, 50));
    expect(expanded('Delivery')).toBe('false');
  });

  it('S2: a Submit problem in Items opens Items, even after it was shut by hand', async () => {
    renderForm();
    await screen.findByText('Customer & project');
    fireEvent.click(trigger('Items'));
    fireEvent.click(trigger('Items'));
    expect(expanded('Items')).toBe('false');
    fireEvent.click(screen.getByRole('button', { name: /^submit$/i }));
    await waitFor(() => expect(expanded('Items')).toBe('true'));
  });
});

describe('crew pass round 3 (owner point 1)', () => {
  it('a customer prefilled from the project does not count as filled: Ship to stays collapsed at first load', async () => {
    (getProject as unknown as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      id: 'proj-1', project_code: 'PPF2611001', title: LONG_TITLE, address: null,
      customer_id: 'c-9', customer_name: 'NUSANTARA BUILDERS SDN BHD',
    });
    renderForm({ projectId: 'proj-1' });
    await screen.findByText('Customer & project');
    expect(await screen.findByDisplayValue(/NUSANTARA BUILDERS/)).toBeTruthy();
    await new Promise((r) => setTimeout(r, 50));
    expect(expanded('Customer & project')).toBe('true');
    for (const t of ['Ship to', 'Items', 'Delivery']) expect(expanded(t)).toBe('false');
  });
});

describe('crew re-pass on d54bb314c1 (step 13): a loaded draft opens only the sections holding values', () => {
  it('a customer but an empty Ship to: Ship to stays collapsed', async () => {
    mut.existing = {
      ...READY_DRAFT, ship_to_party_id: null, ship_to_name: '', ship_to_address: '',
      site_contact_name: '', site_contact_phone: '', delivery_date: null, delivery_mode: null,
      lines: [],
    };
    renderForm({ requestId: 'sr-1' });
    await screen.findByText('Customer & project');
    await new Promise((r) => setTimeout(r, 50));
    expect(expanded('Customer & project')).toBe('true');
    for (const t of ['Ship to', 'Items', 'Delivery']) expect(expanded(t)).toBe('false');
  });

  it('a party but no lines: Ship to opens, Items stays collapsed', async () => {
    mut.existing = { ...READY_DRAFT, delivery_date: null, delivery_mode: null, lines: [] };
    renderForm({ requestId: 'sr-1' });
    await screen.findByText('Customer & project');
    await waitFor(() => expect(expanded('Ship to')).toBe('true'));
    await new Promise((r) => setTimeout(r, 50));
    expect(expanded('Items')).toBe('false');
    expect(expanded('Delivery')).toBe('false');
  });
});
