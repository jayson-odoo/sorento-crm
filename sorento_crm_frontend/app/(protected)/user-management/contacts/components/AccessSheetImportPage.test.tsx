/**
 * Lane BULK-CONTACT-ACCESS, UAC U11, U13-U15, U20: Import access sheet, as a page since
 * BULK-ACCESS-PREVIEW (owner 27 Oct: "a new page [...] so I can scroll down, have pagination").
 * Upload -> Preview -> Result.
 * The feature service is mocked: `previewAccessSheet(file)` and `applyAccessSheet(file, confirmed)`.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/components/common/FileDropzone', () => ({
  FileDropzone: (props: { onFilesChange: (files: File[]) => void }) => (
    <input
      aria-label="Access sheet file"
      type="file"
      onChange={(e) => props.onFilesChange(Array.from(e.target.files ?? []))}
    />
  ),
}));

const toastMock = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() }));
vi.mock('@/lib/toast', () => ({ toast: toastMock }));

const svc = vi.hoisted(() => ({ previewAccessSheet: vi.fn(), applyAccessSheet: vi.fn() }));
vi.mock('@/services/contactAccessSheetService', () => svc);

const routerMock = vi.hoisted(() => ({ push: vi.fn(), back: vi.fn() }));
vi.mock('next/navigation', () => ({
  useRouter: () => routerMock,
  usePathname: () => '/user-management/contacts/access-sheet',
}));
vi.mock('@/components/common/PageHeader', () => ({
  PageHeader: (props: { title: string }) => <h1>{props.title}</h1>,
}));

const customerSvc = vi.hoisted(() => ({ searchCustomersSelect: vi.fn() }));
vi.mock('@/app/(protected)/order-management/customers/services/customerService', () => customerSvc);

// Stand-in for the Radix multi-select: one button per fetched option, chips for the selected ones.
vi.mock('@/components/common/SearchableMultiSelect', () => ({
  SearchableMultiSelect: (props: {
    value: string[];
    onChange: (v: string[]) => void;
    fetchOptions?: (q: string) => Promise<{ value: string; label: string }[]>;
    selectedOptions?: { value: string; label: string }[];
  }) => {
    const [opts, setOpts] = React.useState<{ value: string; label: string }[]>([]);
    React.useEffect(() => {
      void props.fetchOptions?.('').then(setOpts);
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);
    return (
      <div data-testid="extra-search">
        {opts.map((o) => (
          <button key={o.value} type="button" onClick={() => props.onChange([...props.value, o.value])}>
            {`search result ${o.label}`}
          </button>
        ))}
        {(props.selectedOptions ?? []).map((o) => (
          <span key={o.value}>{o.label}</span>
        ))}
      </div>
    );
  },
}));

import AccessSheetImportPage from './AccessSheetImportPage';

const acct = (id: string, over: Record<string, unknown> = {}) => ({
  customer_id: id, customer_code: `300-${id}`, customer_name: `ACCOUNT ${id}`, company_code: 'SRT', is_active: true,
  sales_agent: 'AG ONE', sheet_agent: 'AG ONE', match: 'exact', score: 1, proposed: true, links_to: [], ...over,
});
const person = (name: string, over: Record<string, unknown> = {}) => ({
  line: 2, name, phone: '+60100000001', in_crm: true, contact_id: `id-${name}`, role: 'owner', companies: ['SRT'],
  template: 'SRT owner', status: 'applied', skip_reason: null, changes: [], warnings: [], not_applied: [],
  holds_more_items: [], outside_links: [], ...over,
});

const PREVIEW = {
  dry_run: true,
  counts: {
    rows: 3, row_errors: 0, contacts_found: 3, not_in_crm: 0, ambiguous: 0, already_configured: 0,
    blocks: 2, blocks_exact: 1, blocks_pick: 1, blocks_none: 0, applied: 3, no_change: 0, skipped: 0,
  },
  errors: [],
  blocks: [
    {
      key: 'alpha bath', dealer: 'ALPHA BATH SDN BHD', alt_dealers: [], companies: ['SRT'], status: 'exact', warnings: [],
      accounts: [acct('a1'), acct('a2')], contacts: [person('Ann'), person('Ari')],
    },
    {
      key: 'beta tiles', dealer: 'BETA TILES SDN BHD', alt_dealers: [], companies: ['SRT'], status: 'pick', warnings: [],
      accounts: [acct('b1', { match: 'candidate', score: 0.9, proposed: false })], contacts: [person('Bob')],
    },
  ],
};

const RESULT = {
  ...PREVIEW,
  dry_run: false,
  counts: { ...PREVIEW.counts, applied: 2, no_change: 0, skipped: 1 },
  blocks: [
    { ...PREVIEW.blocks[0] },
    { ...PREVIEW.blocks[1], contacts: [person('Bob', { status: 'skipped', skip_reason: 'dealer_not_confirmed' })] },
  ],
};

function renderDialog() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <AccessSheetImportPage />
    </QueryClientProvider>,
  );
}

const file = new File(['First Name,Phone Number,Tags\n'], 'sheet.csv', { type: 'text/csv' });

function pickFile() {
  fireEvent.change(screen.getByLabelText('Access sheet file'), { target: { files: [file] } });
}

async function toPreview() {
  pickFile();
  fireEvent.click(screen.getByRole('button', { name: /^Preview/ }));
  await screen.findAllByText('ALPHA BATH SDN BHD');
}

beforeEach(() => {
  // Every card starts open, so a pick card's customer search mounts and fetches at once.
  customerSvc.searchCustomersSelect.mockResolvedValue([]);
  svc.previewAccessSheet.mockResolvedValue(PREVIEW);
  svc.applyAccessSheet.mockResolvedValue(RESULT);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('AccessSheetImportPage', () => {
  it('upload step: Preview stays off until a file is chosen, then sends the file to the dry run', async () => {
    renderDialog();
    expect((screen.getByRole('button', { name: /^Preview/ }) as HTMLButtonElement).disabled).toBe(true);
    pickFile();
    fireEvent.click(screen.getByRole('button', { name: /^Preview/ }));
    await waitFor(() => expect(svc.previewAccessSheet).toHaveBeenCalledWith(file));
    expect(svc.applyAccessSheet).not.toHaveBeenCalled();
  });

  it('U13: preview renders each dealer block with its status and the sheet counts', async () => {
    renderDialog();
    await toPreview();
    expect(screen.getAllByText('BETA TILES SDN BHD').length).toBeGreaterThan(0);
    expect(screen.getByText(/^exact$/i)).toBeInTheDocument();
    expect(screen.getByText(/needs a pick/i)).toBeInTheDocument();
    expect(screen.getByText(/3 contacts in sheet/i)).toBeInTheDocument();
    expect(screen.getByText(/3 found in CRM/i)).toBeInTheDocument();
  });

  it('U11: Confirm all exact then Apply posts the file and the exact block ticked ids only', async () => {
    renderDialog();
    await toPreview();
    fireEvent.click(screen.getByRole('button', { name: /confirm all exact/i }));
    fireEvent.click(screen.getByRole('button', { name: /apply access/i }));
    await waitFor(() => expect(svc.applyAccessSheet).toHaveBeenCalledTimes(1));
    expect(svc.applyAccessSheet).toHaveBeenCalledWith(file, { 'alpha bath': ['a1', 'a2'] });
  });

  it('U15: the result step shows applied and skipped counts and offers Download result', async () => {
    renderDialog();
    await toPreview();
    fireEvent.click(screen.getByRole('button', { name: /confirm all exact/i }));
    fireEvent.click(screen.getByRole('button', { name: /apply access/i }));
    expect(await screen.findByText(/Applied 2 contacts/i)).toBeInTheDocument();
    expect(screen.getByText(/Skipped 1/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /download result/i })).toBeInTheDocument();
  });

  it('a refused file shows the error and stays on the upload step', async () => {
    svc.previewAccessSheet.mockRejectedValueOnce(new Error('The file has no Tags column.'));
    renderDialog();
    pickFile();
    fireEvent.click(screen.getByRole('button', { name: /^Preview/ }));
    await waitFor(() => expect(toastMock.error).toHaveBeenCalledWith(expect.stringContaining('The file has no Tags column.')));
    expect(screen.getByRole('button', { name: /^Preview/ })).toBeInTheDocument();
    expect(screen.queryByText('ALPHA BATH SDN BHD')).toBeNull();
  });

  it('U14b: a brands change from "every brand" renders that text and the after brand names', async () => {
    const withBrands = {
      ...PREVIEW,
      blocks: [
        {
          ...PREVIEW.blocks[0],
          contacts: [
            person('Ann', {
              changes: [{ facet: 'brands', before: 'every brand', after: ['SORENTO', 'CABANA'] }],
            }),
          ],
        },
        PREVIEW.blocks[1],
      ],
    };
    svc.previewAccessSheet.mockResolvedValueOnce(withBrands);
    renderDialog();
    await toPreview();
    if (!screen.queryByText(/every brand/i)) fireEvent.click(screen.getAllByText('ALPHA BATH SDN BHD')[0]);
    expect((await screen.findAllByText(/every brand/i)).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/SORENTO/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/CABANA/).length).toBeGreaterThan(0);
  });

  it('an account added through the customer search survives collapsing and reopening its dealer block, and Apply sends it', async () => {
    customerSvc.searchCustomersSelect.mockResolvedValue([
      { value: 'extra-1', label: 'EXTRA TRADING SDN BHD', description: '' },
    ]);
    renderDialog();
    await toPreview();
    const header = () => screen.getAllByText('BETA TILES SDN BHD')[0];
    if (!screen.queryByTestId('extra-search')) fireEvent.click(header());
    fireEvent.click(await screen.findByRole('button', { name: /EXTRA TRADING SDN BHD/ }));
    expect((await screen.findAllByText('EXTRA TRADING SDN BHD')).length).toBeGreaterThan(0);

    fireEvent.click(header()); // collapse
    await waitFor(() => expect(screen.queryByTestId('extra-search')).toBeNull());
    fireEvent.click(header()); // reopen
    expect((await screen.findAllByText('EXTRA TRADING SDN BHD')).length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole('button', { name: /confirm all exact/i }));
    fireEvent.click(screen.getByRole('button', { name: /apply access/i }));
    await waitFor(() => expect(svc.applyAccessSheet).toHaveBeenCalledTimes(1));
    expect(JSON.stringify(svc.applyAccessSheet.mock.calls[0][1])).toContain('extra-1');
  });

  it('a failed apply shows the message as a toast and stays on the preview step', async () => {
    svc.applyAccessSheet.mockRejectedValueOnce(new Error('Mocha is not in your companies.'));
    renderDialog();
    await toPreview();
    fireEvent.click(screen.getByRole('button', { name: /confirm all exact/i }));
    fireEvent.click(screen.getByRole('button', { name: /apply access/i }));
    await waitFor(() => expect(toastMock.error).toHaveBeenCalledWith(expect.stringContaining('Mocha is not in your companies.')));
    expect(screen.getByRole('button', { name: /apply access/i })).toBeInTheDocument();
    expect(screen.queryByText(/Import finished/i)).toBeNull();
  });

  it('U11: ticking a candidate in a pick block confirms the block and Apply sends it; unticking un-confirms', async () => {
    renderDialog();
    await toPreview();
    const header = () => screen.getAllByText('BETA TILES SDN BHD')[0];
    if (!screen.queryByRole('checkbox', { name: /link 300-b1/i })) fireEvent.click(header());
    const confirmBox = () => screen.getByRole('checkbox', { name: /confirm beta tiles/i });
    expect(confirmBox()).toHaveAttribute('aria-checked', 'false');

    fireEvent.click(await screen.findByRole('checkbox', { name: /link 300-b1/i }));
    await waitFor(() => expect(confirmBox()).toHaveAttribute('aria-checked', 'true'));
    fireEvent.click(screen.getByRole('button', { name: /apply access/i }));
    await waitFor(() => expect(svc.applyAccessSheet).toHaveBeenCalledTimes(1));
    expect(svc.applyAccessSheet).toHaveBeenLastCalledWith(file, { 'beta tiles': ['b1'] });
  });

  it('U11: unticking the last account of a pick block un-confirms it and Apply omits the block', async () => {
    renderDialog();
    await toPreview();
    const header = () => screen.getAllByText('BETA TILES SDN BHD')[0];
    if (!screen.queryByRole('checkbox', { name: /link 300-b1/i })) fireEvent.click(header());
    const link = await screen.findByRole('checkbox', { name: /link 300-b1/i });
    fireEvent.click(link);
    await waitFor(() => expect(screen.getByRole('checkbox', { name: /confirm beta tiles/i })).toHaveAttribute('aria-checked', 'true'));
    fireEvent.click(screen.getByRole('checkbox', { name: /link 300-b1/i }));
    await waitFor(() => expect(screen.getByRole('checkbox', { name: /confirm beta tiles/i })).toHaveAttribute('aria-checked', 'false'));
    fireEvent.click(screen.getByRole('button', { name: /apply access/i }));
    await waitFor(() => expect(svc.applyAccessSheet).toHaveBeenCalledTimes(1));
    expect(svc.applyAccessSheet).toHaveBeenLastCalledWith(file, {});
  });

  // Round 4: a pick block can carry pre-ticked EXACT accounts of another company (U10).
  const MIXED = {
    ...PREVIEW,
    blocks: [
      PREVIEW.blocks[0],
      {
        ...PREVIEW.blocks[1],
        accounts: [
          acct('x1', { company_code: 'ZZX', customer_code: '300-x1' }),
          acct('x2', { company_code: 'ZZX', customer_code: '300-x2' }),
          acct('c1', { match: 'candidate', score: 0.9, proposed: false, customer_code: '300-c1' }),
          acct('c2', { match: 'candidate', score: 0.8, proposed: false, customer_code: '300-c2' }),
        ],
      },
    ],
  };

  async function openMixed() {
    svc.previewAccessSheet.mockResolvedValueOnce(MIXED);
    renderDialog();
    await toPreview();
    if (!screen.queryByRole('checkbox', { name: /link 300-x1/i })) fireEvent.click(screen.getAllByText('BETA TILES SDN BHD')[0]);
    await screen.findByRole('checkbox', { name: /link 300-x1/i });
  }
  const confirmBox = () => screen.getByRole('checkbox', { name: /confirm beta tiles/i });
  const apply = async () => {
    fireEvent.click(screen.getByRole('button', { name: /apply access/i }));
    await waitFor(() => expect(svc.applyAccessSheet).toHaveBeenCalledTimes(1));
    return svc.applyAccessSheet.mock.calls[0][1] as Record<string, string[]>;
  };

  it('R4a: unticking a pre-ticked exact account never confirms a pick block', async () => {
    await openMixed();
    fireEvent.click(screen.getByRole('checkbox', { name: /link 300-x1/i }));
    expect(confirmBox()).toHaveAttribute('aria-checked', 'false');
    expect(await apply()).not.toHaveProperty('beta tiles');
  });

  it('R4b: ticking a candidate confirms with candidate + still-ticked exact; unticking it un-confirms', async () => {
    await openMixed();
    fireEvent.click(screen.getByRole('checkbox', { name: /link 300-c1/i }));
    await waitFor(() => expect(confirmBox()).toHaveAttribute('aria-checked', 'true'));
    fireEvent.click(screen.getByRole('checkbox', { name: /link 300-c1/i }));
    await waitFor(() => expect(confirmBox()).toHaveAttribute('aria-checked', 'false'));
    expect(await apply()).not.toHaveProperty('beta tiles');
  });

  it('R4b2: the confirmed payload holds the candidate and the exact accounts', async () => {
    await openMixed();
    fireEvent.click(screen.getByRole('checkbox', { name: /link 300-c1/i }));
    await waitFor(() => expect(confirmBox()).toHaveAttribute('aria-checked', 'true'));
    expect([...(await apply())['beta tiles']].sort()).toEqual(['c1', 'x1', 'x2']);
  });

  it('R4c: the explicit Confirm box on a pick block sends its pre-ticked exact accounts', async () => {
    await openMixed();
    fireEvent.click(confirmBox());
    expect([...(await apply())['beta tiles']].sort()).toEqual(['x1', 'x2']);
  });

  // BULK-ACCESS-PREVIEW (owner 27 Oct): every change visible, per contact, nothing truncated.
  const FULL = {
    ...PREVIEW,
    blocks: [
      {
        ...PREVIEW.blocks[0],
        companies: ['SRT', 'MCH'],
        accounts: [
          acct('m1', { company_code: 'MCH', customer_code: '300-Y055', links_to: ['Wong'] }),
          acct('s1', { customer_code: '300-Y065', links_to: ['Shi', 'Wong'] }),
          acct('z1', { company_code: 'ZZX', customer_code: '300-Z001', links_to: [] }),
        ],
        contacts: [
          person('Shi', {
            changes: [
              { facet: 'access_types', before: ['end_user'], after: ['cabana_dealer', 'dealer', 'end_user'] },
              { facet: 'customers', before: ['300-Y055 YOO A'], after: ['300-Y055 YOO A', '300-Y065 YOO B'] },
            ],
            outside_links: ['300-Y055 YOO A (MCH)'],
          }),
          person('Wong', {
            companies: ['SRT', 'MCH'],
            template: 'SRT+MCH owner',
            warnings: ['holds_more'],
            holds_more_items: [
              { facet: 'brands', items: ['BRAVAT'] },
              { facet: 'stock_locations', items: ['KCH'] },
            ],
          }),
        ],
      },
      PREVIEW.blocks[1],
    ],
  };

  async function openFull() {
    svc.previewAccessSheet.mockResolvedValueOnce(FULL);
    renderDialog();
    await toPreview();
    if (!screen.queryByTestId('contact-Shi')) fireEvent.click(screen.getAllByText('ALPHA BATH SDN BHD')[0]);
    await screen.findByTestId('contact-Shi');
  }

  it('P5: each changed facet lists before and after one item per line, added items marked', async () => {
    await openFull();
    const panel = screen.getByTestId('contact-Shi');
    const added = within(panel).getAllByTestId('added-item').map((n) => n.textContent);
    expect(added).toEqual(expect.arrayContaining(['cabana_dealer', 'dealer', '300-Y065 YOO B']));
    expect(added).not.toContain('end_user');
    // each item is its own element, never a joined line
    expect(within(panel).getAllByText('end_user')).toHaveLength(2);
    expect(within(panel).queryByText(/cabana_dealer, dealer/)).toBeNull();
    expect(panel.querySelector('.truncate')).toBeNull();
  });

  it('P5: unchanged facets are named in one No change line', async () => {
    await openFull();
    expect(within(screen.getByTestId('contact-Shi')).getByText(/^No change:/)).toHaveTextContent(/Segments/);
  });

  it('P6: Holds more than the template lists the extra items per facet', async () => {
    await openFull();
    const panel = screen.getByTestId('contact-Wong');
    expect(within(panel).getByText(/Holds more than the template/i)).toBeInTheDocument();
    expect(within(panel).getByText('Brands: BRAVAT')).toBeInTheDocument();
    expect(within(panel).getByText('Locations: KCH')).toBeInTheDocument();
  });

  it('P4: links outside the row companies show as an info line on that contact only', async () => {
    await openFull();
    expect(within(screen.getByTestId('contact-Shi')).getByText(/Linked outside this row's companies/i)).toBeInTheDocument();
    expect(within(screen.getByTestId('contact-Shi')).getByText('300-Y055 YOO A (MCH)')).toBeInTheDocument();
    expect(within(screen.getByTestId('contact-Wong')).queryByText(/Linked outside/i)).toBeNull();
  });

  it('P3: the accounts table names who each account links to, or Nobody', async () => {
    await openFull();
    const row = (code: string) => screen.getByRole('checkbox', { name: `Link ${code}` }).closest('tr') as HTMLElement;
    expect(within(row('300-Y065')).getByText('Shi')).toBeInTheDocument();
    expect(within(row('300-Y065')).getByText('Wong')).toBeInTheDocument();
    expect(within(row('300-Y055')).queryByText('Shi')).toBeNull();
    expect(within(row('300-Z001')).getByText('Nobody')).toBeInTheDocument();
  });

  // BULK-ACCESS-PREVIEW page: pagination over the dealer cards, selection kept across pages.
  const many = (n: number) => ({
    ...PREVIEW,
    counts: { ...PREVIEW.counts, blocks: n, blocks_exact: n, blocks_pick: 0 },
    blocks: Array.from({ length: n }, (_, i) => ({
      ...PREVIEW.blocks[0],
      key: `dealer ${i + 1}`,
      dealer: `DEALER ${String(i + 1).padStart(2, '0')} SDN BHD`,
      accounts: [acct(`d${i + 1}`, { customer_code: `300-D${i + 1}` })],
      contacts: [person(`Person ${i + 1}`)],
    })),
  });

  it('page: the preview shows 20 dealer cards a page with Prev / Page X of Y / Next', async () => {
    svc.previewAccessSheet.mockResolvedValueOnce(many(25));
    renderDialog();
    pickFile();
    fireEvent.click(screen.getByRole('button', { name: /^Preview/ }));
    await screen.findByText('DEALER 01 SDN BHD');
    expect(screen.getByText('DEALER 20 SDN BHD')).toBeInTheDocument();
    expect(screen.queryByText('DEALER 21 SDN BHD')).toBeNull();
    expect(screen.getAllByText(/Page 1 of 2/)).toHaveLength(2);
    fireEvent.click(screen.getAllByRole('button', { name: 'Next page' })[0]); // pager above and below the cards
    expect(await screen.findByText('DEALER 21 SDN BHD')).toBeInTheDocument();
    expect(screen.queryByText('DEALER 01 SDN BHD')).toBeNull();
    expect(screen.getAllByText(/Page 2 of 2/)).toHaveLength(2);
  });

  it('page: a dealer confirmed on page 2 and Confirm all exact on page 1 are both sent', async () => {
    const data = many(25);
    data.blocks[22] = { ...data.blocks[22], status: 'pick' };
    svc.previewAccessSheet.mockResolvedValueOnce(data);
    renderDialog();
    pickFile();
    fireEvent.click(screen.getByRole('button', { name: /^Preview/ }));
    await screen.findByText('DEALER 01 SDN BHD');
    fireEvent.click(screen.getAllByRole('button', { name: 'Next page' })[0]); // pager above and below the cards
    fireEvent.click(await screen.findByRole('checkbox', { name: /confirm DEALER 23/i }));
    fireEvent.click(screen.getAllByRole('button', { name: 'Previous page' })[0]);
    await screen.findByText('DEALER 01 SDN BHD');
    fireEvent.click(screen.getByRole('button', { name: /confirm all exact/i }));
    fireEvent.click(screen.getByRole('button', { name: /apply access/i }));
    await waitFor(() => expect(svc.applyAccessSheet).toHaveBeenCalledTimes(1));
    const sent = svc.applyAccessSheet.mock.calls[0][1] as Record<string, string[]>;
    expect(Object.keys(sent)).toHaveLength(25);
    expect(sent['dealer 23']).toEqual(['d23']);
  });

  it('page: Back from the preview returns to the upload step with the file kept', async () => {
    renderDialog();
    await toPreview();
    fireEvent.click(screen.getByRole('button', { name: /^Back$/ }));
    expect((screen.getByRole('button', { name: /^Preview/ }) as HTMLButtonElement).disabled).toBe(false);
  });

  it('page: Done on the result goes back to the contacts list', async () => {
    renderDialog();
    await toPreview();
    fireEvent.click(screen.getByRole('button', { name: /confirm all exact/i }));
    fireEvent.click(screen.getByRole('button', { name: /apply access/i }));
    fireEvent.click(await screen.findByRole('button', { name: /^Done$/ }));
    expect(routerMock.push).toHaveBeenCalledWith('/user-management/contact-access-agents');
  });

  it('P3: an unticked account links to Nobody, as Apply will do', async () => {
    await openFull();
    const row = () => screen.getByRole('checkbox', { name: 'Link 300-Y065' }).closest('tr') as HTMLElement;
    fireEvent.click(screen.getByRole('checkbox', { name: 'Link 300-Y065' }));
    await waitFor(() => expect(within(row()).getByText('Nobody')).toBeInTheDocument());
    expect(within(row()).queryByText('Shi')).toBeNull();
  });

  it('a11y: the Before / After labels stay readable to a screen reader at every width', async () => {
    await openFull();
    const labels = within(screen.getByTestId('contact-Shi')).getAllByText('Before');
    for (const l of labels) expect(l.className).not.toMatch(/(^|\s)sm:hidden(\s|$)/);
  });

  it('page: changing page from the pager below the cards brings the first card into view', async () => {
    svc.previewAccessSheet.mockResolvedValueOnce(many(25));
    const spy = vi.spyOn(Element.prototype, 'scrollIntoView').mockImplementation(() => {});
    renderDialog();
    pickFile();
    fireEvent.click(screen.getByRole('button', { name: /^Preview/ }));
    await screen.findByText('DEALER 01 SDN BHD');
    spy.mockClear();
    const next = screen.getAllByRole('button', { name: 'Next page' });
    fireEvent.click(next[next.length - 1]);
    await screen.findByText('DEALER 21 SDN BHD');
    expect(spy).toHaveBeenCalled();
    spy.mockRestore();
  });

  it('P8 (crew ruling 27 Oct): Confirm all exact confirms a Rows disagree card and its pill stays', async () => {
    const disagree = {
      ...PREVIEW,
      blocks: [{ ...PREVIEW.blocks[0], warnings: ['rows_disagree'] }, PREVIEW.blocks[1]],
    };
    svc.previewAccessSheet.mockResolvedValueOnce(disagree);
    renderDialog();
    await toPreview();
    expect(screen.getByText('Rows disagree on companies')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /confirm all exact/i }));
    fireEvent.click(screen.getByRole('button', { name: /apply access/i }));
    await waitFor(() => expect(svc.applyAccessSheet).toHaveBeenCalledTimes(1));
    expect(svc.applyAccessSheet).toHaveBeenCalledWith(file, { 'alpha bath': ['a1', 'a2'] });
  });
});
