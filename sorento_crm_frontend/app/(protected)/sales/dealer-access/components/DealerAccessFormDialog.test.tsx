/**
 * F4 / F5: the add and edit form. Services mocked; the dialog, hooks and rows are real.
 * DEALER-ACCESS-NAMES (UAC `documentation/plans/contacts/dealer-access-names-14nov-acceptance-criteria.md`):
 * N1.4 account options by name, N2.5 the read-only dialog, N4.1 the Company multi-select, N4.3 the "already has
 * access" refusal with its Edit / Show link, N5.3 the Respond.io failure message with Try again. Where the server's
 * answer matters (N4.3, N5.3 Try again) the real service runs against a mocked `apiFetch`.
 */
import React from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render as rtlRender, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { DealerAccessGrantError, type DealerAccessRow } from '@/services/dealerAccessService';
import DealerAccessFormDialog from './DealerAccessFormDialog';

function render(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return rtlRender(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() }));
vi.mock('@/lib/toast', () => ({ toast }));

const svc = vi.hoisted(() => ({
  getAccounts: vi.fn(),
  grant: vi.fn(),
  updatePerson: vi.fn(),
}));
vi.mock('@/services/dealerAccessService', async (orig) => ({
  ...(await orig<typeof import('@/services/dealerAccessService')>()),
  getAccounts: svc.getAccounts,
  grant: svc.grant,
  updatePerson: svc.updatePerson,
}));

const companies = vi.hoisted(() => ({ options: [{ value: 'SRT', label: 'Sorento' }] }));
vi.mock('../hooks/useMyDealerCompanies', () => ({
  useMyDealerCompanies: () => ({ options: companies.options, isLoading: false }),
}));

const api = vi.hoisted(() => ({ apiFetch: vi.fn() }));
vi.mock('@/lib/api', async (orig) => ({
  ...(await orig<typeof import('@/lib/api')>()),
  apiFetch: api.apiFetch,
}));

vi.mock('@/components/common/SearchableSelect', () => ({
  SearchableSelect: (props: {
    id?: string;
    'aria-label'?: string;
    value: string;
    onChange: (v: string) => void;
    options?: { value: string; label: string }[];
  }) => (
    <select
      id={props.id}
      aria-label={props['aria-label']}
      value={props.value}
      onChange={(e) => props.onChange(e.target.value)}
    >
      {(props.options ?? []).map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  ),
}));
vi.mock('@/components/common/SearchableMultiSelect', () => ({
  SearchableMultiSelect: (props: {
    id?: string;
    'aria-label'?: string;
    value: string[];
    onChange: (v: string[]) => void;
    options?: { value: string; label: string }[];
  }) => (
    <select
      id={props.id}
      aria-label={props['aria-label']}
      multiple
      value={props.value}
      onChange={(e) => props.onChange(Array.from(e.target.selectedOptions).map((o) => o.value))}
    >
      {(props.options ?? []).map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  ),
}));
vi.mock('@/components/common/PhoneInput', () => ({
  PhoneInput: (props: {
    id?: string;
    value: string;
    onChange: (v: string, meta: { valid: boolean; country: string }) => void;
  }) => (
    <input
      id={props.id}
      aria-label={props.id}
      value={props.value}
      onChange={(e) => props.onChange(e.target.value, { valid: true, country: 'MY' })}
    />
  ),
}));

const ACCOUNTS = [
  { id: 'a1', code: '300-N034', name: 'CHO*** (A/C I)' },
  { id: 'a2', code: '300-N035', name: 'CHO*** (A/C II)' },
];

beforeEach(() => {
  vi.clearAllMocks();
  companies.options = [{ value: 'SRT', label: 'Sorento' }];
  svc.getAccounts.mockResolvedValue(ACCOUNTS);
  api.apiFetch.mockImplementation(async () => json({}));
});

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

async function realService() {
  return vi.importActual<typeof import('@/services/dealerAccessService')>('@/services/dealerAccessService');
}

/** Picks options of a stubbed multi-select by value. */
function pick(select: HTMLElement, values: string[]) {
  for (const o of Array.from((select as HTMLSelectElement).options)) o.selected = values.includes(o.value);
  fireEvent.change(select);
}

/** One person typed into the first row. */
function typePerson(name: string, phone: string) {
  const row = screen.getByTestId('person-row-0');
  fireEvent.change(within(row).getByLabelText('Name'), { target: { value: name } });
  fireEvent.change(within(row).getByRole('textbox', { name: /person-phone/ }), { target: { value: phone } });
}

describe('DealerAccessFormDialog - add', () => {
  it('shows a refused row under that row and keeps what was typed', async () => {
    svc.grant.mockRejectedValue(
      new DealerAccessGrantError('Some people were refused.', {
        1: 'This number belongs to a staff member.',
      }),
    );
    render(<DealerAccessFormDialog open onOpenChange={vi.fn()} />);

    await waitFor(() => expect(screen.getByRole('option', { name: /300-N034/ })).toBeTruthy());
    fireEvent.change(document.getElementById('dealer-access-accounts')!, {
      target: { value: 'a1' },
    });
    fireEvent.click(screen.getByRole('option', { name: /300-N034/ }));
    fireEvent.click(screen.getByRole('button', { name: /add person/i }));

    const rows = [screen.getByTestId('person-row-0'), screen.getByTestId('person-row-1')];
    const values = [
      ['Person A', '+60120000001'],
      ['Person B', '+60120000002'],
    ];
    rows.forEach((row, i) => {
      fireEvent.change(within(row).getByLabelText('Name'), { target: { value: values[i][0] } });
      fireEvent.change(within(row).getByRole('textbox', { name: /person-phone/ }), {
        target: { value: values[i][1] },
      });
    });

    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() =>
      expect(
        within(screen.getByTestId('person-row-1')).getByText('This number belongs to a staff member.'),
      ).toBeTruthy(),
    );
    expect(within(screen.getByTestId('person-row-0')).queryByRole('alert')).toBeNull();
    expect((within(screen.getByTestId('person-row-0')).getByLabelText('Name') as HTMLInputElement).value).toBe(
      'Person A',
    );
    expect((within(screen.getByTestId('person-row-1')).getByLabelText('Name') as HTMLInputElement).value).toBe(
      'Person B',
    );
    // N4.1: the body sends `companies` (was the single `company`).
    expect(svc.grant).toHaveBeenCalledWith(
      expect.objectContaining({
        companies: ['SRT'],
        account_ids: ['a1'],
        people: [
          { name: 'Person A', phone: '+60120000001', role: 'employee' },
          { name: 'Person B', phone: '+60120000002', role: 'employee' },
        ],
      }),
    );
    // Shown under its row, so not also toasted.
    expect(toast.error).not.toHaveBeenCalled();
  });
});

describe('DealerAccessFormDialog - edit', () => {
  const person: DealerAccessRow = {
    contact_id: 'c1',
    name: 'Person C',
    phone: '+60 17-000 0003',
    company: 'SRT',
    company_name: 'Sorento',
    accounts: [{ ...ACCOUNTS[1], link_id: 'l1', mine: true }],
    access: 'owner',
    owner_tag: 'Sorento Business Owner',
    editable: true,
    in_respond: true,
  } as unknown as DealerAccessRow;

  it('keeps company and phone read-only and shows a refusal under the form', async () => {
    svc.updatePerson.mockRejectedValue(
      new Error('This person also has access through another account; ask the office to change their level.'),
    );
    render(<DealerAccessFormDialog open onOpenChange={vi.fn()} person={person} />);

    expect(screen.getByText('Sorento')).toBeTruthy();
    expect(screen.getByText('+60 17-000 0003')).toBeTruthy();
    expect(screen.queryByLabelText('Name')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() =>
      expect(screen.getByText(/ask the office to change their level/)).toBeTruthy(),
    );
    expect(svc.updatePerson).toHaveBeenCalledWith('c1', {
      company: 'SRT',
      role: 'owner',
      account_ids: ['a2'],
    });
    // The form stays open.
    expect(screen.getByRole('button', { name: 'Save' })).toBeTruthy();
  });
});

describe('DealerAccessFormDialog - DEALER-ACCESS-NAMES', () => {
  it('N1.4 the My accounts options read "<name> (<code>)"', async () => {
    render(<DealerAccessFormDialog open onOpenChange={vi.fn()} />);
    await waitFor(() => expect(screen.getByRole('option', { name: 'CHO*** (A/C I) (300-N034)' })).toBeTruthy());
    expect(screen.getByRole('option', { name: 'CHO*** (A/C II) (300-N035)' })).toBeTruthy();
  });

  it('N2.5 a non-editable person opens read-only: fields shown, no Save', async () => {
    const chong = {
      contact_id: 'c2',
      name: 'Chong Test',
      phone: '+60 12-000 0002',
      company: 'SRT',
      company_name: 'Sorento',
      accounts: [{ id: 'b1', code: '300-B001', name: 'Kedai Lain', mine: false }],
      access: 'employee',
      owner_tag: null,
      editable: false,
      in_respond: true,
    } as unknown as DealerAccessRow;
    render(<DealerAccessFormDialog open onOpenChange={vi.fn()} person={chong} />);

    expect(screen.getByText('Sorento')).toBeTruthy();
    expect(screen.getByText('+60 12-000 0002')).toBeTruthy();
    expect(screen.getAllByText(/Kedai Lain/).length).toBeGreaterThan(0);
    expect(screen.getAllByText('Employee').length).toBeGreaterThan(0);
    expect(screen.queryByRole('button', { name: 'Save' })).toBeNull();
  });

  it('N4.1 Company is a multi-select and the body sends every picked company with accounts across them', async () => {
    companies.options = [
      { value: 'SRT', label: 'Sorento' },
      { value: 'MCH', label: 'Mocha' },
    ];
    svc.getAccounts.mockImplementation(async (company: string) =>
      company === 'MCH'
        ? [{ id: 'm1', code: '300-M001', name: 'Kedai Test Satu' }]
        : [{ id: 'a1', code: '300-A004', name: 'Kedai Test Satu' }],
    );
    svc.grant.mockResolvedValue({
      rows: [{ index: 0, contact_id: 'c5', created: true, respond: 'ok', respond_error: null }],
    });
    render(<DealerAccessFormDialog open onOpenChange={vi.fn()} />);

    const company = screen.getByRole('listbox', { name: 'Company' });
    pick(company, ['SRT', 'MCH']);
    await waitFor(() => expect(screen.getByRole('option', { name: /300-M001/ })).toBeTruthy());
    await waitFor(() => expect(screen.getByRole('option', { name: /300-A004/ })).toBeTruthy());
    pick(screen.getByRole('listbox', { name: 'My accounts' }), ['a1', 'm1']);
    typePerson('Ali Test', '+60120000001');
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(svc.grant).toHaveBeenCalled());
    const body = svc.grant.mock.calls[0][0] as { companies: string[]; account_ids: string[] };
    expect([...body.companies].sort()).toEqual(['MCH', 'SRT']);
    expect([...body.account_ids].sort()).toEqual(['a1', 'm1']);
  });

  async function refuse(contact: { id: string; name: string; company: string; editable: boolean }) {
    const real = await realService();
    svc.grant.mockImplementation(real.grant);
    api.apiFetch.mockImplementation(async (url: string) => {
      if (String(url).includes('/grant')) {
        return json(
          {
            message: 'Some people cannot be added.',
            detail: null,
            code: 'VALIDATION_ERROR',
            details: { rows: [{ index: 0, error: `${contact.name} already has access.`, contact }] },
          },
          422,
        );
      }
      return json({ rows: [], total: 0 });
    });
    render(<DealerAccessFormDialog open onOpenChange={vi.fn()} />);
    await waitFor(() => expect(screen.getByRole('option', { name: /300-N034/ })).toBeTruthy());
    pick(screen.getByRole('listbox', { name: 'My accounts' }), ['a1']);
    typePerson('Typed Name', '+60120000001');
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() =>
      expect(
        within(screen.getByTestId('person-row-0')).getByText(`${contact.name} already has access.`),
      ).toBeTruthy(),
    );
  }

  it('N4.3 an editable "already has access" row offers "Edit <Name>" that opens that person', async () => {
    await refuse({ id: 'c7', name: 'Ali Test', company: 'SRT', editable: true });
    const link = within(screen.getByTestId('person-row-0')).getByText('Edit Ali Test');
    expect(within(screen.getByTestId('person-row-0')).queryByText('Show Ali Test')).toBeNull();
    fireEvent.click(link);
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Ali Test' })).toBeTruthy());
  });

  it('N4.3 a non-editable "already has access" row offers "Show <Name>" that opens it read-only', async () => {
    await refuse({ id: 'c8', name: 'Chong Test', company: 'SRT', editable: false });
    const link = within(screen.getByTestId('person-row-0')).getByText('Show Chong Test');
    expect(within(screen.getByTestId('person-row-0')).queryByText('Edit Chong Test')).toBeNull();
    fireEvent.click(link);
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Chong Test' })).toBeTruthy());
    expect(screen.queryByRole('button', { name: 'Save' })).toBeNull();
  });

  it('N4.3 "another company" refusal shows its text with no link', async () => {
    svc.grant.mockRejectedValue(
      new DealerAccessGrantError('Some people cannot be added.', {
        0: 'This number already has access in another company.',
      }),
    );
    render(<DealerAccessFormDialog open onOpenChange={vi.fn()} />);
    await waitFor(() => expect(screen.getByRole('option', { name: /300-N034/ })).toBeTruthy());
    pick(screen.getByRole('listbox', { name: 'My accounts' }), ['a1']);
    typePerson('Typed Name', '+60120000001');
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));
    const row = screen.getByTestId('person-row-0');
    await waitFor(() => expect(within(row).getByText('This number already has access in another company.')).toBeTruthy());
    expect(within(row).queryByText(/^(Edit|Show) /)).toBeNull();
  });

  it('N5.3 a Respond.io failure says "Access given. Not yet in Respond.io: <reason>." with Try again', async () => {
    const onOpenChange = vi.fn();
    svc.grant.mockResolvedValue({
      rows: [
        {
          index: 0,
          contact_id: 'c9',
          created: true,
          notes: [],
          respond: 'failed',
          respond_error: 'Respond.io did not answer',
        },
      ],
    });
    api.apiFetch.mockImplementation(async () => json({ respond: 'ok', respond_error: null }));
    render(<DealerAccessFormDialog open onOpenChange={onOpenChange} />);
    await waitFor(() => expect(screen.getByRole('option', { name: /300-N034/ })).toBeTruthy());
    pick(screen.getByRole('listbox', { name: 'My accounts' }), ['a1']);
    typePerson('Dan Test', '+60120000003');
    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() =>
      expect(screen.getByText('Access given. Not yet in Respond.io: Respond.io did not answer.')).toBeTruthy(),
    );
    // Not silent: the dialog stays to say it.
    expect(onOpenChange).not.toHaveBeenCalledWith(false);
    fireEvent.click(screen.getByRole('button', { name: /try again/i }));
    await waitFor(() =>
      expect(
        api.apiFetch.mock.calls.some(
          ([url, init]) =>
            /\/sales\/dealer-access\/people\/c9\/respond$/.test(String(url)) &&
            String((init as RequestInit | undefined)?.method).toUpperCase() === 'POST',
        ),
      ).toBe(true),
    );
  });
});
